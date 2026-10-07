// Ein Knopf auf der Startseite: dreht die Zeitachse um. Gebaut ist „heute oben, Anfang unten“;
// ein Tipp stellt den Anfang nach oben, ein zweiter wieder heute. Die Reihenfolge selbst kommt aus dem Bau.
(function () {
  "use strict";
  var knopf = document.querySelector(".zeitachse-knopf");
  var liste = document.querySelector(".liste");
  if (!knopf || !liste) return;
  var anfangOben = false;
  function drehen() {
    var karten = Array.prototype.slice.call(liste.querySelectorAll(".karte"));
    karten.reverse().forEach(function (k) { liste.appendChild(k); });
    anfangOben = !anfangOben;
    knopf.querySelector(".zk-text").textContent = anfangOben ? knopf.dataset.heute : knopf.dataset.anfang;
    knopf.setAttribute("aria-pressed", anfangOben ? "true" : "false");
  }
  knopf.addEventListener("click", drehen);
  knopf.hidden = false;
})();
