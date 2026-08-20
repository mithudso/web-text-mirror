# MCP

**Not applicable.** This repository configures no MCP servers and exposes none.

The tool is consumed either directly as a CLI, or as a Claude *skill* (`SKILL.md` —
a skill, not an MCP server). If an MCP wrapper is ever wanted (e.g. exposing
`mirror_site(url)` as a tool), start from the local HTTP API surface in
`scripts/text_mirror.py` (`/save`, `/crawl`, `/stop`, `/list`) — it is already the
programmatic contract. Until then, there is nothing to document here.
