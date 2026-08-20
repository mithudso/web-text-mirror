"""Self-contained test harness for scripts/text_mirror.py.

Serves two linked HTML pages on localhost, crawls them, and asserts both are
mirrored. Also unit-checks the security- and correctness-critical helpers:
norm_host, wanted, client_out_file (path-traversal/dir-collision containment),
get_state_file (per-host keying), _origin_ok (Origin allowlist), plus a crash-path
regression (a raising crawl must reset CRAWL_ACTIVE).

Run: python3 tests/test_text_mirror.py
Requires trafilatura + lxml importable (the module self-bootstraps them via pip
otherwise — run inside a provisioned venv to avoid that side effect).
Never touches the public internet.
"""
import importlib.util
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "text_mirror.py")

spec = importlib.util.spec_from_file_location("text_mirror", SCRIPT)
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# ---- unit checks: host normalization + URL filtering --------------------------
check("norm_host lowercases + strips :443",
      tm.norm_host("WWW.Example.COM:443") == "www.example.com")
check("norm_host strips userinfo + :80",
      tm.norm_host("user:pw@Host.tld:80") == "host.tld")
check("norm_host keeps custom port",
      tm.norm_host("host.tld:8080") == "host.tld:8080")

check("wanted same-host mixed case",
      tm.wanted("http://Example.com/a", "example.com") is True)
check("wanted rejects other host",
      tm.wanted("http://evil.com/a", "example.com") is False)
check("wanted rejects skip-ext",
      tm.wanted("http://example.com/a.png", "example.com") is False)

# ---- unit checks: client_out_file containment ---------------------------------
tm.DEFAULT_OUT_FILE = None
cwd = os.getcwd()
check("client_out_file blocks ../ traversal",
      tm.client_out_file("../../../../etc/passwd") == os.path.join(cwd, "passwd"))
check("client_out_file blocks absolute path",
      tm.client_out_file("/etc/crontab") == os.path.join(cwd, "crontab"))
check("client_out_file None passthrough",
      tm.client_out_file(None) is None)
check("client_out_file rejects ..", tm.client_out_file("..") is None)
check("client_out_file rejects .", tm.client_out_file(".") is None)
check("client_out_file rejects empty", tm.client_out_file("") is None)
check("client_out_file rejects trailing-slash dir", tm.client_out_file("a/b/") is None)
check("client_out_file rejects null byte", tm.client_out_file("a\x00b") is None)

_tdir = tempfile.mkdtemp()
os.mkdir(os.path.join(_tdir, "adir"))
tm.DEFAULT_OUT_FILE = os.path.join(_tdir, "out.md")
check("client_out_file rejects existing-dir name", tm.client_out_file("adir") is None)
check("client_out_file keeps normal name w/ base",
      tm.client_out_file("ok.md") == os.path.join(_tdir, "ok.md"))
tm.DEFAULT_OUT_FILE = None

# ---- unit checks: per-host state keying ---------------------------------------
tm.DEFAULT_OUT_FILE = os.path.join(tempfile.gettempdir(), "shared.md")
sa = tm.get_state_file("a.com", tm.DEFAULT_OUT_FILE)
sb = tm.get_state_file("b.com", tm.DEFAULT_OUT_FILE)
check("get_state_file distinct per host", sa != sb and "a.com" in sa and "b.com" in sb)
tm.DEFAULT_OUT_FILE = None


# ---- unit checks: Origin allowlist --------------------------------------------
class FakeReq:
    def __init__(self, origin):
        self.headers = {} if origin is None else {'Origin': origin}


_ok = tm.PluginServerHandler._origin_ok
check("origin extension allowed", _ok(FakeReq('chrome-extension://abc')) is True)
check("origin none allowed", _ok(FakeReq(None)) is True)
check("origin null rejected (sandboxed-iframe bypass)", _ok(FakeReq('null')) is False)
check("origin localhost allowed", _ok(FakeReq('http://localhost:3000')) is True)
check("origin evil web rejected", _ok(FakeReq('https://evil.example')) is False)

# ---- functional: two-page localhost crawl -------------------------------------
PAGES = {
    "/": b"<html><body><h1>Index</h1><p>This is the index page with enough "
          b"text for extraction to succeed here.</p>"
          b"<a href='page2.html'>next</a></body></html>",
    "/page2.html": b"<html><body><h1>Page Two</h1><p>Second page body content "
                   b"that is long enough to be extracted as markdown text.</p>"
                   b"</body></html>",
}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)

out = os.path.join(tempfile.mkdtemp(), "mirror.md")
tm.DEFAULT_OUT_FILE = out
tm.LOG_FILE = None
seed = f"http://127.0.0.1:{port}/"
host = tm.norm_host(f"127.0.0.1:{port}")

n = tm.crawl(seed, host, delay=0, max_depth=0, out_file=out)

data = open(out).read() if os.path.exists(out) else ""
check("crawl saved 2 pages", n == 2)
check("output has index URL", seed in data)
check("output has page2 URL", f"http://127.0.0.1:{port}/page2.html" in data)
check("output has 2 URL blocks", data.count("URL: ") == 2)
check("crawl marked inactive at end", tm.CRAWL_ACTIVE is False)

srv.shutdown()

# ---- regression: a crashing crawl must reset CRAWL_ACTIVE ---------------------
# (single-flight guard would otherwise wedge and reject every future /crawl)
orig = tm.get_robots
tm.get_robots = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
tm.CRAWL_ACTIVE = True  # simulate the /crawl handler's reservation
rv = tm.crawl("http://127.0.0.1:1/", "127.0.0.1:1", delay=0, max_depth=0)
tm.get_robots = orig
check("crashing crawl returns 0", rv == 0)
check("crashing crawl resets CRAWL_ACTIVE", tm.CRAWL_ACTIVE is False)

print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
