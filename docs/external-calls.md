# External calls

The generated [operations inventory](operations-registry.json) is owned by
`python scripts/maintain_docs.py`; [route inventory](tool-inventory.json) lists all
8 HTTP routes and zero MCP tools. The registry records source symbols, transport,
targets, triggers, retry/error/remediation policy and actual persistence checks.

| Operation | Logger / test / documentation | Retry and safety |
|---|---|---|
| Page fetch and save | fetch-error/no-content/save-error; smoke + API fixture; Components | No automatic write retry; global request throttle |
| Robots | robots HTTP/unreachable events; synthetic failure fixtures; Architecture | Other scheme on transport failure; documented allow/deny policy |
| Asset fetch | clone-asset-request/ok/error; clone fixtures; Components | Every attempt paced; bounded response; no retry; manifest failure accounting |
| Pip bootstrap + install | bootstrap/installer stdout and failure exit; static command checks; Installation | Existing import-time escalation; explicit venv preferred |
| Optional llms_acquire | acquisition/fallback events; blocked/mock in suites; Integrations | Fallback to text crawl; never called during maintenance |
| Optional agent | start/finish + job history; setup-failure fixture; Integrations | Bounded FIFO/timeouts; billable external capability; no automatic retry |
| Optional distill/index | job status/index outcome; subprocess mocks only; Integrations | Semantic writes; external tools; exit-only backend verification residual |
| Panel API | visible status + console error; VM fixtures; extension runbook | No write retry; status poll; HTTP failures checked |
| Static generator | command output/drift paths; CI --check; Development | Local git read + atomic generated-file replacement; no network/models |

## Five-standard service contract applicability

| Standard | This architecture |
|---|---|
| CLI/MCP operation trigger | Crawler/install/generator have direct CLI commands; browser save/stop and optional jobs use explicit documented local HTTP operations. No general-purpose operations runner is introduced. |
| Central JSONL error service | Inapplicable as a server-platform requirement: core uses local crawl.log/stdout; panel uses visible errors; job history is in memory. No new global error datastore is installed. |
| Remediation map | Inventory provides operation-specific manual remedies. No autonomous remediator is shipped or started. |
| Dashboard cards | Inapplicable: the small panel exposes current crawl stats and controls, not a service dashboard. No dashboard is invented. |
| Datastore readback | Markdown/clone writes have behavioral fixture checks; state/clone/generated references write atomically. Read-only calls have no datastore. Optional external indexer has an explicit independent-readback gap. |

This is architecture-adapted coverage, not a claim that a generic five-standard
service audit passed. File writes and subprocesses have their real side effects
listed. Test fixtures use only temporary synthetic data and mocked optional tools.
