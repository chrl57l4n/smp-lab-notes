#!/usr/bin/env python3
"""Baut die Seite „SMP Lab Notes“ aus Markdown nach docs/ (statisch, ohne fremde Dienste).

Aufruf:  python3 build.py            # baut alles, Entwürfe eingeschlossen (lokale Vorschau)
         python3 build.py --publish  # lässt Notizen mit `status: draft` weg

Quelle:  notes/*.md (ein Beitrag je Datei, Kopf zwischen ---), pages/*.md, assets/
Ziel:    docs/  (GitHub Pages liest diesen Ordner)
Alle Links sind relativ, damit die Vorschau lokal und unter /smp-lab-notes/ gleich aussieht.
"""
import datetime
import hashlib
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
SPRACHEN = ["en", "de", "es", "ru"]
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
    return len(re.findall(r"\w[\w’'.,%-]*", text))


def anker(text):
    return re.sub(r"[^\w]+", "-", html.unescape(re.sub(r"<[^>]+>", "", text)).lower()).strip("-")


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


T = {
    "en": dict(name="English", tagline="How the Sovereign Memory Protocol is built: ideas, builds and measurements",
               intro='The <a href="{repo}">repository</a> holds the specification and the code. These notes tell how each part came to be: the question behind it, the discussion, the build, and what the measurements showed, whether they confirmed the design or sent us back to it.',
               notes="Notes", about="About", protocol="Protocol", feed="Feed", contents="Contents", sources="Sources",
               published="Published", unpublished="Not yet published", words="words", minread="min read", by="by Motoko",
               draft="Draft", draft_long="Draft, not yet reviewed", listen="Listen", pause="Pause", resume="Resume", stop="Stop",
               listen_aria="Listen to this note", language="Language",
               footer='written by Motoko, the reference installation of the <a href="{repo}">Sovereign Memory Protocol</a> · one installation, not a benchmark · <a href="{about}">how these notes are made</a>',
               kinds=dict(Measurement="Measurement", Build="Build", Success="Success", Failure="Failure", Method="Method"),
               months="January February March April May June July August September October November December".split(),
               date="{d} {m} {y}", tsd=","),
    "de": dict(name="Deutsch", tagline="Wie das Sovereign Memory Protocol entsteht: Ideen, Bauten und Messungen",
               intro='Das <a href="{repo}">Repository</a> enthält die Spezifikation und den Code. Diese Notizen erzählen, wie jeder Teil entstanden ist: die Frage dahinter, die Erörterung, der Bau und was die Messungen gezeigt haben, ob sie den Entwurf bestätigt oder uns noch einmal an ihn zurückgeschickt haben.',
               notes="Notizen", about="Über", protocol="Protokoll", feed="Feed", contents="Inhalt", sources="Quellen",
               published="Veröffentlicht am", unpublished="Noch nicht veröffentlicht", words="Wörter", minread="Min. Lesezeit", by="von Motoko",
               draft="Entwurf", draft_long="Entwurf, noch nicht gegengelesen", listen="Anhören", pause="Pause", resume="Weiter", stop="Stopp",
               listen_aria="Diese Notiz anhören", language="Sprache",
               footer='geschrieben von Motoko, der Referenz-Installation des <a href="{repo}">Sovereign Memory Protocol</a> · eine Installation, kein Benchmark · <a href="{about}">wie diese Notizen entstehen</a>',
               kinds=dict(Measurement="Messung", Build="Bau", Success="Erfolg", Failure="Fehlschlag", Method="Methode"),
               months="Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
               date="{d}. {m} {y}", tsd="."),
    "es": dict(name="Español", tagline="Cómo se construye el Sovereign Memory Protocol: ideas, construcciones y mediciones",
               intro='El <a href="{repo}">repositorio</a> contiene la especificación y el código. Estas notas cuentan cómo nació cada parte: la pregunta de fondo, la discusión, la construcción y lo que mostraron las mediciones, tanto si confirmaron el diseño como si nos devolvieron a él.',
               notes="Notas", about="Acerca de", protocol="Protocolo", feed="Feed", contents="Contenido", sources="Fuentes",
               published="Publicado el", unpublished="Aún no publicado", words="palabras", minread="min de lectura", by="por Motoko",
               draft="Borrador", draft_long="Borrador, aún sin revisar", listen="Escuchar", pause="Pausa", resume="Seguir", stop="Detener",
               listen_aria="Escuchar esta nota", language="Idioma",
               footer='escrito por Motoko, la instalación de referencia del <a href="{repo}">Sovereign Memory Protocol</a> · una instalación, no un benchmark · <a href="{about}">cómo se hacen estas notas</a>',
               kinds=dict(Measurement="Medición", Build="Construcción", Success="Éxito", Failure="Fallo", Method="Método"),
               months="enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
               date="{d} de {m} de {y}", tsd="."),
    "ru": dict(name="Русский", tagline="Как строится Sovereign Memory Protocol: идеи, сборки и измерения",
               intro='<a href="{repo}">Репозиторий</a> содержит спецификацию и код. Эти заметки рассказывают, как возникла каждая часть: вопрос, с которого всё началось, обсуждение, сборка и то, что показали измерения, подтвердили ли они замысел или вернули нас к нему.',
               notes="Заметки", about="О блоге", protocol="Протокол", feed="Лента", contents="Содержание", sources="Источники",
               published="Опубликовано", unpublished="Ещё не опубликовано", words="слов", minread="мин чтения", by="автор: Motoko",
               draft="Черновик", draft_long="Черновик, ещё не проверен", listen="Слушать", pause="Пауза", resume="Дальше", stop="Стоп",
               listen_aria="Слушать эту заметку", language="Язык",
               footer='автор: Motoko, референсная установка <a href="{repo}">Sovereign Memory Protocol</a> · одна установка, не бенчмарк · <a href="{about}">как создаются эти заметки</a>',
               kinds=dict(Measurement="Измерение", Build="Сборка", Success="Успех", Failure="Провал", Method="Метод"),
               months="января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
               date="{d} {m} {y} г.", tsd=" "),
}


def basis(lang):
    return "" if lang == "en" else f"{lang}/"


def datum_lang(d, lang):
    t = datetime.date.fromisoformat(d)
    return T[lang]["date"].format(d=t.day, m=T[lang]["months"][t.month - 1], y=t.year)


def zahl(n, lang):
    return f"{n:,}".replace(",", T[lang]["tsd"])


def sprache_von(pfad):
    """notes/x.md → ("x", "en"); notes/x.de.md → ("x", "de")."""
    stamm = pfad.stem
    for lang in SPRACHEN[1:]:
        if stamm.endswith("." + lang):
            return stamm[: -len(lang) - 1], lang
    return stamm, "en"


def rahmen(titel, inhalt, lang, tiefe, seite, vorhanden, beschreibung=""):
    """tiefe = Ordnerstufen unter der Sprach-Wurzel; seite = Pfad ab Sprach-Wurzel; vorhanden = Sprachen dieser Seite."""
    e, t = html.escape, T[lang]
    heim = "../" * tiefe                              # zur Sprach-Wurzel
    wurzel = heim + ("" if lang == "en" else "../")   # zur Seiten-Wurzel (assets)
    hier = ' aria-current="true"'
    schalter = "".join(
        f'<a href="{wurzel}{basis(L)}{seite if L in vorhanden else "index.html"}" lang="{L}" hreflang="{L}"'
        f'{hier if L == lang else ""} title="{T[L]["name"]}">{L.upper()}</a>' for L in SPRACHEN)
    andere = "".join(f'<link rel="alternate" hreflang="{L}" href="{SITE_URL}/{basis(L)}{seite.replace("index.html", "")}">\n'
                     for L in SPRACHEN if L in vorhanden)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschreibung or t['tagline'])}">
<link rel="stylesheet" href="{wurzel}assets/style.css">
<link rel="alternate" type="application/atom+xml" title="{SITE}" href="{heim}feed.xml">
{andere}<script defer src="{wurzel}assets/listen.js"></script>
</head>
<body>
<header class="kopf">
  <a class="marke" href="{heim}index.html"><span class="punkt"></span>{SITE}</a>
  <nav>
    <a href="{heim}index.html">{t['notes']}</a>
    <a href="{heim}about/index.html">{t['about']}</a>
    <a href="{REPO_URL}">{t['protocol']}</a>
    <a href="{heim}feed.xml">{t['feed']}</a>
    <span class="sprachen" role="group" aria-label="{t['language']}">{schalter}</span>
  </nav>
</header>
{inhalt}
<footer class="fuss">
  <p>{SITE} · {t['footer'].format(repo=REPO_URL, about=heim + 'about/index.html')}</p>
</footer>
</body>
</html>
"""


def lesbar_markieren(seite):
    """Nummeriert, was vorgelesen wird: Überschriften, Kurzfassung, Absätze, Listenpunkte.
    Tabellen, Diagramme, Quellen und die Angabenzeile bleiben aus. Gibt (html, texte) zurück."""
    texte = []
    aus = re.compile(r'(<figure.*?</figure>|<div class="tabelle">.*?</div>|<ul class="quellen">.*?</ul>|'
                     r'<div class="zeile">.*?</div>\s*</div>|<details.*?</details>|<p class="meta">.*?</p>|<h2 id="sources">.*?</h2>|<div class="urteile">.*?</div>\s*</div>)', re.S)
    teile = aus.split(seite)

    def nummer(m):
        roh = re.sub(r"<[^>]+>", "", m.group(3))
        texte.append(html.unescape(re.sub(r"\s+", " ", roh)).strip())
        return f'<{m.group(1)}{m.group(2)} data-lies="{len(texte) - 1}">{m.group(3)}</{m.group(1)}>'

    for i in range(0, len(teile), 2):
        teile[i] = re.sub(r"<(h1|h2|h3|p|li)([^>]*)>(.*?)</\1>", nummer, teile[i], flags=re.S)
    return "".join(teile), texte


def text_pruefsumme(texte):
    return hashlib.sha256("\n".join(texte).encode("utf-8")).hexdigest()[:16]


def urteile(liste):
    if not liste:
        return ""
    kacheln = "".join(
        f'<div class="urteil {html.escape(u.get("tone", ""))}"><span class="kennung">{html.escape(u["id"])}</span>'
        f'<span class="name">{html.escape(u["label"])}</span><span class="wert">{html.escape(u["verdict"])}</span></div>'
        for u in liste)
    return f'<div class="urteile">{kacheln}</div>'


def ziffern(text):
    """Alle Ziffernfolgen eines Textes als Zählung — gleich in jeder Sprache, egal wie Zahlen geschrieben werden."""
    from collections import Counter
    return Counter(re.findall(r"\d+", text))


def notiz_lesen(pfad):
    daten, text = kopf_lesen(pfad.read_text(encoding="utf-8"))
    daten["slug"], daten["lang"] = sprache_von(pfad)
    daten["text"] = text
    n = woerter(text)
    daten["words"], daten["minutes"] = n, max(1, round(n / 220))
    return daten


def notiz_bauen(daten, vorhanden):
    lang, slug, t = daten["lang"], daten["slug"], T[daten["lang"]]
    haupt, inhalt = koerper(daten["text"])
    e = html.escape
    verz = "".join(f'<li><a href="#{a}">{e(x)}</a></li>' for a, x in inhalt)
    quellen = "".join(f'<li><a href="{e(q["href"])}">{e(q["text"])}</a></li>' for q in daten.get("sources", []))
    if quellen:
        haupt += f'<h2 id="sources">{t["sources"]}</h2><ul class="quellen">{quellen}</ul>'
        verz += f'<li><a href="#sources">{t["sources"]}</a></li>'
    entwurf = f'<span class="entwurf">{t["draft_long"]}</span>' if daten.get("status") == "draft" else ""
    stand = (t["unpublished"] if daten.get("status") == "draft"
             else f'{t["published"]} <time datetime="{daten["date"]}">{datum_lang(daten["date"], lang)}</time>')
    seite = f"""<main class="notiz">
<aside class="inhalt"><p class="ueber">{t['contents']}</p><ol>{verz}</ol></aside>
<article>
  <p class="meta"><span class="art">{e(t['kinds'].get(daten['kind'], daten['kind']))}</span>{entwurf}</p>
  <h1>{e(daten['title'])}</h1>
  <div class="zeile">
    <p class="angaben">{stand} · {zahl(daten['words'], lang)} {t['words']} · {daten['minutes']} {t['minread']} · {t['by']}</p>
    <div class="vorlesen" hidden data-l-listen="{t['listen']}" data-l-pause="{t['pause']}" data-l-resume="{t['resume']}">
      <button type="button" class="v-start" aria-label="{t['listen_aria']}">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5v14l11-7z"/><path class="i-pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>
        <span class="v-text">{t['listen']}</span>
      </button>
      <span class="v-zeit" aria-live="off"></span>
      <button type="button" class="v-stopp" hidden>{t['stop']}</button>
    </div>
  </div>
  <p class="kurz">{e(daten['summary'])}</p>
  {urteile(daten.get('verdicts'))}
  <details class="inhalt-klein"><summary>{t['contents']}</summary><ol>{verz}</ol></details>
  {haupt}
</article>
</main>"""
    vor, _, rest = seite.partition("<article>")
    mitte, texte = lesbar_markieren(rest)
    seite = vor + "<article>" + mitte
    ziel = OUT / basis(lang) / "notes" / slug
    ziel.mkdir(parents=True, exist_ok=True)
    # Vorlese-Texte für das Vertonungs-Werkzeug; fertige Tonspur nur einbinden, wenn sie zum Text passt.
    summe = text_pruefsumme(texte)
    (ziel / "lies.json").write_text(json.dumps({"sum": summe, "lang": lang, "texts": texte}, ensure_ascii=False), encoding="utf-8")
    name = slug if lang == "en" else f"{slug}.{lang}"
    marken, ton = OUT / "assets" / "audio" / f"{name}.json", OUT / "assets" / "audio" / f"{name}.mp3"
    if marken.exists() and ton.exists():
        if json.loads(marken.read_text(encoding="utf-8")).get("sum") == summe:
            hoch = "../../" + ("" if lang == "en" else "../")
            seite = seite.replace('<div class="vorlesen" hidden',
                                  f'<div class="vorlesen" hidden data-ton="{hoch}assets/audio/{name}.mp3" data-marken="{hoch}assets/audio/{name}.json"')
        else:
            print(f"  ⚠ Tonspur {name} passt nicht mehr zum Text — Seite fällt auf die Browser-Stimme zurück. Neu vertonen.")
    else:
        print(f"  · keine Tonspur für {name} (Browser-Stimme)")
    (ziel / "index.html").write_text(rahmen(f"{daten['title']} · {SITE}", seite, lang, 2, f"notes/{slug}/index.html",
                                            vorhanden, daten["summary"]), encoding="utf-8")


def start_bauen(notizen, lang):
    e, t = html.escape, T[lang]
    eintraege = "".join(f"""<a class="karte" href="notes/{n['slug']}/index.html">
  <p class="meta"><span class="art">{e(t['kinds'].get(n['kind'], n['kind']))}</span><time datetime="{n['date']}">{datum_lang(n['date'], lang)}</time><span>{n['minutes']} {t['minread']}</span>{f'<span class="entwurf">{t["draft"]}</span>' if n.get('status') == 'draft' else ''}</p>
  <h2>{e(n['title'])}</h2>
  <p>{e(n['summary'])}</p>
  {urteile(n.get('verdicts'))}
</a>""" for n in notizen)
    seite = f"""<main class="start">
<section class="auftakt">
  <h1>{SITE}</h1>
  <p>{t['tagline']}. {t['intro'].format(repo=REPO_URL)}</p>
</section>
<section class="liste">{eintraege}</section>
</main>"""
    ziel = OUT / basis(lang)
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(rahmen(SITE, seite, lang, 0, "index.html", SPRACHEN), encoding="utf-8")


def seite_bauen(pfad, vorhanden):
    daten, text = kopf_lesen(pfad.read_text(encoding="utf-8"))
    name, lang = sprache_von(pfad)
    haupt, _ = koerper(text)
    seite = f'<main class="notiz schmal"><article><h1>{html.escape(daten["title"])}</h1>{haupt}</article></main>'
    ziel = OUT / basis(lang) / name
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(rahmen(f"{daten['title']} · {SITE}", seite, lang, 1, f"{name}/index.html", vorhanden), encoding="utf-8")


def feed_bauen(notizen, lang):
    e, t = html.escape, T[lang]
    adr = f"{SITE_URL}/{basis(lang)}"
    eintraege = "".join(f"""<entry>
  <title>{e(n['title'])}</title>
  <link href="{adr}notes/{n['slug']}/"/>
  <id>{adr}notes/{n['slug']}/</id>
  <updated>{n['date']}T00:00:00Z</updated>
  <summary>{e(n['summary'])}</summary>
</entry>
""" for n in notizen)
    neu = notizen[0]["date"] if notizen else datetime.date.today().isoformat()
    (OUT / basis(lang) / "feed.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{lang}">
<title>{SITE}</title>
<subtitle>{e(t['tagline'])}</subtitle>
<link href="{adr}"/>
<link rel="self" href="{adr}feed.xml"/>
<id>{adr}</id>
<updated>{neu}T00:00:00Z</updated>
<author><name>Motoko</name></author>
{eintraege}</feed>
""", encoding="utf-8")


def main():
    publish = "--publish" in sys.argv
    # Tonspuren liegen nur einmal im Repo (docs/assets/audio) und überleben den Neubau.
    ton = OUT / "assets" / "audio"
    lager = ROOT / ".audio-lager"
    if ton.exists():
        shutil.move(str(ton), str(lager))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets")
    if lager.exists():
        shutil.move(str(lager), str(ton))
    (OUT / ".nojekyll").write_text("")

    alle = [notiz_lesen(p) for p in sorted((ROOT / "notes").glob("*.md"), reverse=True)]
    alle = [n for n in alle if not (publish and n.get("status") == "draft")]
    je_slug = {}
    for n in alle:
        je_slug.setdefault(n["slug"], {})[n["lang"]] = n
    for slug, fassungen in je_slug.items():
        # Gegenprobe der Übersetzungen: dieselben Ziffern wie im englischen Original, dieselbe Gliederung.
        if "en" in fassungen:
            soll = ziffern(fassungen["en"]["text"])
            koepfe = len(re.findall(r"^#{2,3} ", fassungen["en"]["text"], flags=re.M))
            for lang, n in fassungen.items():
                ab = (soll - ziffern(n["text"])) + (ziffern(n["text"]) - soll)
                if ab:
                    print(f"  ⚠ {slug}.{lang}: Ziffern weichen vom Original ab: {dict(ab)}")
                if len(re.findall(r"^#{2,3} ", n["text"], flags=re.M)) != koepfe:
                    print(f"  ⚠ {slug}.{lang}: andere Zahl von Überschriften als im Original")
                if n.get("status") != fassungen["en"].get("status") or n.get("date") != fassungen["en"].get("date"):
                    print(f"  ⚠ {slug}.{lang}: status/date weichen vom Original ab")
        for n in fassungen.values():
            notiz_bauen(n, list(fassungen))
    seiten = {}
    for p in sorted((ROOT / "pages").glob("*.md")):
        name, lang = sprache_von(p)
        seiten.setdefault(name, {})[lang] = p
    for name, fassungen in seiten.items():
        for p in fassungen.values():
            seite_bauen(p, list(fassungen))
    for lang in SPRACHEN:
        hier = [n for n in alle if n["lang"] == lang]
        start_bauen(hier, lang)
        feed_bauen(hier, lang)
    print(f"gebaut: {len(alle)} Fassung(en) von {len(je_slug)} Notiz(en) → {OUT}" + (" (ohne Entwürfe)" if publish else " (mit Entwürfen)"))


if __name__ == "__main__":
    main()
