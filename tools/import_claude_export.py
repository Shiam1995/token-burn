"""Estimate claude.ai web-chat tokens from a data export and store them in inbox.csv.

    python3 tools/import_claude_export.py ~/Documents/claude-export-2026-11-06
    python3 tools/import_claude_export.py <export folder> --science <science chats .zip or folder>
    python3 tools/import_claude_export.py <export folder> --dry      # print, write nothing

claude.ai keeps no token counts, so this is an estimate (rows are marked "est"):
  characters / 4 for everything in a chat (text, thinking, tool calls and results,
  pasted attachments), and each reply is charged the whole conversation before it,
  the same way the CLI logs count re-read context. Images, system prompts and the
  re-reads inside one reply's tool loop are not counted, so it runs low.

Reads:  conversations/conversations.json   (chats)
        design_chats/**/*.json             (Claude Design)
        --science: chats/*.md              (the per-project markdown export; a chat
                                            already in conversations.json is skipped)
Writes: inbox.csv lines  day,claude.ai,tokens,est   (gitignored, stays on this computer).
Re-running replaces the claude.ai lines, so import a newer export any time.
These are account-wide: import on ONE computer only, or they are counted twice.
"""
import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
INBOX = HERE / "inbox.csv"
SOURCE = "claude.ai"
SKIP = {"start_timestamp", "stop_timestamp", "type", "uuid", "flags", "id"}


def size(x):
    if isinstance(x, str):
        return len(x)
    if isinstance(x, list):
        return sum(size(i) for i in x)
    if isinstance(x, dict):
        return sum(size(v) for k, v in x.items() if k not in SKIP)
    return 0


def charge(turns, days):
    """turns: [(day, is_reply, chars)] in order. A reply costs itself + all before it."""
    ctx = 0
    for day, is_reply, n in turns:
        if is_reply and day:
            days[day] += (n + ctx) / 4
        ctx += n


def chats(export, days):
    f = export / "conversations" / "conversations.json"
    if not f.exists():
        return set(), 0
    names = set()
    data = json.loads(f.read_text(encoding="utf-8"))
    for c in data:
        names.add((c.get("name") or "").strip().lower())
        turns = []
        for m in c.get("chat_messages") or []:
            n = size(m.get("content")) or len(m.get("text") or "")
            n += sum(len(a.get("extracted_content") or "") for a in m.get("attachments") or [])
            turns.append(((m.get("created_at") or "")[:10], m.get("sender") == "assistant", n))
        charge(turns, days)
    return names, len(data)


def design(export, days):
    n = 0
    for f in (export / "design_chats").rglob("*.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        turns = [((m.get("created_at") or "")[:10], m.get("role") == "assistant", size(m.get("content")))
                 for m in c.get("messages") or []]
        if turns:
            n += 1
            charge(turns, days)
    return n


def science(src, known, days):
    """Markdown chats named YYYY-MM-DD-title.md with '## Me' / '## Claude' turns."""
    if src.is_file():
        z = zipfile.ZipFile(src)
        files = [(n, z.read(n).decode("utf-8", "ignore")) for n in z.namelist()
                 if re.search(r"chats/\d{4}-\d\d-\d\d-.*\.md$", n)]
    else:
        files = [(str(p), p.read_text(encoding="utf-8", errors="ignore")) for p in src.rglob("*.md")
                 if re.match(r"\d{4}-\d\d-\d\d-", p.name)]
    used = skipped = 0
    for name, text in files:
        day = re.search(r"(\d{4}-\d\d-\d\d)-", name).group(1)
        title = text.split("\n", 1)[0].lstrip("# ").strip().lower()
        if title in known:
            skipped += 1
            continue
        parts = re.split(r"^## (Me|Claude)\s*$", text, flags=re.M)
        turns = [(day, parts[i] == "Claude", len(parts[i + 1])) for i in range(1, len(parts) - 1, 2)]
        charge(turns, days)
        used += 1
    return used, skipped


def write_inbox(days):
    keep = []
    if INBOX.exists():
        keep = [l for l in INBOX.read_text(encoding="utf-8").splitlines()
                if l.strip() and l.split(",")[1:2] != [SOURCE]]
    rows = [f"{d},{SOURCE},{int(t)},est" for d, t in sorted(days.items()) if t >= 1]
    INBOX.write_text("\n".join(keep + rows) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export", type=Path, help="unzipped claude.ai export folder")
    ap.add_argument("--science", type=Path, help="markdown chat export (.zip or folder)")
    ap.add_argument("--dry", action="store_true", help="print the totals, write nothing")
    a = ap.parse_args()
    if not a.export.is_dir():
        sys.exit(f"not a folder: {a.export}")

    parts = {}
    days = Counter()
    known, n = chats(a.export, days)
    parts[f"chats ({n})"] = sum(days.values())
    before = sum(days.values())
    n = design(a.export, days)
    parts[f"design chats ({n})"] = sum(days.values()) - before
    if a.science:
        before = sum(days.values())
        used, skipped = science(a.science, known, days)
        parts[f"science chats ({used}, {skipped} already in chats)"] = sum(days.values()) - before

    for k, v in parts.items():
        print(f"{k:48s} ~{v / 1e6:10,.1f}M")
    print(f"{'TOTAL':48s} ~{sum(days.values()) / 1e6:10,.1f}M   {min(days)} to {max(days)}, {len(days)} days")
    if a.dry:
        return
    write_inbox(days)
    print(f"stored in {INBOX} as '{SOURCE}' (estimated)")


if __name__ == "__main__":
    main()
