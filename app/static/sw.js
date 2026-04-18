const CACHE_VERSION = 'v8';
const APP_SHELL_CACHE = `fellows-app-shell-${CACHE_VERSION}`;
// Separate cache so shell-version bumps don't evict the ~34 MB of profile images.
const IMAGES_CACHE = 'fellows-images-v1';

// fellows.db is fetched only after magic-link session (Phase 4); not precached here.
const APP_SHELL_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/sw.js',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-512.png',
  '/vendor/sqlite3.js',
  '/vendor/sqlite3.wasm'
];

function postCacheProgress(payload) {
  self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
    clients.forEach((client) => {
      try {
        client.postMessage(payload);
      } catch (e) {}
    });
  });
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then(async (cache) => {
      const total = APP_SHELL_ASSETS.length;
      let loaded = 0;
      for (let i = 0; i < APP_SHELL_ASSETS.length; i++) {
        const url = APP_SHELL_ASSETS[i];
        const res = await fetch(url);
        if (!res.ok) {
          throw new Error('sw install fetch failed ' + url + ' ' + res.status);
        }
        await cache.put(url, res);
        loaded += 1;
        postCacheProgress({ type: 'sw-cache-progress', url: url, loaded: loaded, total: total });
      }
      await self.skipWaiting();
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    const oldShellCaches = keys.filter(
      (k) => k.startsWith('fellows-app-shell-') && k !== APP_SHELL_CACHE
    );
    await Promise.all(oldShellCaches.map((k) => caches.delete(k)));
    await self.clients.claim();
    // Burn-down: only force-reload controlled windows when we're replacing a
    // prior shell cache. Rescues tabs stuck on stale in-memory app.js from a
    // previous cacheFirst SW. First-time installs skip this.
    if (oldShellCaches.length > 0) {
      const wins = await self.clients.matchAll({ type: 'window' });
      await Promise.all(
        wins.map((w) => {
          try { return w.navigate(w.url); } catch (e) { return null; }
        })
      );
    }
  })());
});

function shellPathNetworkFirst(pathname) {
  if (pathname === '/' || pathname === '/index.html') return true;
  const base = pathname.split('/').pop() || '';
  if (base === 'app.js' || base === 'styles.css' || base === 'sw.js') return true;
  if (base === 'manifest.webmanifest' || base === 'build-meta.json') return true;
  return false;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // HTML/JS/CSS/SW must not be served stale from Cache API — old app.js skipped email gate.
  if (request.mode === 'navigate' || shellPathNetworkFirst(url.pathname)) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Profile images get their own long-lived cache.
  if (url.pathname.startsWith('/images/')) {
    event.respondWith(cacheFirstInto(request, IMAGES_CACHE));
    return;
  }

  event.respondWith(cacheFirstInto(request, APP_SHELL_CACHE));
});

function cacheFirstInto(request, cacheName) {
  return caches.match(request).then((cached) => {
    if (cached) {
      return cached;
    }
    return fetch(request).then((response) => {
      if (!response || response.status !== 200 || response.type !== 'basic') {
        return response;
      }
      const responseToCache = response.clone();
      caches.open(cacheName).then((cache) => {
        cache.put(request, responseToCache);
      });
      return response;
    });
  });
}

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      if (response && response.ok && response.status === 200) {
        const responseClone = response.clone();
        caches.open(APP_SHELL_CACHE).then((cache) => {
          cache.put(request, responseClone);
        });
      }
      return response;
    })
    .catch(() =>
      caches.match(request).then((cached) => {
        if (cached) {
          return cached;
        }
        return new Response('Offline', {
          status: 503,
          statusText: 'Offline'
        });
      })
    );
}
