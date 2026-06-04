#!/usr/bin/env python3
"""
Secret/PII guard (AgentOps: governance / prevent cloud leakage).

Scans content for API keys, tokens, and private keys and masks them BEFORE writing
to the (cloud-synced) Obsidian vault. claude-mem memory can contain plaintext
credentials, so this is the filter applied right before persisting long-term notes.

Usage:
  python3 redact.py --scrub <in> <out>   # mask, write to out, print a findings summary
  python3 redact.py --check <file|dir>    # scan only (dir walks *.md recursively)
  option: --mask-email  (also mask emails; default is detect-only)

Exit code on --check: 0 = nothing found / 3 = findings (for CI). --scrub always 0.
"""
import argparse
import os
import re
import sys

# (type, regex, value_group)  value_group=0 masks the whole match, >0 masks that group only
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), 0),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), 0),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), 0),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), 0),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}"), 0),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), 0),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), 0),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"), 0),
    ("generic_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|access[_-]?key|bearer)\b[\"'\s]*[:=]\s*[\"']?([A-Za-z0-9_\-]{16,})[\"']?"), 2),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def scrub_text(text, mask_email=False):
    findings = {}

    def mark(t):
        findings[t] = findings.get(t, 0) + 1

    for typ, rx, grp in PATTERNS:
        if grp == 0:
            def repl(m, t=typ):
                mark(t)
                return f"<<REDACTED:{t}>>"
            text = rx.sub(repl, text)
        else:
            def repl(m, t=typ, g=grp):
                mark(t)
                return m.group(0).replace(m.group(g), f"<<REDACTED:{t}>>")
            text = rx.sub(repl, text)

    if mask_email:
        def repl(m):
            mark("email")
            return "<<REDACTED:email>>"
        text = EMAIL.sub(repl, text)
    else:
        n = len(EMAIL.findall(text))
        if n:
            findings["email(flagged)"] = n
    return text, findings


def scan_text(text):
    findings = {}
    for typ, rx, _ in PATTERNS:
        n = len(rx.findall(text))
        if n:
            findings[typ] = n
    n = len(EMAIL.findall(text))
    if n:
        findings["email"] = n
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrub", nargs=2, metavar=("IN", "OUT"))
    ap.add_argument("--check", metavar="PATH")
    ap.add_argument("--mask-email", action="store_true")
    args = ap.parse_args()

    if args.scrub:
        src, dst = args.scrub
        with open(src, errors="ignore") as f:
            text = f.read()
        out, findings = scrub_text(text, mask_email=args.mask_email)
        with open(dst, "w") as f:
            f.write(out)
        masked = {k: v for k, v in findings.items() if not k.endswith("(flagged)")}
        if masked:
            print("masked: " + ", ".join(f"{k}:{v}" for k, v in masked.items()))
        flagged = {k: v for k, v in findings.items() if k.endswith("(flagged)")}
        if flagged:
            print("detected (not masked): " + ", ".join(f"{k}:{v}" for k, v in flagged.items()))
        if not findings:
            print("no secrets")
        sys.exit(0)

    if args.check:
        path = args.check
        files = []
        if os.path.isdir(path):
            for root, _, fns in os.walk(path):
                if "/.obsidian/" in root + "/" or "/.git/" in root + "/":
                    continue
                for fn in fns:
                    if fn.endswith(".md"):
                        files.append(os.path.join(root, fn))
        else:
            files = [path]
        any_hit = False
        for fp in sorted(files):
            try:
                with open(fp, errors="ignore") as f:
                    fnd = scan_text(f.read())
            except Exception:
                continue
            if fnd:
                any_hit = True
                rel = os.path.relpath(fp, path) if os.path.isdir(path) else fp
                print(f"{rel}: " + ", ".join(f"{k}:{v}" for k, v in fnd.items()))
        if not any_hit:
            print("clean (no findings)")
        sys.exit(3 if any_hit else 0)

    ap.print_help()


if __name__ == "__main__":
    main()
