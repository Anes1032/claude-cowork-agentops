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
- `hotspots/YYYY-MM/DD/<machine>.md` — weekly tech-debt hotspots

## Plugins
- **Dataview** (enable *Enable JavaScript Queries*) — tables + charts
- **Obsidian Charts** — line charts in the dashboards
