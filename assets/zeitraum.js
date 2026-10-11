// Fortlaufende Grafiken: Auswahl des Zeitraums (Tage · Wochen · Monate · Jahre · Max).
// Der Bau legt je Zeitraum ein fertiges Bild ab; hier wird nur umgeschaltet und der Knopf verschoben.
// Aussehen und Bewegung der Auswahl: gleitender Knopf über einer Leiste mit fünf Zeiträumen.
(function () {
  "use strict";
  var alle = [];
  Array.prototype.forEach.call(document.querySelectorAll("figure.lebend"), function (bild) {
    var knopf = bild.querySelector(".tf-knob");
    var tasten = Array.prototype.slice.call(bild.querySelectorAll(".tf-btn"));
    var bilder = Array.prototype.slice.call(bild.querySelectorAll(".zeitbild"));
    if (!knopf || !tasten.length) return;
    function schieben() {
      var a = bild.querySelector(".tf-btn.active");
      if (!a) return;
      knopf.style.left = a.offsetLeft + "px";
      knopf.style.width = a.offsetWidth + "px";
    }
    tasten.forEach(function (t) {
      t.addEventListener("click", function () {
        tasten.forEach(function (x) { x.classList.toggle("active", x === t); });
        bilder.forEach(function (b) { b.hidden = b.dataset.tage !== t.dataset.tage; });
        schieben();
      });
    });
    bild.classList.add("bereit");
    schieben();
    alle.push(schieben);
  });
  window.addEventListener("resize", function () { alle.forEach(function (f) { f(); }); });
})();
