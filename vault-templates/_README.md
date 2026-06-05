---
type: readme
tags: [claude-cowork-agentops]
---
# Claude long-term memory vault

Populated daily by [claude-cowork-agentops](https://github.com/) from claude-mem.

## Folders
- `reports/YYYY-MM/DD/<machine>.md` — daily work log (+ CLAUDE.md / skill / global proposal history)
- `knowledge/<slug>.md` — reusable knowledge (atomic notes; shared across machines). Index: [[knowledge/_index]]
- `monitoring/YYYY-MM/DD/<machine>.md` — claude-mem metrics. Dashboard: [[monitoring/_dashboard]]
- `monitoring/_alerts.md` — health-check alerts (written on WARN/ALERT)
- `adoption/YYYY-MM/DD/<machine>.md` — CLAUDE.md proposal acceptance. Dashboard: [[adoption/_dashboard]]
- `hotspots/<YYYY>/<MM-DD>-<machine>.md` — weekly tech-debt hotspots

## For agents (Obsidian MCP, etc.)
If an agent reads this vault, start here, then filter by frontmatter `type` and `tags`.
- **Read-only** (script-owned, append-only history): `reports/`, `monitoring/`, `adoption/`, `hotspots/`.
- **Curated / editable**: `knowledge/` — atomic notes; query by `type: knowledge` + `tags`, follow `[[wikilinks]]`.
- Daily artifacts are namespaced per machine (`<machine>.md`); don't rewrite another machine's file.
- An optional `CLAUDE.md` at the vault root (the kit's `vault-CLAUDE.md`) gives a Claude agent explicit operating rules for this vault.

## Plugins
- **Dataview** (enable *Enable JavaScript Queries*) — tables + charts
- **Obsidian Charts** — line charts in the dashboards
