"""Build the public GitHub Pages site into _site/ (run by .github/workflows/pages.yml).

    python tools/build_site.py OWNER/REPO [BASE]      BASE defaults to /REPO/

Copies index.html, designs/ and data/, adds site/tb-public.js to every page (it answers
/api/state from the vague data files) and points the local-server links at Pages paths.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
SKIP = {"v1", "v2", "test", "BRIEF.md"}


def main():
    repo = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "/" + repo.split("/")[1] + "/"
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "designs", OUT / "designs", ignore=lambda d, names: [n for n in names if n in SKIP])
    shutil.copytree(ROOT / "data", OUT / "data")
    shutil.copy(ROOT / "index.html", OUT / "index.html")
    shutil.copy(ROOT / "site" / "tb-public.js", OUT / "tb-public.js")
    (OUT / ".nojekyll").write_text("")

    listing = []
    for f in sorted((OUT / "designs").glob("*.html")):
        if f.name in ("gallery.html", "remix-browse.html"):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")[:4000]
        t = re.search(r"<title>(.*?)</title>", txt, re.S)
        m = re.search(r'<meta name="description" content="([^"]*)"', txt)
        listing.append({"file": f.name, "title": t.group(1).strip() if t else f.stem,
                        "about": m.group(1) if m else "", "mtime": 0})
    (OUT / "designs" / "designs.json").write_text(json.dumps(listing))

    shim = (f'<script>window.TB_REPO={json.dumps(repo)};window.TB_BASE={json.dumps(base)};</script>'
            f'<script src="{base}tb-public.js"></script>')
    for f in [OUT / "index.html", *(OUT / "designs").glob("*.html")]:
        s = f.read_text(encoding="utf-8")
        s = re.sub(r"(<head[^>]*>)", r"\1" + shim.replace("\\", "\\\\"), s, count=1, flags=re.I)
        s = s.replace('href="/gallery"', f'href="{base}designs/gallery.html"')
        s = s.replace('"/designs/', f'"{base}designs/').replace('href="/"', f'href="{base}"')
        s = s.replace("from this computer's logs", "from every computer that publishes (rounded)")
        s = s.replace("Fusion ledger · local", "Fusion ledger · shared").replace("FUSION LEDGER · LOCAL", "FUSION LEDGER · SHARED")
        f.write_text(s, encoding="utf-8")
    print(f"built {OUT} for {repo} at {base}: {len(listing)} designs")


if __name__ == "__main__":
    main()
