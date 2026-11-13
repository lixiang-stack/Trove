"use strict";

const SHELL_CACHE = "trove-shell-v1";
const SHELL_ASSETS = [
  "/static/pico.min.css",
  "/static/app.css",
  "/static/htmx.min.js",
  "/static/player.js",
  "/static/ui.js",
  "/static/pwa.js",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      Promise.all(
        SHELL_ASSETS.map((asset) => cache.add(asset).catch(() => undefined)),
      ),
    ).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== SHELL_CACHE)
          .map((key) => caches.delete(key)),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith("/static/")) return;

  // Static asset URLs are versioned with ?v=<asset_version>, so serving a
  // cached copy is safe: a deploy changes the URL. Revalidate in the
  // background. HTML, API responses and media always go to the network and
  // fail offline instead of serving stale data.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});
