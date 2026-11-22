/* Public (GitHub Pages) mode for Token Burn.
   Loaded before every page's own scripts by tools/build_site.py. It answers the pages'
   /api/state and /api/designs calls from the repo's vague data files, so the same
   pages run unchanged locally and online.
   Live: every 90 s it asks GitHub for the newest commit and reads data/ at that commit
   (raw files by commit id are never stale), so new numbers show within ~2 minutes of a push. */
(function () {
  const REPO = window.TB_REPO, BASE = window.TB_BASE || "/";
  const realFetch = window.fetch.bind(window);
  let sha = null, combined = null, lastCheck = 0;

  async function readData(ref) {
    const root = ref ? `https://raw.githubusercontent.com/${REPO}/${ref}/data/` : BASE + "data/";
    const names = await (await realFetch(root + "machines.json", { cache: "no-store" })).json();
    const ms = await Promise.all(names.map(n => realFetch(root + `m-${n}.json`, { cache: "no-store" }).then(r => r.json()).catch(() => null)));
    return ms.filter(Boolean);
  }

  function combine(ms) {
    const days = {}, models = {};
    let total = 0;
    for (const m of ms) {
      total += m.total;
      for (const [d, t] of Object.entries(m.days || {})) days[d] = (days[d] || 0) + t;
      for (const x of m.models || []) models[x.name] = (models[x.name] || 0) + m.total * x.pct / 100;
    }
    const msum = Object.values(models).reduce((a, b) => a + b, 0) || 1;
    const shares = Object.entries(models).map(([p, t]) => [p, t / msum]);
    // scale the (rounded) days so they add up to the rounded total, keeping every figure vague
    const daySum = Object.values(days).reduce((a, b) => a + b, 0) || 1, k = total / daySum;
    const auto = [];
    for (const [d, t] of Object.entries(days).sort())
      for (const [p, s] of shares) if (t * s * k >= 1) auto.push({ d, p, t: Math.round(t * s * k) });
    return {
      state: { settings: { baseDate: "2026-11-17", baseTokens: 0, basePaid: 0, cur: "£" }, entries: [], payments: [], plans: [], v: 2 },
      auto, notes: {}, public: true, machines: ms.map(m => m.name)
    };
  }

  async function refresh() {
    if (combined && Date.now() - lastCheck < 85e3) return combined;
    lastCheck = Date.now();
    try {
      const r = await realFetch(`https://api.github.com/repos/${REPO}/commits/main`, { headers: { Accept: "application/vnd.github.sha" }, cache: "no-store" });
      if (!r.ok) throw 0;
      const s = (await r.text()).trim();
      if (s !== sha || !combined) { combined = combine(await readData(s)); sha = s; }
    } catch (e) {
      if (!combined) try { combined = combine(await readData(null)); } catch (e2) {}
    }
    return combined;
  }

  const json = o => new Response(JSON.stringify(o), { headers: { "Content-Type": "application/json" } });
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    const method = ((init && init.method) || "GET").toUpperCase();
    if (/(^|\/)api\/state/.test(url)) {
      if (method !== "GET") return json({ ok: true, public: true }); // settings can't be saved online
      const c = await refresh();
      return c ? json(c) : Promise.reject(new Error("no data"));
    }
    if (/(^|\/)api\/designs/.test(url)) return realFetch(BASE + "designs/designs.json");
    return realFetch(input, init);
  };
  refresh();
})();
