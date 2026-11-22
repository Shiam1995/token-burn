/* Token Burn shared data helper for the design gallery.
   Include with <script src="tb-data.js"></script>, then:

     TB.onData(d => { ...draw... });   // called now-ish and again every 60 s

   d = {
     total,        // all tokens burned (number)
     measured,     // counted from logs
     estimated,    // estimated part (old Claude Code days, claude -p seats)
     today,        // tokens today
     week,         // last 7 days incl. today
     since,        // tokens since the money start date (17 Nov)
     paid,         // money paid (plans + payments), number
     cur,          // currency symbol, e.g. "£"
     firstDay,     // "2026-08-10"
     todayISO,     // "2026-11-21"
     models: [{name, tokens, share, color}]   // biggest first
     days:   [{d, tokens, est, byModel:{name:tokens}}]  // every day with use, oldest first
     maxDay,       // biggest single day
     intensity,    // 0..1, today's activity (log scale) – use for animation energy
     demo          // true when the server isn't reachable and numbers are sample data
   }
   Helpers: TB.fmt(n) -> "7.86B"/"412M"/"9.8k", TB.full(n) -> "7,860,595,866",
            TB.color(name), TB.COLORS
   Add ?demo=1 to the URL to force sample data.
*/
(function () {
  const COLORS = {
    Claude: "#ff7a3d", Codex: "#3ddc97", Antigravity: "#4f8dff", Gemini: "#4f8dff", Qwen: "#a98bff",
    "Qwen local": "#7d6be0", Kimi: "#ff4f6d", Mistral: "#ffb81f", GLM: "#2fd3e8", DeepSeek: "#b8e64a",
    OLMo: "#f06bd6", Grok: "#e8f1ff", Local: "#c4ccd8", Other: "#7d8ba3"
  };
  const pad = n => String(n).padStart(2, "0");
  const iso = d => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  const trim = x => x.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  function fmt(n) {
    if (n >= 1e9) return trim((n / 1e9).toFixed(n >= 1e11 ? 1 : 2)) + "B";
    if (n >= 1e6) return trim((n / 1e6).toFixed(n >= 1e7 ? 1 : 2)) + "M";
    if (n >= 1e3) return trim((n / 1e3).toFixed(n >= 1e4 ? 0 : 1)) + "k";
    return String(Math.round(n));
  }
  const full = n => Math.round(n).toLocaleString("en-GB");
  const color = p => COLORS[p] || "#a9b4c6";

  function demoRaw() {
    const auto = [], t0 = new Date(); let seed = 7;
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 103; i >= 0; i--) {
      const d = iso(new Date(t0 - i * 864e5));
      if (rnd() < .3) continue;
      auto.push({ d, p: "Claude", t: Math.round(2e7 + rnd() * 2.2e8), ...(i > 40 ? { e: 1 } : {}) });
      if (i < 20) for (const p of ["Qwen", "Kimi", "Codex", "Antigravity", "Mistral"]) if (rnd() < .5) auto.push({ d, p, t: Math.round(rnd() * 4e7) });
    }
    return { state: { settings: { baseDate: "2026-11-17", baseTokens: 0, basePaid: 0, cur: "£" }, entries: [], payments: [], plans: [] }, auto };
  }

  function build(raw, demo) {
    const st = raw.state || {}, s = st.settings || {};
    const all = (st.entries || []).concat(raw.auto || []);
    const todayISO = iso(new Date()), weekAgo = iso(new Date(Date.now() - 6 * 864e5));
    const dayMap = {}, modelMap = {};
    let measured = 0, estimated = 0;
    for (const e of all) {
      const x = dayMap[e.d] || (dayMap[e.d] = { d: e.d, tokens: 0, est: 0, byModel: {} });
      x.tokens += e.t; x.byModel[e.p] = (x.byModel[e.p] || 0) + e.t;
      if (e.e) { x.est += e.t; estimated += e.t } else measured += e.t;
      modelMap[e.p] = (modelMap[e.p] || 0) + e.t;
    }
    const extra = +s.baseTokens || 0;
    const total = measured + estimated + extra;
    const days = Object.values(dayMap).sort((a, b) => a.d < b.d ? -1 : 1);
    const sum = Object.values(modelMap).reduce((a, b) => a + b, 0) || 1;
    const models = Object.entries(modelMap).sort((a, b) => b[1] - a[1])
      .map(([name, tokens]) => ({ name, tokens, share: tokens / sum, color: color(name) }));
    const today = (dayMap[todayISO] || {}).tokens || 0;
    const week = days.filter(x => x.d >= weekAgo).reduce((a, x) => a + x.tokens, 0);
    const since = days.filter(x => x.d >= (s.baseDate || "2026-11-17")).reduce((a, x) => a + x.tokens, 0);
    // money: plans charged on billing day after start + payments after start + already paid
    let paid = +s.basePaid || 0; const base = s.baseDate || "2026-11-17";
    for (const p of st.plans || []) {
      if (!p.on || !(p.price > 0)) continue;
      const from = p.from || base, start = new Date((from > base ? from : base) + "T00:00"), end = new Date(todayISO + "T00:00");
      let y = start.getFullYear(), m = start.getMonth();
      for (let i = 0; i < 600; i++) {
        const dim = new Date(y, m + 1, 0).getDate(), d = new Date(y, m, Math.min(p.day || 1, dim));
        if (d > end) break; const k = iso(d); if (k > base && k >= from) paid += p.price; if (++m > 11) { m = 0; y++ }
      }
    }
    for (const p of st.payments || []) if (p.d > base) paid += p.a;
    return {
      total, measured, estimated: estimated, today, week, since, paid, cur: s.cur || "£",
      firstDay: days.length ? days[0].d : todayISO, todayISO, models, days,
      maxDay: Math.max(1, ...days.map(x => x.tokens)),
      intensity: Math.max(0, Math.min(1, Math.log10(today + 1) / 9.3)), demo: !!demo
    };
  }

  const subs = []; let last = null;
  async function pull() {
    let d;
    if (/[?&]demo=1/.test(location.search)) d = build(demoRaw(), true);
    else {
      try { const r = await fetch("/api/state", { cache: "no-store" }); d = build(await r.json(), false) }
      catch (e) { d = build(demoRaw(), true) }
    }
    last = d; subs.forEach(f => { try { f(d) } catch (e) { console.error(e) } });
  }
  window.TB = { onData(f) { subs.push(f); if (last) f(last) }, fmt, full, color, COLORS, iso };
  pull(); setInterval(() => { if (!document.hidden) pull() }, 60000);
})();
