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
                        [--max-depth N] [--serve]
Examples:
  python text_mirror.py https://wiki.example.org/
  python text_mirror.py --serve --out extension_mirror.md
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser


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

# Global fetch rate limiter (shared across worker threads).
_RATE_LOCK = threading.Lock()
_next_fetch = 0.0


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if LOG_FILE:
        with LOG_LOCK, open(LOG_FILE, "a") as f:
            f.write(line + "\n")


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
    """Fetch robots.txt with a timeout; fail open (allow-all) on network error so a
    single unreachable robots.txt does not zero out the whole crawl. Mirrors the
    stdlib policy for HTTP status codes (401/403 -> disallow, other 4xx -> allow)."""
    url = f"{scheme}://{host}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=ROBOTS_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        rp.parse(raw.splitlines())
    except HTTPError as e:
        if e.code in (401, 403):
            rp.disallow_all = True
        else:
            rp.allow_all = True
    except Exception as e:
        rp.allow_all = True
        log(f"robots-read-error {host}: {e} (assuming allow-all)")
    return rp


def links_from(htmltext, base, host):
    try:
        doc = LH.fromstring(htmltext)
    except Exception as e:
        log(f"link-parse-error {base}: {e}")
        return []
    out = []
    for a in doc.xpath("//a[@href]"):
        u = norm(urljoin(base, a.get("href")))
        if wanted(u, host):
            out.append(u)
    return out


def get_out_file(host, requested_out=None):
    if requested_out:
        return os.path.abspath(requested_out)
    if DEFAULT_OUT_FILE:
        return os.path.abspath(DEFAULT_OUT_FILE)
    return os.path.abspath(f"text-mirror/{host}.md")


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


def get_state_file(host, out_file=None):
    filepath = get_out_file(host, out_file)
    base_dir = os.path.dirname(filepath) or "."
    safe_host = host.replace(":", "_").replace("/", "_") or "site"
    return os.path.join(base_dir, f"{safe_host}_state.json")


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


def save_state(host, out_file, crawled, discovered, queue):
    state_file = get_state_file(host, out_file)
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    payload = json.dumps({
        "crawled": crawled,
        "discovered": list(discovered),
        "queue": [{"url": u, "depth": d} for u, d in queue]
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
        else:
            self.send_error(404)

    def do_POST(self):
        global CRAWL_ACTIVE, CRAWL_CANCEL
        if not self._origin_ok():
            self.send_error(403)
            return
        if self.path == '/stop':
            CRAWL_CANCEL = True
            self._send_json(200, {'status': 'stopping'})
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
            with CRAWL_START_LOCK:
                if CRAWL_ACTIVE:
                    self._send_json(409, {'status': 'busy',
                                          'error': 'a crawl is already running'})
                    return
                CRAWL_ACTIVE = True  # reserve before spawning to close the race
            t = threading.Thread(
                target=crawl,
                args=(url, host, delay, max_depth, html, force_refresh, out_file),
                daemon=True)
            t.start()
            self._send_json(200, {'status': 'crawl_started'})
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
    try:
        if is_seed:
            downloaded = seed_html
        else:
            _throttle(delay)
            downloaded = trafilatura.fetch_url(url, config=CFG)
    except Exception as e:
        log(f"fetch-error {url}: {e}")
        return url, None, None

    if not downloaded:
        return url, None, None

    try:
        text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                   include_comments=True, include_tables=True,
                                   include_images=True, include_links=True,
                                   favor_recall=True, config=CFG)
    except Exception as e:
        log(f"extract-error {url}: {e}")
        text = None

    new_links = links_from(downloaded, url, host)
    return url, text, new_links


def crawl(seed, host, delay, max_depth, seed_html=None, force_refresh=False, out_file=None):
    """Reset CRAWL_ACTIVE on every exit so a crashed crawl cannot wedge the
    single-flight guard and block all future /crawl requests."""
    global CRAWL_ACTIVE, CRAWL_CANCEL
    CRAWL_ACTIVE = True
    CRAWL_CANCEL = False
    try:
        return _crawl_impl(seed, host, delay, max_depth, seed_html, force_refresh, out_file)
    except Exception as e:
        log(f"{host}: crawl-error {e}")
        return 0
    finally:
        CRAWL_ACTIVE = False


def _crawl_impl(seed, host, delay, max_depth, seed_html=None, force_refresh=False, out_file=None):
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
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        while q:
            CRAWL_STATS['discovered'] = len(seen)
            CRAWL_STATS['downloaded'] = n
            CRAWL_STATS['in_queue'] = len(q)

            if CRAWL_CANCEL:
                log("Crawl cancelled by user.")
                break

            batch = []
            hit_depth_limit = False

            while q and len(batch) < MAX_WORKERS:
                url, depth = q.popleft()

                if max_depth > 0 and depth > max_depth:
                    q.appendleft((url, depth))
                    log(f"{host}: hit max_depth={max_depth}")
                    hit_depth_limit = True
                    break

                if not force_refresh and _is_saved(url) and url != seed_norm:
                    log(f"skip-already-saved {url}")
                    continue

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
                url, text, new_links = future.result()

                if new_links is None and text is None:
                    log(f"no-content {url}")
                    continue

                n += 1
                append_to_file(filepath, text, url)
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
    finally:
        # On cancel, drop in-flight fetches instead of blocking up to 10 x timeout.
        executor.shutdown(wait=not CRAWL_CANCEL, cancel_futures=CRAWL_CANCEL)

    save_state(host, out_file, crawled, seen, q)
    CRAWL_STATS['downloaded'] = n
    CRAWL_STATS['in_queue'] = len(q)
    log(f"{host}: DONE {n} pages, {len(seen)} urls discovered -> {filepath}")
    return n


def main():
    global LOG_FILE, DEFAULT_OUT_FILE, CRAWL_ACTIVE
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
    ap.add_argument("--serve", action="store_true",
                    help=f"Start local HTTP API for the Chrome extension on 127.0.0.1:{PORT}")
    args = ap.parse_args()

    DEFAULT_OUT_FILE = args.out

    if not args.seeds and not args.serve and not args.out:
        args.serve = True

    log_dir = os.path.dirname(args.out) if args.out else "text-mirror"
    os.makedirs(log_dir or ".", exist_ok=True)
    LOG_FILE = os.path.join(log_dir or ".", "crawl.log")
    open(LOG_FILE, "a").close()

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
        log(f"=== crawling {host} from {seed} ===")
        total += crawl(seed, host, delay, args.max_depth, out_file=args.out)

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
