// Sortierung der Startseite: nach der Zeit, von der ein Beitrag erzählt, oder nach dem Tag der Veröffentlichung;
// jeweils das Neueste oder das Älteste zuerst. Ohne Skript gilt die gebaute Reihenfolge (erzählte Zeit, Neuestes oben).
(function () {
  "use strict";
  var leiste = document.querySelector(".sortieren");
  var liste = document.querySelector(".liste");
  if (!leiste || !liste) return;
  var stand = { nach: "event", richtung: "neu" };
  try {
    var alt = JSON.parse(localStorage.getItem("smp-sortierung") || "null");
    if (alt && (alt.nach === "event" || alt.nach === "date") && (alt.richtung === "neu" || alt.richtung === "alt")) stand = alt;
  } catch (e) { /* ohne Speicher geht es auch */ }

  function ordnen() {
    var karten = Array.prototype.slice.call(liste.querySelectorAll(".karte"));
    karten.sort(function (a, b) {
      var x = a.dataset[stand.nach] + a.dataset.event + a.dataset.date;
      var y = b.dataset[stand.nach] + b.dataset.event + b.dataset.date;
      var v = x < y ? -1 : x > y ? 1 : 0;
      return stand.richtung === "neu" ? -v : v;
    });
    karten.forEach(function (k) {
      liste.appendChild(k);
      k.querySelector(".zeit-event").hidden = stand.nach !== "event";
      k.querySelector(".zeit-date").hidden = stand.nach !== "date";
    });
    Array.prototype.forEach.call(leiste.querySelectorAll("button"), function (knopf) {
      var an = knopf.dataset.nach ? knopf.dataset.nach === stand.nach : knopf.dataset.richtung === stand.richtung;
      knopf.setAttribute("aria-pressed", an ? "true" : "false");
    });
    try { localStorage.setItem("smp-sortierung", JSON.stringify(stand)); } catch (e) { /* egal */ }
  }

  leiste.addEventListener("click", function (e) {
    var knopf = e.target.closest("button");
    if (!knopf) return;
    if (knopf.dataset.nach) stand.nach = knopf.dataset.nach;
    if (knopf.dataset.richtung) stand.richtung = knopf.dataset.richtung;
    ordnen();
  });
  leiste.hidden = false;
  ordnen();
})();
