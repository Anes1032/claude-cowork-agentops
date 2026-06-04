# Guided setup — paste this whole file into Cowork chat

You are setting up **claude-cowork-agentops** for the user, interactively, from
Cowork chat. Follow these steps. Ask questions with the AskUserQuestion tool; do
not assume answers.

## Prerequisites (confirm, help if missing)
- claude-mem is installed and running (`~/.claude-mem/claude-mem.db` exists).
- This repo is cloned inside the user's **projects root** (the dev folder they connect to Cowork), e.g. `~/Develop/claude-cowork-agentops`. If not cloned yet, tell them the `git clone` command and where to put it.
- An Obsidian vault exists on a **local path** (not a cloud streaming path), e.g. `~/Develop/obsidian/MyVault`. Dataview (with JavaScript Queries enabled) and Obsidian Charts plugins recommended.

## Step 1 — Ask the user (AskUserQuestion)
Collect:
1. **Output language** for reports & knowledge notes (e.g. English / Japanese / other). Script-generated notes stay English.
2. **Machine name** for this PC (used in filenames; must differ per machine). Suggest a default from the hostname.
3. **UTC offset hours** for this PC's local timezone (e.g. 9 for JST, -8 for US Pacific).
4. **Which optional tasks** to enable (multi-select): health check (2h), weekly hotspot, monthly consolidation. (Daily housekeeping is always enabled.)
5. **Slack alerts?** If yes and they enable health check: ask for/confirm a channel (offer to create `#claude-mem-alerts` via the Slack connector if connected) and capture its channel_id.

## Step 2 — Connect folders (if not already)
Ensure Cowork has access to: `~/.claude-mem` and the projects root (which contains the clone, the user's projects, and the vault). Request access if needed.

## Step 3 — Write machine config
Create `~/.claude-mem/machine.json` with the chosen values:
```json
{"machine":"<name>","utc_offset_hours":<offset>}
```

## Step 4 — Seed the vault (optional but recommended)
Copy the dashboard templates into the vault so Dataview/Charts views work:
`cp -r <workdir>/vault-templates/. "<VAULT>/"` (do not overwrite existing files; skip any that exist).
`<workdir>` is the cloned repo dir; find the vault via `find /sessions/*/mnt -maxdepth 4 -name .obsidian -type d`.

## Step 5 — Verify scripts
Run `cd <workdir> && python3 memory_digest.py --status`. If it prints the observation total, the DB is discovered correctly.

## Step 6 — Register scheduled tasks
Open `scheduled-tasks.md`. For each task the user enabled, register a Cowork scheduled
task with the given taskId and cron, using the prompt block, AFTER substituting:
- `{{OUTPUT_LANGUAGE}}` -> the chosen language.
- `{{SLACK_CHANNEL_ID}}` -> the captured channel_id (health check only; if no Slack, remove the Slack bullet from that prompt).

Always register Task 1 (`claude-mem-housekeeping`, `0 0 * * *`). Register the optional tasks the user selected. For the monthly consolidation task, remind them to enable it on ONE machine only.

## Step 7 — Pre-approve tools
Tell the user to Run now each task once to approve Write/Edit (and Slack for the
health check). For Slack, the first WARN/ALERT (or a one-time forced test) is what
captures the approval — offer to do a temporary test send if they want it pre-approved now.

## Step 8 — Summary
Report what you configured: machine.json contents, which tasks were registered (taskId + cron), vault path, output language, and any follow-ups (e.g. set up Obsidian Sync for multi-device, install Dataview/Charts).
