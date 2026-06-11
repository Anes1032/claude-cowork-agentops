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
| 5 | `claude-mem-backfill` | (ad-hoc / run manually) |
| 6 | `claude-cowork-agentops-update` | `0 23 * * *` |

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
- **Writes to reports/knowledge MUST go through redact**: use the SINGLE fixed temp file `<workdir>/.tmp.md` (overwrite it each time — do not create multiple temp names). Steps: Write content to `<workdir>/.tmp.md`, then `python3 redact.py --scrub "<workdir>/.tmp.md" "<final vault path>"` (auto-masks secrets). Note any masking in the report. CLAUDE.md is written with Write/Edit to host absolute paths.
- **Deletion policy**: never delete CLAUDE.md / data / vault files. The ONLY exception is cleaning up your own temp file (step 9: `rm -f "<workdir>/.tmp"*.md`).

## Steps
1. Prepare the variables above.
2. `cd <workdir> && python3 memory_digest.py --status`. If "unprocessed" is 0, skip CLAUDE.md/knowledge/report/adoption (steps 7 monitoring and 8 healthcheck still run). Otherwise `python3 memory_digest.py --digest` and note the trailing `<!-- MAX_EPOCH=... -->`.
3. Analyze (the `concepts` tags are noise; judge from observation content). Split into:
   (a) CLAUDE.md auto-apply (English, do NOT commit). **Place by level:**
       - **Root CLAUDE.md = high-level only**: project overview, conventions/rules, project settings, environment/setup, architecture, and a summary of the main flows.
       - **Push detail down to a subdirectory CLAUDE.md**: module implementation details, file-level specifics, sub-system config, and localized gotchas belong in the CLAUDE.md of the most relevant directory (package/module boundary — a dir with package.json/pyproject.toml/Cargo.toml etc. — or where files_modified concentrate). Do NOT put low-level detail in the root.
       - When updating, if a project's root CLAUDE.md has accumulated low-level detail, relocate it to the appropriate subdir CLAUDE.md and keep the root high-level (leave a one-line pointer like "see `<subdir>/CLAUDE.md`" if helpful).
       - Write new / Edit existing. In a git repo, if the CLAUDE.md has user uncommitted changes (`git -C <repo> --no-optional-locks status --porcelain` — `--no-optional-locks` so we never create a `.git/index.lock` in the user's repo), do NOT overwrite — mark "needs manual review". Non-git dirs: create new only.
       - **Always append a provenance marker line `<!-- maintained-by: claude-mem-housekeeping -->`.** Touch nothing but CLAUDE.md; never commit.
   (b) skill — place by scope:
       - **Project-specific reusable workflow (scoped to ONE project)** -> auto-apply to that project's `<project>/.claude/skills/<slug>/SKILL.md` (English, do NOT commit). frontmatter (`name`/`description`), append the provenance marker `<!-- maintained-by: claude-mem-housekeeping -->`. Same git rules as CLAUDE.md: if it has user uncommitted changes, mark "needs manual review"; non-git dirs create new only. Create `.claude/skills/<slug>/` if missing.
       - **Cross-project reusable skill (2+ projects)** -> `~/.claude/skills/` is not writable from Cowork, so propose only (SKILL.md skeleton in the report).
   (c) global CLAUDE.md candidates: conventions truly common to 2+ projects (English) — proposal only.
4. **Report ({{OUTPUT_LANGUAGE}}, work-log focused)**: write to a temp file with Write, then `redact.py --scrub` into `"$VAULT/reports/$YM/$DD/$MACHINE.md"`. Include, in order: frontmatter (`type: report`/`date: $TARGET`/`machine`/`tags`/`projects`) -> `## Summary` -> `## What was done` (per project, what was done on TARGET — the main point) -> `## CLAUDE.md applied (history)` (table: path/kind/git/summary; "none" if empty) -> `## skill proposals (history)` (with SKILL.md skeleton; "none" if empty) -> `## global CLAUDE.md proposals` ("none" if empty) -> `## Obsidian outputs` -> `## Next steps / pending`. If redact masked anything, note it at the top.
5. **knowledge/**: extract reusable knowledge as atomic notes (1 idea = 1 file). Write each to a temp file, `redact.py --scrub` into `"$VAULT/knowledge/<slug>.md"`. frontmatter (`type: knowledge`/`project`/`tags`/`created: $TARGET`/`source: claude-mem`), body in {{OUTPUT_LANGUAGE}}, link with `[[wikilink]]`. Dedupe against `ls "$VAULT/knowledge"`.
6. **Adoption**: `python3 adoption_eval.py --vault "$VAULT" --date "$TARGET"`.
7. **Monitoring (always)**: `python3 monitoring_digest.py --vault "$VAULT" --date "$TARGET"`. If no VAULT, use `--print`.
8. **Health check**: `python3 health_check.py`; on WARN/ALERT warn in the final report (usually fixed by restarting the claude-mem worker).
9. Cleanup + state: `rm -f "<workdir>/.tmp"*.md` to remove the temp file. Then, if you have MAX_EPOCH, `python3 memory_digest.py --commit <MAX_EPOCH>`.
10. Final report (brief): report path / CLAUDE.md count + needs-review / skill+global counts / adoption / knowledge new n / monitoring date / health result. Do not dump full bodies.

Rules: never commit; never delete CLAUDE.md/data/vault (only your own temp file); touch nothing but CLAUDE.md; ~/.claude is not writable; reports/knowledge go through redact via the single fixed temp file, removed at the end; CLAUDE.md carries the provenance marker; CLAUDE.md/skill bodies in English; target is the previous day TARGET.
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
4. All writes to knowledge MUST go through `redact.py --scrub` (single fixed temp file `<workdir>/.tmp.md`, overwrite each time -> scrub -> vault), and `rm -f "<workdir>/.tmp"*.md` at the end.
5. Record a consolidation report at `knowledge/_consolidation-<YYYY-MM>.md` (what was merged/updated/redirected).
6. Final report: merged n / updated n / redirected n.
Do not delete files (redirect instead). Do not touch CLAUDE.md/projects. ~/.claude is not writable.
===PROMPT-END===

---

## Task 5 (optional, one-time): claude-mem-backfill — run manually, not on a cron
For users who already had claude-mem before installing this kit. Backfills past dates.
Register it as an **ad-hoc** task (no schedule) and trigger via Run now, or just paste
this prompt into chat once.

===PROMPT-START===
You are doing a one-time **backfill** of past claude-mem memory into the vault.
This can be large, so let the user pick the period.

1. Work dir: `ls -d /sessions/*/mnt/*/claude-cowork-agentops`. If missing, report and stop.
2. Obsidian vault: `VAULT="$(dirname "$(find /sessions/*/mnt -maxdepth 4 -name .obsidian -type d 2>/dev/null | head -1)")"`. If empty, report and stop.
3. Show the available span: `cd <workdir> && python3 backfill.py --list-range`.
4. Ask the user (AskUserQuestion):
   - **Date window** to backfill (suggest the full available span or e.g. "last 14 days"). Capture as --from/--to or --days.
   - **Also backfill reports & knowledge?** (LLM-generated, one analysis per day — can be slow/costly). Default NO. If yes, recommend a SMALL window (e.g. <= 7 days).
5. **Deterministic backfill (monitoring + adoption)** — cheap, do this first:
   `python3 backfill.py --vault "$VAULT" --from <FROM> --to <TO>`  (or `--days <N>`).
   This writes one monitoring note per day plus a single current adoption snapshot.
6. **(Optional) reports + knowledge backfill** — only if the user opted in, and only over the small window:
   For each date D in the chosen small window:
   - `python3 memory_digest.py --date D` to get that day's digest (this does NOT touch state).
   - If the day has memory, write a **report** ({{OUTPUT_LANGUAGE}}) to `"$VAULT/reports/<YM>/<DD>/<MACHINE>.md"` and extract **knowledge** atomic notes to `"$VAULT/knowledge/<slug>.md"`, exactly like the daily housekeeping task (same sections, dedupe knowledge, write via `redact.py --scrub` through a temp file). Use D as the date in frontmatter. Skip empty days.
   - `MACHINE` from `~/.claude-mem/machine.json`.
7. Do NOT run `memory_digest.py --commit` here (backfill must not move the incremental checkpoint used by the daily task).
8. Final report: how many monitoring days written, adoption snapshot date, and (if done) how many report/knowledge days written.

Notes: adoption reflects CURRENT git state (only one snapshot is meaningful, not per past day). Backfill never deletes or commits. reports/knowledge are LLM-generated, so keep the window small.
===PROMPT-END===

---

## Task 6 (optional): claude-cowork-agentops-update (cron `0 23 * * *`)
Keeps the batch (scripts) up to date by pulling the repo. Best on machines that
*consume* the repo (clean clones). On the machine where you author changes, a dirty
working tree will safely block the pull (it never discards local work).

Assumes a **public** repo (anonymous HTTPS pull, no credentials). For a private repo
you'd need a token, which the sandbox does not have.

===PROMPT-START===
Update the claude-cowork-agentops repo (refresh the batch scripts).

1. Find the repo: `REPO=$(ls -d /sessions/*/mnt/*/claude-cowork-agentops 2>/dev/null | head -1)`. If none, report "repo not connected" and stop.
2. `BEFORE=$(git -C "$REPO" rev-parse HEAD)`.
3. **Fast-forward pull over anonymous HTTPS** (rewrite an SSH origin to HTTPS so the sandbox can fetch a public repo without credentials):
   `git -C "$REPO" -c url."https://github.com/".insteadOf="git@github.com:" pull --ff-only --no-edit 2>&1`  (capture output).
4. `AFTER=$(git -C "$REPO" rev-parse HEAD)`.
5. Branch on the result:
   - **Updated (BEFORE != AFTER)**: get the changelog `git -C "$REPO" log --oneline --no-decorate "$BEFORE..$AFTER"`, the changed files `git -C "$REPO" diff --name-only "$BEFORE" "$AFTER"`, and run `cd "$REPO" && python3 -m py_compile *.py`. **Notify Slack** (`slack_send_message` to `channel_id="{{SLACK_CHANNEL_ID}}"`): a header that the repo updated, the commit count + short changelog, and the compile result. **If `scheduled-tasks.md` or `setup.md` is among the changed files, always add a warning**: scripts are updated but the prompt text of already-registered scheduled tasks is NOT auto-updated — re-register the affected tasks from `scheduled-tasks.md`. (Scheduled tasks can update scripts via pull, but not their own registered prompt.) Also report the same in the final message.
   - **Already up to date**: report it in one line. No Slack.
   - **Pull failed** (non-fast-forward / dirty working tree / auth required): **do not force** (never `reset --hard`, `clean -f`, `stash drop`, or discard local changes). Notify Slack with a failure note (auto-update blocked, manual pull may be needed) + the error summary, and report it.
6. **Never** commit / push / reset --hard / delete files. Read-only fast-forward pull only.
7. Slack is optional: if you didn't configure a channel, skip the Slack steps and just report in the final message.

Note: a private repo will fail anonymous HTTPS fetch (needs a token). This task only refreshes the scripts; it does not change the prompt text of already-registered scheduled tasks.
===PROMPT-END===
