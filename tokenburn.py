#!/usr/bin/env python3
"""Token Burn, local and offline.

Serves the fusion page on http://localhost:8787 and reads token usage
from every AI tool's local logs on this computer (readers.py), so the
counter fills in by itself.

    python tokenburn.py                 start the server (default)
    python tokenburn.py scan            print what the log readers found
    python tokenburn.py add Qwen 1.2M   log tokens by hand (e.g. from a script)
    python tokenburn.py pay "API top-up" 20

Only the Python standard library is used.
"""
import glob
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"
PORT = int(os.environ.get("TOKEN_BURN_PORT", "8787"))
HOME = Path.home()

DEFAULT_STATE = {
    "v": 2,
    "settings": {"baseDate": "2026-11-17", "baseTokens": 0, "basePaid": 0, "cur": "£"},
    "entries": [],
    "payments": [],
    "plans": [],  # your plans live in state.json (never published)
}

_lock = threading.Lock()


# ---------- state ----------

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


# ---------- log readers (see readers.py) ----------

import readers

_cache = {"at": 0, "auto": [], "notes": {}}
SCAN_FILE = HERE / "scan_cache.json"   # last scan, so a fresh start serves numbers instantly
_scan_lock = threading.Lock()


def _do_scan():
    with _scan_lock:
        try:
            res, notes = readers.scan_all()
        except Exception as e:
            print(f"[token-burn] scan failed: {e}", file=sys.stderr)
            return
        auto = [dict(d=d, p=p, t=t, **({"e": 1} if est else {}))
                for (d, p, est), t in sorted(res.items())]
        _cache.update(at=time.time(), auto=auto, notes=notes)
        try:
            SCAN_FILE.write_text(json.dumps({"auto": auto, "notes": notes}))
        except Exception:
            pass


def scan(force=False):
    """Never blocks a page: returns the newest finished scan (memory, else disk);
    a background thread keeps it fresh. Only a first-ever run waits."""
    if force:
        _do_scan()
        return _cache["auto"]
    if not _cache["at"] and SCAN_FILE.exists():
        try:
            j = json.loads(SCAN_FILE.read_text())
            _cache.update(at=1, auto=j["auto"], notes=j.get("notes", {}))
        except Exception:
            pass
    if not _cache["auto"]:
        _do_scan()
    return _cache["auto"]


def _scan_loop():
    while True:
        _do_scan()
        time.sleep(45)


def read_inbox():
    """Any tool can drop lines into inbox.csv: date,model,tokens"""
    out = []
    f = HERE / "inbox.csv"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 3 and re.match(r"\d{4}-\d{2}-\d{2}$", parts[0]):
                t = parse_tokens(parts[2])
                if t:
                    out.append({"d": parts[0], "p": parts[1], "t": t})
    return out


# ---------- helpers ----------

def parse_tokens(s):
    m = re.fullmatch(r"(\d*\.?\d+)([kmb]?)", str(s).strip().lower().replace(",", "").replace("_", ""))
    if not m:
        return 0
    return round(float(m.group(1)) * {"k": 1e3, "m": 1e6, "b": 1e9}.get(m.group(2), 1))


# ---------- server ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path.startswith("/api/state"):
            with _lock:
                st = load_state()
            return self._send(200, json.dumps({"state": st, "auto": scan() + read_inbox(),
                                               "notes": _cache["notes"]}))
        if self.path.startswith("/api/designs"):
            out = []
            for f in sorted((HERE / "designs").glob("*.html")):
                if f.name in ("gallery.html", "remix-browse.html"):
                    continue
                txt = f.read_text(encoding="utf-8", errors="ignore")[:4000]
                t = re.search(r"<title>(.*?)</title>", txt, re.S)
                m = re.search(r'<meta name="description" content="([^"]*)"', txt)
                out.append({"file": f.name, "title": t.group(1).strip() if t else f.stem,
                            "about": m.group(1) if m else "", "mtime": f.stat().st_mtime})
            return self._send(200, json.dumps(out))
        if self.path.split("?")[0] in ("/gallery", "/designs", "/designs/"):
            return self._send(200, (HERE / "designs" / "gallery.html").read_bytes(), "text/html; charset=utf-8")
        if self.path.startswith("/designs/"):
            from urllib.parse import unquote
            name = unquote(self.path.split("?")[0][len("/designs/"):])
            f = (HERE / "designs" / name).resolve()
            types = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                     ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json",
                     ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".woff2": "font/woff2", ".ttf": "font/ttf", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}
            if f.is_relative_to((HERE / "designs").resolve()) and f.is_file() and f.suffix.lower() in types:
                return self._send(200, f.read_bytes(), types[f.suffix.lower()])
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, '{"error":"bad json"}')
        if self.path == "/api/state":
            if not isinstance(body, dict) or "settings" not in body:
                return self._send(400, '{"error":"bad state"}')
            with _lock:
                save_state(body)
            return self._send(200, '{"ok":true}')
        if self.path == "/api/add":
            with _lock:
                st = load_state()
                add_entry(st, body.get("model", "Other"), parse_tokens(body.get("tokens", 0)), body.get("date"))
                save_state(st)
            return self._send(200, '{"ok":true}')
        self._send(404, "{}")


def add_entry(st, model, tokens, d=None):
    d = d or date.today().isoformat()
    for e in st["entries"]:
        if e["d"] == d and e["p"] == model:
            e["t"] += tokens
            break
    else:
        st["entries"].append({"d": d, "p": model, "t": tokens})
    st["entries"].sort(key=lambda e: e["d"])


def serve():
    if not STATE_FILE.exists():
        save_state(load_state())
    threading.Thread(target=_scan_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Token Burn running at http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "serve"
    if cmd == "serve":
        serve()
    elif cmd == "scan":
        auto = scan(force=True) + read_inbox()
        by = defaultdict(int)
        for e in auto:
            by[(e["p"], "estimated" if e.get("e") else "")] += e["t"]
        if not auto:
            print("No logs found.")
        for (p, est), t in sorted(by.items(), key=lambda x: -x[1]):
            print(f"{p:12s} {t:>16,}  {est}")
        print(f"{'TOTAL':12s} {sum(by.values()):>16,}  from {min(e['d'] for e in auto)}")
        print(_cache["notes"])
    elif cmd == "add" and len(argv) >= 4:
        st = load_state()
        add_entry(st, argv[2], parse_tokens(argv[3]), argv[4] if len(argv) > 4 else None)
        save_state(st)
        print("Logged.")
    elif cmd == "pay" and len(argv) >= 4:
        st = load_state()
        st["payments"].append({"d": argv[4] if len(argv) > 4 else date.today().isoformat(),
                               "l": argv[2], "a": float(argv[3])})
        save_state(st)
        print("Payment logged.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
