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

// Public keys for bundle signature verification (security/signed-bundles).
//
// The SW refuses to install a new shell unless `/manifest.sig` verifies
// against the appropriate public key for the current origin. The
// signature covers `/manifest.json`, which itself lists every shell
// file's SHA-384 — precacheVerified re-hashes each file before caching.
//
// PROD_PUBLIC_KEY_HEX is the maintainer's ECDSA P-256 public key (raw
// uncompressed point, 130 hex chars). Until the maintainer has run
// `python scripts/keygen_signing_key.py` and replaced the placeholder
// below, prod installs WILL FAIL signature verification by design —
// old SW continues serving the old shell, no app-visible break.
// See docs/DevOps.md § Signing keys and bundle verification.
//
// DEV_PUBLIC_KEY_HEX is the test key from tests/fixtures/. Accepted
// only on http://localhost(:port) and http://127.0.0.1(:port) origins.
// tests/fixtures/README.md explains why a "private" test key in git
// is not a vulnerability (origin gate keeps it inert in production).
const PROD_PUBLIC_KEY_HEX = '__PROD_PUBLIC_KEY_HEX__';
const DEV_PUBLIC_KEY_HEX = '04cf5cb8286e8d401937f48ab1a53c264dac8de3e92b5f66714e7366101f3870bcfc8ec70f930234ba6c97b5af025bb8d585f9b0a1d5c57a774b939f3e07b1dc06';

function isDevOrigin() {
  const o = self.location.origin;
  return o === 'http://localhost' || o.startsWith('http://localhost:') ||
         o === 'http://127.0.0.1' || o.startsWith('http://127.0.0.1:');
}

function selectPublicKeyHex() {
  return isDevOrigin() ? DEV_PUBLIC_KEY_HEX : PROD_PUBLIC_KEY_HEX;
}

function hexToBytes(hex) {
  if (!hex || typeof hex !== 'string' || hex.length % 2 !== 0) return null;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    const b = parseInt(hex.substr(i * 2, 2), 16);
    if (Number.isNaN(b)) return null;
    bytes[i] = b;
  }
  return bytes;
}

function base64ToBytes(b64) {
  const bin = atob((b64 || '').replace(/\s+/g, ''));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bytes.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function bytesToBase64(bytes) {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

async function importVerifyKey() {
  const hex = selectPublicKeyHex();
  const raw = hexToBytes(hex);
  if (!raw || raw.length !== 65 || raw[0] !== 0x04) {
    // 65-byte uncompressed point starts with 0x04. Anything else is
    // either the unsubstituted `__PROD_PUBLIC_KEY_HEX__` placeholder
    // (signing not configured) or a manually corrupted constant.
    throw new Error('sw: public key constant is not a valid raw P-256 point');
  }
  return crypto.subtle.importKey(
    'raw',
    raw,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify']
  );
}

async function fetchAndVerifyManifest() {
  const manifestResp = await fetch('/manifest.json', { cache: 'no-store' });
  if (!manifestResp.ok) {
    throw new Error('sw: manifest fetch failed status=' + manifestResp.status);
  }
  const manifestBuf = await manifestResp.arrayBuffer();

  const sigResp = await fetch('/manifest.sig', { cache: 'no-store' });
  if (!sigResp.ok) {
    throw new Error('sw: signature fetch failed status=' + sigResp.status);
  }
  const sigText = (await sigResp.text()).trim();
  const sigBytes = base64ToBytes(sigText);
  if (sigBytes.length !== 64) {
    throw new Error('sw: signature wrong length ' + sigBytes.length + ' (expected 64)');
  }

  const key = await importVerifyKey();
  const ok = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    sigBytes,
    manifestBuf
  );
  if (!ok) {
    throw new Error('sw: manifest signature did not verify');
  }

  let manifest;
  try {
    manifest = JSON.parse(new TextDecoder().decode(manifestBuf));
  } catch (e) {
    throw new Error('sw: manifest JSON parse failed ' + (e && e.message));
  }
  if (!manifest || typeof manifest !== 'object' || !manifest.files || typeof manifest.files !== 'object') {
    throw new Error('sw: manifest shape invalid');
  }
  return manifest;
}

async function computeSha384(buf) {
  const digest = await crypto.subtle.digest('SHA-384', buf);
  return 'sha384-' + bytesToBase64(new Uint8Array(digest));
}

async function reportSwError(message) {
  // Best-effort post to the client-error sink so a verify-fail surfaces
  // in journald rather than only console. credentials:'omit' because
  // SW install runs without any UI context; the sink doesn't require
  // auth anyway (see deploy/client_error_sanitizer.py).
  try {
    await fetch('/api/client-errors', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      credentials: 'omit',
      keepalive: true,
      body: JSON.stringify({
        events: [{ kind: 'sw', msg: ('bundle verify: ' + String(message)).slice(0, 500) }],
        ua: (self.navigator && self.navigator.userAgent) || '',
        build: CACHE_VERSION,
      }),
    });
  } catch (_) { /* sink may itself be unreachable in some failure modes */ }
}

async function precacheVerified(cache, manifest) {
  const paths = Object.keys(manifest.files);
  const total = paths.length;
  let loaded = 0;
  for (const path of paths) {
    const expectedSri = manifest.files[path];
    const url = '/' + path;
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) {
      throw new Error('sw: precache fetch failed ' + url + ' status=' + resp.status);
    }
    const buf = await resp.arrayBuffer();
    const computedSri = await computeSha384(buf);
    if (computedSri !== expectedSri) {
      throw new Error('sw: hash mismatch ' + path + ' expected=' + expectedSri + ' got=' + computedSri);
    }
    // Re-wrap into a Response so the cached entry preserves the original
    // headers (Cache-Control, Content-Type, etc.) when later served.
    await cache.put(url, new Response(buf, {
      status: resp.status,
      statusText: resp.statusText,
      headers: resp.headers,
    }));
    loaded += 1;
    postCacheProgress({ type: 'sw-cache-progress', url: url, loaded: loaded, total: total });
  }
}

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
  event.waitUntil((async () => {
    try {
      const manifest = await fetchAndVerifyManifest();
      const cache = await caches.open(APP_SHELL_CACHE);
      await precacheVerified(cache, manifest);
      await self.skipWaiting();
    } catch (e) {
      const msg = (e && e.message) || String(e);
      try { console.error('[sw] install failed:', msg); } catch (_) {}
      await reportSwError(msg);
      // Rethrow so the SW install fails, the new SW does not activate,
      // and any old SW continues serving the old shell. Fail-safe.
      throw e;
    }
  })());
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
    // One-time sweep of legacy /images/<slug>.<ext>?v=<build_label>
    // entries. The cache-bust query was retired in this commit; until
    // every installed user activates the new SW, fellows-images-v1
    // continues holding stale duplicates from past deploys (725 / 508
    // ratio observed in production before the fix). No-op once the
    // sweep has run on a given install — new images land at bare URLs
    // and the legacy entries will all have been removed. Safe to leave
    // here permanently.
    let imagesPurged = 0;
    try {
      if (keys.indexOf(IMAGES_CACHE) !== -1) {
        const imageCache = await caches.open(IMAGES_CACHE);
        const reqs = await imageCache.keys();
        for (const req of reqs) {
          // Match any /images/* entry carrying a query string. The only
          // query that ever appeared on these URLs was ?v=<build_label>;
          // matching on '?' keeps the predicate simple and resilient if
          // the form ever varied.
          if (req.url.indexOf('/images/') !== -1 && req.url.indexOf('?') !== -1) {
            const ok = await imageCache.delete(req);
            if (ok) imagesPurged += 1;
          }
        }
      }
    } catch (e) {
      // Non-fatal — quota / private mode / corrupted cache. Activate
      // must still complete so the new app shell takes over.
      try {
        console.warn('[sw] activate: image cache-bust sweep failed', e);
      } catch (_) {}
    }
    await self.clients.claim();
    // Tell the page what we did, regardless of whether anything was
    // deleted. Page logs this to bootDebugLines via the existing SW
    // message handler; future diagnostics dumps then carry a clear
    // record of "activate ran at <ts>, current=<X>, deleted=<list>".
    postCacheProgress({
      type: 'sw-activate-pruned',
      activatedAt: new Date().toISOString(),
      currentCache: APP_SHELL_CACHE,
      deletions: deletions,
      imagesPurged: imagesPurged
    });
    // Also console-log so an operator with DevTools open sees it
    // even if the page-side log channel is disconnected.
    try {
      console.log('[sw] activate: current=', APP_SHELL_CACHE,
        'deletions=', deletions, 'imagesPurged=', imagesPurged);
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
  // sqlite-worker.js carries WORKER_RPC_VERSION, which the page checks
  // against EXPECTED_WORKER_RPC_VERSION on init. Cache-first lets a
  // freshly-network-fetched app.js spawn a stale cached worker during a
  // build-version bump, producing the "Worker version skew" panel even
  // though the disk and server already agree. Other vendor/ assets
  // (sqlite3.js, sqlite3.wasm, jspdf) carry no protocol contract with
  // app.js and stay cache-first.
  if (pathname === '/vendor/sqlite-worker.js') return true;
  return false;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) {
    return;
  }

  // /fellows.db is owned by the sqlite worker's OPFS cache. Double-caching
  // megabytes of DB bytes here would waste quota and create a third place
  // a stale copy can hide; the worker's `fellows.db.meta.json` is the
  // single source of freshness. Pass through to the network unchanged so
  // the worker's `cache: 'no-store'` fetch reaches the server cleanly.
  // Plan: plans/local_first_worker_architecture.md § Phase 3.
  if (url.pathname === '/fellows.db') {
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
