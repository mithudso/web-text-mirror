#!/usr/bin/env python3
"""Recursive text-only website mirror via trafilatura.

BFS-crawls one or more seed URLs (same-host scoping per seed), extracts each page
to Markdown, and appends it to an output file.
Public pages only, robots.txt-respecting, rate-limited. Auto-installs trafilatura
and lxml if missing. Uncapped by default; writes incrementally so partial output
is usable and the run is resumable-by-hand.

Usage:
  python text_mirror.py [URL ...] [--out FILE] [--serve] [--req-per-sec N]
Examples:
  python text_mirror.py https://wiki.example.org/
  python text_mirror.py --serve --out extension_mirror.md
"""
import argparse
import importlib.util
import os
import subprocess
import sys
import time
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse
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
from trafilatura.settings import use_config  # noqa: E402
from lxml import html as LH  # noqa: E402

UA = "trafilatura-text-mirror/1.0 (+public-archive)"
CFG = use_config()
CFG.set("DEFAULT", "USER_AGENTS", UA)
CFG.set("DEFAULT", "DOWNLOAD_TIMEOUT", "30")

SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".css",
            ".js", ".pdf", ".zip", ".gz", ".tar", ".mp4", ".mp3", ".avi",
            ".woff", ".woff2", ".ttf", ".rss", ".atom")
SKIP_SUBSTR = ("/login", "/register", "/account", "/members/", "/lost-password",
               "/whats-new/", "/misc/", "/goto/", "/find-new/", "/attachments/",
               "/logout", "oauth", "action=", "oldid=", "diff=", "special:",
               "printable=", "veaction=", "redlink", "feed=", "&do=", "/help/")

LOG_FILE = None
DEFAULT_OUT_FILE = None
MIRROR_LOCK = threading.Lock()
SAVED_URLS = []
CRAWL_ACTIVE = False
CRAWL_CANCEL = False
CRAWL_STATS = {
    'discovered': 0,
    'downloaded': 0,
    'in_queue': 0
}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")


def norm(url):
    return urldefrag(url)[0].strip()


def wanted(url, host):
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or p.netloc != host:
        return False
    low = url.lower()
    if low.endswith(SKIP_EXT):
        return False
    if any(s in low for s in SKIP_SUBSTR):
        return False
    return True


def get_robots(host):
    rp = RobotFileParser()
    rp.set_url(f"https://{host}/robots.txt")
    try:
        rp.read()
    except Exception as e:
        log(f"robots-read-error {host}: {e}")
    return rp


def links_from(htmltext, base, host):
    try:
        doc = LH.fromstring(htmltext)
    except Exception:
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


def get_state_file(host, out_file=None):
    filepath = get_out_file(host, out_file)
    base, _ = os.path.splitext(filepath)
    return base + "_state.json"


def load_state(host, out_file=None):
    state_file = get_state_file(host, out_file)
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"state-load-error {host}: {e}")
    return {"crawled": {}, "discovered": [], "queue": []}


def save_state(host, out_file, crawled, discovered, queue):
    state_file = get_state_file(host, out_file)
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump({
            "crawled": crawled,
            "discovered": list(discovered),
            "queue": [{"url": u, "depth": d} for u, d in queue]
        }, f, indent=2)


def append_to_file(filepath, text, url):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with MIRROR_LOCK:
        with open(filepath, "a") as f:
            f.write("\n\n" + "=" * 90 + "\n")
            f.write(f"URL: {url}\n")
            f.write("=" * 90 + "\n\n")
            f.write((text or "[no extractable text]") + "\n")
            
        if url not in SAVED_URLS:
            SAVED_URLS.append(url)


def process_single_url(url, host, delay, html_content=None, force_refresh=False, out_file=None):
    if not force_refresh and url in SAVED_URLS:
        log(f"skip-already-saved {url}")
        return True
        
    if html_content:
        downloaded = html_content
    else:
        downloaded = trafilatura.fetch_url(url, config=CFG)
        time.sleep(delay)
        
    if not downloaded:
        log(f"no-content {url}")
        return False
        
    try:
        text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                   include_comments=True, include_tables=True,
                                   favor_recall=True, config=CFG)
    except Exception as e:
        log(f"extract-error {url}: {e}")
        text = None
        
    filepath = get_out_file(host, out_file)
    append_to_file(filepath, text, url)
    log(f"Saved: {url} -> {filepath}")
    return True


class PluginServerHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/list':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'saved_urls': SAVED_URLS,
                'crawl_active': CRAWL_ACTIVE,
                'stats': CRAWL_STATS
            }).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/stop':
            global CRAWL_CANCEL
            CRAWL_CANCEL = True
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'stopping'}).encode())
            return

        if self.path == '/save':
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length))
            url = data.get('url')
            html = data.get('html')
            force_refresh = data.get('force_refresh', False)
            out_file = data.get('out_file')
            
            if url:
                host = urlparse(url).netloc
                process_single_url(url, host, getattr(self.server, 'crawl_delay', 1.0), html, force_refresh, out_file)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'saved_urls': SAVED_URLS, 'status': 'ok'}).encode())
            else:
                self.send_error(400)
        elif self.path == '/crawl':
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length))
            url = data.get('url')
            max_depth = int(data.get('max_depth', 0))
            html = data.get('html')
            force_refresh = data.get('force_refresh', False)
            out_file = data.get('out_file')
            
            if url:
                host = urlparse(url).netloc
                delay = getattr(self.server, 'crawl_delay', 1.0)
                t = threading.Thread(target=crawl, args=(url, host, delay, max_depth, html, force_refresh, out_file), daemon=True)
                t.start()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'crawl_started'}).encode())
            else:
                self.send_error(400)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass # Suppress noisy HTTP logs


def run_server(delay):
    server_address = ('', 8765)
    httpd = HTTPServer(server_address, PluginServerHandler)
    httpd.crawl_delay = delay
    log("Started Chrome extension server on http://localhost:8765")
    httpd.serve_forever()


def crawl(seed, host, delay, max_depth, seed_html=None, force_refresh=False, out_file=None):
    global CRAWL_ACTIVE, CRAWL_CANCEL
    CRAWL_ACTIVE = True
    CRAWL_CANCEL = False
    
    rp = get_robots(host)
    seed_norm = norm(seed)
    
    state = load_state(host, out_file)
    crawled = state.get("crawled", {})
    
    if not force_refresh and state.get("queue"):
        q = deque([(item["url"], item["depth"]) for item in state["queue"]])
        seen = set(state.get("discovered", []))
        seen.update(crawled.keys())
        log(f"Resumed from state: {len(q)} in queue, {len(crawled)} crawled.")
    else:
        q = deque([(seed_norm, 0)]) # Queue stores (url, depth)
        seen = {seed_norm}
        if not force_refresh:
            seen.update(SAVED_URLS)
            seen.update(crawled.keys())
            
    for url in crawled.keys():
        if url not in SAVED_URLS:
            SAVED_URLS.append(url)
        
    n = 0
    filepath = get_out_file(host, out_file)
    
    while q:
        CRAWL_STATS['discovered'] = len(seen)
        CRAWL_STATS['downloaded'] = n
        CRAWL_STATS['in_queue'] = len(q)
        
        if CRAWL_CANCEL:
            log("Crawl cancelled by user.")
            break
            
        url, depth = q.popleft()
        
        if max_depth > 0 and depth > max_depth:
            q.appendleft((url, depth))
            log(f"{host}: hit max_depth={max_depth}")
            break
            
        if not force_refresh and url in SAVED_URLS and url != seed_norm:
            log(f"skip-already-saved {url}"); continue
            
        if not rp.can_fetch(UA, url):
            log(f"robots-skip {url}"); continue
        
        downloaded = None
        is_seed = (url == norm(seed) and seed_html is not None)
        
        try:
            if is_seed:
                downloaded = seed_html
            else:
                downloaded = trafilatura.fetch_url(url, config=CFG)
        except Exception as e:
            log(f"fetch-error {url}: {e}")
            
        if not is_seed:
            if CRAWL_CANCEL: break
            time.sleep(delay)
            
        if not downloaded:
            log(f"no-content {url}"); continue
        n += 1
        
        try:
            text = trafilatura.extract(downloaded, url=url, output_format="markdown",
                                       include_comments=True, include_tables=True,
                                       include_images=True, include_links=True,
                                       favor_recall=True, config=CFG)
        except Exception as e:
            log(f"extract-error {url}: {e}")
            text = None
            
        append_to_file(filepath, text, url)
        crawled[url] = time.strftime('%Y-%m-%d %H:%M:%S')
                
        if n % 10 == 0:
            log(f"{host}: {n} pages saved, queue={len(q)}, seen={len(seen)}")
            save_state(host, out_file, crawled, seen, q)
            
        for u in links_from(downloaded, url, host):
            if u not in seen:
                seen.add(u)
                q.append((u, depth + 1))
                
    save_state(host, out_file, crawled, seen, q)
    CRAWL_STATS['downloaded'] = n
    CRAWL_STATS['in_queue'] = len(q)
    CRAWL_ACTIVE = False
    log(f"{host}: DONE {n} pages, {len(seen)} urls discovered -> {filepath}")
    return n


def main():
    global LOG_FILE, DEFAULT_OUT_FILE
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
                    help="Start local HTTP API for the Chrome extension on port 8765")
    args = ap.parse_args()

    DEFAULT_OUT_FILE = args.out
    
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
        host = urlparse(seed).netloc
        if not host:
            log(f"skip invalid seed (no host): {seed}"); continue
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
