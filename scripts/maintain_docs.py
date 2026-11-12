#!/usr/bin/env python3
"""Generate static reference indexes from maintained source; never import the app.

Run from any directory: python scripts/maintain_docs.py [--check]. No embeddings,
network, services or runtime data are involved. Generated output uses source paths,
AST symbols and checked-in documentation only.
"""
import argparse
import ast
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {'docs/high_signal_file_index.json', 'docs/codebase-overview.md',
             'docs/llm-repo-index.json', 'docs/operations-registry.json',
             'docs/tool-inventory.json', 'llms.txt', 'llms-full.txt', 'llms-small.txt',
             'llms-facts.txt'}
DOCS = ['README.md', 'docs/wiki/README.md', 'docs/ARCHITECTURE.md', 'docs/DEVELOPMENT.md',
        'docs/COMPONENTS.md', 'docs/SECURITY.md', 'docs/TESTING.md', 'docs/INSTALLATION.md',
        'docs/integrations-and-assumptions.md', 'docs/known-issues.md', 'docs/external-calls.md']
OPERATIONS = [
    {'id': 'page-fetch', 'source': 'scripts/text_mirror.py', 'symbol': 'fetch_and_extract',
     'transport': 'HTTP(S)', 'target': 'operator-selected website', 'readOnly': True,
     'verifyDatastore': False, 'retryPolicy': 'no application retry', 'trigger': 'CLI seeds or POST /crawl',
     'failure': 'fetch-error/no-content; skip URL', 'remediation': 'operator reviews URL/connectivity'},
    {'id': 'single-save', 'source': 'scripts/text_mirror.py', 'symbol': 'process_single_url',
     'transport': 'HTTP(S) or supplied DOM', 'target': 'operator-selected page', 'readOnly': False,
     'verifyDatastore': 'offline regression checks URL block after append',
     'retryPolicy': 'manual retry; duplicate suppression per destination', 'trigger': 'POST /save',
     'failure': 'save-error or 502 no content', 'remediation': 'operator checks fetch/extraction'},
    {'id': 'robots', 'source': 'scripts/text_mirror.py', 'symbol': 'get_robots',
     'transport': 'HTTP(S)', 'target': '/robots.txt', 'readOnly': True, 'verifyDatastore': False,
     'retryPolicy': 'other scheme after transport failure', 'trigger': 'crawl setup',
     'failure': '4xx allow; 5xx deny; both transports unavailable allow with log',
     'remediation': 'operator reviews robots and transport diagnostics'},
    {'id': 'asset-fetch', 'source': 'scripts/site_clone.py', 'symbol': 'fetch_bytes',
     'transport': 'HTTP(S)', 'target': 'discovered asset URL', 'readOnly': True,
     'verifyDatastore': False, 'retryPolicy': 'none; bounded timeout/size, paced attempts',
     'trigger': '--clone after page acquisition', 'failure': 'manifest failed entry + clone-asset-error',
     'remediation': 'operator reviews failed/pending manifest; unavailable links remain absolute'},
    {'id': 'dependency-bootstrap', 'source': 'scripts/text_mirror.py', 'symbol': 'ensure_deps',
     'transport': 'subprocess/PyPI', 'target': 'pip', 'readOnly': False, 'verifyDatastore': 'import discovery',
     'retryPolicy': 'four existing pip strategies', 'trigger': 'first import with missing dependencies',
     'failure': 'bootstrap error / process exit', 'remediation': 'use a preprovisioned virtual environment'},
    {'id': 'llms-acquisition', 'source': 'scripts/text_mirror.py', 'symbol': 'try_llms_acquire',
     'transport': 'optional workstation Python module/HTTP(S)', 'target': 'site llms.txt family',
     'readOnly': False, 'verifyDatastore': 'read generated URL headers', 'retryPolicy': 'fall back to crawl',
     'trigger': 'fresh unsharded non-clone crawl unless --no-prefer-llms',
     'failure': 'llms acquire error; fallback', 'remediation': 'disable optional acquisition'},
    {'id': 'llms-agent', 'source': 'scripts/text_mirror.py', 'symbol': '_crawl_llms_txt_job',
     'transport': 'optional subprocess/model/network', 'target': 'claude -p', 'readOnly': False,
     'verifyDatastore': 'changed output directory entries', 'retryPolicy': 'none; 3600s timeout',
     'trigger': 'POST /crawl_llms_txt (not bundled panel)', 'failure': 'job history error',
     'remediation': 'operator verifies CLI/skill and inspects local output; may incur charges'},
    {'id': 'semantic-distill', 'source': 'scripts/text_mirror.py', 'symbol': 'run_distill_job',
     'transport': 'optional subprocess/semantic model', 'target': 'external distill_offline.py then docset_indexer.py',
     'readOnly': False, 'verifyDatastore': 'master-file existence; indexer exit only',
     'retryPolicy': 'none; 600s + 120s timeouts', 'trigger': 'POST /distill (not bundled panel)',
     'failure': 'job status/error', 'remediation': 'operator authorizes semantic work separately and verifies backend'},
    {'id': 'panel-api', 'source': 'chrome-plugin/sidepanel.js', 'symbol': 'request',
     'transport': 'HTTP JSON', 'target': '127.0.0.1:8765', 'readOnly': False,
     'verifyDatastore': 'save response then list poll; server-side append tested offline',
     'retryPolicy': 'list polling; no automatic write retry', 'trigger': 'panel user gesture or refresh',
     'failure': 'panel status/error', 'remediation': 'operator checks local server response'},
    {'id': 'installer', 'source': 'scripts/install.sh', 'symbol': 'shell entrypoint',
     'transport': 'subprocess/PyPI', 'target': 'pip requirements', 'readOnly': False,
     'verifyDatastore': 'module import/version checks', 'retryPolicy': 'none; shell exits on failure',
     'trigger': 'bash scripts/install.sh', 'failure': 'nonzero exit', 'remediation': 'provision chosen virtual environment'},
    {'id': 'reference-generation', 'source': 'scripts/maintain_docs.py', 'symbol': 'inventory',
     'transport': 'local git subprocess/filesystem', 'target': 'maintained source/config/docs',
     'readOnly': False, 'verifyDatastore': '--check byte comparison', 'retryPolicy': 'none',
     'trigger': 'python scripts/maintain_docs.py', 'failure': 'nonzero exit / named drift paths',
     'remediation': 'regenerate static files and review diff'},
]
ROUTES = [('/list', 'GET', 'saved URLs and crawl stats'), ('/save', 'POST', 'save supplied/fetched page'),
          ('/crawl', 'POST', 'start single-flight crawl'), ('/stop', 'POST', 'request crawl cancellation'),
          ('/crawl_llms_txt', 'POST', 'optional billable editing-agent job'),
          ('/crawl_llms_txt/status', 'GET', 'optional agent queue/history'),
          ('/distill', 'POST', 'optional semantic distill/index job'),
          ('/distill_status', 'GET', 'optional semantic job status')]


def safe_path(relative):
    """Refuse symlink components before reading source or replacing references."""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'invalid repository path: {relative}')
    current = ROOT
    for part in path.parts:
        current = current/part
        if current.is_symlink():
            raise ValueError(f'refusing symlink component: {relative}')
    if not current.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f'path leaves repository: {relative}')
    return current


def inventory():
    result = subprocess.run(['git', 'ls-files', '-z', '--cached'],
                            cwd=ROOT, check=True, capture_output=True)
    roots = {'README.md', 'AGENTS.md', 'CLAUDE.md', 'SKILL.md', 'CONTRIBUTING.md',
             'LICENSE', 'CODE_OF_CONDUCT.md', 'SECURITY.md', 'CHANGELOG.md',
             'memory.md', 'prompts.md', 'pyproject.toml', 'requirements.txt',
             'requirements-dev.txt', '.env.example', '.editorconfig', '.gitattributes',
             '.gitignore', '.node-version', '.python-version'}
    def approved(path):
        if path.startswith('docs/archive/'):
            return path == 'docs/archive/README.md'
        return path in roots or path.startswith(('scripts/', 'tests/', 'chrome-plugin/',
                                                  '.github/', '.vscode/', 'docs/'))
    return sorted({p for p in result.stdout.decode().split('\0')
                   if p and approved(p) and p not in GENERATED and safe_path(p).is_file()})


def products():
    cards = []
    for path in inventory():
        file = safe_path(path)
        try:
            text = file.read_text(encoding='utf-8')
            if '\x00' in text:
                text = ''
        except UnicodeDecodeError:
            text = ''
        symbols, purpose = [], ''
        if file.suffix == '.py':
            module = ast.parse(text)
            symbols = [n.name for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            purpose = (ast.get_docstring(module) or '').split('\n')[0]
        if not purpose:
            purpose = next((line.lstrip('# ').strip() for line in text.splitlines()
                            if line.startswith('# ')), '') or f'Maintained {file.suffix or "configuration"} file'
        layer = ('test' if path.startswith('tests/') else 'frontend' if path.startswith('chrome-plugin/')
                 else 'backend' if path in ('scripts/text_mirror.py', 'scripts/site_clone.py')
                 else 'tooling' if path.startswith('scripts/') else 'docs' if file.suffix == '.md'
                 else 'config')
        cards.append({'path': path, 'purpose': purpose, 'layer': layer, 'exports': symbols,
                      'depends_on': (['scripts/site_clone.py', 'trafilatura', 'lxml']
                                     if path == 'scripts/text_mirror.py' else []),
                      'patterns': [], 'last_updated': '2026-11-12'})
    index = json.dumps(cards, indent=2, ensure_ascii=False)+'\n'
    overview = '# Codebase overview\n\nGenerated by `python scripts/maintain_docs.py`; no runtime data or embeddings.\n\n'
    overview += '| Path | Layer | Purpose |\n|---|---|---|\n'
    overview += ''.join(f'| `{c["path"]}` | {c["layer"]} | {c["purpose"].replace("|", "/")} |\n' for c in cards)
    overview += '\nGenerated files: '+', '.join(f'`{p}`' for p in sorted(GENERATED))+'.\n'
    overview += '\nIgnored: crawl/clone output, state, logs, virtual environments, caches and build artifacts. No vendored code is maintained.\n'
    ops = json.dumps({'operations': OPERATIONS, 'status': 'architecture-adapted',
                      'audit': {'contract': 'docs/external-calls.md',
                                'generic_service_standards': 'explicit applicability matrix; no dashboard/MCP service'}}, indent=2)+'\n'
    tools = json.dumps({'totalTools': 0, 'mcp': [], 'httpRoutes': [
        {'path': path, 'method': method, 'description': desc} for path, method, desc in ROUTES]}, indent=2)+'\n'
    header = '<!-- Generated by scripts/maintain_docs.py; source-derived static reference. -->\n\n'
    small = header+'# web-text-mirror\n\n'
    small += '\n'.join(f'- `{p}`: {c["purpose"]} [src: {p}]' for c in cards
                       if (p := c['path']) in ('scripts/text_mirror.py', 'scripts/site_clone.py', 'docs/wiki/README.md'))
    small += '\n\n- Test: `python tests/test_text_mirror.py`; `python -m unittest discover -s tests -p test_regressions.py -v`; `node --test tests/test_sidepanel.js`. [src: docs/TESTING.md]\n- Lint: `ruff check scripts/ tests/`; indexes: `python scripts/maintain_docs.py --check`. [src: docs/DEVELOPMENT.md]\n- Optional model/semantic routes require external workstation tools and are never exercised live by tests. [src: docs/integrations-and-assumptions.md]\n'
    llms = header+'# web-text-mirror\n\nWebsite-to-Markdown crawler, offline cloner and local Chrome side panel. [src: README.md]\n\n'
    llms += '\n'.join(f'- [{p}]({p})' for p in DOCS)
    llms += '\n\n- [llms-small.txt](llms-small.txt): quick reference\n- [llms-full.txt](llms-full.txt): maintained documentation\n- [llms-facts.txt](llms-facts.txt): sourced facts\n- [docs/codebase-overview.md](docs/codebase-overview.md): complete file map\n'
    full = header+'\n\n'.join(f'# Source: {p}\n\n'+safe_path(p).read_text(encoding='utf-8').rstrip() for p in DOCS)+'\n'
    facts = header+'# Sourced facts\n\n'
    facts += '- The crawler writes URL-banner Markdown and destination-scoped resume state. [src: scripts/text_mirror.py]\n'
    facts += '- HTML cloning uses a distinct resource namespace and rewrites links after acquisition. [src: scripts/site_clone.py]\n'
    facts += '- The API binds 127.0.0.1:8765; this is a local operator tool without user authentication. [src: scripts/text_mirror.py]\n'
    facts += '- No MCP server or semantic index is shipped; optional host integrations are separate. [src: docs/MCP.md; docs/integrations-and-assumptions.md]\n'
    return {'docs/high_signal_file_index.json': index, 'docs/llm-repo-index.json': index,
            'docs/codebase-overview.md': overview, 'docs/operations-registry.json': ops,
            'docs/tool-inventory.json': tools, 'llms.txt': llms, 'llms-small.txt': small,
            'llms-full.txt': full, 'llms-facts.txt': facts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    drift = []
    generated = products()
    for path, content in generated.items():
        target = safe_path(path)
        if target.is_file() and target.read_text(encoding='utf-8') == content:
            continue
        drift.append(path)
        if not args.check:
            fd, tmp = tempfile.mkstemp(prefix='.docs-', dir=target.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write(content)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
    if args.check and drift:
        raise SystemExit('Static references drifted; run python scripts/maintain_docs.py: '+', '.join(drift))
    print(f'Static references {"checked" if args.check else "updated"}: {len(generated)} files')


if __name__ == '__main__':
    main()
