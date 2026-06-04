#!/usr/bin/env python3
"""
claude-mem memory housekeeping digest.

Extracts incremental memory (observations / session summaries) from claude-mem.db,
grouped by project, for the housekeeping analysis. Supports incremental processing
(only memory created after the last committed checkpoint).

Usage:
  python3 memory_digest.py --digest            digest of new memory since last commit
  python3 memory_digest.py --digest --all       digest of ALL memory (first run / full scan)
  python3 memory_digest.py --commit <epoch>     advance the processed checkpoint
  python3 memory_digest.py --status             show current state and DB overview

State is stored at ~/.claude-mem/housekeeping-state.json (local, not cloud-synced),
so it never conflicts even if this repo is synced across machines.
The claude-mem DB is read from a COPY (never touches the live WAL).
"""
import argparse
import glob
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict


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
HK_DIR = os.path.dirname(os.path.abspath(__file__))
# State lives under the claude-mem data dir (local, not cloud-synced) so it
# never conflicts even if this repo is shared across machines.
STATE_PATH = os.path.join(DATA_DIR, "housekeeping-state.json")
_LEGACY_STATE_PATH = os.path.join(HK_DIR, "state.json")


def connect_db():
    """Read from a COPY of the live DB instead of opening it in place.
    WAL mode requires shared -shm coordination among all accessors; opening the
    live DB across the VM boundary can induce 'disk I/O error' in the claude-mem
    worker. Copying first avoids any interference."""
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


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    # Migrate from the old location (repo/state.json) if present.
    if os.path.exists(_LEGACY_STATE_PATH):
        with open(_LEGACY_STATE_PATH) as f:
            st = json.load(f)
        save_state(st)
        return st
    return {"last_processed_epoch": 0, "last_run": None, "history": []}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def parse_json_array(blob):
    if not blob:
        return []
    try:
        v = json.loads(blob)
        return v if isinstance(v, list) else [v]
    except Exception:
        return []


def fetch(conn, since_epoch, include_all):
    cur = conn.cursor()
    epoch_filter = 0 if include_all else since_epoch
    obs = cur.execute(
        """
        SELECT project, type, title, subtitle, facts, narrative, concepts,
               files_read, files_modified, created_at, created_at_epoch
        FROM observations
        WHERE created_at_epoch > ?
        ORDER BY project, created_at_epoch
        """,
        (epoch_filter,),
    ).fetchall()
    summaries = cur.execute(
        """
        SELECT project, request, investigated, learned, completed, next_steps,
               notes, created_at, created_at_epoch
        FROM session_summaries
        WHERE created_at_epoch > ?
        ORDER BY project, created_at_epoch
        """,
        (epoch_filter,),
    ).fetchall()
    # MAX_EPOCH considers BOTH observations and summaries (summaries can have a
    # higher epoch; using observations only would re-process or drop them).
    mo = cur.execute("SELECT MAX(created_at_epoch) FROM observations").fetchone()[0] or 0
    ms = cur.execute("SELECT MAX(created_at_epoch) FROM session_summaries").fetchone()[0] or 0
    max_epoch = max(mo, ms, since_epoch)
    return obs, summaries, max_epoch


def build_digest(obs, summaries):
    by_project = defaultdict(
        lambda: {
            "observations": [],
            "summaries": [],
            "concepts": Counter(),
            "types": Counter(),
            "files": Counter(),
        }
    )
    concept_to_projects = defaultdict(set)

    for (project, otype, title, subtitle, facts, narrative, concepts,
         files_read, files_modified, created_at, epoch) in obs:
        p = by_project[project]
        p["observations"].append(
            {
                "type": otype,
                "title": title,
                "subtitle": subtitle,
                "facts": parse_json_array(facts),
                "concepts": parse_json_array(concepts),
                "created_at": created_at,
            }
        )
        if otype:
            p["types"][otype] += 1
        for c in parse_json_array(concepts):
            p["concepts"][c] += 1
            concept_to_projects[c].add(project)
        for f in parse_json_array(files_read) + parse_json_array(files_modified):
            if isinstance(f, str):
                p["files"][f] += 1

    for (project, request, investigated, learned, completed, next_steps,
         notes, created_at, epoch) in summaries:
        by_project[project]["summaries"].append(
            {
                "request": request,
                "learned": learned,
                "completed": completed,
                "next_steps": next_steps,
                "notes": notes,
                "created_at": created_at,
            }
        )

    cross_project = {
        c: sorted(list(projs))
        for c, projs in concept_to_projects.items()
        if len(projs) >= 2
    }
    return by_project, cross_project


def render_markdown(by_project, cross_project, since_epoch, include_all, max_epoch):
    out = []
    scope = "ALL memory" if include_all else f"new memory (epoch > {since_epoch})"
    out.append("# claude-mem memory digest")
    out.append(f"Scope: {scope}  /  latest epoch: {max_epoch}\n")

    if not by_project:
        out.append("No new memory to process.\n")
        return "\n".join(out)

    out.append("## Cross-project concepts (appear in 2+ projects)")
    if cross_project:
        for c, projs in sorted(cross_project.items(), key=lambda x: -len(x[1])):
            out.append(f"- **{c}** — {', '.join(projs)}")
    else:
        out.append("- none")
    out.append("")
    out.append("> NOTE: the `concepts` tags below (how-it-works, what-changed, gotcha, "
               "pattern, ...) are claude-mem's internal taxonomy and are NOISE. Judge "
               "commonality from observation content (title/subtitle/facts/learned), "
               "not from these tags.")
    out.append("")

    for project, data in sorted(by_project.items()):
        out.append(f"## Project: {project}")
        out.append(
            f"{len(data['observations'])} observations / {len(data['summaries'])} summaries"
        )
        if data["types"]:
            tstr = ", ".join(f"{k}:{v}" for k, v in data["types"].most_common())
            out.append(f"Types: {tstr}")
        if data["concepts"]:
            cstr = ", ".join(
                f"{k}({v})" for k, v in data["concepts"].most_common(15)
            )
            out.append(f"Top concepts: {cstr}")
        out.append("")
        out.append("### Observation titles")
        for o in data["observations"][:60]:
            out.append(f"- [{o['type']}] {o['title']}")
            if o["subtitle"]:
                out.append(f"    - {o['subtitle']}")
        if len(data["observations"]) > 60:
            out.append(f"- ...and {len(data['observations']) - 60} more")
        out.append("")
        if data["summaries"]:
            out.append("### Session summaries (learned / next_steps)")
            for s in data["summaries"][:15]:
                if s["learned"]:
                    out.append(f"- learned: {s['learned']}")
                if s["next_steps"]:
                    out.append(f"    - next: {s['next_steps']}")
            out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", action="store_true", help="print the digest")
    ap.add_argument("--all", action="store_true", help="include ALL memory")
    ap.add_argument("--commit", type=int, metavar="EPOCH", help="advance the state checkpoint")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    state = load_state()

    if args.commit is not None:
        import datetime
        state["last_processed_epoch"] = args.commit
        state["last_run"] = datetime.datetime.now().isoformat()
        state.setdefault("history", []).append(
            {"run": state["last_run"], "committed_epoch": args.commit}
        )
        save_state(state)
        print(f"state updated: last_processed_epoch = {args.commit}")
        return

    conn = connect_db()

    if args.status:
        cur = conn.cursor()
        since = state["last_processed_epoch"]
        total_o = cur.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        total_s = cur.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
        new_o = cur.execute(
            "SELECT COUNT(*) FROM observations WHERE created_at_epoch > ?", (since,)
        ).fetchone()[0]
        new_s = cur.execute(
            "SELECT COUNT(*) FROM session_summaries WHERE created_at_epoch > ?", (since,)
        ).fetchone()[0]
        new = new_o + new_s  # unprocessed = observations + summaries
        print(f"DB: {DB_PATH}")
        print(f"last_processed_epoch: {since}")
        print(f"last_run: {state.get('last_run')}")
        print(f"observations total: {total_o} / summaries total: {total_s}")
        print(f"unprocessed: {new} (observations {new_o} / summaries {new_s})")
        return

    if args.digest:
        obs, summaries, max_epoch = fetch(
            conn, state["last_processed_epoch"], args.all
        )
        by_project, cross = build_digest(obs, summaries)
        print(
            render_markdown(
                by_project, cross, state["last_processed_epoch"], args.all, max_epoch
            )
        )
        print(f"\n<!-- MAX_EPOCH={max_epoch} -->")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
