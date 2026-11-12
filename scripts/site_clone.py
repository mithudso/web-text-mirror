"""Offline HTML/assets clone. Paths use URL identities, never remote path segments.

The crawler supplies pages. Assets are fetched afterwards. Finalization rewrites
only files that actually landed; failed or capped resources retain absolute URLs.
No module-level network or filesystem work occurs.
"""
from __future__ import annotations

import hashlib
import html as html_std
import json
import os
import re
import urllib.request
import uuid
from collections import deque
from urllib.parse import quote, urldefrag, urljoin, urlsplit

NAVIGABLE = {("a", "href"), ("area", "href"), ("form", "action")}
_CSS_URL_RE = re.compile(
    r'''url\(\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)'|(?P<bare>(?:\\.|[^()'"\\])*))\s*\)''',
    re.IGNORECASE)
# url(...) imports are handled by _CSS_URL_RE, exactly once.
_CSS_IMPORT_RE = re.compile(r"""@import\s+(['"])([^'"]+)\1""", re.IGNORECASE)
MAX_ASSET_BYTES = 32 * 1024 * 1024
FETCH_TIMEOUT = 30


def split(url: str):
    try:
        return urlsplit(url)
    except ValueError:
        return None


def _resource(url):
    return urldefrag(url)[0]


def url_to_rel_path(url: str, primary_host: str) -> str:
    """Stable collision-resistant resource namespace, separate from metadata.

    The full fragment-free URL supplies the identity. The extension supplies a
    browser MIME hint only. Remote separators, percent escapes, reserved names,
    Unicode bytes and query strings cannot become filesystem path components.
    """
    resource = _resource(url)
    parsed = split(resource)
    ext = os.path.splitext(parsed.path)[1].lower() if parsed else ""
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", ext):
        ext = ".html"
    digest = hashlib.sha256(resource.encode("utf-8")).hexdigest()
    return f"_resources/{digest}{ext}"


def clone_dir_name(host: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]", "_", host)[:60].strip(". ") or "site"
    return f"{readable}-{hashlib.sha256(host.encode()).hexdigest()[:12]}.site"


def safe_join(root: str, rel: str) -> str:
    root_abs = os.path.realpath(os.path.abspath(root))
    target = os.path.abspath(os.path.join(root_abs, rel))
    resolved = os.path.realpath(target)
    if os.path.commonpath([root_abs, resolved]) != root_abs:
        raise ValueError("path escapes clone root")
    return target


def is_asset(tag: str, attr: str | None) -> bool:
    return (tag, attr) not in NAVIGABLE


def _absolute(base, ref):
    if not ref or ref.startswith("#") or ref.lower().startswith(
            ("data:", "javascript:", "mailto:", "tel:")):
        return None
    try:
        url = urljoin(base, ref)
        parsed = split(url)
        return url if parsed and parsed.scheme in ("http", "https") and parsed.netloc else None
    except ValueError:
        return None


def css_urls(css_text: str, base_url: str) -> list[str]:
    refs = [m.group(m.lastgroup).strip() for m in _CSS_URL_RE.finditer(css_text)]
    refs.extend(m.group(2).strip() for m in _CSS_IMPORT_RE.finditer(css_text))
    return list(dict.fromkeys(u for ref in refs if (u := _absolute(base_url, ref))))


def rewrite_css(css_text: str, base_url: str, mapper) -> str:
    def replace(m):
        group = m.lastgroup or 2
        absolute = _absolute(base_url, m.group(group).strip())
        if absolute is None:
            return m.group(0)
        # Replace just the URL span; preserve url(), quotes and media qualifiers.
        start, end = m.span(group)
        mapped = mapper(absolute)
        # URL syntax characters must not close a CSS token after rewriting.
        mapped = mapped.replace('\\', '%5C').replace('"', '%22').replace("'", '%27')
        if group == 'bare':
            mapped = mapped.replace('(', '%28').replace(')', '%29').replace(' ', '%20')
        return m.group(0)[:start-m.start()] + mapped + m.group(0)[end-m.start():]
    return _CSS_IMPORT_RE.sub(replace, _CSS_URL_RE.sub(replace, css_text))


def relative_href(from_rel: str, to_rel: str) -> str:
    rel = os.path.relpath(to_rel, os.path.dirname(from_rel) or ".").replace(os.sep, "/")
    return quote(rel, safe="/.")


def _srcset(value):
    """Read URL tokens and descriptors without splitting commas inside data URLs."""
    pos = 0
    while pos < len(value):
        while pos < len(value) and (value[pos].isspace() or value[pos] == ","):
            pos += 1
        start = pos
        while pos < len(value) and not value[pos].isspace():
            pos += 1
        token = value[start:pos]
        if not token:
            break
        if token.endswith(","):
            yield token.rstrip(","), ""
            continue
        start = pos
        while pos < len(value) and value[pos] != ",":
            pos += 1
        yield token, value[start:pos].strip()
        pos += 1


def _document(html, base_url):
    import lxml.html as LH
    doc = LH.fromstring(html)
    base_elements = doc.xpath("//base[@href]")
    effective_base = (_absolute(base_url, base_elements[0].get("href"))
                      if base_elements else None) or base_url
    for element in doc.xpath("//*[@srcset]"):
        element.set("srcset", ", ".join(
            (_absolute(effective_base, ref) or ref) + (" " + desc if desc else "")
            for ref, desc in _srcset(element.get("srcset"))))
    doc.make_links_absolute(base_url, resolve_base_href=True, handle_failures="ignore")
    return doc


def page_links(html: str, base_url: str):
    doc = _document(html, base_url)
    out = []
    for element, attr, link, _pos in doc.iterlinks():
        absolute = _absolute(base_url, link)
        if absolute:
            out.append((absolute, is_asset(element.tag, attr)))
    # lxml.iterlinks does not enumerate srcset candidates.
    effective_base = doc.base_url or base_url
    for element in doc.xpath("//*[@srcset]"):
        for ref, _descriptor in _srcset(element.get("srcset")):
            absolute = _absolute(effective_base, ref)
            if absolute:
                out.append((absolute, True))
    return out


def rewrite_html(html: str, base_url: str, mapper, absolute=True) -> bytes:
    import lxml.html as LH
    doc = _document(html, base_url) if absolute else LH.fromstring(html)
    doc.rewrite_links(lambda link: mapper(link) if _absolute(base_url, link) else link,
                      resolve_base_href=False)
    for element in doc.xpath("//*[@srcset]"):
        candidates = []
        for ref, descriptor in _srcset(element.get("srcset")):
            url = _absolute(base_url, ref)
            mapped = mapper(url) if url else ref
            candidates.append(mapped + (" " + descriptor if descriptor else ""))
        element.set("srcset", ", ".join(candidates))
    for meta in doc.xpath("//meta[@charset]"):
        meta.set("charset", "utf-8")
    for meta in doc.xpath("//meta[@http-equiv]"):
        if meta.get("http-equiv", "").lower() == "content-type":
            meta.set("content", "text/html; charset=utf-8")
    return LH.tostring(doc, encoding="utf-8", doctype="<!DOCTYPE html>")


def fetch_bytes(url: str, ua: str, timeout: int = FETCH_TIMEOUT):
    """Bounded bytes, content type and effective response URL for relative CSS."""
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_ASSET_BYTES + 1)
        if len(data) > MAX_ASSET_BYTES:
            raise ValueError("asset exceeds 32 MiB limit")
        return data, resp.headers.get("Content-Type", ""), resp.geturl()


class SiteCloner:
    """One unsharded clone. Call save_page, fetch_assets, then write_manifest.

    Existing symlink components inside the selected root are never followed by
    writes. Sharded HTML acquisition is refused until asset discovery can be
    handed off safely; text-only crawl sharding remains independent.
    """
    def __init__(self, root, primary_host, ua, log=None, external_assets=True,
                 max_assets=0, delay=0.0, owns=None, resume=True):
        if owns is not None:
            raise ValueError("HTML cloning does not support shard ownership")
        if max_assets < 0 or delay < 0:
            raise ValueError("asset limits and delay must be nonnegative")
        self.root = os.path.realpath(os.path.abspath(root))
        self.host, self.ua = primary_host, ua
        self.log = log or (lambda _m: None)
        self.external_assets, self.max_assets, self.delay = external_assets, max_assets, delay
        self.planned, self.written, self.pending, self.failed = {}, set(), deque(), {}
        self.pages = self.assets = self.attempts = 0
        self._page_urls, self._css_bases, self._finalized = set(), {}, set()
        self.entry = None
        self.cancelled = lambda: False
        os.makedirs(self.root, exist_ok=True)
        if resume:
            self._load_manifest()

    def _original_rel(self, url):
        return '_original/' + hashlib.sha256(url.encode('utf-8')).hexdigest() + '.txt'

    def _read(self, rel):
        """Read bounded local clone data without following symlink components."""
        parts = rel.split('/')
        if any(p in ('', '.', '..') for p in parts) or os.path.isabs(rel):
            raise ValueError('invalid clone path')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root, flags)
        try:
            for part in parts[:-1]:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            handle = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(handle, 'rb') as stream:
                data = stream.read(MAX_ASSET_BYTES + 1)
            if len(data) > MAX_ASSET_BYTES:
                raise ValueError('clone file exceeds size limit')
            return data
        finally:
            os.close(fd)

    def _load_manifest(self):
        try:
            manifest = json.loads(self._read('_clone-manifest.json'))
        except FileNotFoundError:
            return
        if (not isinstance(manifest, dict) or manifest.get('version') != 2
                or manifest.get('host') != self.host):
            raise ValueError('unsupported clone manifest; choose a new clone directory')
        files, pages = manifest.get('files'), manifest.get('page_urls')
        css, pending = manifest.get('css_bases'), manifest.get('pending')
        failed = manifest.get('failed')
        if (not isinstance(files, dict) or not isinstance(pages, list)
                or not isinstance(css, dict) or not isinstance(pending, list)):
            raise TypeError('invalid clone manifest')
        if (not isinstance(failed, dict)
                or not all(isinstance(u, str) and isinstance(error, str)
                           for u, error in failed.items())):
            raise ValueError('invalid clone failure history')
        for url, rel in files.items():
            if (not isinstance(url, str) or _absolute(url, url) != url
                    or _resource(url) != url or rel != url_to_rel_path(url, self.host)):
                raise ValueError('invalid clone resource identity')
            self._read(rel)
        if (not all(isinstance(u, str) and u in files for u in pages)
                or not all(isinstance(u, str) and u in files and isinstance(base, str)
                           and _absolute(base, base) == base for u, base in css.items())
                or not all(isinstance(u, str) and self._wanted_asset(u)
                           and _resource(u) == u for u in pending)):
            raise ValueError('invalid clone manifest references')
        for url in set(pages) | css.keys():
            self._read(self._original_rel(url))
        entry = manifest.get('entry_url')
        if entry is not None and entry not in pages:
            raise ValueError('invalid clone entry identity')
        self.planned.update(files)
        self.written.update(files)
        self._page_urls.update(pages)
        self._css_bases.update(css)
        self.failed.update(failed)
        self.entry = entry
        self.pages, self.assets = len(self._page_urls), len(self.written - self._page_urls)
        for url in pending:
            if url not in self.written:
                self.plan(url)
                if url not in self.pending:
                    self.pending.append(url)
        # Attempts are bounded per invocation; retained pending work can resume.
        self.log('clone-resumed')

    def has_page(self, url):
        return _resource(url) in self._page_urls

    def _wanted_asset(self, url):
        p = split(url)
        return bool(p and p.scheme in ("http", "https") and p.netloc
                    and (self.external_assets or p.netloc == self.host))

    def plan(self, url):
        key = _resource(url)
        return self.planned.setdefault(key, url_to_rel_path(key, self.host))

    def _queue_asset(self, url):
        key = _resource(url)
        if key not in self.planned and self._wanted_asset(key):
            self.plan(key)
            self.pending.append(key)

    def _write(self, rel, data):
        """Atomic replacement through directory descriptors with no-follow opens."""
        parts = rel.split("/")
        if any(p in ("", ".", "..") for p in parts) or os.path.isabs(rel):
            raise ValueError("invalid clone path")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root, directory_flags)
        temporary = None
        try:
            for part in parts[:-1]:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, directory_flags, dir_fd=fd)
                os.close(fd)
                fd = child
            temporary = ".clone-" + uuid.uuid4().hex
            handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.replace(temporary, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary, dir_fd=fd)
            os.close(fd)

    def save_page(self, url, html):
        key = _resource(url)
        rel = self.plan(key)
        try:
            original = html.encode('utf-8') if isinstance(html, str) else html
            if len(original) > MAX_ASSET_BYTES:
                raise ValueError('clone page exceeds size limit')
            for link, asset in page_links(html, url):
                if asset:
                    self._queue_asset(link)
            # Keep absolute links until availability is known.
            self._write(rel, rewrite_html(html, url, lambda u: u))
            self._write(self._original_rel(key), original)
        except Exception as exc:
            self.failed[key] = type(exc).__name__
            self.log(f"clone-page-error {type(exc).__name__}")
            return
        self.written.add(key)
        self._page_urls.add(key)
        self._finalized.discard(key)
        self.entry = self.entry or key
        self.pages = len(self._page_urls)

    def fetch_assets(self, sleep=None):
        import time
        sleep = sleep or time.sleep
        while (self.pending and not self.cancelled()
               and (not self.max_assets or self.attempts < self.max_assets)):
            url = self.pending.popleft()
            if url in self.written:
                continue
            self.attempts += 1
            self.log("clone-asset-request")
            try:
                data, ctype, effective_url = fetch_bytes(url, self.ua)
                rel = self.plan(url)
                if "css" in ctype.lower() or rel.endswith(".css"):
                    text = data.decode("utf-8", "replace")
                    # Normalize CSS charset when serializing as UTF-8.
                    text = re.sub(r'^\s*@charset\s+[\'"][^\'"]+[\'"]\s*;',
                                  '@charset "UTF-8";', text, flags=re.IGNORECASE)
                    for ref in css_urls(text, effective_url):
                        self._queue_asset(ref)
                    data = rewrite_css(text, effective_url, lambda u: u).encode("utf-8")
                    self._write(self._original_rel(url), data)
                    self._css_bases[url] = effective_url
                self._write(rel, data)
                self.written.add(url)
                self.assets += 1
                self.log("clone-asset-ok")
            except Exception as exc:
                self.failed[url] = type(exc).__name__
                self.log(f"clone-asset-error {type(exc).__name__}")
            finally:
                if self.delay:
                    sleep(self.delay)
        return self.assets

    def _mapper(self, from_rel, link):
        parsed = split(link)
        if not parsed or parsed.scheme not in ("http", "https"):
            return link
        key = _resource(link)
        if key not in self.written:
            return link
        result = relative_href(from_rel, self.planned[key])
        return result + ("#" + parsed.fragment if parsed.fragment else "")

    def write_manifest(self):
        for url in sorted(self.written - self._finalized):
            rel = self.planned[url]
            if url in self._page_urls or url in self._css_bases:
                text = self._read(self._original_rel(url)).decode('utf-8')
                mapper = lambda link, rel=rel: self._mapper(rel, link)
                data = (rewrite_html(text, url, mapper)
                        if url in self._page_urls else
                        rewrite_css(text, self._css_bases[url], mapper).encode("utf-8"))
                self._write(rel, data)
            self._finalized.add(url)
        if self.entry:
            target = html_std.escape(self.planned[self.entry], quote=True)
            self._write("index.html", ('<!doctype html><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0;url={target}">'
                f'<a href="{target}">Open cloned entry page</a>').encode())
        self._write("_clone-manifest.json", json.dumps({
            "version": 2, "entry_url": self.entry,
            "page_urls": sorted(self._page_urls), "css_bases": self._css_bases,
            "host": self.host, "pages": self.pages, "assets": self.assets,
            "attempts": self.attempts, "pending": list(self.pending),
            "failed": self.failed, "entry": self.planned.get(self.entry),
            "files": {u: self.planned[u] for u in sorted(self.written)},
        }, indent=2, sort_keys=True).encode("utf-8"))
        return os.path.join(self.root, "_clone-manifest.json")
