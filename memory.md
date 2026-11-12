# web-text-mirror Memory Log

## v1.0.1 - 2026-11-12
- User request:
  - Full repository maintenance, bootstrap and source audit with verified remote delivery.
- Completed:
  - Destination/resume, cancellation, refresh, clone safety/link handling, API validation, optional worker cleanup and extension error fixes.
  - Offline adversarial regression fixtures; CI/static drift gates; maintained wiki and generated reference/operation/route inventories.
  - Full source/config inventory and reports in docs; no file cap, model benchmark, corpus mutation, service activation or semantic generation.
- In progress:
  - Delivery verification is recorded in the external task receipt; this source log describes the reviewed candidate.
- Next steps:
  - Use the testing and maintenance runbooks. Treat optional live tools and maintainer policy choices as separate scope.

## v1.1 - 2026-08-20
- User request:
  - Commit the local serve-default change and doc touch-ups; sync everywhere
- Completed:
  - scripts/text_mirror.py: no-arg invocation now defaults to --serve
  - README.md, SKILL.md, docs/runbooks/extension-server.md updated for the new
    no-arg behavior
- In progress:
  - None
- Next steps:
  - None

## v1.0 - 2026-08-20
- User request:
  - Bootstrap: initialized all standard workflow, documentation, and tooling files
    (mdb-tam standard, Python-adapted)
- Completed:
  - Workflow: CLAUDE.md, .github/copilot-instructions.md, AGENTS.md, GEMINI.md,
    memory.md, prompts.md
  - Dotfiles: .editorconfig, .gitattributes, .gitignore (extended), .env.example,
    .vscode/{settings,extensions,launch}.json
  - GitHub: workflows/ci.yml, dependabot.yml, CODEOWNERS, PULL_REQUEST_TEMPLATE.md,
    ISSUE_TEMPLATE/{bug_report,feature_request}.md, SECURITY.md
  - Docs suite: README.md, docs/{ARCHITECTURE,DEVELOPMENT,COMPONENTS,SECURITY,MCP,
    TESTING,INSTALLATION,requirements,codebase-overview,integrations-and-assumptions,
    known-issues,onboarding,logging,caching-and-optimization,external-calls}.md,
    docs/high_signal_file_index.json, docs/runbooks/{run-a-crawl,extension-server}.md
  - Community: CONTRIBUTING.md, CODE_OF_CONDUCT.md
  - Code: scripts/text_mirror.py updated to the code-deep-optimizer-hardened version
    (robots fail-open, 127.0.0.1 bind, Origin allowlist, out_file confinement,
    single-flight crawl, atomic state, global rate limiter); tests/test_text_mirror.py
    added (ported CDO verification harness); requirements.txt added
  - Hygiene: untracked .DS_Store and text-mirror/crawl.log removed from git index
- In progress:
  - None
- Next steps:
  - Choose and add a LICENSE (deliberately left TODO — legal choice)
  - Review generated docs for accuracy; fill any `# TODO:` placeholders
  - Reconcile uncommitted local changes to scripts/text_mirror.py in the main
    working tree (PyInstaller experiments: build/, dist/, text_mirror.spec)
