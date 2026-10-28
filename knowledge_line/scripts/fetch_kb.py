"""Fetch public guidance pages and the shelter open-data set into a profile.

    python -m knowledge_line.scripts.fetch_kb [--profile civil-protection-lt] [--only shelters|docs]

Pages are stored as Markdown with front matter (title, url, publisher,
fetched date) so every RAG answer can cite where it came from.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
import time
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

from ..config import load_settings

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def get_page(client: httpx.Client, url: str) -> tuple[str, str | None]:
    """Fetch a page; if the live site blocks automated clients (e.g. a bot
    challenge), fall back to the latest Internet Archive snapshot.
    Returns (html, archive_url_or_None)."""
    r = client.get(url, headers={"Accept": "text/html", "Accept-Language": "lt,en;q=0.5"})
    if r.status_code == 200 and "Just a moment" not in r.text[:2000]:
        return r.text, None
    a = client.get("https://archive.org/wayback/available", params={"url": url}).json()
    snap = (a.get("archived_snapshots") or {}).get("closest") or {}
    if not snap.get("available"):
        r.raise_for_status()
        raise RuntimeError(f"blocked (HTTP {r.status_code}) and no archive snapshot")
    # id_ suffix returns the original HTML without the Wayback toolbar
    arch = snap["url"].replace("http://", "https://")
    raw = re.sub(r"/web/(\d+)/", r"/web/\1id_/", arch)
    r2 = client.get(raw)
    r2.raise_for_status()
    return r2.text, arch
DROP = ["script", "style", "nav", "footer", "header", "form", "noscript", "aside", "iframe", "svg", "button"]
DROP_CLASSES = re.compile(r"(share|social|breadcrumb|cookie|menu|sidebar|related|comments|newsletter|footer|header)", re.I)


def _best_container(soup: BeautifulSoup) -> Tag:
    for sel in [".entry-content", "article", "main .content", "main", "#content", ".content", "body"]:
        nodes = soup.select(sel)
        if nodes:
            return max(nodes, key=lambda n: len(n.get_text(" ", strip=True)))
    return soup


def html_to_markdown(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.find("h1") or soup.find("title") or soup).get_text(" ", strip=True)
    title = re.sub(r"\s*[-|–]\s*(Lietuvos pasirengimas.*|Priešgaisrinės.*|Bendrasis pagalbos.*)$", "", title)
    root = _best_container(soup)
    for t in root.find_all(DROP):
        t.decompose()
    for t in root.find_all(class_=DROP_CLASSES):
        t.decompose()
    lines: list[str] = []

    def walk(node):
        for el in node.children:
            if isinstance(el, NavigableString):
                continue
            if not isinstance(el, Tag):
                continue
            name = el.name
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                txt = el.get_text(" ", strip=True)
                if txt:
                    lines.append("\n" + "#" * min(int(name[1]) + 1, 4) + " " + txt + "\n")
            elif name == "li":
                txt = el.get_text(" ", strip=True)
                if txt:
                    lines.append(f"- {txt}")
            elif name in ("p", "blockquote"):
                txt = el.get_text(" ", strip=True)
                if txt:
                    lines.append("\n" + txt + "\n")
            elif name == "table":
                for tr in el.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if any(cells):
                        lines.append("- " + " | ".join(cells))
            else:
                walk(el)

    walk(root)
    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return title, md


def fetch_docs(profile_dir: Path, sources: dict, client: httpx.Client) -> list[str]:
    kb = profile_dir / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    report = []
    today = dt.date.today().isoformat()
    for d in sources.get("documents", []):
        try:
            html, archive = get_page(client, d["url"])
            title, md = html_to_markdown(html)
            if len(md) < 200:
                raise ValueError(f"extracted only {len(md)} chars")
            front = {"title": d.get("title") or title, "url": d["url"], "publisher": d.get("publisher", ""),
                     "fetched": today, **({"archive_url": archive} if archive else {}), "license_note": "Vieša institucijos informacija; cituojama su šaltiniu."}
            target = kb / f"{d['id']}.md"
            if target.exists() and len(md) < 0.6 * len(target.read_text(encoding="utf-8")):
                report.append(f"KEEP {d['id']:32s} fetched text shorter than committed copy ({len(md)} chars)")
                continue
            target.write_text("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
                                              + "---\n\n# " + front["title"] + "\n\n" + md + "\n", encoding="utf-8")
            report.append(f"OK   {d['id']:32s} {len(md):6d} chars  {d['url']}" + (" (archive)" if archive else ""))
        except Exception as e:  # keep going; report
            report.append(f"FAIL {d['id']:32s} {type(e).__name__}: {e}")
        time.sleep(0.5)
    return report


SHELTER_FIELDS = ["savivaldybe", "seniunija", "gyvenviete", "gatve", "namo_numeris", "pavadinimas",
                  "gyventoju_skaicius", "plotas", "pritaikyta_asmenims_su_negalia", "patekimas_visa_para",
                  "wgs_lat_platuma", "wgs_lon_ilguma", "atnaujinimo_data"]


def fetch_shelters(profile_dir: Path, cfg: dict, client: httpx.Client) -> str:
    """Bulk CSV export from the data.gov.lt (Spinta) API, reduced to the fields we use."""
    import io

    url = cfg["url"]
    munis = cfg.get("municipalities") or []
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            r = client.get(url + "/:format/csv", timeout=180)
            r.raise_for_status()
            break
        except Exception as e:  # the API is occasionally flaky (502/500)
            last_err = e
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"shelter export failed: {last_err}")
    rows: list[dict] = []
    for it in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))):
        if munis and it.get("savivaldybe") not in munis:
            continue
        rows.append({k: (it.get(k) or "") for k in SHELTER_FIELDS})
    out = profile_dir / cfg.get("out", "data/shelters.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["savivaldybe"], r["seniunija"], r["gatve"], str(r["namo_numeris"])))
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHELTER_FIELDS)
        w.writeheader()
        w.writerows(rows)
    meta = {"source": url, "publisher": cfg.get("publisher", ""), "fetched": dt.date.today().isoformat(),
            "rows": len(rows), "municipalities": munis or "all"}
    (out.parent / "shelters.meta.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True), encoding="utf-8")
    return f"OK   shelters {len(rows)} rows -> {out}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--only", choices=["docs", "shelters"], default=None)
    a = ap.parse_args(argv)
    s = load_settings(overrides={"profile": a.profile} if a.profile else None)
    pdir = s.profile_dir
    sources = yaml.safe_load((pdir / "sources.yaml").read_text(encoding="utf-8"))
    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as c:
        if a.only in (None, "docs"):
            print("\n".join(fetch_docs(pdir, sources, c)))
        if a.only in (None, "shelters") and sources.get("structured", {}).get("shelters"):
            try:
                print(fetch_shelters(pdir, sources["structured"]["shelters"], c))
            except Exception as e:
                print(f"FAIL shelters {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
