// Date-abase Service Worker
// Caches static assets for offline/fast load; all API/page requests go to network.

const CACHE = 'dateabase-v1';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/manifest.json',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Network-first for HTML pages, API calls, uploads
  if (event.request.mode === 'navigate' ||
      url.pathname.startsWith('/auth/') ||
      url.pathname.startsWith('/uploads/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Cache-first for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(cache => cache.put(event.request, clone));
        return resp;
      }))
    );
    return;
  }

  // Default: network
  event.respondWith(fetch(event.request));
});
