#!/usr/bin/env python3
"""
Tech-debt hotspot detection (AgentOps).

From the last N days (default 30, local timezone) of claude-mem observations,
finds files that repeatedly receive bugfixes -- i.e. unstable areas / refactor
candidates. Intended for weekly runs.

Usage:
  python3 hotspot.py --print [--window-days 30] [--min-fixes 2]
  python3 hotspot.py --vault "<vault>" [--window-days 30] [--min-fixes 2] [--date YYYY-MM-DD] [--machine NAME]
      -> writes <vault>/hotspots/<YYYY-MM>/<DD>/<machine>.md
"""
import argparse
import datetime as dt
import glob
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

HK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.dirname(HK_DIR)


def resolve_data_dir():
    env = os.environ.get("CLAUDE_MEM_DATA_DIR")
    if env and os.path.exists(os.path.join(env, "claude-mem.db")):
        return env
    cands = [os.path.expanduser("~/.claude-mem")]
    cands += sorted(glob.glob("/sessions/*/mnt/.claude-mem"))
    for c in cands:
        if os.path.exists(os.path.join(c, "claude-mem.db")):
            return c
    return cands[0]


DATA_DIR = resolve_data_dir()
DB_PATH = os.path.join(DATA_DIR, "claude-mem.db")


def _cfg():
    p = os.path.join(DATA_DIR, "machine.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return {}


def machine():
    return str(_cfg().get("machine") or "unknown")


def tz():
    try:
        off = float(_cfg().get("utc_offset_hours", 9))
    except Exception:
        off = 9.0
    return dt.timezone(dt.timedelta(hours=off))


def connect_db():
    import shutil
    import tempfile
    import atexit
    d = tempfile.mkdtemp(prefix="cmhot_")
    atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    dst = os.path.join(d, "claude-mem.db")
    shutil.copy2(DB_PATH, dst)
    for ext in ("-wal", "-shm"):
        s = DB_PATH + ext
        if os.path.exists(s):
            try:
                shutil.copy2(s, dst + ext)
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


def parse_arr(blob):
    if not blob:
        return []
    try:
        v = json.loads(blob)
        return v if isinstance(v, list) else [v]
    except Exception:
        return []


def collect(conn, date_str, window_days):
    TZ = tz()
    end = (dt.datetime.fromisoformat(date_str).replace(tzinfo=TZ) + dt.timedelta(days=1))
    start = end - dt.timedelta(days=window_days)
    lo, hi = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    rows = conn.execute(
        "SELECT project, type, title, files_modified, files_read "
        "FROM observations WHERE created_at_epoch >= ? AND created_at_epoch < ?",
        (lo, hi),
    ).fetchall()

    fix_counts = Counter()
    touch_counts = Counter()
    fix_titles = defaultdict(list)
    proj_of = {}
    for project, otype, title, fmod, fread in rows:
        files = [f for f in parse_arr(fmod) if isinstance(f, str) and f.startswith("/")]
        for f in files:
            touch_counts[f] += 1
            proj_of[f] = project
            if otype == "bugfix":
                fix_counts[f] += 1
                if title:
                    fix_titles[f].append(title)
    return fix_counts, touch_counts, fix_titles, proj_of, len(rows)


def relpath(f):
    # Relativize under projects root; otherwise (container-absolute paths) keep as-is.
    try:
        if os.path.commonpath([os.path.abspath(f), PROJECTS_ROOT]) == PROJECTS_ROOT:
            return os.path.relpath(f, PROJECTS_ROOT)
    except Exception:
        pass
    return f


def render(fix_counts, touch_counts, fix_titles, proj_of, date_str, mach, window_days, min_fixes):
    hotspots = [(f, c) for f, c in fix_counts.items() if c >= min_fixes]
    hotspots.sort(key=lambda x: (-x[1], x[0]))
    fm = [
        "---", "type: hotspot", f"date: {date_str}", f"machine: {mach}",
        f"window_days: {window_days}", f"min_fixes: {min_fixes}",
        f"hotspot_count: {len(hotspots)}",
        "tags: [hotspot, techdebt, agentops, claude-mem]", "---",
    ]
    b = [f"# Tech-debt hotspots - {date_str} @ {mach}", ""]
    b.append(f"Last {window_days} days / files with {min_fixes}+ bugfixes.")
    b.append("")
    if not hotspots:
        b.append("None (no file with repeated bugfixes).")
        b.append("")
    else:
        b.append("## Hotspots (refactor candidates)")
        b.append("| file | bugfixes | total changes | project |")
        b.append("|---|--:|--:|---|")
        for f, c in hotspots:
            b.append(f"| {relpath(f)} | {c} | {touch_counts[f]} | {proj_of.get(f,'')} |")
        b.append("")
        b.append("## Bugfix details per hotspot")
        for f, c in hotspots:
            b.append(f"### {relpath(f)} ({c})")
            for t in fix_titles[f][:8]:
                b.append(f"- {t}")
            b.append("")
    top = [(f, c) for f, c in fix_counts.most_common(10)]
    if top:
        b.append("## Reference: top bugfix-involved files")
        for f, c in top:
            b.append(f"- {relpath(f)}: {c}")
        b.append("")
    return "\n".join(fm) + "\n\n" + "\n".join(b) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--min-fixes", type=int, default=2)
    ap.add_argument("--date", default=None)
    ap.add_argument("--machine")
    ap.add_argument("--vault")
    ap.add_argument("--print", dest="do_print", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    date_str = args.date or dt.datetime.now(tz()).date().isoformat()
    conn = connect_db()
    fix_counts, touch_counts, fix_titles, proj_of, n = collect(conn, date_str, args.window_days)
    mach = args.machine or machine()
    note = render(fix_counts, touch_counts, fix_titles, proj_of, date_str, mach, args.window_days, args.min_fixes)

    if args.vault:
        ym, dd = date_str[:7], date_str[8:10]
        out_dir = os.path.join(args.vault, "hotspots", ym, dd)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{mach}.md")
        with open(out, "w") as f:
            f.write(note)
        print(f"wrote: {out}")
    if args.do_print or not args.vault:
        print(note)


if __name__ == "__main__":
    main()
