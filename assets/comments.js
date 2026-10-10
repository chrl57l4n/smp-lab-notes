// Zeigt unter einem Beitrag die Kommentare aus dem Diskussionsthema auf GitHub.
// FREMDER TEXT ERSCHEINT NUR, WENN ER GEPRÜFT IST: Die Seite rendert einen Kommentar nur, wenn seine
// id UND sein updated_at in assets/comments-approved.json stehen — diese Liste schreibt die Wache auf
// ryzen (blog_kommentar_freigeben.py) aus den Prüf-Urteilen und lässt Angriffe (injection u.ä.) weg.
// Ein nachträglich geänderter Kommentar bekommt ein neues updated_at und fällt heraus, bis er neu
// geprüft ist. Gerendert wird ausschließlich mit textContent (kein innerHTML) — es wird nie etwas
// aus einem Kommentar ausgeführt.
(function () {
  "use strict";
  var kasten = document.querySelector(".kommentare");
  if (!kasten || !window.fetch) return;
  var repo = kasten.dataset.repo, issue = kasten.dataset.issue;
  // Pfad zur Freigabe-Liste aus der eigenen Script-Adresse ableiten (gleicher Ordner,
  // gleiche Tiefe wie comments.js) — unabhängig davon, in welchem Sprach-Unterordner die Seite liegt.
  var skript = document.querySelector('script[src*="assets/comments.js"]');
  var approvedUrl = skript ? skript.getAttribute("src").split("?")[0].replace("comments.js", "comments-approved.json")
                           : "assets/comments-approved.json";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;   // textContent: fremder Text wird nie als HTML gedeutet
    return e;
  }

  Promise.all([
    fetch("https://api.github.com/repos/" + repo + "/issues/" + issue + "/comments?per_page=100")
      .then(function (a) { return a.ok ? a.json() : []; }).catch(function () { return []; }),
    fetch(approvedUrl).then(function (a) { return a.ok ? a.json() : {}; }).catch(function () { return {}; })
  ]).then(function (res) {
    var alle = res[0] || [], frei = (res[1] || {})[issue] || [];
    // Freigabe-Index: id -> updated_at (nur exakte Übereinstimmung wird gezeigt)
    var ok = {};
    frei.forEach(function (f) { ok[f.id] = f.updated_at; });
    var zeigbar = alle.filter(function (c) { return ok[c.id] !== undefined && ok[c.id] === c.updated_at; });

    var zahl = kasten.querySelector(".k-zahl");
    if (zahl) {
      var n = zeigbar.length;
      zahl.textContent = (n === 1 ? kasten.dataset.eins : kasten.dataset.viele).replace("{n}", n);
      zahl.hidden = false;
    }
    if (!zeigbar.length) return;

    var liste = el("ol", "k-liste");
    zeigbar.forEach(function (c) {
      var li = el("li", "k-eintrag");
      var kopf = el("div", "k-kopf");
      kopf.appendChild(el("span", "k-autor", "@" + (c.user && c.user.login ? c.user.login : "?")));
      var d = (c.created_at || "").slice(0, 10);
      if (d) kopf.appendChild(el("span", "k-datum", d));
      li.appendChild(kopf);
      li.appendChild(el("div", "k-körper", c.body || ""));   // textContent, reiner Text
      liste.appendChild(li);
    });
    kasten.appendChild(liste);
  });
})();
