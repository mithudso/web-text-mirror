# Known issues and maintainer choices

| Surface | Exact limitation / action |
|---|---|
| Legacy state | Host-only state predates destination identity. It is preserved and not reused by the new keyed state. Use a new output destination for a clean post-upgrade crawl; retain the prior corpus. No destructive migration runs automatically. |
| Clone format upgrade | Version2 manifests retain canonical HTML/CSS and cumulative identities. Older/invalid manifests are refused without overwrite; choose a new clone directory. Assets/page source reads are bounded at 32 MiB. |
| HTML clone sharding | Unsupported; construction/CLI rejects it. Text-only sharding remains supported with depth metadata. |
| Cloning failures/caps | Unavailable resources keep live absolute references. A partial clone is not wholly offline; inspect failed/pending manifest entries. |
| Resource limits | Assets are bounded at 32 MiB each; max-assets bounds attempts. BFS/text state still grows with the URL space; set max-depth/max-pages. |
| Dynamic sites | CLI fetches raw HTML. The extension can submit a rendered DOM; dynamically loaded subsequent assets/API interactions are not replayed. |
| Local trust | API has no user authentication. Any local process and allowlisted extension can call it. It is not a multi-user or internet-facing service. |
| Robots | Robots bodies above 512 KiB deny with a log. Existing behavior allows 4xx and transport-unavailable robots, denies 5xx. This is a documented project choice; transport fail-open is not an RFC-compliance guarantee. |
| Optional integrations | Host tools/paths are external and unversioned. Agent route may incur charges; distill route performs semantic indexing. No live integration validation or embedding execution occurred in maintenance. Indexer exit success is not independent backend readback. |
| Dependency bootstrap | First import can pip-install with existing escalation strategies. Preprovision a venv. Runtime floors are updated; full transitive reproducibility is not locked. |
| Browser/OS coverage | Chrome minimum is 116 for sidePanel.open. Node fixture tests do not establish real-browser behavior. POSIX no-follow writes are tested on macOS/Ubuntu; Windows is unsupported by the clone writer. |
| Policy choices | Existing MIT license and code of conduct retained. No new security response SLA, compliance attestation, license or legal promise is supplied. Maintainer must choose any future policy. |
| Workflow integration | Hub registry work is delegated to the batch supervisor. Semantic generation stays paused. Global skill installation, concept-tree mutation and daemon activation are outside this repo task. |
