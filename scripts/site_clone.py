"""site_clone.py — high-fidelity offline site clone for web-text-mirror.

The mirror's normal output is ONE markdown file of extracted prose, which is
what an LLM corpus wants and what a human reading the site offline does not.
This module is the other half: it writes a browsable copy of the site to disk
— raw HTML, images, CSS, JS, fonts, media — with links rewritten to relative
paths so the clone opens in a browser with no network.

It is deliberately a module and not a shell-out to httrack/wget: the crawler
already solves robots.txt, rate limiting, host scoping, sharding and resume,
and a second tool would re-solve none of those the same way.

Split by design: everything that maps, extracts or rewrites is a pure function
over strings, so the interesting failure modes (path traversal, query-string
collisions, CSS url() forms) are testable with no network and no filesystem.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from urllib.parse import urljoin, urlsplit

# A link is an ASSET unless it is something the reader clicks to navigate.
# Inverting it this way means a tag we have never heard of is fetched rather
# than silently dropped -- for a clone, over-fetching is recoverable and
# under-fetching leaves a broken page.
NAVIGABLE = {("a", "href"), ("area", "href"), ("form", "action")}

# url(...) in stylesheets, plus @import in both its forms.
_CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)
_CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?(['"])([^'"]+)\1""", re.I)

_ILLEGAL = re.compile(r'[\x00-\x1f<>:"|?*\\]')


def split(url: str):
    """urlsplit that returns None instead of raising.

    A page containing something like `http://host/[oops` makes urlsplit raise
    ValueError("Invalid IPv6 URL"). Unguarded that propagates out of the link
    loop and kills the whole crawl thread -- one malformed href on one page
    silently ending a site-wide crawl.
    """
    try:
        return urlsplit(url)
    except ValueError:
        return None
_MAX_SEGMENT = 100


def _sanitize(segment: str) -> str:
    """One path segment, safe on disk.

    Drops the characters no filesystem agrees on and caps length. A segment
    that sanitizes to nothing becomes a hash of the original rather than being
    silently dropped, which would collapse two distinct URLs onto one file.
    """
    seg = _ILLEGAL.sub("_", segment).strip(". ")
    if len(seg) > _MAX_SEGMENT:
        tail = hashlib.sha1(segment.encode()).hexdigest()[:8]
        seg = f"{seg[:_MAX_SEGMENT - 9]}_{tail}"
    return seg or hashlib.sha1(segment.encode()).hexdigest()[:12]


def url_to_rel_path(url: str, primary_host: str) -> str:
    """Map an absolute URL to a relative path inside the clone root.

    Rules, chosen so two URLs that mean the same page land on the same file:
      /            -> index.html
      /a/b/        -> a/b/index.html
      /a/b         -> a/b/index.html   (extensionless == a page)
      /a/style.css -> a/style.css
      ?q=1         -> ...__q<hash> appended, so paginated URLs stay distinct
      other host   -> _external/<host>/...
    """
    p = split(url)
    if p is None:
        # Unparseable, but it still needs a stable home if anything asks.
        return f"_unparseable/{hashlib.sha1(url.encode()).hexdigest()}.bin"
    parts = [_sanitize(s) for s in p.path.split("/") if s not in ("", ".", "..")]

    if not parts:
        parts = ["index.html"]
    elif "." not in parts[-1]:
        parts.append("index.html")

    if p.query:
        # Distinct query strings are distinct pages; without this, ?page=2
        # overwrites ?page=1 and the clone silently loses content.
        tag = hashlib.sha1(p.query.encode()).hexdigest()[:8]
        stem, dot, ext = parts[-1].rpartition(".")
        parts[-1] = f"{stem}__q{tag}.{ext}" if dot else f"{parts[-1]}__q{tag}"

    if p.netloc and p.netloc != primary_host:
        parts = ["_external", _sanitize(p.netloc)] + parts
    return "/".join(parts)


def clone_dir_name(host: str) -> str:
    """Directory name for a host's clone.

    Sanitised because a host can carry a port ("localhost:8099"), and a colon
    in a path is legal on POSIX but confuses Finder and is illegal on Windows,
    so an archive copied off this machine would break.
    """
    return f"{_sanitize(host)}.site"


def safe_join(root: str, rel: str) -> str:
    """Join under `root`, refusing anything that escapes it.

    url_to_rel_path already drops '..' segments, so this is the second gate:
    a crafted URL must not be able to write outside the clone directory even
    if the first one is ever loosened.
    """
    root_abs = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root_abs, rel))
    if target != root_abs and not target.startswith(root_abs + os.sep):
        raise ValueError(f"path escapes clone root: {rel!r}")
    return target


def is_asset(tag: str, attr: str | None) -> bool:
    """True for things the page needs to render, False for navigation."""
    return (tag, attr) not in NAVIGABLE


def css_urls(css_text: str, base_url: str) -> list[str]:
    """Absolute URLs referenced from a stylesheet (url(...) and @import)."""
    out = []
    for match in _CSS_URL_RE.finditer(css_text):
        ref = match.group(2).strip()
        if ref and not ref.startswith("data:"):
            out.append(urljoin(base_url, ref))
    for match in _CSS_IMPORT_RE.finditer(css_text):
        ref = match.group(2).strip()
        if ref and not ref.startswith("data:"):
            out.append(urljoin(base_url, ref))
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def rewrite_css(css_text: str, base_url: str, mapper) -> str:
    """Rewrite url()/@import through `mapper`, leaving unmapped refs absolute
    so a partially-fetched clone still renders against the live site."""
    def sub_url(m):
        quote, ref = m.group(1), m.group(2).strip()
        if ref.startswith("data:"):
            return m.group(0)
        return f"url({quote}{mapper(urljoin(base_url, ref))}{quote})"

    def sub_import(m):
        quote, ref = m.group(1), m.group(2).strip()
        if ref.startswith("data:"):
            return m.group(0)
        return f"@import {quote}{mapper(urljoin(base_url, ref))}{quote}"

    return _CSS_IMPORT_RE.sub(sub_import, _CSS_URL_RE.sub(sub_url, css_text))


def relative_href(from_rel: str, to_rel: str) -> str:
    """Link from one cloned file to another, as the browser will resolve it."""
    rel = os.path.relpath(to_rel, os.path.dirname(from_rel) or ".")
    return rel.replace(os.sep, "/")


def page_links(html: str, base_url: str):
    """(absolute_url, is_asset) for every link in the document.

    Uses lxml's iterlinks, which already knows every link-bearing attribute
    including srcset and inline style url(), so a new HTML feature does not
    quietly go unfetched.
    """
    import lxml.html as LH

    doc = LH.fromstring(html)
    # handle_failures="ignore": one malformed href (e.g. "//[bad") otherwise
    # raises out of absolutisation and costs the entire page.
    doc.make_links_absolute(base_url, resolve_base_href=True,
                            handle_failures="ignore")
    out = []
    for element, attr, link, _pos in doc.iterlinks():
        if link.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
            continue
        out.append((link, is_asset(element.tag, attr)))
    return out


def rewrite_html(html: str, base_url: str, mapper) -> bytes:
    """Rewrite every link through `mapper` and serialise back to bytes."""
    import lxml.html as LH

    doc = LH.fromstring(html)
    doc.make_links_absolute(base_url, resolve_base_href=True,
                            handle_failures="ignore")
    doc.rewrite_links(lambda link: (
        link if link.startswith(("data:", "javascript:", "mailto:", "tel:", "#"))
        else mapper(link)))
    return LH.tostring(doc, encoding="utf-8", doctype="<!DOCTYPE html>")


def fetch_bytes(url: str, ua: str, timeout: int = 30) -> tuple[bytes | None, str]:
    """Raw bytes + content-type. Assets are binary, so this cannot go through
    trafilatura's text-oriented fetch."""
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


class SiteCloner:
    """Writes the browsable copy: pages as they are crawled, assets after.

    Pages arrive from the crawler one at a time. Assets are DEFERRED into a
    queue and fetched at the end rather than inline, because the same logo and
    stylesheet appear on every page — fetching eagerly would re-request them
    once per page and multiply the crawl's traffic against the site.
    """

    def __init__(self, root, primary_host, ua, log=None, external_assets=True,
                 max_assets=0, delay=0.0, owns=None):
        self.root = os.path.abspath(root)
        self.host = primary_host
        self.ua = ua
        self.log = log or (lambda _m: None)
        self.external_assets = external_assets
        self.max_assets = max_assets
        self.delay = delay
        # Shard partition. Sibling shards would otherwise each fetch the same
        # stylesheet and logo, multiplying asset traffic by the shard count.
        # None means "this process owns every asset" (the unsharded default).
        self.owns = owns or (lambda _url: True)
        self.skipped_other_shard = 0
        self.planned: dict[str, str] = {}   # absolute url -> rel path
        self.written: set[str] = set()      # urls whose bytes are on disk
        self.pending: list[str] = []        # asset urls not yet fetched
        self.failed: dict[str, str] = {}
        self.pages = 0
        self.assets = 0
        os.makedirs(self.root, exist_ok=True)

    # -- planning ---------------------------------------------------------

    def _wanted_asset(self, url: str) -> bool:
        p = split(url)
        if p is None or p.scheme not in ("http", "https"):
            return False
        return self.external_assets or p.netloc == self.host

    def plan(self, url: str) -> str:
        rel = self.planned.get(url)
        if rel is None:
            rel = url_to_rel_path(url, self.host)
            self.planned[url] = rel
        return rel

    def _queue_asset(self, url: str) -> None:
        if url in self.planned or url in self.written:
            return
        if not self._wanted_asset(url):
            return
        # Plan the path either way: a page this shard writes still has to LINK
        # to an asset a sibling shard fetches, so the mapping must exist here
        # even when the bytes are someone else's job.
        self.plan(url)
        if not self.owns(url):
            self.skipped_other_shard += 1
            return
        self.pending.append(url)

    # -- writing ----------------------------------------------------------

    def _write(self, rel: str, data: bytes) -> None:
        path = safe_join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def save_page(self, url: str, html: str) -> None:
        """Write one crawled page, rewritten, and queue what it references."""
        page_rel = self.plan(url)
        try:
            links = page_links(html, url)
        except Exception as exc:  # noqa: BLE001 - a broken page must not stop the clone
            self.log(f"clone-parse-error {url}: {exc}")
            links = []

        for link, asset in links:
            parsed = split(link)
            if parsed is None:
                continue          # malformed href: skip it, never the page
            if asset:
                self._queue_asset(link)
            elif parsed.netloc == self.host:
                # A same-host page the crawler will reach on its own; planning
                # its path now lets this page link to it before it exists.
                self.plan(link)

        def mapper(link: str) -> str:
            rel = self.planned.get(link)
            # Unmapped links stay ABSOLUTE on purpose: a half-finished clone
            # then still navigates to the live site instead of 404ing locally.
            return relative_href(page_rel, rel) if rel else link

        try:
            self._write(page_rel, rewrite_html(html, url, mapper))
        except Exception as exc:  # noqa: BLE001 - includes lxml ParserError on
            # malformed/empty markup; one bad page must not end the crawl
            self.failed[url] = str(exc)
            self.log(f"clone-write-error {url}: {exc}")
            return
        self.written.add(url)
        self.pages += 1

    # -- assets -----------------------------------------------------------

    def fetch_assets(self, sleep=None) -> int:
        """Drain the asset queue. CSS is parsed for further references, so
        fonts and background images reached only from a stylesheet still
        arrive; the queue grows while draining, hence the while loop."""
        import time as _time

        sleep = sleep or (lambda s: _time.sleep(s))
        while self.pending:
            if self.max_assets and self.assets >= self.max_assets:
                self.log(f"clone: hit max_assets={self.max_assets}, "
                         f"{len(self.pending)} left unfetched")
                break
            url = self.pending.pop(0)
            if url in self.written:
                continue
            try:
                data, ctype = fetch_bytes(url, self.ua)
            except Exception as exc:  # noqa: BLE001 - one dead asset is not fatal
                self.failed[url] = str(exc)
                continue
            if data is None:
                continue

            rel = self.plan(url)
            if "css" in ctype.lower() or rel.endswith(".css"):
                try:
                    text = data.decode("utf-8", "replace")
                    for ref in css_urls(text, url):
                        self._queue_asset(ref)
                    data = rewrite_css(text, url, lambda u: (
                        relative_href(rel, self.planned[u])
                        if u in self.planned else u)).encode("utf-8")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"clone-css-error {url}: {exc}")

            try:
                self._write(rel, data)
            except (OSError, ValueError) as exc:
                self.failed[url] = str(exc)
                continue
            self.written.add(url)
            self.assets += 1
            if self.delay:
                sleep(self.delay)
        return self.assets

    def write_manifest(self) -> str:
        import json

        path = os.path.join(self.root, "_clone-manifest.json")
        with open(path, "w") as fh:
            json.dump({
                "host": self.host,
                "pages": self.pages,
                "assets": self.assets,
                "failed": self.failed,
                "files": {u: r for u, r in self.planned.items()
                          if u in self.written},
            }, fh, indent=2, sort_keys=True)
        return path
