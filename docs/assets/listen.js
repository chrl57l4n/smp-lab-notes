// Vorlesen. Zwei Wege, eine Bedienung:
//  1. Fertige Tonspur (data-ton + data-marken am Kasten): eine MP3 mit Zeitmarken je Absatz.
//  2. Sonst die Sprachausgabe des Browsers (Web Speech API), Absatz für Absatz.
// In beiden Fällen wird der gelesene Absatz hervorgehoben und die Seite läuft mit.
// Gelesen wird, was im Bau ein data-lies bekommen hat; Tabellen und Diagramme bleiben aus.
(function () {
  "use strict";
  var kasten = document.querySelector(".vorlesen");
  var artikel = document.querySelector("article");
  if (!kasten || !artikel) return;

  var start = kasten.querySelector(".v-start");
  var stopp = kasten.querySelector(".v-stopp");
  var text = kasten.querySelector(".v-text");
  var zeit = kasten.querySelector(".v-zeit");
  var teile = Array.prototype.slice.call(artikel.querySelectorAll("[data-lies]"));
  var zustand = "aus"; // aus | liest | pause

  function zeigen() {
    kasten.dataset.zustand = zustand;
    text.textContent = zustand === "liest" ? "Pause" : zustand === "pause" ? "Resume" : "Listen";
    stopp.hidden = zustand === "aus";
  }

  function markieren(el) {
    var alt = artikel.querySelector(".wird-gelesen");
    if (alt === el) return;
    if (alt) alt.classList.remove("wird-gelesen");
    if (el) {
      el.classList.add("wird-gelesen");
      var r = el.getBoundingClientRect();
      if (r.top < 80 || r.bottom > window.innerHeight - 80) el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  function uhr(s) {
    s = Math.max(0, Math.floor(s));
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
  }

  // ── Weg 1: fertige Tonspur ──
  function mitTonspur(adresse, marken) {
    var ton = new Audio();
    ton.preload = "none";
    ton.src = adresse;

    function stelle() {
      var t = ton.currentTime, i = 0;
      while (i + 1 < marken.length && marken[i + 1] <= t + 0.05) i += 1;
      return i;
    }
    ton.addEventListener("timeupdate", function () {
      if (zustand === "aus") return;
      markieren(teile[stelle()]);
      if (zeit) zeit.textContent = uhr(ton.currentTime) + " / " + uhr(ton.duration || 0);
    });
    ton.addEventListener("ended", beenden);
    ton.addEventListener("error", function () { beenden(); text.textContent = "Audio unavailable"; });

    function beenden() {
      zustand = "aus";
      ton.pause();
      ton.currentTime = 0;
      markieren(null);
      if (zeit) zeit.textContent = "";
      zeigen();
    }
    start.addEventListener("click", function () {
      if (zustand === "liest") { zustand = "pause"; ton.pause(); }
      else { zustand = "liest"; ton.play(); }
      zeigen();
    });
    stopp.addEventListener("click", beenden);
    // Antippen eines Absatzes springt dorthin, solange vorgelesen wird.
    artikel.addEventListener("click", function (e) {
      if (zustand === "aus" || e.target.closest("a, button")) return;
      var el = e.target.closest("[data-lies]");
      if (!el) return;
      var i = teile.indexOf(el);
      if (i >= 0) { ton.currentTime = marken[i]; if (zustand === "pause") markieren(el); }
    });
  }

  // ── Weg 2: Sprachausgabe des Browsers ──
  function mitBrowserStimme() {
    var synth = window.speechSynthesis;
    var nr = 0;

    function stimme() {
      var en = synth.getVoices().filter(function (v) { return /^en(-|_|$)/i.test(v.lang); });
      return en.filter(function (v) { return v.localService; })[0] || en[0] || null;
    }
    function weiter() {
      if (zustand !== "liest") return;
      if (nr >= teile.length) { beenden(); return; }
      var el = teile[nr];
      var u = new SpeechSynthesisUtterance(el.textContent.replace(/\s+/g, " ").trim());
      var v = stimme();
      if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-US"; }
      u.onend = function () { if (zustand === "liest") { nr += 1; weiter(); } };
      u.onerror = function (e) { if (e.error !== "interrupted" && e.error !== "canceled") beenden(); };
      markieren(el);
      synth.speak(u);
    }
    function beenden() {
      zustand = "aus";
      nr = 0;
      synth.cancel();
      markieren(null);
      zeigen();
    }
    start.addEventListener("click", function () {
      if (zustand === "aus") { nr = 0; zustand = "liest"; synth.cancel(); weiter(); }
      else if (zustand === "liest") { zustand = "pause"; synth.pause(); }
      else {
        zustand = "liest";
        synth.resume();
        setTimeout(function () { if (zustand === "liest" && !synth.speaking) weiter(); }, 400);
      }
      zeigen();
    });
    stopp.addEventListener("click", beenden);
    window.addEventListener("pagehide", function () { synth.cancel(); });
  }

  var kannSprechen = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  function einschalten() { kasten.hidden = false; zeigen(); }

  if (kasten.dataset.ton && kasten.dataset.marken && window.fetch) {
    fetch(kasten.dataset.marken)
      .then(function (a) { return a.json(); })
      .then(function (d) {
        if (!d.marks || d.marks.length !== teile.length) throw new Error("Zeitmarken passen nicht zur Seite");
        mitTonspur(kasten.dataset.ton, d.marks);
        einschalten();
      })
      .catch(function () { if (kannSprechen) { mitBrowserStimme(); einschalten(); } });
  } else if (kannSprechen) {
    mitBrowserStimme();
    einschalten();
  }
})();
