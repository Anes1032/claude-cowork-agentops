#!/usr/bin/env python3
"""
claude-mem health check (AgentOps: active alerting).

Inspects claude-mem worker / errors / WAL health and judges the state.
- Detects memory-write stoppage (disk I/O errors) and worker spawn failures in a recent window
- Detects WAL-mode anomalies (-shm missing / frozen WAL)
- Reports recency of memory ingestion

Exit code: 0 = OK / 1 = WARN / 2 = ALERT
Usage:
  python3 health_check.py [--window-min 60]
  python3 health_check.py --json
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys
import time


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
LOG_DIR = os.path.join(DATA_DIR, "logs")


def offset_hours():
    p = os.path.join(DATA_DIR, "machine.json")
    if os.path.exists(p):
        try:
            return float(json.load(open(p)).get("utc_offset_hours", 9))
        except Exception:
            pass
    return 9.0


def connect_copy():
    import shutil
    import tempfile
    import atexit
    d = tempfile.mkdtemp(prefix="cmhc_")
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


def recent_log_errors(window_min):
    """Aggregate [ERROR] lines from the last window_min minutes (local time), across all logs."""
    off = offset_hours()
    now_local = dt.datetime.utcnow() + dt.timedelta(hours=off)
    start = now_local - dt.timedelta(minutes=window_min)
    cats = {}
    disk_io = 0
    worker_fail = 0
    samples = []
    pat = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    for lf in sorted(glob.glob(os.path.join(LOG_DIR, "claude-mem-*.log"))):
        try:
            with open(lf, errors="ignore") as f:
                for ln in f:
                    m = pat.match(ln)
                    if not m or "[ERROR]" not in ln:
                        continue
                    try:
                        ts = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
                    if ts < start:
                        continue
                    tag = re.search(r"\[ERROR\]\s*\[([A-Z_ ]+?)\]", ln)
                    cat = tag.group(1).strip() if tag else "OTHER"
                    if cat == "CONSOLE" and "protocol protection" in ln:
                        continue
                    cats[cat] = cats.get(cat, 0) + 1
                    if "disk I/O error" in ln:
                        disk_io += 1
                    if "Failed to spawn worker" in ln or "Bun runtime not found" in ln:
                        worker_fail += 1
                    if len(samples) < 3:
                        samples.append(re.sub(r"^\[[0-9:.\- ]+\]\s*", "", ln).strip()[:140])
        except Exception:
            continue
    return dict(categories=cats, total=sum(cats.values()),
                disk_io=disk_io, worker_fail=worker_fail, samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-min", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    problems = []   # (severity, msg)  severity: ALERT/WARN
    info = {}

    if not os.path.exists(DB_PATH):
        print("ALERT: claude-mem.db not found")
        sys.exit(2)

    shm = os.path.exists(DB_PATH + "-shm")
    wal = DB_PATH + "-wal"
    info["shm_present"] = shm
    if not shm and os.path.exists(wal):
        problems.append(("ALERT", "-shm missing (WAL-mode anomaly; worker may need a restart)"))
    if os.path.exists(wal):
        wal_age_min = (time.time() - os.path.getmtime(wal)) / 60
        db_age_min = (time.time() - os.path.getmtime(DB_PATH)) / 60
        info["wal_age_min"] = round(wal_age_min, 1)
        info["db_age_min"] = round(db_age_min, 1)
        if wal_age_min - db_age_min > 180 and db_age_min < 120:
            problems.append(("WARN", f"WAL looks frozen (WAL {int(wal_age_min)} min / DB {int(db_age_min)} min)"))

    err = recent_log_errors(args.window_min)
    info["recent_errors"] = err["total"]
    info["recent_error_categories"] = err["categories"]
    if err["worker_fail"] > 0:
        problems.append(("ALERT", f"{err['worker_fail']} worker spawn failures in last {args.window_min} min (Bun missing / spawn failed)"))
    if err["disk_io"] > 0:
        problems.append(("ALERT", f"{err['disk_io']} disk I/O errors in last {args.window_min} min (memory writes may be failing)"))
    if err["total"] >= 20 and err["disk_io"] == 0 and err["worker_fail"] == 0:
        problems.append(("WARN", f"high error rate in last {args.window_min} min ({err['total']})"))

    try:
        c = connect_copy()
        last_obs = c.execute("SELECT MAX(created_at_epoch) FROM observations").fetchone()[0] or 0
        last_sess = c.execute("SELECT MAX(started_at_epoch) FROM sdk_sessions").fetchone()[0] or 0
        last = max(last_obs, last_sess)
        info["minutes_since_last_memory"] = round((time.time()*1000 - last) / 60000, 1) if last else None
    except Exception as e:
        problems.append(("WARN", f"DB read failed: {e}"))

    sev = "OK"
    if any(s == "ALERT" for s, _ in problems):
        sev = "ALERT"
    elif any(s == "WARN" for s, _ in problems):
        sev = "WARN"
    code = {"OK": 0, "WARN": 1, "ALERT": 2}[sev]

    result = dict(status=sev, problems=[{"severity": s, "message": m} for s, m in problems],
                  window_min=args.window_min, **info)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(sev)
        for s, m in problems:
            print(f"  - [{s}] {m}")
        if sev == "OK":
            print(f"  {err['total']} errors in last {args.window_min} min / -shm {'present' if shm else 'MISSING'}")
        if err["samples"] and sev != "OK":
            print("  samples:")
            for s in err["samples"]:
                print(f"    {s}")
    sys.exit(code)


if __name__ == "__main__":
    main()
