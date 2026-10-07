// Vorlesen mit der Sprachausgabe des Browsers (Web Speech API).
// Kein Server, kein fremder Dienst: die Stimme kommt vom Gerät des Lesers.
// Gelesen wird Absatz für Absatz; Tabellen und Diagramme werden übersprungen.
(function () {
  "use strict";
  var kasten = document.querySelector(".vorlesen");
  var artikel = document.querySelector("article");
  if (!kasten || !artikel || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;

  var synth = window.speechSynthesis;
  var start = kasten.querySelector(".v-start");
  var stopp = kasten.querySelector(".v-stopp");
  var text = kasten.querySelector(".v-text");
  var teile = [];
  var stelle = 0;
  var zustand = "aus"; // aus | liest | pause

  function sammeln() {
    var wahl = "h1, .kurz, h2, h3, p, li";
    return Array.prototype.filter.call(artikel.querySelectorAll(wahl), function (el) {
      if (el.closest("figure, .tabelle, .inhalt-klein, .meta, .zeile, .urteile, .quellen")) return false;
      return el.textContent.trim().length > 0;
    });
  }

  function stimme() {
    var alle = synth.getVoices();
    var en = alle.filter(function (v) { return /^en(-|_|$)/i.test(v.lang); });
    return en.filter(function (v) { return v.localService; })[0] || en[0] || null;
  }

  function zeigen() {
    kasten.dataset.zustand = zustand;
    text.textContent = zustand === "liest" ? "Pause" : zustand === "pause" ? "Resume" : "Listen";
    stopp.hidden = zustand === "aus";
  }

  function markieren(el) {
    var alt = artikel.querySelector(".wird-gelesen");
    if (alt) alt.classList.remove("wird-gelesen");
    if (el) {
      el.classList.add("wird-gelesen");
      var r = el.getBoundingClientRect();
      if (r.top < 80 || r.bottom > window.innerHeight - 80) el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  function weiter() {
    if (zustand !== "liest") return;
    if (stelle >= teile.length) { beenden(); return; }
    var el = teile[stelle];
    var u = new SpeechSynthesisUtterance(el.textContent.replace(/\s+/g, " ").trim());
    var v = stimme();
    if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-US"; }
    u.rate = 1;
    u.onend = function () { if (zustand === "liest") { stelle += 1; weiter(); } };
    u.onerror = function (e) { if (e.error !== "interrupted" && e.error !== "canceled") beenden(); };
    markieren(el);
    synth.speak(u);
  }

  function beenden() {
    zustand = "aus";
    stelle = 0;
    synth.cancel();
    markieren(null);
    zeigen();
  }

  start.addEventListener("click", function () {
    if (zustand === "aus") {
      teile = sammeln();
      stelle = 0;
      zustand = "liest";
      synth.cancel();
      weiter();
    } else if (zustand === "liest") {
      zustand = "pause";
      synth.pause();
    } else {
      zustand = "liest";
      synth.resume();
      // Manche Browser nehmen nach einer Pause nicht wieder auf: dann den Absatz neu beginnen.
      setTimeout(function () { if (zustand === "liest" && !synth.speaking) weiter(); }, 400);
    }
    zeigen();
  });
  stopp.addEventListener("click", beenden);
  window.addEventListener("pagehide", function () { synth.cancel(); });

  kasten.hidden = false;
  zeigen();
})();
