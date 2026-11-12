# Runbook: safe maintenance

Precondition: inspect the branch, status, worktrees, open PRs and effective Git hooks.
Preserve active work and use an isolated worktree from fetched default when needed.
Preinstall dependencies in a venv, then run every command in [Testing](../TESTING.md).
Stage approved new source/docs explicitly before regeneration. The generator reads tracked
paths in approved source/config/docs families; arbitrary root outputs and archive bodies
are excluded. Regenerate with `python scripts/maintain_docs.py`; verify with `--check`.
Review the complete diff and stage task-owned files only. Keep optional host-tool
calls and semantic hooks paused unless separately authorized. Commit with a verified
command-scoped filter when a mixed hook contains indexing; preserve registry/validation.
Push, wait for final CI, merge, verify remote contents, and synchronize only a clean,
nondivergent original checkout. Remove only the task's clean merged worktree/branch.

Before upgrading an existing corpus, retain its output and legacy state. New state
is keyed by output basename/shard count, so use a new output destination for a clean
crawl. Do not delete, overwrite or graft old host-only state automatically. Verify
URL banners and clone manifests on synthetic fixtures before any real acquisition.

Workflow logs are local project history. `python scripts/rotate_workflow_logs.py`
archives full oversized source logs under docs/archive, keeps up to ten highest numeric
versions within 200 KiB, and refuses editor swaps or symlink ancestry. It ignores fenced
heading examples and bounds input at 16 MiB. Run it only when editors are idle; an
existing writer keeps its archived inode, so concurrent source bytes are preserved. `--check` only reports whether rotation is needed.

If checks fail, preserve diagnostics and fix the corroborated defect. If access or
required CI prevents delivery, push a recoverable draft checkpoint and record the
exact blocker. Escalate missing credentials/policy choices to the maintainer; do not
bypass controls or invent promises. Hub registration belongs to the batch supervisor.

Use a new clone directory when upgrading from legacy manifests. Supported manifests
resume cumulative pages/assets and preserve the original entry. Inspect failed/pending
entries; max-assets limits attempts per invocation, so pending assets can resume later.
Canonical HTML/CSS stays local in the clone directory; it is operator data, not source.
