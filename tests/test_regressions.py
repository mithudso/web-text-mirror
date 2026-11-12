"""Synthetic regressions. No public network, host integrations or model calls."""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from collections import deque
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Block the optional workstation module before loading the crawler. It must not
# win import resolution by inserting its host directory ahead of PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
_missing = object()
_previous_module = sys.modules.get('llms_acquire', _missing)
_previous_path = list(sys.path)
sys.modules['llms_acquire'] = None
try:
    spec = importlib.util.spec_from_file_location('mirror_regression_target', ROOT/'scripts/text_mirror.py')
    tm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tm)
finally:
    sys.path[:] = _previous_path
    if _previous_module is _missing:
        sys.modules.pop('llms_acquire', None)
    else:
        sys.modules['llms_acquire'] = _previous_module
sc = tm.site_clone
HTML = '<html><body><p>Synthetic article content sufficient for extraction.</p></body></html>'


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = str(Path(self.temp.name)/'out.md')
        tm._reset_saved()
        tm.CRAWL_CANCEL = False
        tm.CRAWL_ACTIVE = False
        self.stack = []
        for name, value in {'DEFAULT_OUT_FILE': self.out, 'LOG_FILE': None,
                            'PREFER_LLMS': False, 'SHARD_COUNT': 1, 'SHARD_INDEX': 0,
                            'llms_acquire': None}.items():
            p = patch.object(tm, name, value); p.start(); self.addCleanup(p.stop)
        # Any accidental remote fetch or process execution fails immediately.
        for module, name in [(tm.trafilatura, 'fetch_url'), (tm, 'urlopen'),
                             (tm.subprocess, 'run'), (tm.subprocess, 'check_call')]:
            p = patch.object(module, name, side_effect=AssertionError('unmocked external call'))
            p.start(); self.addCleanup(p.stop)

    def allow_robots(self):
        p = patch.object(tm, 'get_robots', return_value=SimpleNamespace(can_fetch=lambda *a: True))
        p.start(); self.addCleanup(p.stop)

    def test_output_state_and_saved_identity(self):
        other = str(Path(self.temp.name)/'other.md')
        self.assertNotEqual(tm.get_state_file('example.org', self.out),
                            tm.get_state_file('example.org', other))
        with patch.object(tm.trafilatura, 'extract', return_value='body'):
            self.assertTrue(tm.process_single_url('https://example.org/a', 'example.org', 0,
                                                 HTML, out_file=self.out))
            self.assertTrue(tm.process_single_url('https://example.org/a', 'example.org', 0,
                                                 HTML, out_file=other))
        self.assertIn('URL: https://example.org/a', Path(other).read_text())

    def test_missing_output_does_not_reuse_crawled_state(self):
        self.allow_robots()
        seed = 'https://example.org/'; child = seed+'child'
        tm.save_state('example.org', self.out, {child: 'old'}, [seed, child], [])
        def fetched(url, *args):
            return url, 'body', [child] if url == seed else [], HTML
        with patch.object(tm, 'fetch_and_extract', side_effect=fetched):
            tm.crawl(seed, 'example.org', 0, 0, out_file=self.out)
        self.assertIn('URL: '+child, Path(self.out).read_text())

    def test_force_refresh_preserves_other_hosts_in_shared_output(self):
        self.allow_robots()
        a = 'https://a.example/'; b = 'https://b.example/'
        tm.append_to_file(self.out, 'first host old bytes', a)
        tm.append_to_file(self.out, 'second host preserved bytes', b)
        tm.save_state('b.example', self.out, {b: 'saved'}, [b], [])
        with patch.object(tm, 'fetch_and_extract', return_value=(a, 'first host new bytes', [], HTML)):
            tm.crawl(a, 'a.example', 0, 0, force_refresh=True, out_file=self.out)
        text = Path(self.out).read_text()
        self.assertIn('second host preserved bytes', text)
        self.assertIn('first host new bytes', text)
        self.assertNotIn('first host old bytes', text)
        self.assertIn(b, tm.load_state('b.example', self.out)['crawled'])

    def test_clone_resume_preserves_entry_pages_and_links(self):
        self.allow_robots()
        seed = 'https://example.org/'; child = seed+'child'
        root = str(Path(self.temp.name)/'clone')
        def fetched(url, *args):
            html = f'<a href="{child}">child</a>' if url == seed else '<p>child</p>'
            return url, 'body', [child] if url == seed else [], html
        with patch.object(tm, 'fetch_and_extract', side_effect=fetched):
            first = sc.SiteCloner(root, 'example.org', 'test')
            tm.crawl(seed, 'example.org', 0, 0, out_file=self.out, max_pages=1, cloner=first)
            resumed = sc.SiteCloner(root, 'example.org', 'test')
            tm.crawl(seed, 'example.org', 0, 0, out_file=self.out, cloner=resumed)
        manifest = json.loads((Path(root)/'_clone-manifest.json').read_text())
        self.assertEqual(manifest['pages'], 2)
        self.assertEqual(manifest['entry'], resumed.planned[seed])
        page = (Path(root)/resumed.planned[seed]).read_text()
        self.assertIn(Path(resumed.planned[child]).name, page)
        self.assertNotIn('https://example.org/child', page)

    def test_cloning_after_text_only_crawl_includes_saved_children(self):
        self.allow_robots()
        seed = 'https://example.org/'; child = seed+'child'
        def fetched(url, *args):
            return url, 'body', [child] if url == seed else [], '<p>page</p>'
        with patch.object(tm, 'fetch_and_extract', side_effect=fetched):
            tm.crawl(seed, 'example.org', 0, 0, out_file=self.out)
            clone = sc.SiteCloner(str(Path(self.temp.name)/'clone'), 'example.org', 'test')
            tm.crawl(seed, 'example.org', 0, 0, out_file=self.out, cloner=clone)
        self.assertEqual(clone.pages, 2)

    def test_worker_start_failure_releases_reservations(self):
        for route in ['/crawl', '/crawl_llms_txt', '/distill']:
            tm.CRAWL_ACTIVE = tm.CRAWL_LLMS_ACTIVE = False
            tm.CRAWL_LLMS_CURRENT = None
            replies = []
            handler = SimpleNamespace(path=route, server=SimpleNamespace(crawl_delay=0),
                _origin_ok=lambda: True, _read_json=lambda: {'url': 'https://example.org/'},
                _send_json=lambda *args, replies=replies: replies.append(args))
            with patch.object(tm.threading.Thread, 'start', side_effect=RuntimeError('synthetic unavailable worker')):
                tm.PluginServerHandler.do_POST(handler)
            self.assertEqual(replies[-1][0], 503)
            self.assertFalse(tm.CRAWL_ACTIVE)
            self.assertFalse(tm.CRAWL_LLMS_ACTIVE)
            self.assertIsNone(tm.CRAWL_LLMS_CURRENT)
            if route == '/distill':
                self.assertTrue(all(job['status'] != 'extracting' for job in tm.DISTILL_JOBS.values()))
            with patch.object(tm.threading, 'Thread', return_value=SimpleNamespace(start=lambda: None)):
                tm.PluginServerHandler.do_POST(handler)
            self.assertEqual(replies[-1][0], 200)

    def test_clone_trailing_slash_stays_in_child_directory(self):
        sentinel = Path(self.temp.name)/'index.html'; sentinel.write_text('unrelated')
        clone = tm.build_cloner('example.org', self.out, {'clone': True, 'clone_dir': 'archive/'}, 0)
        clone.save_page('https://example.org/', HTML); clone.write_manifest()
        self.assertEqual(clone.root, str((Path(self.temp.name)/'archive').resolve()))
        self.assertEqual(sentinel.read_text(), 'unrelated')

    def test_robots_body_is_bounded_and_oversize_denies(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size):
                self.size = size
                return b'x'*size
        response = Response()
        with patch.object(tm, 'urlopen', return_value=response), \
                patch.object(tm, 'MAX_ROBOTS_BYTES', 8, create=True), patch.object(tm, 'log') as log:
            robots = tm.get_robots('example.org')
        self.assertEqual(response.size, 9)
        self.assertFalse(robots.can_fetch('*', 'https://example.org/'))
        self.assertIn('body exceeds limit; assuming deny-all', log.call_args.args[0])

    def test_stop_during_reservation_is_not_cleared_by_worker(self):
        self.allow_robots()
        class SynchronousThread:
            def __init__(self, target, args, **kwargs): self.target, self.args = target, args
            def start(self): self.target(*self.args)
        def stop_during_setup(*args):
            tm.CRAWL_CANCEL = True
        handler = SimpleNamespace(path='/crawl', server=SimpleNamespace(crawl_delay=0),
            _origin_ok=lambda: True, _read_json=lambda: {'url': 'https://example.org/'},
            _send_json=lambda *args: None)
        with patch.object(tm, 'build_cloner', side_effect=stop_during_setup), \
                patch.object(tm.threading, 'Thread', SynchronousThread), \
                patch.object(tm, 'fetch_and_extract') as fetch:
            tm.PluginServerHandler.do_POST(handler)
        fetch.assert_not_called()

    def test_cancel_before_worker_does_not_refresh_existing_bytes(self):
        tm.append_to_file(self.out, 'preserve existing bytes', 'https://example.org/')
        tm.CRAWL_CANCEL = True
        with patch.object(tm, 'get_robots') as robots, patch.object(tm, 'fetch_and_extract') as fetch:
            tm.crawl('https://example.org/', 'example.org', 0, 0, force_refresh=True,
                     out_file=self.out, _reserved=True)
        self.assertIn('preserve existing bytes', Path(self.out).read_text())
        robots.assert_not_called(); fetch.assert_not_called()

    def test_base_href_is_used_before_same_host_filter(self):
        self.assertEqual(tm.links_from('<base href="/v2/"><a href="intro">Intro</a>',
                                      'https://example.org/docs/index.html', 'example.org'),
                         ['https://example.org/v2/intro'])
        self.assertEqual(tm.links_from('<base href="https://elsewhere.example/"><a href="intro">Intro</a>',
                                      'https://example.org/docs/index.html', 'example.org'), [])

    def test_serve_with_seeds_keeps_process_alive(self):
        thread = SimpleNamespace(start=lambda: None)
        with patch.object(tm.sys, 'argv', ['text_mirror', 'https://example.org/', '--serve', '--out', self.out]), \
                patch.object(tm.threading, 'Thread', return_value=thread), \
                patch.object(tm, 'crawl', return_value=0), \
                patch.object(tm.time, 'sleep', side_effect=KeyboardInterrupt) as sleep:
            tm.main()
        sleep.assert_called_once_with(1)

    def test_increasing_depth_resumes_retained_frontier(self):
        self.allow_robots()
        root = 'https://example.org/'; a = root+'a'; b = root+'b'
        links = {root: [a], a: [b], b: []}
        def fetched(url, *args): return url, 'body '+url, links[url], HTML
        with patch.object(tm, 'fetch_and_extract', side_effect=fetched):
            tm.crawl(root, 'example.org', 0, 1, out_file=self.out)
            self.assertNotIn('URL: '+b, Path(self.out).read_text())
            tm.crawl(root, 'example.org', 0, 2, out_file=self.out)
        self.assertIn('URL: '+b, Path(self.out).read_text())

    def test_atomic_duplicate_append_and_symlink(self):
        url = 'https://example.org/a'
        errors = []
        barrier = threading.Barrier(12)
        def append():
            try:
                barrier.wait(timeout=3)
                tm.append_to_file(self.out, 'body', url)
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=append, daemon=True) for _ in range(12)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=3)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(Path(self.out).read_text().count('URL: '), 1)
        outside = Path(self.temp.name)/'outside'; outside.write_text('untouched')
        link = Path(self.temp.name)/'link.md'; link.symlink_to(outside)
        with self.assertRaises(OSError): tm.append_to_file(str(link), 'bad', 'https://example.org/b')
        self.assertEqual(outside.read_text(), 'untouched')

    def test_cancel_restores_batch_with_depth(self):
        self.allow_robots()
        urls = [f'https://example.org/{n}' for n in range(11)]
        Path(self.out).write_text('')
        tm.save_state('example.org', self.out, {}, urls, [(u, 2) for u in urls])
        def cancelled(*args):
            tm.CRAWL_CANCEL = True
            return args[0], 'body', [], HTML
        with patch.object(tm, 'fetch_and_extract', side_effect=cancelled):
            tm.crawl(urls[0], 'example.org', 0, 0, out_file=self.out)
        state = tm.load_state('example.org', self.out)
        self.assertEqual({x['url'] for x in state['queue']}, set(urls))
        self.assertEqual({x['depth'] for x in state['queue']}, {2})

    def test_force_refresh_does_not_reuse_old_crawled(self):
        self.allow_robots()
        url = 'https://example.org/a'; child = 'https://example.org/b'
        tm.append_to_file(self.out, 'old output', url)
        tm.save_state('example.org', self.out, {url: 'old', child: 'old'}, [url, child], [])
        with patch.object(tm, 'fetch_and_extract', return_value=(url, 'new', [], HTML)):
            tm.crawl(url, 'example.org', 0, 0, force_refresh=True, out_file=self.out)
        self.assertEqual(set(tm.load_state('example.org', self.out)['crawled']), {url})
        self.assertNotIn('old output', Path(self.out).read_text())

    def test_clone_bypasses_llms_and_releases_after_finalization(self):
        clone = SimpleNamespace(pages=1, assets=1, failed={}, root=self.temp.name)
        events = []
        clone.fetch_assets = lambda: events.append(('fetch', tm.CRAWL_ACTIVE))
        clone.write_manifest = lambda: events.append(('manifest', tm.CRAWL_ACTIVE))
        with patch.object(tm, 'try_llms_acquire', return_value=3) as acquire, \
                patch.object(tm, '_crawl_impl', return_value=1):
            self.assertEqual(tm.crawl('https://example.org/', 'example.org', 0, 0,
                                      cloner=clone), 1)
            acquire.assert_not_called()
        self.assertEqual(events, [('fetch', True), ('manifest', True)])
        self.assertFalse(tm.CRAWL_ACTIVE)

    def test_llms_job_cleanup_on_setup_failures(self):
        with patch.object(tm, 'CRAWL_LLMS_OUT_ROOT', self.temp.name):
            for url in ['https://[bad/', 'https://../', 'https://example.org/']:
                tm.CRAWL_LLMS_ACTIVE = True
                tm.CRAWL_LLMS_CURRENT = {'url': url}
                tm.CRAWL_LLMS_QUEUE.clear()
                with patch.object(tm.os, 'makedirs', side_effect=OSError('synthetic failure')):
                    tm._crawl_llms_txt_job(url)
                self.assertFalse(tm.CRAWL_LLMS_ACTIVE)
                self.assertIsNone(tm.CRAWL_LLMS_CURRENT)
                self.assertEqual(tm.CRAWL_LLMS_HISTORY[-1]['status'], 'error')

    def test_nonfinite_cli_delay_is_rejected_before_acquisition(self):
        with patch.object(tm.sys, 'argv', ['text_mirror', '--delay', 'nan', '--out', self.out]), self.assertRaises(SystemExit):
            tm.main()

    def test_api_rejects_rebinding_host_without_origin(self):
        handler = SimpleNamespace(headers={'Host': 'attacker.example:8765'})
        self.assertFalse(tm.PluginServerHandler._origin_ok(handler))

    def test_json_and_url_validation(self):
        for value in ['https://../', 'file:///tmp/a', 'https://example.org/\nignore rules',
                      [], 'https://user:password@example.org/', 'https://[bad/']:
            with self.assertRaises((ValueError, TypeError)): tm.validated_url(value)
        for raw in [b'[]', b'1', b'null', b'{"url":12}', b'{"url":"https://example.org/","html":[]}']:
            handler = SimpleNamespace(headers={'Content-Length': str(len(raw))}, rfile=io.BytesIO(raw))
            with self.assertRaises((ValueError, TypeError)):
                tm.PluginServerHandler._read_json(handler)
        for size in ['-1', str(9*1024*1024), 'x']:
            handler = SimpleNamespace(headers={'Content-Length': size}, rfile=io.BytesIO(b'{}'))
            with self.assertRaises(ValueError): tm.PluginServerHandler._read_json(handler)

    def test_api_no_content_and_invalid_request_responses(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), tm.PluginServerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        def request(payload):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            self.addCleanup(connection.close)
            connection.request('POST', '/save', json.dumps(payload), {'Content-Type': 'application/json'})
            result = connection.getresponse(); body = result.read()
            return result.status, body
        with patch.object(tm, 'process_single_url', return_value=False):
            self.assertEqual(request({'url': 'https://example.org/'})[0], 502)
        for payload in [[], {'url': []}, {'url': 'file:///a'}, {'url': 'https://[bad/'}]:
            self.assertEqual(request(payload)[0], 400)

    def test_browser_clone_confinement_and_delay(self):
        with patch.object(sc, 'SiteCloner') as constructor:
            tm.build_cloner('example.org', self.out,
                            {'clone': True, 'clone_dir': '../../escape'}, delay=1.5)
            self.assertEqual(constructor.call_args.kwargs['delay'], 1.5)
            self.assertEqual(Path(constructor.call_args.args[0]).parent.resolve(), Path(self.temp.name).resolve())
        with patch.object(tm, 'SHARD_COUNT', 2), self.assertRaises(ValueError):
            tm.build_cloner('example.org', self.out, {'clone': True})

    def test_shard_handoff_preserves_depth(self):
        with patch.object(tm, 'SHARD_COUNT', 2), patch.object(tm, 'SHARD_INDEX', 1):
            tm.save_state('example.org', self.out, {}, ['https://example.org/deep'], [],
                          extra={'depths': {'https://example.org/deep': 3}})
        with patch.object(tm, 'SHARD_COUNT', 2), patch.object(tm, 'SHARD_INDEX', 0), \
                patch.object(tm, 'owns', return_value=True):
            q = deque(); depths = {}
            tm.merge_siblings('example.org', self.out, {}, set(), q, depths, max_depth=2)
            self.assertEqual(list(q), [])
            tm.merge_siblings('example.org', self.out, {}, set(), q, depths, max_depth=4)
            self.assertEqual(list(q), [('https://example.org/deep', 3)])


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.logs = []
        self.clone = sc.SiteCloner(self.temp.name, 'example.org', 'test', log=self.logs.append)
        self.real_fetch = sc.fetch_bytes
        p = patch.object(sc, 'fetch_bytes', side_effect=AssertionError('unmocked fetch'))
        p.start(); self.addCleanup(p.stop)

    def test_url_mapping_collision_and_metadata_boundaries(self):
        urls = ['https://example.org/a:b', 'https://example.org/a_b',
                'https://example.org/_clone-manifest.json', 'https://example.org/_external/h/x',
                'https://h:8080/x', 'https://h_8080/x', 'https://example.org/a%20b.png',
                'https://example.org/a b.png', 'http://example.org/a:b']
        paths = [sc.url_to_rel_path(u, 'example.org') for u in urls]
        self.assertEqual(len(set(paths)), len(urls))
        self.assertNotIn('_clone-manifest.json', paths)
        self.assertTrue(all(Path(sc.safe_join(self.temp.name, p)).is_relative_to(Path(self.temp.name).resolve()) for p in paths))

    def test_css_import_syntax_and_fragments(self):
        css = '@import url("theme.css"); @import "print.css" print; x {filter:url(#blur)}'
        result = sc.rewrite_css(css, 'https://example.org/main.css', lambda u: '../asset.css')
        self.assertIn('@import url("../asset.css");', result)
        self.assertIn('@import "../asset.css" print;', result)
        self.assertIn('url(#blur)', result)
        self.assertEqual(sc.css_urls('a{src:url("//[bad")} b{src:url(ok.png)}',
                                     'https://example.org/main.css'), ['https://example.org/ok.png'])

    def test_html_fragments_srcset_and_charset(self):
        html = ('<html><head><meta charset="windows-1252"></head><body>café'
                '<a href="#part">go</a><img srcset="a.png 1x, b.png 2x">'
                '<h1 id="part">part</h1></body></html>')
        links = sc.page_links(html, 'https://example.org/page')
        self.assertIn(('https://example.org/a.png', True), links)
        self.assertIn(('https://example.org/b.png', True), links)
        result = sc.rewrite_html(html, 'https://example.org/page', lambda u: u).decode()
        self.assertIn('charset="utf-8"', result)
        self.assertIn('café', result)
        self.assertIn('#part', result)

    def test_finalization_uses_only_written_resources(self):
        url = 'https://example.org/page'
        self.clone.save_page(url, '<html><body><a href="#part">anchor</a>'
                             '<a href="unvisited">live</a><img src="missing.png">'
                             '<img src="ok%20image.png#icon"><h1 id="part">part</h1></body></html>')
        def fetch(u, ua):
            if 'missing' in u: raise OSError('synthetic')
            return b'image', 'image/png', u
        with patch.object(sc, 'fetch_bytes', side_effect=fetch): self.clone.fetch_assets()
        self.clone.write_manifest()
        result = Path(sc.safe_join(self.temp.name, self.clone.planned[url])).read_text()
        self.assertIn('#part', result); self.assertIn('#icon', result)
        self.assertIn('https://example.org/unvisited', result)
        self.assertIn('https://example.org/missing.png', result)
        self.assertNotIn('https://example.org/ok%20image.png', result)
        self.assertTrue((Path(self.temp.name)/'index.html').is_file())
        self.assertIn('clone-asset-error OSError', self.logs)
        self.assertEqual(json.loads((Path(self.temp.name)/'_clone-manifest.json').read_text())['assets'], 1)

    def test_clone_cancel_preserves_pending_without_fetch(self):
        self.clone._queue_asset('https://example.org/a.png')
        self.clone.cancelled = lambda: True
        with patch.object(sc, 'fetch_bytes') as fetch:
            self.clone.fetch_assets()
        fetch.assert_not_called()
        self.assertEqual(list(self.clone.pending), ['https://example.org/a.png'])

    def test_resume_preserves_pending_and_failure_history(self):
        self.clone.save_page('https://example.org/', '<img src="a.png"><img src="b.png">')
        self.clone.max_assets = 1
        with patch.object(sc, 'fetch_bytes', side_effect=OSError('synthetic')):
            self.clone.fetch_assets()
        self.clone.write_manifest()
        resumed = sc.SiteCloner(self.temp.name, 'example.org', 'test', max_assets=1)
        self.assertEqual(resumed.failed, self.clone.failed)
        with patch.object(sc, 'fetch_bytes', return_value=(b'picture', 'image/png', 'https://example.org/b.png')):
            resumed.fetch_assets()
        resumed.write_manifest()
        self.assertEqual(resumed.assets, 1)
        self.assertEqual(list(resumed.pending), [])
        self.assertIn(Path(resumed.planned['https://example.org/b.png']).name,
                      (Path(self.temp.name)/resumed.planned['https://example.org/']).read_text())

    def test_clone_resume_refuses_corrupt_identity_and_symlink_source(self):
        url = 'https://example.org/'
        self.clone.save_page(url, '<p>original</p>'); self.clone.write_manifest()
        manifest_path = Path(self.temp.name)/'_clone-manifest.json'
        original = manifest_path.read_text(); manifest = json.loads(original)
        manifest['files'][url] = '../outside'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): sc.SiteCloner(self.temp.name, 'example.org', 'test')
        manifest_path.write_text(original)
        source = Path(self.temp.name)/self.clone._original_rel(url)
        source.unlink(); source.symlink_to(manifest_path)
        with self.assertRaises(OSError): sc.SiteCloner(self.temp.name, 'example.org', 'test')
        self.assertEqual(manifest_path.read_text(), original)

    def test_parentheses_inside_quoted_css_urls(self):
        css = 'x{background:url("image(1).png")}'
        self.assertEqual(sc.css_urls(css, 'https://example.org/style.css'),
                         ['https://example.org/image(1).png'])
        self.assertIn('https://example.org/image(1).png',
                      sc.rewrite_css(css, 'https://example.org/style.css', lambda u: u))

    def test_failed_attempt_pacing_and_limit(self):
        clone = sc.SiteCloner(self.temp.name, 'example.org', 'test', delay=1, max_assets=2)
        for n in range(3): clone._queue_asset(f'https://example.org/{n}.png')
        with patch.object(sc, 'fetch_bytes', side_effect=OSError('synthetic')):
            sleeps = []; clone.fetch_assets(sleep=sleeps.append)
        self.assertEqual(sleeps, [1, 1]); self.assertEqual(len(clone.pending), 1)
        self.assertEqual(len(clone.failed), 2)

    def test_redirected_css_uses_effective_url(self):
        self.clone._queue_asset('https://example.org/style.css')
        seen = []
        def fetch(url, ua):
            seen.append(url)
            if url.endswith('style.css'):
                return b'x{src:url(font.woff)}', 'text/css', 'https://example.org/v2/main.css'
            return b'font', 'font/woff', url
        with patch.object(sc, 'fetch_bytes', side_effect=fetch): self.clone.fetch_assets()
        self.assertIn('https://example.org/v2/font.woff', seen)

    def test_clone_write_rejects_symlink_components(self):
        outside = Path(self.temp.name)/'outside'; outside.mkdir()
        root = Path(self.temp.name)/'root'; clone = sc.SiteCloner(str(root), 'example.org', 'test')
        (root/'link').symlink_to(outside, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)): clone._write('link/stolen', b'bad')
        self.assertFalse((outside/'stolen').exists())
        with self.assertRaises(ValueError): sc.SiteCloner(str(root), 'example.org', 'test', owns=lambda u: False)

    def test_asset_body_size_is_bounded(self):
        response = SimpleNamespace(headers={}, geturl=lambda: 'https://example.org/a',
                                   read=lambda n: b'x'*n)
        class Response:
            def __enter__(self): return response
            def __exit__(self, *args): return False
        with patch.object(sc, 'MAX_ASSET_BYTES', 8), \
                patch.object(sc.urllib.request, 'urlopen', return_value=Response()), \
                self.assertRaises(ValueError):
            self.real_fetch('https://example.org/a', 'test')


class ToolTests(unittest.TestCase):
    def load_tool(self, name):
        spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_static_generator_rejects_escape_and_includes_binary_async(self):
        module = self.load_tool('maintain_docs')
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root/'README.md').symlink_to(Path(outside)/'secret.md')
            with patch.object(module, 'ROOT', root), patch.object(module, 'inventory', return_value=['README.md']), self.assertRaises(ValueError):
                module.products()
            (root/'README.md').unlink()
            (root/'asset.png').write_bytes(b'\x89PNG\x00\xff')
            (root/'async.py').write_text('async def fetch():\n    pass\n')
            with patch.object(module, 'ROOT', root), patch.object(module, 'DOCS', []), \
                    patch.object(module, 'inventory', return_value=['asset.png', 'async.py']):
                products = module.products()
            cards = json.loads(products['docs/high_signal_file_index.json'])
            self.assertEqual({c['path'] for c in cards}, {'asset.png', 'async.py'})
            self.assertEqual(cards[1]['exports'], ['fetch'])

    def test_rotation_refuses_symlink_ancestors_and_ignores_fenced_headings(self):
        module = self.load_tool('rotate_workflow_logs')
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            text = '# Log\n\n'+''.join(f'## v{i} - date\n'+('content '*5)+'\n' for i in range(12))
            text = text.replace('## v0 - date', '## v0 - date\n```markdown\n## v999\n```')
            (root/'memory.md').write_text(text)
            (root/'docs').symlink_to(outside, target_is_directory=True)
            with patch.object(module, 'LIMIT', 250), patch.object(module, 'KEEP', 3), self.assertRaises(ValueError):
                module.rotate(root)
            (root/'docs').unlink()
            with patch.object(module, 'LIMIT', 250), patch.object(module, 'KEEP', 3):
                module.rotate(root)
            retained = (root/'memory.md').read_text()
            self.assertIn('## v11 ', retained); self.assertNotIn('## v999', retained)
            self.assertLessEqual(len(retained.encode()), 250)
            archives = list((root/'docs/archive').glob('*.md'))
            self.assertTrue(any('## v999' in p.read_text() for p in archives))

    def test_rotation_preserves_a_writer_that_appends_during_handoff(self):
        module = self.load_tool('rotate_workflow_logs')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '# Log\n'+''.join(f'## v{i} - date\ncontent contents\n' for i in range(12))
            (root/'memory.md').write_text(original)
            rename = module.os.rename
            def concurrent_rename(src, dst, **kwargs):
                rename(src, dst, **kwargs)
                with (root/'docs/archive'/dst).open('a') as stream:
                    stream.write('concurrent writer text\n')
            with patch.object(module, 'LIMIT', 120), patch.object(module.os, 'rename', side_effect=concurrent_rename), self.assertRaises(ValueError):
                module.rotate(root)
            self.assertIn('concurrent writer text', (root/'memory.md').read_text())
            self.assertTrue(any(p.read_text().startswith(original) for p in (root/'docs/archive').glob('*.md')))

    def test_generator_uses_only_tracked_approved_source(self):
        module = self.load_tool('maintain_docs')
        result = SimpleNamespace(stdout=b'README.md\0out.md\0scripts/tool.py\0docs/archive/raw.md\0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'scripts').mkdir(); (root/'docs/archive').mkdir(parents=True)
            for path in ['README.md', 'out.md', 'scripts/tool.py', 'docs/archive/raw.md']:
                (root/path).write_text('# Synthetic title')
            with patch.object(module, 'ROOT', root), patch.object(module.subprocess, 'run', return_value=result) as git:
                paths = module.inventory()
        self.assertNotIn('--others', git.call_args.args[0])
        self.assertEqual(paths, ['README.md', 'scripts/tool.py'])

    def test_installer_propagates_verification_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory)/'python'
            fake.write_text("#!/bin/sh\nif [ \"$1\" = -m ]; then exit 0; fi\nexit 1\n")
            fake.chmod(0o700)
            result = subprocess.run(['bash', str(ROOT/'scripts/install.sh')],
                                    env={**os.environ, 'PYTHON': str(fake)}, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_funding_yaml_parses(self):
        import yaml
        data = yaml.safe_load((ROOT/'.github/FUNDING.yml').read_text())
        self.assertEqual(data['github'], 'mithudso')


if __name__ == '__main__':
    unittest.main()
