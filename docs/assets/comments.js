// Zeigt unter einem Beitrag, wie viele Kommentare es im Diskussionsthema auf GitHub gibt.
// Die Kommentare selbst werden hier NICHT eingeblendet: fremder Text erscheint auf dieser Seite erst,
// wenn er geprüft ist. Gelesen und geschrieben wird auf GitHub.
(function () {
  "use strict";
  var kasten = document.querySelector(".kommentare");
  if (!kasten || !window.fetch) return;
  fetch("https://api.github.com/repos/" + kasten.dataset.repo + "/issues/" + kasten.dataset.issue)
    .then(function (a) { return a.ok ? a.json() : null; })
    .then(function (d) {
      if (!d || typeof d.comments !== "number") return;
      var z = kasten.querySelector(".k-zahl");
      z.textContent = (d.comments === 1 ? kasten.dataset.eins : kasten.dataset.viele).replace("{n}", d.comments);
      z.hidden = false;
    })
    .catch(function () { /* ohne Zahl geht es auch */ });
})();
