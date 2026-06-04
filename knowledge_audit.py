#!/usr/bin/env python3
"""
Knowledge consolidation helper (AgentOps). Used by the monthly consolidation task.

Walks the Obsidian knowledge/ folder and surfaces duplicate candidates, tag
distribution, and stale notes so the LLM consolidation task can act. This script
only reads and analyzes; it never modifies notes.

Usage:
  python3 knowledge_audit.py --vault "<vault>" [--stale-days 120]
"""
import argparse
import datetime as dt
import os
import re
import sys
from collections import defaultdict


def parse_front(text):
    fm = {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"^(\w+):\s*(.*)$", line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip()
    htitle = ""
    hm = re.search(r"^#\s+(.*)$", text, re.M)
    if hm:
        htitle = hm.group(1).strip()
    return fm, htitle


def tags_of(fm):
    raw = fm.get("tags", "")
    return set(re.findall(r"[A-Za-z0-9_\-/.]+", raw)) - {"knowledge"}


def title_words(t):
    return set(re.findall(r"[A-Za-z0-9぀-ヿ一-鿿]+", t.lower())) if t else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--stale-days", type=int, default=120)
    args = ap.parse_args()

    kdir = os.path.join(args.vault, "knowledge")
    if not os.path.isdir(kdir):
        print(f"ERROR: {kdir} not found", file=sys.stderr)
        sys.exit(1)

    notes = []
    for fn in sorted(os.listdir(kdir)):
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        path = os.path.join(kdir, fn)
        with open(path, errors="ignore") as f:
            text = f.read()
        fm, htitle = parse_front(text)
        notes.append(dict(file=fn, project=fm.get("project", ""),
                          created=fm.get("created", ""), tags=tags_of(fm),
                          title=htitle, words=title_words(htitle)))

    print(f"# knowledge consolidation digest ({len(notes)} notes)\n")

    by_tag = defaultdict(list)
    by_proj = defaultdict(list)
    for n in notes:
        by_proj[n["project"]].append(n["file"])
        for t in n["tags"]:
            by_tag[t].append(n["file"])

    print("## Duplicate candidates (share 2+ tags OR large title-word overlap)")
    dup = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            a, b = notes[i], notes[j]
            shared = a["tags"] & b["tags"]
            wover = a["words"] & b["words"]
            if len(shared) >= 2 or len(wover) >= 3:
                dup.append((a["file"], b["file"], sorted(shared), sorted(wover)))
    if dup:
        for a, b, st, wo in dup:
            print(f"- `{a}` <-> `{b}` shared_tags:{st} common_words:{wo}")
    else:
        print("- none")
    print()

    print(f"## Stale notes ({args.stale_days}+ days old)")
    today = dt.date.today()
    stale = []
    for n in notes:
        try:
            d = dt.date.fromisoformat(n["created"])
            if (today - d).days >= args.stale_days:
                stale.append((n["file"], n["created"]))
        except Exception:
            pass
    if stale:
        for f, c in stale:
            print(f"- `{f}` ({c}) - verify it still matches reality")
    else:
        print("- none")
    print()

    print("## By project")
    for p, fs in sorted(by_proj.items()):
        print(f"- {p or '(none)'}: {', '.join(fs)}")
    print()
    print("## By tag (2+ notes)")
    for t, fs in sorted(by_tag.items(), key=lambda x: -len(x[1])):
        if len(fs) >= 2:
            print(f"- {t}: {', '.join(fs)}")


if __name__ == "__main__":
    main()
