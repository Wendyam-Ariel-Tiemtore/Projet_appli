// Analyste académique : comportements minimes de l'interface (aucun appel réseau externe).
(function () {
  "use strict";

  // Aperçu exact de la requête bibliographique : seuls ces mots-clés seront transmis.
  var mots = document.getElementById("keywords");
  var apercu = document.getElementById("apercu-requete");
  function nettoyer(k) {
    return k.replace(/\S+@\S+/g, "").replace(/\d{5,}/g, "").replace(/[^\p{L}\p{N}\s\-'’]/gu, " ").trim();
  }
  function majApercu() {
    if (!mots || !apercu) return;
    var parts = mots.value.split(",").map(nettoyer).filter(function (k) { return k.length > 1 && k.length <= 80; });
    apercu.textContent = parts.length ? parts.join(" ") : "(aucun mot-clé)";
  }
  if (mots) { mots.addEventListener("input", majApercu); majApercu(); }

  // Consentement obligatoire pour la rédaction par Claude
  var radios = document.querySelectorAll('input[name="llm"]');
  var consent = document.getElementById("bloc-consentement");
  function majConsent() {
    if (!consent) return;
    var choisi = document.querySelector('input[name="llm"]:checked');
    consent.hidden = !(choisi && choisi.value === "claude");
  }
  radios.forEach(function (r) { r.addEventListener("change", majConsent); });
  majConsent();

  // Présentation : options visibles seulement si demandée ; valeurs par défaut propres à chaque type
  var presActive = document.getElementById("pres_active");
  var blocPres = document.getElementById("bloc-presentation");
  if (presActive && blocPres) {
    presActive.addEventListener("change", function () { blocPres.hidden = !presActive.checked; });
  }
  document.querySelectorAll('input[name="pres_genre"]').forEach(function (r) {
    r.addEventListener("change", function () {
      ["duree", "deroule", "niveau", "visuels"].forEach(function (k) {
        var champ = document.getElementById("pres_" + k);
        if (champ) champ.value = r.getAttribute("data-" + k);
      });
      var ann = document.getElementById("pres_annexes");
      if (ann) ann.checked = r.getAttribute("data-annexes") === "oui";
    });
  });

  // Suivi de l'analyse en cours, sans rechargement complet
  var suivi = document.getElementById("suivi");
  if (suivi) {
    var url = suivi.getAttribute("data-url");
    var barre = document.getElementById("barre");
    var msg = document.getElementById("message-etat");
    var t = setInterval(function () {
      fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (e) {
          if (barre) barre.value = e.progression;
          if (msg) msg.textContent = e.message;
          if (e.statut !== "en_cours") { clearInterval(t); window.location.reload(); }
        })
        .catch(function () { /* réessai au prochain intervalle */ });
    }, 2500);
  }

  // Confirmation avant les actions destructrices
  document.querySelectorAll("form[data-confirmer]").forEach(function (f) {
    f.addEventListener("submit", function (ev) {
      if (!window.confirm(f.getAttribute("data-confirmer"))) ev.preventDefault();
    });
  });

  // Application installable : enregistrement du service worker (contextes sécurisés uniquement)
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () { /* facultatif */ });
    });
  }
})();
