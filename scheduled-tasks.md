# Scheduled task prompts

Register each block below as a Cowork scheduled task. Before registering, replace
the placeholders:
- `{{OUTPUT_LANGUAGE}}` — the language for LLM-authored reports & knowledge notes (e.g. `English`, `Japanese`). Script-generated notes are always English.
- `{{SLACK_CHANNEL_ID}}` — only for the health-check task if you want Slack alerts (the channel_id of e.g. `#claude-mem-alerts`). Omit the Slack step if not using Slack.

Paths, the projects root, and the Obsidian vault are discovered dynamically, so
usernames / nested folders need no edits.

| # | taskId | cron |
|---|---|---|
| 1 | `claude-mem-housekeeping` | `0 0 * * *` |
| 2 | `claude-mem-healthcheck` | `0 */2 * * *` |
| 3 | `claude-mem-hotspot` | `0 9 * * 1` |
| 4 | `claude-mem-knowledge-consolidate` | `0 9 1 * *` |

---

## Task 1: claude-mem-housekeeping (cron `0 0 * * *`)
===PROMPT-START===
You run the daily claude-mem memory housekeeping. Run at 00:00 and target the
**completed previous day (TARGET)**. Outputs: (X) project CLAUDE.md / skill proposals,
(Y) the Obsidian vault (long-term memory).

Memory hierarchy: CLAUDE.md = conventions/structure (project), skill = reusable logic
(project), claude-mem = short/mid-term (local), Obsidian = long-term.
**Language rule: CLAUDE.md and skill bodies are ENGLISH. reports/knowledge and the
housekeeping narrative are written in {{OUTPUT_LANGUAGE}}.**

## Paths
- Work dir: `ls -d /sessions/*/mnt/*/claude-cowork-agentops` (memory_digest.py / monitoring_digest.py / adoption_eval.py / redact.py / health_check.py). If missing, report "folder not connected" in one line and stop. Do NOT put reports/state here (state auto-saves to ~/.claude-mem/housekeeping-state.json).
- Scripts auto-discover `~/.claude-mem` and read the DB from a copy (no live-DB interference).
- Machine/TZ: `MACHINE=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude-mem/machine.json'))).get('machine','unknown'))" 2>/dev/null || echo unknown)` / `OFF=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude-mem/machine.json'))).get('utc_offset_hours',9))" 2>/dev/null || echo 9)`
- TARGET (completed previous day, local TZ): `TARGET=$(python3 -c "import datetime;print((datetime.datetime.utcnow()+datetime.timedelta(hours=float('$OFF'))).date()-datetime.timedelta(days=1))")` / `YM=${TARGET:0:7}` / `DD=${TARGET:8:2}`
- Projects: under the connected projects root (may be nested; resolve a project by `find /sessions/*/mnt/*/ -maxdepth 4 -type d -name "<project>"`).
- Obsidian vault: `VAULT="$(dirname "$(find /sessions/*/mnt -maxdepth 4 -name .obsidian -type d 2>/dev/null | head -1)")"`. If empty, skip Obsidian outputs.
- **Writes to reports/knowledge MUST go through redact**: write content with the Write tool to `<workdir>/.tmp.md`, then `python3 redact.py --scrub "<workdir>/.tmp.md" "<final vault path>"` (auto-masks secrets). Note any masking in the report. CLAUDE.md is written with Write/Edit to host absolute paths. Do NOT delete files via bash.

## Steps
1. Prepare the variables above.
2. `cd <workdir> && python3 memory_digest.py --status`. If "unprocessed" is 0, skip CLAUDE.md/knowledge/report/adoption (steps 7 monitoring and 8 healthcheck still run). Otherwise `python3 memory_digest.py --digest` and note the trailing `<!-- MAX_EPOCH=... -->`.
3. Analyze (the `concepts` tags are noise; judge from observation content). Split into:
   (a) CLAUDE.md auto-apply (English, do NOT commit): pick the most relevant directory, Write new / Edit existing. In a git repo, if the CLAUDE.md has user uncommitted changes (`git -C <repo> status --porcelain`), do NOT overwrite — mark "needs manual review". Non-git dirs: create new only. **Always append a provenance marker line `<!-- maintained-by: claude-mem-housekeeping -->`.** Touch nothing but CLAUDE.md; never commit.
   (b) skill candidates: reusable workflows recurring across 2+ projects, as a SKILL.md skeleton (English) — proposal only.
   (c) global CLAUDE.md candidates: conventions truly common to 2+ projects (English) — proposal only.
4. **Report ({{OUTPUT_LANGUAGE}}, work-log focused)**: write to a temp file with Write, then `redact.py --scrub` into `"$VAULT/reports/$YM/$DD/$MACHINE.md"`. Include, in order: frontmatter (`type: report`/`date: $TARGET`/`machine`/`tags`/`projects`) -> `## Summary` -> `## What was done` (per project, what was done on TARGET — the main point) -> `## CLAUDE.md applied (history)` (table: path/kind/git/summary; "none" if empty) -> `## skill proposals (history)` (with SKILL.md skeleton; "none" if empty) -> `## global CLAUDE.md proposals` ("none" if empty) -> `## Obsidian outputs` -> `## Next steps / pending`. If redact masked anything, note it at the top.
5. **knowledge/**: extract reusable knowledge as atomic notes (1 idea = 1 file). Write each to a temp file, `redact.py --scrub` into `"$VAULT/knowledge/<slug>.md"`. frontmatter (`type: knowledge`/`project`/`tags`/`created: $TARGET`/`source: claude-mem`), body in {{OUTPUT_LANGUAGE}}, link with `[[wikilink]]`. Dedupe against `ls "$VAULT/knowledge"`.
6. **Adoption**: `python3 adoption_eval.py --vault "$VAULT" --date "$TARGET"`.
7. **Monitoring (always)**: `python3 monitoring_digest.py --vault "$VAULT" --date "$TARGET"`. If no VAULT, use `--print`.
8. **Health check**: `python3 health_check.py`; on WARN/ALERT warn in the final report (usually fixed by restarting the claude-mem worker).
9. State: if you have MAX_EPOCH, `python3 memory_digest.py --commit <MAX_EPOCH>`.
10. Final report (brief): report path / CLAUDE.md count + needs-review / skill+global counts / adoption / knowledge new n / monitoring date / health result. Do not dump full bodies.

Rules: never commit, never delete, touch nothing but CLAUDE.md, ~/.claude is not writable, reports/knowledge go through redact, CLAUDE.md carries the provenance marker, CLAUDE.md/skill bodies in English, target is the previous day TARGET.
===PROMPT-END===

---

## Task 2: claude-mem-healthcheck (cron `0 */2 * * *`)
===PROMPT-START===
Check claude-mem health (AgentOps active alerting). Alert only on anomalies.

1. Work dir: `ls -d /sessions/*/mnt/*/claude-cowork-agentops`. If missing, report "folder not connected" in one line and stop.
2. `cd <workdir> && python3 health_check.py --json`. Read `status` (OK/WARN/ALERT) and `problems`.
3. If status is OK: do not notify; final report is one line (e.g. `OK (N errors recently)`). No Slack, no Obsidian write.
4. If status is WARN or ALERT only:
   - **Slack** (if using Slack): call the Slack connector's `slack_send_message` to `channel_id="{{SLACK_CHANNEL_ID}}"`. Body: a header line with the status, the detection time, each problem message, and the recommended action (if disk I/O / Bun missing / -shm missing, say "restart the claude-mem worker").
   - **Obsidian**: `VAULT="$(dirname "$(find /sessions/*/mnt -maxdepth 4 -name .obsidian -type d 2>/dev/null | head -1)")"`; if present, prepend the same content to `"$VAULT/monitoring/_alerts.md"` (keep existing content).
   - State the status and action in the final report.
5. Inspection only. Do not modify the DB/worker/logs. Separate from the housekeeping task. Never notify on OK.
===PROMPT-END===

---

## Task 3: claude-mem-hotspot (cron `0 9 * * 1`)
===PROMPT-START===
Detect tech-debt hotspots (weekly, last 30 days). Files repeatedly bugfixed = refactor candidates.

1. Work dir: `ls -d /sessions/*/mnt/*/claude-cowork-agentops`. If missing, report in one line and stop.
2. Obsidian vault: `VAULT="$(dirname "$(find /sessions/*/mnt -maxdepth 4 -name .obsidian -type d 2>/dev/null | head -1)")"`.
3. Run: `cd <workdir> && python3 hotspot.py --vault "$VAULT" --window-days 30 --min-fixes 2` (writes hotspots/<YYYY-MM>/<DD>/<machine>.md; reads DB from a copy).
4. Final report: the written path and hotspot count ("none" if zero).
(optional) If a file newly crosses the threshold, you may send a summary to your Slack alerts channel.
Do not modify the DB/worker/CLAUDE.md (detection only).
===PROMPT-END===

---

## Task 4: claude-mem-knowledge-consolidate (cron `0 9 1 * *`)
===PROMPT-START===
Consolidate the Obsidian knowledge folder monthly (merge duplicates, update, prune).
Narrative in {{OUTPUT_LANGUAGE}}. **Run on ONE machine only.**

1. Find the work dir and the Obsidian vault (as above).
2. Audit: `cd <workdir> && python3 knowledge_audit.py --vault "$VAULT"` to get duplicate candidates / stale notes / tag distribution.
3. For each duplicate candidate, read the knowledge notes and decide:
   - Clear duplicate -> merge into one note, link related with `[[wikilink]]`. **Do not delete files** (sandbox constraint): fold the redundant note's content into the canonical one and replace the old note's body with a one-line redirect `-> merged into [[canonical]]`.
   - Stale / drifted -> reconcile against the latest claude-mem memory (use `memory_digest.py --digest --all` if needed) and update.
   - Contradiction -> verify the correct one against the latest observations and fix.
4. All writes to knowledge MUST go through `redact.py --scrub` (temp file -> scrub -> vault).
5. Record a consolidation report at `knowledge/_consolidation-<YYYY-MM>.md` (what was merged/updated/redirected).
6. Final report: merged n / updated n / redirected n.
Do not delete files (redirect instead). Do not touch CLAUDE.md/projects. ~/.claude is not writable.
===PROMPT-END===
