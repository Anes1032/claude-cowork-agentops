# Vault guide for agents (claude-cowork-agentops)

This Obsidian vault is the long-term memory produced daily from claude-mem by
claude-cowork-agentops. If you (an agent — e.g. via an Obsidian MCP) read or work
over this vault, follow these conventions.

## What each folder is
- `reports/YYYY-MM/DD/<machine>.md` — daily work logs. Append-only history; read-only.
- `monitoring/YYYY-MM/DD/<machine>.md` — claude-mem metrics. Script-owned; read-only.
- `adoption/YYYY-MM/DD/<machine>.md` — CLAUDE.md proposal acceptance. Script-owned; read-only.
- `hotspots/<YYYY>/<MM-DD>-<machine>.md` — weekly tech-debt hotspots. Script-owned; read-only.
- `knowledge/<slug>.md` — curated, reusable knowledge as atomic notes. Editable / refinable.
- `*/_dashboard.md`, `knowledge/_index.md` — Dataview views; keep the queries intact.

## How to find things
- Filter by frontmatter `type:` (`report` / `knowledge` / `monitoring` / `adoption` / `hotspot`).
- knowledge notes carry `project` and `tags` — query by those; relations use `[[wikilinks]]`.
- Daily artifacts are namespaced per machine (`<machine>.md`).

## Rules
- Treat reports / monitoring / adoption / hotspots as an append-only audit trail: read for context, do not edit or delete them.
- Only `knowledge/` is meant to be curated by hand (and by the monthly consolidation task).
- Do not rewrite a `<machine>.md` that belongs to a different machine.
- Match the existing note language when adding content.
