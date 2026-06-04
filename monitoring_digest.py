#!/usr/bin/env python3
"""
claude-mem monitoring digest.

Extracts four metric groups from claude-mem.db + logs/ and writes a daily Obsidian
monitoring note (with YAML frontmatter for Dataview):
  1. Activity      - daily prompts / sessions / new observations & summaries (per project)
  2. Token usage   - discovery_tokens for the day and cumulative (per project)
  3. Memory growth - observation type breakdown, totals, stale-project detection
  4. Health & hotspots - error counts / failed sessions / most-touched files

The daily window is bucketed by LOCAL timezone (machine.json utc_offset_hours,
default +9). Errors are aggregated across ALL log files by their real timestamp
(log file names are rotation-based and do not match entry dates).

Usage:
  python3 monitoring_digest.py --print [--date YYYY-MM-DD]
  python3 monitoring_digest.py --vault "<vault>" [--date YYYY-MM-DD] [--machine NAME]
      -> writes <vault>/monitoring/<YYYY-MM>/<DD>/<machine>.md
Default --date is "today" in the local timezone.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

STALE_DAYS = 7


def resolve_data_dir():
    env = os.environ.get("CLAUDE_MEM_DATA_DIR")
    if env and os.path.exists(os.path.join(env, "claude-mem.db")):
        return env
    candidates = [os.path.expanduser("~/.claude-mem")]
    candidates += sorted(glob.glob("/sessions/*/mnt/.claude-mem"))
    for c in candidates:
        if os.path.exists(os.path.join(c, "claude-mem.db")):
            return c
    return candidates[0]


DATA_DIR = resolve_data_dir()
DB_PATH = os.path.join(DATA_DIR, "claude-mem.db")
LOG_DIR = os.path.join(DATA_DIR, "logs")


def connect_db():
    """Read from a COPY of the live DB (never touch the live WAL/-shm)."""
    import shutil
    import tempfile
    import atexit
    tmpdir = tempfile.mkdtemp(prefix="cmread_")
    atexit.register(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
    dst = os.path.join(tmpdir, "claude-mem.db")
    shutil.copy2(DB_PATH, dst)
    for ext in ("-wal", "-shm"):
        src = DB_PATH + ext
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst + ext)
            except Exception:
                pass
    try:
        return sqlite3.connect(dst)
    except Exception:
        for ext in ("-wal", "-shm"):
            p = dst + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        return sqlite3.connect(dst)


def _machine_cfg():
    p = os.path.join(DATA_DIR, "machine.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def resolve_machine():
    return str(_machine_cfg().get("machine") or "unknown")


def resolve_tz():
    """Local timezone as a fixed offset from machine.json utc_offset_hours
    (default +9). No tzdata dependency; fine for non-DST offsets like JST."""
    off = _machine_cfg().get("utc_offset_hours", 9)
    try:
        off = float(off)
    except Exception:
        off = 9.0
    return dt.timezone(dt.timedelta(hours=off))


TZ = resolve_tz()


def day_window_ms(date_str):
    """[00:00, next 00:00) of local date_str (YYYY-MM-DD) as epoch ms."""
    start = dt.datetime.fromisoformat(date_str).replace(tzinfo=TZ)
    end = start + dt.timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def epoch_to_local_date(ms):
    return dt.datetime.fromtimestamp(ms / 1000, TZ).date()


def parse_arr(blob):
    if not blob:
        return []
    try:
        v = json.loads(blob)
        return v if isinstance(v, list) else [v]
    except Exception:
        return []


def scan_errors(date_str):
    """Aggregate [ERROR] lines whose real timestamp is on date_str, across ALL logs."""
    errors_total = 0
    err_categories = Counter()
    err_benign = 0
    root_causes = []
    samples = []
    ROOT_HINTS = {
        "Bun runtime not found": "Bun runtime not found (root cause: worker cannot start)",
        "Failed to spawn worker daemon": "worker daemon failed to spawn",
        "Worker not available": "worker not available",
        "disk I/O error": "disk I/O error (DB writes failing)",
        "port conflict": "port conflict",
    }
    prefix = f"[{date_str}"
    for lf in sorted(glob.glob(os.path.join(LOG_DIR, "claude-mem-*.log"))):
        try:
            with open(lf, errors="ignore") as f:
                for ln in f:
                    if not ln.startswith(prefix) or "[ERROR]" not in ln:
                        continue
                    errors_total += 1
                    mtag = re.search(r"\[ERROR\]\s*\[([A-Z_ ]+?)\]", ln)
                    cat = mtag.group(1).strip() if mtag else "OTHER"
                    if cat == "CONSOLE" and "protocol protection" in ln:
                        err_benign += 1
                        continue
                    err_categories[cat] += 1
                    for key, desc in ROOT_HINTS.items():
                        if key in ln and desc not in root_causes:
                            root_causes.append(desc)
                    if len(samples) < 3:
                        msg = re.sub(r"^\[[0-9:.\- ]+\]\s*", "", ln).strip()
                        samples.append(msg[:140])
        except Exception:
            continue
    return dict(
        errors_today=errors_total,
        errors_real_today=errors_total - err_benign,
        err_benign=err_benign,
        err_categories=err_categories.most_common(),
        root_causes=root_causes,
        samples=samples,
    )


def collect(conn, date_str):
    cur = conn.cursor()
    lo, hi = day_window_ms(date_str)

    prompts_today = cur.execute(
        "SELECT COUNT(*) FROM user_prompts WHERE created_at_epoch >= ? AND created_at_epoch < ?",
        (lo, hi),
    ).fetchone()[0]
    obs_today_rows = cur.execute(
        "SELECT project, type, discovery_tokens, files_read, files_modified "
        "FROM observations WHERE created_at_epoch >= ? AND created_at_epoch < ?",
        (lo, hi),
    ).fetchall()
    summ_today = cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(discovery_tokens),0) FROM session_summaries "
        "WHERE created_at_epoch >= ? AND created_at_epoch < ?",
        (lo, hi),
    ).fetchone()
    sess_today = cur.execute(
        "SELECT project, status, started_at_epoch, completed_at_epoch FROM sdk_sessions "
        "WHERE started_at_epoch >= ? AND started_at_epoch < ?",
        (lo, hi),
    ).fetchall()

    obs_today_n = len(obs_today_rows)
    tokens_today = sum((r[2] or 0) for r in obs_today_rows)
    proj_today = Counter(r[0] for r in obs_today_rows)
    type_today = Counter(r[1] for r in obs_today_rows if r[1])
    proj_tokens_today = defaultdict(int)
    for r in obs_today_rows:
        proj_tokens_today[r[0]] += (r[2] or 0)
    files_today = Counter()
    for r in obs_today_rows:
        for f in parse_arr(r[3]) + parse_arr(r[4]):
            if isinstance(f, str):
                files_today[os.path.basename(f)] += 1

    sess_n = len(sess_today)
    sess_failed = sum(1 for r in sess_today if (r[1] or "") != "completed")
    durations = [
        (r[3] - r[2]) / 1000.0 for r in sess_today if r[2] and r[3] and r[3] >= r[2]
    ]
    sess_dur_total_min = round(sum(durations) / 60.0, 1) if durations else 0.0

    obs_total = cur.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    summ_total = cur.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
    tokens_total = cur.execute(
        "SELECT COALESCE(SUM(discovery_tokens),0) FROM observations"
    ).fetchone()[0]
    proj_tokens_cum = cur.execute(
        "SELECT project, COALESCE(SUM(discovery_tokens),0), COUNT(*) "
        "FROM observations GROUP BY project"
    ).fetchall()
    type_cum = cur.execute(
        "SELECT type, COUNT(*) FROM observations WHERE type IS NOT NULL GROUP BY type"
    ).fetchall()

    last_seen = cur.execute(
        "SELECT project, MAX(created_at_epoch) FROM observations GROUP BY project"
    ).fetchall()
    dref = dt.date.fromisoformat(date_str)
    stale = []
    for proj, last_ms in last_seen:
        if not last_ms:
            continue
        gap = (dref - epoch_to_local_date(last_ms)).days
        if gap >= STALE_DAYS:
            stale.append((proj, epoch_to_local_date(last_ms).isoformat(), gap))

    err = scan_errors(date_str)
    runner_err_lines = 0
    rerr = os.path.join(LOG_DIR, "runner-errors.log")
    if os.path.exists(rerr):
        try:
            with open(rerr, errors="ignore") as f:
                runner_err_lines = sum(1 for _ in f)
        except Exception:
            pass
    db_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 1) if os.path.exists(DB_PATH) else 0

    return dict(
        date=date_str,
        prompts_today=prompts_today,
        observations_today=obs_today_n,
        summaries_today=summ_today[0],
        tokens_today=tokens_today,
        sessions_today=sess_n,
        sessions_failed=sess_failed,
        session_minutes_today=sess_dur_total_min,
        errors_today=err["errors_today"],
        errors_real_today=err["errors_real_today"],
        runner_error_lines=runner_err_lines,
        projects_active_today=len([p for p in proj_today if p]),
        observations_total=obs_total,
        summaries_total=summ_total,
        tokens_total=tokens_total,
        db_size_mb=db_mb,
        stale_projects=len(stale),
        _proj_today=dict(proj_today),
        _proj_tokens_today=dict(proj_tokens_today),
        _type_today=dict(type_today),
        _files_today=files_today.most_common(8),
        _proj_tokens_cum=proj_tokens_cum,
        _type_cum=type_cum,
        _stale=stale,
        _err_benign=err["err_benign"],
        _err_categories=err["err_categories"],
        _root_causes=err["root_causes"],
        _err_samples=err["samples"],
    )


def render_note(m):
    fm = [
        "---",
        "type: monitoring",
        f"date: {m['date']}",
        f"machine: {m['machine']}",
        f"prompts_today: {m['prompts_today']}",
        f"observations_today: {m['observations_today']}",
        f"summaries_today: {m['summaries_today']}",
        f"tokens_today: {m['tokens_today']}",
        f"sessions_today: {m['sessions_today']}",
        f"sessions_failed: {m['sessions_failed']}",
        f"session_minutes_today: {m['session_minutes_today']}",
        f"errors_today: {m['errors_today']}",
        f"errors_real_today: {m['errors_real_today']}",
        f"projects_active_today: {m['projects_active_today']}",
        f"observations_total: {m['observations_total']}",
        f"summaries_total: {m['summaries_total']}",
        f"tokens_total: {m['tokens_total']}",
        f"db_size_mb: {m['db_size_mb']}",
        f"stale_projects: {m['stale_projects']}",
        "tags: [monitoring, claude-mem]",
        "---",
    ]
    b = [f"# Monitoring - {m['date']} @ {m['machine']}", ""]

    b.append("## 1. Activity (today)")
    b.append(f"- prompts: **{m['prompts_today']}** / sessions: **{m['sessions_today']}**"
             f" (failed {m['sessions_failed']} / active {m['session_minutes_today']} min)")
    b.append(f"- new observations: **{m['observations_today']}** / new summaries: **{m['summaries_today']}**"
             f" / active projects: **{m['projects_active_today']}**")
    if m["_proj_today"]:
        b.append("")
        b.append("| project | obs | tokens |")
        b.append("|---|--:|--:|")
        for p in sorted(m["_proj_today"], key=lambda x: -m["_proj_today"][x]):
            b.append(f"| {p} | {m['_proj_today'][p]} | {m['_proj_tokens_today'].get(p,0):,} |")
    b.append("")

    b.append("## 2. Token usage")
    b.append(f"- today discovery_tokens: **{m['tokens_today']:,}** / cumulative: **{m['tokens_total']:,}**")
    b.append("")
    b.append("| project | cumulative tokens | observations |")
    b.append("|---|--:|--:|")
    for proj, tok, cnt in sorted(m["_proj_tokens_cum"], key=lambda x: -x[1]):
        b.append(f"| {proj} | {tok:,} | {cnt} |")
    b.append("")

    b.append("## 3. Memory composition & growth")
    b.append(f"- total memory: **{m['observations_total']}** observations / **{m['summaries_total']}** summaries"
             f" / DB **{m['db_size_mb']} MB**")
    if m["_type_cum"]:
        types = ", ".join(f"{t}:{n}" for t, n in sorted(m["_type_cum"], key=lambda x: -x[1]))
        b.append(f"- observation types (cumulative): {types}")
    if m["_type_today"]:
        tt = ", ".join(f"{t}:{n}" for t, n in sorted(m["_type_today"].items(), key=lambda x: -x[1]))
        b.append(f"- types today: {tt}")
    if m["_stale"]:
        b.append(f"- WARNING stale projects (no update for {STALE_DAYS}+ days):")
        for proj, last, gap in m["_stale"]:
            b.append(f"    - {proj} (last {last} / {gap} days ago)")
    else:
        b.append(f"- stale projects ({STALE_DAYS}+ days): none")
    b.append("")

    b.append("## 4. Health & hotspots")
    b.append(f"- errors today (logs): **{m['errors_today']}**"
             f" (real {m['errors_real_today']} / benign console intercepts {m['_err_benign']})"
             f" / runner-errors.log lines: {m['runner_error_lines']}")
    b.append(f"- failed sessions: **{m['sessions_failed']}**")
    if m["_root_causes"]:
        b.append("- detected root causes:")
        for rc in m["_root_causes"]:
            b.append(f"    - {rc}")
    if m["_err_categories"]:
        b.append("- error breakdown (by category):")
        for cat, n in m["_err_categories"][:8]:
            b.append(f"    - {cat}: {n}")
    if m["_err_samples"]:
        b.append("- samples:")
        for s in m["_err_samples"]:
            b.append(f"    - `{s}`")
    if m["_files_today"]:
        b.append("- today's hotspots (most-touched files):")
        for fn, cnt in m["_files_today"]:
            b.append(f"    - {fn} ({cnt})")
    else:
        b.append("- today's hotspots: none")
    b.append("")
    return "\n".join(fm) + "\n\n" + "\n".join(b) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(TZ).date().isoformat())
    ap.add_argument("--vault", help="Obsidian vault root; writes <vault>/monitoring/<YYYY-MM>/<DD>/<machine>.md")
    ap.add_argument("--machine", help="machine name (default: ~/.claude-mem/machine.json)")
    ap.add_argument("--print", dest="do_print", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = connect_db()
    m = collect(conn, args.date)
    m["machine"] = args.machine or resolve_machine()
    note = render_note(m)

    if args.vault:
        ym, dd = args.date[:7], args.date[8:10]
        mon_dir = os.path.join(args.vault, "monitoring", ym, dd)
        os.makedirs(mon_dir, exist_ok=True)
        out = os.path.join(mon_dir, f"{m['machine']}.md")
        with open(out, "w") as f:
            f.write(note)
        print(f"wrote: {out}")
    if args.do_print or not args.vault:
        print(note)


if __name__ == "__main__":
    main()
