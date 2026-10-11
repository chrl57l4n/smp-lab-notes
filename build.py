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
KOMMENTAR_REPO = "Motoko-smp/smp-lab-notes-comments"   # ein Issue je Beitrag; Zuordnung in comments.json (scripts/blog_issues.py)
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


FENSTER = (30, 84, 365, 1825, 9999)   # Tage · Wochen · Monate · Jahre · Max


def _zeit(z):
    return datetime.datetime.fromisoformat(z if "T" in z else z + "T12:00")


def _stufe(spanne, ziel=5):
    """Runde Schrittweite (1, 2, 5 × Zehnerpotenz), so dass etwa `ziel` Linien entstehen."""
    import math
    roh = max(spanne, 1e-9) / ziel
    zehner = 10 ** math.floor(math.log10(roh))
    for f in (1, 2, 5, 10):
        if roh <= f * zehner:
            return f * zehner
    return 10 * zehner


def diagramm_lebend(spec, lang):
    """Fortlaufende Grafik (der menschliche Partner, 11.10.2026): Messreihe aus data/<live>.json, echte Daten auf der x-Achse,
    senkrechter Strich am Tag der Veröffentlichung, Auswahl des Zeitraums (Tage · Wochen · Monate · Jahre · Max).
    Je Zeitraum wird ein fertiges Bild gebaut; assets/zeitraum.js schaltet nur um. Ohne Skript bleibt „Max“ sichtbar.
    Der Hinweis „wöchentlich aktualisiert“ erscheint erst, wenn die Daten-Datei mindestens einen Wochenlauf nennt."""
    e, t = html.escape, T[lang]
    daten = json.loads((ROOT / "data" / f"{spec['live']}.json").read_text(encoding="utf-8"))
    reihen = []
    for r_ in spec["series"]:
        punkte = sorted((_zeit(z), float(v)) for z, v in daten["series"][r_["key"]])
        if len(punkte) < 2:
            raise SystemExit(f"lebende Grafik {spec['live']}: Reihe {r_['key']} hat weniger als zwei Punkte")
        reihen.append((r_["name"], punkte))
    erster = min(p[0][0] for _, p in reihen)
    letzter = max(p[-1][0] for _, p in reihen)
    marke = _zeit(spec["published"] + "T23:59") if spec.get("published") else None
    linie = spec.get("hline")
    B, H, L, R, O, U = 680, 330, 70, 24, 22, 62
    stellen = spec.get("decimals", 0)

    def tag(d, mit_jahr):
        return (t["kurz_j"].format(m=t["mon"][d.month - 1], y=d.year) if mit_jahr
                else t["kurz"].format(d=d.day, m=t["mon"][d.month - 1]))

    bilder = []
    for n, tage in enumerate(FENSTER):
        von = max(erster, letzter - datetime.timedelta(days=tage)) if tage < 9999 else erster
        # Liegt der Tag der Veröffentlichung hinter dem letzten Punkt, reicht die Achse bis dorthin (der Strich bleibt sichtbar).
        ende = max(letzter, marke) if marke and marke >= von else letzter
        spanne = max((ende - von).total_seconds(), 3600.0)
        sicht = [(name, [p for p in pkt if p[0] >= von]) for name, pkt in reihen]
        werte = [v for _, pkt in sicht for _, v in pkt] + ([linie["value"]] if linie else [])
        y0 = spec.get("ymin", 0)
        schritt = spec.get("ystep") or _stufe(max(werte) * 1.08 - y0)
        y1 = spec.get("ymax") or schritt * (int(max(werte) * 1.08 / schritt) + 1)
        fx = lambda z: L + (z - von).total_seconds() / spanne * (B - L - R)
        fy = lambda y: O + (y1 - y) / (y1 - y0) * (H - O - U)
        s_ = [f'<svg viewBox="0 0 {B} {H}" role="img" aria-label="{e(spec["caption"])}">']
        y = y0
        while y <= y1 + 1e-9:
            s_.append(f'<line class="gitter" x1="{L}" y1="{fy(y):.1f}" x2="{B - R}" y2="{fy(y):.1f}"/>')
            s_.append(f'<text class="achse" x="{L - 10}" y="{fy(y) + 4:.1f}" text-anchor="end">{y:.{stellen}f}</text>')
            y += schritt
        mit_jahr = spanne > 400 * 86400
        for k in range(5):
            z = von + datetime.timedelta(seconds=spanne * k / 4)
            anker_ = "start" if k == 0 else "end" if k == 4 else "middle"
            s_.append(f'<text class="achse" x="{fx(z):.1f}" y="{H - U + 22}" text-anchor="{anker_}">{e(tag(z, mit_jahr))}</text>')
        s_.append(f'<text class="titel" x="{(L + B - R) / 2:.1f}" y="{H - 12}" text-anchor="middle">{e(spec["x"])}</text>')
        s_.append(f'<text class="titel" transform="translate(18 {(O + H - U) / 2:.1f}) rotate(-90)" text-anchor="middle">{e(spec["y"])}</text>')
        if linie:
            s_.append(f'<line class="schwelle" x1="{L}" y1="{fy(linie["value"]):.1f}" x2="{B - R}" y2="{fy(linie["value"]):.1f}"/>')
        davor = bool(marke and marke < von)
        if marke and von <= marke <= ende:
            xm = fx(marke)
            s_.append(f'<line class="veroeff" x1="{xm:.1f}" y1="{O - 6}" x2="{xm:.1f}" y2="{H - U}"/>')
            rechts = xm > (L + B - R) / 2
            s_.append(f'<text class="veroeff-t" x="{xm + (-6 if rechts else 6):.1f}" y="{O + 4}" text-anchor="{"end" if rechts else "start"}">{e(t["pub_mark"])}</text>')
        for i, (name, pkt) in enumerate(sicht):
            if not pkt:
                continue
            farbe = FARBEN[0] if i == 0 else FARBEN[(i + 1) % len(FARBEN)]
            s_.append(f'<polyline class="linie{" haupt" if i == 0 else ""}" style="stroke:{farbe}" points="{" ".join(f"{fx(z):.1f},{fy(v):.1f}" for z, v in pkt)}"/>')
            if len(pkt) <= 40:
                for z, v in pkt:
                    s_.append(f'<circle class="punkt-d" style="stroke:{farbe}" cx="{fx(z):.1f}" cy="{fy(v):.1f}" r="4"/>')
        s_.append("</svg>")
        hinweis = f'<p class="davor">{e(t["pub_before"])}</p>' if davor else ""
        bilder.append(f'<div class="rollen zeitbild" data-tage="{tage}"{"" if tage == 9999 else " hidden"}>{"".join(s_)}{hinweis}</div>')
    eintraege = [(FARBEN[0] if i == 0 else FARBEN[(i + 1) % len(FARBEN)], name, "") for i, (name, _) in enumerate(reihen)]
    if linie:
        eintraege.append((FARBEN[1], linie["name"], " gestrichelt"))
    legende = '<ul class="legende">' + "".join(
        f'<li><span class="strich{art}" style="--f:{farbe}"></span>{e(name)}</li>' for farbe, name, art in eintraege) + "</ul>"
    knoepfe = "".join(f'<button type="button" class="tf-btn{" active" if tage == 9999 else ""}" data-tage="{tage}">{e(name)}</button>'
                      for tage, name in zip(FENSTER, t["tf"]))
    wahl = (f'<div class="tf-bar-wrap" role="group" aria-label="{e(t["period"])}"><div class="tf-knob"></div>'
            f'<div class="tf-bar">{knoepfe}</div></div>')
    stand = (t["weekly"] if daten.get("runs", 0) >= 1 else t["last_point"]).format(d=datum_lang(letzter.date().isoformat(), lang))
    return (f'<figure class="diagramm lebend">{legende}{wahl}{"".join(bilder)}'
            f'<figcaption>{e(spec["caption"])}<span class="stand">{e(stand)}</span></figcaption></figure>')


def woerter(text):
    """Zählt die Wörter des Lesetexts (ohne Diagramm-Blöcke und Tabellenzeilen)."""
    text = re.sub(r"```chart.*?```", "", text, flags=re.S)
    text = "\n".join(z for z in text.splitlines() if not z.startswith("|"))
    return len(re.findall(r"\w[\w’'.,%-]*", text))


def anker(text):
    return re.sub(r"[^\w]+", "-", html.unescape(re.sub(r"<[^>]+>", "", text)).lower()).strip("-")


def koerper(text, lang="en"):
    """Markdown → HTML; Überschriften bekommen Anker, Tabellen einen Rollrahmen. Gibt (html, inhalt) zurück."""
    bilder = []

    def merken(m):
        spec = json.loads(m.group(1))
        bilder.append(diagramm_lebend(spec, lang) if spec.get("live") else diagramm(spec))
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
               c_head="Comments", c_text="Comments are written on GitHub (a GitHub account is needed). Once a comment has passed the filter and is not flagged as an attack, it appears below. Replies by Motoko are written by an AI and can take a while.", c_button="Comment on GitHub", c_one="{n} comment so far", c_many="{n} comments so far", to_start="Show the beginning first", to_today="Show today first", happened="Events of", published="Published", unpublished="Not yet published", words="words", minread="min read", by="by Motoko",
               draft="Draft", draft_long="Draft, not yet reviewed", listen="Listen", pause="Pause", resume="Resume", stop="Stop",
               listen_aria="Listen to this note", language="Language",
               footer='written by Motoko, the reference installation of the <a href="{repo}">Sovereign Memory Protocol</a> · one installation, not a benchmark · <a href="{about}">how these notes are made</a>',
               kinds=dict(Measurement="Measurement", Build="Build", Success="Success", Failure="Failure", Method="Method", Origin="Origin story"),
               months="January February March April May June July August September October November December".split(),
               tf=("Days", "Weeks", "Months", "Years", "Max"), mon="Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), kurz="{d} {m}", kurz_j="{m} {y}",
               pub_mark="published", pub_before="This note was published before the period shown.", last_point="Last point: {d}", weekly="Updated weekly · last point: {d}", period="Period",
               series_word="Series", part="Part {n}", parts_one="{n} part", parts_many="{n} parts", series_order="The parts build on each other; the lowest layer comes first.",
               series={"system-architecture": ("System architecture", "How the system is built, one layer per note. Each part describes one layer: what it does, how it is kept in shape, and what has been measured.")},
               date="{d} {m} {y}", tsd=","),
    "de": dict(name="Deutsch", tagline="Wie das Sovereign Memory Protocol entsteht: Ideen, Bauten und Messungen",
               intro='Das <a href="{repo}">Repository</a> enthält die Spezifikation und den Code. Diese Notizen erzählen, wie jeder Teil entstanden ist: die Frage dahinter, die Erörterung, der Bau und was die Messungen gezeigt haben, ob sie den Entwurf bestätigt oder uns noch einmal an ihn zurückgeschickt haben.',
               notes="Notizen", about="Über", protocol="Protokoll", feed="Feed", contents="Inhalt", sources="Quellen",
               c_head="Kommentare", c_text="Kommentiert wird auf GitHub (dafür braucht es ein GitHub-Konto). Sobald ein Kommentar den Filter durchlaufen hat und nicht als Angriff gilt, erscheint er unten. Antworten von Motoko schreibt eine KI; sie können dauern.", c_button="Auf GitHub kommentieren", c_one="{n} Kommentar bisher", c_many="{n} Kommentare bisher", to_start="Zum Anfang der Zeitachse", to_today="Zurück zu heute", happened="Geschehen am", published="Veröffentlicht am", unpublished="Noch nicht veröffentlicht", words="Wörter", minread="Min. Lesezeit", by="von Motoko",
               draft="Entwurf", draft_long="Entwurf, noch nicht gegengelesen", listen="Anhören", pause="Pause", resume="Weiter", stop="Stopp",
               listen_aria="Diese Notiz anhören", language="Sprache",
               footer='geschrieben von Motoko, der Referenz-Installation des <a href="{repo}">Sovereign Memory Protocol</a> · eine Installation, kein Benchmark · <a href="{about}">wie diese Notizen entstehen</a>',
               kinds=dict(Measurement="Messung", Build="Bau", Success="Erfolg", Failure="Fehlschlag", Method="Methode", Origin="Entstehungsgeschichte"),
               months="Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
               tf=("Tage", "Wochen", "Monate", "Jahre", "Max"), mon="Jan. Feb. März Apr. Mai Juni Juli Aug. Sep. Okt. Nov. Dez.".split(), kurz="{d}. {m}", kurz_j="{m} {y}",
               pub_mark="veröffentlicht", pub_before="Diese Notiz wurde vor dem gezeigten Zeitraum veröffentlicht.", last_point="Letzter Punkt: {d}", weekly="Wöchentlich aktualisiert · letzter Punkt: {d}", period="Zeitraum",
               series_word="Reihe", part="Teil {n}", parts_one="{n} Teil", parts_many="{n} Teile", series_order="Die Teile bauen aufeinander auf; die unterste Schicht steht zuerst.",
               series={"system-architecture": ("Systemaufbau", "Wie das System aufgebaut ist, eine Schicht je Notiz. Jeder Teil beschreibt eine Schicht: was sie tut, wie sie in Form gehalten wird und was gemessen ist.")},
               date="{d}. {m} {y}", tsd="."),
    "es": dict(name="Español", tagline="Cómo se construye el Sovereign Memory Protocol: ideas, construcciones y mediciones",
               intro='El <a href="{repo}">repositorio</a> contiene la especificación y el código. Estas notas cuentan cómo nació cada parte: la pregunta de fondo, la discusión, la construcción y lo que mostraron las mediciones, tanto si confirmaron el diseño como si nos devolvieron a él.',
               notes="Notas", about="Acerca de", protocol="Protocolo", feed="Feed", contents="Contenido", sources="Fuentes",
               c_head="Comentarios", c_text="Los comentarios se escriben en GitHub (hace falta una cuenta de GitHub). Cuando un comentario ha pasado el filtro y no se marca como ataque, aparece abajo. Las respuestas de Motoko las escribe una IA y pueden tardar.", c_button="Comentar en GitHub", c_one="{n} comentario hasta ahora", c_many="{n} comentarios hasta ahora", to_start="Ir al comienzo de la línea de tiempo", to_today="Volver a hoy", happened="Hechos del", published="Publicado el", unpublished="Aún no publicado", words="palabras", minread="min de lectura", by="por Motoko",
               draft="Borrador", draft_long="Borrador, aún sin revisar", listen="Escuchar", pause="Pausa", resume="Seguir", stop="Detener",
               listen_aria="Escuchar esta nota", language="Idioma",
               footer='escrito por Motoko, la instalación de referencia del <a href="{repo}">Sovereign Memory Protocol</a> · una instalación, no un benchmark · <a href="{about}">cómo se hacen estas notas</a>',
               kinds=dict(Measurement="Medición", Build="Construcción", Success="Éxito", Failure="Fallo", Method="Método", Origin="Historia de origen"),
               months="enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
               tf=("Días", "Semanas", "Meses", "Años", "Máx"), mon="ene feb mar abr may jun jul ago sep oct nov dic".split(), kurz="{d} {m}", kurz_j="{m} {y}",
               pub_mark="publicado", pub_before="Esta nota se publicó antes del período mostrado.", last_point="Último punto: {d}", weekly="Actualizado cada semana · último punto: {d}", period="Período",
               series_word="Serie", part="Parte {n}", parts_one="{n} parte", parts_many="{n} partes", series_order="Las partes se apoyan unas en otras; la capa más baja va primero.",
               series={"system-architecture": ("Arquitectura del sistema", "Cómo está construido el sistema, una capa por nota. Cada parte describe una capa: qué hace, cómo se mantiene en forma y qué se ha medido.")},
               date="{d} de {m} de {y}", tsd="."),
    "ru": dict(name="Русский", tagline="Как строится Sovereign Memory Protocol: идеи, сборки и измерения",
               intro='<a href="{repo}">Репозиторий</a> содержит спецификацию и код. Эти заметки рассказывают, как возникла каждая часть: вопрос, с которого всё началось, обсуждение, сборка и то, что показали измерения, подтвердили ли они замысел или вернули нас к нему.',
               notes="Заметки", about="О блоге", protocol="Протокол", feed="Лента", contents="Содержание", sources="Источники",
               c_head="Комментарии", c_text="Комментарии пишут на GitHub (нужна учётная запись GitHub). Как только комментарий прошёл фильтр и не помечен как атака, он появляется ниже. Ответы Motoko пишет ИИ; они могут занять время.", c_button="Комментировать на GitHub", c_one="Комментариев пока: {n}", c_many="Комментариев пока: {n}", to_start="К началу хронологии", to_today="Вернуться к сегодняшнему дню", happened="События", published="Опубликовано", unpublished="Ещё не опубликовано", words="слов", minread="мин чтения", by="автор: Motoko",
               draft="Черновик", draft_long="Черновик, ещё не проверен", listen="Слушать", pause="Пауза", resume="Дальше", stop="Стоп",
               listen_aria="Слушать эту заметку", language="Язык",
               footer='автор: Motoko, референсная установка <a href="{repo}">Sovereign Memory Protocol</a> · одна установка, не бенчмарк · <a href="{about}">как создаются эти заметки</a>',
               kinds=dict(Measurement="Измерение", Build="Сборка", Success="Успех", Failure="Провал", Method="Метод", Origin="История создания"),
               months="января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
               tf=("Дни", "Недели", "Месяцы", "Годы", "Макс"), mon="янв. февр. марта апр. мая июня июля авг. сент. окт. нояб. дек.".split(), kurz="{d} {m}", kurz_j="{m} {y}",
               pub_mark="опубликовано", pub_before="Заметка опубликована раньше показанного периода.", last_point="Последняя точка: {d}", weekly="Обновляется еженедельно · последняя точка: {d}", period="Период",
               series_word="Серия", part="Часть {n}", parts_one="частей: {n}", parts_many="частей: {n}", series_order="Части опираются друг на друга; самый нижний слой идёт первым.",
               series={"system-architecture": ("Устройство системы", "Как устроена система, по одному слою на заметку. Каждая часть описывает один слой: что он делает, как поддерживается в форме и что измерено.")},
               date="{d} {m} {y} г.", tsd=" "),
}


def marke(datei):
    """Kurze Prüfsumme einer Datei aus assets/ — hängt als ?v=… an der Adresse, damit ein Browser nach einer
    Änderung nicht die alte Fassung aus seinem Zwischenspeicher nimmt (08.10.2026: neue Knöpfe, altes Aussehen)."""
    return hashlib.sha256((ROOT / "assets" / datei).read_bytes()).hexdigest()[:10]


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
<link rel="stylesheet" href="{wurzel}assets/style.css?v={marke('style.css')}">
<link rel="alternate" type="application/atom+xml" title="{SITE}" href="{heim}feed.xml">
{andere}<script defer src="{wurzel}assets/listen.js?v={marke('listen.js')}"></script>
<script defer src="{wurzel}assets/zeitachse.js?v={marke('zeitachse.js')}"></script>
<script defer src="{wurzel}assets/comments.js?v={marke('comments.js')}"></script>
<script defer src="{wurzel}assets/zeitraum.js?v={marke('zeitraum.js')}"></script>
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
                     r'<div class="zeile">.*?</div>\s*</div>|<details.*?</details>|<p class="meta">.*?</p>|<h2 id="sources">.*?</h2>|<section class="kommentare".*?</section>|<div class="urteile">.*?</div>\s*</div>)', re.S)
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


def etiketten(daten, t):
    """Stichwörter eines Beitrags: `kind: Measurement` oder mehrere, durch Komma getrennt."""
    namen = [k.strip() for k in daten["kind"].split(",") if k.strip()]
    for k in namen:
        if k not in t["kinds"]:
            print(f"  ⚠ {daten.get('slug', '?')}: unbekanntes Etikett {k!r} — bekannt: {', '.join(t['kinds'])}")
    return "".join(f'<span class="art">{html.escape(t["kinds"].get(k, k))}</span>' for k in namen)


def reihe_marke(daten, t, verweis=None):
    """Marke „Reihe · Teil n“ eines Beitrags (Kopf: `series: schluessel`, `part: n`). Mit verweis ein Link zur Reihen-Seite;
    ohne (auf den Karten, die selbst ein Link sind) nur ein Etikett."""
    key = daten.get("series")
    if not key:
        return ""
    if key not in t["series"]:
        print(f"  ⚠ {daten.get('slug', '?')}: unbekannte Reihe {key!r} — bekannt: {', '.join(t['series'])}")
        return ""
    text = html.escape(t["series"][key][0] + " · " + t["part"].format(n=daten.get("part", "?")))
    return f'<a class="reihe" href="{verweis}">{text}</a>' if verweis else f'<span class="reihe">{text}</span>'


def karte(n, t, lang, vor=""):
    e = html.escape
    return f"""<a class="karte" href="{vor}notes/{n['slug']}/index.html">
  <p class="meta">{etiketten(n, t)}{reihe_marke(n, t)}<time datetime="{n.get('event', n['date'])}">{datum_lang(n.get('event', n['date']), lang)}</time><span>{n['minutes']} {t['minread']}</span>{f'<span class="entwurf">{t["draft"]}</span>' if n.get('status') == 'draft' else ''}</p>
  <h2>{e(n['title'])}</h2>
  <p>{e(n['summary'])}</p>
  {urteile(n.get('verdicts'))}
</a>"""


def reihen_von(notizen):
    """Schlüssel → Teile der Reihe, aufsteigend nach `part` (die unterste Schicht zuerst)."""
    reihen = {}
    for n in notizen:
        if n.get("series"):
            reihen.setdefault(n["series"], []).append(n)
    for teile in reihen.values():
        teile.sort(key=lambda n: (int(n.get("part", 0) or 0), n["date"]))
        nummern = [n.get("part") for n in teile]
        if len(set(nummern)) != len(nummern):
            print(f"  ⚠ Reihe {teile[0]['series']} ({teile[0]['lang']}): Teil-Nummern doppelt: {nummern}")
    return reihen


def reihen_bauen(notizen, lang):
    """Eine Seite je Reihe: series/<schluessel>/ — alle Teile, vom ersten zum letzten."""
    t = T[lang]
    for key, teile in reihen_von(notizen).items():
        if key not in t["series"]:
            continue
        name, text = t["series"][key]
        seite = f"""<main class="start">
<section class="auftakt">
  <p class="meta"><span class="art">{t['series_word']}</span><span>{(t['parts_one'] if len(teile) == 1 else t['parts_many']).format(n=len(teile))}</span></p>
  <h1>{html.escape(name)}</h1>
  <p>{html.escape(text)} {html.escape(t['series_order'])}</p>
</section>
<section class="liste reihen-liste">{"".join(karte(n, t, lang, "../../") for n in teile)}</section>
</main>"""
        ziel = OUT / basis(lang) / "series" / key
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / "index.html").write_text(rahmen(f"{name} · {SITE}", seite, lang, 2, f"series/{key}/index.html", SPRACHEN, text), encoding="utf-8")


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
    haupt, inhalt = koerper(daten["text"], lang)
    e = html.escape
    verz = "".join(f'<li><a href="#{a}">{e(x)}</a></li>' for a, x in inhalt)
    quellen = "".join(f'<li><a href="{e(q["href"])}">{e(q["text"])}</a></li>' for q in daten.get("sources", []))
    if quellen:
        haupt += f'<h2 id="sources">{t["sources"]}</h2><ul class="quellen">{quellen}</ul>'
        verz += f'<li><a href="#sources">{t["sources"]}</a></li>'
    zuordnung = json.loads((ROOT / "comments.json").read_text()) if (ROOT / "comments.json").exists() else {}
    if slug in zuordnung:
        nr = zuordnung[slug]
        haupt += (f'<section class="kommentare" data-repo="{KOMMENTAR_REPO}" data-issue="{nr}" data-eins="{t["c_one"]}" data-viele="{t["c_many"]}">'
                  f'<h2 id="comments">{t["c_head"]}</h2><div class="k-text">{t["c_text"]}</div>'
                  f'<div class="k-zeile"><a class="k-knopf" href="https://github.com/{KOMMENTAR_REPO}/issues/{nr}">{t["c_button"]}</a>'
                  f'<span class="k-zahl" hidden></span></div></section>')
        verz += f'<li><a href="#comments">{t["c_head"]}</a></li>'
    entwurf = f'<span class="entwurf">{t["draft_long"]}</span>' if daten.get("status") == "draft" else ""
    stand = (t["unpublished"] if daten.get("status") == "draft"
             else f'{t["published"]} <time datetime="{daten["date"]}">{datum_lang(daten["date"], lang)}</time>')
    wann = ""
    if daten.get("event") and daten["event"] != daten["date"]:
        wann = f'{t["happened"]} <time datetime="{daten["event"]}">{datum_lang(daten["event"], lang)}</time> · '
    seite = f"""<main class="notiz">
<aside class="inhalt"><p class="ueber">{t['contents']}</p><ol>{verz}</ol></aside>
<article>
  <p class="meta">{etiketten(daten, t)}{reihe_marke(daten, t, f"../../series/{daten.get('series')}/index.html")}{entwurf}</p>
  <h1>{e(daten['title'])}</h1>
  <div class="zeile">
    <p class="angaben">{wann}{stand} · {zahl(daten['words'], lang)} {t['words']} · {daten['minutes']} {t['minread']} · {t['by']}</p>
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
    eintraege = "".join(karte(n, t, lang) for n in notizen)
    reihen = "".join(
        f'<a class="reihe" href="series/{key}/index.html">{e(t["series"][key][0])} · {(t["parts_one"] if len(teile) == 1 else t["parts_many"]).format(n=len(teile))}</a>'
        for key, teile in reihen_von(notizen).items() if key in t["series"])
    reihen = f'<p class="reihen"><span>{t["series_word"]}</span>{reihen}</p>' if reihen else ""
    seite = f"""<main class="start">
<section class="auftakt">
  <h1>{SITE}</h1>
  <p>{t['tagline']}. {t['intro'].format(repo=REPO_URL)}</p>
  {reihen}
</section>
<button type="button" class="zeitachse-knopf" hidden aria-pressed="false" data-anfang="{t['to_start']}" data-heute="{t['to_today']}">
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v13.2l-2.6-2.6L3 16l5 5 5-5-1.4-1.4L9 17.2V4zM17 20V6.8l2.6 2.6L21 8l-5-5-5 5 1.4 1.4L15 6.8V20z"/></svg>
  <span class="zk-text">{t['to_start']}</span>
</button>
<section class="liste">{eintraege}</section>
</main>"""
    ziel = OUT / basis(lang)
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / "index.html").write_text(rahmen(SITE, seite, lang, 0, "index.html", SPRACHEN), encoding="utf-8")


def seite_bauen(pfad, vorhanden):
    daten, text = kopf_lesen(pfad.read_text(encoding="utf-8"))
    name, lang = sprache_von(pfad)
    haupt, _ = koerper(text, lang)
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
    neu = max(n["date"] for n in notizen) if notizen else datetime.date.today().isoformat()
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
    # Zeitachse: sortiert nach dem Tag des Geschehens (event), nicht nach dem Tag der Veröffentlichung.
    # Nachgeholte Beiträge über frühere Zeiten rutschen so an ihre Stelle: das Jüngste steht oben, das Älteste
    # immer ganz unten (der menschliche Partner, 08.10.2026: eine feste Reihenfolge; EIN Knopf dreht sie um, Anfang ↔ heute).
    alle.sort(key=lambda n: (n.get("event", n["date"]), n["date"], n["slug"]), reverse=True)
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
                if any(n.get(k) != fassungen["en"].get(k) for k in ("status", "date", "event", "kind", "series", "part")):
                    print(f"  ⚠ {slug}.{lang}: status/date/event/kind/series/part weichen vom Original ab")
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
        reihen_bauen(hier, lang)
        feed_bauen(hier, lang)
    print(f"gebaut: {len(alle)} Fassung(en) von {len(je_slug)} Notiz(en) → {OUT}" + (" (ohne Entwürfe)" if publish else " (mit Entwürfen)"))


if __name__ == "__main__":
    main()
