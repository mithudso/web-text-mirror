# Repo bootstrap audit — 2026-11-12

Full update-to-ideal workflow, canonical prompt and both required references applied.
No previous repo-bootstrap audit ledger existed. Original checkout was clean `main`,
equal to fetched origin/main `2d38884`; all edits used a new isolated worktree. Existing
Dependabot PRs 9/10/11 were inspected and left untouched. Runtime dependency floors
and checkout action were updated in this task's own PR scope.

## Manifest accounting

| File/family | Disposition |
|---|---|
| `.github/copilot-instructions.md` | Present; reviewed and retained or refreshed against source |
| `CLAUDE.md` | Present; reviewed and retained or refreshed against source |
| `AGENTS.md` | Present; reviewed and retained or refreshed against source |
| `GEMINI.md` | Present; reviewed and retained or refreshed against source |
| `memory.md` | Present; reviewed and retained or refreshed against source |
| `prompts.md` | Present; reviewed and retained or refreshed against source |
| `docs/archive/README.md` | Present; reviewed and retained or refreshed against source |
| `scripts/rotate_workflow_logs.py` | Present; reviewed and retained or refreshed against source |
| `.editorconfig` | Present; reviewed and retained or refreshed against source |
| `.gitignore` | Present; reviewed and retained or refreshed against source |
| `.gitattributes` | Present; reviewed and retained or refreshed against source |
| `.node-version` | Present; reviewed and retained or refreshed against source |
| `.python-version` | Present; reviewed and retained or refreshed against source |
| `.env.example` | Present; reviewed and retained or refreshed against source |
| `.vscode/settings.json` | Present; reviewed and retained or refreshed against source |
| `.vscode/extensions.json` | Present; reviewed and retained or refreshed against source |
| `.vscode/launch.json` | Present; reviewed and retained or refreshed against source |
| `.vscode/mcp.json` | Inapplicable: no MCP dependency/server; documented in docs/MCP.md |
| `.mcp.json` | Inapplicable: no MCP dependency/server; documented in docs/MCP.md |
| `.github/workflows/ci.yml` | Present; reviewed and retained or refreshed against source |
| `.github/dependabot.yml` | Present; reviewed and retained or refreshed against source |
| `.github/CODEOWNERS` | Present; reviewed and retained or refreshed against source |
| `.github/PULL_REQUEST_TEMPLATE.md` | Present; reviewed and retained or refreshed against source |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Present; reviewed and retained or refreshed against source |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Present; reviewed and retained or refreshed against source |
| `.github/SECURITY.md` | Existing reporting channel retained; response SLA remains a maintainer choice |
| `LICENSE` | Existing policy retained unchanged; no new license/legal promise |
| `CONTRIBUTING.md` | Present; reviewed and retained or refreshed against source |
| `CODE_OF_CONDUCT.md` | Existing policy retained unchanged; no new license/legal promise |
| `docs/ARCHITECTURE.md` | Present; reviewed and retained or refreshed against source |
| `docs/DEVELOPMENT.md` | Present; reviewed and retained or refreshed against source |
| `docs/COMPONENTS.md` | Present; reviewed and retained or refreshed against source |
| `docs/SECURITY.md` | Present; reviewed and retained or refreshed against source |
| `docs/MCP.md` | Present; reviewed and retained or refreshed against source |
| `docs/TESTING.md` | Present; reviewed and retained or refreshed against source |
| `README.md` | Present; reviewed and retained or refreshed against source |
| `docs/codebase-overview.md` | Generated static reference; CI drift check |
| `docs/high_signal_file_index.json` | Generated static reference; CI drift check |
| `docs/llm-repo-index.json` | Generated static reference; CI drift check |
| `scripts/semantic_indexer.py` | Not added: semantic execution paused; static generation only |
| `scripts/watch_and_index.sh` | Not added: semantic execution paused; static generation only |
| `scripts/maintain_docs.py` | Present; reviewed and retained or refreshed against source |
| `docs/integrations-and-assumptions.md` | Present; reviewed and retained or refreshed against source |
| `docs/known-issues.md` | Present; reviewed and retained or refreshed against source |
| `docs/onboarding.md` | Present; reviewed and retained or refreshed against source |
| `docs/INSTALLATION.md` | Present; reviewed and retained or refreshed against source |
| `docs/requirements.md` | Present; reviewed and retained or refreshed against source |
| `docs/logging.md` | Present; reviewed and retained or refreshed against source |
| `docs/caching-and-optimization.md` | Present; reviewed and retained or refreshed against source |
| `docs/runbooks/run-a-crawl.md` | Present; reviewed and retained or refreshed against source |
| `docs/runbooks/extension-server.md` | Present; reviewed and retained or refreshed against source |
| `docs/runbooks/maintenance.md` | Present; reviewed and retained or refreshed against source |
| `server/src/lib/operations-registry.js` | Architecture-adapted: scripts/maintain_docs.py owns declarative operation/route references; no invented server/MCP operations runner |
| `scripts/generate-ops-registry-doc.mjs` | Architecture-adapted: scripts/maintain_docs.py owns declarative operation/route references; no invented server/MCP operations runner |
| `docs/operations-registry.json` | Generated static reference; CI drift check |
| `docs/tool-inventory.json` | Generated static reference; CI drift check |
| `docs/external-calls.md` | Present; reviewed and retained or refreshed against source |
| `docs/wiki/README.md` | Present; reviewed and retained or refreshed against source |

## Source, documentation and extended checks

- Baseline 22 one-file reviews (21 runtime/config/test plus legacy curated index),
  then seven new maintained files. Final runtime/config/test coverage: 28 of 28,
  with no file cap. Generated/static documentation has separate source-derived checks.
- Entire maintained crawler/cloner/extension/test/installer source and all manifest,
  editor, GitHub and toolchain configuration families were read. No vendor/minified
  runtime code exists. Ignored output/corpus, caches and environments are excluded.
- Single-file crawler architecture remains deliberate. Existing clone utility stays
  importable and documented; constants remain with their owners. No settings service,
  application server, dashboard or semantic daemon is invented.
- No repo-local agents, MCP servers, native messaging, offscreen document, OAuth/cookie/
  vault mechanism or local concept-tree file exists. Those checks are inapplicable.
  Global concept-tree/skill writes and installation are outside authorized repository scope.
- SKILL.md frontmatter/description/routing and every current CLI flag were checked as
  skill/prose data. No model trigger benchmark or global skill mutation was performed.
- Customer-data/secret review used tracked source paths and local redacted shape checks;
  no corpus/browser/customer exports were ingested. Existing MIT and conduct policy remain.
- Full external-call inventory records the optional host module, headless editing agent,
  semantic distiller and docset indexer. Generic service standards are explicitly adapted
  per call; independent backend readback for the optional indexer remains unavailable.
- Static reference generator is the sole writer of indexes, llms references and operation/
  route inventories. It includes all maintained paths, Python exports, and explicit generated
  and ignored categories. The generated route inventory has eight paths and zero MCP tools.
- Maintained wiki links the complete docs/reference/runbook suite (the KNOW-1255 standard).
- Workflow log rotation is a guarded POSIX utility; real logs were under threshold and
  were never rotated. Synthetic fixtures cover fences, symlink ancestry and concurrent bytes.

## Validation and applicability

See the [optimizer report](code-deep-optimizer-2026-11-12.md) for exact commands, baseline
failures, counterexamples and candidate outcomes. CI runs Python3.11/3.13 plus Node22,
including Python/JS/shell syntax, Ruff, smoke/regression suites and static reference drift.
No build/type-check command is configured. No held-out empirical eval/benchmark exists.
Actual merge/check evidence is preserved in the task's external delivery receipt.

## Remaining choices and limits

No security response SLA, new license, compliance attestation or policy was invented.
Optional live models/indexers, real-browser behavior, full transitive reproducibility,
Windows clone support and large-site performance remain unverified or unsupported as
listed in [known issues](known-issues.md). Sharded HTML cloning now fails explicitly;
text-only sharding retains depth metadata. Legacy state is preserved without automatic
migration; use a new output destination for a clean post-upgrade acquisition.

Semantic generation remains paused, including the inherited mixed post-commit hook.
The hash-gated command-scoped filter preserves registry registration and forwards every
other hook; no shared/local/global hook configuration was edited. Hub registry completion
is delegated to the batch supervisor rather than an unresolved product gap.

## Bootstrap convergence

Drift pass 1 found stale/missing clone, optional integration, test, wiki and index facts.
Drift pass 2 refreshed them against the repaired code and explicit architecture exceptions.
Final drift checks must pass before delivery. No quick or changed-only scope was used;
all manifest families above are accounted for. No claim of generic five-standard service
compliance or exhaustive live-runtime verification is made.

## External static dossier

The source-only crawl-repo-to-llms pass emitted eleven dossier artifacts outside this
repository. Census: 73 tracked paths, 39 deep cards, 34 explicitly shallow cards; no
file cap or omitted path. The static executable inventory parses every CLI option,
includes CI/install/test commands and environment names, and does not execute --help.
Header, byte-cap, path/card parity and provenance self-checks are saved externally.
The bounded 200-commit history pass ingests identities/times/churn only; author/message
semantics, reverts and chronology remain unknown. No index probe, semantic generation,
customer corpus or live-link acquisition occurred. Link reachability is unverified.
