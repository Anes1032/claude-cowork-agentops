#!/usr/bin/env python3
"""
Backfill (optional, for users who already had claude-mem before installing this).

Generates the DETERMINISTIC vault artifacts for past dates:
  - monitoring/<YYYY-MM>/<DD>/<machine>.md  (one per day in the range)
  - adoption/<YYYY-MM>/<DD>/<machine>.md     (a single current-state snapshot)

reports/ and knowledge/ are NOT backfilled here: they require LLM analysis, so use
the "claude-mem-backfill" task in scheduled-tasks.md for those (it's expensive, so
pick a small window).

Because the range can be large, you choose the period. Start with --list-range to
see how far back your memory goes.

Usage:
  python3 backfill.py --list-range                         # show available date span
  python3 backfill.py --vault "<vault>" --from 2026-05-01 --to 2026-05-31
  python3 backfill.py --vault "<vault>" --days 14          # last 14 days of memory
  python3 backfill.py --vault "<vault>" --dry-run          # show what would be written
  options: --what monitoring,adoption (default) | --machine NAME
"""
import argparse
import datetime as dt
import glob
import json
import os
import subprocess
import sqlite3
import sys

HK_DIR = os.path.dirname(os.path.abspath(__file__))


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


def tz():
    p = os.path.join(DATA_DIR, "machine.json")
    off = 9.0
    if os.path.exists(p):
        try:
            off = float(json.load(open(p)).get("utc_offset_hours", 9))
        except Exception:
            pass
    return dt.timezone(dt.timedelta(hours=off))


def connect_db():
    import shutil
    import tempfile
    import atexit
    d = tempfile.mkdtemp(prefix="cmbf_")
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


def available_range(conn):
    TZ = tz()
    row = conn.execute(
        "SELECT MIN(created_at_epoch), MAX(created_at_epoch) FROM observations"
    ).fetchone()
    if not row or not row[0]:
        return None, None
    lo = dt.datetime.fromtimestamp(row[0] / 1000, TZ).date()
    hi = dt.datetime.fromtimestamp(row[1] / 1000, TZ).date()
    return lo, hi


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def run_script(name, *cargs):
    return subprocess.run([sys.executable, os.path.join(HK_DIR, name), *cargs],
                          capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault")
    ap.add_argument("--from", dest="dfrom")
    ap.add_argument("--to", dest="dto")
    ap.add_argument("--days", type=int, help="last N days (of available memory)")
    ap.add_argument("--what", default="monitoring,adoption")
    ap.add_argument("--machine")
    ap.add_argument("--list-range", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = connect_db()
    avail_lo, avail_hi = available_range(conn)
    if not avail_lo:
        print("No memory found in claude-mem.db.")
        return
    span = (avail_hi - avail_lo).days + 1
    if args.list_range:
        print(f"Available memory: {avail_lo} .. {avail_hi}  ({span} days)")
        print("Pick a window with --from/--to or --days, then add --vault to write.")
        return

    # Resolve requested range, clamped to available.
    if args.dfrom or args.dto:
        lo = dt.date.fromisoformat(args.dfrom) if args.dfrom else avail_lo
        hi = dt.date.fromisoformat(args.dto) if args.dto else avail_hi
    elif args.days:
        hi = avail_hi
        lo = max(avail_lo, hi - dt.timedelta(days=args.days - 1))
    else:
        lo, hi = avail_lo, avail_hi
    lo = max(lo, avail_lo)
    hi = min(hi, avail_hi)
    if lo > hi:
        print("Empty range after clamping to available memory.")
        return

    dates = list(daterange(lo, hi))
    what = {w.strip() for w in args.what.split(",") if w.strip()}
    print(f"Backfill range: {lo} .. {hi}  ({len(dates)} days) | what={sorted(what)}")
    if args.dry_run:
        print("DRY RUN — nothing written. Dates:")
        print("  " + ", ".join(d.isoformat() for d in dates))
        return
    if not args.vault:
        print("ERROR: --vault is required to write (or use --dry-run / --list-range).", file=sys.stderr)
        sys.exit(1)

    mach = ["--machine", args.machine] if args.machine else []

    written = 0
    if "monitoring" in what:
        for d in dates:
            r = run_script("monitoring_digest.py", "--vault", args.vault, "--date", d.isoformat(), *mach)
            if r.returncode == 0:
                written += 1
            else:
                print(f"  ! monitoring {d}: {r.stderr.strip()[:120]}", file=sys.stderr)
        print(f"monitoring: wrote {written} day notes")

    if "adoption" in what:
        # Adoption is a current git-state snapshot; write a single note dated at the range end.
        r = run_script("adoption_eval.py", "--vault", args.vault, "--date", hi.isoformat(), *mach)
        print(f"adoption: {'wrote 1 snapshot for ' + hi.isoformat() if r.returncode == 0 else 'failed: ' + r.stderr.strip()[:120]}")
        print("  (adoption reflects CURRENT git state, not historical; only one snapshot is meaningful)")

    print("Done. reports/knowledge backfill (LLM) is separate — see the claude-mem-backfill task.")


if __name__ == "__main__":
    main()
