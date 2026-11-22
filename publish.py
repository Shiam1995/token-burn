"""Publish this computer's token use to the shared GitHub repo, rounded so it stays vague.

    python publish.py --name main            # once
    python publish.py --name main --loop 5   # every 5 minutes, forever

Each computer writes only its own file, data/m-<name>.json, so two computers never
clash. What leaves this computer (nothing else does):
  total   rounded to the nearest 0.1B
  today   rounded to the nearest 10M
  days    each day rounded to the nearest 5M
  models  tool names with their share rounded to the nearest 5%
No log contents, file paths, money or plan names are published.
The public page adds up every data/m-*.json it finds in data/machines.json.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOT = ["-c", "user.name=token-burn", "-c", "user.email=token-burn@users.noreply.github.com"]


def rnd(x, step):
    return int(round(x / step) * step)


def measure():
    import tokenburn
    auto = tokenburn.scan(force=True) + tokenburn.read_inbox()
    st = tokenburn.load_state()
    rows = auto + st.get("entries", [])
    extra = float(st.get("settings", {}).get("baseTokens") or 0)
    days, models = {}, {}
    for e in rows:
        days[e["d"]] = days.get(e["d"], 0) + e["t"]
        models[e["p"]] = models.get(e["p"], 0) + e["t"]
    total = sum(days.values()) + extra
    return total, days, models


def vague(name):
    total, days, models = measure()
    msum = sum(models.values()) or 1
    shares = sorted(((p, rnd(100 * t / msum, 5)) for p, t in models.items()), key=lambda x: -x[1])
    return {
        "name": name,
        "updated": date.today().isoformat(),
        "total": rnd(total, 1e8),
        "today": rnd(days.get(date.today().isoformat(), 0), 1e7),
        "days": {d: rnd(t, 5e6) for d, t in sorted(days.items()) if rnd(t, 5e6) > 0},
        "models": [{"name": p, "pct": s} for p, s in shares if s > 0],
    }


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=HERE, check=check, capture_output=True, text=True)


def write_index():
    names = sorted(p.stem[2:] for p in DATA.glob("m-*.json"))
    (DATA / "machines.json").write_text(json.dumps(names) + "\n")


def publish(name):
    if not re.fullmatch(r"[a-z0-9-]{1,32}", name):
        sys.exit("--name: lowercase letters, digits and - only")
    git("pull", "--rebase", "--autostash", "-q", check=False)
    DATA.mkdir(exist_ok=True)
    f = DATA / f"m-{name}.json"
    new = vague(name)
    old = json.loads(f.read_text()) if f.exists() else None
    if old and {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in new.items() if k != "updated"}:
        print(f"[publish] {name}: no change (~{new['total']/1e9:.1f}B)")
        return
    f.write_text(json.dumps(new, indent=1) + "\n")
    write_index()
    git("add", "data")
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        return
    git(*BOT, "commit", "-q", "-m", f"data: {name} ~{new['total']/1e9:.1f}B")
    for _ in range(3):
        if git("push", "-q", check=False).returncode == 0:
            print(f"[publish] {name}: pushed ~{new['total']/1e9:.1f}B, today ~{new['today']/1e6:.0f}M")
            return
        # someone else pushed first: replay on top; machines.json is the only shared file
        r = git("pull", "--rebase", "-q", check=False)
        if r.returncode:
            write_index()
            git("add", "data/machines.json")
            git(*BOT, "-c", "core.editor=true", "rebase", "--continue", check=False)
    print("[publish] push failed, will retry next time", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="label for this computer, e.g. main or laptop")
    ap.add_argument("--loop", type=float, default=0, help="repeat every N minutes")
    a = ap.parse_args()
    while True:
        try:
            publish(a.name)
        except Exception as e:
            print(f"[publish] {e}", file=sys.stderr)
        if not a.loop:
            break
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
