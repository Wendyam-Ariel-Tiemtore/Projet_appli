// Service worker d'Analyste académique : rend l'application installable et affiche une page claire hors
// connexion. Seules les ressources statiques (styles, script, icônes) sont mises en cache : aucune page
// contenant des données ni aucun document produit n'est jamais conservé sur l'appareil.
"use strict";
var VERSION = "aa-statique-1.3.0";
var STATIQUES = ["/static/style.css", "/static/app.js", "/static/icones/icone-192.png", "/hors-ligne"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(STATIQUES); }).then(function () {
    return self.skipWaiting();
  }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (cles) {
    return Promise.all(cles.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === "navigate") {
    // Pages : toujours le réseau (contenu à jour, jamais mis en cache) ; page d'information hors connexion
    e.respondWith(fetch(req).catch(function () { return caches.match("/hors-ligne"); }));
    return;
  }
  if (url.pathname.indexOf("/static/") === 0) {
    e.respondWith(caches.open(VERSION).then(function (c) {
      return c.match(req).then(function (enCache) {
        var reseau = fetch(req).then(function (r) { if (r.ok) c.put(req, r.clone()); return r; });
        return enCache || reseau;
      });
    }));
  }
});
