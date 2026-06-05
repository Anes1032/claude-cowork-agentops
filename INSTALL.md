# Install / Port to another machine

Scheduled tasks are stored locally in each machine's Cowork and are not auto-synced;
each machine has its own claude-mem DB. So the model is: **clone the repo, then
register the tasks on each machine.**

The easiest path is the guided setup — paste [`setup.md`](setup.md) into Cowork chat.
The manual steps are below.

## 1. Prerequisites
- [claude-mem](https://github.com/thedotmack/claude-mem) installed and running (`~/.claude-mem/claude-mem.db` exists).
- **Obsidian** with plugins **Dataview** (enable *Settings -> Dataview -> Enable JavaScript Queries*) and **Obsidian Charts**.
- Python 3 (standard library only; no pip installs).

## 2. Clone into your projects root
This tool treats its **parent directory as the "projects root"** (the target for
adoption / hotspot scans). Put it directly inside the dev folder you connect to Cowork.

```bash
cd ~/Develop                 # the dev folder you connect to Cowork
git clone https://github.com/Anes1032/claude-cowork-agentops.git claude-cowork-agentops
```

## 3. Configure machine name + timezone (per machine, not synced)
```bash
echo '{"machine":"<this-machine-name>","utc_offset_hours":9}' > ~/.claude-mem/machine.json
# e.g. {"machine":"desktop","utc_offset_hours":9}   (JST = 9; US Pacific = -8, etc.)
```
`machine` becomes the filename for reports/monitoring/adoption (prevents collisions
when multiple machines share one vault). `utc_offset_hours` defines the daily-window
boundary (the task VM runs in UTC, so this is required).
The incremental state (`~/.claude-mem/housekeeping-state.json`) is also stored locally; no need to share it.

## 4. Prepare an Obsidian vault (local path)
- Keep the vault on a **local path** (cloud streaming paths are not mounted in Cowork task VMs). e.g. `~/Develop/obsidian/MyVault`.
- Sync across devices with **Obsidian Sync** (recommended) or git.
- Seed dashboards/index: `cp -r <repo>/vault-templates/. "<vault>/"` (skips nothing; don't overwrite existing).
- **Optional — vault `CLAUDE.md`**: if an agent will read/work over the vault (e.g. via an Obsidian MCP, or Claude Code), copy `vault-CLAUDE.md` to the vault root so the agent knows what each folder is and which are read-only:
  `cp <repo>/vault-CLAUDE.md "<vault>/CLAUDE.md"`. Skip if you don't want it.

## 5. Connect folders in Cowork
- `~/.claude-mem`
- your projects root (`~/Develop`, containing the clone, your projects, and the vault)

## 6. Verify
Ask Cowork to run `~/Develop/claude-cowork-agentops/memory_digest.py --status`.
If it prints the observation total, DB discovery works.

## 7. Register scheduled tasks
[`scheduled-tasks.md`](scheduled-tasks.md) contains four task prompts. Paste each
`PROMPT-START`..`PROMPT-END` block when registering, replacing `{{OUTPUT_LANGUAGE}}`
with your desired language for reports/knowledge (e.g. English, Japanese).

| taskId | cron | required/optional |
|---|---|---|
| `claude-mem-housekeeping` | `0 0 * * *` | required (daily) |
| `claude-mem-healthcheck` | `0 */2 * * *` | optional (health -> Slack) |
| `claude-mem-hotspot` | `0 9 * * 1` | optional (weekly) |
| `claude-mem-knowledge-consolidate` | `0 9 1 * *` | optional (monthly, **one machine only**) |

The prompts discover paths and the vault dynamically, so different usernames or nested folders need no edits.

## 8. Run now once to pre-approve tools
Run each task once via **Run now** to approve Write/Edit (and Slack for healthcheck).
Future automated runs then won't pause on permission prompts.
- For Slack: create a channel (e.g. `#claude-mem-alerts`), put its channel_id in the
  health-check prompt, then Run now and approve the Slack tool.

## Notes
- **Other OS**: scripts auto-discover `~/.claude-mem`; if not found, set `CLAUDE_MEM_DATA_DIR`.
- **CLAUDE.md**: in git projects it is proposed uncommitted (`git diff` -> commit = accept / checkout = discard). In non-git dirs, new files are created only (existing ones are never overwritten).
- **Multiple machines**: reports/monitoring/adoption are namespaced by machine; knowledge is shared, so run monthly consolidation on one machine only.

## Optional — backfill past dates (existing claude-mem users)
If you already had claude-mem, backfill history with `backfill.py` (you choose the period):
```bash
python3 backfill.py --list-range
python3 backfill.py --vault "<vault>" --days 14   # monitoring + adoption
```
For `reports/` and `knowledge/` (LLM-generated), use the `claude-mem-backfill` task in `scheduled-tasks.md` over a small window. Backfill never commits or moves the daily checkpoint.
