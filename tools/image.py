"""Type your tokens into tokens.xlsx, then run this to get the picture.

    python3 tools/image.py              -> token-burn.png (and opens it)
    python3 tools/image.py out.png 1600 900

tokens.xlsx (made on the first run, stays on this computer): one row per entry,
  Date | Tool | Tokens        e.g.  22/11/2026 | Grok | 1.2M
Those rows are added to what the log readers find by themselves, so only type
what is not counted automatically (other computers, web chats, other tools).
Needs: openpyxl for the sheet, google-chrome or chromium for the picture.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SHEET = HERE / "tokens.xlsx"


def make_sheet():
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tokens"
    ws.append(["Date", "Tool", "Tokens"])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for col, w in (("A", 14), ("B", 18), ("C", 14)):
        ws.column_dimensions[col].width = w
    ws["E1"] = "One row per entry. Tokens: 1.2M, 500k or a plain number. Then run: python3 tools/image.py"
    wb.save(SHEET)


def up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=60).read()
        return True
    except Exception:
        return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else HERE / "token-burn.png").resolve()
    w, h = args[1:3] if len(args) >= 3 else ("1300", "800")
    if not SHEET.exists():
        make_sheet()
        print(f"made {SHEET}: add rows (Date | Tool | Tokens), save, run this again")

    started = time.time()
    port, srv = 8787, None
    if not up(port):                      # dashboard not running: start one just for the shot
        port = 8797
        srv = subprocess.Popen([sys.executable, str(HERE / "tokenburn.py")],
                               env={**os.environ, "TOKEN_BURN_PORT": str(port)},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            time.sleep(0.5)
            if up(port):
                break
    try:
        chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
        if not chrome:
            sys.exit("picture needs google-chrome or chromium")
        with tempfile.TemporaryDirectory() as prof:
            r = subprocess.run([chrome, "--headless=new", f"--screenshot={out}", f"--window-size={w},{h}",
                                f"--user-data-dir={prof}", "--hide-scrollbars", "--no-first-run",
                                "--virtual-time-budget=25000", f"http://127.0.0.1:{port}/"],
                               capture_output=True, text=True, timeout=120)
        if not out.exists() or out.stat().st_mtime < started:
            sys.exit("picture failed: " + r.stderr.strip()[-400:])
    finally:
        if srv:
            srv.terminate()
    print(f"{out}  ({date.today().isoformat()})")
    if "--no-open" not in sys.argv and os.environ.get("DISPLAY"):
        subprocess.Popen(["xdg-open", str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
