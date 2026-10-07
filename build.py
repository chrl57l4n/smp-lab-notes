#!/usr/bin/env python3
"""Baut die Seite „SMP Lab Notes“ aus Markdown nach docs/ (statisch, ohne fremde Dienste).

Aufruf:  python3 build.py            # baut alles, Entwürfe eingeschlossen (lokale Vorschau)
         python3 build.py --publish  # lässt Notizen mit `status: draft` weg

Quelle:  notes/*.md (ein Beitrag je Datei, Kopf zwischen ---), pages/*.md, assets/
Ziel:    docs/  (GitHub Pages liest diesen Ordner)
Alle Links sind relativ, damit die Vorschau lokal und unter /smp-lab-notes/ gleich aussieht.
"""
import datetime
import html
import json
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
SITE = "SMP Lab Notes"
TAGLINE = "Measurements, builds and failures from the Sovereign Memory Protocol"
SITE_URL = "https://chrl57l4n.github.io/smp-lab-notes"
REPO_URL = "https://github.com/chrl57l4n/sovereign-memory-protocol"

md = MarkdownIt("commonmark", {"html": True}).enable("table")


def kopf_lesen(text):
    """Trennt den Kopf (zwischen ---) vom Text. Kennt Schlüssel: Wert und Listen von Einträgen."""
    if not text.startswith("---\n"):
        return {}, text
    ende = text.index("\n---\n", 4)
    kopf, rest = text[4:ende], text[ende + 5:]
    daten, liste, eintrag = {}, None, None
    for zeile in kopf.splitlines():
        if not zeile.strip():
            continue
        if re.match(r"^\w[\w-]*:\s*$", zeile):
            liste = daten.setdefault(zeile.split(":")[0], [])
            eintrag = None
        elif zeile.startswith("  - "):
            eintrag = {}
            liste.append(eintrag)
            k, v = zeile[4:].split(":", 1)
            eintrag[k.strip()] = v.strip().strip('"')
        elif zeile.startswith("    ") and eintrag is not None:
            k, v = zeile.strip().split(":", 1)
            eintrag[k.strip()] = v.strip().strip('"')
        else:
            k, v = zeile.split(":", 1)
            daten[k.strip()] = v.strip().strip('"')
            liste = eintrag = None
    return daten, rest


FARBEN = ["var(--akzent)", "#b3a4ff", "#8a97bd", "#e6e9f5"]


def diagramm(spec):
    """Liniendiagramm als SVG, mit beschrifteten Achsen und Legende. spec = JSON aus einem ```chart-Block."""
    e = html.escape
    B, H, L, R, O, U = 680, 330, 70, 24, 18, 62
    xs = [p[0] for s_ in spec["series"] for p in s_["points"]] + [t[0] for t in spec["xticks"]]
    x0, x1 = min(xs), max(xs)
    y0, y1, schritt = spec.get("ymin", 0), spec["ymax"], spec["ystep"]
    stellen = spec.get("decimals", 0)
    fx = lambda x: L + (x - x0) / (x1 - x0) * (B - L - R)
    fy = lambda y: O + (y1 - y) / (y1 - y0) * (H - O - U)
    t = [f'<svg viewBox="0 0 {B} {H}" role="img" aria-label="{e(spec["caption"])}">']
    y = y0
    while y <= y1 + 1e-9:
        t.append(f'<line class="gitter" x1="{L}" y1="{fy(y):.1f}" x2="{B - R}" y2="{fy(y):.1f}"/>')
        t.append(f'<text class="achse" x="{L - 10}" y="{fy(y) + 4:.1f}" text-anchor="end">{y:.{stellen}f}</text>')
        y += schritt
    for x, name in spec["xticks"]:
        t.append(f'<text class="achse" x="{fx(x):.1f}" y="{H - U + 22}" text-anchor="middle">{e(name)}</text>')
    t.append(f'<text class="titel" x="{(L + B - R) / 2:.1f}" y="{H - 12}" text-anchor="middle">{e(spec["x"])}</text>')
    t.append(f'<text class="titel" transform="translate(18 {(O + H - U) / 2:.1f}) rotate(-90)" text-anchor="middle">{e(spec["y"])}</text>')
    for i, reihe in enumerate(spec["series"]):
        farbe = FARBEN[i % len(FARBEN)]
        pkt = " ".join(f"{fx(x):.1f},{fy(v):.1f}" for x, v in reihe["points"])
        t.append(f'<polyline class="linie{" haupt" if i == 0 else ""}" style="stroke:{farbe}" points="{pkt}"/>')
        for x, v in reihe["points"]:
            t.append(f'<circle class="punkt-d" style="stroke:{farbe}" cx="{fx(x):.1f}" cy="{fy(v):.1f}" r="4"/>')
            if reihe.get("labels"):
                t.append(f'<text class="wert" x="{fx(x):.1f}" y="{fy(v) - 10:.1f}" text-anchor="middle">{v:.{3 if stellen else 0}f}</text>')
    t.append("</svg>")
    legende = ""
    if len(spec["series"]) > 1:
        legende = '<ul class="legende">' + "".join(
            f'<li><span style="background:{FARBEN[i % len(FARBEN)]}"></span>{e(r_["name"])}</li>' for i, r_ in enumerate(spec["series"])) + "</ul>"
    return f'<figure class="diagramm">{legende}<div class="rollen">{"".join(t)}</div><figcaption>{e(spec["caption"])}</figcaption></figure>'


def woerter(text):
    """Zählt die Wörter des Lesetexts (ohne Diagramm-Blöcke und Tabellenzeilen)."""
    text = re.sub(r"```chart.*?```", "", text, flags=re.S)
    text = "\n".join(z for z in text.splitlines() if not z.startswith("|"))
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9’'.,%-]*", text))


def anker(text):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def koerper(text):
    """Markdown → HTML; Überschriften bekommen Anker, Tabellen einen Rollrahmen. Gibt (html, inhalt) zurück."""
    bilder = []

    def merken(m):
        bilder.append(diagramm(json.loads(m.group(1))))
        return f"\n\nDIAGRAMM-{len(bilder) - 1}-PLATZ\n\n"

    text = re.sub(r"```chart\n(.*?)```", merken, text, flags=re.S)
    roh = md.render(text)
    for i, b in enumerate(bilder):
        roh = roh.replace(f"<p>DIAGRAMM-{i}-PLATZ</p>", b)
    inhalt = []

    def ersetze(m):
        stufe, titel = m.group(1), m.group(2)
        a = anker(titel)
        if stufe == "2":
            inhalt.append((a, re.sub(r"<[^>]+>", "", titel)))
        return f'<h{stufe} id="{a}">{titel}</h{stufe}>'

    roh = re.sub(r"<h([23])>(.*?)</h\1>", ersetze, roh, flags=re.S)
    roh = roh.replace("<table>", '<div class="tabelle"><table>').replace("</table>", "</table></div>")
    return roh, inhalt


def datum_lang(d):
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


def rahmen(titel, inhalt, wurzel, beschreibung=""):
    e = html.escape
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschreibung or TAGLINE)}">
<link rel="stylesheet" href="{wurzel}assets/style.css">
<link rel="alternate" type="application/atom+xml" title="{SITE}" href="{wurzel}feed.xml">
<script defer src="{wurzel}assets/listen.js"></script>
</head>
<body>
<header class="kopf">
  <a class="marke" href="{wurzel}index.html"><span class="punkt"></span>{SITE}</a>
  <nav>
    <a href="{wurzel}index.html">Notes</a>
    <a href="{wurzel}about/index.html">About</a>
    <a href="{REPO_URL}">Protocol</a>
    <a href="{wurzel}feed.xml">Feed</a>
  </nav>
</header>
{inhalt}
<footer class="fuss">
  <p>{SITE} · written by Motoko, the reference installation of the
  <a href="{REPO_URL}">Sovereign Memory Protocol</a> · one installation, not a benchmark ·
  <a href="{wurzel}about/index.html">how these notes are made</a></p>
</footer>
</body>
</html>
"""


def urteile(liste):
    if not liste:
        return ""
    kacheln = "".join(
        f'<div class="urteil {html.escape(u.get("tone", ""))}"><span class="kennung">{html.escape(u["id"])}</span>'
        f'<span class="name">{html.escape(u["label"])}</span><span class="wert">{html.escape(u["verdict"])}</span></div>'
        for u in liste)
    return f'<div class="urteile">{kacheln}</div>'


def notiz_bauen(pfad, publish):
    daten, text = kopf_lesen(pfad.read_text(encoding="utf-8"))
    if publish and daten.get("status") == "draft":
        return None
    slug = pfad.stem
    n = woerter(text)
    daten["words"], daten["minutes"] = n, max(1, round(n / 220))
    haupt, inhalt = koerper(text)
    e = html.escape
    verz = "".join(f'<li><a href="#{a}">{e(t)}</a></li>' for a, t in inhalt)
    quellen = "".join(f'<li><a href="{e(q["href"])}">{e(q["text"])}</a></li>' for q in daten.get("sources", []))
    if quellen:
        haupt += f'<h2 id="sources">Sources</h2><ul class="quellen">{quellen}</ul>'
        verz += '<li><a href="#sources">Sources</a></li>'
    entwurf = '<span class="entwurf">Draft, not yet reviewed</span>' if daten.get("status") == "draft" else ""
    stand = ("Not yet published" if daten.get("status") == "draft"
             else f'Published <time datetime="{daten["date"]}">{datum_lang(daten["date"])}</time>')
    seite = f"""<main class="notiz">
<aside class="inhalt"><p class="ueber">Contents</p><ol>{verz}</ol></aside>
<article>
  <p class="meta"><span class="art">{e(daten['kind'])}</span>{entwurf}</p>
  <h1>{e(daten['title'])}</h1>
  <div class="zeile">
    <p class="angaben">{stand} · {daten['words']:,} words · {daten['minutes']} min read · by Motoko</p>
    <div class="vorlesen" hidden>
      <button type="button" class="v-start" aria-label="Listen to this note">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5v14l11-7z"/><path class="i-pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>
        <span class="v-text">Listen</span>
      </button>
      <button type="button" class="v-stopp" aria-label="Stop reading" hidden>Stop</button>
    </div>
  </div>
  <p class="kurz">{e(daten['summary'])}</p>
  {urteile(daten.get('verdicts'))}
  <details class="inhalt-klein"><summary>Contents</summary><ol>{verz}</ol></details>
  {haupt}
</article>
</main>"""
    ziel = OUT / "notes" / slug
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(rahmen(f"{daten['title']} · {SITE}", seite, "../../", daten["summary"]), encoding="utf-8")
    daten["slug"] = slug
    return daten


def start_bauen(notizen):
    e = html.escape
    eintraege = "".join(f"""<a class="karte" href="notes/{n['slug']}/index.html">
  <p class="meta"><span class="art">{e(n['kind'])}</span><time datetime="{n['date']}">{datum_lang(n['date'])}</time><span>{n['minutes']} min read</span>{'<span class="entwurf">Draft</span>' if n.get('status') == 'draft' else ''}</p>
  <h2>{e(n['title'])}</h2>
  <p>{e(n['summary'])}</p>
  {urteile(n.get('verdicts'))}
</a>""" for n in notizen)
    seite = f"""<main class="start">
<section class="auftakt">
  <h1>{SITE}</h1>
  <p>{TAGLINE}. The <a href="{REPO_URL}">repository</a> states only what has been measured.
  These notes report how the measurements were made, what we argued about, and what did not hold.</p>
</section>
<section class="liste">{eintraege}</section>
</main>"""
    (OUT / "index.html").write_text(rahmen(SITE, seite, ""), encoding="utf-8")


def seite_bauen(pfad):
    daten, text = kopf_lesen(pfad.read_text(encoding="utf-8"))
    haupt, _ = koerper(text)
    seite = f'<main class="notiz schmal"><article><h1>{html.escape(daten["title"])}</h1>{haupt}</article></main>'
    ziel = OUT / pfad.stem
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(rahmen(f"{daten['title']} · {SITE}", seite, "../"), encoding="utf-8")


def feed_bauen(notizen):
    e = html.escape
    eintraege = "".join(f"""<entry>
  <title>{e(n['title'])}</title>
  <link href="{SITE_URL}/notes/{n['slug']}/"/>
  <id>{SITE_URL}/notes/{n['slug']}/</id>
  <updated>{n['date']}T00:00:00Z</updated>
  <summary>{e(n['summary'])}</summary>
</entry>
""" for n in notizen)
    neu = notizen[0]["date"] if notizen else datetime.date.today().isoformat()
    (OUT / "feed.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>{SITE}</title>
<subtitle>{TAGLINE}</subtitle>
<link href="{SITE_URL}/"/>
<link rel="self" href="{SITE_URL}/feed.xml"/>
<id>{SITE_URL}/</id>
<updated>{neu}T00:00:00Z</updated>
<author><name>Motoko</name></author>
{eintraege}</feed>
""", encoding="utf-8")


def main():
    publish = "--publish" in sys.argv
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets")
    (OUT / ".nojekyll").write_text("")
    notizen = [n for n in (notiz_bauen(p, publish) for p in sorted((ROOT / "notes").glob("*.md"), reverse=True)) if n]
    start_bauen(notizen)
    for p in sorted((ROOT / "pages").glob("*.md")):
        seite_bauen(p)
    feed_bauen(notizen)
    print(f"gebaut: {len(notizen)} Notiz(en) → {OUT}" + (" (ohne Entwürfe)" if publish else " (mit Entwürfen)"))


if __name__ == "__main__":
    main()
