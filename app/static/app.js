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
  var authDebugInstallEl = document.getElementById('auth-debug-install');
  var gateReasonBannerEl = document.getElementById('gate-reason-banner');
  var installUnsupportedHintEl = document.getElementById('install-unsupported-hint');
  var backToGateLinkEl = document.getElementById('back-to-gate-link');
  var swUpdateBannerEl = document.getElementById('sw-update-banner');
  var swUpdateReloadEl = document.getElementById('sw-update-reload');
  var siteHeaderEl = document.getElementById('site-header');
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
  var FELLOWS_UI_DIAG = 'diag-2026-04s-groups-pr5';

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

  function createSqliteDataProvider(db, relDb) {
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

  function createApiDataProvider() {
    function jsonOr(url, opts, expectedShapeOnEmpty) {
      return fetch(url, opts || {}).then(function (r) {
        if (r.status === 204) return expectedShapeOnEmpty;
        if (!r.ok) throw apiError(url, r.status);
        return r.json();
      });
    }
    return {
      kind: 'api',
      getList: function () {
        return fetch('/api/fellows').then(function (r) {
          if (!r.ok) throw apiError('/api/fellows', r.status);
          return r.json();
        });
      },
      getFull: function () {
        return fetch('/api/fellows?full=1').then(function (r) {
          if (!r.ok) throw apiError('/api/fellows?full=1', r.status);
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
      // ATTACHed f.fellows on the dev server. In production (deploy/
      // server.py), these endpoints don't exist yet — the SQLite path
      // is the canonical production implementation.
      listGroups: function () {
        return jsonOr('/api/groups', null, []);
      },
      getGroup: function (id) {
        return fetch('/api/groups/' + encodeURIComponent(id)).then(function (r) {
          if (r.status === 404) return null;
          if (!r.ok) throw apiError('/api/groups/' + id, r.status);
          return r.json();
        });
      },
      createGroup: function (data) {
        return fetch('/api/groups', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(data || {})
        }).then(function (r) {
          if (!r.ok) throw apiError('/api/groups', r.status);
          return r.json();
        });
      },
      updateGroup: function (id, patch) {
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
      },
      deleteGroup: function (id) {
        return fetch('/api/groups/' + encodeURIComponent(id), {
          method: 'DELETE',
          credentials: 'same-origin'
        }).then(function (r) {
          if (r.status === 204) return true;
          if (r.status === 404) return false;
          throw apiError('/api/groups/' + id, r.status);
        });
      },
      getSetting: function (key) {
        return fetch('/api/settings/' + encodeURIComponent(key)).then(function (r) {
          if (r.status === 404) return null;
          if (!r.ok) throw apiError('/api/settings/' + key, r.status);
          return r.json().then(function (d) { return d && d.value; });
        });
      },
      getSettings: function () {
        return fetch('/api/settings').then(function (r) {
          if (!r.ok) return {};
          return r.json();
        });
      },
      setSetting: function (key, value) {
        return fetch('/api/settings/' + encodeURIComponent(key), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ value: value })
        }).then(function (r) {
          if (!r.ok) throw apiError('/api/settings/' + key, r.status);
          return r.json();
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
          return createSqliteDataProvider(db, relDb);
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
      if (installUnsupportedHintEl) installUnsupportedHintEl.classList.add('hidden');
      if (installButtonEl) installButtonEl.classList.remove('hidden');
    });

    window.addEventListener('appinstalled', function () {
      deferredInstallPrompt = null;
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
        } else if (isIosSafari()) {
          setInstallStatus('Use Share → Add to Home Screen.');
        } else {
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
    if (siteHeaderEl) siteHeaderEl.classList.add('hidden');
    showLoading(false);
    showApp(false);
    if (connectionBannerEl) connectionBannerEl.classList.add('hidden');

    setGateReasonBanner(reason);

    if (authPayload) {
      showAuthDebugPrivate(authPayload, httpStatus != null ? httpStatus : 200);
    }

    if (unlockEmailFormEl && !unlockEmailFormEl._wired) {
      unlockEmailFormEl._wired = true;
      unlockEmailFormEl.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (unlockEmailInputEl && unlockEmailInputEl.value) || '';
        // Capture the user's own email for the export "email it to me"
        // feature (PR 5). Mirrors to relationships.settings on next boot.
        setSelfEmailLocal(email);
        if (unlockStatusEl) unlockStatusEl.textContent = 'Sending…';
        setGateReasonBanner('');
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
  }

  function tryUnlockFromHash() {
    var hash = window.location.hash || '';
    var m = hash.match(/^#\/unlock\/(.+)$/);
    if (!m) {
      return Promise.resolve();
    }
    var token = m[1];
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
          var reason = (j && j.error) === 'expired' ? 'expired' : 'invalid';
          window.location.replace('/?gate=1&reason=' + reason);
          // stall remaining chain — the replace will reload us
          return new Promise(function () {});
        });
      })
      .catch(function () {
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
      .catch(function () {
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
    aboutHtml += '<p class="about-users-manual"><a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md" target="_blank" rel="noopener">User Guide</a> \u2014 how to install, update, and clear app data.</p>';
    aboutHtml += '<p class="about-update-check">';
    aboutHtml += '<button type="button" id="about-check-updates" class="about-check-updates-btn">Check for updates</button>';
    aboutHtml += '<span id="about-update-status" class="about-update-status" role="status" aria-live="polite"></span>';
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
    var editMatch = hash.match(/^#\/edit\/(\d+)$/);
    var nextEditId = editMatch ? parseInt(editMatch[1], 10) : null;
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
    var directoryMatch = hash.match(/^#\/groups\/(\d+)\/directory$/);
    if (directoryMatch) {
      renderGroupDirectoryPage(parseInt(directoryMatch[1], 10));
      return;
    }
    var groupMatch = hash.match(/^#\/groups\/(\d+)$/);
    if (groupMatch) {
      renderGroupDetailPage(parseInt(groupMatch[1], 10));
      return;
    }
    if (editMatch) {
      // Edit mode is rail-driven, not detail-pane-driven. The directory
      // and rail flip into edit mode; the detail pane shows whatever was
      // there (or a placeholder via updateDetailFromHash). Enter once per
      // hash visit; re-entering for the same id is a no-op.
      if (groupDraft.editingGroupId !== nextEditId) {
        enterEditMode(nextEditId);
      }
      updateDetailFromHash();
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
      .catch(function () {
        var wrap = document.getElementById('groups-list-wrap');
        if (wrap) wrap.innerHTML = '<p class="placeholder">Could not load groups.</p>';
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
      '</table>';
    wireGroupsTableActions(wrap);
  }

  function wireGroupsTableActions(wrap) {
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
  }

  function startInlineRename(wrap, gidStr) {
    var row = wrap.querySelector('tr[data-group-id="' + gidStr + '"]');
    if (!row) return;
    var nameCell = row.querySelector('.groups-cell-name');
    var nameLink = nameCell.querySelector('.groups-name-link');
    if (!nameCell || !nameLink) return;
    var current = nameLink.textContent;
    var input = document.createElement('input');
    input.type = 'text';
    input.value = current;
    input.className = 'groups-rename-input';
    input.maxLength = 200;
    nameCell.innerHTML = '';
    nameCell.appendChild(input);
    input.focus();
    input.select();
    var done = false;
    function commit(save) {
      if (done) return;
      done = true;
      var next = (input.value || '').replace(/^\s+|\s+$/g, '');
      if (!save || !next || next === current) {
        restoreNameLink(nameCell, gidStr, current);
        return;
      }
      nameCell.innerHTML = '<span class="groups-saving">saving…</span>';
      dataProvider.updateGroup(parseInt(gidStr, 10), { name: next })
        .then(function (updated) {
          restoreNameLink(nameCell, gidStr, (updated && updated.name) || next);
        })
        .catch(function () {
          restoreNameLink(nameCell, gidStr, current);
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
      var members = group.members || [];
      var memberCount = members.length;
      var memberWord = memberCount === 1 ? ' fellow' : ' fellows';
      var emailInfo = collectGroupEmails(group);
      var totalEmails = emailInfo.emails.length;
      var hasNote = !!(group.note && String(group.note).trim());
      var noteEditLabel = hasNote ? 'edit' : 'add a note';
      var html = '<div class="group-detail-page" data-group-id="' + escapeHtml(String(group.id)) + '">' +
        '<p class="group-detail-breadcrumb">' +
          '<a href="#/groups">groups</a> › ' + escapeHtml(name) +
        '</p>' +
        '<h2 class="group-detail-title">' + escapeHtml(name) + '</h2>' +
        '<p class="group-detail-meta">' +
          escapeHtml(String(memberCount)) + memberWord +
          ' · created ' + escapeHtml((group.created_at || '').slice(0, 10)) +
        '</p>';

      // Action bar: ✉ Contact (primary, real <a href="mailto:…">) + CC/BCC
      // pill toggle + ⬇ Export + ✎ Edit. Native <a> means the browser
      // handles handing the mailto URL off to the user's mail client.
      // The hard-threshold path intercepts the click and copies addresses
      // to the clipboard instead.
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
      html +=
        '<div class="group-action-bar">' +
          '<a class="' + contactClasses + '" id="group-action-contact" role="button"' + contactAttrs + '>' +
            '✉ Contact the whole group' +
          '</a>' +
          '<div class="group-contact-mode" role="group" aria-label="Recipient header">' +
            '<button type="button" class="group-mode-pill group-mode-pill--active" data-mode="cc" aria-pressed="true">CC</button>' +
            '<button type="button" class="group-mode-pill" data-mode="bcc" aria-pressed="false">BCC</button>' +
          '</div>' +
          '<button type="button" class="group-action-btn" id="group-action-export">⬇ Export a directory</button>' +
          '<button type="button" class="group-action-btn" id="group-action-edit">✎ Edit group</button>' +
          '<span class="group-action-helper">opens your mail client with everyone in <span id="group-action-helper-mode">CC</span></span>' +
        '</div>';

      // Threshold banner. Soft warning between WARN and HARD, hard warning ≥ HARD.
      if (totalEmails >= GROUPS_CONTACT_HARD_AT) {
        html +=
          '<div class="group-contact-banner group-contact-banner--hard" role="status">' +
            escapeHtml(String(totalEmails)) + ' recipients — too many for one mailto: URL on most clients. ' +
            '<a href="#" id="group-action-copy-emails">Copy ' + escapeHtml(String(totalEmails)) + ' addresses</a>' +
            ' and paste them into your mail client manually.' +
          '</div>';
      } else if (totalEmails >= GROUPS_CONTACT_WARN_AT) {
        html +=
          '<div class="group-contact-banner group-contact-banner--soft" role="status">' +
            escapeHtml(String(totalEmails)) + ' recipients — long mailto: URLs may be truncated by some clients. ' +
            '<a href="#" id="group-action-copy-emails">Copy addresses</a> if your client misbehaves.' +
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

      // Inline export panel — checkboxes drive what the Export button emits.
      var slugFn = slugifyForFilename(name);
      html +=
        '<div class="group-export-panel hidden" id="group-export-panel" aria-label="Export options">' +
          '<div class="group-export-head">Export a directory</div>' +
          '<div class="group-export-options">' +
            '<label><input type="checkbox" id="export-pdf" checked> <span><b>PDF directory</b><br><code>' +
              escapeHtml(slugFn) + '.pdf</code></span></label>' +
            '<label><input type="checkbox" id="export-html"> <span><b>HTML directory</b><br><code>' +
              escapeHtml(slugFn) + '.zip</code> · view offline, all relative paths</span></label>' +
            '<label><input type="checkbox" id="export-self-email" checked> <span><b>email it to me</b><br><span id="export-self-email-hint">opens your mail client</span></span></label>' +
          '</div>' +
          '<div class="group-export-actions">' +
            '<button type="button" class="group-export-cancel">cancel</button>' +
            '<button type="button" class="group-export-go" id="group-export-go">Export</button>' +
          '</div>' +
          '<p class="group-export-note" id="group-export-note">' +
            'Files land in your <b>Downloads</b> folder (or via the system share sheet on iOS). ' +
            'The PDF includes clickable mailto: links; the HTML zip is a self-contained portable directory.' +
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
    }).catch(function () {
      detailEl.innerHTML = '<p class="placeholder">Could not load group.</p>';
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
    }).catch(function () {
      detailEl.innerHTML = '<p class="placeholder">Could not load group directory.</p>';
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
          '<a class="fellow-modal-value" href="mailto:' + escapeHtml(email) + '">' +
            escapeHtml(email) +
          '</a>' +
        '</li>';
    }
    if (m.mobile_number) {
      var phoneText = String(m.mobile_number).trim();
      var phoneTel = phoneText.replace(/[^+\d]/g, '');
      rowsHtml +=
        '<li class="fellow-modal-row">' +
          '<span class="fellow-modal-label">phone</span>' +
          '<a class="fellow-modal-value" href="tel:' + escapeHtml(phoneTel) + '">' +
            escapeHtml(phoneText) +
          '</a>' +
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

  /** Minimal CSS shipped inside the exported ZIP. Inlined into one
   *  file so each HTML page in the bundle is human-readable on its own. */
  var EXPORT_CSS =
    'body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;' +
    'background:#fafafa;color:#222;margin:0;padding:1.4rem 1.6rem;}' +
    'h1{margin:0 0 0.2rem;font-size:1.4rem;}' +
    '.meta{font-size:0.85rem;color:#666;margin-bottom:0.6rem;}' +
    '.contact-bar{display:flex;align-items:center;gap:0.75rem;padding:0.5rem 0.7rem;' +
    'margin-bottom:1rem;background:#f0ecf5;border:1px solid #dcd6e8;border-radius:3px;' +
    'font-size:0.85rem;}' +
    '.contact-bar a{color:#0066cc;text-decoration:underline;font-weight:500;}' +
    '.helper{color:#7a6f91;font-size:0.78rem;}' +
    '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:0.9rem;}' +
    '.cell{display:block;text-decoration:none;color:inherit;text-align:center;}' +
    '.portrait{width:100%;aspect-ratio:1/1;border-radius:50%;border:1px solid #ccc;' +
    'overflow:hidden;background:#eee;}' +
    '.portrait img{width:100%;height:100%;object-fit:cover;display:block;}' +
    '.cell-name{font-size:0.78rem;margin-top:4px;line-height:1.2;}' +
    '.back-link{display:inline-block;margin-bottom:1rem;color:#0066cc;font-size:0.85rem;}' +
    '.fellow-card{max-width:420px;margin:0 auto;background:#fff;border:1px solid #ccc;' +
    'border-radius:4px;padding:1.2rem 1.4rem;}' +
    '.fellow-card h2{margin:0 0 0.4rem;}' +
    '.fellow-portrait{width:120px;height:120px;border-radius:50%;border:1px solid #ccc;' +
    'overflow:hidden;margin:0 auto 0.8rem;background:#eee;}' +
    '.fellow-portrait img{width:100%;height:100%;object-fit:cover;}' +
    '.field-table{width:100%;border-collapse:separate;border-spacing:0 0.3em;font-size:0.9rem;}' +
    '.field-table td{padding:0.3em 0.5em;}' +
    '.field-table td.label{background:#f0f0f0;font-weight:600;width:32%;}' +
    '.field-table a{color:#0066cc;}';

  function buildExportIndexHtml(group, members) {
    var contact = buildContactBarMailto(group, members);
    var html =
      '<!doctype html>\n' +
      '<html lang="en"><head><meta charset="utf-8">' +
      '<title>' + escapeHtml(group.name || 'Group directory') + '</title>' +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<link rel="stylesheet" href="styles.css">' +
      '</head><body>' +
      '<h1>' + escapeHtml(group.name || '(untitled)') + '</h1>' +
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
    html += '<div class="grid">';
    members.forEach(function (m) {
      var slug = m.slug || slugifyForFilename(m.name);
      var imgRel = m.has_image && m.slug ? 'images/' + m.slug + '.jpg' : '';
      var imgSrc = imgRel || PORTRAIT_SVG_PLACEHOLDER;
      html += '<a class="cell" href="fellow-' + escapeHtml(slug) + '.html">' +
        '<div class="portrait"><img src="' + escapeHtml(imgSrc) +
        '" alt="' + escapeHtml(m.name) + '" loading="lazy"></div>' +
        '<div class="cell-name">' + escapeHtml(m.name) + '</div>' +
      '</a>';
    });
    html += '</div></body></html>\n';
    return html;
  }

  function buildExportFellowHtml(group, m) {
    var slug = m.slug || slugifyForFilename(m.name);
    var imgRel = m.has_image && m.slug ? 'images/' + m.slug + '.jpg' : '';
    var imgSrc = imgRel || PORTRAIT_SVG_PLACEHOLDER;
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
    return '<!doctype html>\n' +
      '<html lang="en"><head><meta charset="utf-8">' +
      '<title>' + escapeHtml(m.name) + ' — ' + escapeHtml(group.name || '') + '</title>' +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<link rel="stylesheet" href="styles.css">' +
      '</head><body>' +
      '<a class="back-link" href="index.html">‹ back to ' + escapeHtml(group.name || 'directory') + '</a>' +
      '<div class="fellow-card">' +
        '<div class="fellow-portrait"><img src="' + escapeHtml(imgSrc) +
          '" alt="' + escapeHtml(m.name) + '"></div>' +
        '<h2>' + escapeHtml(m.name) + '</h2>' +
        (rows.length
          ? '<table class="field-table"><tbody>' + rows.join('') + '</tbody></table>'
          : '<p>(No public contact info on file.)</p>') +
      '</div></body></html>\n';
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

  /** Build a Blob containing the exported ZIP for a group:
   *    <slug>/index.html, styles.css, fellow-<slug>.html *, images/*
   *  using fflate's zipSync (synchronous, well-suited for small bundles). */
  function exportGroupAsHtmlZip(group) {
    if (typeof fflate === 'undefined') {
      return Promise.reject(new Error('fflate not loaded'));
    }
    var members = resolveMembersForView(group);
    var encoder = new TextEncoder();
    var files = {};
    files['index.html'] = encoder.encode(buildExportIndexHtml(group, members));
    files['styles.css'] = encoder.encode(EXPORT_CSS);
    members.forEach(function (m) {
      var slug = m.slug || slugifyForFilename(m.name);
      files['fellow-' + slug + '.html'] = encoder.encode(buildExportFellowHtml(group, m));
    });
    // Fetch portraits in parallel. Members without an image get nothing in
    // images/; the standalone HTML falls back to the inline SVG placeholder.
    var imageJobs = members
      .filter(function (m) { return m.has_image && m.slug; })
      .map(function (m) {
        return fetchMemberPortrait(m.slug).then(function (res) {
          if (res) {
            files['images/' + m.slug + '.' + res.ext] = res.bytes;
          }
        });
      });
    return Promise.all(imageJobs).then(function () {
      var zipped = fflate.zipSync(files, { level: 6 });
      // ArrayBuffer view → Blob; explicit MIME so Save dialogs and iOS
      // Web Share both recognise it as a zip.
      return new Blob([zipped], { type: 'application/zip' });
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
      '</div>';
    detailEl.innerHTML = html;
    var input = document.getElementById('settings-self-email');
    var status = document.getElementById('settings-status');
    var form = document.getElementById('settings-form');

    // Seed from localStorage immediately for snappy paint, then refresh
    // from relationships.settings (the durable source) when it returns.
    if (input) input.value = getSelfEmail();
    if (dataProvider && typeof dataProvider.getSetting === 'function') {
      dataProvider.getSetting('self_email').then(function (val) {
        if (val && input && document.activeElement !== input) {
          input.value = val;
          setSelfEmailLocal(val);
        }
      }).catch(function () { /* ignore */ });
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
          .catch(function () {
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
    var helperModeEl = document.getElementById('group-action-helper-mode');
    var exportBtn = document.getElementById('group-action-export');
    var editBtn = document.getElementById('group-action-edit');
    var exportPanel = document.getElementById('group-export-panel');
    var exportCancel = document.querySelector('.group-export-cancel');
    var copyEmailsLink = document.getElementById('group-action-copy-emails');
    var noteEditLink = document.getElementById('group-detail-note-edit');

    function setMode(next) {
      contactMode = next;
      for (var i = 0; i < modePills.length; i++) {
        var p = modePills[i];
        var on = p.dataset.mode === next;
        if (on) p.classList.add('group-mode-pill--active');
        else p.classList.remove('group-mode-pill--active');
        p.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      if (helperModeEl) helperModeEl.textContent = next.toUpperCase();
      refreshContactHref();
    }

    for (var i = 0; i < modePills.length; i++) {
      modePills[i].addEventListener('click', function () {
        setMode(this.dataset.mode);
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
        // Refresh the "email it to me" hint with the user's current self_email
        // each time the panel opens — it can change via Settings between visits.
        var hint = document.getElementById('export-self-email-hint');
        if (hint) {
          var self = getSelfEmail();
          hint.textContent = self
            ? ('opens your mail client to send to ' + self)
            : 'set your email in Settings first';
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
  }

  function runGroupExport(group, button) {
    var name = group.name || 'group';
    var slug = slugifyForFilename(name);
    var wantPdf = !!document.getElementById('export-pdf') &&
      document.getElementById('export-pdf').checked;
    var wantHtml = !!document.getElementById('export-html') &&
      document.getElementById('export-html').checked;
    var wantSelf = !!document.getElementById('export-self-email') &&
      document.getElementById('export-self-email').checked;
    if (!wantPdf && !wantHtml && !wantSelf) {
      showToast('Pick at least one export option.');
      return;
    }
    if (button) {
      button.disabled = true;
      button.textContent = 'Exporting…';
    }
    var jobs = [];
    var produced = [];
    if (wantPdf) {
      jobs.push(
        exportGroupAsPdf(group)
          .then(function (blob) {
            produced.push(slug + '.pdf');
            return downloadBlob(blob, slug + '.pdf');
          })
          .catch(function (err) {
            showToast('PDF export failed: ' + (err && err.message || err));
          })
      );
    }
    if (wantHtml) {
      jobs.push(
        exportGroupAsHtmlZip(group)
          .then(function (blob) {
            produced.push(slug + '.zip');
            return downloadBlob(blob, slug + '.zip');
          })
          .catch(function (err) {
            showToast('HTML export failed: ' + (err && err.message || err));
          })
      );
    }
    Promise.all(jobs).then(function () {
      if (wantSelf) {
        var self = getSelfEmail();
        if (!self) {
          showToast('Set your email in Settings to use “email it to me”.');
        } else {
          // Build a mailto: with body listing the files we just produced.
          var lines = produced.length
            ? produced.map(function (f) { return '• ' + f; }).join('\r\n')
            : '(no files were produced)';
          var body = encodeURIComponent(
            'Files saved to your Downloads folder:\r\n' + lines
          );
          var subject = encodeURIComponent(name);
          window.location.href = 'mailto:?to=' + encodeURIComponent(self) +
            '&subject=' + subject + '&body=' + body;
        }
      }
      if (button) {
        button.disabled = false;
        button.textContent = 'Export';
      }
      if (produced.length) {
        showToast('Exported: ' + produced.join(', '));
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
  initDiagnosticsPanel();

  function bootDirectoryAsApp() {
    bootDebugLines.length = 0;
    if (siteHeaderEl) siteHeaderEl.classList.remove('hidden');
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
          if (siteHeaderEl) siteHeaderEl.classList.add('hidden');
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
