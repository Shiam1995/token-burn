TOKEN BURN (local, offline)

Start:   ./start.sh   (Linux/macOS)   or double-click start.bat (Windows)
Open:    http://localhost:8787
Needs:   Python 3.9+ only. No internet.

What fills in by itself (re-read every minute while the page is open):
every AI tool on this computer that keeps token counts on disk. The full
list, and how each is read, is at the top of readers.py and under
"Starting point & sources" on the page:
  Claude Code (+ ~/token-usage/ledger.jsonl for deleted logs), Codex,
  Antigravity, Qwen Code, Kimi Code, Mistral Vibe, duel-lab API/CLI seats,
  local vLLM (OLMo, Qwen), and inbox.csv lines like 2026-11-18,Grok,1.2M

Kept for good: every scan copies each measured day (Claude Code, Codex,
Antigravity) into ~/token-usage/archive.json, largest value seen, and reads
Claude Code's own daily totals from ~/.claude/stats-cache.json. Claude Code
deletes its logs after 30 days; a day that was scanned once stays counted.
Run it at login (below) so no day slips past unscanned.

claude.ai web chats (no token counts exist, so estimated): ask for a data
export in claude.ai Settings, unzip it, then
  python3 tools/import_claude_export.py <export folder> [--science <chats zip>]
It writes "day,claude.ai,tokens,est" lines to inbox.csv; re-run with a newer
export to replace them. Account-wide, so do it on one computer only.

Estimated (dimmed on the heatmap, "est." in the day list):
  Claude Code days before 16 Oct, whose logs were deleted: prompts per day
  from ~/.claude/history.jsonl x measured tokens per prompt (~5.8M).
  Claude Code days between measured days with prompts but no counts: prompts
  x the middle tokens-per-prompt of the 7 measured days either side.
  Duel-lab claude -p seats, which keep no counts.

The counter is all of it plus "Extra tokens not in logs" (0 by default;
use it for other computers or web chats). The start date only matters for
money. Older version of these files: backup-2026-11-21/

By hand:
  python tokenburn.py add Qwen 1.2M
  python tokenburn.py pay "API top-up" 20
  python tokenburn.py scan        shows what the log readers found

Your data lives in state.json next to these files.

Run at login (Linux, systemd user service):
  mkdir -p ~/.config/systemd/user
  printf '[Service]\nExecStart=/usr/bin/python3 %s/tokenburn.py\nRestart=always\n[Install]\nWantedBy=default.target\n' "$PWD" > ~/.config/systemd/user/token-burn.service
  systemctl --user enable --now token-burn

----------------------------------------------------------------------
SHARED VERSION (GitHub)

Public page:  https://shiam1995.github.io/token-burn/   (gallery: designs/gallery.html)
It shows every computer's total added together, rounded: total to 0.1B,
today to 10M, each day to 5M, tools as % shares. Nothing else is published:
state.json, scan_cache.json and inbox.csv are gitignored and stay local.

Add another computer:
  git clone https://github.com/Shiam1995/token-burn.git
  cd token-burn
  git config user.email 30244715+Shiam1995@users.noreply.github.com   (keeps your email private)
  python3 publish.py --name laptop --loop 5      (pick any short name per computer)
Its tokens are read the same way as here (readers.py) and pushed every 5 minutes
when the rounded numbers change. The page picks them up within ~2 minutes.

Change a design from either computer: edit index.html or designs/*.html,
then  git pull --rebase && git commit -am "..." && git push
The site rebuilds itself in about a minute (GitHub Actions, .github/workflows/pages.yml).
publish.py pulls before every push, so both computers stay in step.
