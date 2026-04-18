// EHF Fellows directory – two-phase load: list first, then full data in background.
// Detail layout matches reference: table-like rows, purple/grey section headers, two columns.

(function () {
  var DETAIL_PAGE_TITLE = 'Confidential - Fellows Local-Only Directory Development Project';
  var fellowsBySlug = new Map();
  var list = [];
  var displayedList = [];
  var loadingEl = document.getElementById('loading');
  var loadingPanelEl = document.getElementById('loading-panel');
  var bootErrorPanelEl = document.getElementById('boot-error-panel');
  var bootErrorPreEl = document.getElementById('boot-error-pre');
  var authErrorPanelEl = document.getElementById('auth-error-panel');
  var authErrorPreEl = document.getElementById('auth-error-pre');
  var appWrapEl = document.getElementById('app-wrap');
  var connectionBannerEl = document.getElementById('connection-banner');
  var directoryEl = document.getElementById('directory');
  var directoryListEl = document.getElementById('directory-list') || directoryEl;
  var searchInputEl = document.getElementById('search-input');
  var searchStatusEl = document.getElementById('search-status');
  var searchDebounceId = null;
  var nlSearchContainerEl = document.getElementById('nl-search-container');
  var nlSearchInputEl = document.getElementById('nl-search-input');
  var nlSearchButtonEl = document.getElementById('nl-search-button');
  var nlSearchStatusEl = document.getElementById('nl-search-status');
  var detailEl = document.getElementById('detail');
  var fullFellowsCache = null;
  var installLandingEl = document.getElementById('install-landing');
  var installGatePrivateEl = document.getElementById('install-gate-private');
  var unlockEmailFormEl = document.getElementById('unlock-email-form');
  var unlockEmailInputEl = document.getElementById('unlock-email');
  var unlockStatusEl = document.getElementById('unlock-status');
  var installButtonEl = document.getElementById('install-pwa-button');
  var installStatusEl = document.getElementById('install-status');
  var iosHintEl = document.getElementById('install-ios-hint');
  var authDebugPrivateEl = document.getElementById('auth-debug-private');
  var authDebugInstallEl = document.getElementById('auth-debug-install');
  var swUpdateBannerEl = document.getElementById('sw-update-banner');
  var swUpdateReloadEl = document.getElementById('sw-update-reload');
  var siteHeaderEl = document.getElementById('site-header');
  var deferredInstallPrompt = null;
  var directoryDataSource = 'api';
  var dataProvider = null;
  var bootDebugLines = [];
  var authDebugLines = [];
  var swLifecycleLog = [];
  /** Bump when changing diagnostics behavior (shown in Diagnostics panel). */
  var FELLOWS_UI_DIAG = 'diag-2026-04d-sw-trace';

  function logSwLifecycle(event, detail) {
    swLifecycleLog.push({
      t: new Date().toISOString(),
      event: event,
      detail: detail != null ? detail : null
    });
  }

  var FELLOW_COLS = [
    'record_id',
    'slug',
    'name',
    'bio_tagline',
    'fellow_type',
    'cohort',
    'contact_email',
    'key_links',
    'key_links_urls',
    'image_url',
    'currently_based_in',
    'search_tags',
    'fellow_status',
    'gender_pronouns',
    'ethnicity',
    'primary_citizenship',
    'global_regions_currently_based_in'
  ];

  function rowSqliteToFellow(row) {
    var out = {};
    var i;
    for (i = 0; i < FELLOW_COLS.length; i++) {
      var k = FELLOW_COLS[i];
      out[k] = row[k];
    }
    if (row.key_links_urls) {
      try {
        out.key_links_urls = JSON.parse(row.key_links_urls);
      } catch (e) {
        out.key_links_urls = row.key_links_urls;
      }
    }
    if (row.extra_json) {
      try {
        var ex = JSON.parse(row.extra_json);
        if (ex && typeof ex === 'object') {
          for (var ek in ex) {
            if (Object.prototype.hasOwnProperty.call(ex, ek)) {
              out[ek] = ex[ek];
            }
          }
        }
      } catch (e2) {}
    }
    return out;
  }

  function dbSelectAll(db, sql, bind) {
    var st = db.prepare(sql);
    var out = [];
    try {
      if (bind !== undefined && bind !== null) {
        st.bind(bind);
      }
      while (st.step()) {
        out.push(st.get({}));
      }
    } finally {
      st.finalize();
    }
    return out;
  }

  function dbSelectOne(db, sql, bind) {
    var rows = dbSelectAll(db, sql, bind);
    return rows.length ? rows[0] : null;
  }

  function buildStatsFromDb(db) {
    var total = dbSelectOne(db, 'SELECT COUNT(*) AS c FROM fellows', null);
    var totalN = total ? total.c : 0;

    function groupCounts(sql) {
      var rows = dbSelectAll(db, sql, null);
      return rows.map(function (r) {
        return { label: r.label, count: r.cnt };
      });
    }

    var regionCounter = {};
    var st = db.prepare(
      'SELECT global_regions_currently_based_in FROM fellows WHERE global_regions_currently_based_in IS NOT NULL AND global_regions_currently_based_in != \'\''
    );
    try {
      while (st.step()) {
        var val = st.get(0);
        if (!val) continue;
        val.split(',').forEach(function (region) {
          region = String(region).trim();
          if (region) {
            regionCounter[region] = (regionCounter[region] || 0) + 1;
          }
        });
      }
    } finally {
      st.finalize();
    }
    var byRegion = Object.keys(regionCounter).map(function (k) {
      return { label: k, count: regionCounter[k] };
    });
    byRegion.sort(function (a, b) {
      return b.count - a.count;
    });

    var colLabels = {
      name: 'Name',
      bio_tagline: 'Bio / Tagline',
      fellow_type: 'Fellow Type',
      cohort: 'Cohort',
      contact_email: 'Contact Email',
      key_links: 'Key Links',
      image_url: 'Image URL',
      currently_based_in: 'Currently Based In',
      search_tags: 'Search Tags',
      fellow_status: 'Fellow Status',
      gender_pronouns: 'Gender / Pronouns',
      ethnicity: 'Ethnicity',
      primary_citizenship: 'Primary Citizenship',
      global_regions_currently_based_in: 'Global Regions Based In'
    };
    var fieldCounts = [];
    var col;
    for (col in colLabels) {
      if (!Object.prototype.hasOwnProperty.call(colLabels, col)) continue;
      var cnt = dbSelectOne(
        db,
        'SELECT COUNT(*) AS c FROM fellows WHERE ' + col + ' IS NOT NULL AND ' + col + " != ''",
        null
      );
      fieldCounts.push({ label: colLabels[col], count: cnt ? cnt.c : 0 });
    }
    var extraLabels = {
      all_citizenships: 'All Citizenships',
      ventures: 'Ventures',
      industries: 'Industries',
      career_highlights: 'Career Highlights',
      key_networks: 'Key Networks',
      how_im_looking_to_support_the_nz_ecosystem: 'How Supporting NZ Ecosystem',
      what_is_your_main_mode_of_working: 'Main Mode of Working',
      do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories: 'Investor Categories',
      mobile_number: 'Mobile Number',
      five_things_to_know: 'Five Things to Know',
      skills_to_give: 'Skills to Give',
      skills_to_receive: 'Skills to Receive'
    };
    var key;
    for (key in extraLabels) {
      if (!Object.prototype.hasOwnProperty.call(extraLabels, key)) continue;
      var path = '$.' + key;
      var ec = dbSelectOne(
        db,
        'SELECT COUNT(*) AS c FROM fellows WHERE extra_json IS NOT NULL AND json_extract(extra_json, ?) IS NOT NULL AND json_extract(extra_json, ?) != \'\'',
        [path, path]
      );
      fieldCounts.push({ label: extraLabels[key], count: ec ? ec.c : 0 });
    }
    fieldCounts.sort(function (a, b) {
      return b.count - a.count;
    });

    return {
      total: totalN,
      by_fellow_type: groupCounts(
        'SELECT fellow_type AS label, COUNT(*) AS cnt FROM fellows WHERE fellow_type IS NOT NULL GROUP BY fellow_type ORDER BY cnt DESC'
      ),
      by_cohort: groupCounts(
        'SELECT cohort AS label, COUNT(*) AS cnt FROM fellows WHERE cohort IS NOT NULL GROUP BY cohort ORDER BY cnt DESC'
      ),
      by_region: byRegion,
      field_completeness: fieldCounts
    };
  }

  function createSqliteDataProvider(db) {
    return {
      kind: 'sqlite',
      getList: function () {
        return Promise.resolve(
          dbSelectAll(db, 'SELECT record_id, slug, name FROM fellows ORDER BY name ASC', null)
        );
      },
      getFull: function () {
        var rows = dbSelectAll(db, 'SELECT * FROM fellows ORDER BY name ASC', null);
        return Promise.resolve(rows.map(rowSqliteToFellow));
      },
      getOne: function (slugOrId) {
        var row = dbSelectOne(
          db,
          'SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1',
          [slugOrId, slugOrId]
        );
        return Promise.resolve(row ? rowSqliteToFellow(row) : null);
      },
      search: function (q) {
        var qq = (q || '').trim();
        if (!qq) {
          return Promise.resolve([]);
        }
        if (qq.length > 200) {
          qq = qq.slice(0, 200);
        }
        var rows = dbSelectAll(
          db,
          'SELECT f.* FROM fellows f WHERE f.rowid IN (SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?) ORDER BY f.name ASC',
          [qq]
        );
        return Promise.resolve(rows.map(rowSqliteToFellow));
      },
      getStats: function () {
        return Promise.resolve(buildStatsFromDb(db));
      }
    };
  }

  function createApiDataProvider() {
    return {
      kind: 'api',
      getList: function () {
        return fetch('/api/fellows').then(function (r) {
          if (!r.ok) {
            throw new Error('GET /api/fellows failed: ' + r.status);
          }
          return r.json();
        });
      },
      getFull: function () {
        return fetch('/api/fellows?full=1').then(function (r) {
          if (!r.ok) {
            throw new Error('GET /api/fellows?full=1 failed: ' + r.status);
          }
          return r.json();
        });
      },
      getOne: function (slugOrId) {
        return fetch('/api/fellows/' + encodeURIComponent(slugOrId)).then(function (r) {
          return r.ok ? r.json() : null;
        });
      },
      search: function (q) {
        return fetch('/api/search?q=' + encodeURIComponent(q)).then(function (r) {
          return r.ok ? r.json() : [];
        });
      },
      getStats: function () {
        return fetch('/api/stats').then(function (r) {
          return r.ok ? r.json() : null;
        });
      }
    };
  }

  function shouldTryOpfsProvider() {
    if (!isStandaloneDisplayMode()) {
      return false;
    }
    if (typeof globalThis.sqlite3InitModule !== 'function') {
      return false;
    }
    if (!navigator.storage || typeof navigator.storage.getDirectory !== 'function') {
      return false;
    }
    if (!globalThis.isSecureContext) {
      return false;
    }
    return true;
  }

  function bootDebugPush(msg) {
    bootDebugLines.push(new Date().toISOString() + ' ' + String(msg));
  }

  function authDebugPush(msg) {
    authDebugLines.push(new Date().toISOString() + ' ' + String(msg));
  }

  function describeOpfsGates() {
    var lines = [];
    lines.push('standalone display-mode: ' + isStandaloneDisplayMode());
    lines.push('globalThis.sqlite3InitModule: ' + typeof globalThis.sqlite3InitModule);
    lines.push('navigator.storage: ' + (navigator.storage ? 'present' : 'missing'));
    lines.push(
      'navigator.storage.getDirectory: ' +
        (navigator.storage && typeof navigator.storage.getDirectory)
    );
    lines.push('isSecureContext: ' + globalThis.isSecureContext);
    lines.push('navigator.onLine: ' + navigator.onLine);
    lines.push('shouldTryOpfsProvider(): ' + shouldTryOpfsProvider());
    return lines.join('\n');
  }

  function describeSwState() {
    if (!('serviceWorker' in navigator)) {
      return 'serviceWorker: not available in this context';
    }
    var c = navigator.serviceWorker.controller;
    if (!c) {
      return 'serviceWorker: no active controller yet';
    }
    return 'serviceWorker: controller scriptURL=' + String(c.scriptURL || '');
  }

  function formatBootError(err) {
    if (err == null) {
      return '(no error object)';
    }
    if (typeof err === 'string') {
      return err;
    }
    var msg = err.message != null ? String(err.message) : String(err);
    var stack = err.stack ? '\n' + String(err.stack) : '';
    return msg + stack;
  }

  function buildBootFailureSyncReport(err) {
    var parts = [];
    parts.push('=== Fellows PWA boot failure ===');
    parts.push('time (ISO): ' + new Date().toISOString());
    parts.push('href: ' + String(location.href));
    parts.push('origin: ' + String(location.origin));
    parts.push('userAgent: ' + String(navigator.userAgent || ''));
    parts.push(describeSwState());
    parts.push('');
    parts.push('directoryDataSource: ' + directoryDataSource);
    parts.push('dataProvider present: ' + (dataProvider ? 'yes' : 'no'));
    if (dataProvider && dataProvider.kind) {
      parts.push('dataProvider.kind: ' + dataProvider.kind);
    }
    parts.push('');
    parts.push('--- OPFS / SQLite eligibility ---');
    parts.push(describeOpfsGates());
    parts.push('');
    parts.push('--- Boot trace (chronological) ---');
    parts.push(bootDebugLines.length ? bootDebugLines.join('\n') : '(no trace lines recorded)');
    parts.push('');
    parts.push('--- Thrown error ---');
    parts.push(formatBootError(err));
    return parts.join('\n');
  }

  function probeHttpEndpoints() {
    var urls = ['/fellows.db', '/api/fellows', '/api/stats', '/manifest.webmanifest'];
    return Promise.all(
      urls.map(function (url) {
        return fetch(url, { method: 'GET', cache: 'no-store' })
          .then(function (r) {
            var ct = r.headers.get('content-type') || '';
            return url + ' → HTTP ' + r.status + ' ' + r.statusText + ' content-type: ' + ct;
          })
          .catch(function (e) {
            return url + ' → fetch error: ' + (e && e.message ? e.message : String(e));
          });
      })
    ).then(function (lines) {
      return lines.join('\n');
    });
  }

  function showBootFailure(err) {
    var syncReport = buildBootFailureSyncReport(err);
    console.error('[Fellows PWA] Boot failure', {
      error: err,
      report: syncReport,
      bootTrace: bootDebugLines.slice()
    });
    if (loadingEl) {
      loadingEl.classList.add('hidden');
    }
    if (bootErrorPanelEl) {
      bootErrorPanelEl.classList.remove('hidden');
    }
    if (bootErrorPreEl) {
      bootErrorPreEl.textContent =
        syncReport + '\n\n--- HTTP probes (same-origin, cache: no-store) ---\n… fetching …';
      probeHttpEndpoints().then(function (probeText) {
        if (bootErrorPreEl) {
          bootErrorPreEl.textContent =
            syncReport + '\n\n--- HTTP probes (same-origin, cache: no-store) ---\n' + probeText;
        }
      });
    }
  }

  function clearCookiesBestEffort() {
    var cookiePairs = (document.cookie || '').split(';');
    cookiePairs.forEach(function (cookie) {
      var eqPos = cookie.indexOf('=');
      var rawName = eqPos > -1 ? cookie.slice(0, eqPos) : cookie;
      var name = rawName.trim();
      if (!name) return;
      document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
      document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Strict';
      document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;Secure;SameSite=Strict';
    });
  }

  async function clearAllAppData() {
    try {
      localStorage.clear();
      sessionStorage.clear();

      if (window.indexedDB && typeof window.indexedDB.deleteDatabase === 'function') {
        try {
          window.indexedDB.deleteDatabase('fellows-local-db');
        } catch (err) {}
      }

      if ('caches' in window) {
        try {
          var cacheNames = await caches.keys();
          await Promise.all(
            cacheNames.map(function (cacheName) {
              return caches.delete(cacheName);
            })
          );
        } catch (err) {
          console.error('Error clearing Cache API caches:', err);
        }
      }

      if ('serviceWorker' in navigator) {
        try {
          var registrations = await navigator.serviceWorker.getRegistrations();
          for (var i = 0; i < registrations.length; i++) {
            await registrations[i].unregister();
          }
        } catch (err2) {
          console.error('Error unregistering service workers:', err2);
        }
      }

      clearCookiesBestEffort();
      window.location.replace(
        window.location.pathname + '?cache_reset=' + Date.now() + (window.location.hash || '')
      );
    } catch (e) {
      console.error('[Fellows] clearAllAppData failed:', e);
      try {
        window.location.replace(
          window.location.pathname + '?cache_reset=force' + (window.location.hash || '')
        );
      } catch (e2) {
        window.location.reload();
      }
    }
  }

  window.clearAllAppData = clearAllAppData;

  function initClearCacheButton() {
    var btn = document.getElementById('clear-app-cache-button');
    if (!btn) return;
    btn.addEventListener('click', function () {
      Promise.resolve(clearAllAppData()).catch(function (e) {
        console.error('[Fellows] clearAllAppData rejected:', e);
      });
    });
  }

  async function collectDiagnosticsText() {
    var lines = [];
    lines.push('=== Fellows client diagnostics (UI mark: ' + FELLOWS_UI_DIAG + ') ===');
    lines.push('time (ISO): ' + new Date().toISOString());
    lines.push('href: ' + String(location.href));
    lines.push(
      'document.cookie length (HttpOnly cookies are NOT visible to JS): ' +
        String((document.cookie || '').length)
    );
    lines.push('');
    if ('serviceWorker' in navigator) {
      try {
        var regs = await navigator.serviceWorker.getRegistrations();
        lines.push('serviceWorker.getRegistrations: ' + regs.length);
        for (var ri = 0; ri < regs.length; ri++) {
          var reg = regs[ri];
          lines.push(
            '  [' + ri + '] scope=' + reg.scope +
              ' active=' + (reg.active ? reg.active.scriptURL : '(none)') +
              ' waiting=' + (reg.waiting ? reg.waiting.scriptURL : '(none)') +
              ' installing=' + (reg.installing ? reg.installing.scriptURL : '(none)')
          );
        }
      } catch (e) {
        lines.push('SW getRegistrations error: ' + String(e && e.message));
      }
      if (navigator.serviceWorker.controller) {
        lines.push('navigator.serviceWorker.controller: ' + String(navigator.serviceWorker.controller.scriptURL));
      } else {
        lines.push('navigator.serviceWorker.controller: (none yet)');
      }
      if (swUpdateBannerEl) {
        lines.push(
          'sw-update-banner visible=' + !swUpdateBannerEl.classList.contains('hidden') +
            ' shownReason=' + (swUpdateBannerEl.getAttribute('data-shown-reason') || '(none)') +
            ' shownAt=' + (swUpdateBannerEl.getAttribute('data-shown-at') || '(never)') +
            ' hiddenAt=' + (swUpdateBannerEl.getAttribute('data-hidden-at') || '(never)')
        );
      }
      lines.push('SW lifecycle log (' + swLifecycleLog.length + ' events):');
      if (swLifecycleLog.length === 0) {
        lines.push('  (empty)');
      } else {
        for (var li = 0; li < swLifecycleLog.length; li++) {
          var ev = swLifecycleLog[li];
          lines.push(
            '  ' + ev.t + ' ' + ev.event +
              (ev.detail != null ? ' ' + JSON.stringify(ev.detail) : '')
          );
        }
      }
    } else {
      lines.push('serviceWorker: not available in this context');
    }
    lines.push('');
    try {
      var r = await fetch('/api/auth/status', { credentials: 'same-origin', cache: 'no-store' });
      lines.push('GET /api/auth/status → HTTP ' + r.status);
      lines.push('  X-Fellows-Build: ' + (r.headers.get('X-Fellows-Build') || '(none)'));
      lines.push('  X-Fellows-Auth-Active: ' + (r.headers.get('X-Fellows-Auth-Active') || '(none)'));
      var j = await r.json();
      lines.push('  body: ' + JSON.stringify(j));
    } catch (e) {
      lines.push('/api/auth/status failed: ' + String(e && e.message));
    }
    lines.push('');
    try {
      var r2 = await fetch('/api/debug/diagnostics', { credentials: 'same-origin', cache: 'no-store' });
      lines.push('GET /api/debug/diagnostics → HTTP ' + r2.status);
      lines.push('  X-Fellows-Build: ' + (r2.headers.get('X-Fellows-Build') || '(none)'));
      lines.push(JSON.stringify(await r2.json(), null, 2));
    } catch (e2) {
      lines.push('/api/debug/diagnostics failed: ' + String(e2 && e2.message));
    }
    lines.push('');
    try {
      var r3 = await fetch('/build-meta.json', { cache: 'no-store' });
      lines.push('GET /build-meta.json → HTTP ' + r3.status);
      lines.push((await r3.text()).trim());
    } catch (e3) {
      lines.push('GET /build-meta.json failed (expected before first build): ' + String(e3 && e3.message));
    }
    lines.push('');
    if ('caches' in window) {
      try {
        var keys = await caches.keys();
        lines.push('Cache API keys (' + keys.length + '): ' + (keys.length ? keys.join(', ') : '(none)'));
      } catch (e4) {
        lines.push('caches.keys error: ' + String(e4 && e4.message));
      }
    }
    lines.push('');
    lines.push(
      'Tip: In Chrome DevTools → Application → Cookies → https://your-host — HttpOnly session cookie may list there while document.cookie stays empty.'
    );
    return lines.join('\n');
  }

  function initDiagnosticsPanel() {
    var panel = document.getElementById('diag-panel');
    var pre = document.getElementById('diag-pre');
    var toggle = document.getElementById('diag-toggle');
    var closeBtn = document.getElementById('diag-close');
    var refreshBtn = document.getElementById('diag-refresh');

    async function refresh() {
      if (!pre) return;
      pre.textContent = 'Loading…';
      try {
        pre.textContent = await collectDiagnosticsText();
      } catch (err) {
        pre.textContent = 'Error: ' + (err && err.message ? err.message : String(err));
      }
    }

    if (toggle) {
      toggle.addEventListener('click', function () {
        if (!panel) return;
        panel.classList.toggle('hidden');
        var hidden = panel.classList.contains('hidden');
        panel.setAttribute('aria-hidden', hidden ? 'true' : 'false');
        if (!hidden) {
          refresh();
        }
      });
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        if (panel) {
          panel.classList.add('hidden');
          panel.setAttribute('aria-hidden', 'true');
        }
      });
    }
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        refresh();
      });
    }

    try {
      if (new URLSearchParams(location.search).get('diag') === '1' && panel) {
        panel.classList.remove('hidden');
        panel.setAttribute('aria-hidden', 'false');
        refresh();
      }
    } catch (e5) {}
  }

  function showAuthFailure(reason, extra) {
    var lines = [];
    lines.push('=== Fellows auth check failure ===');
    lines.push('time (ISO): ' + new Date().toISOString());
    lines.push('href: ' + String(location.href));
    lines.push('origin: ' + String(location.origin));
    lines.push('userAgent: ' + String(navigator.userAgent || ''));
    lines.push('reason: ' + String(reason || 'unknown'));
    if (extra != null) {
      lines.push('details: ' + String(extra));
    }
    lines.push('');
    lines.push('--- Auth trace (chronological) ---');
    lines.push(authDebugLines.length ? authDebugLines.join('\n') : '(no auth trace lines recorded)');
    lines.push('');
    lines.push('--- Recommended checks ---');
    lines.push('1) Confirm /api/auth/status returns JSON over HTTPS');
    lines.push('2) Confirm service worker is current (use Clear App Cache & Reload)');
    lines.push('3) Check app server logs for auth initialization warnings');

    if (loadingEl) loadingEl.classList.add('hidden');
    if (loadingPanelEl) loadingPanelEl.classList.add('hidden');
    if (installLandingEl) installLandingEl.classList.add('hidden');
    if (installGatePrivateEl) installGatePrivateEl.classList.add('hidden');
    if (appWrapEl) appWrapEl.classList.add('hidden');
    if (siteHeaderEl) siteHeaderEl.classList.add('hidden');
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');
    if (authErrorPanelEl) authErrorPanelEl.classList.remove('hidden');
    if (authErrorPreEl) authErrorPreEl.textContent = lines.join('\n');
  }

  function setSetupStatus(msg) {
    if (!loadingEl) return;
    loadingEl.textContent = msg || 'Loading…';
  }

  function fetchFellowsDbWithProgress(onProgress) {
    return fetch('/fellows.db').then(function (r) {
      if (!r.ok) {
        throw new Error('GET /fellows.db failed: HTTP ' + r.status);
      }
      var lenHeader = r.headers.get('Content-Length');
      var total = lenHeader ? parseInt(lenHeader, 10) : 0;
      if (!r.body || !r.body.getReader) {
        return r.arrayBuffer().then(function (buf) {
          if (onProgress && total) {
            onProgress(buf.byteLength, total);
          }
          return new Uint8Array(buf);
        });
      }
      var reader = r.body.getReader();
      var chunks = [];
      var received = 0;
      return reader.read().then(function processChunk(result) {
        if (result.done) {
          var i;
          var totalLen = 0;
          for (i = 0; i < chunks.length; i++) {
            totalLen += chunks[i].byteLength;
          }
          var out = new Uint8Array(totalLen);
          var pos = 0;
          for (i = 0; i < chunks.length; i++) {
            out.set(chunks[i], pos);
            pos += chunks[i].byteLength;
          }
          return out;
        }
        chunks.push(result.value);
        received += result.value.byteLength;
        if (onProgress && total) {
          onProgress(received, total);
        }
        return reader.read().then(processChunk);
      });
    });
  }

  function initOpfsDataProvider() {
    setSetupStatus('Setting up your local directory…');
    return globalThis
      .sqlite3InitModule()
      .then(function (Module) {
        bootDebugPush('sqlite3InitModule: OK');
        return Module.sqlite3.installOpfsSAHPoolVfs();
      })
      .then(function (poolUtil) {
        bootDebugPush('installOpfsSAHPoolVfs: OK');
        setSetupStatus('Downloading directory data…');
        return fetchFellowsDbWithProgress(function (n, total) {
          var pct = total ? Math.round((100 * n) / total) : 0;
          setSetupStatus('Downloading directory data… ' + pct + '%');
        }).then(function (bytes) {
          bootDebugPush('fellows.db download: OK bytes=' + (bytes && bytes.byteLength));
          setSetupStatus('Preparing offline database…');
          poolUtil.importDb('fellows.db', bytes);
          var db = new poolUtil.OpfsSAHPoolDb('fellows.db');
          return createSqliteDataProvider(db);
        });
      });
  }

  function pickDataProvider() {
    bootDebugPush('pickDataProvider: start');
    bootDebugPush('gates (one line): ' + describeOpfsGates().replace(/\n/g, ' | '));
    if (!shouldTryOpfsProvider()) {
      bootDebugPush('using API provider (OPFS path not used)');
      return Promise.resolve(createApiDataProvider());
    }
    bootDebugPush('trying OPFS + sqlite-wasm');
    return initOpfsDataProvider().catch(function (e) {
      bootDebugPush(
        'OPFS path failed → API fallback: ' + (e && e.message ? e.message : String(e))
      );
      console.warn('Local SQLite / OPFS unavailable, using API:', e);
      return createApiDataProvider();
    });
  }

  function isStandaloneDisplayMode() {
    if (typeof window.navigator !== 'undefined' && window.navigator.standalone === true) {
      return true;
    }
    return window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
  }

  function setInstallStatus(msg) {
    if (!installStatusEl) return;
    installStatusEl.textContent = msg || '';
  }

  function showSwUpdateBanner(reason) {
    var r = reason || 'unknown';
    if (swUpdateBannerEl) {
      swUpdateBannerEl.classList.remove('hidden');
      swUpdateBannerEl.setAttribute('data-shown-reason', r);
      swUpdateBannerEl.setAttribute('data-shown-at', new Date().toISOString());
    }
    logSwLifecycle('banner_show', { reason: r });
  }

  function hideSwUpdateBanner() {
    if (swUpdateBannerEl) {
      swUpdateBannerEl.classList.add('hidden');
      swUpdateBannerEl.setAttribute('data-hidden-at', new Date().toISOString());
    }
    logSwLifecycle('banner_hide', null);
  }

  function listenForSwUpdate(reg) {
    if (!reg || typeof reg.addEventListener !== 'function') return;
    // Snapshot: null here means this is a first-time install, not an update.
    var hadControllerAtRegister = !!navigator.serviceWorker.controller;
    logSwLifecycle('listen_start', {
      hadControllerAtRegister: hadControllerAtRegister,
      regActive: reg.active ? reg.active.scriptURL : null,
      regWaiting: reg.waiting ? reg.waiting.scriptURL : null,
      regInstalling: reg.installing ? reg.installing.scriptURL : null
    });
    if (reg.waiting && hadControllerAtRegister) {
      showSwUpdateBanner('waiting-at-register');
    }
    reg.addEventListener('updatefound', function () {
      var nw = reg.installing;
      logSwLifecycle('updatefound', {
        hasInstalling: !!nw,
        hadControllerAtRegister: hadControllerAtRegister
      });
      if (!nw) return;
      nw.addEventListener('statechange', function () {
        logSwLifecycle('statechange', {
          state: nw.state,
          hadControllerAtRegister: hadControllerAtRegister
        });
        if (nw.state === 'installed' && hadControllerAtRegister) {
          showSwUpdateBanner('installed-event');
        }
      });
    });
  }

  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      logSwLifecycle('controllerchange', {
        newController: navigator.serviceWorker.controller
          ? navigator.serviceWorker.controller.scriptURL
          : null
      });
      hideSwUpdateBanner();
    });
    window.addEventListener('load', function () {
      logSwLifecycle('window_load', {
        controllerAtLoad: navigator.serviceWorker.controller
          ? navigator.serviceWorker.controller.scriptURL
          : null
      });
      navigator.serviceWorker
        .register('/sw.js')
        .then(function (reg) {
          logSwLifecycle('register_resolved', {
            active: reg.active ? reg.active.scriptURL : null,
            waiting: reg.waiting ? reg.waiting.scriptURL : null,
            installing: reg.installing ? reg.installing.scriptURL : null
          });
          listenForSwUpdate(reg);
          return reg;
        })
        .catch(function (err) {
          logSwLifecycle('register_error', { message: err && err.message });
        });
    });
  }

  function initSwReloadButton() {
    if (!swUpdateReloadEl) return;
    swUpdateReloadEl.addEventListener('click', function () {
      hideSwUpdateBanner();
      window.location.reload();
    });
  }

  function isIosSafari() {
    var ua = navigator.userAgent || '';
    var iOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    var webkit = /WebKit/.test(ua);
    var noChrome = !/CriOS|FxiOS|EdgiOS/.test(ua);
    return iOS && webkit && noChrome;
  }

  function formatAuthDebugLine(data, httpStatus) {
    var st = httpStatus != null ? String(httpStatus) : '?';
    var ae = data && typeof data.authEnabled === 'boolean' ? data.authEnabled : '?';
    var au = data && typeof data.authenticated === 'boolean' ? data.authenticated : '?';
    return (
      'Auth debug: GET /api/auth/status → HTTP ' +
      st +
      ' · authEnabled=' +
      ae +
      ' · authenticated=' +
      au
    );
  }

  function showAuthDebugInstall(data, httpStatus) {
    if (authDebugPrivateEl) {
      authDebugPrivateEl.classList.add('hidden');
      authDebugPrivateEl.textContent = '';
    }
    if (authDebugInstallEl) {
      authDebugInstallEl.textContent = formatAuthDebugLine(data, httpStatus);
      authDebugInstallEl.classList.remove('hidden');
    }
  }

  function showAuthDebugPrivate(data, httpStatus) {
    if (authDebugInstallEl) {
      authDebugInstallEl.classList.add('hidden');
      authDebugInstallEl.textContent = '';
    }
    if (authDebugPrivateEl) {
      authDebugPrivateEl.textContent = formatAuthDebugLine(data, httpStatus);
      authDebugPrivateEl.classList.remove('hidden');
    }
  }

  function initBrowserInstallMode(authPayload, httpStatus) {
    if (installGatePrivateEl) installGatePrivateEl.classList.add('hidden');
    if (installLandingEl) installLandingEl.classList.remove('hidden');
    if (siteHeaderEl) siteHeaderEl.classList.add('hidden');
    showLoading(false);
    showApp(false);
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');

    if (authPayload) {
      showAuthDebugInstall(authPayload, httpStatus != null ? httpStatus : 200);
    }

    if (isIosSafari() && iosHintEl) {
      iosHintEl.classList.remove('hidden');
      if (installButtonEl) installButtonEl.classList.add('hidden');
    }

    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      deferredInstallPrompt = e;
      setInstallStatus('');
    });

    window.addEventListener('appinstalled', function () {
      deferredInstallPrompt = null;
      setInstallStatus('App installed — open it from your dock or app drawer.');
      if (installButtonEl) installButtonEl.classList.add('hidden');
    });

    if (installButtonEl) {
      installButtonEl.addEventListener('click', function () {
        if (deferredInstallPrompt) {
          deferredInstallPrompt.prompt();
          deferredInstallPrompt.userChoice
            .then(function (choice) {
              deferredInstallPrompt = null;
              if (choice && choice.outcome === 'accepted') {
                setInstallStatus('Installing…');
              }
            })
            .catch(function () {
              deferredInstallPrompt = null;
            });
        } else {
          setInstallStatus(
            'Use your browser’s install option (menu) or Add to Home Screen on iOS.'
          );
        }
      });
    }
  }

  function initPrivateGate(authPayload, httpStatus) {
    if (installGatePrivateEl) installGatePrivateEl.classList.remove('hidden');
    if (installLandingEl) installLandingEl.classList.add('hidden');
    if (siteHeaderEl) siteHeaderEl.classList.add('hidden');
    showLoading(false);
    showApp(false);
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');

    if (authPayload) {
      showAuthDebugPrivate(authPayload, httpStatus != null ? httpStatus : 200);
    }

    if (unlockEmailFormEl) {
      unlockEmailFormEl.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (unlockEmailInputEl && unlockEmailInputEl.value) || '';
        if (unlockStatusEl) unlockStatusEl.textContent = 'Sending…';
        fetch('/api/send-unlock', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ email: email.trim() })
        })
          .then(function (r) {
            return r.json();
          })
          .then(function () {
            if (unlockStatusEl) {
              unlockStatusEl.textContent =
                'If that email is on file, you will receive a link shortly. Check your inbox.';
            }
          })
          .catch(function () {
            if (unlockStatusEl) unlockStatusEl.textContent = 'Could not send. Try again later.';
          });
      });
    }

    if (sessionStorage.getItem('fellows_unlock_err')) {
      sessionStorage.removeItem('fellows_unlock_err');
      if (unlockStatusEl) {
        unlockStatusEl.textContent =
          'Link expired or invalid — request a new one from your fellowship email.';
      }
    }
  }

  function tryUnlockFromHash() {
    var hash = window.location.hash || '';
    var m = hash.match(/^#\/unlock\/(.+)$/);
    if (!m) {
      return Promise.resolve();
    }
    var token = m[1];
    window.history.replaceState(null, '', window.location.pathname + window.location.search + '#/');
    return fetch('/api/verify-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ token: token })
    })
      .then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok || !j.ok) {
            sessionStorage.setItem('fellows_unlock_err', '1');
          }
        });
      })
      .catch(function () {
        sessionStorage.setItem('fellows_unlock_err', '1');
      });
  }

  function reloadIfBuildChanged(currentBuild) {
    if (!currentBuild) return false;
    var key = 'fellows_last_seen_build';
    var prev = null;
    try { prev = localStorage.getItem(key); } catch (e) { return false; }
    try { localStorage.setItem(key, currentBuild); } catch (e) {}
    if (prev && prev !== currentBuild) {
      authDebugPush('build changed ' + prev + ' → ' + currentBuild + '; reloading once');
      try { window.location.reload(); } catch (e) {}
      return true;
    }
    return false;
  }

  function startBrowserUx() {
    authDebugLines.length = 0;
    authDebugPush('startBrowserUx: begin auth status check');
    fetch('/api/auth/status', { credentials: 'same-origin' })
      .then(function (r) {
        authDebugPush('/api/auth/status HTTP ' + r.status);
        if (reloadIfBuildChanged(r.headers.get('X-Fellows-Build'))) {
          return new Promise(function () {});
        }
        if (!r.ok) {
          throw new Error('/api/auth/status failed with HTTP ' + r.status);
        }
        return r.json().then(function (data) {
          return { status: r.status, data: data };
        });
      })
      .then(function (result) {
        var data = result.data;
        var httpStatus = result.status;
        if (!data || typeof data.authEnabled !== 'boolean' || typeof data.authenticated !== 'boolean') {
          throw new Error('/api/auth/status returned invalid payload shape');
        }
        authDebugPush(
          '/api/auth/status payload authEnabled=' + data.authEnabled + ' authenticated=' + data.authenticated
        );
        if (!data.authEnabled) {
          authDebugPush('auth disabled on server: using install mode');
          initBrowserInstallMode(data, httpStatus);
          return;
        }
        if (data.authenticated) {
          authDebugPush('session authenticated: using install mode');
          initBrowserInstallMode(data, httpStatus);
          return;
        }
        authDebugPush('auth enabled + unauthenticated: using private gate');
        initPrivateGate(data, httpStatus);
      })
      .catch(function (err) {
        authDebugPush('auth status check failed: ' + (err && err.message ? err.message : String(err)));
        showAuthFailure('Unable to validate auth status; refusing install-mode fallback', err && err.message);
      });
  }

  function showLoading(show) {
    loadingEl.classList.toggle('hidden', !show);
  }

  function showApp(show) {
    if (appWrapEl) appWrapEl.classList.toggle('hidden', !show);
  }

  function renderDirectoryList(items) {
    var ul = document.createElement('ul');
    items.forEach(function (f) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#/fellow/' + encodeURIComponent(f.slug || '');
      var displayName = (f.name && String(f.name).trim()) ? f.name : 'Unknown';
      a.textContent = displayName;
      li.appendChild(a);
      ul.appendChild(li);
    });
    directoryListEl.innerHTML = '';
    directoryListEl.appendChild(ul);
  }

  function renderDirectory() {
    if (!list.length) {
      directoryListEl.innerHTML = '<p class="placeholder">No fellows loaded.</p>';
      return;
    }
    renderDirectoryList(list);
    displayedList = list;
    if (loadingPanelEl) {
      loadingPanelEl.classList.add('hidden');
    }
    showLoading(false);
    showApp(true);
  }

  function setSearchStatus(msg) {
    if (!searchStatusEl) return;
    searchStatusEl.textContent = msg || '';
  }

  function setNlSearchStatus(msg) {
    if (!nlSearchStatusEl) return;
    nlSearchStatusEl.textContent = msg || '';
  }

  function section(title, body, secondary) {
    if (!body || !body.trim()) return '';
    var titleClass = 'detail-section-title' + (secondary ? ' detail-section-title--secondary' : '');
    return '<div class="detail-section"><h3 class="' + titleClass + '">' + escapeHtml(title) + '</h3><div class="detail-section-body">' + body + '</div></div>';
  }

  /** Section that always renders; when body is empty, no text (no "—"), just header and blank line. */
  function sectionAlways(title, body, secondary) {
    var hasBody = body && String(body).trim();
    var content = hasBody ? body : '';
    var bodyClass = 'detail-section-body' + (!hasBody ? ' detail-section-body--empty' : '');
    var titleClass = 'detail-section-title' + (secondary ? ' detail-section-title--secondary' : '');
    return '<div class="detail-section"><h3 class="' + titleClass + '">' + escapeHtml(title) + '</h3><div class="' + bodyClass + '">' + content + '</div></div>';
  }

  function fieldRow(label, value) {
    if (value == null || String(value).trim() === '') return '';
    return '<tr><td class="field-label">' + escapeHtml(label) + '</td><td class="field-value">' + value + '</td></tr>';
  }

  /** Work subheader block: label only, optional value below (no text/dash when empty). Single blank line between blocks. */
  function workBlock(label, value) {
    var hasVal = value != null && String(value).trim() !== '';
    var valueHtml = hasVal ? '<div class="work-value">' + escapeHtml(value) + '</div>' : '';
    return '<div class="work-block"><div class="work-subheader">' + escapeHtml(label) + '</div>' + valueHtml + '</div>';
  }

  function tableFromRows(rows) {
    var joined = rows.join('');
    if (!joined) return '';
    return '<table><tbody>' + joined + '</tbody></table>';
  }

  function renderDetail(fellow) {
    if (!fellow) {
      detailEl.innerHTML = '<p class="placeholder">Select a fellow from the list.</p>';
      detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }
    var name = fellow.name || fellow.slug || 'Unknown';
    var slug = fellow.slug || '';
    var leftTop = '';
    var leftRest = '';

    var demo = [fellow.gender_pronouns, fellow.ethnicity].filter(Boolean).join(' | ');
    leftTop += '<h2 class="detail-name">' + escapeHtml(name) + '</h2>';
    if (demo) leftTop += '<p class="detail-demographics">' + escapeHtml(demo) + '</p>';
    leftTop += '<div class="profile-image-wrap"><img class="profile-image" data-slug="' + escapeHtml(slug) + '" src="/images/' + escapeHtml(slug) + '.jpg" alt="' + escapeHtml(name) + '"></div>';
    if (fellow.bio_tagline) leftTop += '<p class="detail-tagline">' + escapeHtml(fellow.bio_tagline) + '</p>';

    var howRows = [];
    if (fellow.fellow_status) howRows.push(fieldRow('Fellow Status', escapeHtml(fellow.fellow_status)));
    if (fellow.fellow_type) howRows.push(fieldRow('Fellow Type', escapeHtml(fellow.fellow_type)));
    if (fellow.key_links_urls && fellow.key_links_urls.length) {
      var linkLabels = (fellow.key_links || '').split(',');
      var linkHtml = fellow.key_links_urls.map(function (url, i) {
        var label = (linkLabels[i] || url).trim();
        return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(label) + '</a>';
      }).join(', ');
      howRows.push(fieldRow('Key Links', linkHtml));
    }
    if (fellow.contact_email) howRows.push(fieldRow('Contact Email', '<a href="mailto:' + escapeHtml(fellow.contact_email) + '">' + escapeHtml(fellow.contact_email) + '</a>'));
    if (fellow.mobile_number) howRows.push(fieldRow('Mobile Number', escapeHtml(String(fellow.mobile_number))));
    if (fellow.cohort) howRows.push(fieldRow('Cohort', escapeHtml(fellow.cohort)));
    leftRest += section('How to Connect', tableFromRows(howRows));

    var geoRows = [];
    if (fellow.primary_citizenship) geoRows.push(fieldRow('Primary Citizenship', escapeHtml(fellow.primary_citizenship)));
    if (fellow.all_citizenships) geoRows.push(fieldRow('All Citizenships', escapeHtml(fellow.all_citizenships)));
    if (fellow.primary_global_region_of_citizenship) geoRows.push(fieldRow('Primary Global Region of Citizenship', escapeHtml(fellow.primary_global_region_of_citizenship)));
    if (fellow.global_networks) geoRows.push(fieldRow('Global Networks', escapeHtml(fellow.global_networks)));
    if (fellow.currently_based_in) geoRows.push(fieldRow('Currently Based In', escapeHtml(fellow.currently_based_in)));
    if (fellow.global_regions_currently_based_in) geoRows.push(fieldRow('Global Regions Currently Based In', escapeHtml(fellow.global_regions_currently_based_in)));
    leftRest += section('Geography', tableFromRows(geoRows));

    leftRest += section('Search Tags', (fellow.search_tags && String(fellow.search_tags).trim()) ? escapeHtml(fellow.search_tags) : '—', true);
    if (fellow.this_profile_last_updated) leftRest += section('This Profile Last Updated', '<span class="profile-updated-date">' + escapeHtml(fellow.this_profile_last_updated) + '</span>', true);

    var workRows = [];
    workRows.push(workBlock('Ventures', fellow.ventures));
    workRows.push(workBlock('Industries', fellow.industries));
    workRows.push(workBlock('Industries - Other', fellow.industries_other));
    workRows.push(workBlock('What is your main mode of working?', fellow.what_is_your_main_mode_of_working));
    workRows.push(workBlock('Do you consider yourself an investor in one or more of these categories?', fellow.do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories));
    workRows.push(workBlock('What are the main types of organisations you serve?', fellow.what_are_the_main_types_of_organisations_you_serve));
    var workBody = workRows.join('');
    var rightTop = section('Work', workBody);

    var rightRest = '';
    rightRest += sectionAlways('Career Highlights', fellow.career_highlights ? escapeHtml(fellow.career_highlights) : '', true);
    rightRest += sectionAlways("How I'm looking to support the NZ ecosystem", fellow.how_im_looking_to_support_the_nz_ecosystem ? escapeHtml(fellow.how_im_looking_to_support_the_nz_ecosystem) : '', true);
    rightRest += sectionAlways('Key Networks', fellow.key_networks ? escapeHtml(fellow.key_networks) : '', true);

    // Build prev/next navigation arrows
    var navHtml = '';
    if (fellow.slug && displayedList.length) {
      var idx = -1;
      for (var i = 0; i < displayedList.length; i++) {
        if (displayedList[i].slug === fellow.slug) { idx = i; break; }
      }
      if (idx !== -1) {
        var prevSlug = idx > 0 ? displayedList[idx - 1].slug : null;
        var nextSlug = idx < displayedList.length - 1 ? displayedList[idx + 1].slug : null;
        var prevClass = 'fellow-nav-arrow fellow-nav-arrow--prev' + (prevSlug ? '' : ' fellow-nav-arrow--hidden');
        var nextClass = 'fellow-nav-arrow fellow-nav-arrow--next' + (nextSlug ? '' : ' fellow-nav-arrow--hidden');
        var prevHref = prevSlug ? '#/fellow/' + encodeURIComponent(prevSlug) : '#';
        var nextHref = nextSlug ? '#/fellow/' + encodeURIComponent(nextSlug) : '#';
        navHtml = '<nav class="fellow-nav">' +
          '<a class="' + prevClass + '" href="' + prevHref + '" aria-label="Previous fellow">&larr;</a>' +
          '<a class="' + nextClass + '" href="' + nextHref + '" aria-label="Next fellow">&rarr;</a>' +
          '<span class="fellow-nav-hint">or use arrow keys</span>' +
          '</nav>';
      }
    }

    var html = '<header class="detail-page-title">' + escapeHtml(DETAIL_PAGE_TITLE) + '</header>' +
      navHtml +
      '<div class="detail-grid">' +
      '<div class="detail-column detail-left-top">' + leftTop + '</div>' +
      '<div class="detail-column detail-right-top">' + rightTop + '</div>' +
      '<div class="detail-column detail-left-rest">' + leftRest + '</div>' +
      '<div class="detail-column detail-right-rest">' + rightRest + '</div>' +
      '</div>';
    detailEl.innerHTML = html;
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    var img = detailEl.querySelector('.profile-image');
    if (img) {
      img.onerror = function () {
        var s = img.getAttribute('data-slug');
        if (img.src.indexOf('.png') === -1 && s) {
          img.src = '/images/' + s + '.png';
          img.onerror = function () { showImagePlaceholder(img); };
        } else {
          showImagePlaceholder(img);
        }
      };
    }
  }

  function showImagePlaceholder(imgEl) {
    imgEl.onerror = null;
    imgEl.style.display = 'none';
    var p = document.createElement('span');
    p.className = 'placeholder';
    p.textContent = 'No image';
    imgEl.parentNode.appendChild(p);
  }

  function escapeHtml(s) {
    if (s == null) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function statsSection(title, items, color) {
    if (!items || !items.length) return '';
    var maxCount = items[0].count;
    var barHeight = 28;
    var labelWidth = 220;
    var gap = 4;
    var chartWidth = 500;
    var svgHeight = items.length * (barHeight + gap);
    var totalWidth = labelWidth + chartWidth + 60;

    var svg = '<svg class="stats-chart" width="100%" viewBox="0 0 ' + totalWidth + ' ' + svgHeight + '" role="img" aria-label="' + escapeHtml(title) + '">';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var y = i * (barHeight + gap);
      var barWidth = maxCount > 0 ? (item.count / maxCount) * chartWidth : 0;
      svg += '<text x="' + (labelWidth - 8) + '" y="' + (y + barHeight / 2 + 5) + '" text-anchor="end" font-size="13" fill="#333">' + escapeHtml(item.label) + '</text>';
      svg += '<rect x="' + labelWidth + '" y="' + y + '" width="' + barWidth + '" height="' + barHeight + '" rx="3" fill="' + color + '" opacity="0.85"/>';
      svg += '<text x="' + (labelWidth + barWidth + 6) + '" y="' + (y + barHeight / 2 + 5) + '" font-size="13" fill="#333">' + item.count + '</text>';
    }
    svg += '</svg>';

    return '<div class="detail-section"><h3 class="detail-section-title">' + escapeHtml(title) + '</h3><div class="detail-section-body">' + svg + '</div></div>';
  }

  function renderAboutPage() {
    var aboutHtml = '<div class="stats-page">';
    aboutHtml += '<h2 class="stats-title">About This App</h2>';
    aboutHtml += '<div class="about-body">';
    aboutHtml += '<p>V0.1 \u2014 This app is a much faster version of the fellows database. ';
    aboutHtml += 'This app is shared with EHF fellows on request on the condition that they keep the information in it private to the EHF fellows. ';
    aboutHtml += 'Never post this anywhere\u2014 it contains the relevant bits of data from the old fellows directory. ';
    aboutHtml += 'There is no API, login, or web app, so this can only be shared intentionally. ';
    aboutHtml += 'For support, request to join the github repository or just ask on one of the fellows channels.</p>';
    aboutHtml += '<p class="about-support">Having trouble with the app? Contact the EHF Communications Working Group.</p>';
    aboutHtml += '<p class="about-repo"><a href="https://github.com/richbodo/fellows_local_db" target="_blank" rel="noopener">';
    aboutHtml += '<svg class="github-icon" viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>';
    aboutHtml += ' richbodo/fellows_local_db</a></p>';
    aboutHtml += '</div>';

    aboutHtml += '<h2 class="stats-title">Fellowship Statistics</h2>';
    aboutHtml += '<p class="stats-total" id="stats-total">Loading stats\u2026</p>';
    aboutHtml += '<div class="stats-grid" id="stats-grid"></div>';
    aboutHtml += '</div>';
    detailEl.innerHTML = aboutHtml;

    if (!dataProvider) {
      var totalEl0 = document.getElementById('stats-total');
      if (totalEl0) totalEl0.textContent = 'Failed to load stats.';
      return;
    }
    dataProvider
      .getStats()
      .then(function (data) {
        if (!data) return;
        var totalEl = document.getElementById('stats-total');
        var gridEl = document.getElementById('stats-grid');
        if (totalEl) totalEl.innerHTML = 'Total Fellows: <strong>' + escapeHtml(String(data.total)) + '</strong>';
        if (gridEl) {
          var gh = '<div class="stats-col stats-col--left">';
          gh += statsSection('Fellows by Type', data.by_fellow_type, '#4a2c6a');
          gh += statsSection('Fellows by Cohort', data.by_cohort, '#2c6a4a');
          gh += statsSection('Fellows by Region', data.by_region, '#2c4a6a');
          gh += '</div>';
          gh += '<div class="stats-col stats-col--right">';
          gh += statsSection('Field Completeness', data.field_completeness, '#5a5a5a');
          gh += '</div>';
          gridEl.innerHTML = gh;
        }
      })
      .catch(function () {
        var totalEl = document.getElementById('stats-total');
        if (totalEl) totalEl.textContent = 'Failed to load stats.';
      });
  }

  function route() {
    var hash = window.location.hash || '';
    if (hash === '#/about') {
      renderAboutPage();
    } else {
      updateDetailFromHash();
    }
  }

  function getSlugFromHash() {
    var hash = window.location.hash || '';
    var m = hash.match(/#\/fellow\/([^/]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function updateDetailFromHash() {
    var slug = getSlugFromHash();
    if (!slug) {
      renderDetail(null);
      return;
    }
    var fellow = fellowsBySlug.get(slug);
    if (fellow) {
      renderDetail(fellow);
      return;
    }
    detailEl.innerHTML = '<p class="placeholder">Loading…</p>';
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (!dataProvider) {
      if (getSlugFromHash() === slug) renderDetail(null);
      return;
    }
    dataProvider
      .getOne(slug)
      .then(function (data) {
        if (data) {
          if (data.slug) fellowsBySlug.set(data.slug, data);
          if (data.record_id) fellowsBySlug.set(data.record_id, data);
        }
        if (getSlugFromHash() === slug) renderDetail(data);
      })
      .catch(function () {
        if (getSlugFromHash() === slug) renderDetail(null);
      });
  }

  function runSearch(q) {
    if (!q) {
      setSearchStatus('');
      renderDirectory();
      return;
    }
    if (directoryDataSource === 'sqlite' && dataProvider) {
      setSearchStatus('Searching…');
      dataProvider
        .search(q)
        .then(function (results) {
          if (!Array.isArray(results)) {
            results = [];
          }
          results.forEach(function (f) {
            if (f && f.slug) {
              fellowsBySlug.set(f.slug, f);
            }
            if (f && f.record_id) {
              fellowsBySlug.set(f.record_id, f);
            }
          });
          if (!results.length) {
            directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search.</p>';
            setSearchStatus('');
          } else {
            renderDirectoryList(results);
            displayedList = results;
            setSearchStatus(results.length + ' result' + (results.length === 1 ? '' : 's') + ' found');
          }
        })
        .catch(function () {
          setSearchStatus('Search failed.');
        });
      return;
    }
    if (!navigator.onLine) {
      setSearchStatus('Offline search (cached data)…');
      runLocalSearch(q);
      return;
    }
    setSearchStatus('Searching…');
    var url = '/api/search?q=' + encodeURIComponent(q);
    fetch(url)
      .then(function (r) {
        if (!r.ok) return [];
        return r.json();
      })
      .then(function (results) {
        if (!Array.isArray(results)) {
          results = [];
        }
        results.forEach(function (f) {
          if (f && f.slug) {
            fellowsBySlug.set(f.slug, f);
          }
          if (f && f.record_id) {
            fellowsBySlug.set(f.record_id, f);
          }
        });
        if (!results.length) {
          directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search.</p>';
          setSearchStatus('');
        } else {
          renderDirectoryList(results);
          displayedList = results;
          setSearchStatus(results.length + ' result' + (results.length === 1 ? '' : 's') + ' found');
        }
      })
      .catch(function () {
        setSearchStatus('Network search failed. Trying cached data…');
        runLocalSearch(q);
      });
  }

  function runLocalSearch(q) {
    loadFullFellows().then(function (fellows) {
      if (!Array.isArray(fellows) || !fellows.length) {
        directoryListEl.innerHTML = '<p class="placeholder">No cached data available for offline search.</p>';
        setSearchStatus('');
        return;
      }
      var results = filterFellowsLocally(fellows, q);
      results.forEach(function (f) {
        if (f && f.slug) {
          fellowsBySlug.set(f.slug, f);
        }
        if (f && f.record_id) {
          fellowsBySlug.set(f.record_id, f);
        }
      });
      if (!results.length) {
        directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search in cached data.</p>';
        setSearchStatus('');
      } else {
        renderDirectoryList(results);
        displayedList = results;
        setSearchStatus(results.length + ' offline result' + (results.length === 1 ? '' : 's') + ' found');
      }
    }).catch(function () {
      directoryListEl.innerHTML = '<p class="placeholder">Offline search failed.</p>';
      setSearchStatus('');
    });
  }

  function filterFellowsLocally(fellows, q) {
    var query = (q || '').toLowerCase();
    if (!query) return fellows.slice();
    var tokens = query.split(/\s+/).filter(Boolean);
    return fellows.filter(function (f) {
      var parts = [
        f.name,
        f.bio_tagline,
        f.cohort,
        f.fellow_type,
        f.search_tags,
        f.currently_based_in,
        f.global_regions_currently_based_in
      ];
      var haystack = parts
        .map(function (v) {
          return v == null ? '' : String(v).toLowerCase();
        })
        .join(' ');
      for (var i = 0; i < tokens.length; i++) {
        if (haystack.indexOf(tokens[i]) === -1) {
          return false;
        }
      }
      return true;
    });
  }

  function saveFullFellowsToIndexedDB(fellows) {
    if (!window.indexedDB || !Array.isArray(fellows)) return;
    var request = window.indexedDB.open('fellows-local-db', 1);
    request.onupgradeneeded = function (event) {
      var db = event.target.result;
      if (!db.objectStoreNames.contains('meta')) {
        db.createObjectStore('meta', { keyPath: 'id' });
      }
    };
    request.onsuccess = function (event) {
      var db = event.target.result;
      var tx = db.transaction('meta', 'readwrite');
      var store = tx.objectStore('meta');
      store.put({ id: 'allFellows', data: fellows });
      tx.oncomplete = function () {
        db.close();
      };
    };
    request.onerror = function () {
      // Ignore IndexedDB errors; app still works without offline cache.
    };
  }

  function loadFullFellows() {
    if (fullFellowsCache && Array.isArray(fullFellowsCache)) {
      return Promise.resolve(fullFellowsCache);
    }
    if (!window.indexedDB) {
      return Promise.resolve([]);
    }
    return new Promise(function (resolve, reject) {
      var request = window.indexedDB.open('fellows-local-db', 1);
      request.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains('meta')) {
          db.createObjectStore('meta', { keyPath: 'id' });
        }
      };
      request.onsuccess = function (event) {
        var db = event.target.result;
        var tx = db.transaction('meta', 'readonly');
        var store = tx.objectStore('meta');
        var getReq = store.get('allFellows');
        getReq.onsuccess = function () {
          var record = getReq.result;
          var data = record && Array.isArray(record.data) ? record.data : [];
          fullFellowsCache = data;
          resolve(data);
        };
        getReq.onerror = function () {
          resolve([]);
        };
        tx.oncomplete = function () {
          db.close();
        };
      };
      request.onerror = function () {
        resolve([]);
      };
    });
  }

  function handleSearchInput() {
    if (!searchInputEl) return;
    var raw = searchInputEl.value || '';
    var q = raw.trim();
    runSearch(q);
  }

  function hasWindowAI() {
    return typeof window !== 'undefined' && window.ai;
  }

  function handleNlSearchClick() {
    if (!nlSearchInputEl) return;
    var query = (nlSearchInputEl.value || '').trim();
    if (!query) {
      setNlSearchStatus('Enter a question to search.');
      return;
    }
    if (!hasWindowAI()) {
      setNlSearchStatus('window.ai is not available in this browser.');
      return;
    }
    setNlSearchStatus('Asking model…');
    var prompt =
      'You help search a fellows directory stored in a SQLite FTS5 table named fellows_fts. ' +
      'Indexed columns include: name, bio_tagline, cohort, fellow_type, search_tags, key_links, ' +
      'currently_based_in, global_regions_currently_based_in. ' +
      'The user will describe who they are looking for in natural language. ' +
      'Your job is to translate this into a SINGLE MATCH string for SQLite FTS5 over those columns. ' +
      'Prefer combining short keywords with AND and OR. Do NOT return explanations, commentary, or code fences. ' +
      'Do NOT wrap the result in quotes. Return only the bare search string on the first line. ' +
      'Examples of valid outputs: Aaron; investor AND climate; cohort:2019 AND investor; "New Zealand" AND blockchain; women AND investor AND climate. ' +
      'User query: ' + query;

    try {
      var ai = window.ai;
      var generate = ai && ai.generateText ? ai.generateText.bind(ai) : null;
      if (!generate) {
        setNlSearchStatus('window.ai does not support text generation in this context.');
        return;
      }
      generate({
        prompt: prompt,
        maxTokens: 32,
        temperature: 0.2
      })
        .then(function (result) {
          var text = '';
          if (typeof result === 'string') {
            text = result;
          } else if (result && typeof result.text === 'string') {
            text = result.text;
          } else if (result && result.choices && result.choices[0] && typeof result.choices[0].text === 'string') {
            text = result.choices[0].text;
          }
          text = (text || '').trim();
          if (!text) {
            setNlSearchStatus('The model did not return a usable search string.');
            return;
          }
          var line = text.split('\n')[0];
          line = line.replace(/["']/g, '');
          if (line.length > 200) {
            line = line.slice(0, 200);
          }
          if (!line) {
            setNlSearchStatus('The model did not return a usable search string.');
            return;
          }
          setNlSearchStatus('Using search: ' + line);
          runSearch(line);
        })
        .catch(function () {
          setNlSearchStatus('Failed to get a response from window.ai.');
        });
    } catch (e) {
      setNlSearchStatus('Failed to use window.ai in this browser.');
    }
  }

  function initWindowAISearch() {
    if (!hasWindowAI()) return;
    if (nlSearchContainerEl) {
      nlSearchContainerEl.classList.remove('hidden');
    }
    if (nlSearchButtonEl) {
      nlSearchButtonEl.addEventListener('click', handleNlSearchClick);
    }
  }

  function updateConnectionBanner() {
    if (!connectionBannerEl) return;
    if (navigator.onLine) {
      connectionBannerEl.textContent = 'You are online.';
      connectionBannerEl.classList.remove('hidden');
      setTimeout(function () {
        connectionBannerEl.classList.add('hidden');
      }, 2000);
    } else {
      connectionBannerEl.textContent = 'You are offline. Showing cached data where available.';
      connectionBannerEl.classList.remove('hidden');
    }
  }

  initSwReloadButton();
  initClearCacheButton();
  initDiagnosticsPanel();

  if (isStandaloneDisplayMode()) {
    bootDebugLines.length = 0;
    if (siteHeaderEl) siteHeaderEl.classList.remove('hidden');
    if (loadingPanelEl) {
      loadingPanelEl.classList.remove('hidden');
    }
    if (loadingEl) {
      loadingEl.classList.remove('hidden');
    }

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', function (ev) {
        var d = ev.data;
        if (
          d &&
          d.type === 'sw-cache-progress' &&
          loadingPanelEl &&
          !loadingPanelEl.classList.contains('hidden') &&
          loadingEl &&
          !loadingEl.classList.contains('hidden')
        ) {
          setSetupStatus('Getting app ready… ' + d.loaded + '/' + d.total);
        }
      });
    }

    tryUnlockFromHash()
      .then(function () { return pickDataProvider(); })
      .then(function (provider) {
        dataProvider = provider;
        bootDebugPush('provider ready kind=' + provider.kind);
        if (provider.kind === 'sqlite') {
          directoryDataSource = 'sqlite';
        }
        setSetupStatus('Loading…');
        return provider.getList();
      })
      .then(function (data) {
        bootDebugPush(
          'getList: OK count=' + (Array.isArray(data) ? data.length : typeof data)
        );
        list = Array.isArray(data) ? data : [];
        renderDirectory();
        route();
        return dataProvider.getFull();
      })
      .then(function (full) {
        bootDebugPush('getFull: OK rows=' + (Array.isArray(full) ? full.length : typeof full));
        if (Array.isArray(full)) {
          fullFellowsCache = full;
          if (directoryDataSource === 'api') {
            saveFullFellowsToIndexedDB(full);
          }
          full.forEach(function (f) {
            if (f.slug) fellowsBySlug.set(f.slug, f);
            if (f.record_id) fellowsBySlug.set(f.record_id, f);
          });
        }
        route();
      })
      .catch(function (err) {
        showBootFailure(err);
      });

    window.addEventListener('hashchange', route);

    window.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'ArrowLeft') {
        var prev = detailEl.querySelector('.fellow-nav-arrow--prev:not(.fellow-nav-arrow--hidden)');
        if (prev) { e.preventDefault(); prev.click(); }
      } else if (e.key === 'ArrowRight') {
        var next = detailEl.querySelector('.fellow-nav-arrow--next:not(.fellow-nav-arrow--hidden)');
        if (next) { e.preventDefault(); next.click(); }
      }
    });

    if (searchInputEl) {
      searchInputEl.addEventListener('input', function () {
        if (searchDebounceId) {
          clearTimeout(searchDebounceId);
        }
        searchDebounceId = setTimeout(function () {
          handleSearchInput();
        }, 250);
      });
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initWindowAISearch);
    } else {
      initWindowAISearch();
    }

    window.addEventListener('online', updateConnectionBanner);
    window.addEventListener('offline', updateConnectionBanner);
    updateConnectionBanner();
  } else {
    tryUnlockFromHash().then(function () {
      startBrowserUx();
    });
  }

  registerServiceWorker();
})();
