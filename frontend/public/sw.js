const CACHE_NAME = "fut-conversys-shell-v2";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/icons/fut-conversys-logo.png",
  "/icons/favicon-32.png",
  "/icons/apple-touch-icon.png",
  "/icons/fut-conversys-192.png",
  "/icons/fut-conversys-512.png",
  "/icons/fut-conversys-maskable.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/"))),
  );
});
