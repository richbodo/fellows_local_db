// CACHE_VERSION + the FELLOWS_UI_DIAG constant in app.js are placeholders
// substituted at build time by build/build_pwa.py (and at request time by
// the dev server in app/server.py) with the current git short SHA. So
// every build/deploy gets a unique cache name and visible build label
// without needing a hand-maintained chore(version) commit on main. See
// docs/DevOps.md for the routine deploy flow.
const CACHE_VERSION = '__CACHE_VERSION__';
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
  '/vendor/sqlite-worker.js',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-512.png',
  '/vendor/sqlite3.js',
  '/vendor/sqlite3.wasm',
  '/vendor/jspdf-2.5.1.umd.min.js'
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
    // Capture per-key delete results so we can tell, post-hoc, whether
    // the prune fired but didn't actually delete (returns false). The
    // 2026-05-05 incident showed two shell caches coexisting after a
    // build-label rebump even though this handler should have nuked the
    // older one — instrumenting both sides (here + auditShellCaches in
    // app.js) is the path to seeing whether the prune ran at all next
    // time the symptom recurs.
    const deletions = await Promise.all(
      oldShellCaches.map((k) => caches.delete(k).then(
        (ok) => ({ key: k, ok }),
        (err) => ({ key: k, ok: false, error: String(err && err.message || err) })
      ))
    );
    await self.clients.claim();
    // Tell the page what we did, regardless of whether anything was
    // deleted. Page logs this to bootDebugLines via the existing SW
    // message handler; future diagnostics dumps then carry a clear
    // record of "activate ran at <ts>, current=<X>, deleted=<list>".
    postCacheProgress({
      type: 'sw-activate-pruned',
      activatedAt: new Date().toISOString(),
      currentCache: APP_SHELL_CACHE,
      deletions: deletions
    });
    // Also console-log so an operator with DevTools open sees it
    // even if the page-side log channel is disconnected.
    try {
      console.log('[sw] activate: current=', APP_SHELL_CACHE,
        'deletions=', deletions);
    } catch (e) {}
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

// Cache API rejects PUT/POST/DELETE/PATCH at cache.put. Without this guard
// the verify-token / send-unlock / client-errors / logout POSTs all fired
// an unhandled rejection ("Failed to execute 'put' on 'Cache': Request
// method 'POST' is unsupported") on every API call. The response was still
// returned correctly, but the console flood made real errors hard to spot.
// .catch() on the cache write covers quota / private-mode / corrupted-cache
// cases the same way — cache misses are never fatal.
function safeCachePut(cacheName, request, response) {
  if (request.method !== 'GET') return;
  caches.open(cacheName)
    .then((cache) => cache.put(request, response))
    .catch(() => { /* quota / private mode / etc. — non-fatal */ });
}

function cacheFirstInto(request, cacheName) {
  return caches.match(request).then((cached) => {
    if (cached) {
      return cached;
    }
    return fetch(request).then((response) => {
      if (!response || response.status !== 200 || response.type !== 'basic') {
        return response;
      }
      safeCachePut(cacheName, request, response.clone());
      return response;
    });
  });
}

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      if (response && response.ok && response.status === 200) {
        safeCachePut(APP_SHELL_CACHE, request, response.clone());
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
