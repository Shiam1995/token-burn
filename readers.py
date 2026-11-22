"""Token Burn log readers: every AI tool on this computer that leaves token counts on disk.

Each reader returns {(day, source, estimated): tokens}. Files are cached by
(mtime, size), so the once-a-minute refresh only re-reads files that changed.

Measured (counted from the tool's own logs):
  Claude       ~/.claude/projects/**/*.jsonl, plus ~/token-usage/ledger.jsonl
               (the ledger keeps days whose Claude Code logs were deleted)
  Codex        ~/.codex/sessions/**/*.jsonl + ledger, plus duel-lab codex-cli seats
  Antigravity  ~/.gemini/antigravity-cli/brain/*/.../transcript_full.jsonl + ledger
               (duel-lab agy-cli seats are already in here)
  Qwen         ~/.qwen/usage/token-usage-*.jsonl (Qwen Code, one line per request)
  Kimi         ~/.kimi-code/sessions/**/wire.jsonl (incl. duel-lab Kimi seats)
  Mistral      ~/.vibe/logs/session/unified/*/  (Vibe, cumulative per session)
  GLM, DeepSeek, Qwen   duel-lab openai-compat seats (decisions.jsonl usage)
  OLMo, Qwen local      vLLM server logs: "Avg prompt/generation throughput"
                        lines every 10 s, summed x 10 s
Estimated:
  Claude before the first measured day: prompts per day in ~/.claude/history.jsonl
         x the measured tokens per prompt.
  Claude duel-lab seats run with --no-session-persistence (no counts kept):
         prompt + reply characters / 4 + thinking tokens.
Not on disk anywhere: Grok CLI, ChatGPT/Gemini/claude.ai web chats.
"""
import glob
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
LAB = HOME / "Lets Burn Tokens"
MATCHES = LAB / "millennium_engine" / "matches"
LEDGER = HOME / "token-usage" / "ledger.jsonl"

_files = {}  # path -> (sig, result)


def cached(path, fn):
    try:
        st = os.stat(path)
    except OSError:
        return None
    sig = (st.st_mtime, st.st_size)
    hit = _files.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        res = fn(path)
    except Exception:
        res = None
    _files[path] = (sig, res)
    return res


def jsonl(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def iso_day(ts):
    """ISO string or epoch ms to a local calendar day."""
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts).date().isoformat()
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone()
        return dt.date().isoformat()
    except Exception:
        return None


def mtime_day(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()


# ---------- per-file parsers ----------

def p_claude(path):
    """{msg key: (day, tokens)} so repeats across transcripts count once."""
    out = {}
    for o in jsonl(path):
        msg = o.get("message") if isinstance(o, dict) else None
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        if msg.get("model") == "<synthetic>":
            continue
        d = iso_day(o.get("timestamp", ""))
        if not d:
            continue
        u = msg["usage"]
        t = sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                              "cache_creation_input_tokens", "cache_read_input_tokens"))
        out[(msg.get("id"), o.get("requestId"))] = (d, t)
    return out


def p_codex(path):
    out, prev = Counter(), 0
    for o in jsonl(path):
        p = o.get("payload") or o.get("msg") or {}
        if p.get("type") != "token_count" or not p.get("info"):
            continue
        d = iso_day(o.get("timestamp", ""))
        info = p["info"]
        last = info.get("last_token_usage") or {}
        total = (info.get("total_token_usage") or {}).get("total_tokens")
        if last.get("total_tokens") is not None:
            t = int(last["total_tokens"])
        elif total is not None:
            t = max(0, int(total) - prev)
        else:
            continue
        if total is not None:
            prev = int(total)
        if d:
            out[d] += t
    return out


def p_antigravity(path):
    out, seen = Counter(), set()
    for o in jsonl(path):
        if "input_tokens" not in o or o.get("step_index") in seen:
            continue
        seen.add(o.get("step_index"))
        d = iso_day(o.get("created_at") or "") or mtime_day(path)
        out[d] += sum(int(o.get(k) or 0) for k in ("input_tokens", "cache_read_tokens", "output_tokens"))
    return out


def p_qwen(path):
    out = Counter()
    for o in jsonl(path):
        d = o.get("localDate") or iso_day(o.get("timestamp", ""))
        if d:
            out[d] += int(o.get("totalTokens") or 0)
    return out


def p_kimi(path):
    out = Counter()
    for o in jsonl(path):
        if o.get("type") != "usage.record":
            continue
        u = o.get("usage") or {}
        d = iso_day(o.get("time")) or mtime_day(path)
        out[d] += sum(int(u.get(k) or 0) for k in ("inputOther", "output", "inputCacheRead", "inputCacheCreation"))
    return out


def p_vibe(path):
    """Highest cumulative tokenUsage seen in one journal/projection file."""
    best = 0
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for m in re.finditer(r'"tokenUsage":\{[^}]*?"totalTokens":(\d+)', fh.read()):
            best = max(best, int(m.group(1)))
    return best


def p_decisions(path):
    """Duel-lab seats. Returns {(source, est): tokens} for the file's day."""
    out = Counter()
    for o in jsonl(path):
        md = o.get("metadata") or {}
        prov, model, u = md.get("provider"), (md.get("requested_model") or ""), md.get("usage")
        if prov == "codex-cli" and isinstance(u, dict):
            out[("Codex", False)] += int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0)
        elif prov == "openai-compat" and isinstance(u, dict):
            src = "GLM" if "glm" in model else "DeepSeek" if "deepseek" in model else \
                  "Qwen" if "qwen" in model else "Kimi" if "kimi" in model else "Other"
            out[(src, False)] += int(u.get("total_tokens") or 0) or \
                int(u.get("prompt_tokens") or 0) + int(u.get("completion_tokens") or 0)
        elif prov == "claude-cli":
            chars = len(o.get("prompt_sent") or "") + len(o.get("reason") or "")
            out[("Claude", True)] += chars // 4 + int(md.get("thinking_tokens") or 0)
        # agy-cli seats are already in the Antigravity logs
    return out


VLLM_RE = re.compile(r"INFO (\d\d)-(\d\d) [\d:]+ .*?Avg prompt throughput: ([\d.]+) tokens/s, "
                     r"Avg generation throughput: ([\d.]+) tokens/s")


def p_vllm(path):
    out = Counter()
    year = datetime.fromtimestamp(os.path.getmtime(path)).year
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if "throughput" not in line:
                continue
            m = VLLM_RE.search(line)
            if m:
                out[f"{year}-{m.group(1)}-{m.group(2)}"] += (float(m.group(3)) + float(m.group(4))) * 10
    return out


def p_ledger(path):
    """Per (day, tool) totals of the synced rows only (manual rows are read live here)."""
    out = Counter()
    for o in jsonl(path):
        if o.get("via") == "sync" and o.get("tool") in ("claude", "codex", "antigravity"):
            out[(o["day"], o["tool"])] += int(o.get("total") or 0)
    return out


def p_history(path):
    out = Counter()
    for o in jsonl(path):
        d = iso_day(o.get("timestamp")) if o.get("timestamp") else None
        if d:
            out[d] += 1
    return out


# ---------- sources ----------

def g(pattern):
    return glob.glob(str(pattern), recursive=True)


def scan_all():
    """Returns ({(day, source, est): tokens}, notes)."""
    res = Counter()

    # Claude Code: live logs, deduplicated across transcripts
    claude_dirs = [HOME / ".claude" / "projects", HOME / ".config" / "claude" / "projects"]
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        claude_dirs += [Path(p) / "projects" for p in env.split(",")]
    msgs = {}
    for root in claude_dirs:
        for f in g(root / "**" / "*.jsonl"):
            r = cached(f, p_claude)
            if r:
                msgs.update(r)
    live = {"claude": Counter(), "codex": Counter(), "antigravity": Counter()}
    for d, t in msgs.values():
        live["claude"][d] += t
    codex_home = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
    for f in g(codex_home / "sessions" / "**" / "*.jsonl"):
        live["codex"].update(cached(f, p_codex) or {})
    for f in g(HOME / ".gemini" / "antigravity-cli" / "brain" / "*" / ".system_generated" / "logs" / "transcript_full.jsonl"):
        live["antigravity"].update(cached(f, p_antigravity) or {})

    # the ledger remembers days whose logs are gone: take the larger per day
    ledger = cached(str(LEDGER), p_ledger) or {}
    names = {"claude": "Claude", "codex": "Codex", "antigravity": "Antigravity"}
    for tool, days in live.items():
        merged = dict(days)
        for (d, tl), t in ledger.items():
            if tl == tool:
                merged[d] = max(merged.get(d, 0), t)
        for d, t in merged.items():
            res[(d, names[tool], False)] += t

    for f in g(HOME / ".qwen" / "usage" / "token-usage-*.jsonl"):
        for d, t in (cached(f, p_qwen) or {}).items():
            res[(d, "Qwen", False)] += t
    for f in g(HOME / ".kimi-code" / "sessions" / "**" / "wire.jsonl"):
        for d, t in (cached(f, p_kimi) or {}).items():
            res[(d, "Kimi", False)] += t
    for sdir in g(HOME / ".vibe" / "logs" / "session" / "unified" / "*"):
        best = 0
        for f in g(Path(sdir) / "**" / "*.json*"):
            best = max(best, cached(f, p_vibe) or 0)
        if best:
            try:
                d = iso_day(json.load(open(Path(sdir) / "meta.json"))["start_time"])
            except Exception:
                d = mtime_day(sdir)
            res[(d, "Mistral", False)] += best

    for f in g(MATCHES / "**" / "decisions.jsonl"):
        r = cached(f, p_decisions)
        if r:
            d = mtime_day(f)
            for (src, est), t in r.items():
                res[(d, src, est)] += t

    for f in g(LAB / "**" / "*.log"):
        low = os.path.basename(f).lower()
        if "olmo" not in low and "qwen" not in low and "vllm" not in low:
            continue
        src = "OLMo" if "olmo" in low else "Qwen local" if "qwen" in low else "Local"
        for d, t in (cached(f, p_vllm) or {}).items():
            res[(d, src, False)] += int(t)

    # Claude Code days before the first measured day: estimate from prompt counts
    notes = {}
    hist = cached(str(HOME / ".claude" / "history.jsonl"), p_history) or {}
    claude_days = {d: t for (d, s, e), t in res.items() if s == "Claude" and not e and t > 0}
    if hist and claude_days:
        first = min(claude_days)
        both = [d for d in claude_days if hist.get(d)]
        rate = sum(claude_days[d] for d in both) / max(1, sum(hist[d] for d in both))
        notes["claude_per_prompt"] = round(rate)
        notes["claude_first_measured"] = first
        for d, n in hist.items():
            if d < first:
                res[(d, "Claude", True)] += int(n * rate)
    return {k: v for k, v in res.items() if v > 0}, notes
