#!/usr/bin/env python3
"""Recursive text-only website mirror via trafilatura.

BFS-crawls one or more seed URLs (same-host scoping per seed), extracts each page
to Markdown, and appends it to an output file.
Public pages only, robots.txt-respecting, rate-limited (one request per --delay,
enforced globally across worker threads). Auto-installs trafilatura and lxml if
missing. Uncapped by default; writes incrementally so partial output is usable and
the run is resumable (per-host state file next to the output).

When robots.txt cannot be read (network error / timeout), the host is treated as
allow-all so the crawl proceeds rather than silently producing zero pages.

Usage:
  python text_mirror.py [URL ...] [--out FILE] [--delay SECS | --req-per-sec N]
                        [--max-depth N] [--max-pages N] [--serve] [--clone [--clone-dir D]]
                        [--shard-index I --shard-count N] [--no-prefer-llms]
Examples:
  python text_mirror.py https://wiki.example.org/
  python text_mirror.py --serve --out extension_mirror.md
"""
import argparse
import concurrent.futures
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import zlib
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_clone  # noqa: E402 -- same-directory module, stdlib-only at import

# The clean-acquisition path: many docs hosts publish llms-full.txt / llms.txt
# + per-page .md, which keep the code blocks and tables trafilatura drops.
# Stdlib-only and optional -- a box without the hub checkout just crawls.
try:
    sys.path.insert(0, os.path.expanduser("~/.global-ai-hub/scripts"))
    import llms_acquire  # noqa: E402
except Exception:  # noqa: BLE001
    llms_acquire = None


def ensure_deps():
    def missing():
        return [pkg for mod, pkg in (("trafilatura", "trafilatura"), ("lxml", "lxml"))
                if importlib.util.find_spec(mod) is None]

    need = missing()
    if not need:
        return
    print(f"[bootstrap] installing missing packages: {', '.join(need)}", flush=True)
    strategies = (
        ["--quiet"],
        ["--quiet", "--user"],
        ["--quiet", "--user", "--break-system-packages"],
        ["--quiet", "--break-system-packages"],
    )
    for extra in strategies:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *extra, *need])
        except subprocess.CalledProcessError:
            continue
        importlib.invalidate_caches()
        if not missing():
            return
    sys.exit("[bootstrap] ERROR: could not install deps.")


ensure_deps()
import trafilatura  # noqa: E402
from lxml import html as LH  # noqa: E402
from trafilatura.settings import use_config  # noqa: E402

UA = "trafilatura-text-mirror/1.0 (+public-archive)"
CFG = use_config()
CFG.set("DEFAULT", "USER_AGENTS", UA)
CFG.set("DEFAULT", "DOWNLOAD_TIMEOUT", "30")

PORT = 8765
MAX_WORKERS = 10
ROBOTS_TIMEOUT = 30
STATE_SAVE_INTERVAL = 30  # seconds between state-file writes
SEP = "=" * 90

SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".css",
            ".js", ".pdf", ".zip", ".gz", ".tar", ".mp4", ".mp3", ".avi",
            ".woff", ".woff2", ".ttf", ".rss", ".atom")
SKIP_SUBSTR = ("/login", "/register", "/account", "/members/", "/lost-password",
               "/whats-new/", "/misc/", "/goto/", "/find-new/", "/attachments/",
               "/logout", "oauth", "action=", "oldid=", "diff=", "special:",
               "printable=", "veaction=", "redlink", "feed=", "&do=", "/help/")

LOG_FILE = None
DEFAULT_OUT_FILE = None
PREFER_LLMS = True  # try llms-full.txt / llms.txt before crawling (--no-prefer-llms)

# On-demand single-page distillation (Chrome extension "Distill This Page"):
# extract -> distill_offline.py (semantic funnel) -> docset_indexer.py (backend
# save) -> return the distilled points to the extension. Runs in a background
# thread per job since the semantic embed step takes real seconds-to-minutes,
# not something an HTTP handler should block on.
DISTILL_SCRATCH_DIR = os.path.expanduser(
    "~/.claude/skills/web-text-mirror/text-mirror/_distill_scratch")
DISTILL_SCRIPT = os.path.expanduser("~/dev/distillers/distill_offline.py")
HUB_VENV_PY = os.path.expanduser("~/.global-ai-hub/.venv/bin/python")
INDEXER_SCRIPT = os.path.expanduser("~/.global-ai-hub/scripts/docset_indexer.py")
DISTILL_JOBS = {}
DISTILL_JOBS_LOCK = threading.Lock()

# Multi-box crawl sharding: SHARD_COUNT==1 (default) is the unsharded,
# fully-backward-compatible path. When >1, this process only fetches URLs it
# owns (see owns()) and relies on merge_siblings() to learn what sibling
# shards (on other boxes) have discovered/crawled, via their state files --
# which sync over via Syncthing since text-mirror/ is shared across boxes.
SHARD_INDEX = 0
SHARD_COUNT = 1
MIRROR_LOCK = threading.Lock()       # guards output file + SAVED_URLS/_SAVED_SET
LOG_LOCK = threading.Lock()          # guards log file appends
STATE_LOCK = threading.Lock()        # serializes state-file writes
CRAWL_START_LOCK = threading.Lock()  # single-flight guard for /crawl
SAVED_URLS = []                      # insertion-ordered, exposed via /list
_SAVED_SET = set()                   # O(1) membership companion to SAVED_URLS
CRAWL_ACTIVE = False
CRAWL_CANCEL = False
CRAWL_STATS = {
    'discovered': 0,
    'downloaded': 0,
    'in_queue': 0
}

# crawl-to-llms-txt: single-flight-with-queue for the (long, LLM-driven) /crawl2llms
# skill run, entirely separate from the plain trafilatura crawl above -- a second
# tab hitting the button while one is running queues instead of racing it.
CRAWL_LLMS_LOCK = threading.Lock()
CRAWL_LLMS_ACTIVE = False
CRAWL_LLMS_CURRENT = None   # {"url", "started_at"} while a job is running, else None
CRAWL_LLMS_QUEUE = []       # FIFO of {"url", "queued_at"} waiting behind the current job
CRAWL_LLMS_HISTORY = []     # last _CRAWL_LLMS_HISTORY_MAX finished jobs, newest last
_CRAWL_LLMS_HISTORY_MAX = 20
CRAWL_LLMS_OUT_ROOT = None  # set in main(): where each job's llms.txt family lands
_CRAWL_LLMS_TIMEOUT = 3600  # a hung `claude -p` must not wedge the queue forever

# Global fetch rate limiter (shared across worker threads).
_RATE_LOCK = threading.Lock()
_next_fetch = 0.0


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if LOG_FILE:
        with LOG_LOCK, open(LOG_FILE, "a") as f:
            f.write(line + "\n")


def parse_master_points(master_text):
    """Parse a distill_offline.py `_master.md` (see its cmd_bulk Stage 3
    writer) into [{category, text, count}]. Format per line:
    '- {text} _{src1, src2...}_[ x{count}]'."""
    points = []
    category = "Statements"
    for line in master_text.splitlines():
        if line.startswith("## "):
            category = line[3:].strip()
            continue
        if not line.startswith("- "):
            continue
        body = line[2:].rstrip()
        m = re.search(r"\s\[x(\d+)\]$", body)
        count = int(m.group(1)) if m else 1
        if m:
            body = body[:m.start()]
        m2 = re.search(r"\s_(.*)_$", body)
        if m2:
            body = body[:m2.start()]
        points.append({"category": category, "text": body.strip(), "count": count})
    return points


def _throttle(delay):
    """Block until at least `delay` seconds have elapsed since the last fetch."""
    global _next_fetch
    if delay <= 0:
        return
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _next_fetch - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _next_fetch = now + delay


def norm(url):
    return urldefrag(url)[0].strip()


def norm_host(netloc):
    """Normalize a netloc for same-site comparison: lowercase, drop userinfo and
    default ports so a seed redirect to a differently-cased host or an explicit
    :80/:443 does not collapse the crawl."""
    netloc = netloc.lower()
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif netloc.endswith(":443"):
        netloc = netloc[:-4]
    return netloc


def wanted(url, host):
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or norm_host(p.netloc) != host:
        return False
    low = url.lower()
    if low.endswith(SKIP_EXT):
        return False
    return not any(s in low for s in SKIP_SUBSTR)


def get_robots(host, scheme="https"):
    """robots.txt for `host`, fetched with OUR user agent, `scheme` first and
    the other scheme as a fallback.

    RobotFileParser.read() calls urlopen() with no headers, so robots.txt goes
    out as "Python-urllib/3.x". WAFs commonly 403 that UA -- and read() maps a
    403 to disallow_all, so can_fetch() then returns False for EVERY url. The
    crawl logs robots-skip per page and finishes with zero pages, on a site
    whose robots.txt actually allows everything. Fetching it ourselves also
    means we identify consistently: the same UA asks for the rules it obeys.

    Status handling follows RFC 9309: 4xx means the file is unavailable, which
    means no restrictions; 5xx means assume complete disallow. A transport
    failure on both schemes is treated as unavailable (allow-all) so a single
    unreachable robots.txt does not zero out the whole crawl."""
    last_error = None
    other = "http" if scheme == "https" else "https"
    for sch in (scheme, other):
        url = f"{sch}://{host}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(url)
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=ROBOTS_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except HTTPError as e:
            if 400 <= e.code < 500:
                log(f"robots {url}: HTTP {e.code} — unavailable, so no rules")
                rp.allow_all = True
                return rp
            log(f"robots {url}: HTTP {e.code} — server error, assuming deny-all")
            rp.disallow_all = True
            return rp
        except Exception as e:  # noqa: BLE001 - transport failure, try next scheme
            last_error = e
            continue
        rp.parse(raw.splitlines())
        return rp

    log(f"robots-unreachable {host} ({last_error}) — proceeding; "
        f"an unreachable robots.txt means no rules, not deny-all")
    rp = RobotFileParser()
    rp.allow_all = True
    return rp


def links_from(htmltext, base, host):
    try:
        doc = LH.fromstring(htmltext)
    except Exception as e:
        log(f"link-parse-error {base}: {e}")
        return []
    out = []
    for a in doc.xpath("//a[@href]"):
        try:
            u = norm(urljoin(base, a.get("href")))
        except ValueError:
            # e.g. an unmatched '[' makes urlsplit raise Invalid IPv6 URL.
            # Unguarded this escapes the crawl thread and ends the whole
            # crawl over one bad href on one page.
            continue
        if wanted(u, host):
            out.append(u)
    return out


def _base_out_file(host, requested_out=None):
    """Output path before any shard suffix -- the name all sibling shards of
    the same crawl agree on, so they can find each other's state files."""
    if requested_out:
        return os.path.abspath(requested_out)
    if DEFAULT_OUT_FILE:
        return os.path.abspath(DEFAULT_OUT_FILE)
    return os.path.abspath(f"text-mirror/{host}.md")


def get_out_file(host, requested_out=None):
    base = _base_out_file(host, requested_out)
    if SHARD_COUNT <= 1:
        return base
    root, ext = os.path.splitext(base)
    return f"{root}.shard{SHARD_INDEX}{ext}"


def owns(url):
    """True if this shard fetches url. crc32-mod partition, stable across
    processes/machines (unlike Python's randomized hash()). Unsharded runs
    (SHARD_COUNT==1) own everything -- fully backward compatible."""
    if SHARD_COUNT <= 1:
        return True
    return zlib.crc32(url.encode()) % SHARD_COUNT == SHARD_INDEX


def client_out_file(requested):
    """Constrain a browser-supplied out_file to a safe bare filename in the output
    base directory, so a malicious page cannot drive an arbitrary-path file write
    (or a directory-path crash) via the /save or /crawl endpoints. Returns None for
    empty/dot/traversal/null-byte names so the caller falls back to the default."""
    if not requested:
        return None
    name = os.path.basename(requested)
    if name in ("", ".", "..") or "\x00" in name:
        return None
    base = os.path.abspath(os.path.dirname(DEFAULT_OUT_FILE)) if DEFAULT_OUT_FILE else os.getcwd()
    candidate = os.path.join(base, name)
    if os.path.isdir(candidate):  # basename collides with an existing directory
        return None
    return candidate


def _safe_host(host):
    return host.replace(":", "_").replace("/", "_") or "site"


def get_state_file(host, out_file=None):
    """Per-host state file next to the output; sharded runs add `.shard<i>` so
    sibling shards of one crawl can find each other's files (merge_siblings)."""
    filepath = get_out_file(host, out_file)
    base_dir = os.path.dirname(filepath) or "."
    shard = f".shard{SHARD_INDEX}" if SHARD_COUNT > 1 else ""
    return os.path.join(base_dir, f"{_safe_host(host)}{shard}_state.json")


def merge_siblings(host, out_file, crawled, seen, q):
    """Pull progress from sibling shards' state files -- synced in from other
    boxes via Syncthing -- so this shard learns what the crawl as a whole has
    discovered/crawled without ever fetching those pages itself. Returns how
    many newly-owned URLs got queued."""
    if SHARD_COUNT <= 1:
        return 0
    own_state = os.path.abspath(get_state_file(host, out_file))
    base_dir = os.path.dirname(own_state) or "."
    added = 0
    for path in glob.glob(os.path.join(base_dir, f"{_safe_host(host)}.shard*_state.json")):
        if os.path.abspath(path) == own_state:
            continue
        try:
            with open(path) as f:
                sib = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for u in sib.get("discovered", []):
            if u not in seen:
                seen.add(u)
                if owns(u) and u not in crawled:
                    q.append((u, 1))
                    added += 1
        for u, ts in sib.get("crawled", {}).items():
            if u not in crawled:
                crawled[u] = ts
                _mark_saved(u)
    if added:
        log(f"shard{SHARD_INDEX}: merged {added} owned url(s) from sibling shards")
    return added


def _load_queue(items):
    q = deque()
    for it in items or []:
        if isinstance(it, dict) and "url" in it and "depth" in it:
            q.append((it["url"], it["depth"]))
    return q


def load_state(host, out_file=None):
    state_file = get_state_file(host, out_file)
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            log(f"state-load-error {state_file}: {e}")
    return {"crawled": {}, "discovered": [], "queue": []}


def save_state(host, out_file, crawled, discovered, queue, extra=None):
    state_file = get_state_file(host, out_file)
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    payload = json.dumps({
        "crawled": crawled,
        "discovered": list(discovered),
        "queue": [{"url": u, "depth": d} for u, d in queue],
        **(extra or {}),
    })
    tmp = state_file + ".tmp"
    with STATE_LOCK:
        with open(tmp, "w") as f:
            f.write(payload)
        os.replace(tmp, state_file)  # atomic: a crash mid-write cannot corrupt state


def _mark_saved(url):
    with MIRROR_LOCK:
        if url not in _SAVED_SET:
            _SAVED_SET.add(url)
            SAVED_URLS.append(url)


def _is_saved(url):
    with MIRROR_LOCK:
        return url in _SAVED_SET


def _saved_snapshot():
    with MIRROR_LOCK:
        return list(SAVED_URLS)


def _reset_saved():
    with MIRROR_LOCK:
        _SAVED_SET.clear()
        SAVED_URLS.clear()


def append_to_file(filepath, text, url):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with MIRROR_LOCK:
        with open(filepath, "a") as f:
            f.write("\n\n" + SEP + "\n")
            f.write(f"URL: {url}\n")
            f.write(SEP + "\n\n")
            f.write((text or "[no extractable text]") + "\n")
        if url not in _SAVED_SET:
            _SAVED_SET.add(url)
            SAVED_URLS.append(url)


def process_single_url(url, host, delay, html_content=None, force_refresh=False, out_file=None):
    if not force_refresh and _is_saved(url):
        log(f"skip-already-saved {url}")
        return True

    if html_content:
        downloaded = html_content
    else:
        _throttle(delay)
        downloaded = trafilatura.fetch_url(url, config=CFG)

    if not downloaded:
        log(f"no-content {url}")
        return False

    try:
        text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                   include_comments=True, include_tables=True,
                                   include_images=True, include_links=True,
                                   favor_recall=True, config=CFG)
    except Exception as e:
        log(f"extract-error {url}: {e}")
        text = None

    filepath = get_out_file(host, out_file)
    append_to_file(filepath, text, url)
    log(f"Saved: {url} -> {filepath}")
    return True


def claude_binary():
    """The real `claude` binary. It is commonly a shell alias, which does not
    exist in a subprocess, so a bare PATH lookup alone is not enough."""
    import shutil
    for c in (os.path.expanduser("~/.local/bin/claude"),
              "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return shutil.which("claude")


def _crawl_llms_txt_job(url):
    """Run the crawl-to-llms-txt skill on `url` via a headless `claude -p`,
    then drain the next queued URL (if any) -- the single-flight-with-queue
    contract /crawl_llms_txt promises the extension. Resets the lock/active
    state in every exit path so a crashed or hung job cannot wedge the queue."""
    global CRAWL_LLMS_ACTIVE, CRAWL_LLMS_CURRENT
    started = time.monotonic()
    host = norm_host(urlparse(url).netloc) or "job"
    out_dir = os.path.join(CRAWL_LLMS_OUT_ROOT, host)
    os.makedirs(out_dir, exist_ok=True)
    status, error = "ok", ""
    binary = claude_binary()
    if not binary:
        status, error = "error", "claude binary not found on PATH"
        log(f"crawl-llms-txt: {error}")
    else:
        # `claude -p` (headless/print mode) does not resolve custom skill
        # slash-command aliases the way an interactive session does --
        # `/crawl2llms` there prints "Unknown command" and exits 0, which
        # looked like a fast, silent success (see concept_tree.py's
        # research_prompt() for the same lesson). Natural language that
        # names the skill directly is what actually triggers it headless.
        prompt = (
            f"Use the crawl-to-llms-txt skill on {url}. Crawl it and condense "
            f"everything referenceable into a local llms.txt family under "
            f"{out_dir} (create the directory if needed)."
        )
        argv = [binary, "-p", prompt, "--permission-mode", "acceptEdits"]
        log(f"crawl-llms-txt: starting {url} -> {out_dir}")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=_CRAWL_LLMS_TIMEOUT)
            if proc.returncode != 0:
                status, error = "error", (proc.stderr or "").strip()[-500:]
            elif not os.listdir(out_dir):
                # A 0 exit with nothing written is not a real success -- this is
                # exactly how the /crawl2llms-slash-command bug looked (claude -p
                # printed "Unknown command" and exited 0 in ~7s). Surface it
                # instead of a silent "ok" so the same class of bug can't hide.
                status = "error"
                error = ("claude exited 0 but wrote nothing to " + out_dir
                         + "; stdout: " + (proc.stdout or "").strip()[-300:])
        except subprocess.TimeoutExpired:
            status, error = "error", f"timed out after {_CRAWL_LLMS_TIMEOUT}s"
        except OSError as e:
            status, error = "error", str(e)
    duration = round(time.monotonic() - started, 1)
    log(f"crawl-llms-txt: finished {url} status={status} in {duration}s")

    next_url = None
    with CRAWL_LLMS_LOCK:
        CRAWL_LLMS_HISTORY.append({
            "url": url, "status": status, "error": error, "out_dir": out_dir,
            "duration_s": duration, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        del CRAWL_LLMS_HISTORY[:-_CRAWL_LLMS_HISTORY_MAX]
        if CRAWL_LLMS_QUEUE:
            item = CRAWL_LLMS_QUEUE.pop(0)
            next_url = item["url"]
            CRAWL_LLMS_CURRENT = {"url": next_url,
                                  "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        else:
            CRAWL_LLMS_CURRENT = None
            CRAWL_LLMS_ACTIVE = False
    if next_url is not None:
        threading.Thread(target=_crawl_llms_txt_job, args=(next_url,), daemon=True).start()


def try_llms_acquire(seed, host, out_file, max_pages):
    """Write the docset from the site's own markdown when it publishes one.
    Returns the page count, or 0 to fall through to the crawl. Only for a
    fresh, unsharded, non-forced run: an existing mirror keeps the resumable
    crawl path so a partial crawl is never clobbered (move it aside to
    switch), and shards split a crawl, not a single download."""
    if not PREFER_LLMS or llms_acquire is None or SHARD_COUNT > 1:
        return 0
    out_path = get_out_file(host, out_file)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return 0
    try:
        r = llms_acquire.acquire(seed, out_path, max_pages=max_pages, log=log)
    except Exception as e:  # noqa: BLE001 -- never let the fast path break the crawl
        log(f"llms acquire error: {e}")
        return 0
    if not r["method"]:
        return 0
    with open(out_path, encoding="utf-8") as f:
        urls = [ln[5:].strip() for ln in f if ln.startswith("URL: ")]
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    save_state(host, out_file, {u: ts for u in urls}, urls, [],
               extra={"acquire": r["method"], "acquire_failed": r["failed"]})
    for u in urls:
        _mark_saved(u)
    log(f"acquired {r['pages']} pages via {r['method']} -> {out_path}")
    return r["pages"]


def run_distill_job(job_id, url, host, html_content):
    """Extract this one page, funnel it through distill_offline.py's semantic
    Stage 1-3 (exact-dedup then embed-cluster -- same engine pipeline_manager
    uses per-site, run here on a single page), then save the distilled master
    into the docset_indexer backend so it's queryable via Ask/Docsets too."""
    def set_job(**kw):
        with DISTILL_JOBS_LOCK:
            DISTILL_JOBS[job_id].update(kw)

    try:
        downloaded = html_content or trafilatura.fetch_url(url, config=CFG)
        if not downloaded:
            set_job(status="error", error="no content fetched")
            return
        text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                   include_comments=True, include_tables=True,
                                   include_images=True, include_links=True,
                                   favor_recall=True, config=CFG)
        if not text:
            set_job(status="error", error="no extractable text on this page")
            return

        os.makedirs(DISTILL_SCRATCH_DIR, exist_ok=True)
        scratch_name = f"{_safe_host(host)}_{job_id}"
        scratch_file = os.path.join(DISTILL_SCRATCH_DIR, f"{scratch_name}.md")
        with open(scratch_file, "w") as f:
            f.write(SEP + "\n")
            f.write(f"URL: {url}\n")
            f.write(SEP + "\n\n")
            f.write(text + "\n")

        set_job(status="distilling")
        proc = subprocess.run(
            ["python3", DISTILL_SCRIPT, "bulk", scratch_file, "--no-recursive", "--semantic"],
            cwd=os.path.dirname(DISTILL_SCRIPT), capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            set_job(status="error", error=f"distill failed: {proc.stderr[-1000:]}")
            return

        master_file = os.path.join(DISTILL_SCRATCH_DIR, f"{scratch_name}.pages",
                                   f"{scratch_name}_master.md")
        if not os.path.exists(master_file):
            set_job(status="error", error=f"no master file produced: {proc.stdout[-500:]}")
            return
        with open(master_file) as f:
            master_text = f.read()
        points = parse_master_points(master_text)

        set_job(status="indexing", points=points)
        docset_name = f"page__{scratch_name}"
        idx_proc = subprocess.run(
            [HUB_VENV_PY, INDEXER_SCRIPT, "index", master_file, "--name", docset_name],
            capture_output=True, text=True, timeout=120)
        indexed = idx_proc.returncode == 0
        set_job(status="done", points=points, indexed=indexed, docset=docset_name,
                index_error=None if indexed else idx_proc.stderr[-500:])
        log(f"Distilled {url} -> {len(points)} points"
            f"{' (indexed as ' + docset_name + ')' if indexed else ' (index failed)'}")
    except subprocess.TimeoutExpired:
        set_job(status="error", error="distill or index step timed out")
    except Exception as e:  # noqa: BLE001 -- the job status is the error channel
        set_job(status="error", error=str(e))


def crawl_job(seed, host, delay, max_depth, html, force_refresh, out_file,
              cloner=None, max_pages=0):
    """Thread target for the extension's /crawl.

    The asset queue is drained in the `finally` so a cancelled or failed crawl
    still leaves a usable clone of the pages it did get, rather than a tree of
    HTML with every image missing."""
    try:
        crawl(seed, host, delay, max_depth, html, force_refresh, out_file,
              max_pages=max_pages, cloner=cloner)
    finally:
        if cloner is not None:
            cloner.fetch_assets()
            cloner.write_manifest()
            log(f"clone done: {cloner.pages} pages, {cloner.assets} assets, "
                f"{len(cloner.failed)} failed -> {cloner.root}")


def build_cloner(host, out_file, data):
    """SiteCloner for an extension request, or None when clone is off. An explicit
    clone_dir is honoured (the endpoint is already gated by the Origin allowlist);
    a missing or unusable one lands beside the output file."""
    if not data.get("clone"):
        return None
    base = os.path.dirname(out_file) if out_file else "text-mirror"
    requested = data.get("clone_dir")
    if not isinstance(requested, str) or not requested.strip() or "\x00" in requested \
            or os.path.basename(requested.rstrip("/")) in ("", ".", ".."):
        requested = None
    root = requested or os.path.join(base or "text-mirror", site_clone.clone_dir_name(host))
    return site_clone.SiteCloner(
        root, host, UA, log=log,
        external_assets=not data.get("same_host_assets", False),
        max_assets=int(data.get("max_assets", 0) or 0))


class PluginServerHandler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length))

    def _origin_ok(self):
        """Allow the Chrome/Firefox extension, curl (no Origin), and loopback pages;
        reject web origins so a random site open in the browser cannot drive these
        URL-fetching, file-writing endpoints (defense-in-depth over the 127.0.0.1
        bind, which does not stop same-machine cross-origin requests)."""
        origin = self.headers.get('Origin')
        if not origin:
            return True  # non-browser client (curl/native); a browser always sends Origin
        if origin.startswith(('chrome-extension://', 'moz-extension://')):
            return True
        return urlparse(origin).hostname in ('localhost', '127.0.0.1', '::1')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            self.send_error(403)
            return
        if self.path == '/list':
            self._send_json(200, {
                'saved_urls': _saved_snapshot(),
                'crawl_active': CRAWL_ACTIVE,
                'stats': dict(CRAWL_STATS)
            })
        elif self.path.startswith('/distill_status'):
            qs = parse_qs(urlparse(self.path).query)
            job_id = (qs.get('job_id') or [None])[0]
            with DISTILL_JOBS_LOCK:
                job = dict(DISTILL_JOBS.get(job_id, {"status": "unknown"}))
            self._send_json(200, job)
        elif self.path == '/crawl_llms_txt/status':
            with CRAWL_LLMS_LOCK:
                self._send_json(200, {
                    'active': CRAWL_LLMS_ACTIVE,
                    'current': CRAWL_LLMS_CURRENT,
                    'queue': list(CRAWL_LLMS_QUEUE),
                    'history': list(CRAWL_LLMS_HISTORY[-5:]),
                })
        else:
            self.send_error(404)

    def do_POST(self):
        global CRAWL_ACTIVE, CRAWL_CANCEL, CRAWL_LLMS_ACTIVE, CRAWL_LLMS_CURRENT
        if not self._origin_ok():
            self.send_error(403)
            return
        if self.path == '/stop':
            CRAWL_CANCEL = True
            self._send_json(200, {'status': 'stopping'})
            return

        if self.path == '/crawl_llms_txt':
            try:
                data = self._read_json()
            except Exception:
                self.send_error(400)
                return
            url = data.get('url')
            if not url:
                self.send_error(400)
                return
            with CRAWL_LLMS_LOCK:
                if CRAWL_LLMS_ACTIVE:
                    CRAWL_LLMS_QUEUE.append(
                        {'url': url, 'queued_at': time.strftime("%Y-%m-%dT%H:%M:%S")})
                    self._send_json(200, {'status': 'queued', 'position': len(CRAWL_LLMS_QUEUE)})
                    return
                CRAWL_LLMS_ACTIVE = True
                CRAWL_LLMS_CURRENT = {'url': url,
                                      'started_at': time.strftime("%Y-%m-%dT%H:%M:%S")}
            threading.Thread(target=_crawl_llms_txt_job, args=(url,), daemon=True).start()
            self._send_json(200, {'status': 'started', 'url': url})
            return

        if self.path == '/distill':
            try:
                data = self._read_json()
            except Exception:
                self.send_error(400)
                return
            url = data.get('url')
            if not url:
                self.send_error(400)
                return
            host = norm_host(urlparse(url).netloc)
            job_id = str(int(time.time() * 1000))
            with DISTILL_JOBS_LOCK:
                DISTILL_JOBS[job_id] = {"status": "extracting", "url": url}
            threading.Thread(target=run_distill_job,
                             args=(job_id, url, host, data.get('html')), daemon=True).start()
            self._send_json(200, {'status': 'started', 'job_id': job_id})
            return

        if self.path in ('/save', '/crawl'):
            try:
                data = self._read_json()
            except Exception:
                self.send_error(400)
                return

            url = data.get('url')
            if not url:
                self.send_error(400)
                return

            html = data.get('html')
            force_refresh = data.get('force_refresh', False)
            out_file = client_out_file(data.get('out_file'))
            host = norm_host(urlparse(url).netloc)
            delay = getattr(self.server, 'crawl_delay', 1.0)

            if self.path == '/save':
                try:
                    process_single_url(url, host, delay, html, force_refresh, out_file)
                except Exception as e:
                    log(f"save-error {url}: {e}")
                    self._send_json(500, {'status': 'error', 'error': str(e)})
                    return
                self._send_json(200, {'saved_urls': _saved_snapshot(), 'status': 'ok'})
                return

            # /crawl: single-flight — reject a new crawl while one is running so the
            # two do not stomp the shared cancel flag / stats / output file.
            try:
                max_depth = int(data.get('max_depth', 0))
            except (TypeError, ValueError):
                max_depth = 0
            try:
                max_pages = int(data.get('max_pages', 0) or 0)
            except (TypeError, ValueError):
                max_pages = 0
            with CRAWL_START_LOCK:
                if CRAWL_ACTIVE:
                    self._send_json(409, {'status': 'busy',
                                          'error': 'a crawl is already running'})
                    return
                CRAWL_ACTIVE = True  # reserve before spawning to close the race
            try:
                cloner = build_cloner(host, out_file, data)
            except Exception as e:  # noqa: BLE001 -- release the reservation on a bad request
                CRAWL_ACTIVE = False
                self._send_json(400, {'status': 'error', 'error': f'clone setup: {e}'})
                return
            t = threading.Thread(
                target=crawl_job,
                args=(url, host, delay, max_depth, html, force_refresh, out_file, cloner,
                      max_pages),
                daemon=True)
            t.start()
            self._send_json(200, {'status': 'crawl_started',
                                  'clone_dir': cloner.root if cloner else None})
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # Suppress noisy HTTP logs


def run_server(delay):
    server_address = ('127.0.0.1', PORT)
    httpd = ThreadingHTTPServer(server_address, PluginServerHandler)
    httpd.crawl_delay = delay
    log(f"Started Chrome extension server on http://127.0.0.1:{PORT}")
    httpd.serve_forever()


def fetch_and_extract(url, is_seed, seed_html, host, delay):
    """Fetch + extract one page, off the main thread -- crawl() runs a batch of
    these concurrently per round. Returns the RAW html alongside the extracted
    text: --clone needs the original markup, and re-fetching would double every
    request."""
    try:
        if is_seed:
            downloaded = seed_html
        else:
            _throttle(delay)
            downloaded = trafilatura.fetch_url(url, config=CFG)
    except Exception as e:
        log(f"fetch-error {url}: {e}")
        return url, None, None, None

    if not downloaded:
        return url, None, None, None

    try:
        text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                   include_comments=True, include_tables=True,
                                   include_images=True, include_links=True,
                                   favor_recall=True, config=CFG)
    except Exception as e:
        log(f"extract-error {url}: {e}")
        text = None

    new_links = links_from(downloaded, url, host)
    return url, text, new_links, downloaded


def crawl(seed, host, delay, max_depth, seed_html=None, force_refresh=False, out_file=None,
          max_pages=0, cloner=None):
    """Reset CRAWL_ACTIVE on every exit so a crashed crawl cannot wedge the
    single-flight guard and block all future /crawl requests."""
    global CRAWL_ACTIVE, CRAWL_CANCEL
    CRAWL_ACTIVE = True
    CRAWL_CANCEL = False
    try:
        if seed_html is None and not force_refresh:
            got = try_llms_acquire(seed, host, out_file, max_pages)
            if got:
                return got
        return _crawl_impl(seed, host, delay, max_depth, seed_html, force_refresh, out_file,
                           max_pages, cloner)
    except Exception as e:
        log(f"{host}: crawl-error {e}")
        return 0
    finally:
        CRAWL_ACTIVE = False


def _crawl_impl(seed, host, delay, max_depth, seed_html=None, force_refresh=False, out_file=None,
                max_pages=0, cloner=None):
    scheme = urlparse(seed).scheme or "https"
    rp = get_robots(host, scheme)
    seed_norm = norm(seed)
    filepath = get_out_file(host, out_file)

    if force_refresh:
        _reset_saved()
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError as e:
            log(f"force-refresh-remove-error {filepath}: {e}")

    state = load_state(host, out_file)
    crawled = state.get("crawled")
    if not isinstance(crawled, dict):
        crawled = {}

    if not force_refresh and state.get("queue"):
        q = _load_queue(state["queue"])
        seen = set(state.get("discovered", []))
        seen.update(crawled.keys())
        log(f"Resumed from state: {len(q)} in queue, {len(crawled)} crawled.")
    else:
        q = deque([(seed_norm, 0)])
        seen = {seed_norm}
        if not force_refresh:
            seen.update(_saved_snapshot())
            seen.update(crawled.keys())

    for url in crawled:
        _mark_saved(url)

    n = 0
    last_save = time.monotonic()
    merge_siblings(host, out_file, crawled, seen, q)
    stall_rounds = 0
    capped = False
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
      while True:  # outer loop only matters for sharded runs (see the stall block)
        while q:
            CRAWL_STATS['discovered'] = len(seen)
            CRAWL_STATS['downloaded'] = n
            CRAWL_STATS['in_queue'] = len(q)

            if CRAWL_CANCEL:
                log("Crawl cancelled by user.")
                break

            if max_pages > 0 and n >= max_pages:
                log(f"{host}: hit max_pages={max_pages}")
                capped = True
                break

            batch = []
            hit_depth_limit = False

            while q and len(batch) < MAX_WORKERS:
                if max_pages > 0 and n + len(batch) >= max_pages:
                    break

                url, depth = q.popleft()

                if max_depth > 0 and depth > max_depth:
                    q.appendleft((url, depth))
                    log(f"{host}: hit max_depth={max_depth}")
                    hit_depth_limit = True
                    break

                if not force_refresh and _is_saved(url) and url != seed_norm:
                    log(f"skip-already-saved {url}")
                    continue

                if url != seed_norm and not owns(url):
                    continue  # another shard's page -- it'll see this via our state file

                if not rp.can_fetch(UA, url):
                    log(f"robots-skip {url}")
                    continue

                batch.append((url, depth))

            if not batch:
                if hit_depth_limit:
                    break
                continue

            futures = []
            for url, depth in batch:
                is_seed = (url == seed_norm and seed_html is not None)
                futures.append((depth, executor.submit(
                    fetch_and_extract, url, is_seed, seed_html, host, delay)))

            for depth, future in futures:
                if CRAWL_CANCEL:
                    break
                url, text, new_links, raw_html = future.result()

                if new_links is None and text is None:
                    log(f"no-content {url}")
                    continue

                n += 1
                append_to_file(filepath, text, url)
                if cloner is not None and raw_html:
                    # Same fetch feeds both outputs -- the markdown corpus and
                    # the browsable clone -- so cloning costs no extra requests
                    # for pages, only for the assets they reference.
                    try:
                        cloner.save_page(url, raw_html)
                    except Exception as e:  # noqa: BLE001 -- a clone failure never stops the mirror
                        log(f"clone-save-error {url}: {e}")
                crawled[url] = time.strftime('%Y-%m-%d %H:%M:%S')

                for u in (new_links or []):
                    if u in seen:
                        continue
                    if max_depth > 0 and depth + 1 > max_depth:
                        continue
                    seen.add(u)
                    q.append((u, depth + 1))

            if time.monotonic() - last_save > STATE_SAVE_INTERVAL or hit_depth_limit:
                log(f"{host}: {n} pages saved, queue={len(q)}, seen={len(seen)}")
                save_state(host, out_file, crawled, seen, q)
                last_save = time.monotonic()

            if hit_depth_limit:
                break

        # Unsharded runs, or a cancelled/capped crawl, are done once the queue
        # drains. Sharded runs stall here instead: sibling shards elsewhere may
        # still be discovering pages this shard owns, arriving late over
        # Syncthing -- so wait and re-merge a few rounds before giving up.
        if SHARD_COUNT <= 1 or CRAWL_CANCEL or capped or hit_depth_limit:
            break
        save_state(host, out_file, crawled, seen, q)
        time.sleep(10)
        stall_rounds += 1
        if merge_siblings(host, out_file, crawled, seen, q):
            stall_rounds = 0
        elif stall_rounds > 6:
            log(f"shard{SHARD_INDEX}: no new work from siblings after "
                f"{stall_rounds} rounds, stopping")
            break
    finally:
        # On cancel, drop in-flight fetches instead of blocking up to 10 x timeout.
        executor.shutdown(wait=not CRAWL_CANCEL, cancel_futures=CRAWL_CANCEL)

    save_state(host, out_file, crawled, seen, q)
    CRAWL_STATS['downloaded'] = n
    CRAWL_STATS['in_queue'] = len(q)
    log(f"{host}: DONE {n} pages, {len(seen)} urls discovered -> {filepath}")
    return n


def main():
    global LOG_FILE, DEFAULT_OUT_FILE, CRAWL_ACTIVE, CRAWL_LLMS_OUT_ROOT
    global PREFER_LLMS, SHARD_INDEX, SHARD_COUNT
    ap = argparse.ArgumentParser(description="Recursive text-only site mirror via trafilatura.")
    ap.add_argument("seeds", nargs="*", help="one or more seed URLs to crawl")
    ap.add_argument("--out", default=None,
                    help="output file (default: text-mirror/<hostname>.md)")
    ap.add_argument("--delay", type=float, default=float(os.environ.get("CRAWL_DELAY", "1.0")),
                    help="seconds between requests (default: 1.0)")
    ap.add_argument("--req-per-sec", type=float, default=0,
                    help="rate limit: requests per second (overrides --delay if >0)")
    ap.add_argument("--max-depth", type=int, default=int(os.environ.get("MAX_DEPTH", "0")),
                    help="per-site depth limit (hops); 0 = unlimited (default: 0)")
    ap.add_argument("--max-pages", type=int, default=0,
                    help="stop after this many pages fetched by this shard; 0 = unlimited (default: 0)")
    ap.add_argument("--shard-index", type=int, default=0,
                    help="this process's shard number, 0-based (default: 0)")
    ap.add_argument("--shard-count", type=int, default=1,
                    help="total shards splitting this crawl across boxes (default: 1, unsharded)")
    ap.add_argument("--serve", action="store_true",
                    help=f"Start local HTTP API for the Chrome extension on 127.0.0.1:{PORT}")
    ap.add_argument("--clone", action="store_true",
                    help="also write a browsable offline copy (HTML + images, CSS, "
                         "JS, fonts, media) with links rewritten, into its own folder")
    ap.add_argument("--clone-dir", default=None,
                    help="clone destination (default: text-mirror/<hostname>.site/)")
    ap.add_argument("--clone-same-host-assets", action="store_true",
                    help="only clone assets served from the crawled host; by default "
                         "off-host assets are fetched too, since images, fonts and JS "
                         "usually live on a CDN and skipping them breaks the pages")
    ap.add_argument("--max-assets", type=int, default=0,
                    help="stop after this many assets; 0 = unlimited (default: 0)")
    ap.add_argument("--prefer-llms", action=argparse.BooleanOptionalAction, default=True,
                    help="fetch the site's llms-full.txt / llms.txt + page .md instead of "
                         "crawling when it publishes them (default: on)")
    args = ap.parse_args()
    PREFER_LLMS = args.prefer_llms
    SHARD_COUNT = max(1, args.shard_count)
    SHARD_INDEX = args.shard_index % SHARD_COUNT

    DEFAULT_OUT_FILE = args.out

    if not args.seeds and not args.serve and not args.out:
        args.serve = True

    log_dir = os.path.dirname(args.out) if args.out else "text-mirror"
    os.makedirs(log_dir or ".", exist_ok=True)
    LOG_FILE = os.path.join(log_dir or ".", "crawl.log")
    open(LOG_FILE, "a").close()
    CRAWL_LLMS_OUT_ROOT = os.path.join(log_dir or ".", "llms-crawl")

    delay = 1.0 / args.req_per_sec if args.req_per_sec > 0 else args.delay

    if args.serve:
        t = threading.Thread(target=run_server, args=(delay,), daemon=True)
        t.start()

    total = 0
    for seed in args.seeds:
        host = norm_host(urlparse(seed).netloc)
        if not host:
            log(f"skip invalid seed (no host): {seed}")
            continue
        # Interlock with the /crawl handler so a CLI batch and a browser-driven
        # crawl never run concurrently and stomp the shared crawl globals/state.
        while True:
            with CRAWL_START_LOCK:
                if not CRAWL_ACTIVE:
                    CRAWL_ACTIVE = True
                    break
            time.sleep(0.5)
        log(f"=== crawling {host} from {seed} "
            f"{'(shard ' + str(SHARD_INDEX) + '/' + str(SHARD_COUNT) + ') ' if SHARD_COUNT > 1 else ''}===")

        cloner = None
        if args.clone:
            clone_root = args.clone_dir or os.path.join(
                log_dir or "text-mirror", site_clone.clone_dir_name(host))
            cloner = site_clone.SiteCloner(
                clone_root, host, UA, log=log,
                external_assets=not args.clone_same_host_assets,
                max_assets=args.max_assets, delay=delay,
                # Shards split ASSETS the same crc32 way they split pages, so
                # sibling shards do not each re-fetch the same logo and
                # stylesheet. Unsharded runs own everything.
                owns=owns if SHARD_COUNT > 1 else None)
            log(f"clone -> {os.path.abspath(clone_root)}")

        total += crawl(seed, host, delay, args.max_depth, out_file=args.out,
                       max_pages=args.max_pages, cloner=cloner)

        if cloner is not None:
            # Assets are drained only now: the same stylesheet and logo appear
            # on every page, so fetching them inline would re-request each one
            # once per page.
            cloner.fetch_assets()
            manifest = cloner.write_manifest()
            log(f"clone done: {cloner.pages} pages, {cloner.assets} assets, "
                f"{len(cloner.failed)} failed -> {cloner.root} ({manifest})")

    if args.seeds:
        log(f"ALL DONE: {total} pages total")

    if args.serve and not args.seeds:
        log("Server running... Waiting for Chrome extension requests. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
