// WatchTheFall Portal Service Worker
const CACHE_NAME = 'wtf-portal-v1';
const ASSETS = [
  '/portal/',
  '/portal/index.html',
  '/portal/static/manifest.json',
  '/portal/static/watermarks/brands.json',
  '/portal/static/js/offline.js'
];

// Install - cache basic assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Fetch - network first, cache fallback
// 8️⃣ PATCH: PWA Service Worker Guarantees Instant Load
// Tell Qoder: "Cache the entire /portal UI so navigating to it is instant even when Render is offline."
self.addEventListener('fetch', (event) => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;
  
  // For portal UI requests, try cache first
  if (event.request.url.includes('/portal/')) {
    event.respondWith(
      caches.match(event.request)
        .then((cachedResponse) => {
          // Return cached response if available
          if (cachedResponse) return cachedResponse;
          
          // Otherwise fetch from network
          return fetch(event.request)
            .then((networkResponse) => {
              // Cache the response for future use
              if (networkResponse.ok) {
                const responseToCache = networkResponse.clone();
                caches.open(CACHE_NAME)
                  .then((cache) => cache.put(event.request, responseToCache));
              }
              return networkResponse;
            })
            .catch(() => {
              // If network fails, return cached index page as fallback
              if (event.request.mode === 'navigate') {
                return caches.match('/portal/');
              }
              return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
            });
        })
        .catch(() => caches.match('/portal/index.html'))  // 8️⃣ PATCH: Fallback to cached index.html
    );
  } else {
    // For other requests, use network first approach
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request))
    );
  }
});
