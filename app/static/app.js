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
  var hasEmailFilterEl = document.getElementById('has-email-filter');
  var filterCountEl = document.getElementById('filter-count');
  var HAS_EMAIL_FILTER_KEY = 'ehf_has_email_only';
  var hasEmailOnly = loadHasEmailFilter();
  var nlSearchContainerEl = document.getElementById('nl-search-container');
  var nlSearchInputEl = document.getElementById('nl-search-input');
  var nlSearchButtonEl = document.getElementById('nl-search-button');
  var nlSearchStatusEl = document.getElementById('nl-search-status');
  var detailEl = document.getElementById('detail');
  var fullFellowsCache = null;
  // Groups feature: relationships.db schema mirror. The canonical DDL is in
  // app/relationships.py; this string must stay in sync. Bootstrap is
  // idempotent (CREATE TABLE IF NOT EXISTS), so running it on every PWA
  // boot is cheap. The OPFS-stored DB persists across app updates; the
  // schema only adds, never destructively migrates.
  var RELATIONSHIPS_SCHEMA_SQL =
    'CREATE TABLE IF NOT EXISTS groups (' +
    '  id INTEGER PRIMARY KEY,' +
    '  name TEXT NOT NULL,' +
    '  note TEXT NOT NULL DEFAULT \'\',' +
    '  created_at TEXT NOT NULL,' +
    '  updated_at TEXT NOT NULL' +
    ');' +
    'CREATE TABLE IF NOT EXISTS group_members (' +
    '  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,' +
    '  fellow_record_id TEXT NOT NULL,' +
    '  PRIMARY KEY (group_id, fellow_record_id)' +
    ');' +
    'CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);' +
    'CREATE TABLE IF NOT EXISTS fellow_tags (' +
    '  fellow_record_id TEXT NOT NULL,' +
    '  tag TEXT NOT NULL,' +
    '  created_at TEXT NOT NULL,' +
    '  PRIMARY KEY (fellow_record_id, tag)' +
    ');' +
    'CREATE INDEX IF NOT EXISTS idx_fellow_tags_tag ON fellow_tags(tag);' +
    'CREATE TABLE IF NOT EXISTS fellow_notes (' +
    '  fellow_record_id TEXT PRIMARY KEY,' +
    '  body TEXT NOT NULL,' +
    '  updated_at TEXT NOT NULL' +
    ');' +
    'CREATE TABLE IF NOT EXISTS settings (' +
    '  key TEXT PRIMARY KEY,' +
    '  value TEXT' +
    ');';
  var groupRailEl = document.getElementById('group-rail');
  var groupRailEyebrowEl = document.getElementById('group-rail-eyebrow');
  var groupRailTitleEl = document.getElementById('group-rail-title');
  var groupRailTitleIconEl = document.getElementById('group-rail-title-icon');
  var groupRailHelperEl = document.getElementById('group-rail-helper');
  var groupRailMembersEl = document.getElementById('group-rail-members');
  var groupRailCreateEl = document.getElementById('group-rail-create');
  var groupRailStatusEl = document.getElementById('group-rail-status');
  var bulkSelectBarEl = document.getElementById('bulk-select-bar');
  var bulkSelectInputEl = document.getElementById('bulk-select-input');
  var bulkSelectTextEl = document.getElementById('bulk-select-text');
  var GROUP_DRAFT_KEY = 'ehf.group_draft';
  // Drafts persist to localStorage so they survive page reloads and app
  // updates. They are NOT preserved across Clear App Cache (the red button
  // calls localStorage.clear() and only preserves fellows_authenticated_once).
  // That's acceptable: drafts are unsaved by definition. Saved groups go to
  // relationships.db (PR 2+), which lives in OPFS and survives every reset.
  // See docs/persistence_and_upgrades.md for the full state-survival matrix.
  var groupDraft = {
    members: new Set(),       // record_id values picked
    memberNames: {},          // record_id -> display name (for chips)
    title: '',
    titleEdited: false,
    // PR 4: when non-null, the rail is editing an existing saved group
    // instead of composing a new one. editEntrySnapshot is what
    // "cancel edits" restores.
    editingGroupId: null,
    editEntrySnapshot: null   // {name, note, fellow_record_ids: []}
  };
  // In-memory backup of the compose-mode draft while edit mode is active.
  // Restored to groupDraft + localStorage when edit mode exits, so the
  // user's in-progress new group survives a detour into editing an
  // existing one. NOT persisted itself; reload during edit mode re-derives
  // this from the localStorage compose draft (which was last written
  // before edit mode was entered).
  var composeDraftBackup = null;
  var editModeBannerEl = document.getElementById('edit-mode-banner');
  var editModeBannerNameEl = document.getElementById('edit-mode-banner-name');
  var editModeBannerCancelEl = document.getElementById('edit-mode-banner-cancel');
  var editTitlePatchTimer = null;
  var installLandingEl = document.getElementById('install-landing');
  var installGatePrivateEl = document.getElementById('install-gate-private');
  var unlockEmailFormEl = document.getElementById('unlock-email-form');
  var unlockEmailInputEl = document.getElementById('unlock-email');
  var unlockStatusEl = document.getElementById('unlock-status');
  var installButtonEl = document.getElementById('install-pwa-button');
  var installStatusEl = document.getElementById('install-status');
  var iosHintEl = document.getElementById('install-ios-hint');
  var authDebugPrivateEl = document.getElementById('auth-debug-private');
  var authDebugPrivatePreEl = document.getElementById('auth-debug-private-pre');
  var authDebugPrivateCopyEl = document.getElementById('auth-debug-private-copy');
  var authDebugPrivateSendEl = document.getElementById('auth-debug-private-send');
  var authDebugPrivateCopyStatusEl = document.getElementById('auth-debug-private-copy-status');
  var authDebugInstallEl = document.getElementById('auth-debug-install');
  var gateReasonBannerEl = document.getElementById('gate-reason-banner');
  var installUnsupportedHintEl = document.getElementById('install-unsupported-hint');
  var installUseInTabEl = document.getElementById('install-use-in-tab');
  var backToGateLinkEl = document.getElementById('back-to-gate-link');
  var swUpdateBannerEl = document.getElementById('sw-update-banner');
  var swUpdateReloadEl = document.getElementById('sw-update-reload');
  var siteHeaderEl = document.getElementById('site-header');
  // Mobile shell (≤1024px): appbar + tab strip + kebab sheet. Hidden on
  // desktop via CSS, hidden during install/boot via the same .hidden
  // toggle as siteHeaderEl. setShellVisible() keeps the three in lockstep.
  var appbarEl = document.getElementById('appbar');
  var appbarTitleEl = document.getElementById('appbar-title');
  var appbarKebabEl = document.getElementById('appbar-kebab');
  var tabsEl = document.getElementById('tabs');
  var kebabSheetEl = document.getElementById('kebab-sheet');
  var kebabScrimEl = document.getElementById('kebab-scrim');
  // PR 2 of the mobile redesign: FAB-driven composer sheet + per-card
  // kebab on the groups index + group-detail action-bar overflow sheet.
  // All three reuse the .sheet / .sheet-scrim CSS pattern landed in PR 1.
  var composerFabEl = document.getElementById('composer-fab');
  var composerFabCountEl = document.getElementById('composer-fab-count');
  var composerScrimEl = document.getElementById('composer-scrim');
  var groupCardSheetEl = document.getElementById('group-card-sheet');
  var groupCardScrimEl = document.getElementById('group-card-scrim');
  var groupActionbarSheetEl = document.getElementById('group-actionbar-sheet');
  var groupActionbarScrimEl = document.getElementById('group-actionbar-scrim');
  var deferredInstallPrompt = null;
  var directoryDataSource = 'api';
  var dataProvider = null;
  var bootDebugLines = [];
  var authDebugLines = [];
  var swLifecycleLog = [];
  var imagePrewarmState = {
    status: 'idle',
    total: 0,
    loaded: 0,
    errors: 0,
    startedAt: null,
    finishedAt: null,
    reason: null
  };
  /** Bump on every meaningful UI / diagnostics change. Rendered in the
   *  always-visible build badge so a dev can tell at a glance which app.js
   *  is actually running vs what the server was deployed with. */
  var FELLOWS_UI_DIAG = '2026-05-02-6a74fa5-initial';

  // Persistent marker: "this origin has been authenticated successfully at
  // least once." Preserved across clearAllAppData. Used by startBrowserUx's
  // catch path so a transient /api/auth/status failure (e.g. 503 during a
  // deploy, or flaky mobile data) does NOT block a previously-authed user
  // behind the scary 'Authentication check failed' panel.
  var AUTH_ONCE_KEY = 'fellows_authenticated_once';

  // The user's "me" email — captured from the magic-link gate submit so
  // the export "email it to me" feature can pre-populate mailto?to=…. Also
  // lives in relationships.settings for durability across Clear App Cache;
  // localStorage is just a fast-read cache that boot mirrors from settings.
  var FELLOWS_SELF_EMAIL_KEY = 'fellows_self_email';

  // Last gate submit, used as a correlation handle in the bug-report body
  // and the gate diag block. Hash matches what deploy/server.py logs as
  // email_hash_prefix in event=send_unlock_email, so a maintainer can join
  // a user report to the journald entry without the email leaving the user.
  var lastSubmitInfo = { emailHashPrefix: null, submittedAt: null };

  function sha256HexBrowser(str) {
    if (!(window.crypto && window.crypto.subtle && window.TextEncoder)) {
      return Promise.resolve(null);
    }
    try {
      var bytes = new TextEncoder().encode(str);
      return window.crypto.subtle.digest('SHA-256', bytes).then(function (buf) {
        var arr = new Uint8Array(buf);
        var hex = '';
        for (var i = 0; i < arr.length; i++) {
          hex += (arr[i] < 16 ? '0' : '') + arr[i].toString(16);
        }
        return hex;
      }).catch(function () { return null; });
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  function getSelfEmail() {
    try { return localStorage.getItem(FELLOWS_SELF_EMAIL_KEY) || ''; }
    catch (e) { return ''; }
  }
  function setSelfEmailLocal(value) {
    try {
      if (value && value.trim()) {
        localStorage.setItem(FELLOWS_SELF_EMAIL_KEY, value.trim());
      } else {
        localStorage.removeItem(FELLOWS_SELF_EMAIL_KEY);
      }
    } catch (e) {}
  }

  function markAuthenticatedOnce() {
    try { localStorage.setItem(AUTH_ONCE_KEY, '1'); } catch (e) {}
  }

  function hasAuthenticatedOnce() {
    try { return localStorage.getItem(AUTH_ONCE_KEY) === '1'; } catch (e) { return false; }
  }

  function initBuildBadge() {
    var clientEl = document.getElementById('build-badge-client');
    if (clientEl) clientEl.textContent = 'app: ' + FELLOWS_UI_DIAG;
  }

  function setBuildBadgeServer(gitSha, builtAt) {
    var serverEl = document.getElementById('build-badge-server');
    var badgeEl = document.getElementById('build-badge');
    if (!serverEl) return;
    var label = gitSha || builtAt || 'unknown';
    serverEl.textContent = 'server: ' + label;
    if (badgeEl && gitSha) {
      // Heuristic: when server exposes a sha, the client constant should have
      // been bumped for any change that reached this server build. A mismatch
      // between "what sha the server reports" and the client constant isn't a
      // hard error, but the highlight class is reserved for future use when we
      // add a client→server mapping.
      badgeEl.classList.remove('build-badge--mismatch');
    }
  }

  function setBuildBadgeServerUnreachable() {
    // Called from the auth-status fallback path when the server is 5xx or
    // network-unreachable. Low-drama label: non-technical users should not
    // read this as "something is broken" — the app continues to work from
    // cached state.
    var serverEl = document.getElementById('build-badge-server');
    if (serverEl) serverEl.textContent = 'server: unreachable';
  }

  // True once the app has fallen back to cached local data because the
  // server refused us (401 / expired session) or was otherwise unreachable
  // during boot. Surface-only flag; the UI uses it to label the badge and
  // show a gentle "using cached data" hint. The user stays in the app.
  var offlineOnlyMode = false;

  function setBuildBadgeOfflineOnly(reason) {
    var serverEl = document.getElementById('build-badge-server');
    if (serverEl) {
      serverEl.textContent = 'server: offline · using cache';
    }
    offlineOnlyMode = true;
    bootDebugPush('entered offline-only mode: ' + (reason || 'unknown'));
  }

  initBuildBadge();
  // Install early so the ring buffer captures errors thrown during the rest
  // of the IIFE setup. Function declaration is hoisted; definition lives
  // further down with the rest of the bug-report module.
  initBugReportErrorCapture();

  // Boot snapshot of /build-meta.json. The hourly update check and the
  // About-page "Check for updates" button both compare against this snapshot
  // to decide whether the server has shipped a newer build since this page
  // was loaded. Populated asynchronously; consumers guard on .git_sha.
  var bootBuildMeta = { git_sha: null, built_at: null, capturedAt: null };
  var updateCheckState = {
    lastAttemptAt: null,
    lastResult: null,
    lastLatestMeta: null
  };

  // Populate the server-side label independently of the auth flow so a dev
  // reading the badge still gets a signal when /api/auth/status is failing.
  function primeServerBadgeFromBuildMeta() {
    try {
      fetch('/build-meta.json', { cache: 'no-cache', credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (meta) {
          if (meta) {
            setBuildBadgeServer(meta.git_sha, meta.built_at);
            if (!bootBuildMeta.git_sha) {
              bootBuildMeta = {
                git_sha: meta.git_sha || null,
                built_at: meta.built_at || null,
                capturedAt: new Date().toISOString()
              };
            }
          }
        })
        .catch(function () {});
    } catch (e) {}
  }
  primeServerBadgeFromBuildMeta();

  // Fetch /build-meta.json and compare to the boot snapshot. If the server
  // has shipped a newer build (different git_sha), surface the existing
  // sw-update-banner so the user can reload into the new version.
  //
  // Returns a Promise resolving to { status, latest?, error? } where status
  // is one of:
  //   'update-available' — server build differs from boot snapshot
  //   'up-to-date'       — server build matches boot snapshot
  //   'no-boot-snapshot' — never captured a boot snapshot (offline at boot)
  //   'error'            — fetch failed or response was not ok
  function checkForServerUpdate() {
    updateCheckState.lastAttemptAt = new Date().toISOString();
    return fetch('/build-meta.json', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (meta) {
        updateCheckState.lastLatestMeta = meta || null;
        if (!bootBuildMeta.git_sha) {
          // First successful fetch: adopt it as the boot snapshot so subsequent
          // polls have something to compare against.
          bootBuildMeta = {
            git_sha: (meta && meta.git_sha) || null,
            built_at: (meta && meta.built_at) || null,
            capturedAt: new Date().toISOString()
          };
          updateCheckState.lastResult = 'no-boot-snapshot';
          return { status: 'no-boot-snapshot', latest: meta };
        }
        var latestSha = meta && meta.git_sha;
        if (latestSha && latestSha !== bootBuildMeta.git_sha) {
          showSwUpdateBanner('server-meta-drift');
          updateCheckState.lastResult = 'update-available';
          return { status: 'update-available', latest: meta };
        }
        updateCheckState.lastResult = 'up-to-date';
        return { status: 'up-to-date', latest: meta };
      })
      .catch(function (err) {
        updateCheckState.lastResult = 'error';
        return { status: 'error', error: err && err.message ? err.message : String(err) };
      });
  }

  // Hourly background check. Runs only once the document is visible and only
  // in standalone PWA mode — a browser-mode visit is transient and doesn't
  // need a poll. Exposed via window for e2e testing.
  var UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000; // 1 hour
  var updateCheckIntervalHandle = null;
  function startUpdateCheckPoll() {
    if (updateCheckIntervalHandle) return;
    if (!isStandaloneDisplayMode()) return;
    updateCheckIntervalHandle = setInterval(function () {
      if (document.hidden) return;
      checkForServerUpdate();
    }, UPDATE_CHECK_INTERVAL_MS);
  }

  function logSwLifecycle(event, detail) {
    swLifecycleLog.push({
      t: new Date().toISOString(),
      event: event,
      detail: detail != null ? detail : null
    });
  }

  function prewarmProfileImages(fellows) {
    if (!Array.isArray(fellows) || !fellows.length) {
      imagePrewarmState.status = 'skipped-empty';
      return Promise.resolve();
    }
    try {
      var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (conn && conn.saveData) {
        imagePrewarmState.status = 'skipped-save-data';
        imagePrewarmState.reason = 'navigator.connection.saveData=true';
        return Promise.resolve();
      }
    } catch (e) {}

    var eligible = fellows.filter(function (f) {
      return (f.has_image === 1 || f.has_image === true) && f.slug;
    });
    imagePrewarmState.total = eligible.length;
    imagePrewarmState.loaded = 0;
    imagePrewarmState.errors = 0;
    imagePrewarmState.status = 'running';
    imagePrewarmState.startedAt = new Date().toISOString();

    if (!eligible.length) {
      imagePrewarmState.status = 'done';
      imagePrewarmState.finishedAt = new Date().toISOString();
      return Promise.resolve();
    }

    var queue = eligible.slice();
    var CONCURRENCY = 6;

    function next() {
      var f = queue.shift();
      if (!f) return null;
      // Same cache-busting suffix as <img src> in renderDetail — keeps the
      // prewarm and the on-demand render aligned so we hit one cache entry.
      var jpgUrl = '/images/' + encodeURIComponent(f.slug) + '.jpg?v=' + encodeURIComponent(FELLOWS_UI_DIAG);
      var pngUrl = '/images/' + encodeURIComponent(f.slug) + '.png?v=' + encodeURIComponent(FELLOWS_UI_DIAG);
      // Try .jpg first. If 404 / not-ok, fall back to .png — some fellows
      // have only a .png on disk (they uploaded a PNG on Knack), and
      // without this fallback the prewarm never caches them. Mirrors the
      // same .jpg→.png fallback that renderDetail already does when the
      // on-page <img> errors.
      return fetch(jpgUrl, { cache: 'default', credentials: 'same-origin' })
        .then(function (r) {
          if (r && r.ok) {
            imagePrewarmState.loaded += 1;
            return;
          }
          return fetch(pngUrl, { cache: 'default', credentials: 'same-origin' })
            .then(function (r2) {
              if (r2 && r2.ok) {
                imagePrewarmState.loaded += 1;
              } else {
                imagePrewarmState.errors += 1;
              }
            })
            .catch(function () { imagePrewarmState.errors += 1; });
        })
        .catch(function () {
          // Total network failure on .jpg — try .png anyway.
          return fetch(pngUrl, { cache: 'default', credentials: 'same-origin' })
            .then(function (r2) {
              if (r2 && r2.ok) {
                imagePrewarmState.loaded += 1;
              } else {
                imagePrewarmState.errors += 1;
              }
            })
            .catch(function () { imagePrewarmState.errors += 1; });
        })
        .then(next);
    }

    var starters = [];
    for (var i = 0; i < CONCURRENCY; i++) starters.push(next());
    return Promise.all(starters).then(function () {
      imagePrewarmState.status = 'done';
      imagePrewarmState.finishedAt = new Date().toISOString();
    });
  }

  // Throttled resume hook. When the browser transitions to online, re-run
  // the prewarm so any images that failed during a flaky-network window
  // get another chance. Browser + SW cache mean already-cached images
  // resolve fast without network; only misses actually hit prod.
  //
  // Floor of 60s between attempts so mobile radio flapping doesn't hammer
  // the server. Only runs if we have fellows data loaded AND the previous
  // attempt finished with errors (or was mid-flight but stalled).
  var _lastPrewarmAttempt = 0;
  function maybeResumePrewarm() {
    if (!Array.isArray(fullFellowsCache) || !fullFellowsCache.length) return;
    var now = Date.now();
    if (now - _lastPrewarmAttempt < 60000) return;
    // Don't bother re-running if everything was already captured.
    if (imagePrewarmState.status === 'done' && imagePrewarmState.errors === 0) return;
    _lastPrewarmAttempt = now;
    prewarmProfileImages(fullFellowsCache).catch(function () {});
  }
  window.addEventListener('online', maybeResumePrewarm);

  function countCachedImages() {
    if (!('caches' in self)) return Promise.resolve(null);
    return caches.keys().then(function (keys) {
      var imagesKey = keys.indexOf('fellows-images-v1') !== -1
        ? 'fellows-images-v1'
        : keys.filter(function (k) { return k.indexOf('fellows-') === 0; })[0];
      if (!imagesKey) return { key: null, count: 0 };
      return caches.open(imagesKey).then(function (c) {
        return c.keys().then(function (reqs) {
          var count = 0;
          for (var i = 0; i < reqs.length; i++) {
            if (reqs[i].url.indexOf('/images/') !== -1) count += 1;
          }
          return { key: imagesKey, count: count };
        });
      });
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
    'global_regions_currently_based_in',
    'has_image'
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

  /** Run a non-SELECT statement (INSERT/UPDATE/DELETE). Used by the groups
   *  data layer; the fellows side is read-only and uses dbSelect* only. */
  function dbRun(db, sql, bind) {
    var st = db.prepare(sql);
    try {
      if (bind !== undefined && bind !== null) {
        st.bind(bind);
      }
      st.step();
    } finally {
      st.finalize();
    }
  }

  function bootstrapRelationshipsSchema(relDb) {
    // exec accepts multi-statement scripts; idempotent thanks to IF NOT EXISTS.
    relDb.exec(RELATIONSHIPS_SCHEMA_SQL);
    relDb.exec('PRAGMA user_version = 1');
  }

  function nowIsoSecond() {
    return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  }

  function dedupeRecordIds(ids) {
    var seen = {};
    var out = [];
    if (!ids) return out;
    for (var i = 0; i < ids.length; i++) {
      var rid = ids[i];
      if (typeof rid !== 'string') continue;
      var s = rid.replace(/^\s+|\s+$/g, '');
      if (!s || seen[s]) continue;
      seen[s] = 1;
      out.push(s);
    }
    return out;
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

  function createSqliteDataProvider(db, relDb, poolUtil) {
    function attachMemberNames(rows) {
      // OPFS path skips ATTACH between SAH-pool databases; instead we
      // resolve fellow names from the in-memory cache populated by
      // getList/getFull on boot. Rows arrive as [{record_id}], leave as
      // [{record_id, name}].
      return rows.map(function (m) {
        var rid = m.record_id;
        var fellow = fellowsBySlug.get(rid);
        return { record_id: rid, name: fellow ? fellow.name : rid };
      });
    }

    function readGroupWithMembers(gid) {
      var row = dbSelectOne(relDb, 'SELECT * FROM groups WHERE id = ?', [gid]);
      if (!row) return null;
      var members = dbSelectAll(
        relDb,
        'SELECT fellow_record_id AS record_id FROM group_members WHERE group_id = ?',
        [gid]
      );
      // Sort members by resolved name (or record_id fallback) so the order
      // matches the dev API's COALESCE(fl.name, gm.fellow_record_id).
      var withNames = attachMemberNames(members);
      withNames.sort(function (a, b) {
        var an = (a.name || '').toLowerCase();
        var bn = (b.name || '').toLowerCase();
        return an < bn ? -1 : (an > bn ? 1 : 0);
      });
      row.members = withNames;
      return row;
    }

    return {
      kind: 'sqlite',
      getList: function () {
        var rows = dbSelectAll(
          db,
          'SELECT record_id, slug, name,' +
            " CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END" +
            ' AS has_contact_email' +
            ' FROM fellows ORDER BY name ASC',
          null
        );
        return Promise.resolve(rows.map(function (r) {
          return {
            record_id: r.record_id,
            slug: r.slug,
            name: r.name,
            has_contact_email: r.has_contact_email === 1 || r.has_contact_email === true
          };
        }));
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
      },

      // ===== Groups =================================================
      // Mirrors the /api/groups REST shape. relDb is the OPFS-stored
      // relationships.db opened by initOpfsDataProvider.
      listGroups: function () {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        var rows = dbSelectAll(
          relDb,
          'SELECT g.id, g.name, g.note, g.created_at, g.updated_at, ' +
            'COUNT(gm.fellow_record_id) AS count ' +
            'FROM groups g ' +
            'LEFT JOIN group_members gm ON gm.group_id = g.id ' +
            'GROUP BY g.id ' +
            'ORDER BY g.updated_at DESC, g.id DESC',
          null
        );
        return Promise.resolve(rows);
      },
      getGroup: function (id) {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        return Promise.resolve(readGroupWithMembers(id));
      },
      createGroup: function (data) {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        var name = data && data.name;
        var note = (data && typeof data.note === 'string') ? data.note : '';
        var ids = dedupeRecordIds(data && data.fellow_record_ids);
        var now = nowIsoSecond();
        relDb.exec('BEGIN');
        try {
          dbRun(
            relDb,
            'INSERT INTO groups(name, note, created_at, updated_at) VALUES (?, ?, ?, ?)',
            [name, note, now, now]
          );
          var idRow = dbSelectOne(relDb, 'SELECT last_insert_rowid() AS id', null);
          var gid = idRow && idRow.id;
          for (var i = 0; i < ids.length; i++) {
            dbRun(
              relDb,
              'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)',
              [gid, ids[i]]
            );
          }
          relDb.exec('COMMIT');
          return Promise.resolve(readGroupWithMembers(gid));
        } catch (e) {
          try { relDb.exec('ROLLBACK'); } catch (e2) {}
          return Promise.reject(e);
        }
      },
      updateGroup: function (id, patch) {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
        if (!existing) return Promise.resolve(null);
        var sets = ['updated_at = ?'];
        var params = [nowIsoSecond()];
        if (patch && typeof patch.name === 'string') {
          sets.push('name = ?');
          params.push(patch.name);
        }
        if (patch && typeof patch.note === 'string') {
          sets.push('note = ?');
          params.push(patch.note);
        }
        params.push(id);
        relDb.exec('BEGIN');
        try {
          dbRun(
            relDb,
            'UPDATE groups SET ' + sets.join(', ') + ' WHERE id = ?',
            params
          );
          if (patch && Array.isArray(patch.fellow_record_ids)) {
            dbRun(relDb, 'DELETE FROM group_members WHERE group_id = ?', [id]);
            var ids = dedupeRecordIds(patch.fellow_record_ids);
            for (var i = 0; i < ids.length; i++) {
              dbRun(
                relDb,
                'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)',
                [id, ids[i]]
              );
            }
          }
          relDb.exec('COMMIT');
          return Promise.resolve(readGroupWithMembers(id));
        } catch (e) {
          try { relDb.exec('ROLLBACK'); } catch (e2) {}
          return Promise.reject(e);
        }
      },
      deleteGroup: function (id) {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
        if (!existing) return Promise.resolve(false);
        dbRun(relDb, 'DELETE FROM groups WHERE id = ?', [id]);
        return Promise.resolve(true);
      },
      getSetting: function (key) {
        if (!relDb) return Promise.resolve(null);
        var row = dbSelectOne(relDb, 'SELECT value FROM settings WHERE key = ?', [key]);
        return Promise.resolve(row ? row.value : null);
      },
      getSettings: function () {
        if (!relDb) return Promise.resolve({});
        var rows = dbSelectAll(relDb, 'SELECT key, value FROM settings', null);
        var bag = {};
        rows.forEach(function (r) { bag[r.key] = r.value; });
        return Promise.resolve(bag);
      },
      setSetting: function (key, value) {
        if (!relDb) return Promise.reject(new Error('relationships db not open'));
        if (value === null || value === undefined || value === '') {
          dbRun(relDb, 'DELETE FROM settings WHERE key = ?', [key]);
        } else {
          dbRun(
            relDb,
            'INSERT INTO settings(key, value) VALUES (?, ?)' +
            ' ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            [key, value]
          );
        }
        return Promise.resolve({ key: key, value: value });
      },
      // Hands the user the live relationships.db file as bytes so the
      // Settings UI can offer a download. SAH-pool supports reads while
      // the DB is open; sqlite locks are file-level and exportFile() is
      // a snapshot read.
      exportRelationshipsBytes: function () {
        if (!poolUtil) return Promise.reject(new Error('pool util unavailable'));
        try {
          return Promise.resolve(poolUtil.exportFile('relationships.db'));
        } catch (e) {
          return Promise.reject(e);
        }
      },
      // Read-only validation of a candidate file. Returns
      // {valid, error?, counts?} where counts mirrors the live row
      // counts so the Settings UI can render a delta in the confirm
      // dialog before importRelationshipsBytes touches anything.
      inspectRelationshipsBytes: function (bytes) {
        if (!poolUtil) return Promise.reject(new Error('pool util unavailable'));
        return inspectRelationshipsBytes(poolUtil, bytes);
      },
      // Live row counts on the open relationships.db, for the "current"
      // side of the restore confirm dialog's row-count delta.
      countRelationships: function () {
        if (!relDb) return Promise.resolve(null);
        try {
          return Promise.resolve({
            groups: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM groups', null).n,
            members: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM group_members', null).n,
            tags: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
            notes: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
            settings: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM settings', null).n
          });
        } catch (e) {
          return Promise.reject(e);
        }
      },
      // Replace the live relationships.db with `bytes`. Validates first,
      // snapshots the current state into the auto-backup rotation slot
      // (so a wrong restore is recoverable from the picker), then
      // closes / replaces / reopens the live OPFS slot. Resolves with
      // the new row counts. Reassigns the closure-captured relDb so
      // every other provider method (listGroups, getSetting, etc.)
      // sees the new handle without a page reload.
      importRelationshipsBytes: function (bytes) {
        if (!poolUtil) return Promise.reject(new Error('pool util unavailable'));
        return inspectRelationshipsBytes(poolUtil, bytes).then(function (inspection) {
          if (!inspection.valid) {
            var err = new Error(inspection.error || 'invalid relationships.db file');
            err.invalidBackup = true;
            throw err;
          }
          return snapshotRelationshipsDbToBackup(poolUtil).then(function (snap) {
            return { inspection: inspection, snapshot: snap };
          });
        }).then(function (state) {
          if (relDb) {
            try { relDb.close(); } catch (e) {}
            relDb = null;
          }
          poolUtil.importDb('relationships.db', bytes);
          relDb = new poolUtil.OpfsSAHPoolDb('relationships.db');
          // Belt-and-suspenders: backup might be from a slightly older
          // schema (CREATE IF NOT EXISTS handles it). No-ops on a
          // current backup.
          bootstrapRelationshipsSchema(relDb);
          return {
            counts: state.inspection.counts,
            preRestoreSnapshot: state.snapshot && state.snapshot.backedUp
              ? state.snapshot.name
              : null
          };
        });
      },
      // List on-device auto-backups for the "Recent auto-backups"
      // picker. Each entry is enriched with the row counts inside the
      // backup so the user can pick by content, not just timestamp.
      // Enrichment runs SEQUENTIALLY — every inspect call writes to
      // the shared restore-staging SAH-pool slot, so parallel calls
      // would clobber each other.
      listRelationshipsBackups: function () {
        if (!poolUtil) return Promise.resolve([]);
        return listRelationshipsBackups().then(function (raw) {
          function enrichOne(entry) {
            return _opfsReadBinary(entry.name).then(function (bytes) {
              return inspectRelationshipsBytes(poolUtil, bytes).then(function (insp) {
                return {
                  name: entry.name,
                  size: entry.size,
                  lastModified: entry.lastModified,
                  counts: insp.valid ? insp.counts : null,
                  invalid: !insp.valid,
                  error: insp.valid ? null : insp.error
                };
              });
            }).catch(function (e) {
              return {
                name: entry.name,
                size: entry.size,
                lastModified: entry.lastModified,
                counts: null,
                invalid: true,
                error: (e && e.message) || String(e)
              };
            });
          }
          var chain = Promise.resolve([]);
          raw.forEach(function (entry) {
            chain = chain.then(function (acc) {
              return enrichOne(entry).then(function (one) {
                acc.push(one);
                return acc;
              });
            });
          });
          return chain;
        });
      },
      // Restore one of the on-device auto-backups by name. Reads the
      // bytes from OPFS root, then funnels through importRelationshipsBytes
      // (which handles validation + pre-restore snapshot + replace).
      restoreRelationshipsBackup: function (backupName) {
        var self = this;
        if (!poolUtil) return Promise.reject(new Error('pool util unavailable'));
        return listRelationshipsBackups().then(function (backups) {
          var match = null;
          for (var i = 0; i < backups.length; i++) {
            if (backups[i].name === backupName) { match = backups[i]; break; }
          }
          if (!match) {
            throw new Error('Backup not found: ' + backupName);
          }
          return _opfsReadBinary(backupName);
        }).then(function (bytes) {
          return self.importRelationshipsBytes(bytes);
        });
      }
    };
  }

  // Errors thrown by the API provider carry the HTTP status so the boot
  // chain can react (e.g., fall back to the IndexedDB cache on a 401 instead
  // of showing a boot-failure panel).
  function apiError(url, status) {
    var err = new Error('GET ' + url + ' failed: ' + status);
    err.status = status;
    return err;
  }

  // Thrown by the API provider when groups/settings endpoints don't exist
  // on this server (production deploy/server.py) AND the OPFS path was
  // unavailable (browser too old, missing sqlite3.wasm, insecure context,
  // …). Render paths catch this and show the unsupported-browser panel
  // built by renderLocalDataUnavailablePanel(). See docs/browser_support.md.
  function localDataUnavailableError(reason) {
    var err = new Error('local user data unavailable: ' + (reason || 'unknown'));
    err.localDataUnavailable = true;
    err.reason = reason || 'unknown';
    return err;
  }

  // OPFS + SQLite-WASM (FileSystemSyncAccessHandle) version floors. Used by
  // renderLocalDataUnavailablePanel to tell the user exactly what version
  // they need. If you bump sqlite3.wasm and the floors shift, update these
  // and docs/browser_support.md together.
  var OPFS_MIN_VERSIONS = {
    chrome: 102,   // FileSystemSyncAccessHandle landed Chrome 102 (May 2022)
    edge: 102,     // Same engine as Chrome
    safari: 16.4,  // iOS/macOS Safari 16.4 (Mar 2023) — first OPFS+SAH release
    firefox: 111   // Firefox 111 (Mar 2023)
  };

  // Best-effort UA parsing. Modern UA-CH would be cleaner but is not
  // available in Safari. We use the parsed values only to build a helpful
  // message — never to gate features (the OPFS capability gates do that
  // directly via shouldTryOpfsProvider). Returns:
  //   { name: 'chrome'|'edge'|'safari'|'firefox'|'opera'|'samsung'|'unknown',
  //     version: number|null,  // major.minor as float for safari, integer otherwise
  //     versionString: string,  // raw version captured from UA
  //     onIos: boolean,         // iPhone/iPad/iPod, including iPadOS desktop UA
  //     minVersion: number|null // floor for this browser, or null if unknown
  //   }
  function detectBrowserSupport() {
    var ua = (navigator.userAgent || '');
    var onIos = /iPad|iPhone|iPod/.test(ua) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    var name = 'unknown';
    var versionString = '';
    var version = null;
    var m;
    // Order matters — Edge/Opera/Samsung UA strings also contain "Chrome".
    if ((m = ua.match(/EdgiOS\/([\d.]+)/)) || (m = ua.match(/Edg(?:e|A|iOS)?\/([\d.]+)/))) {
      name = 'edge';
      versionString = m[1];
    } else if ((m = ua.match(/OPR\/([\d.]+)/)) || (m = ua.match(/Opera\/([\d.]+)/))) {
      name = 'opera';
      versionString = m[1];
    } else if ((m = ua.match(/SamsungBrowser\/([\d.]+)/))) {
      name = 'samsung';
      versionString = m[1];
    } else if ((m = ua.match(/FxiOS\/([\d.]+)/)) || (m = ua.match(/Firefox\/([\d.]+)/))) {
      name = 'firefox';
      versionString = m[1];
    } else if ((m = ua.match(/CriOS\/([\d.]+)/)) || (m = ua.match(/Chrome\/([\d.]+)/))) {
      name = 'chrome';
      versionString = m[1];
    } else if ((m = ua.match(/Version\/([\d.]+).*Safari/))) {
      name = 'safari';
      versionString = m[1];
    }
    if (versionString) {
      // For Safari, capture major.minor (e.g. 16.4); for others, the major
      // is enough — but parseFloat handles both consistently.
      version = parseFloat(versionString);
      if (isNaN(version)) version = null;
    }
    return {
      name: name,
      version: version,
      versionString: versionString,
      onIos: onIos,
      minVersion: OPFS_MIN_VERSIONS[name] != null ? OPFS_MIN_VERSIONS[name] : null
    };
  }

  // Build the "your browser can't store groups locally" panel. Returns an
  // HTML string. Caller decides which container to drop it into.
  // `feature` is what the user was trying to do — "groups", "this group",
  // "settings", "save this group". Used in the headline only.
  function renderLocalDataUnavailablePanel(feature) {
    var b = detectBrowserSupport();
    var label = feature || 'this feature';
    var browserHuman =
      b.name === 'chrome' ? 'Chrome' :
      b.name === 'edge' ? 'Edge' :
      b.name === 'safari' ? 'Safari' :
      b.name === 'firefox' ? 'Firefox' :
      b.name === 'opera' ? 'Opera' :
      b.name === 'samsung' ? 'Samsung Internet' :
      'your browser';
    var versionTxt = b.versionString ? (' ' + b.versionString) : '';
    var detailLines = [];
    if (b.onIos) {
      // iOS forces every browser engine to WebKit, so the only fix is to
      // upgrade iOS itself (iOS 16.4+ ships Safari 16.4+).
      detailLines.push(
        'You\'re on an iPhone or iPad. iOS uses Safari\'s engine for every browser, ' +
        'so changing browsers won\'t help — only an iOS upgrade will. ' +
        'Update to <b>iOS 16.4 or newer</b> in <i>Settings → General → Software Update</i>, ' +
        'then reload this page. (iPhone 8 and newer support iOS 16.4+; iPhone 7 and older do not.)'
      );
      detailLines.push(
        'If you can\'t upgrade iOS on this device, open this app on a desktop or laptop ' +
        'using Chrome 102+, Edge 102+, Safari 16.4+, or Firefox 111+.'
      );
    } else if (b.name === 'safari') {
      detailLines.push(
        'You\'re running ' + browserHuman + versionTxt + '. ' +
        'This app needs <b>Safari 16.4 or newer</b> on macOS 13.3+ ' +
        '(<i>Apple menu → System Settings → General → Software Update</i>).'
      );
      detailLines.push(
        'If you can\'t upgrade macOS, install the latest <b>Chrome</b>, <b>Edge</b>, or <b>Firefox</b> ' +
        'on this Mac and open the app there instead.'
      );
    } else if (b.name === 'chrome' || b.name === 'edge') {
      detailLines.push(
        'You\'re running ' + browserHuman + versionTxt + '. ' +
        'This app needs <b>' + browserHuman + ' 102 or newer</b> ' +
        '(open the menu → Help → About ' + browserHuman + ' to update).'
      );
      detailLines.push(
        'If your operating system can\'t run a current ' + browserHuman + ', try installing the latest <b>Firefox</b> ' +
        '— or use a different device with a current browser.'
      );
    } else if (b.name === 'firefox') {
      detailLines.push(
        'You\'re running ' + browserHuman + versionTxt + '. ' +
        'This app needs <b>Firefox 111 or newer</b> ' +
        '(menu → Help → About Firefox to update).'
      );
      detailLines.push(
        'You can also use the latest <b>Chrome</b>, <b>Edge</b>, or <b>Safari 16.4+</b>.'
      );
    } else if (b.name === 'opera' || b.name === 'samsung') {
      detailLines.push(
        'You\'re running ' + browserHuman + versionTxt + '. ' +
        'This app hasn\'t been verified on ' + browserHuman + '; even up-to-date versions may not support ' +
        'the local-storage feature it needs.'
      );
      detailLines.push(
        'Open the app in <b>Chrome 102+</b>, <b>Edge 102+</b>, <b>Safari 16.4+</b>, or <b>Firefox 111+</b> instead.'
      );
    } else {
      detailLines.push(
        'Couldn\'t identify your browser, but the local-storage feature this app needs ' +
        '(<a href="https://caniuse.com/native-filesystem-api" target="_blank" rel="noopener">OPFS with SyncAccessHandle</a>) ' +
        'isn\'t available here.'
      );
      detailLines.push(
        'Open the app in <b>Chrome 102+</b>, <b>Edge 102+</b>, <b>Safari 16.4+</b>, or <b>Firefox 111+</b>.'
      );
    }
    if (!globalThis.isSecureContext) {
      detailLines.unshift(
        'This page isn\'t in a secure context, which the local-storage feature requires. ' +
        'Open <code>https://fellows.globaldonut.com/</code> directly (not over an http:// link or a file:// path).'
      );
    }
    var detailHtml = detailLines.map(function (l) { return '<p>' + l + '</p>'; }).join('');
    return (
      '<div class="local-data-unavailable">' +
        '<h3>Can\'t open ' + escapeHtml(label) + ' on this browser</h3>' +
        '<p class="local-data-unavailable-lede">' +
          'Saved groups and per-device settings live in your browser\'s local storage. ' +
          'On this device, that storage isn\'t available — so the rest of the app works, but ' +
          escapeHtml(label) + ' can\'t.' +
        '</p>' +
        detailHtml +
        '<p class="local-data-unavailable-foot">' +
          'If none of these options work for you, please reach out — we\'re happy to help.' +
        '</p>' +
      '</div>'
    );
  }

  function createApiDataProvider() {
    function jsonOr(url, opts, expectedShapeOnEmpty) {
      return fetch(url, opts || {}).then(function (r) {
        if (r.status === 204) return expectedShapeOnEmpty;
        if (!r.ok) throw apiError(url, r.status);
        return r.json();
      });
    }

    // Production (deploy/server.py) does not serve /api/groups or
    // /api/settings — OPFS is the canonical store for those. When OPFS
    // capability gates fail (older browser, insecure context, …) we
    // land on this provider on prod and need to surface a helpful
    // unsupported-browser panel rather than a generic "Could not load
    // groups." error. The collection endpoint /api/groups is the
    // unambiguous probe: dev returns 200 (`[]` if empty), prod returns
    // 404 (no route). Cache the result so per-id 404s on getGroup,
    // updateGroup, etc. can be disambiguated correctly:
    //  - groupsRouteSupported === true  → 404 means "id not found"
    //  - groupsRouteSupported === false → all groups/settings calls
    //                                     reject with localDataUnavailable
    //  - groupsRouteSupported === null  → not yet probed; settings
    //                                     methods do their own probe
    //                                     before the first call
    var groupsRouteSupported = null; // null | true | false
    function probeGroupsRoute() {
      if (groupsRouteSupported !== null) {
        return Promise.resolve(groupsRouteSupported);
      }
      return fetch('/api/groups').then(function (r) {
        if (r.status === 404) {
          groupsRouteSupported = false;
        } else {
          groupsRouteSupported = true;
        }
        return groupsRouteSupported;
      }).catch(function () {
        // Network error: don't lock the user out. Treat as "supported"
        // and let the actual call surface a real error.
        groupsRouteSupported = true;
        return true;
      });
    }
    function rejectIfUnsupported() {
      if (groupsRouteSupported === false) {
        return Promise.reject(localDataUnavailableError('server-no-local-data'));
      }
      return probeGroupsRoute().then(function (ok) {
        if (!ok) throw localDataUnavailableError('server-no-local-data');
        return true;
      });
    }
    return {
      kind: 'api',
      getList: function () {
        return fetch('/api/fellows').then(function (r) {
          if (!r.ok) {
            pushBugReportError('http', 'GET /api/fellows → ' + r.status);
            throw apiError('/api/fellows', r.status);
          }
          return r.json();
        });
      },
      getFull: function () {
        return fetch('/api/fellows?full=1').then(function (r) {
          if (!r.ok) {
            pushBugReportError('http', 'GET /api/fellows?full=1 → ' + r.status);
            throw apiError('/api/fellows?full=1', r.status);
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
      },

      // ===== Groups (HTTP fallback) =================================
      // Same JSON shape as the SQLite path. Resolves member names via
      // ATTACHed f.fellows on the dev server. On production
      // (deploy/server.py) these routes don't exist; the OPFS path is
      // the canonical production implementation. When OPFS is also
      // unavailable, every call here rejects with
      // localDataUnavailableError so the UI can render the unsupported-
      // browser panel.
      listGroups: function () {
        // listGroups doubles as the route probe — its 404 is the
        // signal that prod doesn't serve groups.
        return fetch('/api/groups').then(function (r) {
          if (r.status === 404) {
            groupsRouteSupported = false;
            throw localDataUnavailableError('server-no-local-data');
          }
          groupsRouteSupported = true;
          if (r.status === 204) return [];
          if (!r.ok) throw apiError('/api/groups', r.status);
          return r.json();
        });
      },
      getGroup: function (id) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/groups/' + encodeURIComponent(id)).then(function (r) {
            if (r.status === 404) return null; // legitimate "id not found"
            if (!r.ok) throw apiError('/api/groups/' + id, r.status);
            return r.json();
          });
        });
      },
      createGroup: function (data) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(data || {})
          }).then(function (r) {
            if (!r.ok) throw apiError('/api/groups', r.status);
            return r.json();
          });
        });
      },
      updateGroup: function (id, patch) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/groups/' + encodeURIComponent(id), {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(patch || {})
          }).then(function (r) {
            if (r.status === 404) return null;
            if (!r.ok) throw apiError('/api/groups/' + id, r.status);
            return r.json();
          });
        });
      },
      deleteGroup: function (id) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/groups/' + encodeURIComponent(id), {
            method: 'DELETE',
            credentials: 'same-origin'
          }).then(function (r) {
            if (r.status === 204) return true;
            if (r.status === 404) return false;
            throw apiError('/api/groups/' + id, r.status);
          });
        });
      },
      getSetting: function (key) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/settings/' + encodeURIComponent(key)).then(function (r) {
            if (r.status === 404) return null;
            if (!r.ok) throw apiError('/api/settings/' + key, r.status);
            return r.json().then(function (d) { return d && d.value; });
          });
        });
      },
      getSettings: function () {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/settings').then(function (r) {
            if (!r.ok) return {};
            return r.json();
          });
        });
      },
      setSetting: function (key, value) {
        return rejectIfUnsupported().then(function () {
          return fetch('/api/settings/' + encodeURIComponent(key), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ value: value })
          }).then(function (r) {
            if (!r.ok) throw apiError('/api/settings/' + key, r.status);
            return r.json();
          });
        });
      },
      // API path = no OPFS = no local relationships.db to export. The
      // Settings UI hides the download button when this rejects.
      exportRelationshipsBytes: function () {
        return Promise.reject(localDataUnavailableError('export-relationships'));
      },
      // Same story for inspect / import / restore — the Settings UI
      // hides the restore section when listRelationshipsBackups returns
      // []  AND import rejects, so unsupported browsers see only the
      // unsupported-browser panel that already covers groups/settings.
      inspectRelationshipsBytes: function () {
        return Promise.reject(localDataUnavailableError('inspect-relationships'));
      },
      countRelationships: function () {
        return Promise.resolve(null);
      },
      importRelationshipsBytes: function () {
        return Promise.reject(localDataUnavailableError('import-relationships'));
      },
      listRelationshipsBackups: function () {
        return Promise.resolve([]);
      },
      restoreRelationshipsBackup: function () {
        return Promise.reject(localDataUnavailableError('restore-relationships'));
      }
    };
  }

  function shouldTryOpfsProvider() {
    // OPFS is the canonical store for user-authored data (groups,
    // settings) in BOTH standalone PWA and browser-tab modes.
    // Production's deploy/server.py does not serve /api/groups or
    // /api/settings; OPFS is what makes those features work end-to-end
    // for browser-tab visitors. The capability gates below decide
    // whether the visitor's browser can run the OPFS path; if any
    // fails, the API provider takes over (which works on dev) and the
    // groups/settings UI surfaces an unsupported-browser panel on prod
    // via localDataUnavailableError. See docs/browser_support.md.
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
    lines.push('standalone display-mode: ' + isStandaloneDisplayMode() + ' (informational; not a gate)');
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
      // Server-side cookie clear. The session cookie is HttpOnly so JS can't
      // see or unset it — clearCookiesBestEffort() below only handles
      // JS-visible cookies. POST /api/logout asks the server to send a
      // clearing Set-Cookie header. Best-effort: the dev server has no
      // /api/logout endpoint, so this 404s harmlessly there. Done first
      // so the request reaches the network before we tear down caches and
      // unregister the SW.
      try {
        await fetch('/api/logout', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: '{}'
        });
      } catch (e) { /* offline / network — proceed with local clear */ }

      // Preserve the "has ever been authenticated" marker across full reset.
      // Rationale: Clear App Cache is meant to fix "my app is broken," not
      // "log me out of an installed PWA I was happily using." Without this,
      // an intermittent server error after clear + reload drops users into
      // the email gate unnecessarily.
      var preservedAuthMarker = null;
      try { preservedAuthMarker = localStorage.getItem(AUTH_ONCE_KEY); } catch (e) {}
      localStorage.clear();
      sessionStorage.clear();
      if (preservedAuthMarker === '1') {
        try { localStorage.setItem(AUTH_ONCE_KEY, '1'); } catch (e) {}
      }

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

  // Recovery escape hatch beyond Clear App Cache. Wipes OPFS too —
  // meaning the user loses all their saved groups, group notes, fellow
  // tags, and settings. Use only when Clear App Cache hasn't fixed the
  // problem (corrupt OPFS-stored fellows.db, schema-migration glitch,
  // a hard "I want a brand-new install" reset). Also clears the
  // fellows_authenticated_once marker so the next load starts at the
  // email gate as if the URL had never been visited.
  async function clearEverything() {
    try {
      // Server-side cookie clear: see clearAllAppData for the same
      // rationale (HttpOnly cookie can't be touched from JS).
      try {
        await fetch('/api/logout', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: '{}'
        });
      } catch (e) { /* offline / dev / network — proceed */ }

      // OPFS wipe: removes relationships.db (groups + notes + settings),
      // fellows.db (re-imported on next boot anyway), and any sibling
      // files (e.g. relationships.db.bak.* once auto-backup ships).
      // Iterate and removeEntry for each — there is no per-origin
      // "wipe OPFS" API, so we delete each top-level entry by name.
      if (navigator.storage && typeof navigator.storage.getDirectory === 'function') {
        try {
          var root = await navigator.storage.getDirectory();
          var names = [];
          // values() returns an async iterator; collect names first so
          // we don't mutate while iterating.
          if (typeof root.values === 'function') {
            for await (var entry of root.values()) {
              names.push(entry.name);
            }
          }
          for (var i = 0; i < names.length; i++) {
            try {
              await root.removeEntry(names[i], { recursive: true });
            } catch (rmErr) {
              console.error('[Fellows] OPFS removeEntry failed for ' + names[i], rmErr);
            }
          }
        } catch (opfsErr) {
          console.error('[Fellows] OPFS wipe failed:', opfsErr);
        }
      }

      // Full local-storage clear — DON'T preserve AUTH_ONCE_KEY here.
      // Reset Everything is the explicit "treat me like a brand-new
      // install" path; the marker survival in clearAllAppData is for
      // the gentler Clear App Cache flow.
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
          for (var j = 0; j < registrations.length; j++) {
            await registrations[j].unregister();
          }
        } catch (err2) {
          console.error('Error unregistering service workers:', err2);
        }
      }

      clearCookiesBestEffort();
      window.location.replace(
        window.location.pathname + '?cache_reset=full&t=' + Date.now()
      );
    } catch (e) {
      console.error('[Fellows] clearEverything failed:', e);
      try {
        window.location.replace(
          window.location.pathname + '?cache_reset=full-force'
        );
      } catch (e2) {
        window.location.reload();
      }
    }
  }

  window.clearEverything = clearEverything;

  function initClearCacheButton() {
    var btn = document.getElementById('clear-app-cache-button');
    if (!btn) return;
    btn.addEventListener('click', function () {
      Promise.resolve(clearAllAppData()).catch(function (e) {
        console.error('[Fellows] clearAllAppData rejected:', e);
      });
    });
  }

  function initResetEverythingButton() {
    var btn = document.getElementById('reset-everything-button');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var ok = window.confirm(
        'Reset everything?\n\n' +
        'This deletes your saved groups, group notes, fellow tags, and settings, ' +
        'AND signs you out. It is meant for the case where Clear App Cache hasn\'t ' +
        'fixed the problem.\n\n' +
        'Continue?'
      );
      if (!ok) return;
      Promise.resolve(clearEverything()).catch(function (e) {
        console.error('[Fellows] clearEverything rejected:', e);
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
      try {
        var imgStat = await countCachedImages();
        if (imgStat) {
          lines.push(
            'Profile images cached: ' + imgStat.count +
              ' (cache=' + (imgStat.key || '(none)') + ')'
          );
        }
      } catch (e5) {
        lines.push('image-cache count error: ' + String(e5 && e5.message));
      }
      lines.push(
        'Image prewarm: status=' + imagePrewarmState.status +
          ' loaded=' + imagePrewarmState.loaded +
          '/' + imagePrewarmState.total +
          ' errors=' + imagePrewarmState.errors +
          (imagePrewarmState.reason ? ' reason=' + imagePrewarmState.reason : '') +
          (imagePrewarmState.startedAt ? ' started=' + imagePrewarmState.startedAt : '') +
          (imagePrewarmState.finishedAt ? ' finished=' + imagePrewarmState.finishedAt : '')
      );
    }
    lines.push('');
    // Auto-backup snapshot list (PR D). Only meaningful on the OPFS
    // path; on the API/unsupported-browser fallback this section is
    // empty.
    try {
      var backups = await listRelationshipsBackups();
      lines.push('relationships.db backups (newest 3, OPFS-only):');
      if (!backups.length) {
        lines.push('  (none yet)');
      } else {
        var totalBytes = 0;
        for (var bi = 0; bi < backups.length; bi++) {
          var b = backups[bi];
          totalBytes += b.size || 0;
          lines.push(
            '  ' + b.name + ' — ' + (b.size || 0) + ' bytes' +
            (b.lastModified ? ' (mtime ' + new Date(b.lastModified).toISOString() + ')' : '')
          );
        }
        lines.push('  total: ' + totalBytes + ' bytes');
      }
      var lastSha = await _opfsReadText(BACKUP_SENTINEL);
      lines.push('last_seen_sha.txt: ' + (lastSha || '(none)'));
    } catch (bErr) {
      lines.push('backups: list error — ' + String(bErr && bErr.message || bErr));
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

  // ===== Bug-report module ===============================================
  // Lets a user email a diagnostics-rich bug report to the maintainer in two
  // clicks: top-level "Report bug" button → preview-with-edit dialog → Send.
  // Also surfaces inline triggers on the install / gate / boot-error / auth-
  // error panels (the "couldn't even get into the app" surfaces) where the
  // sync-only diagnostics path is the most we can reliably gather.
  //
  // Future: a gmail-to-issues bridge would let us point this at an address
  // that creates a GitHub issue; for now the destination is hardcoded.
  var BUG_REPORT_TO = 'richbodo@gmail.com';
  var BUG_REPORT_RING_MAX = 20;
  var BUG_REPORT_BODY_CAP = 1500;
  var bugReportErrorRing = [];

  function pushBugReportError(kind, msg, extra) {
    try {
      var entry = {
        t: new Date().toISOString(),
        kind: String(kind),
        msg: String(msg == null ? '' : msg).slice(0, 500)
      };
      if (extra != null) entry.extra = String(extra).slice(0, 200);
      bugReportErrorRing.push(entry);
      if (bugReportErrorRing.length > BUG_REPORT_RING_MAX) {
        bugReportErrorRing.shift();
      }
    } catch (e) {}
  }

  function initBugReportErrorCapture() {
    // Wrap console.error so the original logger still runs — we just tee a
    // copy into the ring buffer. Wrapped in try/catch so a failure in the
    // tee can never break console.error itself.
    try {
      var origError = console.error.bind(console);
      console.error = function () {
        try {
          var parts = [];
          for (var i = 0; i < arguments.length; i++) {
            var a = arguments[i];
            if (a == null) {
              parts.push(String(a));
            } else if (a instanceof Error) {
              parts.push(a.message + (a.stack ? '\n' + a.stack : ''));
            } else if (typeof a === 'object') {
              try { parts.push(JSON.stringify(a)); }
              catch (je) { parts.push(String(a)); }
            } else {
              parts.push(String(a));
            }
          }
          pushBugReportError('console.error', parts.join(' '));
        } catch (e) {}
        return origError.apply(null, arguments);
      };
    } catch (e) {}
    try {
      window.addEventListener('error', function (event) {
        var msg = (event && event.message) ||
          (event && event.error && event.error.message) || 'window error';
        var loc = (event.filename || '') + ':' +
          (event.lineno != null ? event.lineno : '?') + ':' +
          (event.colno != null ? event.colno : '?');
        pushBugReportError('window.error', msg, loc);
      });
    } catch (e) {}
    try {
      window.addEventListener('unhandledrejection', function (event) {
        var reason = event && event.reason;
        var msg;
        if (reason instanceof Error) {
          msg = reason.message + (reason.stack ? '\n' + reason.stack : '');
        } else {
          msg = String(reason);
        }
        pushBugReportError('unhandledrejection', msg);
      });
    } catch (e) {}
  }

  function buildBugReportSyncBody() {
    var lines = [];
    lines.push('--- diagnostics (please leave attached) ---');
    lines.push('time: ' + new Date().toISOString());
    lines.push('app: ' + FELLOWS_UI_DIAG);
    var serverLabel = '(unknown)';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      serverLabel = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    lines.push('server: ' + serverLabel);
    lines.push('url: ' + String(location.href));
    lines.push('route: ' + String(location.hash || '(none)'));
    lines.push('display: ' + (isStandaloneDisplayMode() ? 'standalone' : 'browser-tab'));
    try { lines.push('online: ' + Boolean(navigator.onLine)); } catch (e) {}
    lines.push('userAgent: ' + String(navigator.userAgent || ''));
    try { lines.push('platform: ' + String(navigator.platform || '')); } catch (e) {}
    try { lines.push('language: ' + String(navigator.language || '')); } catch (e) {}
    try {
      lines.push('viewport: ' + window.innerWidth + 'x' + window.innerHeight);
    } catch (e) {}
    try { lines.push('auth_once: ' + hasAuthenticatedOnce()); } catch (e) {}
    try { lines.push('offline_only_mode: ' + offlineOnlyMode); } catch (e) {}
    try {
      lines.push('directoryDataSource: ' +
        (typeof directoryDataSource !== 'undefined' ? directoryDataSource : '(unset)'));
    } catch (e) {}
    if (lastSubmitInfo.emailHashPrefix && lastSubmitInfo.submittedAt) {
      // Join key into deploy/server.py's event=send_unlock_email log.
      lines.push(
        'last_submit: hash=' + lastSubmitInfo.emailHashPrefix +
        '  at ' + lastSubmitInfo.submittedAt
      );
    }
    if (bugReportErrorRing.length === 0) {
      lines.push('recent errors: (none captured)');
    } else {
      lines.push('recent errors (' + bugReportErrorRing.length + '):');
      for (var i = 0; i < bugReportErrorRing.length; i++) {
        var ev = bugReportErrorRing[i];
        var firstLine = ev.msg.split('\n')[0];
        lines.push('  - [' + ev.t + '] ' + ev.kind + ': ' + firstLine);
        if (ev.extra) {
          lines.push('      at ' + ev.extra);
        }
      }
    }
    return lines.join('\n');
  }

  function buildBugReportTemplateBody(syncDiag) {
    var lines = [];
    lines.push('Hi! Thanks for reporting a bug. Please answer what you can — leave anything you don\'t know:');
    lines.push('');
    lines.push('1) What were you trying to do?');
    lines.push('   ');
    lines.push('2) What did you expect to happen?');
    lines.push('   ');
    lines.push('3) What actually happened?');
    lines.push('   ');
    lines.push('');
    lines.push(syncDiag);
    return lines.join('\n');
  }

  function buildBugReportMailtoHref(subject, body) {
    // mailto: URLs get truncated by some mail clients past ~2000 chars
    // post-encoding, so we cap the unencoded body. The full body lives in
    // the textarea and the Copy button — this is just the convenience path.
    var capped = body;
    if (body.length > BUG_REPORT_BODY_CAP) {
      capped = body.slice(0, BUG_REPORT_BODY_CAP) +
        '\n\n[truncated for mailto: — paste the full report from the dialog]';
    }
    return 'mailto:' + encodeURIComponent(BUG_REPORT_TO) +
      '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(capped);
  }

  function openBugReportDialog(opts) {
    opts = opts || {};
    var dialog = document.getElementById('bug-report-dialog');
    var textarea = document.getElementById('bug-report-textarea');
    var sendBtn = document.getElementById('bug-report-send');
    var copyBtn = document.getElementById('bug-report-copy');
    var closeBtn = document.getElementById('bug-report-close');
    var statusEl = document.getElementById('bug-report-status');
    if (!dialog || !textarea) return;

    var subjectId = (bootBuildMeta && bootBuildMeta.git_sha) || FELLOWS_UI_DIAG;
    if (subjectId && subjectId.length > 24) subjectId = subjectId.slice(0, 24);
    var subject = 'EHF Directory bug — ' + subjectId;
    var syncDiag = buildBugReportSyncBody();
    var fullBody = buildBugReportTemplateBody(syncDiag);

    textarea.value = fullBody;
    if (statusEl) statusEl.textContent = '';
    dialog.classList.remove('hidden');
    dialog.setAttribute('aria-hidden', 'false');

    // Focus the first answer line so the user can start typing immediately.
    try {
      textarea.focus();
      var idx = textarea.value.indexOf('1) ');
      if (idx >= 0) {
        var nl = textarea.value.indexOf('\n', idx);
        var caret = nl > 0 ? nl + 4 : textarea.value.length;
        textarea.setSelectionRange(caret, caret);
      }
    } catch (e) {}

    function onSend() {
      var body = textarea.value;
      var href = buildBugReportMailtoHref(subject, body);
      try {
        window.location.href = href;
        if (statusEl) {
          statusEl.textContent =
            'If your mail app didn\'t open, click "Copy to clipboard" and paste into a new email to ' +
            BUG_REPORT_TO + '.';
        }
      } catch (e) {
        if (statusEl) {
          statusEl.textContent = 'Could not open mail app — use Copy to clipboard.';
        }
      }
    }

    function onCopy() {
      var body = textarea.value;
      function fallback() {
        try {
          textarea.select();
          if (document.execCommand && document.execCommand('copy')) {
            if (statusEl) {
              statusEl.textContent = 'Copied. Email it to ' + BUG_REPORT_TO + '.';
            }
            return;
          }
        } catch (e) {}
        if (statusEl) {
          statusEl.textContent =
            'Copy failed — select all in the box above and copy manually, then email to ' +
            BUG_REPORT_TO + '.';
        }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(body).then(function () {
          if (statusEl) {
            statusEl.textContent = 'Copied. Email it to ' + BUG_REPORT_TO + '.';
          }
        }, fallback);
      } else {
        fallback();
      }
    }

    function onClose() {
      dialog.classList.add('hidden');
      dialog.setAttribute('aria-hidden', 'true');
      sendBtn && sendBtn.removeEventListener('click', onSend);
      copyBtn && copyBtn.removeEventListener('click', onCopy);
      closeBtn && closeBtn.removeEventListener('click', onClose);
      dialog.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKey);
    }

    function onBackdrop(ev) {
      if (ev.target === dialog) onClose();
    }

    function onKey(ev) {
      if (ev.key === 'Escape') onClose();
    }

    sendBtn && sendBtn.addEventListener('click', onSend);
    copyBtn && copyBtn.addEventListener('click', onCopy);
    closeBtn && closeBtn.addEventListener('click', onClose);
    dialog.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);

    // In-app surfaces (no syncOnly flag) try to enrich with the heavier
    // diagnostics gather (SW state, /api/auth/status, /api/debug/diagnostics,
    // cache keys) once it returns. Pre-app surfaces skip this because their
    // surrounding context (boot failure, gate, install) means those probes
    // are likely to hang or 5xx.
    if (!opts.syncOnly) {
      var marker = '\n\n--- additional diagnostics ---\n';
      Promise.resolve(collectDiagnosticsText()).then(function (extra) {
        if (dialog.classList.contains('hidden')) return;
        var current = textarea.value;
        if (current.indexOf(syncDiag) === -1) return;  // user replaced it
        if (current.indexOf(marker) !== -1) return;     // already enriched
        textarea.value = current.replace(syncDiag, syncDiag + marker + extra);
      }).catch(function () {
        // Best-effort enrichment; silent failure is fine.
      });
    }
  }

  function initBugReportButtons() {
    var ids = [
      'bug-report-button',
      'bug-report-button-install',
      'bug-report-button-gate',
      'bug-report-button-boot-error',
      'bug-report-button-auth-error'
    ];
    ids.forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var syncOnly = btn.getAttribute('data-sync-only') === '1';
        openBugReportDialog({ syncOnly: syncOnly });
      });
    });
  }

  // ===== Mobile shell: appbar + tabs + kebab sheet =======================
  // Phase 3 of the mobile redesign (plans/mobile_redesign/). The appbar
  // and tab strip are mobile-only persistent chrome (CSS hides them at
  // >1024px). The kebab sheet consolidates the floating Diagnostics /
  // Report bug / Clear App Cache controls into one bottom sheet on
  // mobile; the same controls remain on screen at desktop widths.

  function setShellVisible(visible) {
    var hide = !visible;
    if (siteHeaderEl) siteHeaderEl.classList.toggle('hidden', hide);
    if (appbarEl) appbarEl.classList.toggle('hidden', hide);
    if (tabsEl) tabsEl.classList.toggle('hidden', hide);
  }

  function setShellChrome(routeKey, title) {
    if (appbarTitleEl && typeof title === 'string' && title) {
      appbarTitleEl.textContent = title;
    }
    if (tabsEl) {
      var tabs = tabsEl.querySelectorAll('.tabs__tab');
      for (var i = 0; i < tabs.length; i++) {
        var t = tabs[i];
        t.classList.toggle('tabs__tab--active', t.getAttribute('data-tab') === routeKey);
      }
    }
  }

  function updateAppbarFellowNav(prevSlug, prevHref, nextSlug, nextHref) {
    var prevEl = document.getElementById('appbar-fellow-prev');
    var nextEl = document.getElementById('appbar-fellow-next');
    if (prevEl) {
      if (prevSlug) {
        prevEl.classList.remove('hidden');
        prevEl.removeAttribute('hidden');
        prevEl.setAttribute('href', prevHref);
      } else {
        prevEl.classList.add('hidden');
        prevEl.setAttribute('hidden', '');
        prevEl.setAttribute('href', '#');
      }
    }
    if (nextEl) {
      if (nextSlug) {
        nextEl.classList.remove('hidden');
        nextEl.removeAttribute('hidden');
        nextEl.setAttribute('href', nextHref);
      } else {
        nextEl.classList.add('hidden');
        nextEl.setAttribute('hidden', '');
        nextEl.setAttribute('href', '#');
      }
    }
  }

  function isKebabSheetOpen() {
    return !!(kebabSheetEl && !kebabSheetEl.classList.contains('hidden'));
  }

  function openKebabSheet() {
    if (!kebabSheetEl) return;
    // Mirror the current build-badge values into the sheet so users on
    // mobile (where the badge is hidden) still see what they're running.
    var appBadge = document.getElementById('build-badge-client');
    var serverBadge = document.getElementById('build-badge-server');
    var appOut = document.getElementById('kebab-sheet-build-app');
    var serverOut = document.getElementById('kebab-sheet-build-server');
    if (appOut && appBadge) appOut.textContent = (appBadge.textContent || '').replace(/^app:\s*/, '');
    if (serverOut && serverBadge) serverOut.textContent = (serverBadge.textContent || '').replace(/^server:\s*/, '');
    kebabSheetEl.classList.remove('hidden');
    kebabSheetEl.removeAttribute('hidden');
    if (kebabScrimEl) {
      kebabScrimEl.classList.remove('hidden');
      kebabScrimEl.removeAttribute('hidden');
    }
    if (appbarKebabEl) appbarKebabEl.setAttribute('aria-expanded', 'true');
  }

  function closeKebabSheet() {
    if (!kebabSheetEl) return;
    kebabSheetEl.classList.add('hidden');
    kebabSheetEl.setAttribute('hidden', '');
    if (kebabScrimEl) {
      kebabScrimEl.classList.add('hidden');
      kebabScrimEl.setAttribute('hidden', '');
    }
    if (appbarKebabEl) appbarKebabEl.setAttribute('aria-expanded', 'false');
  }

  function initKebabSheet() {
    if (!appbarKebabEl || !kebabSheetEl) return;
    appbarKebabEl.addEventListener('click', function () {
      if (isKebabSheetOpen()) closeKebabSheet();
      else openKebabSheet();
    });
    if (kebabScrimEl) {
      kebabScrimEl.addEventListener('click', closeKebabSheet);
    }
    var closeBtn = document.getElementById('kebab-sheet-close');
    if (closeBtn) closeBtn.addEventListener('click', closeKebabSheet);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isKebabSheetOpen()) closeKebabSheet();
    });
    // Each sheet action proxies to the existing floating-button handler
    // by clicking the original element. Means we don't reimplement any
    // of the dialog/diag/clear-cache logic — same code path as the
    // desktop floating buttons.
    var actions = kebabSheetEl.querySelectorAll('[data-kebab-action]');
    for (var i = 0; i < actions.length; i++) {
      var btn = actions[i];
      btn.addEventListener('click', function (ev) {
        var action = ev.currentTarget.getAttribute('data-kebab-action');
        closeKebabSheet();
        var targetId = null;
        if (action === 'diagnostics') targetId = 'diag-toggle';
        else if (action === 'report-bug') targetId = 'bug-report-button';
        else if (action === 'clear-cache') targetId = 'clear-app-cache-button';
        else if (action === 'reset-everything') targetId = 'reset-everything-button';
        if (!targetId) return;
        var target = document.getElementById(targetId);
        if (target) target.click();
      });
    }
    // Tab clicks should close the sheet too if it happens to be open.
    if (tabsEl) {
      tabsEl.addEventListener('click', function () {
        if (isKebabSheetOpen()) closeKebabSheet();
      });
    }
  }

  // ----- Composer FAB + sheet (PR 2) -----------------------------------
  // The FAB is the mobile entry point into the existing #group-rail
  // composer. CSS turns the rail into a fixed bottom-sheet at ≤1024px;
  // the FAB only renders on the directory route when at least one
  // fellow is selected. Selection state already lives in
  // groupDraft.members (a Set); we mirror it onto the body class so
  // CSS can react without JS having to touch the FAB on every change.

  function updateComposerFabFromDraft() {
    var n = groupDraft && groupDraft.members ? groupDraft.members.size : 0;
    if (composerFabCountEl) composerFabCountEl.textContent = String(n);
    var body = document.body;
    if (n > 0) body.classList.add('has-selection');
    else {
      body.classList.remove('has-selection');
      // If the sheet was open and selection drained to zero, close it.
      if (body.classList.contains('composer-open')) closeComposerSheet();
    }
  }

  function openComposerSheet() {
    var body = document.body;
    body.classList.add('composer-open');
    if (composerScrimEl) {
      composerScrimEl.classList.remove('hidden');
      composerScrimEl.removeAttribute('hidden');
    }
    if (composerFabEl) composerFabEl.setAttribute('aria-expanded', 'true');
    // Focus the title input so the user can start naming immediately.
    if (groupRailTitleEl) {
      try { groupRailTitleEl.focus({ preventScroll: true }); } catch (_) { groupRailTitleEl.focus(); }
    }
  }

  function closeComposerSheet() {
    var body = document.body;
    body.classList.remove('composer-open');
    if (composerScrimEl) {
      composerScrimEl.classList.add('hidden');
      composerScrimEl.setAttribute('hidden', '');
    }
    if (composerFabEl) composerFabEl.setAttribute('aria-expanded', 'false');
  }

  function initComposerFab() {
    if (!composerFabEl) return;
    composerFabEl.addEventListener('click', function () {
      if (document.body.classList.contains('composer-open')) closeComposerSheet();
      else openComposerSheet();
    });
    if (composerScrimEl) {
      composerScrimEl.addEventListener('click', closeComposerSheet);
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('composer-open')) {
        closeComposerSheet();
      }
    });
    // Initial sync — selection may already be non-empty if the user
    // had a draft saved in localStorage.
    updateComposerFabFromDraft();
  }

  // ----- Per-card kebab sheet (groups index) ---------------------------

  function initGroupCardSheet() {
    if (!groupCardSheetEl) return;
    if (groupCardScrimEl) {
      groupCardScrimEl.addEventListener('click', closeGroupCardSheet);
    }
    var closeBtn = document.getElementById('group-card-sheet-close');
    if (closeBtn) closeBtn.addEventListener('click', closeGroupCardSheet);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && groupCardSheetEl && !groupCardSheetEl.classList.contains('hidden')) {
        closeGroupCardSheet();
      }
    });
    var actions = groupCardSheetEl.querySelectorAll('[data-card-action]');
    for (var i = 0; i < actions.length; i++) {
      actions[i].addEventListener('click', function (ev) {
        var action = ev.currentTarget.getAttribute('data-card-action');
        var gidStr = groupCardSheetEl.dataset.groupId;
        var wrap = groupCardSheetEl._fellowsHostWrap;
        closeGroupCardSheet();
        if (!gidStr || !wrap) return;
        if (action === 'rename') startInlineRename(wrap, gidStr);
        else if (action === 'delete') confirmAndDeleteGroup(wrap, gidStr);
      });
    }
  }

  // ----- Group-detail action-bar overflow sheet ------------------------

  function openGroupActionbarSheet(currentMode) {
    if (!groupActionbarSheetEl) return;
    // Reflect the current CC/BCC selection from the visible pill so
    // the radio in the sheet matches what the action bar shows.
    var radios = groupActionbarSheetEl.querySelectorAll('input[name="group-mode-sheet"]');
    for (var i = 0; i < radios.length; i++) {
      radios[i].checked = radios[i].value === currentMode;
    }
    groupActionbarSheetEl.classList.remove('hidden');
    groupActionbarSheetEl.removeAttribute('hidden');
    if (groupActionbarScrimEl) {
      groupActionbarScrimEl.classList.remove('hidden');
      groupActionbarScrimEl.removeAttribute('hidden');
    }
  }

  function closeGroupActionbarSheet() {
    if (!groupActionbarSheetEl) return;
    groupActionbarSheetEl.classList.add('hidden');
    groupActionbarSheetEl.setAttribute('hidden', '');
    if (groupActionbarScrimEl) {
      groupActionbarScrimEl.classList.add('hidden');
      groupActionbarScrimEl.setAttribute('hidden', '');
    }
    var moreBtn = document.getElementById('group-action-more');
    if (moreBtn) moreBtn.setAttribute('aria-expanded', 'false');
  }

  function initGroupActionbarSheet() {
    if (!groupActionbarSheetEl) return;
    if (groupActionbarScrimEl) {
      groupActionbarScrimEl.addEventListener('click', closeGroupActionbarSheet);
    }
    var closeBtn = document.getElementById('group-actionbar-sheet-close');
    if (closeBtn) closeBtn.addEventListener('click', closeGroupActionbarSheet);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && groupActionbarSheetEl && !groupActionbarSheetEl.classList.contains('hidden')) {
        closeGroupActionbarSheet();
      }
    });
    // Radio changes mirror to the visible CC/BCC pill in the action
    // bar so the desktop and the sheet stay in lockstep.
    var radios = groupActionbarSheetEl.querySelectorAll('input[name="group-mode-sheet"]');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', function (ev) {
        var mode = ev.target.value;
        var pill = document.querySelector('.group-mode-pill[data-mode="' + mode + '"]');
        if (pill) pill.click();
      });
    }
    // Each sheet action proxies to the matching action-bar button so
    // there is exactly one set of click handlers in the renderer.
    var actions = groupActionbarSheetEl.querySelectorAll('[data-actionbar-action]');
    for (var j = 0; j < actions.length; j++) {
      actions[j].addEventListener('click', function (ev) {
        var action = ev.currentTarget.getAttribute('data-actionbar-action');
        closeGroupActionbarSheet();
        var targetId = null;
        if (action === 'copy') targetId = 'group-action-copy-emails';
        else if (action === 'edit') targetId = 'group-action-edit';
        if (!targetId) return;
        var btn = document.getElementById(targetId);
        if (btn) btn.click();
      });
    }
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
    setShellVisible(false);
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
        pushBugReportError('http', 'GET /fellows.db → ' + r.status);
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

  // ===== Auto-backup of relationships.db on app upgrade ===================
  //
  // relationships.db is the user-authored store (groups, notes, settings,
  // fellow tags). It is intentionally not regenerated on app update — it
  // is the one local file the user can't recover if it gets corrupted by
  // a botched migration or an OPFS glitch. Auto-backup runs on every
  // boot where the build SHA differs from the last-seen SHA: copy
  // relationships.db (via SAH-pool exportFile) to a top-level OPFS file
  // relationships.db.bak.<ISO timestamp>, then rotate to keep the newest
  // BACKUP_KEEP. Backups live at OPFS root, NOT inside the SAH pool —
  // Reset Everything iterates the root and removeEntry's everything, so
  // backups go with the rest of the wipe.
  //
  // The sentinel file last_seen_sha.txt also lives at OPFS root. On
  // first boot post-PR-D, the sentinel is absent → baseline backup.
  // First install (no relationships.db at all) → just write the sentinel.
  var BACKUP_PREFIX = 'relationships.db.bak.';
  var BACKUP_SENTINEL = 'last_seen_sha.txt';
  var BACKUP_KEEP = 3;

  async function _opfsRoot() {
    return await navigator.storage.getDirectory();
  }

  async function _opfsReadText(name) {
    try {
      var root = await _opfsRoot();
      var fh = await root.getFileHandle(name);
      var f = await fh.getFile();
      return await f.text();
    } catch (e) {
      return null;
    }
  }

  async function _opfsWriteText(name, content) {
    var root = await _opfsRoot();
    var fh = await root.getFileHandle(name, { create: true });
    var w = await fh.createWritable();
    await w.write(content);
    await w.close();
  }

  async function _opfsWriteBinary(name, bytes) {
    var root = await _opfsRoot();
    var fh = await root.getFileHandle(name, { create: true });
    var w = await fh.createWritable();
    await w.write(bytes);
    await w.close();
  }

  async function _opfsReadBinary(name) {
    var root = await _opfsRoot();
    var fh = await root.getFileHandle(name);
    var f = await fh.getFile();
    return new Uint8Array(await f.arrayBuffer());
  }

  async function listRelationshipsBackups() {
    try {
      var root = await _opfsRoot();
      var out = [];
      for await (var entry of root.values()) {
        if (entry.kind === 'file' && entry.name.indexOf(BACKUP_PREFIX) === 0) {
          var f = await entry.getFile();
          out.push({ name: entry.name, size: f.size, lastModified: f.lastModified });
        }
      }
      out.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
      return out;
    } catch (e) {
      return [];
    }
  }

  async function _rotateRelationshipsBackups() {
    var backups = await listRelationshipsBackups();
    var root = await _opfsRoot();
    while (backups.length > BACKUP_KEEP) {
      var oldest = backups.shift();
      try {
        await root.removeEntry(oldest.name);
        bootDebugPush('backup: rotated out ' + oldest.name);
      } catch (e) {
        bootDebugPush('backup: rotate removeEntry failed for ' + oldest.name);
      }
    }
  }

  async function maybeBackupRelationshipsDb(poolUtil) {
    var sha = (bootBuildMeta && bootBuildMeta.git_sha) || null;
    if (!sha) {
      bootDebugPush('backup: skipped (no build SHA available)');
      return { backedUp: false, reason: 'no SHA' };
    }
    var poolFiles = [];
    try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
    var hasRelDb = poolFiles.indexOf('relationships.db') !== -1;
    var prevSha = await _opfsReadText(BACKUP_SENTINEL);
    if (!hasRelDb) {
      // First install: no DB to back up. Sentinel marks "we've seen
      // this SHA boot the app cleanly".
      try { await _opfsWriteText(BACKUP_SENTINEL, sha); } catch (e) {}
      bootDebugPush('backup: skipped (no relationships.db yet)');
      return { backedUp: false, reason: 'first install' };
    }
    if (prevSha === sha) {
      bootDebugPush('backup: skipped (no SHA change)');
      return { backedUp: false, reason: 'no SHA change' };
    }
    // Different SHA, OR no sentinel → back up.
    var bytes;
    try {
      bytes = poolUtil.exportFile('relationships.db');
    } catch (e) {
      bootDebugPush('backup: exportFile failed: ' + (e && e.message || e));
      return { backedUp: false, reason: 'export failed' };
    }
    if (!bytes || !bytes.byteLength) {
      try { await _opfsWriteText(BACKUP_SENTINEL, sha); } catch (e) {}
      bootDebugPush('backup: empty file, sentinel updated');
      return { backedUp: false, reason: 'empty file' };
    }
    var ts = new Date().toISOString().replace(/[:.]/g, '-');
    var backupName = BACKUP_PREFIX + ts;
    try {
      await _opfsWriteBinary(backupName, bytes);
    } catch (e) {
      bootDebugPush('backup: write failed: ' + (e && e.message || e));
      return { backedUp: false, reason: 'write failed' };
    }
    await _rotateRelationshipsBackups();
    try { await _opfsWriteText(BACKUP_SENTINEL, sha); } catch (e) {}
    bootDebugPush(
      'backup: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes); ' +
      'sentinel ' + (prevSha || '<none>') + ' → ' + sha
    );
    return { backedUp: true, name: backupName, size: bytes.byteLength };
  }

  // Forced version of maybeBackupRelationshipsDb: skips the SHA-change
  // check and always writes a backup if relationships.db exists. The
  // restore flow calls this to capture pre-restore state into the same
  // rotation slot, so a wrong restore is one click away from undo.
  // Sentinel is left untouched — a snapshot is not a deploy event.
  async function snapshotRelationshipsDbToBackup(poolUtil) {
    var poolFiles = [];
    try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
    if (poolFiles.indexOf('relationships.db') === -1) {
      return { backedUp: false, reason: 'no relationships.db' };
    }
    var bytes;
    try {
      bytes = poolUtil.exportFile('relationships.db');
    } catch (e) {
      return { backedUp: false, reason: 'export failed: ' + (e && e.message || e) };
    }
    if (!bytes || !bytes.byteLength) {
      return { backedUp: false, reason: 'empty file' };
    }
    var ts = new Date().toISOString().replace(/[:.]/g, '-');
    var backupName = BACKUP_PREFIX + ts;
    try {
      await _opfsWriteBinary(backupName, bytes);
    } catch (e) {
      return { backedUp: false, reason: 'write failed: ' + (e && e.message || e) };
    }
    await _rotateRelationshipsBackups();
    bootDebugPush('snapshot: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes)');
    return { backedUp: true, name: backupName, size: bytes.byteLength };
  }

  // Validates a candidate relationships.db file by writing it to a temp
  // SAH-pool slot, opening it, and checking schema + row counts. The
  // staging slot is left occupied; the next inspection overwrites it.
  // Returns { valid, error?, counts? } where counts has groups, members,
  // tags, notes, settings — used to render the restore confirm dialog.
  var RESTORE_STAGING_SLOT = 'relationships.db.restore-staging';
  var REQUIRED_RESTORE_TABLES = ['groups', 'group_members', 'fellow_tags', 'fellow_notes', 'settings'];

  async function inspectRelationshipsBytes(poolUtil, bytes) {
    if (!poolUtil) {
      return { valid: false, error: 'pool util unavailable' };
    }
    if (!bytes || !bytes.byteLength) {
      return { valid: false, error: 'File is empty.' };
    }
    // SQLite header is "SQLite format 3\0" (16 bytes). Cheap pre-flight
    // before paying the import cost.
    var hdr = 'SQLite format 3\0';
    if (bytes.byteLength < hdr.length) {
      return { valid: false, error: 'File is too small to be a SQLite database.' };
    }
    for (var i = 0; i < hdr.length; i++) {
      if (bytes[i] !== hdr.charCodeAt(i)) {
        return { valid: false, error: 'File does not look like a SQLite database.' };
      }
    }
    var tmp = null;
    try {
      poolUtil.importDb(RESTORE_STAGING_SLOT, bytes);
      tmp = new poolUtil.OpfsSAHPoolDb(RESTORE_STAGING_SLOT);
      var qc = dbSelectOne(tmp, 'PRAGMA quick_check', null);
      var qcResult = qc && (qc.quick_check || qc['quick_check']);
      if (qcResult !== 'ok') {
        return { valid: false, error: 'SQLite integrity check failed: ' + (qcResult || 'unknown') };
      }
      var tableRows = dbSelectAll(
        tmp, "SELECT name FROM sqlite_master WHERE type='table'", null
      );
      var tableNames = tableRows.map(function (r) { return r.name; });
      var missing = REQUIRED_RESTORE_TABLES.filter(function (t) {
        return tableNames.indexOf(t) === -1;
      });
      if (missing.length) {
        return {
          valid: false,
          error: 'File is missing expected tables: ' + missing.join(', ') +
            '. Is this a relationships.db backup?'
        };
      }
      var counts = {
        groups: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM groups', null).n,
        members: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM group_members', null).n,
        tags: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
        notes: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
        settings: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM settings', null).n
      };
      return { valid: true, counts: counts };
    } catch (e) {
      return { valid: false, error: (e && e.message) || String(e) };
    } finally {
      if (tmp) {
        try { tmp.close(); } catch (e2) {}
      }
    }
  }

  // Exposed for diagnostics + Settings UI.
  window._fellowsBackups = { list: listRelationshipsBackups };

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
        // Auto-backup runs BEFORE we open relationships.db for app use,
        // so any schema migration or app-update glitch leaves a clean
        // pre-upgrade snapshot the user can fall back on.
        return maybeBackupRelationshipsDb(poolUtil).then(function () {
          return poolUtil;
        });
      })
      .then(function (poolUtil) {
        setSetupStatus('Downloading directory data…');
        return fetchFellowsDbWithProgress(function (n, total) {
          var pct = total ? Math.round((100 * n) / total) : 0;
          setSetupStatus('Downloading directory data… ' + pct + '%');
        }).then(function (bytes) {
          bootDebugPush('fellows.db download: OK bytes=' + (bytes && bytes.byteLength));
          setSetupStatus('Preparing offline database…');
          // fellows.db: re-imported from server every boot (replaces any
          // previous OPFS copy, picking up new fellow data on update).
          poolUtil.importDb('fellows.db', bytes);
          var db = new poolUtil.OpfsSAHPoolDb('fellows.db');
          // relationships.db: created on first use; never replaced by
          // updates. SAH-pool VFS handles file-not-existing by creating it.
          // Schema bootstrap is idempotent (CREATE IF NOT EXISTS).
          var relDb;
          try {
            relDb = new poolUtil.OpfsSAHPoolDb('relationships.db');
            bootstrapRelationshipsSchema(relDb);
            bootDebugPush('relationships.db: open + schema OK');
          } catch (relErr) {
            bootDebugPush(
              'relationships.db: open failed (' + (relErr && relErr.message || relErr) + ')'
            );
            relDb = null;
          }
          return createSqliteDataProvider(db, relDb, poolUtil);
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

  // Treat the current visit as "the app is running" (not "the install
  // landing") when the page is open as an installed PWA *or* when this
  // browser profile has already authenticated against this origin before.
  // The second case covers: user installed once, then later visits the
  // URL in a regular browser tab. Without this, every tab visit would
  // force them through the install landing even though the app is ready.
  // `?gate=1` still bypasses both branches so a dev can always reach the
  // email gate explicitly.
  function shouldActAsApp() {
    if (isStandaloneDisplayMode()) return true;
    if (parseGateOverride().force) return false;
    return hasAuthenticatedOnce();
  }

  // True when the current page is being served from the maintainer's
  // local dev server. Used to fork the `authEnabled === false` branch
  // of the email-gate decision tree: a dev session should land on the
  // directory, not on the install landing (issue #58 LOW #2). Tests
  // that simulate the prod auth flow on localhost mock authEnabled to
  // true, bypassing this fork.
  function isLocalhostHostname() {
    var h = (window.location && window.location.hostname) || '';
    return h === 'localhost' || h === '127.0.0.1' || h === '::1';
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
          pushBugReportError('sw', 'register_error: ' + (err && err.message));
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

  // Multi-line diag for the email-gate block. Same fields the bug-report
  // body uses, minus the recent-error ring — we keep the gate compact and
  // expect the user to click "report a problem" if they need to send the
  // full payload. last_submit appears only after a Send link click; that
  // hash matches deploy/server.py's email_hash_prefix log so a maintainer
  // can grep journald without the user having to disclose their address.
  function formatGateDiagSummary(data, httpStatus) {
    var lines = [];
    lines.push('time:        ' + new Date().toISOString());
    lines.push('auth:        ' + formatAuthDebugLine(data, httpStatus));
    lines.push('app:         ' + FELLOWS_UI_DIAG);
    var serverLabel = '(unknown)';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      serverLabel = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    lines.push('server:      ' + serverLabel);
    lines.push('display:     ' + (isStandaloneDisplayMode() ? 'standalone' : 'browser-tab'));
    try { lines.push('viewport:    ' + window.innerWidth + 'x' + window.innerHeight); } catch (e) {}
    try { lines.push('online:      ' + Boolean(navigator.onLine)); } catch (e) {}
    try { lines.push('language:    ' + String(navigator.language || '')); } catch (e) {}
    try { lines.push('platform:    ' + String(navigator.platform || '')); } catch (e) {}
    lines.push('userAgent:   ' + String(navigator.userAgent || ''));
    if (lastSubmitInfo.emailHashPrefix && lastSubmitInfo.submittedAt) {
      lines.push(
        'last_submit: hash=' + lastSubmitInfo.emailHashPrefix +
        '  at ' + lastSubmitInfo.submittedAt
      );
    }
    return lines.join('\n');
  }

  function showAuthDebugInstall(data, httpStatus) {
    if (authDebugPrivateEl) {
      authDebugPrivateEl.classList.add('hidden');
    }
    if (authDebugPrivatePreEl) authDebugPrivatePreEl.textContent = '';
    if (authDebugInstallEl) {
      authDebugInstallEl.textContent = formatAuthDebugLine(data, httpStatus);
      authDebugInstallEl.classList.remove('hidden');
    }
  }

  function renderAuthDebugPrivate(data, httpStatus) {
    if (authDebugPrivatePreEl) {
      authDebugPrivatePreEl.textContent = formatGateDiagSummary(data, httpStatus);
    }
  }

  function showAuthDebugPrivate(data, httpStatus) {
    if (authDebugInstallEl) {
      authDebugInstallEl.classList.add('hidden');
      authDebugInstallEl.textContent = '';
    }
    if (authDebugPrivateEl) {
      // Stash the latest payload so a later refresh (e.g. after a submit
      // populates lastSubmitInfo) can rebuild the block in place.
      authDebugPrivateEl._lastData = data;
      authDebugPrivateEl._lastHttpStatus = httpStatus;
      renderAuthDebugPrivate(data, httpStatus);
      authDebugPrivateEl.classList.remove('hidden');
    }
  }

  function refreshAuthDebugPrivate() {
    if (!authDebugPrivateEl) return;
    if (authDebugPrivateEl.classList.contains('hidden')) return;
    renderAuthDebugPrivate(
      authDebugPrivateEl._lastData || null,
      authDebugPrivateEl._lastHttpStatus
    );
  }

  function setAuthDebugCopyStatus(msg) {
    if (!authDebugPrivateCopyStatusEl) return;
    authDebugPrivateCopyStatusEl.textContent = msg || '';
  }

  function initAuthDebugCopyButton() {
    if (!authDebugPrivateCopyEl || authDebugPrivateCopyEl._wired) return;
    authDebugPrivateCopyEl._wired = true;
    authDebugPrivateCopyEl.addEventListener('click', function () {
      var text = (authDebugPrivatePreEl && authDebugPrivatePreEl.textContent) || '';
      function fallback() {
        try {
          var sel = window.getSelection();
          var range = document.createRange();
          range.selectNodeContents(authDebugPrivatePreEl);
          sel.removeAllRanges();
          sel.addRange(range);
          if (document.execCommand && document.execCommand('copy')) {
            setAuthDebugCopyStatus('Copied.');
            sel.removeAllRanges();
            return;
          }
        } catch (e) {}
        setAuthDebugCopyStatus('Copy failed — select the box above and copy manually.');
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          setAuthDebugCopyStatus('Copied.');
        }, fallback);
      } else {
        fallback();
      }
    });
  }

  // Payload for POST /api/client-errors. Mirrors the schema declared in
  // deploy/client_error_sanitizer.py; the server re-sanitizes regardless,
  // so this is a best-effort cleanup, not the privacy boundary. The
  // boundary is server-side. Email is never sent — only the 12-hex
  // sha256 prefix from lastSubmitInfo (PR #69), which matches what the
  // server already logs as email_hash_prefix in event=send_unlock_email.
  function buildClientErrorsPayload() {
    var events = [];
    for (var i = 0; i < bugReportErrorRing.length; i++) {
      var ev = bugReportErrorRing[i];
      var out = { kind: String(ev.kind || ''), msg: String(ev.msg || '') };
      if (ev.t) out.ts = String(ev.t);
      if (ev.extra) out.extra = String(ev.extra);
      events.push(out);
    }
    var build = '';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      build = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    var route = '';
    try { route = String(location.hash || location.pathname || ''); } catch (e) {}
    var payload = {
      events: events,
      ua: String(navigator.userAgent || ''),
      build: build,
      route: route,
      displayMode: isStandaloneDisplayMode() ? 'standalone' : 'browser-tab'
    };
    try { payload.online = Boolean(navigator.onLine); } catch (e) {}
    if (lastSubmitInfo.emailHashPrefix) {
      payload.lastSubmitHashPrefix = lastSubmitInfo.emailHashPrefix;
    }
    return payload;
  }

  function initAuthDebugSendButton() {
    if (!authDebugPrivateSendEl || authDebugPrivateSendEl._wired) return;
    authDebugPrivateSendEl._wired = true;
    authDebugPrivateSendEl.addEventListener('click', function () {
      var payload;
      try {
        payload = buildClientErrorsPayload();
      } catch (e) {
        setAuthDebugCopyStatus('Send failed — try Copy diagnostics instead.');
        return;
      }
      setAuthDebugCopyStatus('Sending…');
      authDebugPrivateSendEl.disabled = true;
      fetch('/api/client-errors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      })
        .then(function (r) {
          if (r.status === 204) {
            setAuthDebugCopyStatus('Sent. Thank you.');
          } else {
            setAuthDebugCopyStatus('Send failed — try Copy diagnostics instead.');
          }
        })
        .catch(function () {
          setAuthDebugCopyStatus('Send failed — try Copy diagnostics instead.');
        })
        .then(function () {
          authDebugPrivateSendEl.disabled = false;
        });
    });
  }

  // Reports a single install-flow event to /api/client-errors so the
  // maintainer can grep journald to answer questions like "what fraction
  // of install-landing visits saw beforeinstallprompt fire vs. timed
  // out?" Fire-and-forget; never blocks the install UX. The server-side
  // sanitizer (deploy/client_error_sanitizer.py) is the privacy
  // boundary — same email-redaction + length cap rules as the existing
  // kinds. Uses fetch keepalive so the request survives the navigation
  // that often follows (e.g. user_in_tab_clicked → bootDirectoryAsApp).
  function reportInstallEvent(name, extra) {
    if (!name) return;
    var build = '';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      build = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    var ev = { kind: 'install', msg: String(name) };
    if (extra) ev.extra = String(extra);
    var payload = {
      events: [ev],
      ua: String(navigator.userAgent || ''),
      build: build,
      route: '#install-landing',
      displayMode: isStandaloneDisplayMode() ? 'standalone' : 'browser-tab'
    };
    try { payload.online = Boolean(navigator.onLine); } catch (e) {}
    try {
      fetch('/api/client-errors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(function () { /* ignore — telemetry is best-effort */ });
    } catch (e) { /* ignore */ }
  }

  function initBrowserInstallMode(authPayload, httpStatus) {
    if (installGatePrivateEl) installGatePrivateEl.classList.add('hidden');
    if (installLandingEl) installLandingEl.classList.remove('hidden');
    setShellVisible(false);
    showLoading(false);
    showApp(false);
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');

    if (authPayload) {
      showAuthDebugInstall(authPayload, httpStatus != null ? httpStatus : 200);
    }

    reportInstallEvent('landing_shown');

    if (isIosSafari() && iosHintEl) {
      iosHintEl.classList.remove('hidden');
      if (installButtonEl) installButtonEl.classList.add('hidden');
      reportInstallEvent('ios_safari_advised');
    }

    // Track whether beforeinstallprompt arrived. The 5s timer reports
    // a "never_arrived" event so we can distinguish browsers that
    // suppress the prompt (already-installed Chrome on the same
    // profile, engagement heuristic not yet met) from browsers that
    // genuinely don't support it. Skipped when the iOS Safari path
    // already advised the user — beforeinstallprompt is iOS-by-design
    // not-a-thing there, no value reporting it.
    var beforeInstallPromptSeen = false;
    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      deferredInstallPrompt = e;
      beforeInstallPromptSeen = true;
      var platforms = '';
      try { platforms = (e.platforms || []).join(','); } catch (ePf) {}
      reportInstallEvent('before_prompt_fired', platforms);
      setInstallStatus('');
      if (installUnsupportedHintEl) installUnsupportedHintEl.classList.add('hidden');
      if (installButtonEl) installButtonEl.classList.remove('hidden');
    });
    if (!isIosSafari()) {
      setTimeout(function () {
        if (!beforeInstallPromptSeen) {
          reportInstallEvent('before_prompt_never_arrived');
        }
      }, 5000);
    }

    window.addEventListener('appinstalled', function () {
      deferredInstallPrompt = null;
      reportInstallEvent('app_installed');
      setInstallStatus('App installed — open it from your dock or app drawer.');
      if (installButtonEl) installButtonEl.classList.add('hidden');
    });

    // Note: no proactive "unsupported browser" detection timer.
    //   An earlier version flipped the install landing to an "unsupported"
    //   warning after 3s if `beforeinstallprompt` hadn't fired. That's a
    //   false positive on Chrome/Edge when the PWA is already installed on
    //   the device — Chrome won't re-fire the event in that case (the
    //   address bar shows "Open in app" instead). We now rely on the
    //   click-handler fallback below, which shows the hint only if the
    //   user actually clicks Install and the prompt isn't available.

    if (installButtonEl && !installButtonEl._wired) {
      installButtonEl._wired = true;
      installButtonEl.addEventListener('click', function () {
        reportInstallEvent('button_clicked');
        if (deferredInstallPrompt) {
          deferredInstallPrompt.prompt();
          deferredInstallPrompt.userChoice
            .then(function (choice) {
              deferredInstallPrompt = null;
              var outcome = (choice && choice.outcome) || 'unknown';
              var platform = (choice && choice.platform) || '';
              reportInstallEvent('outcome_' + outcome, platform);
              if (outcome === 'accepted') {
                setInstallStatus('Installing…');
              }
            })
            .catch(function (err) {
              deferredInstallPrompt = null;
              reportInstallEvent('outcome_error', err && err.message);
            });
        } else if (isIosSafari()) {
          setInstallStatus('Use Share → Add to Home Screen.');
        } else {
          reportInstallEvent('button_clicked_no_prompt');
          if (installUnsupportedHintEl) installUnsupportedHintEl.classList.remove('hidden');
          if (installButtonEl) installButtonEl.classList.add('hidden');
        }
      });
    }

    if (backToGateLinkEl && !backToGateLinkEl._wired) {
      backToGateLinkEl._wired = true;
      backToGateLinkEl.addEventListener('click', function (ev) {
        ev.preventDefault();
        fetch('/api/logout', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: '{}'
        })
          .catch(function () {})
          .then(function () {
            window.location.replace('/?gate=1');
          });
      });
    }

    // "Use the directory in this tab" — escape hatch for users whose browser
    // never fires beforeinstallprompt (already-installed Chrome, engagement
    // heuristic not yet met, etc.). Mirrors the path a returning user gets
    // automatically via shouldActAsApp(): mark this origin as authenticated
    // and boot the directory in the current tab.
    if (installUseInTabEl && !installUseInTabEl._wired) {
      installUseInTabEl._wired = true;
      installUseInTabEl.addEventListener('click', function (ev) {
        ev.preventDefault();
        reportInstallEvent('use_in_tab_clicked');
        markAuthenticatedOnce();
        if (installLandingEl) installLandingEl.classList.add('hidden');
        bootDirectoryAsApp();
      });
    }
  }

  function setGateReasonBanner(reason) {
    if (!gateReasonBannerEl) return;
    var text = '';
    if (reason === 'expired') {
      text = 'That link expired. Enter your email to get a new one.';
    } else if (reason === 'invalid') {
      text = "That link isn't valid. Enter your email to get a new one.";
    }
    if (text) {
      gateReasonBannerEl.textContent = text;
      gateReasonBannerEl.classList.remove('hidden');
    } else {
      gateReasonBannerEl.textContent = '';
      gateReasonBannerEl.classList.add('hidden');
    }
  }

  function initEmailGate(authPayload, httpStatus, reason) {
    if (installGatePrivateEl) installGatePrivateEl.classList.remove('hidden');
    if (installLandingEl) installLandingEl.classList.add('hidden');
    setShellVisible(false);
    showLoading(false);
    showApp(false);
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');

    setGateReasonBanner(reason);

    if (authPayload) {
      showAuthDebugPrivate(authPayload, httpStatus != null ? httpStatus : 200);
    }
    initAuthDebugCopyButton();
    initAuthDebugSendButton();

    if (unlockEmailFormEl && !unlockEmailFormEl._wired) {
      unlockEmailFormEl._wired = true;
      unlockEmailFormEl.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (unlockEmailInputEl && unlockEmailInputEl.value) || '';
        var trimmed = email.trim();
        // Capture the user's own email for the export "email it to me"
        // feature (PR 5). Mirrors to relationships.settings on next boot.
        setSelfEmailLocal(email);
        if (unlockStatusEl) unlockStatusEl.textContent = 'Sending…';
        setGateReasonBanner('');
        // Hash the submitted email locally so the bug-report and gate diag
        // block carry a stable join key into deploy/server.py's journald
        // event=send_unlock_email.email_hash_prefix without ever sending
        // the address itself out-of-band.
        var submittedAt = new Date().toISOString();
        var hashPromise = trimmed
          ? sha256HexBrowser(trimmed.toLowerCase())
          : Promise.resolve(null);
        hashPromise.then(function (hex) {
          lastSubmitInfo = {
            emailHashPrefix: hex ? hex.slice(0, 12) : null,
            submittedAt: submittedAt
          };
          refreshAuthDebugPrivate();
        });
        fetch('/api/send-unlock', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ email: trimmed })
        })
          .then(function (r) {
            if (!r.ok) {
              pushBugReportError('http', 'POST /api/send-unlock → ' + r.status);
            }
            return r.json();
          })
          .then(function () {
            if (unlockStatusEl) {
              unlockStatusEl.textContent =
                'If that email is on file, you will receive a link shortly. Check your inbox.';
            }
          })
          .catch(function (err) {
            pushBugReportError('http', 'POST /api/send-unlock failed: ' + (err && err.message));
            if (unlockStatusEl) unlockStatusEl.textContent = 'Could not send. Try again later.';
          });
      });
    }
  }

  function tryUnlockFromHash() {
    var hash = window.location.hash || '';
    var m = hash.match(/^#\/unlock\/(.+)$/);
    if (!m) {
      return Promise.resolve();
    }
    var token = m[1];
    // Guard against double-fire within the same tab. Magic-link tokens are
    // single-use server-side, so a second POST returns "invalid" — which the
    // user sees as "That link isn't valid." iOS Safari's bfcache restore and
    // back/forward navigation can both resurrect a page with the original
    // #/unlock/<tok> hash and re-run boot. sessionStorage is per-tab and
    // cleared on tab close, so a fresh visit (new tab) always retries cleanly.
    var redeemKey = 'redeeming:' + token;
    try {
      if (sessionStorage.getItem(redeemKey)) {
        // Already in-flight or completed in this tab; strip hash, no-op.
        window.history.replaceState(null, '', '/#/');
        return Promise.resolve();
      }
      sessionStorage.setItem(redeemKey, String(Date.now()));
    } catch (e) {}
    return fetch('/api/verify-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ token: token })
    })
      .then(function (r) {
        return r.json().then(function (j) {
          if (r.ok && j.ok) {
            // Success: strip the token from the URL so reload doesn't re-submit,
            // drop any ?gate=1&reason=… that may have been carried through, and
            // let startBrowserUx run — it will see authenticated=true &
            // installRecentlyAllowed=true and render the install landing.
            window.history.replaceState(null, '', '/#/');
            return;
          }
          pushBugReportError(
            'http',
            'POST /api/verify-token → ' + r.status + ' error=' + (j && j.error)
          );
          var reason = (j && j.error) === 'expired' ? 'expired' : 'invalid';
          window.location.replace('/?gate=1&reason=' + reason);
          // stall remaining chain — the replace will reload us
          return new Promise(function () {});
        });
      })
      .catch(function (err) {
        pushBugReportError(
          'http',
          'POST /api/verify-token failed: ' + (err && err.message)
        );
        window.location.replace('/?gate=1&reason=invalid');
        return new Promise(function () {});
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

  function parseGateOverride() {
    try {
      var u = new URL(window.location.href);
      if (u.searchParams.get('gate') === '1') {
        var reason = u.searchParams.get('reason') || '';
        return { force: true, reason: reason };
      }
    } catch (e) {}
    return { force: false, reason: '' };
  }

  function startBrowserUx() {
    authDebugLines.length = 0;
    authDebugPush('startBrowserUx: begin auth status check');
    var override = parseGateOverride();
    fetch('/api/auth/status', { credentials: 'same-origin' })
      .then(function (r) {
        authDebugPush('/api/auth/status HTTP ' + r.status);
        if (reloadIfBuildChanged(r.headers.get('X-Fellows-Build'))) {
          return new Promise(function () {});
        }
        if (!r.ok) {
          pushBugReportError('http', 'GET /api/auth/status → ' + r.status);
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
          '/api/auth/status payload authEnabled=' + data.authEnabled +
          ' authenticated=' + data.authenticated +
          ' installRecentlyAllowed=' + (data.installRecentlyAllowed === true)
        );
        setBuildBadgeServer(data.buildGitSha, data.build);

        // Decision tree per docs/email_gate.md:
        // 1. Force-gate URL (?gate=1) overrides everything — explicit dev escape.
        // 2. If auth isn't active on the server (local dev), skip the gate and
        //    go straight to install mode as before.
        // 3. Install landing only when authenticated AND inside the
        //    install-recently-allowed window.
        // 4. Otherwise: email gate.
        if (override.force) {
          authDebugPush('?gate=1 override: using email gate (reason=' + (override.reason || 'none') + ')');
          initEmailGate(data, httpStatus, override.reason);
          return;
        }
        if (!data.authEnabled) {
          // Dev passthrough. On localhost we boot the directory directly —
          // the install landing every time a maintainer hits Clear App
          // Cache was confusing in practice (issue #58 LOW #2). Boot
          // shell elements (#site-header, #app-wrap) all start hidden,
          // so deferring to bootDirectoryAsApp is safe — it reveals
          // the header itself and renderDirectory shows app-wrap.
          // On any other host with authEnabled=false (a misconfigured
          // prod, a staging box without secrets), keep the historical
          // install-landing behavior so the misconfiguration is
          // visible.
          if (isLocalhostHostname()) {
            authDebugPush('auth disabled on localhost: booting directory directly');
            bootDirectoryAsApp();
            return;
          }
          authDebugPush('auth disabled on server: using install mode');
          initBrowserInstallMode(data, httpStatus);
          return;
        }
        if (data.authenticated && data.installRecentlyAllowed === true) {
          authDebugPush('authenticated + recent-token-window: using install mode');
          markAuthenticatedOnce();
          initBrowserInstallMode(data, httpStatus);
          return;
        }
        if (data.authenticated) {
          // Authenticated but outside the install window. Record the marker
          // so future transient failures fall through gracefully.
          markAuthenticatedOnce();
        }
        authDebugPush('default: using email gate');
        initEmailGate(data, httpStatus, '');
      })
      .catch(function (err) {
        var errMsg = err && err.message ? err.message : String(err);
        authDebugPush('auth status check failed: ' + errMsg);
        // If this origin has been authenticated successfully at least once, a
        // transient auth-status failure (5xx, network error) must NOT block
        // the app behind a scary "Authentication check failed" panel.
        // Quiet fallback: label the server as unreachable on the build badge
        // and show the email gate as the default view. The user still has
        // the option to submit a new email if they want a fresh token; most
        // will just reload when the server is back.
        if (hasAuthenticatedOnce()) {
          authDebugPush('fallback: marker set → quiet email-gate (no auth-failure panel)');
          setBuildBadgeServerUnreachable();
          initEmailGate(
            { authEnabled: true, authenticated: false, _offline: true },
            0,
            ''
          );
          return;
        }
        showAuthFailure('Unable to validate auth status; refusing install-mode fallback', errMsg);
      });
  }

  function showLoading(show) {
    loadingEl.classList.toggle('hidden', !show);
  }

  function showApp(show) {
    if (appWrapEl) appWrapEl.classList.toggle('hidden', !show);
  }

  function loadHasEmailFilter() {
    try {
      var v = localStorage.getItem(HAS_EMAIL_FILTER_KEY);
      if (v === '0') return false;
      if (v === '1') return true;
    } catch (e) {}
    return true;
  }

  function saveHasEmailFilter(v) {
    try { localStorage.setItem(HAS_EMAIL_FILTER_KEY, v ? '1' : '0'); } catch (e) {}
    // Mirror to relationships.settings for durability across Clear App
    // Cache. localStorage stays as the synchronous read path on boot;
    // settings is the source of truth that survives.
    if (dataProvider && typeof dataProvider.setSetting === 'function') {
      dataProvider.setSetting('has_email_only', v ? '1' : '0').catch(function () { /* ignore */ });
    }
  }

  /** Boot-time companion to reconcileSelfEmailOnBoot: reconcile the
   *  has-email filter pref between localStorage (fast read) and
   *  relationships.settings (durable). On the first boot after this
   *  PR ships, settings is empty and localStorage carries the user's
   *  pref → migrate localStorage → settings. After Clear App Cache,
   *  localStorage is wiped but settings survives → rehydrate the
   *  localStorage cache and update the in-memory + UI state. */
  function reconcileHasEmailFilterOnBoot() {
    if (!dataProvider || typeof dataProvider.getSetting !== 'function') return;
    dataProvider.getSetting('has_email_only').then(function (settingVal) {
      if (settingVal === '0' || settingVal === '1') {
        var fromSettings = settingVal === '1';
        if (fromSettings !== hasEmailOnly) {
          hasEmailOnly = fromSettings;
          try { localStorage.setItem(HAS_EMAIL_FILTER_KEY, settingVal); } catch (e) {}
          if (hasEmailFilterEl) hasEmailFilterEl.checked = fromSettings;
          // Re-render the directory if it's currently visible.
          if (typeof updateDirectory === 'function') {
            try { updateDirectory(); } catch (e) {}
          }
        }
      } else if (typeof dataProvider.setSetting === 'function') {
        // Settings is empty — migrate from localStorage.
        var localVal = hasEmailOnly ? '1' : '0';
        dataProvider.setSetting('has_email_only', localVal).catch(function () { /* ignore */ });
      }
    }).catch(function () { /* ignore */ });
  }

  function fellowHasEmail(f) {
    if (f.has_contact_email === true || f.has_contact_email === 1) return true;
    return !!(f.contact_email && String(f.contact_email).trim());
  }

  function applyHasEmailFilter(items) {
    if (!hasEmailOnly) return items;
    return items.filter(fellowHasEmail);
  }

  function setFilterCount(msg) {
    if (filterCountEl) filterCountEl.textContent = msg || '';
  }

  function renderDirectoryList(items) {
    var ul = document.createElement('ul');
    items.forEach(function (f) {
      var li = document.createElement('li');
      li.className = 'dir-row';
      var rid = f.record_id || '';
      var on = !!(rid && groupDraft.members.has(rid));
      var displayName = (f.name && String(f.name).trim()) ? f.name : 'Unknown';
      var mark = document.createElement('button');
      mark.type = 'button';
      mark.className = 'dir-mark' + (on ? ' dir-mark--on' : '');
      mark.dataset.recordId = rid;
      mark.setAttribute('aria-pressed', on ? 'true' : 'false');
      mark.title = on ? 'remove from group' : 'add to group';
      mark.textContent = on ? '✓' : '+';
      mark.addEventListener('click', function (ev) {
        // Marker is inside the row but must NOT trigger row navigation.
        ev.stopPropagation();
        ev.preventDefault();
        toggleDraftMember(rid, displayName);
      });
      var a = document.createElement('a');
      a.href = '#/fellow/' + encodeURIComponent(f.slug || '');
      a.className = 'dir-link';
      a.textContent = displayName;
      li.appendChild(mark);
      li.appendChild(a);
      ul.appendChild(li);
    });
    directoryListEl.innerHTML = '';
    directoryListEl.appendChild(ul);
  }

  function renderDirectory() {
    if (!list.length) {
      directoryListEl.innerHTML = '<p class="placeholder">No fellows loaded.</p>';
      setFilterCount('');
      updateBulkBar();
      return;
    }
    var filtered = applyHasEmailFilter(list);
    if (!filtered.length) {
      directoryListEl.innerHTML = '<p class="placeholder">No fellows match the current filter.</p>';
      displayedList = [];
    } else {
      renderDirectoryList(filtered);
      displayedList = filtered;
    }
    // This UI element is defined as "count of fellows visible in the current
    // view." In directory mode it reflects the `has email` filter; in search
    // mode it reflects the search + filter together (see renderSearchResults).
    setFilterCount(
      filtered.length === list.length
        ? list.length + ' fellows visible'
        : filtered.length + ' of ' + list.length + ' fellows visible'
    );
    if (loadingPanelEl) {
      loadingPanelEl.classList.add('hidden');
    }
    showLoading(false);
    showApp(true);
    updateBulkBar();
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
    if (window.location.hash.indexOf('#/fellow/') === 0) {
      setShellChrome('directory', name);
    }
    var slug = fellow.slug || '';
    var rid = fellow.record_id || '';
    var inDraft = !!(rid && groupDraft.members.has(rid));
    var leftTop = '';
    var leftRest = '';

    var demo = [fellow.gender_pronouns, fellow.ethnicity].filter(Boolean).join(' | ');
    leftTop += '<h2 class="detail-name">' + escapeHtml(name);
    if (rid) {
      leftTop += ' <a href="#" class="detail-add-to-group" data-record-id="' +
        escapeHtml(rid) + '">' +
        (inDraft ? 'remove from group' : 'add to group') +
        '</a>';
    }
    leftTop += '</h2>';
    if (demo) leftTop += '<p class="detail-demographics">' + escapeHtml(demo) + '</p>';
    var hasImage = fellow.has_image === 1 || fellow.has_image === true;
    if (hasImage && slug) {
      // Cache-bust against stale 404s from before a fellow's photo existed.
      // The HTTP cache has a long max-age for 200 images (good), but if a
      // browser cached a 404 during a gap, it would persist for days. Adding
      // ?v=<version> to the URL forces a fresh cache key on every release
      // so a recovered image surfaces immediately after deploy.
      var imgUrl = '/images/' + escapeHtml(slug) + '.jpg?v=' + escapeHtml(FELLOWS_UI_DIAG);
      leftTop +=
        '<div class="profile-image-wrap profile-image-wrap--loading" data-slug="' + escapeHtml(slug) + '">' +
          '<img class="profile-image" data-slug="' + escapeHtml(slug) + '" src="' + imgUrl + '" alt="' + escapeHtml(name) + '">' +
          '<span class="profile-image-status profile-image-status--loading">Loading… just a sec.</span>' +
        '</div>';
    } else {
      leftTop +=
        '<div class="profile-image-wrap profile-image-wrap--none" data-slug="' + escapeHtml(slug) + '">' +
          '<span class="profile-image-status profile-image-status--none">Not Submitted</span>' +
        '</div>';
    }
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
    if (fellow.contact_email) {
      var emailVal = String(fellow.contact_email);
      howRows.push(fieldRow(
        'Contact Email',
        '<a href="mailto:' + escapeHtml(emailVal) + '">' + escapeHtml(emailVal) + '</a>' +
          copyButton(emailVal, 'email')
      ));
    }
    if (fellow.mobile_number) {
      var phoneText = String(fellow.mobile_number).trim();
      var phoneTel = phoneText.replace(/[^+\d]/g, '');
      howRows.push(fieldRow(
        'Mobile Number',
        '<a href="tel:' + escapeHtml(phoneTel) + '">' + escapeHtml(phoneText) + '</a>' +
          copyButton(phoneText, 'phone number')
      ));
    }
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
        // Mirror prev/next into the mobile app bar so it stays
        // reachable with one thumb at narrow widths. CSS gates
        // visibility by `body.route-fellow` + the `.hidden` class
        // we toggle here for end-of-list cases.
        updateAppbarFellowNav(prevSlug, prevHref, nextSlug, nextHref);
      } else {
        updateAppbarFellowNav(null, null, null, null);
      }
    } else {
      updateAppbarFellowNav(null, null, null, null);
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

    var addLink = detailEl.querySelector('.detail-add-to-group');
    if (addLink) {
      addLink.addEventListener('click', function (ev) {
        ev.preventDefault();
        var linkRid = addLink.dataset.recordId;
        if (!linkRid) return;
        toggleDraftMember(linkRid, fellow.name || fellow.slug || linkRid);
      });
    }

    var img = detailEl.querySelector('.profile-image');
    if (img) {
      var wrap = img.parentNode;
      var markLoaded = function () {
        wrap.classList.remove('profile-image-wrap--loading');
        wrap.classList.add('profile-image-wrap--loaded');
      };
      // The fellow's `has_image=1` — they DID submit a photo. If the <img>
      // fetch fails (network, auth, 404, cache miss), we must NOT flip to
      // "Not Submitted" — that would lie to users about a fellow we have
      // data for. Instead, keep the loading visual and hint at reloading.
      // "Not Submitted" is reserved for has_image=0 (rendered statically
      // at HTML build time; never reached by this JS path).
      var markPending = function () {
        var status = wrap.querySelector('.profile-image-status');
        if (status) status.textContent = 'Loading… try reloading';
      };
      // Image already decoded (served from Cache Storage / memory) — skip the
      // loading flash entirely.
      if (img.complete && img.naturalWidth > 0) {
        markLoaded();
      } else if (img.complete) {
        markPending();
      } else {
        img.addEventListener('load', markLoaded, { once: true });
        img.addEventListener(
          'error',
          function () {
            var s = img.getAttribute('data-slug');
            if (s && img.src.indexOf('.png') === -1) {
              img.src = '/images/' + s + '.png?v=' + FELLOWS_UI_DIAG;
              img.addEventListener('load', markLoaded, { once: true });
              img.addEventListener('error', markPending, { once: true });
            } else {
              markPending();
            }
          },
          { once: true }
        );
      }
    }
  }

  function escapeHtml(s) {
    if (s == null) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  // Transient bottom-of-page toast. role="status" so screen readers announce it
  // without yanking focus. Singleton element re-used across calls.
  var toastEl = null;
  var toastTimer = null;
  function showToast(msg, ttlMs) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'app-toast';
      toastEl.id = 'app-toast';
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg || '';
    toastEl.classList.add('app-toast--visible');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      if (toastEl) toastEl.classList.remove('app-toast--visible');
    }, ttlMs || 3000);
  }

  // ===== Groups feature (PR 1): draft state, rail rendering, marker sync ===

  function loadGroupDraft() {
    try {
      var raw = localStorage.getItem(GROUP_DRAFT_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      if (Array.isArray(d.members)) {
        groupDraft.members = new Set(d.members);
      }
      if (d.memberNames && typeof d.memberNames === 'object') {
        groupDraft.memberNames = d.memberNames;
      }
      groupDraft.title = typeof d.title === 'string' ? d.title : '';
      groupDraft.titleEdited = !!d.titleEdited;
    } catch (e) {
      // Corrupt draft; ignore — user can rebuild the selection.
    }
  }

  function saveGroupDraft() {
    try {
      var snapshot = {
        members: [],
        memberNames: groupDraft.memberNames,
        title: groupDraft.title,
        titleEdited: groupDraft.titleEdited
      };
      groupDraft.members.forEach(function (rid) { snapshot.members.push(rid); });
      localStorage.setItem(GROUP_DRAFT_KEY, JSON.stringify(snapshot));
    } catch (e) {
      // Quota or disabled storage — silent. The rail still works in-memory.
    }
  }

  function deriveAutoTitle(query) {
    var q = (query || '').trim();
    if (!q) return '';
    if (q.charAt(0) === '#') return q;
    return q.charAt(0).toUpperCase() + q.slice(1);
  }

  function setRailStatus(msg, kind) {
    if (!groupRailStatusEl) return;
    groupRailStatusEl.textContent = msg || '';
    groupRailStatusEl.classList.remove(
      'group-rail-status--info',
      'group-rail-status--warn'
    );
    if (kind) {
      groupRailStatusEl.classList.add('group-rail-status--' + kind);
    }
  }

  function renderRailHeader() {
    if (!groupRailTitleEl || !groupRailHelperEl || !groupRailCreateEl) return;
    var editing = isEditing();
    var eyebrowEl = groupRailEyebrowEl;
    if (eyebrowEl) {
      eyebrowEl.textContent = editing ? 'editing group' : 'add to a group';
    }
    var query = (searchInputEl && searchInputEl.value || '').trim();
    var autoTitle = deriveAutoTitle(query);
    var displayed = (editing || groupDraft.titleEdited) ? groupDraft.title : autoTitle;
    if (document.activeElement !== groupRailTitleEl) {
      groupRailTitleEl.value = displayed;
    }
    // Edit mode: never show the cream auto-state. Compose mode behaves as before.
    if (editing || groupDraft.titleEdited) {
      groupRailTitleEl.classList.remove('group-rail-title--auto');
    } else {
      groupRailTitleEl.classList.add('group-rail-title--auto');
    }
    var n = groupDraft.members.size;
    var fellows = n + ' fellow' + (n === 1 ? '' : 's');
    var helper;
    if (editing) {
      helper = fellows;
    } else if (groupDraft.titleEdited) {
      helper = fellows;
    } else if (autoTitle) {
      helper = 'auto-named — click to rename · ' + fellows;
    } else {
      helper = 'type a name, or search to auto-fill · ' + fellows;
    }
    groupRailHelperEl.textContent = helper;
    // Edit mode: always enabled (Done editing). Compose mode: disabled when no members.
    groupRailCreateEl.disabled = !editing && n === 0;
    groupRailCreateEl.textContent = editing ? 'Done editing' : 'Create new group';
    var footnoteEl = document.querySelector('.group-rail-footnote');
    if (footnoteEl) {
      footnoteEl.textContent = editing
        ? 'changes save automatically as you add or remove.'
        : 'saves immediately to your groups. You can rename and edit it later.';
    }
  }

  function renderRailMembers() {
    if (!groupRailMembersEl) return;
    groupRailMembersEl.innerHTML = '';
    groupDraft.members.forEach(function (rid) {
      var li = document.createElement('li');
      li.className = 'group-rail-member';
      var name = document.createElement('span');
      name.className = 'group-rail-member-name';
      name.textContent = groupDraft.memberNames[rid] || rid;
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'group-rail-member-remove';
      rm.title = 'remove';
      rm.textContent = '×';
      rm.addEventListener('click', function () {
        toggleDraftMember(rid, name.textContent);
      });
      li.appendChild(name);
      li.appendChild(rm);
      groupRailMembersEl.appendChild(li);
    });
  }

  function renderRail() {
    renderRailHeader();
    renderRailMembers();
    // Mirror selection state onto body class so the FAB renders only
    // when there's something to compose with — see initComposerFab().
    if (typeof updateComposerFabFromDraft === 'function') {
      updateComposerFabFromDraft();
    }
  }

  function setMarkerEl(markEl, on) {
    if (!markEl) return;
    markEl.textContent = on ? '✓' : '+';
    markEl.title = on ? 'remove from group' : 'add to group';
    markEl.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) {
      markEl.classList.add('dir-mark--on');
    } else {
      markEl.classList.remove('dir-mark--on');
    }
  }

  function refreshAllMarkers() {
    if (!directoryListEl) return;
    var marks = directoryListEl.querySelectorAll('.dir-mark');
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      var rid = m.dataset.recordId;
      setMarkerEl(m, !!(rid && groupDraft.members.has(rid)));
    }
  }

  function refreshDetailAddLink() {
    if (!detailEl) return;
    var link = detailEl.querySelector('.detail-add-to-group');
    if (!link) return;
    var rid = link.dataset.recordId;
    var on = !!(rid && groupDraft.members.has(rid));
    link.textContent = on ? 'remove from group' : 'add to group';
  }

  function toggleDraftMember(rid, name) {
    if (!rid) return;
    if (groupDraft.members.has(rid)) {
      groupDraft.members.delete(rid);
      delete groupDraft.memberNames[rid];
    } else {
      groupDraft.members.add(rid);
      if (name) {
        groupDraft.memberNames[rid] = name;
      }
    }
    persistDraft();
    renderRail();
    refreshAllMarkers();
    refreshDetailAddLink();
    updateBulkBar();
  }

  function updateBulkBar() {
    if (!bulkSelectBarEl || !bulkSelectInputEl || !bulkSelectTextEl) return;
    var query = (searchInputEl && searchInputEl.value || '').trim();
    var filtered = !!query || hasEmailOnly;
    if (!filtered || !displayedList || !displayedList.length) {
      bulkSelectBarEl.classList.add('hidden');
      return;
    }
    bulkSelectBarEl.classList.remove('hidden');
    var allSelected = displayedList.every(function (f) {
      return f.record_id && groupDraft.members.has(f.record_id);
    });
    bulkSelectInputEl.checked = allSelected;
    bulkSelectTextEl.textContent =
      (allSelected ? 'deselect' : 'select') + ' all ' + displayedList.length + ' results';
  }

  function bulkToggleVisible() {
    if (!displayedList || !displayedList.length) return;
    var allSelected = displayedList.every(function (f) {
      return f.record_id && groupDraft.members.has(f.record_id);
    });
    displayedList.forEach(function (f) {
      if (!f.record_id) return;
      if (allSelected) {
        groupDraft.members.delete(f.record_id);
        delete groupDraft.memberNames[f.record_id];
      } else {
        groupDraft.members.add(f.record_id);
        groupDraft.memberNames[f.record_id] = f.name || f.record_id;
      }
    });
    persistDraft();
    renderRail();
    refreshAllMarkers();
    refreshDetailAddLink();
    updateBulkBar();
  }

  function clearDraftAfterSave() {
    groupDraft.members = new Set();
    groupDraft.memberNames = {};
    groupDraft.title = '';
    groupDraft.titleEdited = false;
    saveGroupDraft();
    renderRail();
    refreshAllMarkers();
    refreshDetailAddLink();
    updateBulkBar();
  }

  // --- PR 4: edit mode -------------------------------------------------

  function persistDraft() {
    // Compose mode: the draft IS the saved state, so localStorage is the
    // store. Edit mode: localStorage is left alone (it holds the user's
    // backed-up compose draft); persistence happens via PATCH against the
    // saved group instead.
    if (groupDraft.editingGroupId == null) {
      saveGroupDraft();
    } else {
      patchEditedGroupMembership();
    }
  }

  function patchEditedGroupMembership() {
    if (groupDraft.editingGroupId == null) return;
    if (!dataProvider || typeof dataProvider.updateGroup !== 'function') return;
    var ids = [];
    groupDraft.members.forEach(function (rid) { ids.push(rid); });
    dataProvider
      .updateGroup(groupDraft.editingGroupId, { fellow_record_ids: ids })
      .catch(function () {
        showToast('Could not save change');
      });
  }

  function patchEditedGroupName(name) {
    if (groupDraft.editingGroupId == null) return;
    if (!dataProvider || typeof dataProvider.updateGroup !== 'function') return;
    var trimmed = (name || '').replace(/^\s+|\s+$/g, '');
    if (!trimmed) return;
    dataProvider
      .updateGroup(groupDraft.editingGroupId, { name: trimmed })
      .then(function () {
        // Update banner text in case the user paused editing.
        if (editModeBannerNameEl) editModeBannerNameEl.textContent = trimmed;
      })
      .catch(function () {
        showToast('Could not save name');
      });
  }

  function showEditBanner(name) {
    if (!editModeBannerEl || !editModeBannerNameEl) return;
    editModeBannerNameEl.textContent = name || '';
    editModeBannerEl.classList.remove('hidden');
  }

  function hideEditBanner() {
    if (editModeBannerEl) editModeBannerEl.classList.add('hidden');
  }

  function snapshotComposeDraft() {
    // Plain object so it isn't tangled with the live Set / mutations.
    var members = [];
    groupDraft.members.forEach(function (rid) { members.push(rid); });
    return {
      members: members,
      memberNames: Object.assign({}, groupDraft.memberNames),
      title: groupDraft.title,
      titleEdited: groupDraft.titleEdited
    };
  }

  function restoreComposeDraft(snap) {
    if (!snap) snap = { members: [], memberNames: {}, title: '', titleEdited: false };
    groupDraft.members = new Set(snap.members || []);
    groupDraft.memberNames = snap.memberNames || {};
    groupDraft.title = snap.title || '';
    groupDraft.titleEdited = !!snap.titleEdited;
    groupDraft.editingGroupId = null;
    groupDraft.editEntrySnapshot = null;
  }

  function enterEditMode(groupId) {
    if (!dataProvider || typeof dataProvider.getGroup !== 'function') {
      showToast('Edit mode is unavailable in this mode');
      window.location.hash = '#/groups';
      return;
    }
    // Preserve the user's compose draft so the detour into edit mode
    // doesn't clobber their in-progress new group.
    if (groupDraft.editingGroupId == null) {
      composeDraftBackup = snapshotComposeDraft();
    }
    dataProvider.getGroup(groupId)
      .then(function (group) {
        if (!group) {
          showToast('Group not found');
          window.location.hash = '#/groups';
          return;
        }
        var memberIds = (group.members || []).map(function (m) { return m.record_id; });
        // Snapshot for cancel-edits.
        groupDraft.editEntrySnapshot = {
          name: group.name || '',
          note: group.note || '',
          fellow_record_ids: memberIds.slice()
        };
        groupDraft.editingGroupId = group.id;
        // Replace draft with the group's current state. memberNames are
        // best-effort: members[].name comes from the dev-server JOIN; on
        // OPFS we resolved them from fellowsBySlug at getGroup time.
        groupDraft.members = new Set(memberIds);
        groupDraft.memberNames = {};
        (group.members || []).forEach(function (m) {
          if (m.record_id) {
            groupDraft.memberNames[m.record_id] = m.name || m.record_id;
          }
        });
        groupDraft.title = group.name || '';
        // In edit mode the title field shows the live group name (no cream
        // auto-state) — set titleEdited so renderRailHeader treats it as
        // user-authored.
        groupDraft.titleEdited = true;

        // Clear search and uncheck has-email so the directory is unrestricted.
        if (searchInputEl) {
          searchInputEl.value = '';
        }
        if (hasEmailFilterEl) {
          hasEmailFilterEl.checked = false;
        }
        hasEmailOnly = false;
        showEditBanner(group.name || '(untitled)');
        setShellChrome('groups', 'Editing — ' + (group.name || '(untitled)'));
        // The detail pane during edit mode shows the current fellow detail
        // (or the group's detail page that brought us here, depending on
        // hash). We render the directory afresh and let the existing route
        // handler resolve the detail.
        if (Array.isArray(list) && list.length) {
          renderDirectory();
        }
        renderRail();
        refreshAllMarkers();
        refreshDetailAddLink();
        updateBulkBar();
      })
      .catch(function (err) {
        if (err && err.localDataUnavailable) {
          // listGroups will surface the full panel on the destination page.
          window.location.hash = '#/groups';
          return;
        }
        showToast('Could not load group');
        window.location.hash = '#/groups';
      });
  }

  function exitEditMode() {
    if (groupDraft.editingGroupId == null) return;
    // Cancel any pending name PATCH; it would race against the snapshot.
    if (editTitlePatchTimer) {
      clearTimeout(editTitlePatchTimer);
      editTitlePatchTimer = null;
    }
    hideEditBanner();
    restoreComposeDraft(composeDraftBackup);
    composeDraftBackup = null;
    saveGroupDraft();
    // Re-derive has-email filter from localStorage so we restore whatever
    // the user had set before edit mode.
    hasEmailOnly = loadHasEmailFilter();
    if (hasEmailFilterEl) hasEmailFilterEl.checked = hasEmailOnly;
    if (Array.isArray(list) && list.length) {
      renderDirectory();
    }
    renderRail();
    refreshAllMarkers();
    refreshDetailAddLink();
    updateBulkBar();
  }

  function isEditing() {
    return groupDraft.editingGroupId != null;
  }

  function handleCancelEdits() {
    if (!isEditing()) return;
    var snapshot = groupDraft.editEntrySnapshot;
    var gid = groupDraft.editingGroupId;
    if (!snapshot) {
      // Nothing to revert to (unexpected — should never happen since
      // edit-mode-entry only ever fires for saved groups).
      window.location.hash = '#/groups/' + encodeURIComponent(String(gid));
      return;
    }
    // Cancel any pending name-debounce so it doesn't overwrite the revert.
    if (editTitlePatchTimer) {
      clearTimeout(editTitlePatchTimer);
      editTitlePatchTimer = null;
    }
    dataProvider
      .updateGroup(gid, {
        name: snapshot.name,
        note: snapshot.note,
        fellow_record_ids: snapshot.fellow_record_ids
      })
      .then(function () {
        showToast('Edits reverted.');
        window.location.hash = '#/groups/' + encodeURIComponent(String(gid));
      })
      .catch(function () {
        showToast('Could not revert edits.');
      });
  }

  function handleCreateGroupClick() {
    if (!groupRailCreateEl) return;
    if (groupDraft.members.size === 0) return;
    if (!dataProvider || typeof dataProvider.createGroup !== 'function') {
      setRailStatus('Groups not available right now.', 'warn');
      return;
    }
    var titleVal = groupDraft.titleEdited
      ? groupDraft.title
      : deriveAutoTitle((searchInputEl && searchInputEl.value) || '');
    if (!titleVal || !titleVal.trim()) {
      titleVal = 'Untitled group';
    }
    var ids = [];
    groupDraft.members.forEach(function (rid) { ids.push(rid); });
    setRailStatus('Saving…', 'info');
    groupRailCreateEl.disabled = true;
    dataProvider.createGroup({
      name: titleVal,
      note: '',
      fellow_record_ids: ids
    })
      .then(function (group) {
        if (!group || group.id == null) {
          setRailStatus('Save returned no group; please retry.', 'warn');
          groupRailCreateEl.disabled = groupDraft.members.size === 0;
          return;
        }
        clearDraftAfterSave();
        setRailStatus('Group saved.', 'info');
        // Navigate to the new group's detail page. route() runs on
        // hashchange and renders renderGroupDetailPage.
        window.location.hash = '#/groups/' + encodeURIComponent(String(group.id));
      })
      .catch(function (err) {
        if (err && err.localDataUnavailable) {
          setRailStatus(
            'This browser can\'t save groups locally. Open Groups for details.',
            'warn'
          );
          groupRailCreateEl.disabled = groupDraft.members.size === 0;
          window.location.hash = '#/groups';
          return;
        }
        setRailStatus(
          'Could not save: ' + (err && err.message ? err.message : 'unknown error'),
          'warn'
        );
        groupRailCreateEl.disabled = groupDraft.members.size === 0;
      });
  }

  // ===== End groups feature ============================================

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
    aboutHtml += '<p class="about-users-manual"><a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md" target="_blank" rel="noopener">User Guide</a> \u2014 how to install, browse, save groups, export, and manage settings.</p>';
    aboutHtml += '<p class="about-update-check">';
    aboutHtml += '<button type="button" id="about-check-updates" class="about-check-updates-btn">Check for updates</button>';
    aboutHtml += '<span id="about-update-status" class="about-update-status" role="status" aria-live="polite"></span>';
    aboutHtml += '</p>';
    var serverLabel = bootBuildMeta.git_sha
      ? bootBuildMeta.git_sha + (bootBuildMeta.built_at ? ' · ' + bootBuildMeta.built_at : '')
      : (bootBuildMeta.built_at || 'unknown');
    aboutHtml += '<p class="about-build">';
    aboutHtml += '<span class="about-build-label">Build</span> ';
    aboutHtml += '<code class="about-build-value">app: ' + escapeHtml(FELLOWS_UI_DIAG) + '</code> ';
    aboutHtml += '<code class="about-build-value">server: ' + escapeHtml(serverLabel) + '</code>';
    aboutHtml += '</p>';
    aboutHtml += '<p class="about-repo"><a href="https://github.com/richbodo/fellows_local_db" target="_blank" rel="noopener">';
    aboutHtml += '<svg class="github-icon" viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>';
    aboutHtml += ' richbodo/fellows_local_db</a></p>';
    aboutHtml += '</div>';

    aboutHtml += '<h2 class="stats-title">Fellowship Statistics</h2>';
    aboutHtml += '<p class="stats-total" id="stats-total">Loading stats\u2026</p>';
    aboutHtml += '<p class="stats-images-cached" id="stats-images-cached">Counting cached profile photos\u2026</p>';
    aboutHtml += '<div class="stats-grid" id="stats-grid"></div>';
    aboutHtml += '</div>';
    detailEl.innerHTML = aboutHtml;

    // Wire the "Check for updates" button. Shares the same checker used by
    // the hourly poll so the user-visible status stays consistent with what
    // triggers the sw-update-banner.
    (function wireUpdateCheckButton() {
      var btn = document.getElementById('about-check-updates');
      var statusEl = document.getElementById('about-update-status');
      if (!btn || !statusEl) return;
      btn.addEventListener('click', function () {
        btn.disabled = true;
        statusEl.textContent = 'Checking\u2026';
        checkForServerUpdate().then(function (res) {
          btn.disabled = false;
          if (res.status === 'update-available') {
            statusEl.textContent = 'New version available \u2014 reload to apply.';
          } else if (res.status === 'up-to-date') {
            statusEl.textContent = 'You\u2019re on the latest version.';
          } else if (res.status === 'no-boot-snapshot') {
            statusEl.textContent = 'Version recorded \u2014 future checks will compare against this build.';
          } else {
            statusEl.textContent = 'Unable to reach the server right now. Try again later.';
          }
        });
      });
    })();

    // Render the "N / M" cached-photo counter using the existing helper.
    // Snapshotted at page-render time; refreshes on next About visit.
    (function renderImagesCachedCounter() {
      var el = document.getElementById('stats-images-cached');
      if (!el) return;
      var withImageTotal = 0;
      var source = Array.isArray(fullFellowsCache) ? fullFellowsCache : list;
      source.forEach(function (f) {
        if (f && (f.has_image === 1 || f.has_image === true)) withImageTotal++;
      });
      countCachedImages().then(function (result) {
        if (!result) {
          el.textContent = 'Profile photos cached locally: unknown (Cache API unavailable on this browser).';
          return;
        }
        el.textContent =
          'Profile photos cached locally: ' + result.count + ' / ' + withImageTotal +
          ' (fellows who uploaded a photo). Reload this page to update the count.';
      }).catch(function () {
        el.textContent = 'Profile photos cached locally: unknown.';
      });
    })();

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
          gh += statsSection('Fellows by Type', data.by_fellow_type, '#0066cc');
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
    var editMatch = hash.match(/^#\/edit\/(\d+)$/);
    var nextEditId = editMatch ? parseInt(editMatch[1], 10) : null;
    var directoryMatch = hash.match(/^#\/groups\/(\d+)\/directory$/);
    var groupMatch = !directoryMatch ? hash.match(/^#\/groups\/(\d+)$/) : null;

    // Tag <body> with the current focus mode so CSS can collapse the
    // global directory + composer rails (and, in edit mode, the central
    // pane). Always clear all four before adding the matching one so
    // navigating between routes doesn't leave a stale class behind.
    var body = document.body;
    body.classList.remove(
      'route-groups-list', 'route-group-detail',
      'route-group-edit', 'route-group-directory',
      'route-directory', 'route-about', 'route-settings', 'route-fellow'
    );
    if (directoryMatch) body.classList.add('route-group-directory');
    else if (groupMatch) body.classList.add('route-group-detail');
    else if (editMatch) body.classList.add('route-group-edit');
    else if (hash === '#/groups') body.classList.add('route-groups-list');
    else if (hash === '#/about') body.classList.add('route-about');
    else if (hash === '#/settings') body.classList.add('route-settings');
    else if (hash.indexOf('#/fellow/') === 0) body.classList.add('route-fellow');
    else body.classList.add('route-directory');

    // Sheets are route-local — close anything left open when the URL
    // changes so the next route renders cleanly.
    if (typeof closeComposerSheet === 'function' && body.classList.contains('composer-open')) {
      closeComposerSheet();
    }
    if (typeof closeKebabSheet === 'function' && isKebabSheetOpen()) {
      closeKebabSheet();
    }
    if (typeof closeGroupCardSheet === 'function' && groupCardSheetEl &&
        !groupCardSheetEl.classList.contains('hidden')) {
      closeGroupCardSheet();
    }
    if (typeof closeGroupActionbarSheet === 'function' && groupActionbarSheetEl &&
        !groupActionbarSheetEl.classList.contains('hidden')) {
      closeGroupActionbarSheet();
    }

    // Mobile shell chrome — appbar title + active tab. Renderers that
    // know a richer title (group name, fellow name) can overwrite by
    // calling setShellChrome again after their data resolves.
    if (hash === '#/about') setShellChrome('about', 'About');
    else if (hash === '#/settings') setShellChrome('settings', 'Settings');
    else if (hash === '#/groups') setShellChrome('groups', 'Groups');
    else if (groupMatch || directoryMatch || editMatch) setShellChrome('groups', 'Group');
    else if (hash.indexOf('#/fellow/') === 0) setShellChrome('directory', 'Fellow');
    else setShellChrome('directory', 'Directory');

    // Transition out of edit mode if the URL no longer points there. (Same
    // group still in editingGroupId? Different group? Either way, exit
    // first; if we're entering a new edit-mode session we re-enter below.)
    if (isEditing() && nextEditId !== groupDraft.editingGroupId) {
      exitEditMode();
    }
    if (hash === '#/about') {
      renderAboutPage();
      return;
    }
    if (hash === '#/settings') {
      renderSettingsPage();
      return;
    }
    if (hash === '#/groups') {
      renderGroupsPage();
      return;
    }
    if (directoryMatch) {
      renderGroupDirectoryPage(parseInt(directoryMatch[1], 10));
      return;
    }
    if (groupMatch) {
      renderGroupDetailPage(parseInt(groupMatch[1], 10));
      return;
    }
    if (editMatch) {
      // Edit mode is rail-driven; the central pane is hidden via CSS so
      // there's nothing useful to render there. Enter once per hash
      // visit; re-entering for the same id is a no-op.
      if (groupDraft.editingGroupId !== nextEditId) {
        enterEditMode(nextEditId);
      }
      return;
    }
    updateDetailFromHash();
  }

  // ===== Groups index + detail (PR 2) =====================================

  function renderGroupsPage() {
    if (!detailEl) return;
    var html =
      '<div class="groups-page">' +
        '<h2 class="groups-title">Groups</h2>' +
        '<p class="groups-meta" id="groups-meta">Loading groups…</p>' +
        '<div id="groups-list-wrap"></div>' +
        '<p class="groups-footer-hint">' +
          'Click a group’s name to open its detail page — that’s ' +
          'where you’ll contact the whole group, export, or edit. ' +
          'Deleting only removes the saved group; the fellows themselves are unaffected.' +
        '</p>' +
      '</div>';
    detailEl.innerHTML = html;
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (!dataProvider || typeof dataProvider.listGroups !== 'function') {
      var w0 = document.getElementById('groups-list-wrap');
      if (w0) w0.innerHTML = '<p class="placeholder">Groups not available in this mode.</p>';
      return;
    }
    dataProvider.listGroups()
      .then(function (groups) { renderGroupsList(groups || []); })
      .catch(function (err) {
        var wrap = document.getElementById('groups-list-wrap');
        var meta = document.getElementById('groups-meta');
        if (meta) meta.textContent = '';
        if (!wrap) return;
        if (err && err.localDataUnavailable) {
          wrap.innerHTML = renderLocalDataUnavailablePanel('groups');
        } else {
          wrap.innerHTML = '<p class="placeholder">Could not load groups.</p>';
        }
      });
  }

  function renderGroupsList(groups) {
    var wrap = document.getElementById('groups-list-wrap');
    var meta = document.getElementById('groups-meta');
    if (!wrap || !meta) return;
    if (!groups.length) {
      meta.textContent = '';
      wrap.innerHTML =
        '<p class="groups-empty">No groups yet. Build one from the directory by selecting fellows and tapping <b>Create new group</b>.</p>';
      return;
    }
    meta.textContent =
      groups.length + (groups.length === 1 ? ' saved group' : ' saved groups');
    var rowsHtml = groups.map(function (g) {
      var gidStr = String(g.id);
      var date = (g.created_at || '').slice(0, 10);
      var note = g.note || '';
      var noteHtml = note
        ? '<span class="groups-note">' + escapeHtml(note) + '</span>'
        : '<span class="groups-note groups-note--empty">—</span>';
      return (
        '<tr data-group-id="' + escapeHtml(gidStr) + '">' +
          '<td class="groups-cell-name">' +
            '<a class="groups-name-link" href="#/groups/' + escapeHtml(gidStr) + '">' +
              escapeHtml(g.name || '(untitled)') +
            '</a>' +
          '</td>' +
          '<td class="groups-cell-num">' + escapeHtml(String(g.count || 0)) + '</td>' +
          '<td class="groups-cell-date">' + escapeHtml(date) + '</td>' +
          '<td>' + noteHtml + '</td>' +
          '<td class="groups-cell-actions">' +
            '<a href="#/groups/' + escapeHtml(gidStr) + '/directory" class="groups-action groups-action-view" data-group-id="' + escapeHtml(gidStr) + '">visual directory</a>' +
            '<a href="#/edit/' + escapeHtml(gidStr) + '" class="groups-action groups-action-edit" data-group-id="' + escapeHtml(gidStr) + '">edit</a>' +
            '<a href="#" class="groups-action groups-action-rename" data-group-id="' + escapeHtml(gidStr) + '">rename</a>' +
            '<a href="#" class="groups-action groups-action-delete" data-group-id="' + escapeHtml(gidStr) + '">delete</a>' +
          '</td>' +
        '</tr>'
      );
    }).join('');
    // Path A from plans/mobile_redesign/css_porting_notes.md §8: render both
    // a desktop table and a mobile card list from the same group array.
    // CSS picks which is visible at the breakpoint (>1024px → table,
    // ≤1024px → cards). Each card wires the same actions as the matching
    // table row — wireGroupsListActions covers both DOM shapes.
    var cardsHtml = groups.map(function (g) {
      var gidStr = String(g.id);
      var date = (g.created_at || '').slice(0, 10);
      var note = g.note || '';
      var memberCount = g.count || 0;
      var memberWord = memberCount === 1 ? ' member' : ' members';
      var noteHtml = note
        ? '<p class="groups-card__note">' + escapeHtml(note) + '</p>'
        : '';
      return (
        '<li class="groups-card" data-group-id="' + escapeHtml(gidStr) + '">' +
          '<a class="groups-card__title-link" href="#/groups/' + escapeHtml(gidStr) + '">' +
            escapeHtml(g.name || '(untitled)') +
          '</a>' +
          '<p class="groups-card__meta">' +
            escapeHtml(String(memberCount)) + memberWord +
            ' · created ' + escapeHtml(date) +
          '</p>' +
          noteHtml +
          '<div class="groups-card__actions">' +
            '<a href="#/groups/' + escapeHtml(gidStr) + '/directory" class="groups-card__action groups-card__action--visual" data-group-id="' + escapeHtml(gidStr) + '" aria-label="Open visual directory">▤ Visual</a>' +
            '<a href="#/edit/' + escapeHtml(gidStr) + '" class="groups-card__action groups-card__action--edit" data-group-id="' + escapeHtml(gidStr) + '" aria-label="Edit members">✎ Edit</a>' +
            '<button type="button" class="groups-card__kebab" data-group-id="' + escapeHtml(gidStr) + '" aria-label="More" aria-haspopup="dialog" aria-expanded="false">' +
              '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
                '<circle cx="12" cy="5" r="1.7" fill="currentColor" />' +
                '<circle cx="12" cy="12" r="1.7" fill="currentColor" />' +
                '<circle cx="12" cy="19" r="1.7" fill="currentColor" />' +
              '</svg>' +
            '</button>' +
          '</div>' +
        '</li>'
      );
    }).join('');
    wrap.innerHTML =
      '<table class="groups-table">' +
        '<thead><tr>' +
          '<th>Name</th>' +
          '<th class="groups-th-num">Members</th>' +
          '<th>Created</th>' +
          '<th>Note</th>' +
          '<th class="groups-th-actions"></th>' +
        '</tr></thead>' +
        '<tbody>' + rowsHtml + '</tbody>' +
      '</table>' +
      '<ul class="groups-card-list">' + cardsHtml + '</ul>';
    wireGroupsListActions(wrap);
  }

  function wireGroupsListActions(wrap) {
    var renameLinks = wrap.querySelectorAll('.groups-action-rename');
    for (var i = 0; i < renameLinks.length; i++) {
      renameLinks[i].addEventListener('click', function (ev) {
        ev.preventDefault();
        startInlineRename(wrap, this.dataset.groupId);
      });
    }
    var deleteLinks = wrap.querySelectorAll('.groups-action-delete');
    for (var j = 0; j < deleteLinks.length; j++) {
      deleteLinks[j].addEventListener('click', function (ev) {
        ev.preventDefault();
        confirmAndDeleteGroup(wrap, this.dataset.groupId);
      });
    }
    // Per-card kebab on mobile. Opens a sheet with Rename / Delete; both
    // proxy to the same handlers as the desktop inline links above.
    var kebabs = wrap.querySelectorAll('.groups-card__kebab');
    for (var k = 0; k < kebabs.length; k++) {
      kebabs[k].addEventListener('click', function (ev) {
        ev.preventDefault();
        openGroupCardSheet(wrap, this.dataset.groupId, this);
      });
    }
  }

  function openGroupCardSheet(wrap, gidStr, sourceBtn) {
    if (!groupCardSheetEl) return;
    groupCardSheetEl.dataset.groupId = gidStr;
    if (sourceBtn) sourceBtn.setAttribute('aria-expanded', 'true');
    // Stash a closer that resets the source's aria-expanded back.
    groupCardSheetEl._fellowsResetExpanded = function () {
      if (sourceBtn) sourceBtn.setAttribute('aria-expanded', 'false');
    };
    groupCardSheetEl._fellowsHostWrap = wrap;
    groupCardSheetEl.classList.remove('hidden');
    groupCardSheetEl.removeAttribute('hidden');
    if (groupCardScrimEl) {
      groupCardScrimEl.classList.remove('hidden');
      groupCardScrimEl.removeAttribute('hidden');
    }
  }

  function closeGroupCardSheet() {
    if (!groupCardSheetEl) return;
    groupCardSheetEl.classList.add('hidden');
    groupCardSheetEl.setAttribute('hidden', '');
    if (groupCardScrimEl) {
      groupCardScrimEl.classList.add('hidden');
      groupCardScrimEl.setAttribute('hidden', '');
    }
    if (typeof groupCardSheetEl._fellowsResetExpanded === 'function') {
      groupCardSheetEl._fellowsResetExpanded();
      groupCardSheetEl._fellowsResetExpanded = null;
    }
    groupCardSheetEl._fellowsHostWrap = null;
  }

  function startInlineRename(wrap, gidStr) {
    // Edit on whichever DOM form is currently visible (table row at
    // desktop, card at mobile). offsetParent is null when an ancestor
    // has display:none, which is exactly how the breakpoint switches
    // them.
    var row = wrap.querySelector('tr[data-group-id="' + gidStr + '"]');
    var card = wrap.querySelector('li.groups-card[data-group-id="' + gidStr + '"]');
    var rowVisible = !!(row && row.offsetParent !== null);
    var cardVisible = !!(card && card.offsetParent !== null);
    if (rowVisible) {
      startInlineRenameOnTable(row, gidStr);
    } else if (cardVisible) {
      startInlineRenameOnCard(card, gidStr);
    } else if (row) {
      startInlineRenameOnTable(row, gidStr);
    } else if (card) {
      startInlineRenameOnCard(card, gidStr);
    }
  }

  function startInlineRenameOnTable(row, gidStr) {
    var nameCell = row.querySelector('.groups-cell-name');
    var nameLink = nameCell ? nameCell.querySelector('.groups-name-link') : null;
    if (!nameCell || !nameLink) return;
    var current = nameLink.textContent;
    var input = createRenameInput(current);
    nameCell.innerHTML = '';
    nameCell.appendChild(input);
    bindRenameCommit(input, gidStr, current, function (savedName) {
      restoreNameLink(nameCell, gidStr, savedName);
    }, function () {
      nameCell.innerHTML = '<span class="groups-saving">saving…</span>';
    });
  }

  function startInlineRenameOnCard(card, gidStr) {
    var link = card.querySelector('.groups-card__title-link');
    if (!link) return;
    var current = link.textContent;
    var input = createRenameInput(current);
    input.classList.add('groups-rename-input--card');
    var holder = link.parentNode;
    holder.replaceChild(input, link);
    bindRenameCommit(input, gidStr, current, function (savedName) {
      var a = document.createElement('a');
      a.className = 'groups-card__title-link';
      a.href = '#/groups/' + gidStr;
      a.textContent = savedName;
      if (input.parentNode === holder) holder.replaceChild(a, input);
    }, function () {
      input.disabled = true;
    });
  }

  function createRenameInput(initial) {
    var input = document.createElement('input');
    input.type = 'text';
    input.value = initial;
    input.className = 'groups-rename-input';
    input.maxLength = 200;
    return input;
  }

  function bindRenameCommit(input, gidStr, current, onSettled, onSaving) {
    input.focus();
    input.select();
    var done = false;
    function commit(save) {
      if (done) return;
      done = true;
      var next = (input.value || '').replace(/^\s+|\s+$/g, '');
      if (!save || !next || next === current) {
        onSettled(current);
        return;
      }
      if (typeof onSaving === 'function') onSaving();
      dataProvider.updateGroup(parseInt(gidStr, 10), { name: next })
        .then(function (updated) {
          onSettled((updated && updated.name) || next);
        })
        .catch(function () {
          onSettled(current);
        });
    }
    input.addEventListener('blur', function () { commit(true); });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); commit(true); }
      else if (ev.key === 'Escape') { ev.preventDefault(); commit(false); }
    });
  }

  function restoreNameLink(nameCell, gidStr, name) {
    nameCell.innerHTML = '';
    var a = document.createElement('a');
    a.className = 'groups-name-link';
    a.href = '#/groups/' + encodeURIComponent(gidStr);
    a.textContent = name;
    nameCell.appendChild(a);
  }

  function confirmAndDeleteGroup(wrap, gidStr) {
    var row = wrap.querySelector('tr[data-group-id="' + gidStr + '"]');
    var name = row ? row.querySelector('.groups-name-link').textContent : '(untitled)';
    var ok = window.confirm(
      'Delete the group "' + name + '"? ' +
      'This removes only the group, not the fellows themselves.'
    );
    if (!ok) return;
    dataProvider.deleteGroup(parseInt(gidStr, 10)).then(function (deleted) {
      if (!deleted) return;
      if (row && row.parentNode) row.parentNode.removeChild(row);
      if (!wrap.querySelector('tbody tr')) {
        var meta = document.getElementById('groups-meta');
        if (meta) meta.textContent = '';
        wrap.innerHTML =
          '<p class="groups-empty">No groups yet. Build one from the directory by selecting fellows and tapping <b>Create new group</b>.</p>';
      } else {
        // Update the saved-count line.
        var remaining = wrap.querySelectorAll('tbody tr').length;
        var meta2 = document.getElementById('groups-meta');
        if (meta2) {
          meta2.textContent = remaining + (remaining === 1 ? ' saved group' : ' saved groups');
        }
      }
    });
  }

  // Recipient-count thresholds for the Contact button. mailto: URL length
  // is the underlying constraint (see docs/persistence_and_upgrades.md and
  // PR 1 design discussion); recipient count is a friendlier proxy.
  var GROUPS_CONTACT_WARN_AT = 50;
  var GROUPS_CONTACT_HARD_AT = 100;

  function collectGroupEmails(group) {
    var out = [];
    var missing = 0;
    if (!group || !group.members) return { emails: out, missing: 0 };
    group.members.forEach(function (m) {
      var rid = m.record_id;
      var fellow = rid && fellowsBySlug.get(rid);
      var email = fellow && fellow.contact_email;
      if (email && String(email).trim()) {
        out.push(String(email).trim());
      } else {
        missing += 1;
      }
    });
    return { emails: out, missing: missing };
  }

  function buildContactMailto(group, mode, emails) {
    // Email addresses don't need URL-encoding for normal characters; the
    // mailto: spec accepts them verbatim. encodeURIComponent on the subject
    // handles spaces / unicode safely.
    var key = mode === 'bcc' ? 'bcc' : 'cc';
    var subject = encodeURIComponent(group.name || '');
    var url = 'mailto:?' + key + '=' + emails.join(',');
    if (subject) url += '&subject=' + subject;
    return url;
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    // Fallback: textarea + document.execCommand. Older Safari needs this.
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        resolve();
      } catch (e) {
        reject(e);
      }
    });
  }

  // Inline 📋 button rendered next to mailto:/tel: links. The label is the
  // noun ("email", "phone number") used for both the hover/aria title and
  // the toast on success. A single delegated handler (wireCopyButtons,
  // installed once at boot) reads data-copy and copies it.
  function copyButton(value, label) {
    if (value == null || String(value) === '') return '';
    return ' <button type="button" class="copy-btn" data-copy="' +
      escapeHtml(String(value)) + '" data-copy-label="' + escapeHtml(label) +
      '" aria-label="Copy ' + escapeHtml(label) + '" title="Copy ' +
      escapeHtml(label) + '">📋</button>';
  }

  // Single document-level click delegate for every .copy-btn the app
  // renders (per-fellow rows, modal rows, group action bar). Idempotent —
  // wireCopyButtons() is called once during init.
  var copyButtonsWired = false;
  function wireCopyButtons() {
    if (copyButtonsWired) return;
    copyButtonsWired = true;
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('.copy-btn');
      if (!btn) return;
      ev.preventDefault();
      var value = btn.getAttribute('data-copy') || '';
      var label = btn.getAttribute('data-copy-label') || 'value';
      if (!value) return;
      copyToClipboard(value).then(
        function () {
          var ucfirst = label.charAt(0).toUpperCase() + label.slice(1);
          showToast(ucfirst + ' copied');
        },
        function () { showToast('Copy failed'); }
      );
    });
  }

  function renderGroupDetailPage(groupId) {
    if (!detailEl) return;
    detailEl.innerHTML = '<p class="placeholder">Loading group…</p>';
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (!dataProvider || typeof dataProvider.getGroup !== 'function') {
      detailEl.innerHTML = '<p class="placeholder">Could not load group.</p>';
      return;
    }
    dataProvider.getGroup(groupId).then(function (group) {
      if (!group) {
        detailEl.innerHTML =
          '<p class="placeholder">Group not found. <a href="#/groups">Back to groups</a>.</p>';
        return;
      }
      var name = group.name || '(untitled)';
      setShellChrome('groups', name);
      var members = group.members || [];
      var memberCount = members.length;
      var memberWord = memberCount === 1 ? ' fellow' : ' fellows';
      var emailInfo = collectGroupEmails(group);
      var totalEmails = emailInfo.emails.length;
      var hasNote = !!(group.note && String(group.note).trim());
      var noteEditLabel = hasNote ? 'edit' : 'add a note';
      var html = '<div class="group-detail-page" data-group-id="' + escapeHtml(String(group.id)) + '">' +
        '<p class="group-detail-breadcrumb">' +
          '<a href="#/groups">groups</a> › ' +
          '<span id="group-detail-breadcrumb-name">' + escapeHtml(name) + '</span>' +
        '</p>' +
        '<h2 class="group-detail-title">' +
          '<span class="group-detail-title-text" id="group-detail-title-text">' + escapeHtml(name) + '</span>' +
          '<a href="#" class="group-detail-title-edit" id="group-detail-title-edit" role="button" ' +
            'aria-label="Rename group" title="Rename group">✎</a>' +
        '</h2>' +
        '<p class="group-detail-meta">' +
          escapeHtml(String(memberCount)) + memberWord +
          ' · created ' + escapeHtml((group.created_at || '').slice(0, 10)) +
        '</p>';

      // Action bar, two rows. Row 1 = "✉ Mail to the whole group" + CC/BCC
      // pill (the primary action and its modifier live together). Row 2 =
      // "✎ Edit members" + "⬇ Export a directory" (the secondary actions).
      // The Mail button is a native <a href="mailto:…">; the hard-threshold
      // path intercepts the click and copies addresses to the clipboard
      // instead. Group rename is reachable via the pencil next to the
      // title; "Edit members" is membership-only.
      var hasEmails = totalEmails > 0;
      var hardLimit = totalEmails >= GROUPS_CONTACT_HARD_AT;
      var initialHref = (hasEmails && !hardLimit)
        ? buildContactMailto(group, 'cc', emailInfo.emails)
        : '';
      var contactClasses = 'group-action-btn group-action-btn--primary' +
        (hasEmails ? '' : ' group-action-btn--disabled');
      var contactAttrs = '';
      if (initialHref) contactAttrs += ' href="' + escapeHtml(initialHref) + '"';
      if (!hasEmails) contactAttrs += ' aria-disabled="true" title="No email addresses available for this group"';
      // Always-on "Copy email addresses" affordance. Sits on Row 1 next
      // to the CC/BCC pill so users whose mailto: handler is broken or
      // missing have an unconditional path to the addresses (no need to
      // hit the recipient threshold to discover it).
      var copyAttrs = '';
      if (!hasEmails) {
        copyAttrs += ' disabled aria-disabled="true" title="No email addresses available for this group"';
      } else {
        copyAttrs += ' title="Copy ' + escapeHtml(String(totalEmails)) +
          ' email address' + (totalEmails === 1 ? '' : 'es') + ' to the clipboard"';
      }
      // The action bar carries every group-level action. At desktop
      // (>1024px) all six are inline across two rows. At mobile
      // (≤1024px) it pins to the bottom of the viewport: Mail and
      // Export remain inline as the two primary verbs; the rest
      // (CC/BCC, Copy emails, Edit members) are reachable via the
      // kebab on the bar, which opens the #group-actionbar-sheet.
      html +=
        '<div class="group-action-bar">' +
          '<div class="group-action-row">' +
            '<a class="' + contactClasses + '" id="group-action-contact" role="button"' + contactAttrs + '>' +
              '✉ Mail to the whole group' +
            '</a>' +
            '<div class="group-contact-mode" role="group" aria-label="Recipient header">' +
              '<button type="button" class="group-mode-pill group-mode-pill--active" data-mode="cc" aria-pressed="true">CC</button>' +
              '<button type="button" class="group-mode-pill" data-mode="bcc" aria-pressed="false">BCC</button>' +
            '</div>' +
            '<button type="button" class="group-action-btn" id="group-action-copy-emails"' + copyAttrs + '>' +
              '📋 Copy email addresses' +
            '</button>' +
          '</div>' +
          '<div class="group-action-row">' +
            '<button type="button" class="group-action-btn" id="group-action-edit">✎ Edit members</button>' +
            '<button type="button" class="group-action-btn" id="group-action-export">⬇ Export a directory</button>' +
            '<button type="button" class="group-action-btn group-action-btn--more" id="group-action-more"' +
              ' aria-label="More actions" aria-haspopup="dialog" aria-expanded="false">' +
              '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
                '<circle cx="12" cy="5" r="1.7" fill="currentColor" />' +
                '<circle cx="12" cy="12" r="1.7" fill="currentColor" />' +
                '<circle cx="12" cy="19" r="1.7" fill="currentColor" />' +
              '</svg>' +
            '</button>' +
          '</div>' +
        '</div>';

      // Threshold banner. Soft warning between WARN and HARD, hard warning ≥ HARD.
      // The "Copy email addresses" button on the action bar is always present;
      // the banners now point users to it rather than carrying their own copy link.
      if (totalEmails >= GROUPS_CONTACT_HARD_AT) {
        html +=
          '<div class="group-contact-banner group-contact-banner--hard" role="status">' +
            escapeHtml(String(totalEmails)) + ' recipients — too many for one mailto: URL on most clients. ' +
            'Use <b>Copy email addresses</b> above and paste into a new message.' +
          '</div>';
      } else if (totalEmails >= GROUPS_CONTACT_WARN_AT) {
        html +=
          '<div class="group-contact-banner group-contact-banner--soft" role="status">' +
            escapeHtml(String(totalEmails)) + ' recipients — long mailto: URLs may be truncated by some clients. ' +
            'Use <b>Copy email addresses</b> above if your client misbehaves.' +
          '</div>';
      } else if (emailInfo.missing > 0 && totalEmails > 0) {
        html +=
          '<div class="group-contact-banner group-contact-banner--info" role="status">' +
            escapeHtml(String(emailInfo.missing)) +
            ' member' + (emailInfo.missing === 1 ? '' : 's') +
            ' without an email; ' +
            escapeHtml(String(totalEmails)) +
            ' will be addressed.' +
          '</div>';
      }

      // Inline export panel. Two-phase: pick a format and Export → file
      // is built locally and downloaded. After success, the result row
      // surfaces an Email button alongside the View link, which opens
      // the user's mail client with a body referencing the just-saved
      // file. The email input lives inside the result row (it's only
      // relevant after the file exists); it prefills from getSelfEmail()
      // and lets the user override per-export without leaving the page.
      var slugFn = slugifyForFilename(name);
      var initialSelfEmail = getSelfEmail();
      html +=
        '<div class="group-export-panel hidden" id="group-export-panel" aria-label="Export options">' +
          '<div class="group-export-head">Export a directory</div>' +
          '<div class="group-export-options">' +
            '<label class="group-export-format">' +
              '<input type="radio" name="export-format" id="export-format-pdf" value="pdf" checked> ' +
              '<span><b>PDF directory</b><br><code>' + escapeHtml(slugFn) + '.pdf</code></span>' +
            '</label>' +
            '<label class="group-export-format">' +
              '<input type="radio" name="export-format" id="export-format-html" value="html"> ' +
              '<span><b>HTML directory</b><br><code>' + escapeHtml(slugFn) + '.html</code> · self-contained, view in any browser</span>' +
            '</label>' +
          '</div>' +
          '<div class="group-export-actions">' +
            '<button type="button" class="group-export-cancel">cancel</button>' +
            '<button type="button" class="group-export-go" id="group-export-go">Export</button>' +
          '</div>' +
          '<div class="group-export-result hidden" id="group-export-result" aria-live="polite">' +
            '<div class="group-export-result-row">' +
              '<span class="group-export-result-text" id="group-export-result-text"></span> ' +
              '<a href="#" class="group-export-view" id="group-export-view" target="_blank" rel="noopener">View</a>' +
            '</div>' +
            '<div class="group-export-email-row">' +
              '<input type="email" id="export-self-email-addr" class="group-export-email-input' +
                (initialSelfEmail ? '' : ' group-export-email-input--empty') + '" ' +
                'placeholder="your@email.com" autocomplete="email" ' +
                'value="' + escapeHtml(initialSelfEmail) + '">' +
              '<span class="group-export-email-cue" id="export-self-email-cue">' +
                (initialSelfEmail ? 'override here to send to a different address' : 'enter your email to send the export to yourself') +
              '</span>' +
              '<button type="button" class="group-export-email-btn" id="group-export-email-btn">Email it to me</button>' +
            '</div>' +
          '</div>' +
          '<div class="group-contact-banner hidden" id="group-export-banner" role="status"></div>' +
          '<p class="group-export-note" id="group-export-note">' +
            'Files land in your <b>Downloads</b> folder (or via the system share sheet on iOS). ' +
            'PDF includes clickable mailto: links; the HTML directory is one self-contained file.' +
          '</p>' +
        '</div>';

      // Cream note callout. Always rendered; "edit" / "add a note" link beside it.
      html +=
        '<div class="group-detail-note-wrap" id="group-detail-note-wrap">' +
          (hasNote
            ? '<span class="group-detail-note-text" id="group-detail-note-text">' + escapeHtml(group.note) + '</span>'
            : '<span class="group-detail-note-empty" id="group-detail-note-text">No note yet.</span>') +
          ' <a href="#" class="group-detail-note-edit" id="group-detail-note-edit">' +
            escapeHtml(noteEditLabel) +
          '</a>' +
        '</div>';

      if (memberCount) {
        html +=
          '<table class="group-detail-members">' +
            '<thead><tr><th>Member</th></tr></thead><tbody>';
        members.forEach(function (m) {
          var rid = m.record_id || '';
          var fellow = fellowsBySlug.get(rid);
          var slug = fellow && fellow.slug ? fellow.slug : '';
          var href = slug ? '#/fellow/' + encodeURIComponent(slug) : '#';
          html += '<tr><td><a href="' + escapeHtml(href) + '">' +
            escapeHtml(m.name || rid) + '</a></td></tr>';
        });
        html += '</tbody></table>';
      } else {
        html += '<p class="placeholder">No members yet.</p>';
      }
      html += '</div>';
      detailEl.innerHTML = html;
      wireGroupDetailPage(group, emailInfo);
    }).catch(function (err) {
      if (err && err.localDataUnavailable) {
        detailEl.innerHTML = renderLocalDataUnavailablePanel('this group');
      } else {
        detailEl.innerHTML = '<p class="placeholder">Could not load group.</p>';
      }
    });
  }

  function slugifyForFilename(name) {
    return String(name || '')
      .toLowerCase()
      .replace(/^#/, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'group';
  }

  // ===== Visual directory + export helpers (PR 5) ===========================

  // Inline SVG placeholder, same one as the design's screen-output mock.
  // Used both in-app (when an image is missing) and in the standalone
  // export (so the ZIP doesn't need a separate placeholder asset).
  var PORTRAIT_SVG_PLACEHOLDER =
    "data:image/svg+xml;utf8," + encodeURIComponent(
      "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'>" +
      "<rect width='80' height='80' fill='%23d9cfc1'/>" +
      "<circle cx='40' cy='32' r='14' fill='%23a89682'/>" +
      "<path d='M14 76c4-16 18-22 26-22s22 6 26 22z' fill='%23a89682'/>" +
      "</svg>"
    );

  /** Trigger a Blob download. On platforms that support
   *  navigator.share with files (iOS 16.4+, modern Android), prefer the
   *  share sheet — gives the user Save to Files / AirDrop / Mail
   *  options. Fall back to <a download> for desktop and older mobile.
   *  Per the PR 1 mitigation plan in docs/persistence_and_upgrades.md. */
  function downloadBlob(blob, filename) {
    try {
      if (navigator.canShare && typeof File === 'function') {
        var file = new File([blob], filename, { type: blob.type || 'application/octet-stream' });
        if (navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file], title: filename });
        }
      }
    } catch (e) { /* fall through to <a download> */ }
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        try { document.body.removeChild(a); } catch (e) {}
        try { URL.revokeObjectURL(url); } catch (e) {}
        resolve();
      }, 100);
    });
  }

  /** For each member, look up the full fellow record from fellowsBySlug.
   *  Returns array of {record_id, name, slug, contact_email, mobile_number,
   *  has_image, key_links, key_links_urls} — best effort, missing fields
   *  default to empty. */
  function resolveMembersForView(group) {
    var out = [];
    (group.members || []).forEach(function (m) {
      var rid = m.record_id;
      var fellow = rid ? fellowsBySlug.get(rid) : null;
      out.push({
        record_id: rid,
        name: (fellow && fellow.name) || m.name || rid || '',
        slug: (fellow && fellow.slug) || '',
        contact_email: (fellow && fellow.contact_email) || '',
        mobile_number: (fellow && fellow.mobile_number) || '',
        has_image: fellow ? (fellow.has_image === 1 || fellow.has_image === true) : false,
        key_links: (fellow && fellow.key_links) || '',
        key_links_urls: (fellow && fellow.key_links_urls) || []
      });
    });
    out.sort(function (a, b) {
      var an = (a.name || '').toLowerCase();
      var bn = (b.name || '').toLowerCase();
      return an < bn ? -1 : (an > bn ? 1 : 0);
    });
    return out;
  }

  function buildContactBarMailto(group, members) {
    var emails = members.map(function (m) {
      return (m.contact_email || '').trim();
    }).filter(Boolean);
    var subject = encodeURIComponent(group.name || '');
    var url = 'mailto:?cc=' + emails.join(',');
    if (subject) url += '&subject=' + subject;
    return { url: url, count: emails.length };
  }

  function renderGroupDirectoryPage(groupId) {
    if (!detailEl) return;
    detailEl.innerHTML = '<p class="placeholder">Loading group directory…</p>';
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (!dataProvider || typeof dataProvider.getGroup !== 'function') {
      detailEl.innerHTML = '<p class="placeholder">Could not load group.</p>';
      return;
    }
    dataProvider.getGroup(groupId).then(function (group) {
      if (!group) {
        detailEl.innerHTML =
          '<p class="placeholder">Group not found. <a href="#/groups">Back to groups</a>.</p>';
        return;
      }
      var members = resolveMembersForView(group);
      var contact = buildContactBarMailto(group, members);
      var name = group.name || '(untitled)';
      setShellChrome('groups', name + ' — Visual');
      var html = '<div class="group-directory-page" data-group-id="' + escapeHtml(String(group.id)) + '">' +
        '<p class="group-detail-breadcrumb">' +
          '<a href="#/groups">groups</a> › ' +
          '<a href="#/groups/' + escapeHtml(String(group.id)) + '">' + escapeHtml(name) + '</a> › directory' +
        '</p>' +
        '<h2 class="group-directory-title">' + escapeHtml(name) + '</h2>' +
        '<p class="group-directory-meta">' +
          escapeHtml(String(members.length)) + ' fellow' + (members.length === 1 ? '' : 's') +
          ' · created ' + escapeHtml((group.created_at || '').slice(0, 10)) +
          (group.note ? ' · ' + escapeHtml(group.note) : '') +
        '</p>';
      if (contact.count) {
        html +=
          '<div class="group-directory-contact-bar">' +
            '<a href="' + escapeHtml(contact.url) + '" class="group-directory-contact-link">✉ Contact the whole group</a>' +
            '<span class="group-directory-contact-helper">' +
              'opens your mail client with all ' + escapeHtml(String(contact.count)) + ' addresses in CC' +
            '</span>' +
          '</div>';
      }
      html += '<div class="group-directory-grid">';
      members.forEach(function (m, idx) {
        var slug = m.slug;
        var imgSrc;
        if (m.has_image && slug) {
          imgSrc = '/images/' + encodeURIComponent(slug) + '.jpg?v=' + escapeHtml(FELLOWS_UI_DIAG);
        } else {
          imgSrc = PORTRAIT_SVG_PLACEHOLDER;
        }
        html += '<button type="button" class="group-directory-cell" data-member-idx="' + escapeHtml(String(idx)) + '">' +
          '<div class="group-directory-portrait">' +
            '<img src="' + escapeHtml(imgSrc) + '" alt="' + escapeHtml(m.name) +
            '" loading="lazy" onerror="this.onerror=null;this.src=\'' + PORTRAIT_SVG_PLACEHOLDER + '\';">' +
          '</div>' +
          '<div class="group-directory-name">' + escapeHtml(m.name) + '</div>' +
        '</button>';
      });
      html += '</div></div>';
      detailEl.innerHTML = html;
      wireGroupDirectoryCells(detailEl, members);
    }).catch(function (err) {
      if (err && err.localDataUnavailable) {
        detailEl.innerHTML = renderLocalDataUnavailablePanel('this group directory');
      } else {
        detailEl.innerHTML = '<p class="placeholder">Could not load group directory.</p>';
      }
    });
  }

  /** Click handler for visual-directory portraits/names: open the
   *  contact-card modal. Single delegated listener, lookup by index. */
  function wireGroupDirectoryCells(wrap, members) {
    var grid = wrap.querySelector('.group-directory-grid');
    if (!grid) return;
    grid.addEventListener('click', function (ev) {
      var cell = ev.target.closest('.group-directory-cell');
      if (!cell) return;
      ev.preventDefault();
      var idx = parseInt(cell.getAttribute('data-member-idx'), 10);
      if (isNaN(idx) || !members[idx]) return;
      openFellowContactModal(members[idx]);
    });
  }

  /** Inline contact-info modal launched from the visual-directory grid.
   *  Shows name, email (mailto:), phone (tel:), key links, and a link
   *  to the fellow's full profile. Closes on backdrop click, X button,
   *  or Escape key. */
  function openFellowContactModal(m) {
    closeFellowContactModal();
    var slug = m.slug;
    var imgSrc;
    if (m.has_image && slug) {
      imgSrc = '/images/' + encodeURIComponent(slug) + '.jpg?v=' + escapeHtml(FELLOWS_UI_DIAG);
    } else {
      imgSrc = PORTRAIT_SVG_PLACEHOLDER;
    }

    var rowsHtml = '';
    if (m.contact_email) {
      var email = String(m.contact_email);
      rowsHtml +=
        '<li class="fellow-modal-row">' +
          '<span class="fellow-modal-label">email</span>' +
          '<span class="fellow-modal-value">' +
            '<a href="mailto:' + escapeHtml(email) + '">' +
              escapeHtml(email) +
            '</a>' +
            copyButton(email, 'email') +
          '</span>' +
        '</li>';
    }
    if (m.mobile_number) {
      var phoneText = String(m.mobile_number).trim();
      var phoneTel = phoneText.replace(/[^+\d]/g, '');
      rowsHtml +=
        '<li class="fellow-modal-row">' +
          '<span class="fellow-modal-label">phone</span>' +
          '<span class="fellow-modal-value">' +
            '<a href="tel:' + escapeHtml(phoneTel) + '">' +
              escapeHtml(phoneText) +
            '</a>' +
            copyButton(phoneText, 'phone number') +
          '</span>' +
        '</li>';
    }
    if (Array.isArray(m.key_links_urls) && m.key_links_urls.length) {
      var labels = (m.key_links || '').split(',');
      var links = m.key_links_urls.map(function (url, i) {
        var label = (labels[i] || url || '').trim() || url;
        return '<a class="fellow-modal-value" href="' + escapeHtml(url) +
          '" target="_blank" rel="noopener">' + escapeHtml(label) + '</a>';
      }).join('<br>');
      rowsHtml +=
        '<li class="fellow-modal-row">' +
          '<span class="fellow-modal-label">links</span>' +
          '<span class="fellow-modal-value">' + links + '</span>' +
        '</li>';
    }
    if (!rowsHtml) {
      rowsHtml =
        '<li class="fellow-modal-row fellow-modal-row--empty">' +
          'No public contact info on file.' +
        '</li>';
    }

    var profileHref = slug ? ('#/fellow/' + encodeURIComponent(slug)) : '';
    var profileHtml = profileHref
      ? '<a class="fellow-modal-profile-link" href="' + escapeHtml(profileHref) + '">View full profile →</a>'
      : '';

    var overlay = document.createElement('div');
    overlay.className = 'fellow-modal-overlay';
    overlay.setAttribute('role', 'presentation');
    overlay.innerHTML =
      '<div class="fellow-modal-card" role="dialog" aria-modal="true" aria-labelledby="fellow-modal-name">' +
        '<button type="button" class="fellow-modal-close" aria-label="Close">×</button>' +
        '<div class="fellow-modal-portrait">' +
          '<img src="' + escapeHtml(imgSrc) + '" alt="' + escapeHtml(m.name) +
          '" onerror="this.onerror=null;this.src=\'' + PORTRAIT_SVG_PLACEHOLDER + '\';">' +
        '</div>' +
        '<h3 class="fellow-modal-name" id="fellow-modal-name">' + escapeHtml(m.name || '') + '</h3>' +
        '<ul class="fellow-modal-rows">' + rowsHtml + '</ul>' +
        profileHtml +
      '</div>';

    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (ev) {
      if (ev.target === overlay || ev.target.closest('.fellow-modal-close')) {
        closeFellowContactModal();
      }
    });
    // Profile-link click is a hash navigation; close the modal so it
    // doesn't sit on top of the detail view.
    var profileLink = overlay.querySelector('.fellow-modal-profile-link');
    if (profileLink) {
      profileLink.addEventListener('click', function () {
        closeFellowContactModal();
      });
    }
    document.addEventListener('keydown', fellowContactModalKeydown);
    var closeBtn = overlay.querySelector('.fellow-modal-close');
    if (closeBtn) closeBtn.focus();
  }

  function fellowContactModalKeydown(ev) {
    if (ev.key === 'Escape' || ev.key === 'Esc') {
      closeFellowContactModal();
    }
  }

  function closeFellowContactModal() {
    var overlay = document.querySelector('.fellow-modal-overlay');
    if (overlay && overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
    document.removeEventListener('keydown', fellowContactModalKeydown);
  }

  // ===== Standalone HTML export (PR 5) ======================================

  /** Minimal CSS inlined into the single-file HTML export. */
  var EXPORT_CSS =
    'body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;' +
    'background:#fafafa;color:#222;margin:0;padding:1.4rem 1.6rem;}' +
    'h1{margin:0 0 0.2rem;font-size:1.4rem;}' +
    '.meta{font-size:0.85rem;color:#666;margin-bottom:0.6rem;}' +
    '.contact-bar{display:flex;align-items:center;gap:0.75rem;padding:0.5rem 0.7rem;' +
    'margin-bottom:1rem;background:#dbeafe;border:1px solid #c4d0e0;border-radius:3px;' +
    'font-size:0.85rem;}' +
    '.contact-bar a{color:#0066cc;text-decoration:underline;font-weight:500;}' +
    '.helper{color:#64748b;font-size:0.78rem;}' +
    '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:0.9rem;' +
    'margin-bottom:1.6rem;}' +
    '.cell{display:block;text-decoration:none;color:inherit;text-align:center;}' +
    '.portrait{width:100%;aspect-ratio:1/1;border-radius:50%;border:1px solid #ccc;' +
    'overflow:hidden;background:#eee;}' +
    '.portrait img{width:100%;height:100%;object-fit:cover;display:block;}' +
    '.cell-name{font-size:0.78rem;margin-top:4px;line-height:1.2;}' +
    '.back-link{display:inline-block;margin:1.2rem 0 0.4rem;color:#0066cc;font-size:0.85rem;}' +
    '.fellow-card{max-width:420px;margin:0 auto 1rem;background:#fff;border:1px solid #ccc;' +
    'border-radius:4px;padding:1.2rem 1.4rem;}' +
    '.fellow-card h2{margin:0 0 0.4rem;}' +
    '.fellow-portrait{width:120px;height:120px;border-radius:50%;border:1px solid #ccc;' +
    'overflow:hidden;margin:0 auto 0.8rem;background:#eee;}' +
    '.fellow-portrait img{width:100%;height:100%;object-fit:cover;}' +
    '.field-table{width:100%;border-collapse:separate;border-spacing:0 0.3em;font-size:0.9rem;}' +
    '.field-table td{padding:0.3em 0.5em;}' +
    '.field-table td.label{background:#f0f0f0;font-weight:600;width:32%;}' +
    '.field-table a{color:#0066cc;}' +
    '.fellow-anchor{display:block;height:0;overflow:hidden;}';

  function bytesToBase64(bytes) {
    // Chunk to keep String.fromCharCode argument list bounded.
    var CHUNK = 0x8000;
    var binary = '';
    for (var i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return window.btoa(binary);
  }

  function buildExportIndexGrid(members, imgMap) {
    var html = '<div class="grid">';
    members.forEach(function (m) {
      var slug = m.slug || slugifyForFilename(m.name);
      var imgSrc = imgMap[m.slug] || PORTRAIT_SVG_PLACEHOLDER;
      html += '<a class="cell" href="#fellow-' + escapeHtml(slug) + '">' +
        '<div class="portrait"><img src="' + escapeHtml(imgSrc) +
        '" alt="' + escapeHtml(m.name) + '"></div>' +
        '<div class="cell-name">' + escapeHtml(m.name) + '</div>' +
      '</a>';
    });
    return html + '</div>';
  }

  function buildExportFellowSection(group, m, imgMap) {
    var slug = m.slug || slugifyForFilename(m.name);
    var imgSrc = imgMap[m.slug] || PORTRAIT_SVG_PLACEHOLDER;
    var rows = [];
    if (m.contact_email) {
      rows.push('<tr><td class="label">email</td><td><a href="mailto:' +
        escapeHtml(m.contact_email) + '">' + escapeHtml(m.contact_email) + '</a></td></tr>');
    }
    if (m.mobile_number) {
      rows.push('<tr><td class="label">phone</td><td><a href="tel:' +
        escapeHtml(String(m.mobile_number).replace(/[^+\d]/g, '')) + '">' +
        escapeHtml(String(m.mobile_number)) + '</a></td></tr>');
    }
    if (Array.isArray(m.key_links_urls) && m.key_links_urls.length) {
      var labels = (m.key_links || '').split(',');
      var links = m.key_links_urls.map(function (url, i) {
        var label = (labels[i] || url || '').trim() || url;
        return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' +
          escapeHtml(label) + '</a>';
      }).join(', ');
      rows.push('<tr><td class="label">links</td><td>' + links + '</td></tr>');
    }
    return '<a class="fellow-anchor" id="fellow-' + escapeHtml(slug) + '"></a>' +
      '<a class="back-link" href="#top">‹ back to ' + escapeHtml(group.name || 'directory') + '</a>' +
      '<div class="fellow-card">' +
        '<div class="fellow-portrait"><img src="' + escapeHtml(imgSrc) +
          '" alt="' + escapeHtml(m.name) + '"></div>' +
        '<h2>' + escapeHtml(m.name) + '</h2>' +
        (rows.length
          ? '<table class="field-table"><tbody>' + rows.join('') + '</tbody></table>'
          : '<p>(No public contact info on file.)</p>') +
      '</div>';
  }

  /** Fetch the JPG bytes for a member's portrait, returning a Uint8Array
   *  or null if the image isn't available. Tries .jpg first, then .png. */
  function fetchMemberPortrait(slug) {
    var jpgUrl = '/images/' + encodeURIComponent(slug) + '.jpg';
    var pngUrl = '/images/' + encodeURIComponent(slug) + '.png';
    return fetch(jpgUrl, { credentials: 'same-origin' })
      .then(function (r) {
        if (r.ok) {
          return r.arrayBuffer().then(function (buf) {
            return { ext: 'jpg', bytes: new Uint8Array(buf) };
          });
        }
        return fetch(pngUrl, { credentials: 'same-origin' }).then(function (r2) {
          if (r2.ok) {
            return r2.arrayBuffer().then(function (buf) {
              return { ext: 'png', bytes: new Uint8Array(buf) };
            });
          }
          return null;
        });
      })
      .catch(function () { return null; });
  }

  /** Build a Blob containing a single self-contained HTML file:
   *  inline <style>, the index portrait grid, then per-fellow cards as
   *  anchored sections (#fellow-<slug>). Portraits are inlined as data:
   *  URIs so the file is portable and viewable in any browser without
   *  extracting an archive. */
  function exportGroupAsHtml(group) {
    var members = resolveMembersForView(group);
    var imageJobs = members
      .filter(function (m) { return m.has_image && m.slug; })
      .map(function (m) {
        return fetchMemberPortrait(m.slug).then(function (res) {
          if (!res) return null;
          var mime = res.ext === 'png' ? 'image/png' : 'image/jpeg';
          return { slug: m.slug, url: 'data:' + mime + ';base64,' + bytesToBase64(res.bytes) };
        });
      });
    return Promise.all(imageJobs).then(function (results) {
      var imgMap = {};
      results.forEach(function (r) { if (r) imgMap[r.slug] = r.url; });
      var contact = buildContactBarMailto(group, members);
      var name = group.name || '(untitled)';
      var html =
        '<!doctype html>\n' +
        '<html lang="en"><head><meta charset="utf-8">' +
        '<title>' + escapeHtml(name) + '</title>' +
        '<meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<style>' + EXPORT_CSS + '</style>' +
        '</head><body>' +
        '<a id="top"></a>' +
        '<h1>' + escapeHtml(name) + '</h1>' +
        '<p class="meta">' +
          escapeHtml(String(members.length)) + ' fellow' + (members.length === 1 ? '' : 's') +
          ' · exported ' + escapeHtml(new Date().toISOString().slice(0, 10)) +
          (group.note ? ' · ' + escapeHtml(group.note) : '') +
        '</p>';
      if (contact.count) {
        html +=
          '<div class="contact-bar">' +
            '<a href="' + escapeHtml(contact.url) + '">✉ Contact the whole group</a>' +
            '<span class="helper">opens your mail client with all ' +
              escapeHtml(String(contact.count)) + ' addresses in CC</span>' +
          '</div>';
      }
      html += buildExportIndexGrid(members, imgMap);
      members.forEach(function (m) {
        html += buildExportFellowSection(group, m, imgMap);
      });
      html += '</body></html>\n';
      return new Blob([html], { type: 'text/html;charset=utf-8' });
    });
  }

  // ===== PDF export via jsPDF (PR 5) ========================================

  function exportGroupAsPdf(group) {
    if (typeof window.jspdf === 'undefined' || !window.jspdf.jsPDF) {
      return Promise.reject(new Error('jsPDF not loaded'));
    }
    var members = resolveMembersForView(group);
    var doc = new window.jspdf.jsPDF({ unit: 'pt', format: 'a4' });
    var pageW = doc.internal.pageSize.getWidth();
    var pageH = doc.internal.pageSize.getHeight();
    var marginX = 36;
    var marginY = 48;

    // Header
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(18);
    doc.text(group.name || '(untitled)', marginX, marginY);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(102);
    var meta = members.length + (members.length === 1 ? ' fellow' : ' fellows') +
      ' · exported ' + new Date().toISOString().slice(0, 10);
    if (group.note) meta += ' · ' + group.note;
    doc.text(meta, marginX, marginY + 16);
    doc.setTextColor(34);

    // Fetch all portraits up front so the layout pass is sync.
    var imageJobs = members.map(function (m) {
      if (!m.has_image || !m.slug) return Promise.resolve({ member: m, image: null });
      return fetchMemberPortrait(m.slug).then(function (res) {
        return { member: m, image: res };
      });
    });
    return Promise.all(imageJobs).then(function (resolved) {
      // Grid: 4 columns, ~120pt cells.
      var cols = 4;
      var cellW = (pageW - marginX * 2) / cols;
      var portraitSize = 70;
      var nameLineH = 12;
      var emailLineH = 10;
      var rowH = portraitSize + nameLineH + emailLineH + 18;
      var startY = marginY + 36;
      var x = marginX;
      var y = startY;
      var col = 0;
      resolved.forEach(function (entry) {
        var m = entry.member;
        var image = entry.image;
        if (y + rowH > pageH - marginY) {
          doc.addPage();
          y = marginY;
        }
        var cx = x + (cellW - portraitSize) / 2;
        if (image) {
          try {
            var fmt = image.ext === 'png' ? 'PNG' : 'JPEG';
            doc.addImage(image.bytes, fmt, cx, y, portraitSize, portraitSize);
          } catch (e) { /* malformed image bytes; fall through */ }
        } else {
          // Draw a soft circle placeholder.
          doc.setDrawColor(204);
          doc.setFillColor(238);
          doc.circle(cx + portraitSize / 2, y + portraitSize / 2, portraitSize / 2, 'FD');
        }
        // Name (centered)
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        var nameY = y + portraitSize + nameLineH;
        var nameTextW = doc.getStringUnitWidth(m.name) * 9;
        doc.text(m.name, x + (cellW - nameTextW) / 2, nameY);
        // Email (clickable mailto annotation)
        if (m.contact_email) {
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8);
          doc.setTextColor(0, 102, 204);
          var emailY = nameY + emailLineH;
          var emailW = doc.getStringUnitWidth(m.contact_email) * 8;
          var emailX = x + (cellW - emailW) / 2;
          doc.text(m.contact_email, emailX, emailY);
          if (typeof doc.link === 'function') {
            doc.link(emailX, emailY - 8, emailW, 10, { url: 'mailto:' + m.contact_email });
          }
          doc.setTextColor(34);
        }
        col += 1;
        if (col >= cols) {
          col = 0;
          x = marginX;
          y += rowH;
        } else {
          x += cellW;
        }
      });
      var blob = doc.output('blob');
      return blob;
    });
  }

  // ===== Settings page (PR 5) ==============================================

  function renderSettingsPage() {
    if (!detailEl) return;
    var html = '<div class="settings-page">' +
      '<h2 class="settings-title">Settings</h2>' +
      '<p class="settings-intro">' +
        'These settings live on this device only, in <code>relationships.db</code>. ' +
        'They survive app updates and Clear App Cache.' +
      '</p>' +
      '<form id="settings-form" class="settings-form" autocomplete="off">' +
        '<label class="settings-field">' +
          '<span class="settings-label">Your email (for &ldquo;email it to me&rdquo; on group exports)</span>' +
          '<input type="email" id="settings-self-email" class="settings-input" placeholder="you@example.com" />' +
          '<span class="settings-hint">' +
            'Captured automatically when you used the magic-link gate. ' +
            'Override here to send exports to a different mailbox.' +
          '</span>' +
        '</label>' +
        '<div class="settings-actions">' +
          '<button type="submit" class="settings-save">Save</button>' +
          '<span id="settings-status" class="settings-status" aria-live="polite"></span>' +
        '</div>' +
      '</form>' +
      '<div class="settings-section" id="settings-export-section">' +
        '<h3 class="settings-section-title">Your saved data</h3>' +
        '<p class="settings-hint">' +
          'Download a copy of <code>relationships.db</code> — your saved groups, ' +
          'group notes, fellow tags, and settings. ' +
          'The app also auto-snapshots this file before every app upgrade ' +
          '(rotated to keep the newest 3); see Diagnostics for the current list.' +
        '</p>' +
        '<button type="button" id="settings-download-userdata" class="settings-download">' +
          '⬇ Download my user data' +
        '</button>' +
        '<span id="settings-download-status" class="settings-status" aria-live="polite"></span>' +
      '</div>' +
      '<div class="settings-section" id="settings-restore-section">' +
        '<h3 class="settings-section-title">Restore from backup</h3>' +
        '<p class="settings-hint">' +
          'Replace your current saved data with a backup. ' +
          'Reversible — the app captures a snapshot of your current data ' +
          'into the auto-backup rotation before each restore, so the recent-backups ' +
          'list below always lets you undo.' +
        '</p>' +
        '<input type="file" id="settings-restore-file" accept=".db,.sqlite,application/octet-stream" hidden />' +
        '<button type="button" id="settings-restore-pick" class="settings-download">' +
          '⬆ Restore from a file…' +
        '</button>' +
        '<span id="settings-restore-status" class="settings-status" aria-live="polite"></span>' +
        '<h4 class="settings-section-subtitle">Recent auto-backups</h4>' +
        '<p class="settings-hint" id="settings-backup-list-empty">' +
          'No auto-backups on this device yet — they’re written before each app upgrade.' +
        '</p>' +
        '<ul id="settings-backup-list" class="settings-backup-list" hidden></ul>' +
      '</div>' +
      '</div>';
    detailEl.innerHTML = html;
    var input = document.getElementById('settings-self-email');
    var status = document.getElementById('settings-status');
    var form = document.getElementById('settings-form');
    var downloadBtn = document.getElementById('settings-download-userdata');
    var downloadStatus = document.getElementById('settings-download-status');
    var exportSection = document.getElementById('settings-export-section');

    if (downloadBtn) {
      downloadBtn.addEventListener('click', function () {
        if (!dataProvider || typeof dataProvider.exportRelationshipsBytes !== 'function') {
          if (downloadStatus) downloadStatus.textContent = 'Export not available in this mode.';
          return;
        }
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Preparing…';
        dataProvider.exportRelationshipsBytes()
          .then(function (bytes) {
            if (!bytes || !bytes.byteLength) {
              if (downloadStatus) downloadStatus.textContent = 'No data yet to download.';
              return;
            }
            var ts = new Date().toISOString().replace(/[:.]/g, '-');
            var filename = 'relationships-' + ts + '.db';
            var blob = new Blob([bytes], { type: 'application/octet-stream' });
            return downloadBlob(blob, filename).then(function () {
              if (downloadStatus) {
                downloadStatus.textContent =
                  'Downloaded ' + filename + ' (' + bytes.byteLength + ' bytes).';
              }
            });
          })
          .catch(function (err) {
            if (err && err.localDataUnavailable) {
              if (exportSection) exportSection.style.display = 'none';
              return;
            }
            if (downloadStatus) {
              downloadStatus.textContent =
                'Could not export: ' + (err && err.message || String(err));
            }
          })
          .then(function () {
            downloadBtn.disabled = false;
            downloadBtn.textContent = '⬇ Download my user data';
          });
      });
    }

    // ===== Restore from backup =====
    var restoreSection = document.getElementById('settings-restore-section');
    var restoreFile = document.getElementById('settings-restore-file');
    var restorePick = document.getElementById('settings-restore-pick');
    var restoreStatus = document.getElementById('settings-restore-status');
    var backupListEl = document.getElementById('settings-backup-list');
    var backupListEmptyEl = document.getElementById('settings-backup-list-empty');

    function hideRestoreSection() {
      if (restoreSection) restoreSection.style.display = 'none';
    }

    function fmtCounts(c) {
      if (!c) return '(unreadable)';
      return c.groups + ' groups · ' + c.notes + ' notes · ' + c.tags + ' tags';
    }

    function fmtBytes(n) {
      if (!n && n !== 0) return '';
      if (n < 1024) return n + ' B';
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      return (n / (1024 * 1024)).toFixed(2) + ' MB';
    }

    function fmtBackupTimestamp(name) {
      // BACKUP_PREFIX is "relationships.db.bak."; the rest is an ISO
      // timestamp with ":" and "." replaced by "-".
      var prefix = 'relationships.db.bak.';
      if (name.indexOf(prefix) !== 0) return name;
      var stamp = name.slice(prefix.length);
      // Reverse the [:.] → '-' substitution so it parses back as ISO.
      var iso = stamp.replace(
        /^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})-(\d+)Z?$/,
        '$1-$2-$3T$4:$5:$6.$7Z'
      );
      var d = new Date(iso);
      if (isNaN(d.getTime())) return stamp;
      return d.toLocaleString();
    }

    // Build a multi-line confirm message showing the row-count delta
    // between current and incoming backup. Used by both restore paths.
    function buildConfirmMessage(currentCounts, incomingCounts, sourceLabel) {
      function deltaLine(label, key) {
        var cur = currentCounts ? currentCounts[key] : '?';
        var inc = incomingCounts[key];
        return '  • ' + label + ': ' + cur + ' → ' + inc;
      }
      return (
        'Restore from ' + sourceLabel + ' will replace your current saved data:\n' +
        deltaLine('Groups', 'groups') + '\n' +
        deltaLine('Group members', 'members') + '\n' +
        deltaLine('Group notes / fellow notes', 'notes') + '\n' +
        deltaLine('Fellow tags', 'tags') + '\n' +
        deltaLine('Settings', 'settings') + '\n\n' +
        'Your current data will first be saved as an auto-backup so you can undo.\n\n' +
        'Continue?'
      );
    }

    // Render the recent-auto-backups list. Each row: timestamp, content
    // summary, restore button. The list is enriched server-side (well,
    // provider-side) with row counts read out of each backup file, so
    // the user can choose by content rather than by timestamp guess.
    function refreshBackupList() {
      if (!backupListEl) return;
      if (!dataProvider || typeof dataProvider.listRelationshipsBackups !== 'function') {
        return;
      }
      dataProvider.listRelationshipsBackups()
        .then(function (backups) {
          if (!backups || !backups.length) {
            if (backupListEmptyEl) backupListEmptyEl.hidden = false;
            backupListEl.hidden = true;
            backupListEl.innerHTML = '';
            return;
          }
          if (backupListEmptyEl) backupListEmptyEl.hidden = true;
          backupListEl.hidden = false;
          // Newest first.
          backups.sort(function (a, b) {
            return b.name < a.name ? -1 : (b.name > a.name ? 1 : 0);
          });
          var html = '';
          for (var i = 0; i < backups.length; i++) {
            var b = backups[i];
            html +=
              '<li class="settings-backup-item">' +
                '<div class="settings-backup-meta">' +
                  '<div class="settings-backup-when">' + escapeHtml(fmtBackupTimestamp(b.name)) + '</div>' +
                  '<div class="settings-backup-summary">' +
                    (b.invalid
                      ? '<em>Backup unreadable: ' + escapeHtml(b.error || 'unknown error') + '</em>'
                      : escapeHtml(fmtCounts(b.counts) + ' · ' + fmtBytes(b.size))) +
                  '</div>' +
                '</div>' +
                '<button type="button" class="settings-backup-restore" ' +
                  'data-backup-name="' + escapeHtml(b.name) + '"' +
                  (b.invalid ? ' disabled' : '') +
                  '>Restore this</button>' +
              '</li>';
          }
          backupListEl.innerHTML = html;
        })
        .catch(function () {
          // Provider doesn't have backups (API path) or OPFS read failed.
          // Hide the section entirely; the file-picker still works only
          // on OPFS providers anyway.
          if (backupListEmptyEl) backupListEmptyEl.hidden = false;
          backupListEl.hidden = true;
          backupListEl.innerHTML = '';
        });
    }

    function flashRestoreStatus(text) {
      if (restoreStatus) restoreStatus.textContent = text;
    }

    function performImport(bytes, sourceLabel) {
      if (!dataProvider || typeof dataProvider.importRelationshipsBytes !== 'function') {
        flashRestoreStatus('Restore not available in this mode.');
        return Promise.resolve(null);
      }
      return Promise.all([
        dataProvider.inspectRelationshipsBytes(bytes),
        dataProvider.countRelationships()
      ]).then(function (results) {
        var inspection = results[0];
        var current = results[1];
        if (!inspection || !inspection.valid) {
          var msg = inspection && inspection.error
            ? 'Could not read backup: ' + inspection.error
            : 'Could not read backup.';
          flashRestoreStatus(msg);
          return null;
        }
        var ok = window.confirm(buildConfirmMessage(current, inspection.counts, sourceLabel));
        if (!ok) {
          flashRestoreStatus('Restore cancelled.');
          return null;
        }
        flashRestoreStatus('Restoring…');
        return dataProvider.importRelationshipsBytes(bytes).then(function (result) {
          flashRestoreStatus(
            'Restored from ' + sourceLabel + ' — ' +
            result.counts.groups + ' groups, ' +
            result.counts.notes + ' notes, ' +
            result.counts.tags + ' tags.' +
            (result.preRestoreSnapshot
              ? ' Previous data saved as auto-backup; click an entry below to undo.'
              : '')
          );
          // Refresh the backup list so the user can see the new
          // pre-restore snapshot land.
          refreshBackupList();
          return result;
        });
      }).catch(function (err) {
        if (err && err.localDataUnavailable) {
          hideRestoreSection();
          return null;
        }
        flashRestoreStatus('Restore failed: ' + (err && err.message || String(err)));
        return null;
      });
    }

    if (restorePick && restoreFile) {
      restorePick.addEventListener('click', function () { restoreFile.click(); });
      restoreFile.addEventListener('change', function () {
        var f = restoreFile.files && restoreFile.files[0];
        if (!f) return;
        flashRestoreStatus('Reading ' + f.name + '…');
        f.arrayBuffer().then(function (buf) {
          performImport(new Uint8Array(buf), '“' + f.name + '”');
        }).catch(function (e) {
          flashRestoreStatus('Could not read file: ' + (e && e.message || String(e)));
        }).then(function () {
          // Reset the input so picking the same file twice still fires change.
          try { restoreFile.value = ''; } catch (e) {}
        });
      });
    }

    if (backupListEl) {
      backupListEl.addEventListener('click', function (ev) {
        var btn = ev.target && ev.target.closest && ev.target.closest('.settings-backup-restore');
        if (!btn || btn.disabled) return;
        var name = btn.getAttribute('data-backup-name');
        if (!name) return;
        flashRestoreStatus('Reading auto-backup…');
        if (!dataProvider || typeof dataProvider.restoreRelationshipsBackup !== 'function') {
          flashRestoreStatus('Restore not available in this mode.');
          return;
        }
        // For the auto-backup path we read bytes ourselves (so we can
        // run the confirm dialog), then reuse performImport for the
        // shared validation + delta + import flow.
        _opfsReadBinary(name).then(function (bytes) {
          return performImport(bytes, 'auto-backup ' + fmtBackupTimestamp(name));
        }).catch(function (err) {
          flashRestoreStatus('Could not read auto-backup: ' + (err && err.message || String(err)));
        });
      });
    }

    refreshBackupList();

    function showUnsupportedAndDisable() {
      detailEl.innerHTML = renderLocalDataUnavailablePanel('settings');
    }

    // Seed from localStorage immediately for snappy paint, then refresh
    // from relationships.settings (the durable source) when it returns.
    if (input) input.value = getSelfEmail();
    if (dataProvider && typeof dataProvider.getSetting === 'function') {
      dataProvider.getSetting('self_email').then(function (val) {
        if (val && input && document.activeElement !== input) {
          input.value = val;
          setSelfEmailLocal(val);
        }
      }).catch(function (err) {
        if (err && err.localDataUnavailable) showUnsupportedAndDisable();
        // else: ignore — localStorage seed still gives them something useful
      });
    }

    if (form) {
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var next = (input && input.value || '').trim();
        if (status) status.textContent = 'Saving…';
        var write = (dataProvider && typeof dataProvider.setSetting === 'function')
          ? dataProvider.setSetting('self_email', next)
          : Promise.resolve();
        write
          .then(function () {
            setSelfEmailLocal(next);
            if (status) status.textContent = 'Saved.';
          })
          .catch(function (err) {
            if (err && err.localDataUnavailable) {
              showUnsupportedAndDisable();
              return;
            }
            if (status) status.textContent = 'Could not save.';
          });
      });
    }
  }

  /** Boot-time: if relationships.settings is empty for self_email but
   *  localStorage has it (typical after first magic-link submit, or
   *  after a Clear App Cache that wiped settings but preserved
   *  localStorage — actually localStorage gets cleared too, so this
   *  primarily handles "first ever boot with PR 5"), seed the settings
   *  table. Conversely, if settings has a value but localStorage
   *  doesn't (Clear App Cache cleared localStorage, OPFS survived),
   *  rehydrate the localStorage cache. */
  function reconcileSelfEmailOnBoot() {
    if (!dataProvider || typeof dataProvider.getSetting !== 'function') return;
    dataProvider.getSetting('self_email').then(function (settingVal) {
      var localVal = getSelfEmail();
      if (settingVal && !localVal) {
        setSelfEmailLocal(settingVal);
      } else if (localVal && !settingVal && typeof dataProvider.setSetting === 'function') {
        dataProvider.setSetting('self_email', localVal).catch(function () { /* ignore */ });
      }
    }).catch(function () { /* ignore */ });
  }

  function wireGroupDetailPage(group, emailInfo) {
    var contactMode = 'cc';
    var contactBtn = document.getElementById('group-action-contact');
    var modePills = document.querySelectorAll('.group-mode-pill');
    var exportBtn = document.getElementById('group-action-export');
    var editBtn = document.getElementById('group-action-edit');
    var exportPanel = document.getElementById('group-export-panel');
    var exportCancel = document.querySelector('.group-export-cancel');
    var copyEmailsLink = document.getElementById('group-action-copy-emails');
    var noteEditLink = document.getElementById('group-detail-note-edit');
    var titleEditLink = document.getElementById('group-detail-title-edit');

    function setMode(next) {
      contactMode = next;
      for (var i = 0; i < modePills.length; i++) {
        var p = modePills[i];
        var on = p.dataset.mode === next;
        if (on) p.classList.add('group-mode-pill--active');
        else p.classList.remove('group-mode-pill--active');
        p.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      refreshContactHref();
    }

    for (var i = 0; i < modePills.length; i++) {
      modePills[i].addEventListener('click', function () {
        setMode(this.dataset.mode);
      });
    }

    // Mobile-only overflow kebab in the action bar. Opens the
    // #group-actionbar-sheet with the current CC/BCC value pre-selected;
    // the sheet's controls proxy back to the inline buttons + pills via
    // initGroupActionbarSheet().
    var actionbarMoreBtn = document.getElementById('group-action-more');
    if (actionbarMoreBtn) {
      actionbarMoreBtn.addEventListener('click', function () {
        openGroupActionbarSheet(contactMode);
        actionbarMoreBtn.setAttribute('aria-expanded', 'true');
      });
    }

    if (contactBtn) {
      contactBtn.addEventListener('click', function (ev) {
        // Disabled state: no emails. Block click so the empty href doesn't
        // jump to top of page.
        if (!emailInfo.emails.length) {
          ev.preventDefault();
          return;
        }
        // Hard threshold: don't navigate. Copy addresses to clipboard.
        if (emailInfo.emails.length >= GROUPS_CONTACT_HARD_AT) {
          ev.preventDefault();
          copyToClipboard(emailInfo.emails.join(', '))
            .then(function () {
              showToast(emailInfo.emails.length + ' addresses copied. Paste into the ' +
                contactMode.toUpperCase() + ' field of a new message.');
            })
            .catch(function () {
              showToast('Could not copy addresses. Open the page console to grab them manually.');
            });
          return;
        }
        // Normal path: <a href="mailto:..."> handles itself; nothing to do.
      });
    }

    // When CC/BCC mode flips, rebuild the mailto: href so the link reflects
    // the chosen header. Skipped when the button is disabled or in
    // hard-threshold copy-fallback mode.
    function refreshContactHref() {
      if (!contactBtn) return;
      if (!emailInfo.emails.length) return;
      if (emailInfo.emails.length >= GROUPS_CONTACT_HARD_AT) return;
      contactBtn.setAttribute(
        'href',
        buildContactMailto(group, contactMode, emailInfo.emails)
      );
    }

    if (copyEmailsLink) {
      copyEmailsLink.addEventListener('click', function (ev) {
        ev.preventDefault();
        copyToClipboard(emailInfo.emails.join(', '))
          .then(function () {
            showToast(emailInfo.emails.length + ' addresses copied to clipboard.');
          })
          .catch(function () {
            showToast('Could not copy addresses.');
          });
      });
    }

    if (exportBtn && exportPanel) {
      exportBtn.addEventListener('click', function () {
        exportPanel.classList.toggle('hidden');
        // Refresh the email input / cue with the user's current self_email
        // each time the panel opens — Settings may have changed between visits.
        // Don't clobber an in-progress edit: only restore from settings when
        // the input is currently empty (i.e., not user-entered).
        var addrInput = document.getElementById('export-self-email-addr');
        var cue = document.getElementById('export-self-email-cue');
        if (addrInput && cue) {
          var self = getSelfEmail();
          if (!addrInput.value && self) {
            addrInput.value = self;
          }
          var hasValue = !!(addrInput.value || '').trim();
          addrInput.classList.toggle('group-export-email-input--empty', !hasValue);
          cue.textContent = hasValue
            ? 'override here to send to a different address'
            : 'enter your email to send the export to yourself';
        }
        // Reset any prior post-export state when reopening so the panel
        // doesn't confusingly show a stale "View" link.
        var result = document.getElementById('group-export-result');
        var banner = document.getElementById('group-export-banner');
        if (result) result.classList.add('hidden');
        if (banner) {
          banner.classList.add('hidden');
          banner.classList.remove('group-contact-banner--soft', 'group-contact-banner--hard', 'group-contact-banner--info');
          banner.innerHTML = '';
        }
      });
    }
    if (exportCancel && exportPanel) {
      exportCancel.addEventListener('click', function () {
        exportPanel.classList.add('hidden');
      });
    }
    var exportGoBtn = document.getElementById('group-export-go');
    if (exportGoBtn) {
      exportGoBtn.addEventListener('click', function () {
        runGroupExport(group, exportGoBtn);
      });
    }
    var exportAddrInput = document.getElementById('export-self-email-addr');
    var exportAddrCue = document.getElementById('export-self-email-cue');
    if (exportAddrInput && exportAddrCue) {
      exportAddrInput.addEventListener('input', function () {
        var hasValue = !!(exportAddrInput.value || '').trim();
        exportAddrInput.classList.toggle('group-export-email-input--empty', !hasValue);
        exportAddrCue.textContent = hasValue
          ? 'override here to send to a different address'
          : 'enter your email — you can save it in Settings later';
      });
    }
    var exportEmailBtn = document.getElementById('group-export-email-btn');
    if (exportEmailBtn) {
      exportEmailBtn.addEventListener('click', function () {
        runExportEmail();
      });
    }

    if (editBtn) {
      editBtn.addEventListener('click', function () {
        // PR 3 navigates; PR 4 will replace the placeholder route handler
        // with the real "directory in edit mode" entry behavior.
        window.location.hash = '#/edit/' + encodeURIComponent(String(group.id));
      });
    }

    if (noteEditLink) {
      noteEditLink.addEventListener('click', function (ev) {
        ev.preventDefault();
        startInlineNoteEdit(group);
      });
    }

    if (titleEditLink) {
      titleEditLink.addEventListener('click', function (ev) {
        ev.preventDefault();
        startInlineGroupRename(group);
      });
    }
  }

  /** Inline rename for the group name (pencil ✎ next to the title on the
   *  group detail page). Swaps the title h2's text + pencil for an input
   *  + save/cancel pair. On save, PATCHes the group, mirrors the new
   *  name into group.name + the in-memory groups list, and re-renders
   *  the title text and the breadcrumb. The "Edit members" page can
   *  also rename via the rail input; this is just the primary
   *  affordance from the detail page. */
  function startInlineGroupRename(group) {
    var titleH2 = document.querySelector('.group-detail-title');
    var crumbName = document.getElementById('group-detail-breadcrumb-name');
    if (!titleH2) return;
    var current = group.name || '';
    titleH2.innerHTML = '';
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'group-detail-title-input';
    input.value = current;
    input.maxLength = 200;
    input.setAttribute('aria-label', 'Group name');
    var actions = document.createElement('span');
    actions.className = 'group-detail-title-actions';
    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'group-detail-title-save';
    saveBtn.textContent = 'Save';
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'group-detail-title-cancel';
    cancelBtn.textContent = 'Cancel';
    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    titleH2.appendChild(input);
    titleH2.appendChild(actions);
    input.focus();
    input.select();

    function restoreTitle(name) {
      var safe = escapeHtml(name);
      titleH2.innerHTML =
        '<span class="group-detail-title-text" id="group-detail-title-text">' + safe + '</span>' +
        '<a href="#" class="group-detail-title-edit" id="group-detail-title-edit" role="button" ' +
          'aria-label="Rename group" title="Rename group">✎</a>';
      var newLink = document.getElementById('group-detail-title-edit');
      if (newLink) {
        newLink.addEventListener('click', function (ev) {
          ev.preventDefault();
          startInlineGroupRename(group);
        });
      }
      if (crumbName) crumbName.textContent = name;
    }

    function commit() {
      var next = (input.value || '').trim();
      if (!next) {
        showToast('Group name cannot be empty.');
        input.focus();
        return;
      }
      if (next.length > 200) {
        showToast('Group name is too long (max 200 chars).');
        input.focus();
        return;
      }
      if (next === current) {
        restoreTitle(current);
        return;
      }
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      dataProvider.updateGroup(group.id, { name: next })
        .then(function (updated) {
          var saved = (updated && typeof updated.name === 'string') ? updated.name : next;
          group.name = saved;
          restoreTitle(saved);
          showToast('Group renamed.');
        })
        .catch(function () {
          saveBtn.disabled = false;
          cancelBtn.disabled = false;
          showToast('Could not rename group.');
        });
    }

    saveBtn.addEventListener('click', commit);
    cancelBtn.addEventListener('click', function () { restoreTitle(current); });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
      else if (ev.key === 'Escape') { ev.preventDefault(); restoreTitle(current); }
    });
  }

  // Mailto: URL length thresholds for the export "Email it to me" button.
  // Recipient count is always 1 here, so URL length — the underlying
  // constraint behind GROUPS_CONTACT_*_AT — is the right measure directly.
  // Most clients tolerate ~2000 chars; Outlook truncates around 2048.
  var EXPORT_EMAIL_WARN_AT_LEN = 1500;
  var EXPORT_EMAIL_HARD_AT_LEN = 2000;

  // The most-recently-produced export's revocable object URL + filename,
  // kept around so the post-export "View" link and "Email it to me" button
  // work after Export completes. Replaced (and the old URL revoked) on each
  // successful export.
  var lastExportObjectUrl = null;
  var lastExportFilename = null;
  var lastExportGroup = null;

  function buildExportEmailMailto(groupName, addr, filename) {
    var subject = encodeURIComponent(groupName || '');
    var body = encodeURIComponent(
      'Files saved to your Downloads folder:\r\n• ' + filename
    );
    return 'mailto:?to=' + encodeURIComponent(addr) +
      '&subject=' + subject + '&body=' + body;
  }

  function buildExportEmailCopyText(groupName, addr, filename) {
    return 'To: ' + addr + '\nSubject: ' + (groupName || '') +
      '\n\nFiles saved to your Downloads folder:\n• ' + filename + '\n';
  }

  function runExportEmail() {
    var group = lastExportGroup;
    var filename = lastExportFilename;
    if (!group || !filename) return;
    var addrInput = document.getElementById('export-self-email-addr');
    var addr = addrInput ? (addrInput.value || '').trim() : '';
    if (!addr || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) {
      if (addrInput) addrInput.focus();
      showToast('Enter your email above.');
      return;
    }
    // Cache for next time so a fresh panel render prefills it.
    setSelfEmailLocal(addr);
    var groupName = group.name || '';
    var url = buildExportEmailMailto(groupName, addr, filename);
    var copyText = buildExportEmailCopyText(groupName, addr, filename);
    var banner = document.getElementById('group-export-banner');
    if (banner) {
      banner.classList.remove(
        'group-contact-banner--soft',
        'group-contact-banner--hard',
        'group-contact-banner--info'
      );
      banner.classList.add('hidden');
      banner.innerHTML = '';
    }
    function showBanner(modifier, html) {
      if (!banner) return;
      banner.classList.remove('hidden');
      banner.classList.add(modifier);
      banner.innerHTML = html;
      var copyLink = banner.querySelector('.group-export-banner-copy');
      if (copyLink) {
        copyLink.addEventListener('click', function (e) {
          e.preventDefault();
          copyToClipboard(copyText).then(
            function () { showToast('Email contents copied — paste into a new message.'); },
            function () { showToast('Copy failed; select and copy manually.'); }
          );
        });
      }
    }
    if (url.length >= EXPORT_EMAIL_HARD_AT_LEN) {
      showBanner(
        'group-contact-banner--hard',
        'Email URL too long for most mail clients. ' +
          '<a href="#" class="group-export-banner-copy">Copy email contents</a> and paste into a new message.'
      );
      return;
    }
    if (url.length >= EXPORT_EMAIL_WARN_AT_LEN) {
      showBanner(
        'group-contact-banner--soft',
        'Email URL is long — some mail clients may truncate. ' +
          '<a href="#" class="group-export-banner-copy">Copy email contents</a> if your client misbehaves.'
      );
    }
    window.location.href = url;
  }

  function runGroupExport(group, button) {
    var name = group.name || 'group';
    var slug = slugifyForFilename(name);
    var formatPdf = !!document.getElementById('export-format-pdf') &&
      document.getElementById('export-format-pdf').checked;
    var formatHtml = !!document.getElementById('export-format-html') &&
      document.getElementById('export-format-html').checked;
    if (!formatPdf && !formatHtml) {
      showToast('Pick PDF or HTML.');
      return;
    }
    var ext = formatPdf ? 'pdf' : 'html';
    var filename = slug + '.' + ext;
    if (button) {
      button.disabled = true;
      button.textContent = 'Exporting…';
    }
    var resultEl = document.getElementById('group-export-result');
    var resultText = document.getElementById('group-export-result-text');
    var viewLink = document.getElementById('group-export-view');
    var banner = document.getElementById('group-export-banner');
    if (resultEl) resultEl.classList.add('hidden');
    if (banner) {
      banner.classList.add('hidden');
      banner.classList.remove('group-contact-banner--soft', 'group-contact-banner--hard', 'group-contact-banner--info');
      banner.innerHTML = '';
    }
    var producer = formatPdf ? exportGroupAsPdf(group) : exportGroupAsHtml(group);
    producer
      .then(function (blob) {
        return downloadBlob(blob, filename).then(function () { return blob; });
      })
      .then(function (blob) {
        if (lastExportObjectUrl) {
          try { URL.revokeObjectURL(lastExportObjectUrl); } catch (e) {}
        }
        lastExportObjectUrl = URL.createObjectURL(blob);
        lastExportFilename = filename;
        lastExportGroup = group;
        if (viewLink) viewLink.setAttribute('href', lastExportObjectUrl);
        if (resultText) {
          resultText.textContent = 'Created ' + filename + '.';
        }
        if (resultEl) resultEl.classList.remove('hidden');
        showToast('Exported: ' + filename);
      })
      .catch(function (err) {
        showToast(
          (formatPdf ? 'PDF' : 'HTML') + ' export failed: ' + (err && err.message || err)
        );
      })
      .then(function () {
        if (button) {
          button.disabled = false;
          button.textContent = 'Export';
        }
      });
  }

  function startInlineNoteEdit(group) {
    var wrap = document.getElementById('group-detail-note-wrap');
    if (!wrap) return;
    var current = group.note || '';
    wrap.innerHTML = '';
    wrap.classList.add('group-detail-note-wrap--editing');
    var textarea = document.createElement('textarea');
    textarea.className = 'group-detail-note-input';
    textarea.value = current;
    textarea.maxLength = 4000;
    textarea.rows = 3;
    var actions = document.createElement('div');
    actions.className = 'group-detail-note-actions';
    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'group-detail-note-save';
    saveBtn.textContent = 'Save';
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'group-detail-note-cancel';
    cancelBtn.textContent = 'Cancel';
    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    wrap.appendChild(textarea);
    wrap.appendChild(actions);
    textarea.focus();
    textarea.select();

    function restore(noteText) {
      wrap.classList.remove('group-detail-note-wrap--editing');
      var hasNote = !!(noteText && String(noteText).trim());
      wrap.innerHTML =
        (hasNote
          ? '<span class="group-detail-note-text" id="group-detail-note-text">' + escapeHtml(noteText) + '</span>'
          : '<span class="group-detail-note-empty" id="group-detail-note-text">No note yet.</span>') +
        ' <a href="#" class="group-detail-note-edit" id="group-detail-note-edit">' +
          (hasNote ? 'edit' : 'add a note') +
        '</a>';
      // Re-bind the new edit link.
      var newLink = document.getElementById('group-detail-note-edit');
      if (newLink) {
        newLink.addEventListener('click', function (ev) {
          ev.preventDefault();
          startInlineNoteEdit(group);
        });
      }
    }

    cancelBtn.addEventListener('click', function () { restore(current); });
    saveBtn.addEventListener('click', function () {
      var next = textarea.value;
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      dataProvider.updateGroup(group.id, { note: next })
        .then(function (updated) {
          var savedNote = (updated && typeof updated.note === 'string') ? updated.note : next;
          group.note = savedNote;
          restore(savedNote);
          showToast('Note saved.');
        })
        .catch(function () {
          saveBtn.disabled = false;
          cancelBtn.disabled = false;
          showToast('Could not save note.');
        });
    });
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
    // #tag prefix → scope FTS5 to the search_tags column. The tokens are
    // stored in fellows.search_tags as plain CSV-ish text and the FTS5
    // virtual table indexes that column, so column-scoped MATCH works.
    // Local-fallback search keeps the leading '#' and decodes it inside
    // filterFellowsLocally.
    var ftsQ = q;
    if (q.charAt(0) === '#' && q.length > 1) {
      ftsQ = 'search_tags:' + q.slice(1);
    }
    if (directoryDataSource === 'sqlite' && dataProvider) {
      setSearchStatus('Searching…');
      dataProvider
        .search(ftsQ)
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
          renderSearchResults(results, 'result');
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
    var url = '/api/search?q=' + encodeURIComponent(ftsQ);
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
        renderSearchResults(results, 'result');
      })
      .catch(function () {
        setSearchStatus('Network search failed. Trying cached data…');
        runLocalSearch(q);
      });
  }

  function renderSearchResults(results, label) {
    var total = results.length;
    var filtered = applyHasEmailFilter(results);
    displayedList = filtered;
    // Keep the visible-count indicator in sync with what's actually shown,
    // including during search. The denominator stays at list.length (total
    // fellows in the current data set) so "5 of 515 fellows visible" is
    // unambiguous even when both a search AND the has-email filter apply.
    var total_in_data = (list && list.length) || total;
    setFilterCount(filtered.length + ' of ' + total_in_data + ' fellows visible');
    if (!filtered.length) {
      if (!total) {
        directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search.</p>';
      } else {
        directoryListEl.innerHTML =
          '<p class="placeholder">No fellows match that search with the current filter.</p>';
      }
      setSearchStatus('');
      return;
    }
    renderDirectoryList(filtered);
    var suffix = filtered.length === 1 ? '' : 's';
    var msg = filtered.length + ' ' + label + suffix + ' found';
    if (filtered.length !== total) {
      msg += ' (' + total + ' before filter)';
    }
    setSearchStatus(msg);
    updateBulkBar();
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
      renderSearchResults(results, 'offline result');
    }).catch(function () {
      directoryListEl.innerHTML = '<p class="placeholder">Offline search failed.</p>';
      setSearchStatus('');
    });
  }

  function filterFellowsLocally(fellows, q) {
    var query = (q || '').toLowerCase();
    if (!query) return fellows.slice();
    // #tag prefix → match against the search_tags column only. Mirrors
    // the FTS5 column-scoped path in runSearch so on/offline behaviour
    // stays consistent.
    if (query.charAt(0) === '#' && query.length > 1) {
      var tag = query.slice(1);
      return fellows.filter(function (f) {
        var st = (f.search_tags == null ? '' : String(f.search_tags)).toLowerCase();
        return st.indexOf(tag) !== -1;
      });
    }
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
  initResetEverythingButton();
  initDiagnosticsPanel();
  initBugReportButtons();
  initKebabSheet();
  initComposerFab();
  initGroupCardSheet();
  initGroupActionbarSheet();
  wireCopyButtons();

  function bootDirectoryAsApp() {
    bootDebugLines.length = 0;
    setShellVisible(true);
    if (loadingPanelEl) {
      loadingPanelEl.classList.remove('hidden');
    }
    if (loadingEl) {
      loadingEl.classList.remove('hidden');
    }
    // Restore the in-progress group draft (members + auto-title state)
    // before any rendering so the rail and markers come up consistent.
    loadGroupDraft();
    renderRail();

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

    // If the API refuses us (expired session = 401, rare 403), try the
    // IndexedDB cache populated by a prior successful boot. Rationale:
    // "install once, works forever." A stale session must not lock users
    // out of data they already downloaded.
    function isAuthFailure(err) {
      return !!(err && (err.status === 401 || err.status === 403));
    }
    function tryListFromCache(originalErr) {
      return loadFullFellows().then(function (cached) {
        if (cached && cached.length) {
          setBuildBadgeOfflineOnly('getList ' + (originalErr && originalErr.status));
          return cached;
        }
        throw originalErr;
      });
    }
    function tryFullFromCache(originalErr) {
      return loadFullFellows().then(function (cached) {
        if (cached && cached.length) {
          setBuildBadgeOfflineOnly('getFull ' + (originalErr && originalErr.status));
          return cached;
        }
        throw originalErr;
      });
    }

    pickDataProvider()
      .then(function (provider) {
        dataProvider = provider;
        bootDebugPush('provider ready kind=' + provider.kind);
        if (provider.kind === 'sqlite') {
          directoryDataSource = 'sqlite';
        }
        // Reconcile self_email between localStorage (fast cache) and
        // relationships.settings (durable). PR 5: needed by the export
        // "email it to me" feature; safe to fire-and-forget.
        reconcileSelfEmailOnBoot();
        // Same pattern for the has-email filter pref. Migrates
        // ehf_has_email_only from localStorage-only into the durable
        // relationships.settings store on first post-PR-D boot.
        reconcileHasEmailFilterOnBoot();
        setSetupStatus('Loading…');
        return provider.getList().catch(function (err) {
          if (isAuthFailure(err)) return tryListFromCache(err);
          throw err;
        });
      })
      .then(function (data) {
        bootDebugPush(
          'getList: OK count=' + (Array.isArray(data) ? data.length : typeof data) +
          (offlineOnlyMode ? ' (from cache)' : '')
        );
        // Reaching getList success (fresh API or cached) means this
        // browser has been authenticated here at least once. Record the
        // marker so the URL-just-works path works on next visit.
        markAuthenticatedOnce();
        list = Array.isArray(data) ? data : [];
        // Backfill display names for any draft members loaded before
        // we had data (record_id was saved, name wasn't, or the saved
        // name has since changed in fellows.db). Saves the rail from
        // showing raw record_ids in chips.
        var draftDirty = false;
        list.forEach(function (f) {
          if (
            f.record_id &&
            groupDraft.members.has(f.record_id) &&
            groupDraft.memberNames[f.record_id] !== f.name
          ) {
            groupDraft.memberNames[f.record_id] = f.name || f.record_id;
            draftDirty = true;
          }
        });
        if (draftDirty) {
          saveGroupDraft();
          renderRail();
        }
        renderDirectory();
        route();
        return dataProvider.getFull().catch(function (err) {
          if (isAuthFailure(err)) return tryFullFromCache(err);
          throw err;
        });
      })
      .then(function (full) {
        bootDebugPush('getFull: OK rows=' + (Array.isArray(full) ? full.length : typeof full) +
          (offlineOnlyMode ? ' (from cache)' : ''));
        if (Array.isArray(full)) {
          fullFellowsCache = full;
          // Only persist a fresh API payload. A cache-served full is
          // already in IndexedDB; re-saving the same blob is wasted IO.
          if (directoryDataSource === 'api' && !offlineOnlyMode) {
            saveFullFellowsToIndexedDB(full);
          }
          full.forEach(function (f) {
            if (f.slug) fellowsBySlug.set(f.slug, f);
            if (f.record_id) fellowsBySlug.set(f.record_id, f);
          });
        }
        route();
        // Kick off image prewarm in the background — does not block UI.
        // Images are served out of the SW cache once prewarmed, so this
        // stays useful even in offline-only mode.
        if (Array.isArray(full)) {
          setTimeout(function () {
            prewarmProfileImages(full).catch(function () {});
          }, 0);
        }
        // Start the hourly server-build-drift check. Idempotent; only
        // arms the interval when running as an installed PWA.
        startUpdateCheckPoll();
      })
      .catch(function (err) {
        // Only reached when the API refused us AND no local cache could
        // answer. In browser-tab-acting-as-app mode, hand off to the
        // email gate quietly. Otherwise show the boot-failure panel.
        if (!isStandaloneDisplayMode() && hasAuthenticatedOnce()) {
          bootDebugPush('as-app boot failed; handing off to startBrowserUx: ' +
            (err && err.message ? err.message : String(err)));
          setShellVisible(false);
          if (loadingPanelEl) loadingPanelEl.classList.add('hidden');
          if (loadingEl) loadingEl.classList.add('hidden');
          startBrowserUx();
          return;
        }
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
        // Auto-following rail title is meant to feel instant; update it
        // before the debounced search fires.
        renderRailHeader();
        if (searchDebounceId) {
          clearTimeout(searchDebounceId);
        }
        searchDebounceId = setTimeout(function () {
          handleSearchInput();
        }, 250);
      });
    }

    if (hasEmailFilterEl) {
      hasEmailFilterEl.checked = hasEmailOnly;
      hasEmailFilterEl.addEventListener('change', function () {
        hasEmailOnly = !!hasEmailFilterEl.checked;
        saveHasEmailFilter(hasEmailOnly);
        var q = (searchInputEl && searchInputEl.value || '').trim();
        if (q) {
          runSearch(q);
        } else {
          renderDirectory();
        }
      });
    }

    if (groupRailTitleEl) {
      groupRailTitleEl.addEventListener('input', function () {
        // Once the user types in the title field, the auto-follow flip is
        // permanent for this draft (even if they clear it back to empty).
        groupDraft.title = groupRailTitleEl.value;
        groupDraft.titleEdited = true;
        groupRailTitleEl.classList.remove('group-rail-title--auto');
        if (isEditing()) {
          // Edit mode: debounce a PATCH so we don't spam the server on
          // every keystroke. Banner reflects the saved name on success.
          if (editTitlePatchTimer) clearTimeout(editTitlePatchTimer);
          editTitlePatchTimer = setTimeout(function () {
            patchEditedGroupName(groupRailTitleEl.value);
          }, 600);
        } else {
          saveGroupDraft();
        }
        renderRailHeader();
      });
    }
    if (groupRailCreateEl) {
      groupRailCreateEl.addEventListener('click', function () {
        if (isEditing()) {
          // Done editing: bounce back to the detail page. The hashchange
          // triggers exitEditMode in route().
          window.location.hash =
            '#/groups/' + encodeURIComponent(String(groupDraft.editingGroupId));
        } else {
          handleCreateGroupClick();
        }
      });
    }
    if (editModeBannerCancelEl) {
      editModeBannerCancelEl.addEventListener('click', function (ev) {
        ev.preventDefault();
        handleCancelEdits();
      });
    }
    if (bulkSelectInputEl) {
      bulkSelectInputEl.addEventListener('change', bulkToggleVisible);
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initWindowAISearch);
    } else {
      initWindowAISearch();
    }

    window.addEventListener('online', updateConnectionBanner);
    window.addEventListener('offline', updateConnectionBanner);
    updateConnectionBanner();
  }

  tryUnlockFromHash().then(function () {
    if (shouldActAsApp()) {
      bootDirectoryAsApp();
    } else {
      startBrowserUx();
    }
  });

  registerServiceWorker();
})();
