const CACHE_NAME = 'viernes-pwa-cache-v2';
const ASSETS_TO_CACHE = [
  '/',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

// Install Service Worker and cache essential assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Caching App Shell and Assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate Service Worker and clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('[Service Worker] Clearing Old Cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Intercept - serve cached resources where appropriate
self.addEventListener('fetch', (event) => {
  // Only handle local HTTP/HTTPS requests (avoid chrome-extension/etc.)
  if (!event.request.url.startsWith(self.location.origin)) {
    return;
  }

  // Skip WebSocket connections and audio uploads/POST requests
  if (event.request.url.includes('/ws') || event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Fetch in background to update cache (Stale-While-Revalidate)
        fetch(event.request).then((networkResponse) => {
          if (networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, networkResponse);
            });
          }
        }).catch(() => {
          // Ignore background fetch errors
        });
        return cachedResponse;
      }

      return fetch(event.request).then((networkResponse) => {
        // Cache new successful GET requests dynamically
        if (networkResponse.status === 200 && event.request.method === 'GET') {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      }).catch((err) => {
        console.error('[Service Worker] Fetch failed:', err);
        // If offline and request is for page, return cached root
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
      });
    })
  );
});
