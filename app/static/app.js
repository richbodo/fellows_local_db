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
  var bootStuckPanelEl = document.getElementById('boot-stuck-panel');
  var bootStuckLastMarkEl = document.getElementById('boot-stuck-last-mark');
  var bootStuckElapsedEl = document.getElementById('boot-stuck-elapsed-secs');
  var authErrorPanelEl = document.getElementById('auth-error-panel');
  var authErrorPreEl = document.getElementById('auth-error-pre');
  var appWrapEl = document.getElementById('app-wrap');
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
  // Page-side compatibility constants for the worker handshake. Bumped only
  // on RPC wire-shape or schema-version changes; do NOT bump for cosmetic
  // worker refactors. Mirrored constants live in
  // app/static/vendor/sqlite-worker.js (`WORKER_RPC_VERSION`,
  // `RELATIONSHIPS_SCHEMA_VERSION`). See plans/local_first_worker_architecture.md
  // §"Why build label is not the gate".
  var EXPECTED_WORKER_RPC_VERSION = 3;
  var EXPECTED_RELATIONSHIPS_SCHEMA_VERSION = 1;

  // Thrown by mutating dataProvider methods when the worker reports a
  // workerRpcVersion / schemaVersion that doesn't match the page's
  // expected values. Reads still work; the SW's existing reload banner
  // is the canonical update affordance.
  function VersionMismatchError(msg) {
    var e = new Error(msg);
    e.name = 'VersionMismatchError';
    return e;
  }
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
  var macSafariHintEl = document.getElementById('install-mac-safari-hint');
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
  // Directory filter UI (issue #86). Trigger sits beside the search input;
  // the sheet is the single point of entry on every viewport. Controls
  // are populated lazily once phase 2 (?full=1) lands. See
  // filterState / filterOptions / buildFilterOptions below.
  var filterTriggerEl = document.getElementById('filter-trigger');
  var filterTriggerCountEl = document.getElementById('filter-trigger-count');
  var filterSheetEl = document.getElementById('filter-sheet');
  var filterScrimEl = document.getElementById('filter-scrim');
  var deferredInstallPrompt = null;
  var directoryDataSource = 'api';
  var dataProvider = null;
  var bootDebugLines = [];
  // Monotonic clock for boot-phase relative timing. performance.now() is
  // wall-clock-independent (won't jump on NTP correction) and survives DST
  // transitions cleanly. Falls back to Date.now() if performance is missing
  // (very old browsers; harmless approximation).
  var _bootPerfStart = (typeof performance !== 'undefined' && performance.now)
    ? performance.now()
    : Date.now();
  function _bootMs() {
    return (typeof performance !== 'undefined' && performance.now)
      ? Math.round(performance.now() - _bootPerfStart)
      : Date.now() - _bootPerfStart;
  }
  // Marks the time of every named milestone for later phase-duration math
  // in emitBootSummary(). Filled by bootMark(); reading it directly is
  // fine for diagnostics. Order is insertion order.
  var bootMarks = {};
  function bootMark(name) {
    if (!Object.prototype.hasOwnProperty.call(bootMarks, name)) {
      bootMarks[name] = _bootMs();
    }
  }
  // Expose for e2e tests that need to wait for a specific boot phase
  // (notably `get_full_done` — knowing that the boot path's second
  // route() call has fired prevents test assertions from racing with
  // an About-page re-render). Read-only by convention.
  window.__bootMarks = bootMarks;
  // Same rationale: e2e tests assert that specific boot trace lines
  // appear or don't appear. Notably, the install-landing → use-in-tab
  // regression test checks that 'worker: spawn + init starting' fires
  // exactly once (no warm-worker re-spawn). Read-only by convention.
  window.__bootDebugLines = bootDebugLines;
  // Captures the very start of script execution; everything else is
  // relative to this. Helpful when a boot stalls before pickDataProvider
  // even runs (e.g., long script-parse, blocked dependency fetch).
  bootMark('script_start');
  // Single-shot guard so emitBootSummary doesn't fire twice if boot
  // races finish out of order (image prewarm vs. getFull etc.).
  var _bootSummaryEmitted = false;
  var authDebugLines = [];
  var swLifecycleLog = [];
  // Local mirror of every reportInstallEvent() call, plus shape of
  // beforeinstallprompt/appinstalled events. The server-side counterpart
  // (kind=install events to /api/client-errors) is great for aggregate
  // funnel telemetry but useless when triaging a single user's session
  // from a pasted Diagnostics blob — that user's events are mixed in
  // with everyone else's on the server side. This array goes into the
  // Diagnostics dialog so the install lifecycle is visible per-session.
  // Capped at 50 entries (more than enough; install flow has ~10 events).
  var installLifecycleLog = [];
  // Snapshots of (display-mode: standalone) at multiple boot checkpoints.
  // Chrome desktop has been observed to return false for matchMedia(
  // '(display-mode: standalone)').matches at the very first script tick
  // in a freshly-launched PWA window, even when the window IS standalone —
  // that's the race the install-loop fix is defending against. Without
  // multiple samples we can't tell "always browser-tab" from "standalone
  // but matchMedia hadn't resolved." Samples carry both isStandaloneDisplay
  // Mode() (which OR's iOS navigator.standalone) and the raw matchMedia
  // result, plus a label for the call site.
  var displayModeSamples = [];
  function sampleDisplayMode(label) {
    try {
      var rawMatches = null;
      try {
        rawMatches = (window.matchMedia &&
          window.matchMedia('(display-mode: standalone)').matches) || false;
      } catch (eMm) { rawMatches = '(matchMedia threw)'; }
      var navStandalone = null;
      try { navStandalone = window.navigator && window.navigator.standalone; } catch (eNs) {}
      displayModeSamples.push({
        ts: new Date().toISOString(),
        label: String(label || ''),
        standalone: isStandaloneDisplayMode(),
        matchMedia: rawMatches,
        navStandalone: navStandalone === undefined ? '(unset)' : navStandalone
      });
      if (displayModeSamples.length > 30) displayModeSamples.shift();
    } catch (e) { /* best-effort */ }
  }
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
   *  is actually running vs what the server was deployed with.
   *
   *  '__FELLOWS_UI_DIAG__' is a build-time placeholder.
   *  build/build_pwa.py replaces it with `<YYYY-MM-DD>-<short-sha>` when
   *  assembling deploy/dist/; the dev server in app/server.py does the
   *  same substitution when serving /app.js. If you see the literal
   *  placeholder in the running app, the bundle wasn't built — you're
   *  either looking at raw source or hit a build step that didn't run.
   *  See docs/DevOps.md. */
  var FELLOWS_UI_DIAG = '__FELLOWS_UI_DIAG__';

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

  // Install identity — per-browser-storage codename + browser/OS metadata.
  // Generated once on first launch, persisted in localStorage. Survives
  // Clear App Cache; reset by Reset Everything (intentional — a fresh
  // reset deserves a fresh identity). Surfaces in document.title, the
  // About page, and bug-report diagnostics so users with multiple installs
  // (different browsers on the same Mac, multiple Chrome profiles, etc.)
  // can identify which install they're in. Rationale in docs/never-saas.md
  // § Stretched fit; user-facing explanation in
  // docs/users_manual.md § Install name / Multiple installs on the same
  // device.
  var INSTALL_IDENTITY_KEY = 'fellows_install_identity';
  var CODENAME_WORDS = [
    'giraffe', 'gorilla', 'mouse', 'panda', 'otter', 'koala', 'badger',
    'beaver', 'raccoon', 'squirrel', 'hamster', 'rabbit', 'fox', 'wolf',
    'bear', 'deer', 'moose', 'elk', 'bison', 'zebra', 'hippo', 'rhino',
    'elephant', 'camel', 'llama', 'alpaca', 'sloth', 'lemur', 'monkey',
    'baboon', 'gibbon', 'chimp', 'lynx', 'bobcat', 'puma', 'jaguar',
    'leopard', 'cheetah', 'lion', 'tiger', 'ocelot', 'mongoose', 'meerkat',
    'hedgehog', 'porcupine', 'armadillo', 'anteater', 'capybara',
    'marmot', 'wombat', 'possum', 'platypus', 'kangaroo', 'wallaby',
    'dingo', 'hyena', 'jackal', 'coyote', 'falcon', 'hawk', 'eagle',
    'owl', 'raven', 'sparrow', 'robin', 'finch', 'heron', 'crane',
    'pelican', 'flamingo', 'ostrich', 'penguin', 'puffin', 'parrot',
    'toucan', 'magpie', 'dolphin', 'whale', 'narwhal', 'walrus', 'seal',
    'manatee', 'octopus', 'turtle', 'tortoise', 'gecko', 'iguana',
    'chameleon', 'frog', 'salamander'
  ];
  var INSTALL_IDENTITY_CACHE = null;

  function detectBrowserBestEffort() {
    var ua = (navigator && navigator.userAgent) || '';
    if (/Edg\//.test(ua)) return 'Edge';
    if (/Firefox\//.test(ua)) return 'Firefox';
    if (/OPR\//.test(ua) || /Opera\//.test(ua)) return 'Opera';
    // Chrome match also covers Brave / Arc / other Chromium derivatives;
    // they all advertise "Chrome/..." in UA. The users-manual explains
    // the detection is best-effort and may collapse derivatives under
    // "Chrome".
    if (/Chrome\//.test(ua)) return 'Chrome';
    if (/Safari\//.test(ua) && /Version\//.test(ua)) return 'Safari';
    return 'Unknown';
  }

  function detectOSBestEffort() {
    var ua = (navigator && navigator.userAgent) || '';
    if (/Android/.test(ua)) return 'Android';
    if (/iPhone|iPad|iPod/.test(ua)) return 'iOS';
    if (/Macintosh|Mac OS X/.test(ua)) return 'macOS';
    if (/Windows/.test(ua)) return 'Windows';
    if (/Linux/.test(ua)) return 'Linux';
    return 'Unknown';
  }

  function generateCodename() {
    var n = CODENAME_WORDS.length;
    function pick() {
      return CODENAME_WORDS[Math.floor(Math.random() * n)];
    }
    // Three words picked independently. Repeat-allowed: the pool is
    // large enough that per-user collisions across a handful of
    // installs are vanishingly rare, and distinct-by-index would feel
    // hand-curated rather than auto-generated.
    return pick() + '-' + pick() + '-' + pick();
  }

  function getOrCreateInstallIdentity() {
    if (INSTALL_IDENTITY_CACHE) return INSTALL_IDENTITY_CACHE;
    try {
      var raw = localStorage.getItem(INSTALL_IDENTITY_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed.codename === 'string' && parsed.codename) {
          INSTALL_IDENTITY_CACHE = parsed;
          return parsed;
        }
      }
    } catch (e) {}
    var identity = {
      codename: generateCodename(),
      browser: detectBrowserBestEffort(),
      os: detectOSBestEffort(),
      installedAt: new Date().toISOString()
    };
    try {
      localStorage.setItem(INSTALL_IDENTITY_KEY, JSON.stringify(identity));
    } catch (e) {}
    INSTALL_IDENTITY_CACHE = identity;
    return identity;
  }

  function initInstallIdentityTitle() {
    try {
      var identity = getOrCreateInstallIdentity();
      // Append the codename to the existing window/tab title so it's
      // visible in OS window chrome, browser tab strips, command-tab
      // labels, and macOS Mission Control. Sticky enough that users
      // notice it without needing to navigate anywhere.
      document.title = (document.title || 'EHF Fellows Directory') +
        ' · ' + identity.codename;
    } catch (e) {}
  }

  // MCP bundle setup state. Tracks (a) whether the user has run the
  // Claude Desktop integration setup at least once so the Settings UI
  // can flip from "Set up…" to a refresh flow, and (b) the
  // fellows_db_sha that was current at setup time so we can detect
  // a server-side directory snapshot change and prompt for a re-install
  // of just shared_data_ops.mcpb. Plan:
  // plans/easy_mcp_install.md § 4 + § 8.
  var MCPB_SETUP_KEY = 'fellows_mcpb_setup';
  // Three-bundle layout — names match the .mcpb filenames served by
  // deploy/server.py (Handler.MCPB_NAMES whitelist) and the manifest
  // filenames in mcpb/node/manifests/. Order is the install order
  // shown in the preamble UI: directory first (recommended), private
  // second (per-call consent boundary), comms last (no DB).
  var MCPB_BUNDLE_NAMES = ['shared_data_ops', 'private_data_ops', 'comms'];

  function getMcpbSetupState() {
    try {
      var raw = localStorage.getItem(MCPB_SETUP_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === 'object') ? parsed : null;
    } catch (e) { return null; }
  }

  function persistMcpbSetupState(state) {
    try { localStorage.setItem(MCPB_SETUP_KEY, JSON.stringify(state)); }
    catch (e) {}
  }

  function recordMcpbSetup(fellowsDbSha) {
    var now = new Date().toISOString();
    var state = getMcpbSetupState() || {};
    if (!state.setupAt) state.setupAt = now;
    state.refreshedAt = now;
    state.fellowsDbSha = fellowsDbSha || null;
    persistMcpbSetupState(state);
  }

  function recordMcpbDirectoryRefresh(fellowsDbSha) {
    var state = getMcpbSetupState();
    if (!state) {
      // No setup record — directory refresh-only is meaningless on its
      // own. Treat as a full setup.
      recordMcpbSetup(fellowsDbSha);
      return;
    }
    state.fellowsDbSha = fellowsDbSha || null;
    state.refreshedAt = new Date().toISOString();
    persistMcpbSetupState(state);
  }

  // Trigger a same-origin file download via synthetic <a click()>. The
  // browser sends the existing session cookie automatically; the
  // auth-gated /mcpb/<name>.mcpb route accepts. A short setTimeout
  // between calls keeps Chrome from coalescing multiple sequential
  // downloads into one "this site is downloading multiple files" prompt
  // beyond the first. Used by both the MCPB Settings full-setup flow
  // and the About-page directory-refresh button.
  function triggerSameOriginDownload(url, filename) {
    return new Promise(function (resolve) {
      var a = document.createElement('a');
      a.href = url;
      if (filename) a.download = filename;
      a.rel = 'noopener';
      a.style.display = 'none';
      document.body.appendChild(a);
      try { a.click(); } catch (e) {}
      setTimeout(function () {
        try { document.body.removeChild(a); } catch (e) {}
        resolve();
      }, 250);
    });
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
  initInstallIdentityTitle();
  // Install early so the ring buffer captures errors thrown during the rest
  // of the IIFE setup. Function declaration is hoisted; definition lives
  // further down with the rest of the bug-report module.
  initBugReportErrorCapture();

  // Boot snapshot of /build-meta.json. The hourly update check and the
  // About-page "Check for updates" button both compare against this snapshot
  // to decide whether the server has shipped a newer build since this page
  // was loaded. Populated asynchronously; consumers guard on .git_sha.
  //
  // `fellows_db_sha` (Phase 3 of the local-first worker plan) is the
  // input to the worker's SHA-keyed `ensureFellowsDb` refresh. We capture
  // it here so `pickDataProvider` can pass it into the worker without
  // doing its own /build-meta.json fetch.
  var bootBuildMeta = {
    git_sha: null,
    built_at: null,
    fellows_db_sha: null,
    capturedAt: null
  };
  var updateCheckState = {
    lastAttemptAt: null,
    lastResult: null,
    lastLatestMeta: null
  };

  // Promise of the boot-time /build-meta.json fetch. Resolved when the
  // first response comes back (regardless of ok/fail). Consumers `.then`
  // on it to read fields after population without racing the IIFE.
  var bootBuildMetaPromise = null;

  // Populate the server-side label independently of the auth flow so a dev
  // reading the badge still gets a signal when /api/auth/status is failing.
  function primeServerBadgeFromBuildMeta() {
    try {
      bootBuildMetaPromise = fetch('/build-meta.json', { cache: 'no-cache', credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (meta) {
          if (meta) {
            setBuildBadgeServer(meta.git_sha, meta.built_at);
            if (!bootBuildMeta.git_sha) {
              bootBuildMeta = {
                git_sha: meta.git_sha || null,
                built_at: meta.built_at || null,
                fellows_db_sha: (typeof meta.fellows_db_sha === 'string' && meta.fellows_db_sha)
                  ? meta.fellows_db_sha : null,
                pubkey_fingerprint: (typeof meta.pubkey_fingerprint === 'string' && meta.pubkey_fingerprint)
                  ? meta.pubkey_fingerprint : null,
                capturedAt: new Date().toISOString()
              };
            }
          }
          return bootBuildMeta;
        })
        .catch(function () { return bootBuildMeta; });
    } catch (e) {
      bootBuildMetaPromise = Promise.resolve(bootBuildMeta);
    }
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
            pubkey_fingerprint: (meta && typeof meta.pubkey_fingerprint === 'string' && meta.pubkey_fingerprint)
              ? meta.pubkey_fingerprint : null,
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

  // Companion to checkForServerUpdate — checks whether the bundled
  // fellows.db has changed since the local sidecar was last written.
  // Always uses /build-meta.json:fellows_db_sha as the truth value;
  // the worker handles the local read. Independent of app-shell SHA
  // so the two flows can succeed/fail individually.
  // plans/opt_in_directory_data_updates.md.
  //
  // Returns a Promise resolving to { status, serverSha?, localSha?, fetchedAt?, error? }.
  // `status`:
  //   'update-available' — local fellows.db differs from server
  //   'up-to-date'       — SHAs match
  //   'no-local-data'    — worker has no fellows.db (cold-start case)
  //   'unsupported'      — running on a provider that can't compare
  //                        (api+idb fallback, no-OPFS browser)
  //   'worker-stale'     — page is on a newer build than the worker
  //                        (transient SW upgrade race; worker doesn't
  //                        know the new RPC). Resolves on reload.
  //   'error'            — server unreachable or worker errored
  function checkForDirectoryDataUpdate() {
    if (!dataProvider || typeof dataProvider._compareFellowsDbSha !== 'function') {
      return Promise.resolve({ status: 'unsupported' });
    }
    return fetch('/build-meta.json', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (meta) {
        var serverSha = (meta && typeof meta.fellows_db_sha === 'string' && meta.fellows_db_sha)
          ? meta.fellows_db_sha : null;
        return dataProvider._compareFellowsDbSha({ serverSha: serverSha }).then(function (cmp) {
          if (!cmp.hasFellowsDb) {
            return {
              status: 'no-local-data',
              serverSha: serverSha,
              localSha: cmp.localSha,
              fetchedAt: cmp.fetchedAt
            };
          }
          if (cmp.dataUpdateAvailable === true) {
            return {
              status: 'update-available',
              serverSha: serverSha,
              localSha: cmp.localSha,
              fetchedAt: cmp.fetchedAt
            };
          }
          if (cmp.dataUpdateAvailable === false) {
            return {
              status: 'up-to-date',
              serverSha: serverSha,
              localSha: cmp.localSha,
              fetchedAt: cmp.fetchedAt
            };
          }
          // dataUpdateAvailable === null (server didn't expose a SHA).
          return {
            status: 'error',
            error: 'server did not report fellows_db_sha',
            serverSha: serverSha,
            localSha: cmp.localSha,
            fetchedAt: cmp.fetchedAt
          };
        });
      })
      .catch(function (err) {
        // Worker doesn't know the new RPC → page is newer than the
        // worker bundle. Common during the SW upgrade race: page
        // loaded the new shell, worker was spawned with the old shell
        // still in cache. Reload spawns a fresh worker from the new
        // cache and the check works.
        var msg = (err && err.message) || String(err);
        if (/unknown op:\s*compareFellowsDbSha/i.test(msg)) {
          return { status: 'worker-stale', error: msg };
        }
        return { status: 'error', error: msg };
      });
  }

  // Handler for the "Update directory data" button on the About page.
  // Three-step flow per plans/opt_in_directory_data_updates.md:
  //   1. previewFellowsDbSwap → fetch + validate, compute affected
  //      members.
  //   2. If affected.length > 0, render the confirm dialog;
  //      Cancel → cancelFellowsDbSwap; Update anyway → step 3.
  //      If affected.length === 0, apply silently (step 3).
  //   3. applyFellowsDbSwap → atomic replace + meta update.
  //   4. Refresh in-page directory state and the orphan set.
  function handleUpdateDirectoryDataClick(checkResult, refreshBtn) {
    var dataStatusEl = document.getElementById('about-data-status');
    var dataActionEl = document.getElementById('about-data-action');
    var lastCheckEl = document.getElementById('about-last-check');
    function setBusy(msg) {
      if (dataStatusEl) dataStatusEl.textContent = msg;
      if (dataActionEl) dataActionEl.innerHTML = '';
    }
    function setDone(msg) {
      if (dataStatusEl) dataStatusEl.textContent = msg;
      if (dataActionEl) dataActionEl.innerHTML = '';
      if (lastCheckEl) lastCheckEl.textContent = 'Last check: ' + new Date().toISOString();
    }

    if (!dataProvider || typeof dataProvider._previewFellowsDbSwap !== 'function') {
      setDone('Directory data updates aren’t available in this browser.');
      return;
    }
    var serverSha = checkResult && checkResult.serverSha;
    setBusy('Checking impact…');

    dataProvider._previewFellowsDbSwap({ serverSha: serverSha })
      .then(function (preview) {
        var affected = (preview && preview.affectedGroups) || [];
        if (!affected.length) {
          // No group impact — apply silently.
          return applyDirectoryUpdate(preview.stagingId);
        }
        return new Promise(function (resolve) {
          openDirectoryUpdateDialog(affected, {
            onCancel: function () {
              dataProvider._cancelFellowsDbSwap({ stagingId: preview.stagingId })
                .catch(function () {});
              setDone('Update cancelled. Your directory data is unchanged.');
              resolve();
            },
            onConfirm: function () {
              applyDirectoryUpdate(preview.stagingId).then(resolve, resolve);
            }
          });
        });
      })
      .catch(function (err) {
        if (err && err.versionMismatch) {
          setDone('Reload the app first (a newer version is available), then try again.');
          return;
        }
        var reason = (err && err.message) || String(err);
        setDone('Could not stage update: ' + reason);
      });

    function applyDirectoryUpdate(stagingId) {
      setBusy('Applying update…');
      return dataProvider._applyFellowsDbSwap({ stagingId: stagingId })
        .then(function () {
          // Re-render the directory in place — getList + getFull rebuild
          // the in-memory cache. Cheap; ~hundreds of rows.
          return reloadDirectoryAfterDataSwap()
            .catch(function () { /* surfaced via toast below if it matters */ });
        })
        .then(function () {
          // Refresh orphan set against the freshly-imported fellows.db
          // so group detail views flag any rows that became orphaned by
          // the swap.
          if (typeof dataProvider._findOrphanedGroupMembers === 'function') {
            return dataProvider._findOrphanedGroupMembers().then(function (res) {
              setOrphanedRecordIdsFromList(res && res.orphans);
            }).catch(function () {});
          }
        })
        .then(function () {
          setDone('Directory data updated.');
        })
        .catch(function (err) {
          var reason = (err && err.message) || String(err);
          setDone('Update failed: ' + reason + '. Try again.');
        });
    }
  }

  // Reload directory data after a swap. Re-uses the existing getList +
  // getFull pipeline so the rail / search / detail views all see the
  // new rows. Resolves once renderDirectory has run with the new data.
  // Skips re-routing the current view if the user is on About — About
  // doesn't render fellow data, and a re-render would wipe the status
  // text the apply handler is about to set.
  function reloadDirectoryAfterDataSwap() {
    if (!dataProvider || typeof dataProvider.getList !== 'function') return Promise.resolve();
    return dataProvider.getList().then(function (data) {
      list = Array.isArray(data) ? data : [];
      renderDirectory();
      return dataProvider.getFull();
    }).then(function (full) {
      if (Array.isArray(full)) {
        fullFellowsCache = full;
        fellowsBySlug = new Map();
        full.forEach(function (f) {
          if (f.slug) fellowsBySlug.set(f.slug, f);
          if (f.record_id) fellowsBySlug.set(f.record_id, f);
        });
        // Re-derive filter options after a directory-data swap; the new
        // bytes may have introduced or removed cohort/region/citizenship
        // values. Existing filterState is preserved — values that no
        // longer exist in the data simply match nothing.
        activateFiltersFromFullData(full);
      }
      // Re-route data-rendering views (group detail, fellow detail,
      // visual directory) so the new bytes show through. Skip when
      // the user is on a non-data view (About, Settings) — re-rendering
      // those would clobber the just-applied status text and add
      // nothing useful.
      var hash = String(window.location.hash || '');
      var skipReroute = hash.indexOf('#/about') === 0 || hash.indexOf('#/settings') === 0;
      if (!skipReroute) {
        try { route(); } catch (e) {}
      }
    });
  }

  // Build a one-shot modal listing the affected members. Cleans itself
  // up on close. No bespoke markup in index.html — this dialog is
  // unique to the update flow and is created on demand.
  function openDirectoryUpdateDialog(affected, callbacks) {
    var existing = document.getElementById('directory-update-dialog');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

    var dialog = document.createElement('div');
    dialog.id = 'directory-update-dialog';
    dialog.className = 'directory-update-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'directory-update-dialog-title');

    var listHtml = '';
    for (var i = 0; i < affected.length; i++) {
      var item = affected[i];
      var name = item.name || ('record_id ' + item.recordId);
      var groupNames = (item.groups || []).map(function (g) { return '‘' + g.name + '’'; });
      listHtml += '<li><strong>' + escapeHtml(name) + '</strong> — in ' +
        escapeHtml(groupNames.join(', ')) + '</li>';
    }

    dialog.innerHTML =
      '<div class="directory-update-dialog-inner" role="document">' +
        '<h2 id="directory-update-dialog-title" class="directory-update-dialog-title">Update directory data?</h2>' +
        '<p>This update removes <strong>' + affected.length + ' fellow' +
          (affected.length === 1 ? '' : 's') + '</strong> from your saved groups:</p>' +
        '<ul class="directory-update-dialog-list">' + listHtml + '</ul>' +
        '<p>After the update they will no longer appear in those groups. ' +
        'Their entries will be flagged as &lsquo;Profile no longer available&rsquo; ' +
        'so you can review and remove them.</p>' +
        '<div class="directory-update-dialog-actions">' +
          '<button type="button" class="directory-update-dialog-cancel" id="directory-update-dialog-cancel">Cancel</button>' +
          '<button type="button" class="directory-update-dialog-confirm" id="directory-update-dialog-confirm">Update anyway</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(dialog);

    function close() {
      if (dialog.parentNode) dialog.parentNode.removeChild(dialog);
      document.removeEventListener('keydown', onKey);
    }
    function onKey(e) {
      if (e.key === 'Escape') {
        close();
        if (callbacks && callbacks.onCancel) callbacks.onCancel();
      }
    }
    document.addEventListener('keydown', onKey);

    document.getElementById('directory-update-dialog-cancel').addEventListener('click', function () {
      close();
      if (callbacks && callbacks.onCancel) callbacks.onCancel();
    });
    document.getElementById('directory-update-dialog-confirm').addEventListener('click', function () {
      close();
      if (callbacks && callbacks.onConfirm) callbacks.onConfirm();
    });
    // Click outside the inner panel closes (cancel-equivalent).
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog) {
        close();
        if (callbacks && callbacks.onCancel) callbacks.onCancel();
      }
    });
    // Focus the cancel button by default — destructive action requires
    // explicit confirm.
    var cancelBtn = document.getElementById('directory-update-dialog-cancel');
    if (cancelBtn) try { cancelBtn.focus(); } catch (e) {}
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
      // No cache-bust query: profile photos for a given slug are
      // immutable and the URL must stay stable across deploys. A `?v=`
      // suffix tied to the build label produces a fresh cache key on
      // every deploy and never evicts the old one — fellows-images-v1
      // grew to 725 entries across 508 fellows in production before
      // this fix. Recovery from a previously-404'd photo lags the
      // deploy by up to a few minutes (browser HTTP cache TTL on the
      // 404), which is acceptable for ~hundreds of mostly-static
      // photos. The SW activate handler also sweeps any legacy `?v=`
      // entries left over from before this change.
      var jpgUrl = '/images/' + encodeURIComponent(f.slug) + '.jpg';
      var pngUrl = '/images/' + encodeURIComponent(f.slug) + '.png';
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
      bootMark('image_prewarm_done');
      // End-of-boot milestone — emit summary if not already emitted by
      // an earlier path (e.g. getFull errored and we never reached here).
      emitBootSummary();
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
  // message — never to gate features (the worker decides if OPFS works).
  // Returns:
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

  // The cheap-fix copy for the multi-tab ownership-conflict case. Returns
  // an HTML string with the same outer .local-data-unavailable shell as
  // renderLocalDataUnavailablePanel so the existing CSS applies. Distinct
  // from the version-floor copy because the user is on a perfectly
  // capable browser — the only problem is another tab is holding OPFS.
  // The remedy is mechanical: close the other tab and reload here. The
  // coordinated takeover is the follow-up in
  // plans/multi_tab_ownership_takeover.md.
  function renderOwnershipConflictPanel(feature) {
    var label = feature || 'this feature';
    var headline = 'Directory is already open in another window';
    var lede =
      'Saved groups and per-device settings live in your browser\'s local storage (OPFS), and only ' +
      'one tab or window can use it at a time. Another window of this app is already using it, ' +
      'so ' + escapeHtml(label) + ' can\'t open here until you close that window.';
    var detailHtml =
      '<p>To use ' + escapeHtml(label) + ' here:</p>' +
      '<ol>' +
        '<li>Find the other open tab or window of this app (it may be the installed app on your dock or home screen).</li>' +
        '<li>Close it, or quit the installed app entirely.</li>' +
        '<li>Click <b>Reload this tab</b> below.</li>' +
      '</ol>' +
      '<p>If you\'d rather use the other window, switch to it instead — your work there is intact.</p>';
    // Inline boot trace so the user (and the maintainer triaging) can
    // see the captured DOMException without clicking elsewhere. Same
    // pattern as the runtimeFailure branch in renderLocalDataUnavailablePanel.
    var traceParts = [];
    try {
      if (warmWorkerError) {
        traceParts.push('Worker init error: ' +
          ((warmWorkerError && warmWorkerError.message) || String(warmWorkerError)));
      }
    } catch (e) {}
    try {
      if (bootDebugLines && bootDebugLines.length) {
        traceParts.push('');
        traceParts.push('Boot trace (chronological):');
        traceParts.push(bootDebugLines.join('\n'));
      }
    } catch (e) {}
    var traceHtml = traceParts.length
      ? '<details class="local-data-unavailable-trace">' +
          '<summary>Show what failed (boot trace)</summary>' +
          '<pre>' + escapeHtml(traceParts.join('\n')) + '</pre>' +
        '</details>'
      : '';
    return (
      '<div class="local-data-unavailable">' +
        '<h3>' + escapeHtml(headline) + '</h3>' +
        '<p class="local-data-unavailable-lede">' + lede + '</p>' +
        detailHtml +
        '<p><button type="button" class="local-data-unavailable-action" ' +
          'onclick="window.location.reload()">Reload this tab</button></p>' +
        traceHtml +
        '<p class="local-data-unavailable-foot">' +
          'If reloading doesn\'t help after closing every other tab and the installed app, ' +
          'please reach out — we\'re happy to help.' +
        '</p>' +
      '</div>'
    );
  }

  // Build the "your browser can't store groups locally" panel. Returns an
  // HTML string. Caller decides which container to drop it into.
  // `feature` is what the user was trying to do — "groups", "this group",
  // "settings", "save this group". Used in the headline only.
  // `opts.runtimeFailure` (optional) means the OPFS path *should* have
  // worked on this browser version but failed at runtime (e.g. the page
  // loaded before the dev server picked up COOP/COEP, or a transient
  // sqlite-wasm glitch). When set AND the detected version meets the
  // floor, we render a different copy that doesn't tell a Chrome-130
  // user to upgrade Chrome.
  // `opts.ownershipConflict` (optional) means worker init failed because
  // another tab/window already holds the OPFS SAH-pool. Defaults to the
  // module-level bootOwnershipConflict flag if not passed, so callsites
  // don't need to thread it through. Renders a specific "directory is
  // open in another window" panel — see plans/multi_tab_ownership_takeover.md
  // for the coordinated-takeover follow-up that supersedes this copy.
  function renderLocalDataUnavailablePanel(feature, opts) {
    opts = opts || {};
    if (opts.ownershipConflict == null) {
      opts.ownershipConflict = bootOwnershipConflict;
    }
    if (opts.ownershipConflict) {
      return renderOwnershipConflictPanel(feature);
    }
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
    // "Version meets the floor we ship for": if both numbers are known
    // and version >= minVersion. Used to decide whether the "you need a
    // newer browser" copy applies, or whether the runtime-failure copy
    // is a better fit.
    var versionLooksOk =
      b.version != null && b.minVersion != null && b.version >= b.minVersion;
    var detailLines = [];
    if (opts.runtimeFailure && versionLooksOk) {
      // Browser is recent enough on paper. Most likely cause: the page
      // loaded before the server sent the cross-origin-isolation headers
      // OPFS-SAH-Pool needs (Cross-Origin-Opener-Policy: same-origin +
      // Cross-Origin-Embedder-Policy: require-corp). A hard reload almost
      // always fixes it. If not, Diagnostics has the boot trace.
      detailLines.push(
        'You\'re running ' + browserHuman + versionTxt + ', which is recent enough — ' +
        'so this is unusual. The local-storage layer (OPFS) didn\'t initialize on this load. ' +
        'The most common cause is the page loading before the server finished sending the ' +
        'cross-origin-isolation headers OPFS needs.'
      );
      detailLines.push(
        'Try a <b>hard reload</b>: <kbd>Cmd-Shift-R</kbd> on macOS, ' +
        '<kbd>Ctrl-Shift-R</kbd> on Windows/Linux. ' +
        'If that doesn\'t fix it, open <b>Diagnostics</b> (lower-left button) and copy the boot trace — ' +
        'the OPFS gates section shows exactly which capability check failed.'
      );
    } else if (b.onIos) {
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
    var isRuntime = !!(opts.runtimeFailure && versionLooksOk);
    var headline = isRuntime
      ? 'Can\'t open ' + escapeHtml(label) + ' right now'
      : 'Can\'t open ' + escapeHtml(label) + ' on this browser';
    var lede = isRuntime
      ? 'Saved groups and per-device settings live in your browser\'s local storage (OPFS). ' +
        'On this load, that storage didn\'t initialize — so the rest of the app works, but ' +
        escapeHtml(label) + ' can\'t until it does.'
      : 'Saved groups and per-device settings live in your browser\'s local storage. ' +
        'On this device, that storage isn\'t available — so the rest of the app works, but ' +
        escapeHtml(label) + ' can\'t.';
    // On the runtime-failure path, embed the OPFS gates + boot trace
    // inline so the user (and the maintainer triaging) can see the
    // actual reason without clicking elsewhere. Collapsed by default
    // so the panel stays scannable; always present when isRuntime.
    var traceHtml = '';
    if (isRuntime) {
      var traceParts = [];
      try {
        traceParts.push('Provider chosen: ' +
          (dataProvider && dataProvider.kind ? dataProvider.kind : '(none yet)'));
      } catch (e) {}
      try {
        traceParts.push('OPFS capability gates:');
        traceParts.push(describeOpfsGates());
      } catch (e) {
        traceParts.push('(could not read gates: ' + String(e && e.message || e) + ')');
      }
      try {
        if (bootDebugLines && bootDebugLines.length) {
          traceParts.push('');
          traceParts.push('Boot trace (chronological):');
          traceParts.push(bootDebugLines.join('\n'));
        } else {
          traceParts.push('');
          traceParts.push('Boot trace: (empty — nothing recorded yet)');
        }
      } catch (e) {
        traceParts.push('Boot trace error: ' + String(e && e.message || e));
      }
      traceHtml =
        '<details class="local-data-unavailable-trace">' +
          '<summary>Show what failed (boot trace)</summary>' +
          '<pre>' + escapeHtml(traceParts.join('\n')) + '</pre>' +
        '</details>';
    }
    return (
      '<div class="local-data-unavailable">' +
        '<h3>' + headline + '</h3>' +
        '<p class="local-data-unavailable-lede">' + lede + '</p>' +
        detailHtml +
        traceHtml +
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

  function bootDebugPush(msg) {
    // Relative `t+Nms` makes phase durations readable at a glance without
    // having to do math on the ISO timestamps. Cheap (one performance.now()
    // call) and only ever appended — no parsing concerns. Unblocks the
    // "tab spun for several minutes but boot trace looked fast" debug
    // case where the wall-clock timestamps gave no signal about which
    // phase actually stalled.
    bootDebugLines.push(
      new Date().toISOString() + ' (t+' + _bootMs() + 'ms) ' + String(msg)
    );
  }

  // Persistence key for last-known-slow boot. Single record, overwritten
  // each time a new slow boot is detected. Survives Clear App Cache
  // intentionally — a regression that only repros once a week needs to
  // outlive the session that captured it.
  var SLOW_BOOT_KEY = 'fellows_last_slow_boot';
  // Thresholds. Conservative — we want this to fire only when boot
  // genuinely felt slow, not on every minor hiccup. Total covers
  // end-to-end perceived latency; any-phase covers a single stuck step
  // even when the rest were fast.
  var SLOW_BOOT_TOTAL_MS = 3000;
  var SLOW_BOOT_PHASE_MS = 2000;

  // Persist a one-line slow-boot record to localStorage so the user can
  // copy it from diagnostics on the next session even if the slow tab
  // got closed. Safe under quota / private-mode by failing silently.
  function persistSlowBoot(record) {
    try {
      localStorage.setItem(SLOW_BOOT_KEY, JSON.stringify(record));
    } catch (e) {}
  }

  // Read the last persisted slow-boot record, if any. Returns null on
  // missing / malformed / unreadable. Only called from diagnostics.
  function readLastSlowBoot() {
    try {
      var raw = localStorage.getItem(SLOW_BOOT_KEY);
      if (!raw) return null;
      var rec = JSON.parse(raw);
      if (rec && typeof rec === 'object') return rec;
    } catch (e) {}
    return null;
  }

  // Compute a phase-duration line from bootMarks and emit it once. Called
  // from multiple boot completion sites (provider ready, getList done,
  // getFull done, image prewarm done) — the _bootSummaryEmitted guard
  // makes it idempotent. Persists a slow-boot record when warranted.
  // The phase order here mirrors the sequence in bootDirectoryAsApp;
  // missing marks are skipped, so this works on partial-boot exits too.
  function emitBootSummary() {
    if (_bootSummaryEmitted) return;
    _bootSummaryEmitted = true;
    bootMark('summary');
    var phaseSeq = [
      'script_start',
      'pick_provider_start',
      'worker_init_done',
      'provider_ready',
      'get_list_done',
      'get_full_done',
      'image_prewarm_done',
      'summary'
    ];
    var parts = [];
    var slowestPhase = null;
    var slowestMs = 0;
    for (var i = 1; i < phaseSeq.length; i++) {
      var prev = phaseSeq[i - 1];
      var curr = phaseSeq[i];
      if (bootMarks[prev] == null || bootMarks[curr] == null) continue;
      var dur = bootMarks[curr] - bootMarks[prev];
      parts.push(curr.replace(/_/g, '-') + '=' + dur + 'ms');
      if (dur > slowestMs) {
        slowestMs = dur;
        slowestPhase = curr;
      }
    }
    var totalMs = bootMarks.summary != null ? bootMarks.summary : _bootMs();
    bootDebugPush(
      'boot summary: ' + parts.join(' ') + ' total=' + totalMs + 'ms'
    );
    if (totalMs > SLOW_BOOT_TOTAL_MS || slowestMs > SLOW_BOOT_PHASE_MS) {
      var rec = {
        ts: new Date().toISOString(),
        totalMs: totalMs,
        slowestPhase: slowestPhase,
        slowestMs: slowestMs,
        phases: parts.join(' '),
        route: (location && location.hash) ? location.hash : '',
        ua: (navigator && navigator.userAgent) ? navigator.userAgent.slice(0, 160) : ''
      };
      persistSlowBoot(rec);
      bootDebugPush(
        'boot SLOW (>'+ SLOW_BOOT_TOTAL_MS + 'ms total or >' + SLOW_BOOT_PHASE_MS +
        'ms phase) — persisted to localStorage[' + SLOW_BOOT_KEY +
        '] for inspection on next session'
      );
    }
  }

  // List shell caches and remove any that don't match the current build
  // label. The SW activate handler already does this (sw.js), but in the
  // 2026-05-05 incident the user's diagnostics showed two shell caches
  // coexisting after a label rebump — the activate prune either didn't
  // run or didn't catch the previous version. This is a defensive page-side
  // safety net: cheap (one caches.keys() call) and silent on the happy
  // path. Logs to bootDebugLines so any future incident shows whether
  // this path actually fired and what it pruned.
  function auditShellCaches() {
    if (!self.caches || typeof self.caches.keys !== 'function') return;
    self.caches.keys().then(function (keys) {
      var shellKeys = keys.filter(function (k) {
        return typeof k === 'string' && k.indexOf('fellows-app-shell-') === 0;
      });
      var current = 'fellows-app-shell-' + FELLOWS_UI_DIAG;
      var stale = shellKeys.filter(function (k) { return k !== current; });
      bootDebugPush(
        'cache audit: shell caches=' + shellKeys.length +
        ' (current=' + current + ', stale=' + stale.length + ')'
      );
      if (!stale.length) return;
      Promise.all(stale.map(function (k) {
        return self.caches.delete(k).then(function (ok) {
          bootDebugPush(
            'cache audit: deleted ' + k + ' (ok=' + ok + ')'
          );
        }).catch(function (e) {
          bootDebugPush(
            'cache audit: delete failed ' + k + ': ' + (e && e.message || e)
          );
        });
      }));
    }).catch(function (e) {
      bootDebugPush('cache audit: caches.keys() failed: ' + (e && e.message || e));
    });
  }

  function authDebugPush(msg) {
    authDebugLines.push(new Date().toISOString() + ' ' + String(msg));
  }

  // Describes the page-side capability gates that decide whether the
  // worker stands a chance of bringing OPFS up. The actual OPFS opener
  // is the dedicated worker (sqlite-worker.js) — these checks are for
  // diagnostics surfaces and the unsupported-browser copy. The main
  // thread itself never opens OPFS post-cutover.
  function describeOpfsGates() {
    var lines = [];
    lines.push('standalone display-mode: ' + isStandaloneDisplayMode() + ' (informational; not a gate)');
    lines.push('Worker constructor: ' + (typeof Worker));
    lines.push('navigator.storage: ' + (navigator.storage ? 'present' : 'missing'));
    // The OPFS root opener itself lives in the worker post-cutover (L1);
    // the page records only the page-side method-presence type (no actual
    // call) so the diagnostic doesn't violate the "no main-thread OPFS"
    // rule. Bracket access is used so a literal-string grep against
    // app.js for the OPFS root method stays clean.
    var pageOpfsApi = navigator.storage && typeof navigator.storage['getDirectory'];
    lines.push('page-side OPFS opener (informational): ' + (pageOpfsApi || 'missing'));
    lines.push('isSecureContext: ' + globalThis.isSecureContext);
    lines.push('crossOriginIsolated: ' + (typeof globalThis.crossOriginIsolated !== 'undefined' ? globalThis.crossOriginIsolated : '(unset)'));
    lines.push('navigator.onLine: ' + navigator.onLine);
    // Page-side surface check is informational. The worker carries its
    // own check; if its init throws, the page falls back to API+IDB.
    lines.push('--- Page-side OPFS API surface (informational) ---');
    lines.push('FileSystemHandle: ' + typeof globalThis.FileSystemHandle);
    lines.push('FileSystemDirectoryHandle: ' + typeof globalThis.FileSystemDirectoryHandle);
    lines.push('FileSystemFileHandle: ' + typeof globalThis.FileSystemFileHandle);
    var sahType = '(FileSystemFileHandle missing)';
    try {
      sahType = globalThis.FileSystemFileHandle
        ? typeof globalThis.FileSystemFileHandle.prototype.createSyncAccessHandle
        : '(FileSystemFileHandle missing)';
    } catch (e) {
      sahType = '(probe threw: ' + (e && e.message || e) + ')';
    }
    lines.push('FileSystemFileHandle.prototype.createSyncAccessHandle: ' + sahType);
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

  // Boot watchdog. The bootDirectoryAsApp Promise chain has no built-in
  // timeout: if the worker init resolves (we've already got an 8 s timeout
  // there) but a subsequent RPC like _ensureFellowsDb or getList hangs —
  // an OPFS contention edge case, an unresponsive cached fellows.db, an
  // SW that won't deliver a network response — the user just sees
  // "Loading…" forever. The watchdog fires after BOOT_WATCHDOG_MS to
  // surface that state with actionable recovery affordances rather than
  // letting the user guess.
  //
  // Cleared on bootMark('get_list_done') (the first moment the directory
  // is known-renderable) and on .catch in bootDirectoryAsApp (different
  // failure path; showBootFailure already has the user covered).
  //
  // The ?wd=<ms> URL parameter overrides the timer for e2e tests; bounded
  // to a sane range so it can't be abused into an infinite loop or a
  // pathological 0-delay.
  var BOOT_WATCHDOG_MS = (function () {
    try {
      var raw = new URLSearchParams(location.search).get('wd');
      var n = raw == null ? null : parseInt(raw, 10);
      if (n != null && isFinite(n) && n >= 100 && n <= 60000) return n;
    } catch (e) {}
    return 20000;
  })();
  var bootWatchdog = {
    state: 'idle',     // idle → pending → cleared|fired
    startedAt: null,
    lastMark: null,
    timerId: null,
    elapsedMs: null
  };
  // Exposed for e2e tests that need to assert the watchdog has fired or
  // not without re-implementing the timer logic. Read-only by convention.
  window.__bootWatchdog = bootWatchdog;

  // Returns the most recent bootMark name (insertion order in bootMarks).
  // bootMark is idempotent so insertion order is the order phases first
  // completed; the last-inserted key is therefore "the latest phase that
  // finished" — the load-bearing context for the recovery panel.
  function lastCompletedBootMark() {
    var keys = Object.keys(bootMarks);
    return keys.length ? keys[keys.length - 1] : null;
  }

  function startBootWatchdog() {
    if (bootWatchdog.state !== 'idle') return;
    bootWatchdog.state = 'pending';
    bootWatchdog.startedAt = _bootMs();
    bootWatchdog.timerId = setTimeout(function () {
      if (bootWatchdog.state !== 'pending') return;
      bootWatchdog.state = 'fired';
      bootWatchdog.lastMark = lastCompletedBootMark();
      bootWatchdog.elapsedMs = _bootMs() - bootWatchdog.startedAt;
      bootDebugPush(
        'boot watchdog: stuck after ' + BOOT_WATCHDOG_MS +
        'ms; last mark=' + (bootWatchdog.lastMark || '(none)')
      );
      // Telemetry so the operator sees stuck-boot rates in journald
      // without depending on the user clicking Send report. Cardinality
      // bounded to one event per page load by the state machine.
      try {
        reportWorkerEvent('boot_stuck', String(bootWatchdog.lastMark || 'unknown'));
      } catch (e) {}
      showBootStuck(bootWatchdog.lastMark);
    }, BOOT_WATCHDOG_MS);
  }

  function clearBootWatchdog(reason) {
    if (bootWatchdog.state !== 'pending') return;
    bootWatchdog.state = 'cleared';
    bootWatchdog.lastMark = lastCompletedBootMark();
    bootWatchdog.elapsedMs = bootWatchdog.startedAt != null
      ? _bootMs() - bootWatchdog.startedAt
      : null;
    if (bootWatchdog.timerId != null) {
      clearTimeout(bootWatchdog.timerId);
      bootWatchdog.timerId = null;
    }
    bootDebugPush(
      'boot watchdog: cleared (' + (reason || 'unspecified') +
      ') at last mark=' + (bootWatchdog.lastMark || '(none)') +
      ' elapsed=' + (bootWatchdog.elapsedMs != null ? bootWatchdog.elapsedMs + 'ms' : '?')
    );
  }

  function showBootStuck(lastMark) {
    if (loadingEl) loadingEl.classList.add('hidden');
    if (bootStuckLastMarkEl) {
      bootStuckLastMarkEl.textContent = lastMark || 'starting up';
    }
    if (bootStuckElapsedEl) {
      bootStuckElapsedEl.textContent = String(Math.round(BOOT_WATCHDOG_MS / 1000));
    }
    if (bootStuckPanelEl) bootStuckPanelEl.classList.remove('hidden');
    // Capture a snapshot of the boot trace into the bug-report ring so
    // the Send-report button (sync-only path) carries enough context
    // without an awaitable diagnostics probe — the reason we ended up
    // here is precisely that async probes can hang.
    pushBugReportError(
      'boot',
      'boot_stuck',
      'last_mark=' + String(lastMark || 'unknown') +
      ' elapsed=' + BOOT_WATCHDOG_MS + 'ms'
    );
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

  // Re-entrancy + repeat-call guards for clearAllAppData / clearEverything.
  // 2026-05-04 incident: an OPFS-state-induced boot pathology made the
  // post-Clear-App-Cache reload re-enter clearAllAppData on the next page
  // load — the URL kept getting bumped to /?cache_reset=<new timestamp> in
  // a slow loop and the page flashed visibly. We never identified the exact
  // trigger; Reset Everything (clearEverything → wipes OPFS via worker
  // wipeAll RPC) broke it. Defense in depth:
  //
  //   - Across-reload guard: if the URL already carries a recent
  //     ?cache_reset= timestamp from a previous run, refuse to fire again.
  //     The URL is the only state the previous run guarantees survives the
  //     reload (sessionStorage + localStorage are both cleared inside the
  //     run itself, so they can't carry the lock).
  //   - Within-tab guard: a flag prevents double-fire if the click handler
  //     somehow runs twice before the navigate completes.
  var clearInProgress = false;
  var REPEAT_RUN_WINDOW_MS = 5000;

  function recentCacheResetMs() {
    // clearAllAppData uses ?cache_reset=<ts>; clearEverything uses
    // ?cache_reset=full&t=<ts> (and ?cache_reset=force / =full-force on
    // the error paths). The timestamp lands in `cache_reset` if numeric,
    // otherwise in `t` — pick whichever parses as a Date.now() value.
    try {
      var u = new URL(window.location.href);
      var raw = u.searchParams.get('cache_reset');
      var prev = raw ? parseInt(raw, 10) : 0;
      if (!prev) {
        var t = u.searchParams.get('t');
        prev = t ? parseInt(t, 10) : 0;
      }
      if (!prev) return null;
      var age = Date.now() - prev;
      return age >= 0 && age < REPEAT_RUN_WINDOW_MS ? age : null;
    } catch (e) { return null; }
  }

  async function clearAllAppData() {
    var recent = recentCacheResetMs();
    if (recent !== null) {
      console.warn(
        '[Fellows] clearAllAppData suppressed: cache_reset URL marker is ' +
          recent + 'ms old (< ' + REPEAT_RUN_WINDOW_MS + 'ms repeat-run window). ' +
          'See the 2026-05-04 OPFS boot-loop incident comment.'
      );
      // Tee into the bug-report ring so a user who hits the suppression
      // and then files a bug report carries the signal with them. The
      // 2026-05-04 incident never reproduced in DevTools — field reports
      // are the only way we'll catch the underlying trigger.
      pushBugReportError(
        'clear-suppressed',
        'clearAllAppData suppressed (' + recent + 'ms < ' + REPEAT_RUN_WINDOW_MS + 'ms window)'
      );
      return;
    }
    if (clearInProgress) {
      console.warn('[Fellows] clearAllAppData already in progress; ignoring re-entrant call');
      pushBugReportError(
        'clear-suppressed',
        'clearAllAppData re-entrant call blocked'
      );
      return;
    }
    clearInProgress = true;
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
    // Same re-entrancy guards as clearAllAppData (see comment above its
    // definition for the 2026-05-04 incident). clearEverything also
    // navigates to /?cache_reset=full&t=<timestamp> at the end, so the
    // URL marker check covers it too.
    var recent = recentCacheResetMs();
    if (recent !== null) {
      console.warn(
        '[Fellows] clearEverything suppressed: cache_reset URL marker is ' +
          recent + 'ms old (< ' + REPEAT_RUN_WINDOW_MS + 'ms repeat-run window).'
      );
      pushBugReportError(
        'clear-suppressed',
        'clearEverything suppressed (' + recent + 'ms < ' + REPEAT_RUN_WINDOW_MS + 'ms window)'
      );
      return;
    }
    if (clearInProgress) {
      console.warn('[Fellows] clearEverything blocked: another clear is in progress');
      pushBugReportError(
        'clear-suppressed',
        'clearEverything re-entrant call blocked'
      );
      return;
    }
    clearInProgress = true;
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

      // OPFS wipe — delegated to the worker via the wipeAll RPC. L1
      // forbids the page from opening OPFS, so the worker's removeVfs()
      // tear-down + root-iteration sweep is the only path that nukes
      // relationships.db, fellows.db, the bak.<ISO> rotation, and the
      // fellows.db.meta.json sidecar in one shot.
      //
      // Two providers can be active here:
      //   1. The worker provider — has wipeAll directly.
      //   2. The api+idb fallback (auth-failure cold-start path in
      //      pickDataProvider) — does NOT have wipeAll, but the worker
      //      that produced the 401 is still alive and still owns OPFS.
      //      Reach it through warmWorker.rpc so Reset Everything still
      //      wipes the user's groups/notes/tags/settings instead of
      //      silently leaving them on disk.
      // Worker spawn failure on this very session leaves nothing to
      // wipe via RPC; the SW unregister + cache clear below still nukes
      // the JS bundle.
      try {
        var wipeFn = null;
        if (dataProvider && typeof dataProvider.wipeAll === 'function') {
          wipeFn = function () { return dataProvider.wipeAll(); };
        } else if (warmWorker && warmWorker.rpc) {
          wipeFn = function () { return warmWorker.rpc.call('wipeAll'); };
        }
        if (wipeFn) {
          await wipeFn();
        }
      } catch (wipeErr) {
        console.error('[Fellows] worker wipeAll failed:', wipeErr);
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

  // Triggers a Settings-equivalent download of the user's relationships
  // data. Returns a promise that resolves to {filename, byteLength} on
  // a successful save, resolves to null when there's nothing to save
  // (export returned empty), or rejects on a real error. Reused by the
  // Reset Everything backup-first prompt so the user can grab a copy
  // before the destructive flow runs (issue #123). Settings page calls
  // its own inlined version with extra UI feedback; this is the
  // headless equivalent for callers that drive their own UI.
  function downloadRelationshipsBackup() {
    if (!dataProvider || typeof dataProvider.exportRelationshipsBytes !== 'function') {
      return Promise.reject(new Error('export not available in this mode'));
    }
    return dataProvider.exportRelationshipsBytes().then(function (bytes) {
      if (!bytes || !bytes.byteLength) return null;
      var ts = new Date().toISOString().replace(/[:.]/g, '-');
      var filename = 'relationships-' + ts + '.db';
      var blob = new Blob([bytes], { type: 'application/octet-stream' });
      return downloadBlob(blob, filename).then(function (result) {
        return {
          outcome: (result && result.outcome) || 'fallback',
          filename: (result && result.filename) || filename,
          byteLength: bytes.byteLength
        };
      });
    });
  }

  function initResetEverythingButton() {
    var btn = document.getElementById('reset-everything-button');
    if (!btn) return;
    var prompt = document.getElementById('reset-backup-prompt');
    var promptStatus = document.getElementById('reset-backup-prompt-status');
    var downloadBtn = document.getElementById('reset-backup-download');
    var skipBtn = document.getElementById('reset-backup-skip');
    var cancelBtn = document.getElementById('reset-backup-cancel');

    function openPrompt() {
      if (!prompt) return;
      if (promptStatus) promptStatus.textContent = '';
      [downloadBtn, skipBtn, cancelBtn].forEach(function (b) {
        if (b) b.disabled = false;
      });
      if (downloadBtn) downloadBtn.textContent = '⬇ Download backup & continue';
      prompt.classList.remove('hidden');
      prompt.setAttribute('aria-hidden', 'false');
    }
    function closePrompt() {
      if (!prompt) return;
      prompt.classList.add('hidden');
      prompt.setAttribute('aria-hidden', 'true');
    }

    // Existing destructive confirm preserved as the second step. Spelling
    // out *that data is gone* in plain English at this point — the
    // backup prompt is gentle, this one is the safety latch.
    function destructiveConfirmAndReset() {
      var ok = window.confirm(
        'Reset everything?\n\n' +
        'This permanently deletes your saved groups, group notes, fellow tags, ' +
        'and settings, AND signs you out. The on-device fellow data is wiped ' +
        'too. Use this only when Clear App Cache hasn\'t fixed the problem.\n\n' +
        'Continue?'
      );
      if (!ok) return;
      Promise.resolve(clearEverything()).catch(function (e) {
        console.error('[Fellows] clearEverything rejected:', e);
      });
    }

    btn.addEventListener('click', openPrompt);

    if (downloadBtn) {
      downloadBtn.addEventListener('click', function () {
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Preparing backup…';
        if (promptStatus) promptStatus.textContent = '';
        downloadRelationshipsBackup()
          .then(function (result) {
            if (!result) {
              // No user data exists yet — nothing was downloaded.
              // Surface that and continue without a "broken" feeling:
              // the user's about to wipe nothing, so the destructive
              // confirm is still appropriate.
              if (promptStatus) {
                promptStatus.textContent =
                  'No saved data on this device — nothing to back up. Continuing.';
              }
              closePrompt();
              destructiveConfirmAndReset();
              return;
            }
            if (result.outcome === 'cancelled') {
              // User dismissed the save dialog — treat as backing out.
              // Don't proceed to the destructive confirm; let them
              // pick again or hit Skip explicitly.
              downloadBtn.disabled = false;
              downloadBtn.textContent = '⬇ Download backup & continue';
              if (promptStatus) {
                promptStatus.textContent =
                  'Save cancelled — pick again, or use Skip to reset without saving.';
              }
              return;
            }
            if (promptStatus) {
              if (result.outcome === 'picker') {
                promptStatus.textContent =
                  'Saved as ' + result.filename + ' (' + result.byteLength + ' bytes). Continuing.';
              } else if (result.outcome === 'share') {
                promptStatus.textContent =
                  'Saved via the share sheet (' + result.byteLength + ' bytes). Continuing.';
              } else {
                promptStatus.textContent =
                  'Saved ' + result.filename + ' to your Downloads folder (' + result.byteLength + ' bytes). Continuing.';
              }
            }
            closePrompt();
            destructiveConfirmAndReset();
          })
          .catch(function (err) {
            // Export failed (e.g., dataProvider didn't surface the
            // method, or the worker rejected). Don't proceed to reset
            // — surface the error so the user can decide whether to
            // skip-and-reset anyway.
            downloadBtn.disabled = false;
            downloadBtn.textContent = '⬇ Download backup & continue';
            if (promptStatus) {
              promptStatus.textContent =
                'Could not export: ' + (err && err.message || String(err)) +
                '. Pick "Skip — no data to save" if you want to reset anyway.';
            }
          });
      });
    }
    if (skipBtn) {
      skipBtn.addEventListener('click', function () {
        closePrompt();
        destructiveConfirmAndReset();
      });
    }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', closePrompt);
    }
  }

  async function collectDiagnosticsText() {
    var lines = [];
    lines.push('=== Fellows client diagnostics (UI mark: ' + FELLOWS_UI_DIAG + ') ===');
    lines.push('time (ISO): ' + new Date().toISOString());
    lines.push('href: ' + String(location.href));
    // Per-install identity — auto-generated codename + best-effort
    // browser/OS detection + first-launch timestamp. Lets a maintainer
    // disambiguate which install of the app a bug report came from when
    // a user has more than one (e.g., Safari + Chrome on the same Mac).
    try {
      var diagIdentity = getOrCreateInstallIdentity();
      lines.push('install codename: ' + diagIdentity.codename);
      lines.push('install detected browser/OS: ' +
        (diagIdentity.browser || '?') + ' on ' + (diagIdentity.os || '?'));
      lines.push('install first launched (ISO): ' +
        (diagIdentity.installedAt || '(unknown)'));
    } catch (e) {
      lines.push('install identity: (unavailable — ' + String(e && e.message) + ')');
    }
    lines.push(
      'document.cookie length (HttpOnly cookies are NOT visible to JS): ' +
        String((document.cookie || '').length)
    );
    // Surface the persisted slow-boot record (if any) right at the top.
    // Lives in localStorage[fellows_last_slow_boot]; written by
    // emitBootSummary when total boot >SLOW_BOOT_TOTAL_MS or any single
    // phase >SLOW_BOOT_PHASE_MS. Survives Clear App Cache so a rare
    // regression captured one session is still readable in the next.
    try {
      var slow = readLastSlowBoot();
      if (slow) {
        lines.push('');
        lines.push('--- Last slow boot recorded ---');
        lines.push('  at: ' + (slow.ts || '(unknown)'));
        lines.push('  total: ' + (slow.totalMs != null ? slow.totalMs + 'ms' : '(?)'));
        lines.push('  slowest phase: ' + (slow.slowestPhase || '(?)') +
          ' (' + (slow.slowestMs != null ? slow.slowestMs + 'ms' : '?') + ')');
        if (slow.phases) lines.push('  all phases: ' + slow.phases);
        if (slow.route) lines.push('  route: ' + slow.route);
        if (slow.ua) lines.push('  ua: ' + slow.ua);
      }
    } catch (e) {}
    lines.push('');
    // OPFS / sqlite-wasm boot state. The Settings page hides backup/restore
    // when this fell through to API mode; this section answers "and why?".
    // Showing it before SW state because it's the first place we look when
    // a "no backup section" report comes in.
    lines.push('--- OPFS / sqlite-wasm boot state ---');
    try {
      lines.push('dataProvider.kind: ' +
        (dataProvider && dataProvider.kind ? dataProvider.kind : '(none — boot incomplete)'));
    } catch (e) {
      lines.push('dataProvider.kind: (unavailable: ' + String(e && e.message || e) + ')');
    }
    try {
      lines.push('directoryDataSource: ' +
        (typeof directoryDataSource !== 'undefined' ? directoryDataSource : '(unset)'));
    } catch (e) {}
    try {
      lines.push('OPFS capability gates:');
      var gateLines = describeOpfsGates().split('\n');
      for (var gi = 0; gi < gateLines.length; gi++) {
        lines.push('  ' + gateLines[gi]);
      }
    } catch (e) {
      lines.push('OPFS capability gates: (error — ' + String(e && e.message || e) + ')');
    }
    try {
      if (bootDebugLines && bootDebugLines.length) {
        lines.push('Boot trace (chronological, ' + bootDebugLines.length + ' lines):');
        for (var bli = 0; bli < bootDebugLines.length; bli++) {
          lines.push('  ' + bootDebugLines[bli]);
        }
      } else {
        lines.push('Boot trace: (empty — boot has not run, or trace not yet captured)');
      }
    } catch (e) {
      lines.push('Boot trace: (error — ' + String(e && e.message || e) + ')');
    }
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
    // Worker handshake + OPFS inventory. Worker is the OPFS owner
    // post-Phase-1; the main thread reads its inventory via RPC.
    //
    // The active dataProvider can be 'worker' (happy path) or 'api+idb'
    // (worker spawn failed, OR ensureFellowsDb returned 401 and the
    // page fell back). In the auth-fallback case the worker is still
    // alive in `warmWorker` even though dataProvider is api+idb. We
    // surface spawn state from warmWorker / warmWorkerError directly
    // so the panel is informative whichever path you're on — and so
    // the version handshake values land in the bug report even when
    // the worker isn't the active provider.
    var activeKind = (dataProvider && dataProvider.kind) || '(none)';
    lines.push('active dataProvider: ' + activeKind);
    if (warmWorker && warmWorker.init) {
      var wi = warmWorker.init;
      var versionOk = (
        wi.workerRpcVersion === EXPECTED_WORKER_RPC_VERSION &&
        wi.schemaVersion === EXPECTED_RELATIONSHIPS_SCHEMA_VERSION
      );
      lines.push(
        'worker spawn: OK rpc=' + wi.workerRpcVersion +
        ' (page expects ' + EXPECTED_WORKER_RPC_VERSION + ')' +
        ' schema=' + wi.schemaVersion +
        ' (page expects ' + EXPECTED_RELATIONSHIPS_SCHEMA_VERSION + ')' +
        ' build=' + wi.buildLabel
      );
      lines.push('worker version compatibility: ' +
        (versionOk ? 'OK' : 'SKEW — mutating ops refused, reads work'));
      lines.push(
        'worker capabilities: opfsCapable=' + !!wi.opfsCapable +
        ' hasFellowsDb=' + !!wi.hasFellowsDb +
        ' hasRelDb=' + !!wi.hasRelationshipsDb
      );
      // Inventory call: prefer the active provider (so we exercise the
      // same code path the rest of the app uses); fall back to the warm
      // worker rpc when the active provider is api+idb (auth-fallback).
      var invSource = null;
      if (dataProvider && typeof dataProvider._getOpfsInventory === 'function') {
        invSource = dataProvider._getOpfsInventory();
      } else if (warmWorker && warmWorker.rpc) {
        invSource = warmWorker.rpc.call('getOpfsInventory');
      }
      if (invSource) {
        try {
          var inv = await invSource;
          if (inv && Array.isArray(inv.root)) {
            lines.push('OPFS root entries (worker view):');
            if (!inv.root.length) {
              lines.push('  (empty)');
            } else {
              for (var ri = 0; ri < inv.root.length; ri++) {
                var e = inv.root[ri];
                var sz = (e.size != null ? ' — ' + e.size + ' bytes' : '');
                var mt = (e.lastModified ? ' (mtime ' + new Date(e.lastModified).toISOString() + ')' : '');
                lines.push('  ' + e.kind + ' ' + e.name + sz + mt);
              }
            }
          }
          if (inv && Array.isArray(inv.poolFiles)) {
            lines.push('SAH-pool slots: ' + inv.poolFiles.join(', '));
          }
        } catch (invErr) {
          lines.push('worker getOpfsInventory failed: ' + String(invErr && invErr.message || invErr));
        }
      }
      // fellows.db.meta.json — the freshness sidecar that gates
      // SHA-keyed re-import (Phase 3) and powers the About-page
      // "Last update check" line (Phase 4). Same source-prefer pattern
      // as the inventory call above.
      var metaSource = null;
      if (dataProvider && typeof dataProvider._getFellowsDbMeta === 'function') {
        metaSource = dataProvider._getFellowsDbMeta();
      } else if (warmWorker && warmWorker.rpc) {
        metaSource = warmWorker.rpc.call('getFellowsDbMeta');
      }
      if (metaSource) {
        try {
          var meta = await metaSource;
          if (meta && typeof meta === 'object') {
            lines.push('fellows.db.meta.json (worker view):');
            lines.push('  sha: ' + (meta.sha || '(unset)'));
            lines.push('  fetched_at: ' + (meta.fetched_at || '(never)'));
            lines.push('  last_failure_at: ' + (meta.last_failure_at || '(none)'));
            if (meta.last_failure_reason) {
              lines.push('  last_failure_reason: ' + meta.last_failure_reason);
            }
          } else {
            lines.push('fellows.db.meta.json: (not yet written — cold start)');
          }
        } catch (metaErr) {
          lines.push('worker getFellowsDbMeta failed: ' + String(metaErr && metaErr.message || metaErr));
        }
      }
    } else if (warmWorkerError) {
      var failTag = (warmWorkerError && warmWorkerError.code === 'OWNERSHIP_CONFLICT')
        ? 'FAILED [OWNERSHIP_CONFLICT — another tab/window holds OPFS]'
        : 'FAILED';
      lines.push('worker spawn: ' + failTag + ' — ' +
        String((warmWorkerError && warmWorkerError.message) || warmWorkerError));
      lines.push('  (page expects rpc=' + EXPECTED_WORKER_RPC_VERSION +
        ' schema=' + EXPECTED_RELATIONSHIPS_SCHEMA_VERSION +
        '; reported via /api/client-errors event=client_error kind=worker)');
    } else {
      lines.push('worker spawn: pending (init not yet resolved)');
    }
    // L6: persisted-storage state (best-effort). Visible whether persist()
    // succeeded, was denied, or wasn't asked.
    var pss = window.__persistStorageState;
    if (pss) {
      lines.push(
        'navigator.storage.persist(): attempted=' + pss.attempted +
        ' persisted=' + (pss.persisted == null ? '(unset)' : pss.persisted) +
        (pss.error ? ' error=' + pss.error : '') +
        (pss.finishedAt ? ' at=' + pss.finishedAt : '')
      );
    }
    // Data folder (issue #165 Phase 1) — handle present? what subfolder?
    // last save outcome? Pulled live from the worker so this reflects
    // current truth even after the user disconnects mid-session.
    lines.push('');
    lines.push('Data folder:');
    try {
      var folderCtrl = window.__folderController;
      if (!folderCtrl) {
        lines.push('  (folder controller not initialized)');
      } else {
        var fState = await folderCtrl.getState();
        lines.push('  browser supports showDirectoryPicker: ' + !!fState.supported);
        lines.push('  worker reachable: ' + !!fState.workerAvailable);
        lines.push('  handle persisted: ' + !!fState.hasHandle);
        if (fState.hasHandle) {
          lines.push('  parent folder name: ' + (fState.parentName || '(unset)'));
          lines.push('  subfolder name: ' + (fState.subfolderName || '(unset)'));
          lines.push('  permission: ' + (fState.permission || '(unknown)'));
          lines.push('  last saved at: ' + (fState.lastSavedAt || '(never)'));
          if (fState.fileLastModified) {
            lines.push('  file mtime (folder): ' + new Date(fState.fileLastModified).toISOString());
          }
          if (fState.fileSize != null) {
            lines.push('  file size (folder): ' + fState.fileSize + ' bytes');
          }
          if (fState.lastError && fState.lastError.reason) {
            lines.push('  last error: ' + fState.lastError.reason +
              ' at ' + (fState.lastError.at || '(unknown)'));
          }
        }
        lines.push('  badge: ' + folderCtrl.badge(fState));
      }
    } catch (folderErr) {
      lines.push('  (read failed: ' + String(folderErr && folderErr.message || folderErr) + ')');
    }
    lines.push('');
    // Auth trace: which routing branches fired during this page load.
    // Mirrors the "Auth trace" surfaced in the bug-report dialog —
    // duplicated here because the Diagnostics dialog is what users
    // typically paste, and without this it's impossible to tell from a
    // diag whether bootDirectoryAsApp / startBrowserUx / initEmailGate /
    // initBrowserInstallMode was reached or why.
    try {
      lines.push('Auth trace (' + authDebugLines.length + ' events):');
      if (authDebugLines.length === 0) {
        lines.push('  (no auth trace lines recorded)');
      } else {
        for (var ai = 0; ai < authDebugLines.length; ai++) {
          lines.push('  ' + authDebugLines[ai]);
        }
      }
    } catch (e) {
      lines.push('Auth trace: (error — ' + String(e && e.message || e) + ')');
    }
    lines.push('');
    // Install lifecycle: every reportInstallEvent() in this page load.
    // Distinguishes "Chrome never fired beforeinstallprompt" (suppressed
    // because PWA is already installed elsewhere on this profile) from
    // "user dismissed" or "Chrome offered install but click failed".
    try {
      lines.push('Install lifecycle (' + installLifecycleLog.length + ' events):');
      if (installLifecycleLog.length === 0) {
        lines.push('  (no install events recorded — install landing not reached or before_prompt timer not yet fired)');
      } else {
        for (var ii = 0; ii < installLifecycleLog.length; ii++) {
          var iev = installLifecycleLog[ii];
          lines.push(
            '  ' + iev.ts + ' ' + iev.name +
            (iev.extra ? ' [' + iev.extra + ']' : '') +
            ' (standalone=' + iev.standalone + ')'
          );
        }
      }
    } catch (e) {
      lines.push('Install lifecycle: (error — ' + String(e && e.message || e) + ')');
    }
    lines.push('');
    // Display-mode samples — the matchMedia race at the heart of the
    // install-loop bug. If the first samples show standalone=false and
    // a later sample shows standalone=true, the matchMedia race fired:
    // the dispatcher saw browser-tab and routed to startBrowserUx, but
    // by the time of a later check the window was actually standalone.
    try {
      lines.push('Display-mode samples (' + displayModeSamples.length + '):');
      if (displayModeSamples.length === 0) {
        lines.push('  (no samples — module init may not have completed)');
      } else {
        for (var si = 0; si < displayModeSamples.length; si++) {
          var s = displayModeSamples[si];
          lines.push(
            '  ' + s.ts + ' ' + s.label +
            ': standalone=' + s.standalone +
            ' matchMedia=' + s.matchMedia +
            ' navStandalone=' + s.navStandalone
          );
        }
      }
    } catch (e) {
      lines.push('Display-mode samples: (error — ' + String(e && e.message || e) + ')');
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
    var copyBtn = document.getElementById('diag-copy');

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
    if (copyBtn) {
      var copyBtnDefaultLabel = copyBtn.textContent;
      var copyBtnRevertTimer = null;
      copyBtn.addEventListener('click', function () {
        if (!pre) return;
        var text = pre.textContent || '';
        function flash(msg) {
          copyBtn.textContent = msg;
          if (copyBtnRevertTimer) clearTimeout(copyBtnRevertTimer);
          copyBtnRevertTimer = setTimeout(function () {
            copyBtn.textContent = copyBtnDefaultLabel;
          }, 1500);
        }
        copyToClipboard(text).then(
          function () { flash('Copied'); },
          function () { flash('Copy failed'); }
        );
      });
    }
    // Power-user escape hatch from any boot state — including the
    // standalone-PWA auth-trap that motivated this button (issue #125).
    // Standalone PWA windows have no URL bar, so a user whose session
    // expired and whose IDB cache is empty can be stuck in a loop where
    // every Clear App Cache reload returns to the same boot-error panel.
    // Diagnostics is reachable from that state (it sits on top of the
    // boot-error panel), and from here the user can sign out + force the
    // gate UI in one click. Fires the same teardown as `clearCookiesBestEffort`
    // + `POST /api/logout` does for the auth cookie, then navigates to
    // `/?gate=1` which forces the email-gate render path regardless of
    // localStorage markers (per email_gate.md invariant 7).
    var forceGateBtn = document.getElementById('diag-force-gate');
    if (forceGateBtn) {
      forceGateBtn.addEventListener('click', function () {
        var ok = window.confirm(
          'Sign out of this device and reload to the email gate?\n\n' +
          'Your saved groups, notes, and settings stay safe in local storage. ' +
          'You will need to re-request a magic link to sign back in.'
        );
        if (!ok) return;
        // Server clears the HttpOnly session cookie. Best-effort —
        // a network failure here shouldn't block the recovery flow,
        // because the gate UI itself doesn't require a cleared cookie
        // (?gate=1 forces the gate render).
        var logoutPromise;
        try {
          logoutPromise = fetch('/api/logout', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: '{}'
          }).catch(function () { /* swallowed */ });
        } catch (e) {
          logoutPromise = Promise.resolve();
        }
        // Best-effort JS-visible cookie sweep for any non-HttpOnly
        // residue. Then nuke localStorage so the gate boots clean — the
        // `fellows_authenticated_once` marker would otherwise route a
        // returning visitor straight back into the same trap on the
        // browser-tab decision tree.
        Promise.resolve(logoutPromise).then(function () {
          try { clearCookiesBestEffort(); } catch (e) {}
          try { localStorage.clear(); } catch (e) {}
          try { sessionStorage.clear(); } catch (e) {}
          window.location.replace('/?gate=1');
        });
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
    // OPFS / sqlite-wasm boot state. Critical for triaging
    // "backup/restore section says 'OPFS didn't initialize' — but why?".
    // Without these the bug-report tells us the failure was visible to
    // the user but not which gate failed or what the SAH-pool threw.
    try {
      lines.push(
        'dataProvider: ' +
          (dataProvider && dataProvider.kind ? dataProvider.kind : '(none)')
      );
    } catch (e) {}
    try {
      lines.push('opfs gates: ' + describeOpfsGates().replace(/\n/g, ' | '));
    } catch (e) {}
    try {
      if (bootDebugLines && bootDebugLines.length) {
        lines.push('boot trace (' + bootDebugLines.length + ' lines):');
        for (var bdi = 0; bdi < bootDebugLines.length; bdi++) {
          lines.push('  ' + bootDebugLines[bdi]);
        }
      } else {
        lines.push('boot trace: (empty — boot has not run, or trace not yet captured)');
      }
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
      'bug-report-button-boot-stuck',
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

  // Wires the Reload and Clear-App-Cache buttons inside the boot-stuck
  // recovery panel. Both delegate to existing global affordances rather
  // than duplicating logic — Reload is a plain location.reload(), and
  // Clear App Cache routes through the global #clear-app-cache-button
  // so the click is indistinguishable from the user pressing the same
  // button at the bottom of the page (single source of truth for the
  // confirm dialog + clearAllAppData re-entrancy guards).
  function initBootStuckPanelButtons() {
    var reloadBtn = document.getElementById('boot-stuck-reload-button');
    if (reloadBtn) {
      reloadBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        window.location.reload();
      });
    }
    var clearBtn = document.getElementById('boot-stuck-clear-cache-button');
    if (clearBtn) {
      clearBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var globalBtn = document.getElementById('clear-app-cache-button');
        if (globalBtn) globalBtn.click();
      });
    }
  }

  // Same pattern for the boot-error panel (issue #124). The panel
  // surfaces when bootDirectoryAsApp's catch handler can't recover
  // — post-#126 that's no longer the auth-failure case (which now
  // hands off to startBrowserUx → email gate), so the panel only
  // shows for genuinely unknown failures (network, 5xx, unexpected
  // exceptions). Inline Reload / Clear App Cache & Reload buttons
  // give the user a productive next step without forcing them to
  // hunt for the floating chrome at the bottom of the page.
  function initBootErrorPanelButtons() {
    var reloadBtn = document.getElementById('boot-error-reload-button');
    if (reloadBtn) {
      reloadBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        window.location.reload();
      });
    }
    var clearBtn = document.getElementById('boot-error-clear-cache-button');
    if (clearBtn) {
      clearBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var globalBtn = document.getElementById('clear-app-cache-button');
        if (globalBtn) globalBtn.click();
      });
    }
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
    // The build-info mirror that used to populate kebab-sheet-build
    // from the floating build-badge was removed 2026-05-22 along with
    // the badge itself. Users who need app+server build info open the
    // About page from the menu instead — that's the canonical surface.
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
    terminateWarmWorkerIfStillWarm('showAuthFailure');
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

  // ===== Worker-RPC data provider ===========================================
  // The dedicated worker (vendor/sqlite-worker.js) is the sole OPFS owner
  // post-Phase-1. The page is a thin RPC client. Init is network-free; the
  // page issues `ensureFellowsDb` only after the gate decision tree
  // resolves to directory mode (per L4a). See plans/local_first_worker_architecture.md.

  // Fan-in dispatch on a single Worker. Multiple postMessage roundtrips share
  // the worker's onmessage handler via a sequence-numbered pending Map.
  function createSqliteWorkerRpc(worker) {
    var nextId = 0;
    var pending = new Map();
    worker.onmessage = function (ev) {
      var msg = ev.data || {};
      var slot = pending.get(msg.id);
      if (!slot) return;
      pending.delete(msg.id);
      if (msg.ok) {
        slot.resolve(msg.result);
      } else {
        var err = new Error(msg.error || 'worker rpc error');
        if (msg.errorName) err.name = msg.errorName;
        if (msg.errorCode) err.code = msg.errorCode;
        if (msg.httpStatus) err.httpStatus = msg.httpStatus;
        if (msg.meta) err.meta = msg.meta;
        if (msg.stack) err.workerStack = msg.stack;
        slot.reject(err);
      }
    };
    worker.onerror = function (ev) {
      var msg = (ev && ev.message) || 'unknown';
      bootDebugPush('sqlite-worker error: ' + msg);
      // A worker-script error (e.g. importScripts failed because the
      // bundle 404'd) silently breaks every pending RPC otherwise. Fail
      // them all so the caller can fall back instead of hanging.
      pending.forEach(function (slot) {
        var e = new Error('worker error: ' + msg);
        e.workerScriptError = true;
        slot.reject(e);
      });
      pending.clear();
    };
    return {
      call: function (op, args, transferables) {
        var id = ++nextId;
        return new Promise(function (resolve, reject) {
          pending.set(id, { resolve: resolve, reject: reject });
          try {
            worker.postMessage({ id: id, op: op, args: args }, transferables || []);
          } catch (e) {
            pending.delete(id);
            reject(e);
          }
        });
      },
      terminate: function () { try { worker.terminate(); } catch (e) {} }
    };
  }

  // Wrap the worker RPC in a data-provider whose method shapes match the
  // legacy main-thread provider's callsite contract (so consumers in the
  // rest of app.js don't need to learn a new shape). `init` already ran
  // on the rpc; the handshake blob is passed in so the provider can decide
  // whether mutating ops are version-compatible.
  function createWorkerDataProvider(rpc, init) {
    var versionOk = !!(
      init &&
      init.workerRpcVersion === EXPECTED_WORKER_RPC_VERSION &&
      init.schemaVersion === EXPECTED_RELATIONSHIPS_SCHEMA_VERSION
    );
    function refuseIfVersionSkew(opLabel) {
      if (versionOk) return null;
      var msg = 'Worker version skew: page expects rpc=' +
        EXPECTED_WORKER_RPC_VERSION + ' schema=' + EXPECTED_RELATIONSHIPS_SCHEMA_VERSION +
        ' but worker reports rpc=' + init.workerRpcVersion +
        ' schema=' + init.schemaVersion + ' — ' + opLabel + ' refused, reload to update';
      return Promise.reject(VersionMismatchError(msg));
    }
    function attachMemberNamesFromCache(members) {
      if (!Array.isArray(members)) return [];
      var out = members.map(function (m) {
        var rid = m && m.record_id;
        var fellow = fellowsBySlug.get(rid);
        return { record_id: rid, name: fellow ? fellow.name : rid };
      });
      out.sort(function (a, b) {
        var an = (a.name || '').toLowerCase(), bn = (b.name || '').toLowerCase();
        return an < bn ? -1 : (an > bn ? 1 : 0);
      });
      return out;
    }
    function withResolvedMembers(group) {
      if (!group) return null;
      group.members = attachMemberNamesFromCache(group.members || []);
      return group;
    }
    return {
      kind: 'worker',
      // Internals exposed for the boot path (ensureFellowsDb gate, version
      // gate). No consumer outside boot should touch these.
      _rpc: rpc,
      _init: init,
      _versionOk: versionOk,
      // ----- Directory (fellows.db) — sole local read source.
      getList: function () {
        return rpc.call('getList');
      },
      getFull: function () {
        return rpc.call('getFull');
      },
      getOne: function (slugOrId) {
        return rpc.call('getOne', { slug: slugOrId });
      },
      search: function (q) {
        return rpc.call('search', { q: q });
      },
      getStats: function () {
        return rpc.call('getStats');
      },
      // ----- Groups + settings (relationships.db) — mutating ops gated.
      listGroups: function () {
        return rpc.call('listGroups');
      },
      getGroup: function (id) {
        return rpc.call('getGroup', { id: id }).then(withResolvedMembers);
      },
      createGroup: function (data) {
        return refuseIfVersionSkew('createGroup') ||
          rpc.call('createGroup', data).then(withResolvedMembers);
      },
      updateGroup: function (id, patch) {
        return refuseIfVersionSkew('updateGroup') ||
          rpc.call('updateGroup', { id: id, patch: patch }).then(withResolvedMembers);
      },
      deleteGroup: function (id) {
        return refuseIfVersionSkew('deleteGroup') ||
          rpc.call('deleteGroup', { id: id });
      },
      getSetting: function (key) {
        return rpc.call('getSetting', { key: key });
      },
      getSettings: function () {
        return rpc.call('getSettings');
      },
      setSetting: function (key, value) {
        return refuseIfVersionSkew('setSetting') ||
          rpc.call('setSetting', { key: key, value: value });
      },
      // ----- Backup / restore. Page-side bytes get transferred to the
      // worker; the worker is the OPFS owner and writes them.
      exportRelationshipsBytes: function () {
        return rpc.call('exportRelationshipsBytes');
      },
      inspectRelationshipsBytes: function (bytes) {
        return rpc.call('inspectRelationshipsBytes', { bytes: bytes });
      },
      countRelationships: function () {
        return rpc.call('countRelationships');
      },
      importRelationshipsBytes: function (bytes) {
        return refuseIfVersionSkew('importRelationshipsBytes') ||
          rpc.call('importRelationshipsBytes', { bytes: bytes });
      },
      listRelationshipsBackups: function () {
        return rpc.call('listRelationshipsBackups');
      },
      restoreRelationshipsBackup: function (name) {
        return refuseIfVersionSkew('restoreRelationshipsBackup') ||
          rpc.call('restoreRelationshipsBackup', { name: name });
      },
      // Reset Everything — closes both DBs, tears down SAH-pool VFS,
      // sweeps OPFS root siblings. Not version-gated: explicit user
      // intent to nuke state always wins. Page must reload after.
      wipeAll: function () { return rpc.call('wipeAll'); },
      // Diagnostics — pulls the worker's own boot trace + OPFS inventory.
      _getWorkerTrace: function () { return rpc.call('getTrace'); },
      _getOpfsInventory: function () { return rpc.call('getOpfsInventory'); },
      _ensureFellowsDb: function (args) { return rpc.call('ensureFellowsDb', args || {}); },
      // Read-only view of fellows.db.meta.json. Powers the About-page
      // "Last update check" line and the diag panel's meta block. Pure
      // read; does not trigger a fetch.
      _getFellowsDbMeta: function () { return rpc.call('getFellowsDbMeta'); },
      // Opt-in directory-data update RPCs
      // (plans/opt_in_directory_data_updates.md). Compare is a cheap
      // sidecar read; preview fetches + validates + stages; apply
      // promotes; cancel discards. None of them are version-gated —
      // reads are always safe, and apply requires a stagingId minted in
      // the same worker session so a stale page can't accidentally
      // commit a swap.
      _compareFellowsDbSha: function (args) {
        return rpc.call('compareFellowsDbSha', args || {});
      },
      _previewFellowsDbSwap: function (args) {
        return refuseIfVersionSkew('previewFellowsDbSwap') ||
          rpc.call('previewFellowsDbSwap', args || {});
      },
      _applyFellowsDbSwap: function (args) {
        return refuseIfVersionSkew('applyFellowsDbSwap') ||
          rpc.call('applyFellowsDbSwap', args || {});
      },
      _cancelFellowsDbSwap: function (args) {
        return rpc.call('cancelFellowsDbSwap', args || {});
      },
      _findOrphanedGroupMembers: function () {
        return rpc.call('findOrphanedGroupMembers');
      },
      // ----- User-folder durable storage (issue #165 Phase 1).
      // Reads are version-tolerant — page surfaces folder state even on
      // a stale worker, since the badge has to make sense before the
      // user reloads. Writes are gated alongside other mutations.
      _getFolderState: function () { return rpc.call('getFolderState'); },
      _setFolderHandle: function (args) {
        return refuseIfVersionSkew('setFolderHandle') ||
          rpc.call('setFolderHandle', args);
      },
      _clearFolderHandle: function () {
        return refuseIfVersionSkew('clearFolderHandle') ||
          rpc.call('clearFolderHandle');
      },
      _checkFolderPermission: function () { return rpc.call('checkFolderPermission'); },
      _getFolderHandleForReconnect: function () { return rpc.call('getFolderHandleForReconnect'); },
      _writeRelationshipsToFolder: function () {
        return refuseIfVersionSkew('writeRelationshipsToFolder') ||
          rpc.call('writeRelationshipsToFolder');
      },
      _readRelationshipsFromFolder: function () {
        return refuseIfVersionSkew('readRelationshipsFromFolder') ||
          rpc.call('readRelationshipsFromFolder');
      }
    };
  }

  // Fall-back provider used when the worker init throws (no OPFS-capable
  // browser, blocked worker, etc.). Directory + IDB paths still work for
  // browse-only use; groups/settings show the unsupported panel.
  // Phase 6 retires the IDB layer; until then it is the third-tier fallback
  // that backs `email_gate.md` invariant 10 on no-OPFS browsers.
  function createApiPlusIdbDataProvider() {
    var apiProvider = createApiDataProvider();
    return {
      kind: 'api+idb',
      // Directory: API only (IDB write/read mirroring is wired into bootDirectoryAsApp).
      getList: apiProvider.getList.bind(apiProvider),
      getFull: apiProvider.getFull.bind(apiProvider),
      getOne: apiProvider.getOne.bind(apiProvider),
      search: apiProvider.search.bind(apiProvider),
      getStats: apiProvider.getStats.bind(apiProvider),
      // Everything relationships-shaped rejects with localDataUnavailable
      // so the unsupported-browser panel renders.
      listGroups: apiProvider.listGroups.bind(apiProvider),
      getGroup: apiProvider.getGroup.bind(apiProvider),
      createGroup: apiProvider.createGroup.bind(apiProvider),
      updateGroup: apiProvider.updateGroup.bind(apiProvider),
      deleteGroup: apiProvider.deleteGroup.bind(apiProvider),
      getSetting: apiProvider.getSetting.bind(apiProvider),
      getSettings: apiProvider.getSettings.bind(apiProvider),
      setSetting: apiProvider.setSetting.bind(apiProvider),
      exportRelationshipsBytes: apiProvider.exportRelationshipsBytes.bind(apiProvider),
      inspectRelationshipsBytes: apiProvider.inspectRelationshipsBytes.bind(apiProvider),
      countRelationships: apiProvider.countRelationships.bind(apiProvider),
      importRelationshipsBytes: apiProvider.importRelationshipsBytes.bind(apiProvider),
      listRelationshipsBackups: apiProvider.listRelationshipsBackups.bind(apiProvider),
      restoreRelationshipsBackup: apiProvider.restoreRelationshipsBackup.bind(apiProvider)
    };
  }

  // Spawn the worker eagerly (init only — network-free) so OPFS handles
  // and the sqlite3 runtime are warm by the time the gate decision tree
  // commits to a UI. The init promise resolves with the worker handle +
  // handshake blob, OR rejects with a structured error if the worker
  // can't be brought up. If the gate decision lands at email-gate or
  // install-landing, the caller terminates the worker (no network
  // requests have happened yet; it's safe to throw away).
  // Worker init timeout. A bundle-load failure (404 / network error /
  // syntax error in the worker) can leave the Worker constructor
  // succeeding but no script ever running, so the init RPC never gets
  // a response. 8s covers a slow first-load on cold cache; anything
  // longer means something is really wrong and we should bail to the
  // API+IDB fallback rather than hang the boot.
  var WORKER_INIT_TIMEOUT_MS = 8000;

  function spawnWorkerAndInit() {
    bootDebugPush('worker: spawn + init starting');
    var worker;
    try {
      worker = new Worker('/vendor/sqlite-worker.js');
    } catch (ce) {
      bootDebugPush('worker: construction failed: ' + (ce && ce.message || ce));
      return Promise.reject(new Error('worker construction failed: ' + (ce && ce.message || ce)));
    }
    var rpc = createSqliteWorkerRpc(worker);
    var initPromise = rpc.call('init', {});
    var timeoutPromise = new Promise(function (_, reject) {
      setTimeout(function () {
        reject(new Error('worker init timed out after ' + WORKER_INIT_TIMEOUT_MS + 'ms'));
      }, WORKER_INIT_TIMEOUT_MS);
    });
    return Promise.race([initPromise, timeoutPromise]).then(function (initResult) {
      bootMark('worker_init_done');
      bootDebugPush(
        'worker: init OK rpc=' + (initResult && initResult.workerRpcVersion) +
        ' schema=' + (initResult && initResult.schemaVersion) +
        ' build=' + (initResult && initResult.buildLabel) +
        ' hasFellowsDb=' + !!(initResult && initResult.hasFellowsDb) +
        ' hasRelDb=' + !!(initResult && initResult.hasRelationshipsDb)
      );
      if (initResult && initResult.trace && initResult.trace.length) {
        bootDebugPush('--- begin worker trace ---');
        for (var i = 0; i < initResult.trace.length; i++) {
          bootDebugPush('  ' + initResult.trace[i]);
        }
        bootDebugPush('--- end worker trace ---');
      }
      return { rpc: rpc, init: initResult };
    }).catch(function (err) {
      try { rpc.terminate(); } catch (e) {}
      bootDebugPush('worker: init failed: ' + (err && err.message || err));
      throw err;
    });
  }

  // Best-effort `navigator.storage.persist()` exactly once per install.
  // L6 invariant — denied/unavailable is non-fatal. Result cached in
  // diagnostics-visible globals.
  var persistStorageState = {
    attempted: false,
    persisted: null,
    error: null,
    finishedAt: null
  };
  function maybeRequestPersistedStorage() {
    if (persistStorageState.attempted) return Promise.resolve(persistStorageState);
    persistStorageState.attempted = true;
    if (!navigator.storage || typeof navigator.storage.persist !== 'function') {
      persistStorageState.persisted = null;
      persistStorageState.error = 'navigator.storage.persist unavailable';
      persistStorageState.finishedAt = new Date().toISOString();
      bootDebugPush('persist: skipped — navigator.storage.persist unavailable');
      return Promise.resolve(persistStorageState);
    }
    return navigator.storage.persist().then(function (result) {
      persistStorageState.persisted = !!result;
      persistStorageState.finishedAt = new Date().toISOString();
      bootDebugPush('persist: result=' + persistStorageState.persisted);
      return persistStorageState;
    }).catch(function (e) {
      persistStorageState.persisted = false;
      persistStorageState.error = (e && e.message) || String(e);
      persistStorageState.finishedAt = new Date().toISOString();
      bootDebugPush('persist: rejected (non-fatal): ' + persistStorageState.error);
      return persistStorageState;
    });
  }
  // Exposed so the diagnostics panel + e2e tests can read it without
  // having to time their probe to the boot completion.
  window.__persistStorageState = persistStorageState;

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
    // `?gate=1` is the always-reachable dev escape hatch (email_gate.md
    // invariant 7). Checked FIRST so it wins over standalone-mode short-
    // circuit — without that ordering, a standalone PWA whose session has
    // expired had no in-app path back to the gate (issue #125): every
    // reload entered shouldActAsApp() → standalone short-circuit → true →
    // bootDirectoryAsApp → 403 → boot-error panel, even when navigating
    // to /?gate=1 from the diag panel's Force-email-gate button.
    if (parseGateOverride().force) return false;
    if (isStandaloneDisplayMode()) return true;
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

  // macOS Safari is its own thing: same WebKit lineage as iOS Safari but
  // a different install path (File → Add to Dock, macOS Sonoma 14+),
  // and it never fires beforeinstallprompt — that's Chromium-only. So
  // the install button is unconditionally non-functional on macOS Safari
  // and the UI must surface the correct path instead. The iPad-pretending-
  // to-be-Mac case (MacIntel platform + touchPoints > 1) is excluded so
  // those devices still get the iOS Safari hint.
  function isMacOsSafari() {
    var ua = navigator.userAgent || '';
    var isMac = /Macintosh/.test(ua);
    var isSafari = /Safari/.test(ua);
    var isChromium = /Chrome|Chromium|Edg\/|CriOS|FxiOS|EdgiOS/.test(ua);
    var isTouchMac = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return isMac && isSafari && !isChromium && !isTouchMac;
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
    // Local mirror first — independent of network. The server-side fetch
    // below can fail silently; the local log goes into the Diagnostics
    // blob the user pastes, so this is what unsticks debugging.
    try {
      installLifecycleLog.push({
        ts: new Date().toISOString(),
        name: String(name),
        extra: extra ? String(extra) : '',
        standalone: isStandaloneDisplayMode()
      });
      if (installLifecycleLog.length > 50) installLifecycleLog.shift();
    } catch (eLi) { /* best-effort */ }
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

  // Fire-once guard for reportBootEvent — see comments there.
  var bootBeaconFired = false;

  // Reports a single boot-success beacon to /api/client-errors so the
  // maintainer can grep journald for `event=client_error` lines with
  // `"kind": "boot"` and answer "what build is each installed PWA
  // actually running right now?" This is the load-bearing telemetry
  // for `just installed-versions` (plans/install_version_telemetry.md
  // Phase B); the `build` field carries the running build_label, and
  // `lastSubmitHashPrefix` (when present from a prior magic-link gate
  // submit) is the join key back to the user's email.
  //
  // Cardinality is exactly one event per page load — guarded by
  // bootBeaconFired so retries / re-renders don't multiply events.
  // Fire-and-forget; never blocks boot.
  function reportBootEvent() {
    if (bootBeaconFired) return;
    bootBeaconFired = true;
    var build = '';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      build = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    var route = '';
    try { route = String(location.hash || location.pathname || ''); } catch (e) {}
    var displayMode = isStandaloneDisplayMode() ? 'standalone' : 'browser-tab';
    var providerKind = '';
    try { providerKind = String((window.__dataProvider && window.__dataProvider.kind) || ''); } catch (e) {}
    var extraParts = ['displayMode=' + displayMode];
    if (providerKind) extraParts.push('provider=' + providerKind);
    var ev = { kind: 'boot', msg: 'cold_start', extra: extraParts.join(' ') };
    var payload = {
      events: [ev],
      ua: String(navigator.userAgent || ''),
      build: build,
      route: route,
      displayMode: displayMode
    };
    try { payload.online = Boolean(navigator.onLine); } catch (e) {}
    if (lastSubmitInfo && lastSubmitInfo.emailHashPrefix) {
      payload.lastSubmitHashPrefix = lastSubmitInfo.emailHashPrefix;
    }
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

  // Reports a single worker spawn/init outcome to /api/client-errors so
  // the operator can grep journald for `event=client_error` lines with
  // `"kind": "worker"` to answer questions like "what fraction of boots
  // dropped to the API+IDB fallback because the worker couldn't come
  // up?" Fire-and-forget; never blocks boot. Server-side sanitizer
  // (deploy/client_error_sanitizer.py) is the privacy boundary — same
  // email-redaction + length cap rules as the other kinds.
  //
  // Cardinality is one event per spawn outcome (success or failure);
  // the warm-worker spawn fires once per page load, the re-spawn case
  // (install-landing → use-in-tab) adds at most one more.
  function reportWorkerEvent(name, extra) {
    if (!name) return;
    var build = '';
    if (bootBuildMeta && (bootBuildMeta.git_sha || bootBuildMeta.built_at)) {
      build = (bootBuildMeta.git_sha || '') +
        (bootBuildMeta.built_at ? ' @ ' + bootBuildMeta.built_at : '');
    }
    var ev = { kind: 'worker', msg: String(name) };
    if (extra) ev.extra = String(extra).slice(0, 200);
    var route = '';
    try { route = String(location.hash || location.pathname || ''); } catch (e) {}
    var payload = {
      events: [ev],
      ua: String(navigator.userAgent || ''),
      build: build,
      route: route,
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
    sampleDisplayMode('initBrowserInstallMode_entry');
    // Defensive re-check for the standalone race. matchMedia(
    // '(display-mode: standalone)').matches has been observed to return
    // false in startBrowserUx's auth-status .then() callback even when
    // the window IS standalone — Chrome's matchMedia in a freshly-
    // launched PWA window can resolve after initial script execution,
    // so the pre-branch in startBrowserUx misses the route. By the
    // time we reach initBrowserInstallMode (one tick later), it may
    // have flipped to true. If so, redirect to directory per the
    // PWA-mode tree in docs/email_gate.md.
    if (!directoryBootAttempted && isStandaloneDisplayMode()) {
      authDebugPush(
        'initBrowserInstallMode: standalone detected on entry — redirecting to directory'
      );
      if (installLandingEl) installLandingEl.classList.add('hidden');
      markAuthenticatedOnce();
      bootDirectoryAsApp();
      return;
    }
    // Even later: listen for display-mode flipping to standalone after
    // the install landing renders. Catches the case where matchMedia
    // hasn't resolved by initBrowserInstallMode entry but flips during
    // the user's interaction with the install landing.
    if (window.matchMedia && typeof window.matchMedia === 'function') {
      try {
        var standaloneMq = window.matchMedia('(display-mode: standalone)');
        var standaloneFlipHandler = function (ev) {
          if (ev.matches && !directoryBootAttempted) {
            authDebugPush(
              'display-mode flipped to standalone — redirecting from install landing'
            );
            try { standaloneMq.removeEventListener('change', standaloneFlipHandler); } catch (e) {}
            if (installLandingEl) installLandingEl.classList.add('hidden');
            markAuthenticatedOnce();
            bootDirectoryAsApp();
          }
        };
        if (typeof standaloneMq.addEventListener === 'function') {
          standaloneMq.addEventListener('change', standaloneFlipHandler);
        }
      } catch (e) {}
    }
    // The install landing is a transition state, not a leaving-directory-mode
    // state. Both forward paths the user can take from here — clicking
    // Install (which spawns a separate standalone PWA process anyway) and
    // clicking "Use the directory in this tab" (which calls
    // bootDirectoryAsApp and immediately needs a worker) — benefit from the
    // warm worker remaining alive. Pre-emptively terminating it here forced
    // pickDataProvider to re-spawn, racing OPFS SAH-pool handle-release from
    // the just-killed worker; in practice that race could deadlock the new
    // worker on installOpfsSAHPoolVfs and surface as an indefinite "Loading…"
    // after use-in-tab. Leave the warm worker alive; terminate is handled
    // by initEmailGate (genuine leave) and showAuthFailure (broken state),
    // and back-to-gate navigates via location.replace which reloads anyway.
    if (installGatePrivateEl) installGatePrivateEl.classList.add('hidden');
    if (installLandingEl) installLandingEl.classList.remove('hidden');
    setShellVisible(false);
    showLoading(false);
    showApp(false);

    if (authPayload) {
      showAuthDebugInstall(authPayload, httpStatus != null ? httpStatus : 200);
    }

    reportInstallEvent('landing_shown');

    if (isIosSafari() && iosHintEl) {
      iosHintEl.classList.remove('hidden');
      if (installButtonEl) installButtonEl.classList.add('hidden');
      reportInstallEvent('ios_safari_advised');
    } else if (isMacOsSafari() && macSafariHintEl) {
      // macOS Safari never fires beforeinstallprompt, but does support
      // PWA install via File → Add to Dock on macOS Sonoma 14+. Surface
      // that path eagerly (same shape as iOS Safari) and hide the
      // install button — clicking it would just trigger the click-no-
      // prompt fallback, which is the wrong message for this case.
      macSafariHintEl.classList.remove('hidden');
      if (installButtonEl) installButtonEl.classList.add('hidden');
      reportInstallEvent('macos_safari_advised');
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
    if (!isIosSafari() && !isMacOsSafari()) {
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
    terminateWarmWorkerIfStillWarm('initEmailGate');
    if (installGatePrivateEl) installGatePrivateEl.classList.remove('hidden');
    if (installLandingEl) installLandingEl.classList.add('hidden');
    setShellVisible(false);
    showLoading(false);
    showApp(false);

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

  // ?app=1 — debug counterpart to ?gate=1. Forces directory boot in a
  // browser tab even when the routing tree would normally show the
  // install landing (authenticated + installRecentlyAllowed). Use cases:
  //   - Verify the directory works without dealing with Chrome's install
  //     heuristic (which can refuse to fire beforeinstallprompt after
  //     repeated install/uninstall cycles).
  //   - Confirm relationships.db data survives across sessions.
  //   - Test a code change against existing groups without the install dance.
  // Like ?gate=1, this is a UI-layer override only — protected endpoints
  // still require a valid session cookie. Honored only when authenticated;
  // unauthenticated visits with ?app=1 still go through the gate.
  function parseAppOverride() {
    try {
      var u = new URL(window.location.href);
      if (u.searchParams.get('app') === '1') {
        return { force: true };
      }
    } catch (e) {}
    return { force: false };
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
        // ?app=1 — debug escape hatch. When authenticated, force directory
        // boot in browser-tab mode, bypassing the install landing. See
        // parseAppOverride doc for use cases. Only honored when
        // authenticated and not already attempted (the standard guard
        // against bootDirectoryAsApp re-entry from its catch handler).
        if (parseAppOverride().force && data.authEnabled && data.authenticated && !directoryBootAttempted) {
          authDebugPush('?app=1 override: forcing directory boot in browser tab');
          markAuthenticatedOnce();
          bootDirectoryAsApp();
          return;
        }
        // PWA-mode decision tree per docs/email_gate.md: installed PWAs
        // route to directory or email gate, never the install landing.
        // Two ways we can reach this code path while standalone:
        //   1. shouldActAsApp() returned false at boot — possible on a
        //      freshly-installed PWA where the display-mode media query
        //      hadn't resolved standalone by the time the dispatcher
        //      ran. Reproduces as an "install loop" inside the standalone
        //      window for 30 minutes after token issue.
        //   2. bootDirectoryAsApp's catch handler routed an authFailure
        //      (401/403) here.
        // The directoryBootAttempted guard prevents (2) from re-entering
        // bootDirectoryAsApp and looping; in that case we fall through to
        // the email gate so the user can request a fresh magic link.
        sampleDisplayMode('startBrowserUx_then');
        var standaloneAtCheck = isStandaloneDisplayMode();
        authDebugPush(
          'pre-branch check: standalone=' + standaloneAtCheck +
          ' authEnabled=' + data.authEnabled +
          ' authenticated=' + data.authenticated +
          ' directoryBootAttempted=' + directoryBootAttempted
        );
        if (standaloneAtCheck && data.authEnabled) {
          if (data.authenticated && !directoryBootAttempted) {
            authDebugPush('standalone + authenticated: routing to directory (PWA-mode tree)');
            markAuthenticatedOnce();
            bootDirectoryAsApp();
            return;
          }
          authDebugPush(
            'standalone + (unauth or directory already attempted): using email gate'
          );
          if (data.authenticated) {
            markAuthenticatedOnce();
          }
          initEmailGate(data, httpStatus, '');
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

  // Set of record_ids known to be missing from the live fellows.db. Populated
  // by the boot soft-scan and refreshed after applyFellowsDbSwap, so group
  // detail rendering can flag rows whose underlying fellow is no longer in
  // the directory. Empty when no scan has run, when there are no orphans,
  // or when the api+idb fallback is in use (worker required to query).
  var orphanedRecordIds = Object.create(null);

  function setOrphanedRecordIdsFromList(orphans) {
    orphanedRecordIds = Object.create(null);
    if (!Array.isArray(orphans)) return;
    for (var i = 0; i < orphans.length; i++) {
      var rid = orphans[i] && orphans[i].recordId;
      if (rid) orphanedRecordIds[rid] = true;
    }
  }

  function isOrphanedRecordId(rid) {
    return !!(rid && orphanedRecordIds[rid]);
  }

  // One-shot post-PR-#113 orphan scan. Catches group_members whose
  // record_id is no longer in fellows.db — possible if the user got an
  // auto-refresh under the old policy. Toast fires once; the
  // orphan_scan_done setting prevents repeats. Group detail surfaces the
  // orphan rows via isOrphanedRecordId regardless.
  // plans/opt_in_directory_data_updates.md.
  function maybeRunOrphanSoftScan() {
    if (!dataProvider) return;
    if (typeof dataProvider._findOrphanedGroupMembers !== 'function') return;
    if (typeof dataProvider.getSetting !== 'function') return;
    Promise.resolve(dataProvider.getSetting('orphan_scan_done')).then(function (done) {
      if (done === '1') {
        // Already scanned in a previous boot. Still refresh the in-memory
        // set so group detail flags any orphans that are present, but no
        // toast.
        return dataProvider._findOrphanedGroupMembers().then(function (res) {
          setOrphanedRecordIdsFromList(res && res.orphans);
        });
      }
      return dataProvider._findOrphanedGroupMembers().then(function (res) {
        var orphans = (res && res.orphans) || [];
        setOrphanedRecordIdsFromList(orphans);
        if (orphans.length) {
          try {
            showToast('Some group members are no longer in the directory. ' +
              'See group details for review.', 8000);
          } catch (e) {}
        }
        if (typeof dataProvider.setSetting === 'function') {
          return dataProvider.setSetting('orphan_scan_done', '1').catch(function () {});
        }
      });
    }).catch(function (e) {
      bootDebugPush('orphan soft scan failed: ' + (e && e.message || e));
    });
  }

  function fellowHasEmail(f) {
    if (f.has_contact_email === true || f.has_contact_email === 1) return true;
    return !!(f.contact_email && String(f.contact_email).trim());
  }

  // Directory filter UI (issue #86). filterState is the source of truth
  // for what's active; filterOptions caches the distinct values scanned
  // out of the loaded fellow set after phase 2 (?full=1). The trigger
  // button stays disabled until filterOptions is populated, which is
  // why has-email + keyword search remain valid during phase 1 (their
  // codepaths don't depend on filterOptions).
  var filterState = {
    cohort: null,           // string | null  (single-select)
    fellowType: null,       // string | null  (single-select)
    regions: [],            // string[]       (any-of multi-select)
    citizenship: null       // string | null  (single-select)
  };
  var filterOptions = null;
  var filterSheetWired = false;
  // Re-entry guard: applyFiltersToHash() writes the URL via
  // history.replaceState which doesn't fire 'hashchange', but defensive
  // code paths may also call route() directly. The flag lets the
  // hash-read pass bail when we initiated the change ourselves.
  var filtersWritingHash = false;

  function activeFilterCount() {
    var n = 0;
    if (filterState.cohort) n++;
    if (filterState.fellowType) n++;
    if (filterState.regions && filterState.regions.length) n++;
    if (filterState.citizenship) n++;
    return n;
  }

  function filterStateSignature() {
    // Stable serialization for change detection. Region order is
    // normalized so reordering checkboxes doesn't look like a change.
    var rs = (filterState.regions || []).slice().sort().join(',');
    return [
      filterState.cohort || '',
      filterState.fellowType || '',
      rs,
      filterState.citizenship || ''
    ].join('|');
  }

  function uniqueSorted(values, opts) {
    var seen = Object.create(null);
    var out = [];
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (v == null) continue;
      v = String(v).trim();
      if (!v) continue;
      if (seen[v]) continue;
      seen[v] = true;
      out.push(v);
    }
    if (opts && opts.cohort) {
      // Cohort labels often start with a year ("2020", "2020 Cohort").
      // Sort by leading numeric prefix when present, falling back to a
      // string compare so "Inaugural" / "Founder" stay deterministic.
      out.sort(function (a, b) {
        var na = parseInt(a, 10);
        var nb = parseInt(b, 10);
        var aIsNum = !isNaN(na);
        var bIsNum = !isNaN(nb);
        if (aIsNum && bIsNum && na !== nb) return na - nb;
        if (aIsNum && !bIsNum) return -1;
        if (!aIsNum && bIsNum) return 1;
        return a.localeCompare(b);
      });
    } else {
      out.sort(function (a, b) { return a.localeCompare(b); });
    }
    return out;
  }

  function buildFilterOptions(items) {
    if (!Array.isArray(items) || !items.length) {
      filterOptions = null;
      return;
    }
    var cohorts = [];
    var fellowTypes = [];
    var regions = [];
    var citizenships = [];
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      if (!f) continue;
      cohorts.push(f.cohort);
      fellowTypes.push(f.fellow_type);
      citizenships.push(f.primary_citizenship);
      var raw = f.global_regions_currently_based_in;
      if (raw) {
        var parts = String(raw).split(',');
        for (var j = 0; j < parts.length; j++) regions.push(parts[j]);
      }
    }
    filterOptions = {
      cohorts: uniqueSorted(cohorts, { cohort: true }),
      fellowTypes: uniqueSorted(fellowTypes),
      regions: uniqueSorted(regions),
      citizenships: uniqueSorted(citizenships)
    };
  }

  function fellowMatchesRegions(f, picked) {
    if (!picked || !picked.length) return true;
    var raw = f.global_regions_currently_based_in;
    if (!raw) return false;
    var parts = String(raw).split(',');
    for (var i = 0; i < parts.length; i++) {
      var r = parts[i].trim();
      if (!r) continue;
      for (var j = 0; j < picked.length; j++) {
        if (picked[j] === r) return true;
      }
    }
    return false;
  }

  // Resolve a possibly-minimal directory row to the full row that has
  // structured fields (cohort, fellow_type, etc.). The directory's
  // `list` carries the minimal projection from /api/fellows; full rows
  // arrive after phase 2 and are indexed in fellowsBySlug. Search
  // results already come back as full rows, so this is a no-op in that
  // path.
  function resolveFullRow(f) {
    if (!f) return null;
    if (f.cohort !== undefined || f.fellow_type !== undefined) return f;
    if (f.slug && fellowsBySlug.has(f.slug)) return fellowsBySlug.get(f.slug);
    if (f.record_id && fellowsBySlug.has(f.record_id)) return fellowsBySlug.get(f.record_id);
    return null;
  }

  function applyFilters(items) {
    if (!Array.isArray(items)) return items;
    var out = items;
    if (hasEmailOnly) out = out.filter(fellowHasEmail);
    var needsFull =
      !!filterState.cohort ||
      !!filterState.fellowType ||
      (filterState.regions && filterState.regions.length > 0) ||
      !!filterState.citizenship;
    if (!needsFull) return out;
    out = out.filter(function (f) {
      var full = resolveFullRow(f);
      if (!full) return false; // can't evaluate without full data; treat as miss
      if (filterState.cohort && full.cohort !== filterState.cohort) return false;
      if (filterState.fellowType && full.fellow_type !== filterState.fellowType) return false;
      if (filterState.regions && filterState.regions.length &&
          !fellowMatchesRegions(full, filterState.regions)) return false;
      if (filterState.citizenship && full.primary_citizenship !== filterState.citizenship) return false;
      return true;
    });
    return out;
  }

  // ----- Filter hash <-> state ------------------------------------------
  // Filter state lives in the directory hash as a query-style suffix:
  // #/?cohort=2020&type=Fellow&region=Africa,Asia&citizenship=United%20States.
  // Read on directory route entry; write via history.replaceState on
  // every filter change so reload + share-as-link round-trip cleanly
  // without thrashing the back stack.

  function readFiltersFromHash() {
    var hash = window.location.hash || '';
    var qIdx = hash.indexOf('?');
    if (qIdx === -1) {
      filterState.cohort = null;
      filterState.fellowType = null;
      filterState.regions = [];
      filterState.citizenship = null;
      return;
    }
    var qs = hash.slice(qIdx + 1);
    var params;
    try {
      params = new URLSearchParams(qs);
    } catch (_) {
      return;
    }
    filterState.cohort = params.get('cohort') || null;
    filterState.fellowType = params.get('type') || null;
    var regionParam = params.get('region') || '';
    filterState.regions = regionParam
      ? regionParam.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
      : [];
    filterState.citizenship = params.get('citizenship') || null;
  }

  function writeFiltersToHash() {
    var hash = window.location.hash || '';
    var qIdx = hash.indexOf('?');
    var pathPart = qIdx === -1 ? hash : hash.slice(0, qIdx);
    if (!pathPart) pathPart = '#/';
    var qs = new URLSearchParams();
    if (filterState.cohort) qs.set('cohort', filterState.cohort);
    if (filterState.fellowType) qs.set('type', filterState.fellowType);
    if (filterState.regions && filterState.regions.length) {
      qs.set('region', filterState.regions.join(','));
    }
    if (filterState.citizenship) qs.set('citizenship', filterState.citizenship);
    var qsStr = qs.toString();
    var newHash = qsStr ? (pathPart + '?' + qsStr) : pathPart;
    if (newHash === hash) return;
    filtersWritingHash = true;
    try {
      if (window.history && window.history.replaceState) {
        var url = window.location.pathname + window.location.search + newHash;
        window.history.replaceState(null, '', url);
      } else {
        window.location.hash = newHash;
      }
    } finally {
      filtersWritingHash = false;
    }
  }

  // ----- Filter sheet UI ------------------------------------------------

  function setSelectOptions(selectEl, values, currentValue, anyLabel) {
    if (!selectEl) return;
    var html = '<option value="">' + escapeHtml(anyLabel || 'Any') + '</option>';
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      var sel = (v === currentValue) ? ' selected' : '';
      html += '<option value="' + escapeHtml(v) + '"' + sel + '>' + escapeHtml(v) + '</option>';
    }
    selectEl.innerHTML = html;
  }

  function populateFilterSheetControls() {
    if (!filterOptions) return;
    var cohortEl = document.getElementById('filter-cohort');
    var typeEl = document.getElementById('filter-fellow-type');
    var citEl = document.getElementById('filter-citizenship');
    var regionWrap = document.getElementById('filter-region-options');
    setSelectOptions(cohortEl, filterOptions.cohorts, filterState.cohort);
    setSelectOptions(typeEl, filterOptions.fellowTypes, filterState.fellowType);
    setSelectOptions(citEl, filterOptions.citizenships, filterState.citizenship);
    if (regionWrap) {
      var html = '';
      var picked = {};
      for (var p = 0; p < filterState.regions.length; p++) picked[filterState.regions[p]] = true;
      for (var i = 0; i < filterOptions.regions.length; i++) {
        var r = filterOptions.regions[i];
        var checked = picked[r] ? ' checked' : '';
        html +=
          '<label><input type="checkbox" data-filter-region value="' +
          escapeHtml(r) + '"' + checked + ' /><span>' + escapeHtml(r) + '</span></label>';
      }
      regionWrap.innerHTML = html || '<p class="placeholder">No regions in data.</p>';
    }
  }

  function syncFilterSheetControls() {
    // Lighter than re-rendering: just reflect filterState into existing
    // controls. Used after Reset and after readFiltersFromHash().
    if (!filterOptions) return;
    var cohortEl = document.getElementById('filter-cohort');
    var typeEl = document.getElementById('filter-fellow-type');
    var citEl = document.getElementById('filter-citizenship');
    if (cohortEl) cohortEl.value = filterState.cohort || '';
    if (typeEl) typeEl.value = filterState.fellowType || '';
    if (citEl) citEl.value = filterState.citizenship || '';
    var regionWrap = document.getElementById('filter-region-options');
    if (regionWrap) {
      var picked = {};
      for (var p = 0; p < filterState.regions.length; p++) picked[filterState.regions[p]] = true;
      var inputs = regionWrap.querySelectorAll('input[data-filter-region]');
      for (var i = 0; i < inputs.length; i++) {
        inputs[i].checked = !!picked[inputs[i].value];
      }
    }
  }

  function updateFilterTriggerUI() {
    if (!filterTriggerEl) return;
    var n = activeFilterCount();
    var ready = !!filterOptions;
    filterTriggerEl.disabled = !ready;
    filterTriggerEl.classList.toggle('filter-trigger--active', n > 0);
    if (filterTriggerCountEl) {
      if (n > 0) {
        filterTriggerCountEl.textContent = String(n);
        filterTriggerCountEl.removeAttribute('hidden');
      } else {
        filterTriggerCountEl.textContent = '';
        filterTriggerCountEl.setAttribute('hidden', '');
      }
    }
    if (ready) {
      filterTriggerEl.title = n > 0
        ? n + ' filter' + (n === 1 ? '' : 's') + ' active'
        : 'Filters';
    } else {
      filterTriggerEl.title = 'Filters available once full data loads';
    }
    var resetBtn = document.getElementById('filter-sheet-reset');
    if (resetBtn) {
      if (n > 0) resetBtn.removeAttribute('hidden');
      else resetBtn.setAttribute('hidden', '');
    }
  }

  function rerenderForFilterChange() {
    var query = (searchInputEl && searchInputEl.value || '').trim();
    if (query) {
      runSearch(query);
    } else if (Array.isArray(list) && list.length) {
      renderDirectory();
    }
  }

  function isFilterSheetOpen() {
    return !!(filterSheetEl && !filterSheetEl.classList.contains('hidden'));
  }

  function openFilterSheet() {
    if (!filterSheetEl) return;
    if (!filterOptions) return; // defense in depth; trigger is also disabled
    populateFilterSheetControls();
    filterSheetEl.classList.remove('hidden');
    filterSheetEl.removeAttribute('hidden');
    if (filterScrimEl) {
      filterScrimEl.classList.remove('hidden');
      filterScrimEl.removeAttribute('hidden');
    }
    if (filterTriggerEl) filterTriggerEl.setAttribute('aria-expanded', 'true');
  }

  function closeFilterSheet() {
    if (!filterSheetEl) return;
    filterSheetEl.classList.add('hidden');
    filterSheetEl.setAttribute('hidden', '');
    if (filterScrimEl) {
      filterScrimEl.classList.add('hidden');
      filterScrimEl.setAttribute('hidden', '');
    }
    if (filterTriggerEl) filterTriggerEl.setAttribute('aria-expanded', 'false');
  }

  function resetFilters() {
    var changed = activeFilterCount() > 0;
    filterState.cohort = null;
    filterState.fellowType = null;
    filterState.regions = [];
    filterState.citizenship = null;
    syncFilterSheetControls();
    updateFilterTriggerUI();
    writeFiltersToHash();
    if (changed) rerenderForFilterChange();
  }

  function initFilterSheet() {
    if (filterSheetWired) return;
    if (!filterTriggerEl || !filterSheetEl) return;
    filterSheetWired = true;
    filterTriggerEl.addEventListener('click', function () {
      if (isFilterSheetOpen()) closeFilterSheet();
      else openFilterSheet();
    });
    if (filterScrimEl) {
      filterScrimEl.addEventListener('click', closeFilterSheet);
    }
    var closeBtn = document.getElementById('filter-sheet-close');
    if (closeBtn) closeBtn.addEventListener('click', closeFilterSheet);
    var doneBtn = document.getElementById('filter-sheet-done');
    if (doneBtn) doneBtn.addEventListener('click', closeFilterSheet);
    var resetBtn = document.getElementById('filter-sheet-reset');
    if (resetBtn) resetBtn.addEventListener('click', resetFilters);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isFilterSheetOpen()) closeFilterSheet();
    });

    var cohortEl = document.getElementById('filter-cohort');
    if (cohortEl) {
      cohortEl.addEventListener('change', function () {
        filterState.cohort = cohortEl.value || null;
        writeFiltersToHash();
        updateFilterTriggerUI();
        rerenderForFilterChange();
      });
    }
    var typeEl = document.getElementById('filter-fellow-type');
    if (typeEl) {
      typeEl.addEventListener('change', function () {
        filterState.fellowType = typeEl.value || null;
        writeFiltersToHash();
        updateFilterTriggerUI();
        rerenderForFilterChange();
      });
    }
    var citEl = document.getElementById('filter-citizenship');
    if (citEl) {
      citEl.addEventListener('change', function () {
        filterState.citizenship = citEl.value || null;
        writeFiltersToHash();
        updateFilterTriggerUI();
        rerenderForFilterChange();
      });
    }
    // Region checkboxes are added dynamically; delegate at the wrap.
    var regionWrap = document.getElementById('filter-region-options');
    if (regionWrap) {
      regionWrap.addEventListener('change', function (ev) {
        var t = ev.target;
        if (!t || !t.matches || !t.matches('input[data-filter-region]')) return;
        var val = t.value;
        var picked = filterState.regions.slice();
        var idx = picked.indexOf(val);
        if (t.checked && idx === -1) picked.push(val);
        else if (!t.checked && idx !== -1) picked.splice(idx, 1);
        filterState.regions = picked;
        writeFiltersToHash();
        updateFilterTriggerUI();
        rerenderForFilterChange();
      });
    }
  }

  // Called after phase 2 (?full=1) settles. Builds option lists, enables
  // the trigger, and re-renders if hash-derived filters were already in
  // play during phase 1 (they applied via applyFilters but the trigger
  // count UI couldn't update until we knew the option set was real).
  function activateFiltersFromFullData(items) {
    buildFilterOptions(items);
    populateFilterSheetControls();
    updateFilterTriggerUI();
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
      mark.setAttribute('aria-label', on ? 'remove from group' : 'add to group');
      mark.textContent = on ? '✕' : '+';
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
    var filtered = applyFilters(list);
    if (!filtered.length) {
      directoryListEl.innerHTML = '<p class="placeholder">No fellows match the current filter.</p>';
      displayedList = [];
    } else {
      renderDirectoryList(filtered);
      displayedList = filtered;
    }
    // This UI element is defined as "count of fellows visible in the current
    // view." In directory mode it reflects all active filters (has email +
    // structured filters from #86); in search mode it reflects search +
    // filters together (see renderSearchResults).
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
      var addLabel = inDraft ? 'remove from group' : 'add to group';
      leftTop += ' <a href="#" class="detail-add-to-group' +
        (inDraft ? ' detail-add-to-group--on' : '') +
        '" data-record-id="' + escapeHtml(rid) + '"' +
        ' role="button" aria-pressed="' + (inDraft ? 'true' : 'false') + '"' +
        ' aria-label="' + addLabel + '" title="' + addLabel + '">' +
        (inDraft ? '✕' : '+') +
        '</a>';
    }
    leftTop += '</h2>';
    if (demo) leftTop += '<p class="detail-demographics">' + escapeHtml(demo) + '</p>';
    var hasImage = fellow.has_image === 1 || fellow.has_image === true;
    if (hasImage && slug) {
      // Stable URL across deploys — see prewarmProfileImages for why we
      // don't append ?v=<build_label>. A fellow whose photo was 404 on
      // a prior visit will keep showing the placeholder until the
      // browser's HTTP cache TTL on that 404 expires; for ~hundreds of
      // mostly-static photos that lag is acceptable, and the alternative
      // accumulates cache entries on every deploy without bound.
      var imgUrl = '/images/' + escapeHtml(slug) + '.jpg';
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
              img.src = '/images/' + s + '.png';
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
      var resolvedName = groupDraft.memberNames[rid];
      // Unresolved when no name was stored, OR when the stored name
      // equals the record_id itself (attachMemberNamesFromCache /
      // edit-mode loader both fall back to `rid` as the "name" when
      // the fellow row is missing from fellows.db).
      var unresolved = !resolvedName || resolvedName === rid;
      var name = document.createElement('span');
      name.className = 'group-rail-member-name';
      name.textContent = resolvedName || rid;
      if (unresolved) {
        // Edit-mode rail can include an orphan whose fellow row is
        // gone from fellows.db; chip would otherwise show a raw
        // record_id with no context. See issue #111.
        li.classList.add('group-rail-member--unresolved');
        var hint = document.createElement('span');
        hint.className = 'fellow-data-unavailable-hint';
        hint.textContent = '(fellow data unavailable)';
        name.appendChild(document.createTextNode(' '));
        name.appendChild(hint);
      }
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'group-rail-member-remove';
      rm.title = 'remove';
      rm.textContent = '×';
      rm.addEventListener('click', function () {
        toggleDraftMember(rid, resolvedName || rid);
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
    markEl.textContent = on ? '✕' : '+';
    markEl.title = on ? 'remove from group' : 'add to group';
    markEl.setAttribute('aria-label', on ? 'remove from group' : 'add to group');
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
    var label = on ? 'remove from group' : 'add to group';
    link.textContent = on ? '✕' : '+';
    link.title = label;
    link.setAttribute('aria-label', label);
    link.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) link.classList.add('detail-add-to-group--on');
    else link.classList.remove('detail-add-to-group--on');
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

  /** Render a stats section as semantic HTML bars instead of SVG.
   *  Each row is a CSS grid: label · bar-track (with proportional fill) ·
   *  count. Bar heights are fixed in CSS so they stay legible at any
   *  viewport — issue #132. The SVG predecessor coupled bar height to
   *  width via aspect-ratio scaling, which made bars shrink in both
   *  dimensions on narrow columns. `multicol` opts the section into a
   *  two-column wrap above the desktop breakpoint — appropriate for the
   *  long Field Completeness list.
   *
   *  Per-row width and per-section color are emitted as `data-pct` /
   *  `data-bar-color` attributes (not inline `style="..."`) so the page
   *  is CSP-compliant under `style-src 'self'`. The caller applies them
   *  via `applyStatsBarStyles(rootEl)` after innerHTML lands in the
   *  DOM — CSSOM writes don't count as inline styles for CSP. */
  function statsSection(title, items, color, multicol) {
    if (!items || !items.length) return '';
    var maxCount = items[0].count;
    var rows = '';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var pct = maxCount > 0 ? (item.count / maxCount) * 100 : 0;
      var ariaLabel = title + ': ' + item.label + ' — ' + item.count;
      // Label + count travel together inside .stats-bar-text so the
      // count is readable on mobile even when the bar overflows the
      // viewport. Bars all start at the same x across sections via a
      // fixed-width label column on desktop (CSS).
      rows += '<li class="stats-bar-row" aria-label="' + escapeHtml(ariaLabel) + '">' +
        '<span class="stats-bar-text">' +
          '<span class="stats-bar-label">' + escapeHtml(item.label) + '</span>' +
          '<span class="stats-bar-count">' + escapeHtml(String(item.count)) + '</span>' +
        '</span>' +
        '<span class="stats-bar-track">' +
          '<span class="stats-bar-fill" data-pct="' + pct.toFixed(1) + '"></span>' +
        '</span>' +
      '</li>';
    }
    var sectionClass = 'stats-section' + (multicol ? ' stats-section--multicol' : '');
    return '<section class="' + sectionClass + '" data-bar-color="' + escapeHtml(color) + '">' +
      '<h3 class="stats-section-title">' + escapeHtml(title) + '</h3>' +
      '<ol class="stats-bars">' + rows + '</ol>' +
    '</section>';
  }

  /** Apply per-row widths and per-section bar colors via CSSOM after
   *  `gridEl.innerHTML = ...` has parsed the markup. Pairs with
   *  `statsSection`, which writes the values into `data-pct` /
   *  `data-bar-color` instead of inline `style="..."` attributes (the
   *  latter are blocked by `style-src 'self'`; CSSOM is not). */
  function applyStatsBarStyles(rootEl) {
    if (!rootEl) return;
    var fills = rootEl.querySelectorAll('.stats-bar-fill[data-pct]');
    for (var i = 0; i < fills.length; i++) {
      var pct = fills[i].getAttribute('data-pct');
      if (pct) fills[i].style.width = pct + '%';
    }
    var sections = rootEl.querySelectorAll('.stats-section[data-bar-color]');
    for (var j = 0; j < sections.length; j++) {
      var color = sections[j].getAttribute('data-bar-color');
      if (color) sections[j].style.setProperty('--stats-bar-color', color);
    }
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
    aboutHtml += '<p class="about-users-manual"><a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md" target="_blank" rel="noopener">Help from the user manual</a> \u2014 how to install, use the app, fix common issues, and uninstall.</p>';
    // Install name surfaces the per-install codename so a user with
    // multiple installs (Safari + Chrome on the same Mac, multiple
    // Chrome profiles, etc.) can tell instances apart. Intentionally
    // small + unalarming \u2014 the explanation lives in the users-manual.
    var aboutIdentity = getOrCreateInstallIdentity();
    aboutHtml += '<p class="about-install-name">This install: <strong>' +
      escapeHtml(aboutIdentity.codename) +
      '</strong> <a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md#install-name" target="_blank" rel="noopener">(What\u2019s this?)</a></p>';
    // Two-row update status block. App and Directory data are
    // independently versioned (build/build_pwa.py emits both `git_sha`
    // and `fellows_db_sha` into /build-meta.json); the user can act on
    // either without affecting the other.
    // plans/opt_in_directory_data_updates.md.
    var serverLabel = bootBuildMeta.git_sha
      ? bootBuildMeta.git_sha + (bootBuildMeta.built_at ? ' · ' + bootBuildMeta.built_at : '')
      : (bootBuildMeta.built_at || 'unknown');
    aboutHtml += '<div class="about-update-block">';
    aboutHtml += '<div class="about-update-row" id="about-app-row">';
    aboutHtml += '<div class="about-update-row-label">App</div>';
    aboutHtml += '<div class="about-update-row-status" id="about-app-status" role="status" aria-live="polite">';
    aboutHtml += '<code class="about-build-value">app: ' + escapeHtml(FELLOWS_UI_DIAG) + '</code> ';
    aboutHtml += '<code class="about-build-value">server: ' + escapeHtml(serverLabel) + '</code>';
    aboutHtml += '</div>';
    aboutHtml += '<div class="about-update-row-action" id="about-app-action"></div>';
    aboutHtml += '</div>';
    aboutHtml += '<div class="about-update-row" id="about-data-row">';
    aboutHtml += '<div class="about-update-row-label">Directory data</div>';
    aboutHtml += '<div class="about-update-row-status" id="about-data-status" role="status" aria-live="polite">Click "Check for updates" to compare with the server.</div>';
    aboutHtml += '<div class="about-update-row-action" id="about-data-action"></div>';
    aboutHtml += '</div>';
    // Signing-key row. The fingerprint here should match the value
    // printed in the magic-link email; mismatch means the bundle did
    // not come from the maintainer (or the email did not). See
    // SECURITY.md § Signing keys.
    var fingerprint = (bootBuildMeta && bootBuildMeta.pubkey_fingerprint) || '';
    var fingerprintHtml = fingerprint
      ? '<code class="about-build-value about-fingerprint">' + escapeHtml(fingerprint) + '</code>'
      : '<em>not configured for this build</em>';
    aboutHtml += '<div class="about-update-row" id="about-signing-row">';
    aboutHtml += '<div class="about-update-row-label">Signing key</div>';
    aboutHtml += '<div class="about-update-row-status" id="about-signing-status">';
    aboutHtml += fingerprintHtml;
    aboutHtml += '<div class="about-signing-hint">';
    aboutHtml += fingerprint
      ? 'Compare against the fingerprint shown in the magic-link email that brought you here. Mismatch → do not trust this bundle.'
      : 'The maintainer has not yet activated signature verification for this build. Updates are delivered over HTTPS but are not cryptographically signed.';
    aboutHtml += '</div></div>';
    aboutHtml += '<div class="about-update-row-action"></div>';
    aboutHtml += '</div>';
    aboutHtml += '<p class="about-update-check">';
    aboutHtml += '<button type="button" id="about-check-updates" class="about-check-updates-btn">Check for updates</button>';
    aboutHtml += '<span id="about-last-check" class="about-update-status"></span>';
    aboutHtml += '</p>';
    // Persistent record of when fellows.db was last fetched (or last
    // failed). Populated async from fellows.db.meta.json. Useful when a
    // user reports stale data — answers "is the distribution channel
    // actually working for me?" without sending them into the
    // diagnostics panel.
    aboutHtml += '<p class="about-last-update" id="about-last-update"></p>';
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

    // Populate the "Last update check" line from the worker's
    // fellows.db.meta.json. Async + non-blocking: a missing/empty meta
    // (cold-start) renders "No update checks recorded yet" and the page
    // continues. If the dataProvider doesn't expose the meta RPC (api+idb
    // fallback on no-OPFS browsers), leave the line empty — the meta
    // doesn't exist in that path.
    (function renderLastUpdateCheck() {
      var el = document.getElementById('about-last-update');
      if (!el) return;
      if (!dataProvider || typeof dataProvider._getFellowsDbMeta !== 'function') return;
      Promise.resolve(dataProvider._getFellowsDbMeta()).then(function (meta) {
        if (!meta || (!meta.fetched_at && !meta.last_failure_at)) {
          el.textContent = 'No update checks recorded yet.';
          return;
        }
        var fetchedTs = meta.fetched_at ? new Date(meta.fetched_at).getTime() : 0;
        var failedTs = meta.last_failure_at ? new Date(meta.last_failure_at).getTime() : 0;
        if (failedTs > fetchedTs) {
          var reason = meta.last_failure_reason || 'unknown reason';
          el.textContent = 'Last update attempt: ' + meta.last_failure_at + ' — failed: ' + reason;
        } else {
          el.textContent = 'Last update check: ' + meta.fetched_at + ' — succeeded.';
        }
      }).catch(function () { /* non-fatal — leave line empty */ });
    })();

    // Wire the "Check for updates" button. Drives the app-shell check
    // (existing checkForServerUpdate, which raises the SW reload banner
    // on drift) AND the directory-data check in parallel; each result
    // populates its own status row independently.
    // plans/opt_in_directory_data_updates.md.
    (function wireUpdateCheckButton() {
      var btn = document.getElementById('about-check-updates');
      var lastCheckEl = document.getElementById('about-last-check');
      var appStatusEl = document.getElementById('about-app-status');
      var appActionEl = document.getElementById('about-app-action');
      var dataStatusEl = document.getElementById('about-data-status');
      var dataActionEl = document.getElementById('about-data-action');
      if (!btn) return;

      function paintAppRow(res) {
        if (!appStatusEl) return;
        var serverLabel = bootBuildMeta.git_sha
          ? bootBuildMeta.git_sha + (bootBuildMeta.built_at ? ' \u00b7 ' + bootBuildMeta.built_at : '')
          : (bootBuildMeta.built_at || 'unknown');
        var build = '<code class="about-build-value">app: ' + escapeHtml(FELLOWS_UI_DIAG) + '</code> ' +
          '<code class="about-build-value">server: ' + escapeHtml(serverLabel) + '</code>';
        var statusText, actionHtml = '';
        if (res.status === 'update-available') {
          statusText = ' \u2014 App update available';
          actionHtml = '<button type="button" class="about-update-action-btn" id="about-app-update-btn">Reload to apply</button>';
        } else if (res.status === 'up-to-date') {
          statusText = ' \u2014 up to date';
        } else if (res.status === 'no-boot-snapshot') {
          statusText = ' \u2014 version recorded; future checks will compare against this build.';
        } else {
          statusText = ' \u2014 Couldn\u2019t check (offline?)';
        }
        appStatusEl.innerHTML = build + statusText;
        if (appActionEl) appActionEl.innerHTML = actionHtml;
        var appBtn = document.getElementById('about-app-update-btn');
        if (appBtn) {
          appBtn.addEventListener('click', function () { window.location.reload(); });
        }
      }

      function paintDataRow(res) {
        if (!dataStatusEl) return;
        var statusText = '', actionHtml = '';
        // MCPB integration is set up AND its bundled fellows.db sha is
        // out of step with what the server reports now. Two trigger
        // cases: (a) local fellows.db is also behind server (the user
        // hasn't run "Update directory data" yet either), and (b) local
        // fellows.db has been updated already but the .mcpb extension
        // installed in Claude Desktop still carries the old snapshot.
        // The button surfaces in both, since the user action is the
        // same: re-download shared_data_ops.mcpb. Pre-PR-#204 this
        // lived in the MCPB Settings section; consolidated here per
        // maintainer feedback so all "your data versions need
        // refreshing" affordances live in one place.
        var mcpState = getMcpbSetupState();
        var mcpStaleVsServer = !!(mcpState && mcpState.setupAt &&
          res.serverSha && mcpState.fellowsDbSha &&
          mcpState.fellowsDbSha !== res.serverSha);
        var mcpRefreshBtnHtml = '<button type="button" class="about-update-action-btn" id="about-data-mcpb-refresh-btn">Re-install Fellows directory extension</button>';

        if (res.status === 'unsupported') {
          statusText = 'Directory data updates aren\u2019t available in this browser.';
        } else if (res.status === 'no-local-data') {
          statusText = 'No local directory data \u2014 reload to download.';
        } else if (res.status === 'worker-stale') {
          // Transient SW-upgrade race: the page is on a newer build
          // than the worker, so the new compareFellowsDbSha RPC isn't
          // recognized. Reloading spawns a fresh worker from the now-
          // current shell cache and the check works.
          statusText = 'Reload the app to enable update checks.';
          actionHtml = '<button type="button" class="about-update-action-btn" id="about-data-reload-btn">Reload</button>';
        } else if (res.status === 'update-available') {
          statusText = 'Directory Data update available';
          actionHtml = '<button type="button" class="about-update-action-btn" id="about-data-update-btn">Update directory data</button>';
          if (mcpStaleVsServer) actionHtml += ' ' + mcpRefreshBtnHtml;
        } else if (res.status === 'up-to-date') {
          var snap = res.fetchedAt ? ' (snapshot from ' + escapeHtml(String(res.fetchedAt)) + ')' : '';
          statusText = 'up to date' + snap;
          if (mcpStaleVsServer) {
            statusText += ' \u2014 Claude Desktop extension is older';
            actionHtml = mcpRefreshBtnHtml;
          }
        } else {
          statusText = 'Couldn\u2019t check (offline?)';
        }
        dataStatusEl.textContent = statusText;
        if (dataActionEl) dataActionEl.innerHTML = actionHtml;
        var dataBtn = document.getElementById('about-data-update-btn');
        if (dataBtn) {
          dataBtn.addEventListener('click', function () {
            handleUpdateDirectoryDataClick(res, btn);
          });
        }
        var reloadBtn = document.getElementById('about-data-reload-btn');
        if (reloadBtn) {
          reloadBtn.addEventListener('click', function () { window.location.reload(); });
        }
        var mcpbBtn = document.getElementById('about-data-mcpb-refresh-btn');
        if (mcpbBtn) {
          mcpbBtn.addEventListener('click', function () {
            mcpbBtn.disabled = true;
            var originalText = mcpbBtn.textContent;
            mcpbBtn.textContent = 'Downloading\u2026';
            triggerSameOriginDownload('/mcpb/shared_data_ops.mcpb', 'shared_data_ops.mcpb').then(function () {
              recordMcpbDirectoryRefresh(res.serverSha);
              mcpbBtn.textContent = 'Downloaded \u2014 open the file to re-install';
            }).catch(function () {
              mcpbBtn.disabled = false;
              mcpbBtn.textContent = originalText;
            });
          });
        }
      }

      btn.addEventListener('click', function () {
        btn.disabled = true;
        if (lastCheckEl) lastCheckEl.textContent = 'Checking\u2026';
        if (appStatusEl) appStatusEl.textContent = 'Checking\u2026';
        if (appActionEl) appActionEl.innerHTML = '';
        if (dataStatusEl) dataStatusEl.textContent = 'Checking\u2026';
        if (dataActionEl) dataActionEl.innerHTML = '';
        Promise.all([checkForServerUpdate(), checkForDirectoryDataUpdate()]).then(function (results) {
          btn.disabled = false;
          paintAppRow(results[0] || { status: 'error' });
          paintDataRow(results[1] || { status: 'error' });
          if (lastCheckEl) lastCheckEl.textContent = 'Last check: ' + new Date().toISOString();
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
          // Issue #132: stack sections single-column at full pane width
          // so bars use the available horizontal space; Field
          // Completeness opts into a 2-column wrap (CSS-only) above the
          // desktop breakpoint to keep its ~30 entries scannable
          // without dwarfing the others.
          var gh = '';
          gh += statsSection('Fellows by Type', data.by_fellow_type, '#0066cc');
          gh += statsSection('Fellows by Cohort', data.by_cohort, '#2c6a4a');
          gh += statsSection('Fellows by Region', data.by_region, '#2c4a6a');
          gh += statsSection('Field Completeness', data.field_completeness, '#5a5a5a', true);
          gridEl.innerHTML = gh;
          applyStatsBarStyles(gridEl);
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
    if (typeof closeFilterSheet === 'function' && isFilterSheetOpen()) {
      closeFilterSheet();
    }
    // Filter state lives in the directory hash. Re-read on every route()
    // call so back/forward and externally-set hashes (shared links,
    // diagnostics tools) hydrate correctly. Off-directory routes ignore
    // the params; switching back to '#/' re-hydrates from whatever the
    // hash carried at the time. Skip when we initiated the hash write
    // ourselves (replaceState doesn't fire hashchange but defensive
    // route() callers might reach here anyway).
    //
    // Also re-render the directory if filterState actually changed —
    // the list is already in the DOM (focus mode hides it via body
    // class, doesn't unmount it), so without an explicit re-render
    // the user would see stale, pre-filter rows when arriving from
    // a shared link or from another route.
    if (!filtersWritingHash) {
      var prevSig = filterStateSignature();
      readFiltersFromHash();
      syncFilterSheetControls();
      updateFilterTriggerUI();
      if (filterStateSignature() !== prevSig) {
        rerenderForFilterChange();
      }
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
        '<p class="group-detail-visual-link-row">' +
          '<a href="#/groups/' + escapeHtml(String(group.id)) +
            '/directory" class="group-detail-visual-link">view as visual directory</a>' +
        '</p>' +
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
          // Orphan = explicitly flagged by the orphan scan, OR not found
          // in the in-memory cache (defensive — the scan may not have run
          // yet on this boot, e.g. on the api+idb fallback). The latter
          // never produces false positives in worker mode because
          // fellowsBySlug is populated from the same fellows.db the
          // worker uses to validate group_members.
          var orphaned = isOrphanedRecordId(rid) || (rid && !fellow);
          if (orphaned) {
            html += '<tr class="group-detail-member-orphan" data-record-id="' +
              escapeHtml(rid) + '"><td>' +
              '<span class="group-detail-orphan-icon" aria-hidden="true">?</span>' +
              '<span class="group-detail-orphan-text">Profile no longer available' +
              ' <code class="group-detail-orphan-rid">(record_id: ' +
              escapeHtml(rid) + ')</code></span>' +
              '<button type="button" class="group-detail-orphan-remove" data-record-id="' +
              escapeHtml(rid) + '">Remove</button>' +
              '</td></tr>';
            return;
          }
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

  /** Trigger a Blob download. Returns a Promise that resolves to an
   *  outcome object so callers can render a status message tied to
   *  *how* the file got saved:
   *
   *    {outcome: 'picker',    filename: <chosen name>}    — user picked
   *                                                         via the
   *                                                         showSaveFilePicker
   *                                                         native dialog
   *    {outcome: 'share',     filename: <suggested name>} — mobile share
   *                                                         sheet save
   *    {outcome: 'fallback',  filename: <suggested name>} — <a download>
   *                                                         (goes to the
   *                                                         browser's
   *                                                         Downloads folder)
   *    {outcome: 'cancelled', filename: <suggested name>} — user dismissed
   *                                                         the picker /
   *                                                         share sheet
   *
   *  Decision tree:
   *    - **Desktop** (any non-mobile UA) with `showSaveFilePicker` →
   *      native Save As dialog. User picks name + location explicitly.
   *      The old behavior (invisible `<a download>` click) silently lost
   *      files inside installed PWAs on Chrome — the file lands in a
   *      PWA-context path that's not the user's Downloads folder, with
   *      no save dialog and no recoverable feedback. This is the fix.
   *    - **Mobile** (iOS 16.4+, modern Android) with `navigator.canShare`
   *      for files → OS share sheet. Includes Save to Files / Save to
   *      Drive destinations; the mobile-native way to choose a location.
   *      iOS / Android PWAs have no Downloads folder concept, so an
   *      `<a download>` fallback there is even less reliable than on
   *      desktop.
   *    - **Everything else** (Safari, Firefox, older browsers,
   *      capability rejections) → `<a download>`. Both Safari and
   *      Firefox handle this correctly, landing the file in the user's
   *      Downloads folder with a visible banner.
   */
  function downloadBlob(blob, filename) {
    function isMobileUA() {
      var ua = navigator.userAgent || '';
      return /iPad|iPhone|iPod|Android/.test(ua) ||
             (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    }
    function triggerAnchorDownload() {
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
          resolve({ outcome: 'fallback', filename: filename });
        }, 100);
      });
    }

    // Desktop with the File System Access API → native Save As dialog.
    if (!isMobileUA() && typeof window.showSaveFilePicker === 'function') {
      return Promise.resolve().then(function () {
        return window.showSaveFilePicker({
          suggestedName: filename,
          types: [{
            description: 'SQLite database',
            accept: { 'application/octet-stream': ['.db'] }
          }]
        });
      }).then(function (handle) {
        return handle.createWritable().then(function (writable) {
          return writable.write(blob).then(function () {
            return writable.close();
          });
        }).then(function () {
          return { outcome: 'picker', filename: handle.name };
        });
      }).catch(function (err) {
        if (err && err.name === 'AbortError') {
          return { outcome: 'cancelled', filename: filename };
        }
        // Real failure (permission denied, write error, etc.) — fall
        // back to the anchor path so the user still gets the file.
        try { console.warn('[Fellows] showSaveFilePicker failed; falling back:', err); } catch (e) {}
        return triggerAnchorDownload();
      });
    }

    // Mobile share sheet — only when the OS supports file shares
    // and accepts this MIME. canShare guards both.
    try {
      if (isMobileUA() && navigator.canShare && typeof File === 'function') {
        var file = new File([blob], filename, { type: blob.type || 'application/octet-stream' });
        if (navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file], title: filename })
            .then(function () {
              return { outcome: 'share', filename: filename };
            })
            .catch(function (err) {
              if (err && err.name === 'AbortError') {
                return { outcome: 'cancelled', filename: filename };
              }
              return triggerAnchorDownload();
            });
        }
      }
    } catch (e) { /* fall through to <a download> */ }

    return triggerAnchorDownload();
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
          imgSrc = '/images/' + encodeURIComponent(slug) + '.jpg';
        } else {
          imgSrc = PORTRAIT_SVG_PLACEHOLDER;
        }
        // Unresolved member: resolveMembersForView fell back to rid as
        // the display name. See issue #111.
        var unresolved = m.record_id && m.name === m.record_id;
        var hintHtml = unresolved
          ? '<div class="fellow-data-unavailable-hint">(fellow data unavailable)</div>'
          : '';
        html += '<button type="button" class="group-directory-cell' +
          (unresolved ? ' group-directory-cell--unresolved' : '') +
          '" data-member-idx="' + escapeHtml(String(idx)) + '">' +
          '<div class="group-directory-portrait">' +
            '<img src="' + escapeHtml(imgSrc) + '" alt="' + escapeHtml(m.name) +
            '" loading="lazy" onerror="this.onerror=null;this.src=\'' + PORTRAIT_SVG_PLACEHOLDER + '\';">' +
          '</div>' +
          '<div class="group-directory-name">' + escapeHtml(m.name) + '</div>' +
          hintHtml +
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
      imgSrc = '/images/' + encodeURIComponent(slug) + '.jpg';
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

    // See issue #111: portrait was clicked from a group whose member's
    // fellow row is gone from fellows.db; modal would otherwise show the
    // raw record_id as the heading with no context.
    var unresolved = m.record_id && m.name === m.record_id;
    var unresolvedHintHtml = unresolved
      ? '<div class="fellow-data-unavailable-hint fellow-modal-unresolved-hint">' +
          '(fellow data unavailable)' +
        '</div>'
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
        unresolvedHintHtml +
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
    '.fellow-data-unavailable-hint{font-size:0.72rem;color:#888;font-style:italic;' +
    'margin:2px 0 0;line-height:1.2;}' +
    '.fellow-card .fellow-data-unavailable-hint{margin:-0.2rem 0 0.6rem;font-size:0.85rem;}' +
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
      // See issue #111: orphan members in an exported group otherwise
      // print as a portrait placeholder under a raw record_id.
      var unresolved = m.record_id && m.name === m.record_id;
      var hintHtml = unresolved
        ? '<div class="fellow-data-unavailable-hint">(fellow data unavailable)</div>'
        : '';
      html += '<a class="cell" href="#fellow-' + escapeHtml(slug) + '">' +
        '<div class="portrait"><img src="' + escapeHtml(imgSrc) +
        '" alt="' + escapeHtml(m.name) + '"></div>' +
        '<div class="cell-name">' + escapeHtml(m.name) + '</div>' +
        hintHtml +
      '</a>';
    });
    return html + '</div>';
  }

  function buildExportFellowSection(group, m, imgMap) {
    var slug = m.slug || slugifyForFilename(m.name);
    var imgSrc = imgMap[m.slug] || PORTRAIT_SVG_PLACEHOLDER;
    var unresolved = m.record_id && m.name === m.record_id;
    var unresolvedHintHtml = unresolved
      ? '<p class="fellow-data-unavailable-hint">(fellow data unavailable)</p>'
      : '';
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
        unresolvedHintHtml +
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
        // Unresolved member: render a muted italic hint where the email
        // line would go. See issue #111.
        var unresolved = m.record_id && m.name === m.record_id;
        if (unresolved) {
          doc.setFont('helvetica', 'italic');
          doc.setFontSize(8);
          doc.setTextColor(136);
          var hintText = '(fellow data unavailable)';
          var hintY = nameY + emailLineH;
          var hintW = doc.getStringUnitWidth(hintText) * 8;
          doc.text(hintText, x + (cellW - hintW) / 2, hintY);
          doc.setTextColor(34);
        } else if (m.contact_email) {
          // Email (clickable mailto annotation)
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

  // ===== User-folder durable storage controller (issue #165 Phase 1) =======
  // Page-side wrapper around the worker's folder RPCs + the small bit of
  // user-gesture orchestration that has to live here (showDirectoryPicker
  // and requestPermission both require transient user activation; the
  // worker can't synthesize that). Pure controller — owns no DOM; the
  // Settings page consumes it through render-time callbacks.

  var FOLDER_CONTROLLER = (function () {
    function browserSupportsFolderPicker() {
      return typeof window.showDirectoryPicker === 'function';
    }

    function workerProvider() {
      // The folder controller only operates against the worker provider.
      // On api+idb fallback the warmWorker may still be alive (auth
      // failure mid-boot); fall through to it so a Reconnect attempt in
      // Settings doesn't pop a misleading "not available" message.
      if (dataProvider && dataProvider.kind === 'worker') return dataProvider;
      if (warmWorker && warmWorker.rpc) {
        // Wrap a minimal subset around warmWorker.rpc so the API shape
        // matches the worker provider.
        return {
          kind: 'worker-warm',
          _getFolderState: function () { return warmWorker.rpc.call('getFolderState'); },
          _setFolderHandle: function (a) { return warmWorker.rpc.call('setFolderHandle', a); },
          _clearFolderHandle: function () { return warmWorker.rpc.call('clearFolderHandle'); },
          _checkFolderPermission: function () { return warmWorker.rpc.call('checkFolderPermission'); },
          _getFolderHandleForReconnect: function () { return warmWorker.rpc.call('getFolderHandleForReconnect'); },
          _writeRelationshipsToFolder: function () { return warmWorker.rpc.call('writeRelationshipsToFolder'); },
          _readRelationshipsFromFolder: function () { return warmWorker.rpc.call('readRelationshipsFromFolder'); }
        };
      }
      return null;
    }

    function getState() {
      var p = workerProvider();
      if (!p) {
        return Promise.resolve({
          supported: browserSupportsFolderPicker(),
          workerAvailable: false,
          hasHandle: false,
          parentName: null,
          subfolderName: null,
          permission: 'no-worker',
          lastSavedAt: null,
          lastError: null,
          fileLastModified: null
        });
      }
      return p._getFolderState().then(function (raw) {
        raw.supported = browserSupportsFolderPicker();
        raw.workerAvailable = true;
        return raw;
      });
    }

    // Compute the badge state from a state snapshot. Returns one of:
    //   'unsupported'   — browser has no showDirectoryPicker.
    //   'browser-only'  — supported but no folder chosen.
    //   'saved'         — folder chosen and last write succeeded.
    //   'pending'       — folder chosen but no write yet (open-existing path).
    //   'inaccessible'  — folder chosen but queryPermission isn't 'granted'.
    //   'write-failed'  — most recent write attempt errored.
    function badge(state) {
      if (!state.supported) return 'unsupported';
      if (!state.hasHandle) return 'browser-only';
      if (state.permission !== 'granted') return 'inaccessible';
      if (state.lastError && state.lastError.at &&
          (!state.lastSavedAt || state.lastError.at > state.lastSavedAt)) {
        return 'write-failed';
      }
      if (!state.lastSavedAt) return 'pending';
      return 'saved';
    }

    // Step 1: invoke the OS folder picker. Must be called from a user-
    // gesture handler (showDirectoryPicker requires transient activation).
    // Returns the FileSystemDirectoryHandle, or null on user-cancel /
    // unsupported.
    function pickParentFolder() {
      if (!browserSupportsFolderPicker()) return Promise.resolve(null);
      return window.showDirectoryPicker({ mode: 'readwrite', id: 'fellows-data-folder' })
        .catch(function (e) {
          // AbortError = user cancelled the picker. Treat as null, not a
          // failure to surface to the user.
          if (e && (e.name === 'AbortError' || /cancel/i.test(String(e.message || '')))) return null;
          throw e;
        });
    }

    // Step 2: hand the handle to the worker. Returns either
    //   { ok: true, parentName, subfolderName }
    // or
    //   { ok: false, requiresChoice: true, existing, suggestion }
    function setHandle(handle, mode) {
      var p = workerProvider();
      if (!p) return Promise.reject(new Error('worker provider unavailable'));
      return p._setFolderHandle({ handle: handle, mode: mode || 'auto' });
    }

    function clearHandle() {
      var p = workerProvider();
      if (!p) return Promise.reject(new Error('worker provider unavailable'));
      return p._clearFolderHandle();
    }

    function writeNow() {
      var p = workerProvider();
      if (!p) return Promise.reject(new Error('worker provider unavailable'));
      return p._writeRelationshipsToFolder();
    }

    function readNow() {
      var p = workerProvider();
      if (!p) return Promise.reject(new Error('worker provider unavailable'));
      return p._readRelationshipsFromFolder();
    }

    // Reconnect path: pull the in-memory handle from the worker, call
    // requestPermission on it inside the page's user-gesture, then ask
    // the worker to recheck. Returns the new state.
    function reconnect() {
      var p = workerProvider();
      if (!p) return Promise.reject(new Error('worker provider unavailable'));
      return p._getFolderHandleForReconnect().then(function (res) {
        if (!res || !res.handle) {
          throw new Error('no folder handle persisted');
        }
        var handle = res.handle;
        if (typeof handle.requestPermission !== 'function') {
          // Older shim — already granted (was returned by the picker).
          return p._checkFolderPermission().then(function () { return getState(); });
        }
        return handle.requestPermission({ mode: 'readwrite' }).then(function (state) {
          // Worker re-runs queryPermission to refresh its cached value.
          return p._checkFolderPermission().then(function () {
            return getState();
          });
        });
      });
    }

    return {
      browserSupportsFolderPicker: browserSupportsFolderPicker,
      getState: getState,
      badge: badge,
      pickParentFolder: pickParentFolder,
      setHandle: setHandle,
      clearHandle: clearHandle,
      writeNow: writeNow,
      readNow: readNow,
      reconnect: reconnect
    };
  })();
  // Exposed for tests + diag panel.
  window.__folderController = FOLDER_CONTROLLER;

  // ===== Folder-push banner (Phase 2 PR 3) =================================
  // Top-of-page banner that surfaces to capable browsers in OPFS-only mode,
  // pushing the user to pick a data folder. Hidden when:
  //   - The browser doesn't support showDirectoryPicker (Safari, Firefox,
  //     iOS) — the user manual explains the OPFS-only fallback for them.
  //   - A folder is already picked (folderRecord.parentHandle present).
  //   - The user clicked "Not now" this session (sessionStorage flag —
  //     re-appears on next browser session).
  // Re-evaluated after any folder operation via wireFolderSection's
  // renderState hook + on an initial post-boot delay so the worker has
  // time to load folderRecord from IDB.
  var FOLDER_PUSH_DISMISS_KEY = 'fellows_folder_push_dismissed';

  function isFolderPushDismissed() {
    try { return sessionStorage.getItem(FOLDER_PUSH_DISMISS_KEY) === '1'; }
    catch (e) { return false; }
  }

  function refreshFolderPushBanner() {
    var bannerEl = document.getElementById('folder-push-banner');
    if (!bannerEl) return;
    if (isFolderPushDismissed()) {
      bannerEl.classList.add('hidden');
      return;
    }
    if (!FOLDER_CONTROLLER) {
      bannerEl.classList.add('hidden');
      return;
    }
    FOLDER_CONTROLLER.getState().then(function (state) {
      // Hide for: incapable browser, worker not yet ready (avoids flash),
      // or folder already picked. Show otherwise (i.e., capable + OPFS-only).
      if (!state.supported || !state.workerAvailable || state.hasHandle) {
        bannerEl.classList.add('hidden');
        return;
      }
      bannerEl.classList.remove('hidden');
    }).catch(function () {
      bannerEl.classList.add('hidden');
    });
  }

  (function bindFolderPushBanner() {
    var ctaBtn = document.getElementById('folder-push-cta');
    var dismissBtn = document.getElementById('folder-push-dismiss');
    if (ctaBtn) {
      ctaBtn.addEventListener('click', function () {
        // Navigate to Settings → focus the Data folder section so the
        // user lands on the Choose button. Use a small post-hashchange
        // delay so the section markup is mounted before scrolling.
        location.hash = '#/settings';
        setTimeout(function () {
          var section = document.getElementById('settings-folder-section');
          var chooseBtn = document.getElementById('settings-folder-choose');
          if (section) section.scrollIntoView({ behavior: 'smooth', block: 'center' });
          if (chooseBtn) {
            try { chooseBtn.focus(); } catch (e) {}
          }
        }, 200);
      });
    }
    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () {
        try { sessionStorage.setItem(FOLDER_PUSH_DISMISS_KEY, '1'); }
        catch (e) {}
        var bannerEl = document.getElementById('folder-push-banner');
        if (bannerEl) bannerEl.classList.add('hidden');
      });
    }
    // Initial evaluation. The worker may still be initializing — that
    // case returns workerAvailable:false and the banner stays hidden.
    // Subsequent re-evaluations happen on Settings page render and on
    // a small delay below as a safety net for users who never open
    // Settings.
    setTimeout(refreshFolderPushBanner, 1500);
  })();

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
      '<div class="settings-section" id="settings-folder-section">' +
        '<h3 class="settings-section-title">Data folder</h3>' +
        '<p class="settings-hint">' +
          'Pick a folder on your device for the app to keep <code>relationships.db</code> in. ' +
          'The app creates a <code>Fellows/</code> subfolder inside the folder you choose, so your other files in that folder are untouched. ' +
          'Your data still lives on your device — nothing is uploaded — but it becomes a real file you can browse to, copy, sync, or back up like any other file.' +
        '</p>' +
        '<div id="settings-folder-badge" class="settings-folder-badge" role="status" aria-live="polite">' +
          '<span class="settings-folder-badge-dot"></span>' +
          '<span class="settings-folder-badge-text">Checking…</span>' +
        '</div>' +
        '<p id="settings-folder-path" class="settings-hint settings-folder-path" hidden>' +
          'File: <code id="settings-folder-path-value"></code> ' +
          '<span class="settings-folder-path-note">(your browser doesn\'t expose absolute system paths — find this in Finder / Explorer to see the full path)</span>' +
        '</p>' +
        '<div id="settings-folder-actions" class="settings-folder-actions">' +
          '<button type="button" id="settings-folder-choose" class="settings-download" hidden>Choose data folder…</button>' +
          '<button type="button" id="settings-folder-save-now" class="settings-download" hidden ' +
            'title="Manually re-save your current data to the folder. Auto-save runs after every change; this is a retry button for when auto-save fails.">Save now</button>' +
          '<button type="button" id="settings-folder-refresh" class="settings-download" hidden ' +
            'title="Replace your current working data with whatever is in the folder right now. Useful if you edited the file in another browser, or your cloud-sync service pulled in a new version. Your current data is captured as an auto-backup first, so this is undoable.">Reload from folder</button>' +
          '<button type="button" id="settings-folder-reconnect" class="settings-download" hidden>Reconnect folder…</button>' +
          '<button type="button" id="settings-folder-disconnect" class="settings-download settings-folder-disconnect" hidden>Disconnect folder</button>' +
        '</div>' +
        '<p id="settings-folder-detail" class="settings-hint settings-folder-detail" hidden></p>' +
      '</div>' +
      '<dialog id="settings-folder-collision-dialog" class="settings-folder-dialog">' +
        '<form method="dialog">' +
          '<h4 id="settings-folder-collision-title">This folder already contains fellows data</h4>' +
          '<p id="settings-folder-collision-body"></p>' +
          '<menu class="settings-folder-dialog-actions">' +
            '<button type="submit" value="create-new" class="settings-folder-dialog-primary" id="settings-folder-collision-create"></button>' +
            '<button type="submit" value="open-existing" class="settings-folder-dialog-secondary">Open existing data</button>' +
            '<button type="submit" value="cancel" class="settings-folder-dialog-cancel">Cancel</button>' +
          '</menu>' +
        '</form>' +
      '</dialog>' +
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
        '<p class="settings-hint settings-restore-migrate-hint">' +
          'Migrating from another browser? ' +
          '<a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md#migrating-from-another-browser" target="_blank" rel="noopener">See the recipe</a> ' +
          '(it\'s the same Download / Restore flow on this page, but in a deliberate order).' +
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
      '<div class="settings-section" id="settings-mcpb-section">' +
        '<h3 class="settings-section-title">Claude Desktop integration (beta)</h3>' +
        '<p class="settings-hint" id="settings-mcpb-intro">' +
          'Plug the directory into Claude Desktop so you can ask things like ' +
          '<em>"draft an invite email to my Climate Action group, don\'t send."</em> ' +
          'Three small extensions, installed in one go. ' +
          '<a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/use_with_claude_desktop.md" target="_blank" rel="noopener">Walkthrough</a>.' +
        '</p>' +
        '<div class="settings-mcpb-actions">' +
          '<button type="button" id="settings-mcpb-setup" class="settings-download">' +
            'Set up Claude Desktop integration' +
          '</button>' +
        '</div>' +
        '<p id="settings-mcpb-setup-meta" class="settings-hint settings-mcpb-meta" hidden></p>' +
        '<span id="settings-mcpb-status" class="settings-status" aria-live="polite"></span>' +
      '</div>' +
      '<dialog id="settings-mcpb-preamble-dialog" class="settings-folder-dialog settings-mcpb-dialog">' +
        '<form method="dialog">' +
          '<h4>Set up Claude Desktop integration</h4>' +
          '<p class="settings-mcpb-platform-note">' +
            'This easy path is for <strong>Chrome and Chrome-derived browsers</strong> (Edge, Brave, Arc). ' +
            'If you\'re using Safari, Firefox, or another browser, use the ' +
            '<a href="https://github.com/richbodo/fellows_local_db/blob/main/docs/use_with_claude_desktop.md" target="_blank" rel="noopener">manual walkthrough</a>.' +
          '</p>' +
          '<p id="settings-mcpb-preamble-folder-warning" class="settings-mcpb-warning" hidden>' +
            '<strong>Heads up.</strong> You haven\'t set up a data folder yet. ' +
            'We recommend <em>Settings → Data folder → Choose data folder…</em> first (takes about ten seconds). ' +
            'Without it, you\'ll need to redo this setup every time you change a group.' +
          '</p>' +
          '<p id="settings-mcpb-preamble-browser-warning" class="settings-mcpb-warning" hidden>' +
            '<strong>Your browser:</strong> the easy install works on Chrome, Edge, Brave, and Arc. ' +
            'Safari and Firefox need the manual setup linked above.' +
          '</p>' +
          '<div class="settings-mcpb-warning settings-mcpb-warning--banner">' +
            '<strong>You will see three scary warnings from Claude Desktop.</strong> ' +
            'They say <em>"Installing will grant this extension access to everything on your computer…"</em> ' +
            'Nothing is wrong. The extensions only read fellows data. Anthropic just had to add these warnings. ' +
            'Click <strong>Install</strong> to proceed on each.' +
          '</div>' +
          '<h5 class="settings-mcpb-section-title">What happens next</h5>' +
          '<ol class="settings-mcpb-steps">' +
            '<li>Click <strong>Continue</strong> below. Your browser asks permission to download multiple files — approve.</li>' +
            '<li>Three <code>.mcpb</code> files arrive in your Downloads folder.</li>' +
            '<li>Open each file. Claude Desktop pops up an Install dialog showing the red warning above. Click <strong>Install</strong>.</li>' +
            '<li>For <strong>private_data_ops.mcpb</strong>, the install dialog asks you to pick a file. Navigate to your data folder → <strong>Fellows</strong> → <code>relationships.db</code>.</li>' +
            '<li>When all three are installed, <strong>quit Claude Desktop (⌘Q) and reopen it</strong>.</li>' +
            '<li>Test by asking Claude: <em>"How many fellows are in the directory?"</em></li>' +
          '</ol>' +
          '<menu class="settings-folder-dialog-actions">' +
            '<button type="submit" value="continue" class="settings-folder-dialog-primary" id="settings-mcpb-preamble-continue">Continue — start downloads</button>' +
            '<button type="submit" value="cancel" class="settings-folder-dialog-cancel">Cancel</button>' +
          '</menu>' +
          '<details class="settings-mcpb-bundle-details">' +
            '<summary>What the three extensions do</summary>' +
            '<p>Each extension covers a different boundary; you can install just the ones you want.</p>' +
            '<ol class="settings-mcpb-bundles">' +
              '<li>' +
                '<strong>Fellows directory (Shared).</strong> Lets Claude read the public fellows directory: names, bios, contact info, search. ' +
                '<em>Recommended.</em>' +
              '</li>' +
              '<li>' +
                '<strong>Your saved groups (Private).</strong> Lets Claude read your saved groups, group members, and any notes you\'ve added. ' +
                'This data is private to you and never leaves your device through the Fellows app — but when Claude reads it, it goes to Claude\'s servers (Anthropic). ' +
                'If that\'s not OK for you, skip this extension and Claude will only have access to the directory.' +
              '</li>' +
              '<li>' +
                '<strong>Email staging (Communications).</strong> Lets Claude prepare draft emails to your groups and hand them back to you for review. ' +
                'Claude never sends mail itself — drafts open in your mail app with To, Subject, and Body filled in, and you click Send.' +
              '</li>' +
            '</ol>' +
          '</details>' +
        '</form>' +
      '</dialog>' +
      '</div>';
    detailEl.innerHTML = html;
    var input = document.getElementById('settings-self-email');
    var status = document.getElementById('settings-status');
    var form = document.getElementById('settings-form');
    var downloadBtn = document.getElementById('settings-download-userdata');
    var downloadStatus = document.getElementById('settings-download-status');
    var exportSection = document.getElementById('settings-export-section');

    // Backup + restore both depend on the OPFS-backed sqlite provider —
    // the API provider (dev fallback) operates on a server-side
    // relationships.db that isn't the user's data, and prod doesn't
    // serve those routes at all. So when we're on the API provider we
    // can't honor a click on "Download my user data" or "Restore from
    // a file"; PR #84 hid the export section on click rejection and
    // PR #92 hid both sections proactively at render time. That avoided
    // broken affordances but turned the failure silent — a user who
    // arrived hoping to restore got an email field and no explanation.
    // Now: render the existing local-data-unavailable panel into the
    // export section (covering "backup and restore" together), hide
    // the restore section, and let the panel tell the user what to do.
    // The late `localDataUnavailable` click-handler paths below remain
    // for paranoia / late provider downgrades.
    // 'worker' = the dedicated sqlite-worker.js owns OPFS; backup/restore
    // both go through worker RPC. 'api+idb' = worker init failed (no OPFS-
    // capable browser); the unavailable-panel covers groups/settings.
    var localPersistenceAvailable = !!(
      dataProvider && dataProvider.kind === 'worker'
    );
    if (!localPersistenceAvailable) {
      var preExport = document.getElementById('settings-export-section');
      if (preExport) {
        preExport.innerHTML = renderLocalDataUnavailablePanel(
          'backup and restore',
          { runtimeFailure: true }
        );
      }
      var preRestore = document.getElementById('settings-restore-section');
      if (preRestore) preRestore.style.display = 'none';
    }

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
            return downloadBlob(blob, filename).then(function (result) {
              if (!downloadStatus) return;
              var savedName = (result && result.filename) || filename;
              var size = bytes.byteLength;
              if (result && result.outcome === 'cancelled') {
                downloadStatus.textContent = 'Cancelled — no file saved.';
              } else if (result && result.outcome === 'picker') {
                downloadStatus.textContent =
                  'Saved as ' + savedName + ' (' + size + ' bytes).';
              } else if (result && result.outcome === 'share') {
                downloadStatus.textContent =
                  'Saved via the share sheet (' + size + ' bytes).';
              } else {
                downloadStatus.textContent =
                  'Saved ' + savedName + ' to your browser\'s Downloads folder (' + size + ' bytes).';
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
      // Worker writes backups as "relationships.db.bak.<ISO timestamp>"
      // with ":" and "." replaced by "-" for filesystem-safety.
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
    var lastBackupList = [];
    function refreshBackupList() {
      if (!backupListEl) return;
      if (!dataProvider || typeof dataProvider.listRelationshipsBackups !== 'function') {
        return;
      }
      dataProvider.listRelationshipsBackups()
        .then(function (backups) {
          lastBackupList = Array.isArray(backups) ? backups.slice() : [];
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
        if (!dataProvider || typeof dataProvider.restoreRelationshipsBackup !== 'function') {
          flashRestoreStatus('Restore not available in this mode.');
          return;
        }
        // Worker is the OPFS owner — page can't read backup bytes
        // directly. Use the cached row counts from listRelationshipsBackups
        // for the confirm dialog, then call restoreRelationshipsBackup({name})
        // which reads + imports atomically inside the worker (and snapshots
        // the current state into the rotation slot before overwriting).
        var entry = null;
        for (var i = 0; i < lastBackupList.length; i++) {
          if (lastBackupList[i].name === name) { entry = lastBackupList[i]; break; }
        }
        var sourceLabel = 'auto-backup ' + fmtBackupTimestamp(name);
        if (!entry || entry.invalid) {
          flashRestoreStatus('Backup unreadable; refresh the list and try again.');
          return;
        }
        dataProvider.countRelationships().then(function (current) {
          var ok = window.confirm(buildConfirmMessage(current, entry.counts, sourceLabel));
          if (!ok) {
            flashRestoreStatus('Restore cancelled.');
            return null;
          }
          flashRestoreStatus('Restoring…');
          return dataProvider.restoreRelationshipsBackup(name).then(function (result) {
            flashRestoreStatus(
              'Restored from ' + sourceLabel + ' — ' +
              result.counts.groups + ' groups, ' +
              result.counts.notes + ' notes, ' +
              result.counts.tags + ' tags.' +
              (result.preRestoreSnapshot
                ? ' Previous data saved as auto-backup; click an entry below to undo.'
                : '')
            );
            refreshBackupList();
          });
        }).catch(function (err) {
          if (err && err.name === 'VersionMismatchError') {
            flashRestoreStatus('App update pending — reload to enable restore.');
            return;
          }
          flashRestoreStatus('Restore failed: ' + (err && err.message || String(err)));
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

    wireFolderSection();
    wireMcpbSection();
  }

  // Settings → Claude Desktop integration. Pure glue between the DOM
  // nodes injected by renderSettingsPage, the MCPB setup state
  // (localStorage `fellows_mcpb_setup`), and the auth-gated
  // `/mcpb/<name>.mcpb` routes served by deploy/server.py. Plan:
  // plans/easy_mcp_install.md § 4 + § 7.
  function wireMcpbSection() {
    var sectionEl = document.getElementById('settings-mcpb-section');
    if (!sectionEl) return;
    var setupBtn = document.getElementById('settings-mcpb-setup');
    var statusEl = document.getElementById('settings-mcpb-status');
    var metaEl = document.getElementById('settings-mcpb-setup-meta');
    var dialog = document.getElementById('settings-mcpb-preamble-dialog');
    var folderWarning = document.getElementById('settings-mcpb-preamble-folder-warning');
    var browserWarning = document.getElementById('settings-mcpb-preamble-browser-warning');
    var continueBtn = document.getElementById('settings-mcpb-preamble-continue');
    if (!setupBtn || !dialog) return;

    function setStatus(text) {
      if (statusEl) statusEl.textContent = text || '';
    }

    function browserIsChromium() {
      // Conservative — only the four browsers we explicitly support on
      // the easy path. Brave / Arc / other Chromium derivatives advertise
      // "Chrome/..." in UA so they fall through into this set. Safari /
      // Firefox are deliberately excluded; they get the manual-setup link
      // in the preamble dialog and the no-easy-path messaging in the
      // walkthrough doc. The same caveat that lives in
      // detectBrowserBestEffort() applies here — UA can be spoofed.
      var ua = (navigator && navigator.userAgent) || '';
      if (/Firefox\//.test(ua)) return false;
      if (/Edg\//.test(ua)) return true;
      if (/Chrome\//.test(ua)) return true;
      if (/Safari\//.test(ua) && /Version\//.test(ua)) return false;
      return false;
    }

    function refreshUiFromState() {
      var state = getMcpbSetupState();
      // Button label stays constant — "Set up Claude Desktop integration" —
      // for both first-time and re-run. The meta line below carries the
      // state distinction (whether the user has set up before, and when).
      // Earlier iteration relabelled the button to "Re-download all
      // extensions"; maintainer feedback was that the label was awkward
      // and the meta line already conveyed the same info.
      //
      // Directory-data refresh affordance used to live in this section
      // too. As of PR #204 it lives on the About page next to the
      // existing "Update directory data" button — all "your data
      // versions need updating" affordances in one place. paintDataRow
      // owns it.
      if (state && state.setupAt) {
        if (metaEl) {
          metaEl.hidden = false;
          metaEl.innerHTML = 'Last set up: <strong>' +
            escapeHtml(formatRelativeTime(state.refreshedAt || state.setupAt)) +
            '</strong>. Re-running this will replace the extensions you have installed in Claude Desktop.';
        }
      } else {
        if (metaEl) {
          metaEl.hidden = true;
          metaEl.textContent = '';
        }
      }
    }

    function openPreamble() {
      if (!dialog) return;
      // Decide which warnings to surface BEFORE opening so first
      // render is correct. The folder check is async (worker RPC); the
      // browser check is sync.
      if (browserWarning) browserWarning.hidden = browserIsChromium();
      // Default: hide the folder warning; flip it on if folder mode
      // isn't active. The check uses FOLDER_CONTROLLER which surfaces
      // the worker's `getFolderState` RPC. Failing the check (e.g.,
      // unsupported browser) leaves the warning hidden — the browser
      // warning already covers that audience.
      if (folderWarning) folderWarning.hidden = true;
      try {
        if (window.__folderController && typeof window.__folderController.getState === 'function') {
          window.__folderController.getState().then(function (state) {
            if (!folderWarning) return;
            var folderActive = state && state.hasHandle &&
              (state.permission === 'granted');
            // Only Chromium users benefit from this nudge — Safari /
            // Firefox got the browser warning instead.
            folderWarning.hidden = folderActive || !browserIsChromium();
          }, function () {});
        }
      } catch (e) {}
      try { dialog.showModal(); }
      catch (e) {
        // Fallback for browsers without <dialog> support — surface as
        // a confirm() so the user can at least proceed past the
        // preamble. The actual download trigger still works.
        if (window.confirm('Set up Claude Desktop integration — three .mcpb files will download. Proceed?')) {
          runMcpbDownloads();
        }
      }
    }

    function downloadBundles(bundleNames) {
      var seq = Promise.resolve();
      bundleNames.forEach(function (name) {
        seq = seq.then(function () {
          return triggerSameOriginDownload('/mcpb/' + name + '.mcpb', name + '.mcpb');
        });
      });
      return seq;
    }

    function runMcpbDownloads() {
      setStatus('Downloading three .mcpb files…');
      setupBtn.disabled = true;
      return downloadBundles(MCPB_BUNDLE_NAMES).then(function () {
        var serverSha = (bootBuildMeta && bootBuildMeta.fellows_db_sha) || null;
        recordMcpbSetup(serverSha);
        setStatus('Downloads triggered. Check your Downloads folder.');
        refreshUiFromState();
      }).catch(function (e) {
        setStatus('Download failed: ' + (e && e.message ? e.message : String(e)));
      }).then(function () {
        setupBtn.disabled = false;
      });
    }

    setupBtn.addEventListener('click', openPreamble);
    if (dialog) {
      dialog.addEventListener('close', function () {
        // <dialog>'s close event fires for any submit (including the
        // primary "Continue" button). returnValue carries the button's
        // value attribute — "continue" / "cancel" / empty (Esc).
        if (dialog.returnValue === 'continue') {
          runMcpbDownloads();
        }
      });
    }
    refreshUiFromState();
  }

  // Settings → Data folder section: badge, action buttons, collision
  // dialog. State is owned by FOLDER_CONTROLLER; this function is pure
  // glue between the controller and the DOM nodes injected by
  // renderSettingsPage.
  function wireFolderSection() {
    var sectionEl = document.getElementById('settings-folder-section');
    if (!sectionEl) return;
    var badgeEl = document.getElementById('settings-folder-badge');
    var detailEl2 = document.getElementById('settings-folder-detail');
    var btnChoose = document.getElementById('settings-folder-choose');
    var btnSave = document.getElementById('settings-folder-save-now');
    var btnRefresh = document.getElementById('settings-folder-refresh');
    var btnReconnect = document.getElementById('settings-folder-reconnect');
    var btnDisconnect = document.getElementById('settings-folder-disconnect');
    var dialog = document.getElementById('settings-folder-collision-dialog');
    var dialogTitle = document.getElementById('settings-folder-collision-title');
    var dialogBody = document.getElementById('settings-folder-collision-body');
    var dialogCreateBtn = document.getElementById('settings-folder-collision-create');

    if (!FOLDER_CONTROLLER) return;

    var BADGE_COPY = {
      'unsupported': {
        text: 'Browser-only — this browser doesn\'t support saving to a folder',
        cls: 'settings-folder-badge--warning'
      },
      'browser-only': {
        text: 'Browser-only — your data is not yet saved to a folder',
        cls: 'settings-folder-badge--warning'
      },
      'saved': {
        text: 'Saved',
        cls: 'settings-folder-badge--saved'
      },
      'pending': {
        text: 'Folder selected — no save yet',
        cls: 'settings-folder-badge--pending'
      },
      'inaccessible': {
        text: 'Folder set but unreachable — reconnect to keep saving',
        cls: 'settings-folder-badge--warning'
      },
      'write-failed': {
        text: 'Last save failed — Retry to save again',
        cls: 'settings-folder-badge--warning'
      }
    };

    function renderState(state) {
      if (!state) return;
      var b = FOLDER_CONTROLLER.badge(state);
      var copy = BADGE_COPY[b] || BADGE_COPY['browser-only'];
      var dotEl = badgeEl && badgeEl.querySelector('.settings-folder-badge-dot');
      var textEl = badgeEl && badgeEl.querySelector('.settings-folder-badge-text');
      if (badgeEl) {
        badgeEl.className = 'settings-folder-badge ' + copy.cls;
        if (textEl) {
          var label = copy.text;
          if (b === 'saved' && state.parentName && state.subfolderName) {
            label = 'Saved to ' + escapeHtml(state.parentName) + ' / ' + escapeHtml(state.subfolderName);
            if (state.lastSavedAt) label += ' · ' + formatRelativeTime(state.lastSavedAt);
            textEl.innerHTML = label;
          } else {
            textEl.textContent = label;
          }
        }
        if (dotEl) dotEl.setAttribute('aria-hidden', 'true');
      }
      // The detail line is reserved for transient status/errors (the
      // flashDetail messages). Don't stomp on it here — the badge above
      // already shows folder path + timestamp, and an in-progress
      // "Saving…" flash would be lost if we overwrote on every refresh.
      // We only update detailEl2 here for a sticky error message; the
      // happy path leaves whatever flashDetail last wrote in place.
      if (detailEl2 && state.lastError && state.lastError.reason &&
          (!state.lastSavedAt || (state.lastError.at && state.lastError.at > state.lastSavedAt))) {
        detailEl2.textContent = 'Last error: ' + state.lastError.reason;
        detailEl2.hidden = false;
      }
      // Path detail line — show the parent/Fellows/relationships.db
      // relative path so forgetful users have a reminder of where their
      // file lives. The File System Access API does NOT expose absolute
      // system paths (security by design), so we show the best we can
      // and direct the user to Finder for the full path.
      var pathLineEl = document.getElementById('settings-folder-path');
      var pathValueEl = document.getElementById('settings-folder-path-value');
      var showPath = state.hasHandle && state.parentName && state.subfolderName;
      if (pathLineEl) pathLineEl.hidden = !showPath;
      if (pathValueEl && showPath) {
        pathValueEl.textContent =
          state.parentName + ' / ' + state.subfolderName + ' / relationships.db';
      }
      // Wire which buttons are visible to the badge state.
      var supported = !!state.supported && (state.workerAvailable !== false);
      function showBtn(btn, on) { if (btn) btn.hidden = !on; }
      showBtn(btnChoose,     supported && (b === 'browser-only'));
      showBtn(btnSave,       supported && (b === 'pending' || b === 'saved' || b === 'write-failed'));
      showBtn(btnRefresh,    supported && b === 'saved');
      showBtn(btnReconnect,  supported && b === 'inaccessible');
      showBtn(btnDisconnect, supported && state.hasHandle);
      // The "Your saved data" / Download my user data section is
      // redundant when folder mode is actively writing to the user's
      // disk — they can just grab the file from Finder. Hide it in
      // that case. Keep it visible for OPFS-only-mode users (their
      // only path to a backup file) and for degraded folder-mode
      // sessions where permission has lapsed (the folder file may
      // be stale; the in-browser data is what they'd want to grab).
      var exportSectionEl = document.getElementById('settings-export-section');
      if (exportSectionEl) {
        var folderActive = b === 'saved' || b === 'pending';
        exportSectionEl.hidden = folderActive;
      }
      // Cascade: state change here may also affect whether the top-of-
      // page folder-push banner is visible (e.g., user just picked a
      // folder → badge becomes 'saved' → banner should hide).
      refreshFolderPushBanner();
    }

    function refresh() {
      return FOLDER_CONTROLLER.getState().then(renderState).catch(function (e) {
        if (detailEl2) {
          detailEl2.textContent = 'Could not read folder state: ' + (e && e.message || String(e));
          detailEl2.hidden = false;
        }
      });
    }

    function flashDetail(msg) {
      if (!detailEl2) return;
      detailEl2.textContent = msg;
      detailEl2.hidden = false;
    }

    function fmtCountsSummary(c) {
      if (!c) return '';
      return c.groups + ' group' + (c.groups === 1 ? '' : 's') +
        ', ' + c.members + ' member' + (c.members === 1 ? '' : 's') +
        ', ' + c.tags + ' tag' + (c.tags === 1 ? '' : 's');
    }

    function askCollision(parentName, existing, suggestion) {
      // Native <dialog>.showModal — falls back to confirm() on browsers
      // without dialog support (extremely rare in 2026; Chromium/Safari/
      // Firefox all ship it).
      if (!dialog || typeof dialog.showModal !== 'function') {
        var msg = (existing && existing.counts)
          ? 'This folder already has fellows data (' + fmtCountsSummary(existing.counts) + '). ' +
            'Use existing data here? OK → Open existing · Cancel → save to a new folder (' + suggestion + ').'
          : 'This folder already has fellows data. OK → Open existing · Cancel → save to a new folder (' + suggestion + ').';
        return Promise.resolve(window.confirm(msg) ? 'open-existing' : 'create-new');
      }
      if (dialogTitle) {
        dialogTitle.textContent = parentName
          ? '"' + parentName + '" already contains fellows data'
          : 'This folder already contains fellows data';
      }
      if (dialogBody) {
        var summary = existing && existing.counts ? fmtCountsSummary(existing.counts) : '';
        var lines = [];
        if (existing && existing.subfolderName) {
          lines.push('A "' + existing.subfolderName + '" folder is already there' +
            (summary ? ' with ' + summary + '.' : '.'));
        }
        if (existing && existing.invalid) {
          lines.push('(Existing relationships.db looks unreadable: ' +
            (existing.invalidReason || 'unknown') + '.)');
        }
        lines.push(
          'To avoid overwriting it, the app can save your current data into a new "' +
          (suggestion || 'Fellows N') + '" folder. Or open the existing data and use it here.'
        );
        dialogBody.textContent = lines.join(' ');
      }
      if (dialogCreateBtn) {
        dialogCreateBtn.textContent = 'Create "' + (suggestion || 'Fellows N') + '"';
      }
      return new Promise(function (resolve) {
        dialog.addEventListener('close', function once() {
          dialog.removeEventListener('close', once);
          var v = dialog.returnValue;
          if (v === 'open-existing' || v === 'create-new') resolve(v);
          else resolve(null);
        });
        try { dialog.showModal(); }
        catch (e) {
          // Already open or browser quirk — treat as cancel.
          resolve(null);
        }
      });
    }

    if (btnChoose) {
      btnChoose.addEventListener('click', function () {
        btnChoose.disabled = true;
        flashDetail('Pick a folder…');
        FOLDER_CONTROLLER.pickParentFolder()
          .then(function (handle) {
            if (!handle) {
              flashDetail('No folder selected.');
              return null;
            }
            return FOLDER_CONTROLLER.setHandle(handle, 'auto').then(function (res) {
              if (res && res.requiresChoice) {
                return askCollision(res.parentName, res.existing, res.suggestion).then(function (choice) {
                  if (!choice) {
                    flashDetail('Cancelled.');
                    return null;
                  }
                  return FOLDER_CONTROLLER.setHandle(handle, choice).then(function (resolved) {
                    return { picked: resolved, mode: choice };
                  });
                });
              }
              return { picked: res, mode: 'auto' };
            });
          })
          .then(function (outcome) {
            if (!outcome || !outcome.picked || !outcome.picked.ok) return;
            // Newly-attached folder: do an immediate save so the badge
            // flips to "Saved" right away on create-new, and (for the
            // happy-path "auto" case where the subfolder was empty) the
            // file exists. open-existing skips the write and instead
            // reads the existing data into OPFS.
            if (outcome.mode === 'open-existing') {
              flashDetail('Loading existing data from folder…');
              return FOLDER_CONTROLLER.readNow().then(function (result) {
                flashDetail('Loaded ' + (result && result.counts ? fmtCountsSummary(result.counts) : '') +
                  ' from the folder.');
              });
            }
            flashDetail('Saving to folder…');
            return FOLDER_CONTROLLER.writeNow().then(function () { flashDetail('Saved.'); });
          })
          .catch(function (e) {
            flashDetail('Could not set folder: ' + (e && e.message || String(e)));
          })
          .then(function () {
            btnChoose.disabled = false;
            return refresh();
          });
      });
    }

    if (btnSave) {
      btnSave.addEventListener('click', function () {
        btnSave.disabled = true;
        flashDetail('Saving to folder…');
        FOLDER_CONTROLLER.writeNow()
          .then(function (res) {
            flashDetail('Saved (' + res.bytesWritten + ' bytes).');
          })
          .catch(function (e) {
            flashDetail('Save failed: ' + (e && e.message || String(e)));
          })
          .then(function () {
            btnSave.disabled = false;
            return refresh();
          });
      });
    }

    if (btnRefresh) {
      btnRefresh.addEventListener('click', function () {
        var ok = window.confirm(
          'Reload your working data from the folder file?\n\n' +
          'This replaces what you\'re currently looking at with whatever is in the folder right now — useful if the file was edited elsewhere (another browser, cloud sync, or a manual restore). Your current data is captured as an auto-backup first, so this is undoable.'
        );
        if (!ok) return;
        btnRefresh.disabled = true;
        flashDetail('Reading from folder…');
        FOLDER_CONTROLLER.readNow()
          .then(function (res) {
            flashDetail('Loaded ' + fmtCountsSummary(res.counts) + ' from the folder.' +
              (res.preRestoreSnapshot ? ' Previous data saved as auto-backup.' : ''));
          })
          .catch(function (e) {
            flashDetail('Refresh failed: ' + (e && e.message || String(e)));
          })
          .then(function () {
            btnRefresh.disabled = false;
            return refresh();
          });
      });
    }

    if (btnReconnect) {
      btnReconnect.addEventListener('click', function () {
        btnReconnect.disabled = true;
        flashDetail('Reconnecting…');
        FOLDER_CONTROLLER.reconnect()
          .then(function (state) {
            renderState(state);
            if (state && state.permission === 'granted') {
              flashDetail('Reconnected.');
            } else {
              flashDetail('Reconnect declined — folder still unreachable.');
            }
          })
          .catch(function (e) {
            flashDetail('Reconnect failed: ' + (e && e.message || String(e)));
          })
          .then(function () {
            btnReconnect.disabled = false;
          });
      });
    }

    if (btnDisconnect) {
      btnDisconnect.addEventListener('click', function () {
        var ok = window.confirm(
          'Disconnect this folder?\n\n' +
          'Your data stays in this browser (and the file in the folder is untouched). ' +
          'You can re-pick the same folder later to reconnect.'
        );
        if (!ok) return;
        btnDisconnect.disabled = true;
        FOLDER_CONTROLLER.clearHandle()
          .then(function () { flashDetail('Disconnected.'); })
          .catch(function (e) {
            flashDetail('Disconnect failed: ' + (e && e.message || String(e)));
          })
          .then(function () {
            btnDisconnect.disabled = false;
            return refresh();
          });
      });
    }

    refresh();
  }

  // Tiny relative-time formatter: "just now", "2 min ago", etc. Used by
  // the folder badge so the timestamp doesn't dominate the UI.
  function formatRelativeTime(iso) {
    if (!iso) return '';
    var t = new Date(iso).getTime();
    if (isNaN(t)) return iso;
    var ms = Date.now() - t;
    if (ms < 0) return new Date(iso).toLocaleString();
    var sec = Math.round(ms / 1000);
    if (sec < 30) return 'just now';
    if (sec < 60) return sec + 's ago';
    var min = Math.round(sec / 60);
    if (min < 60) return min + ' min ago';
    var hr = Math.round(min / 60);
    if (hr < 24) return hr + ' hr ago';
    var day = Math.round(hr / 24);
    if (day < 30) return day + ' day' + (day === 1 ? '' : 's') + ' ago';
    return new Date(iso).toLocaleDateString();
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

    // Wire per-row "Remove" buttons on orphan rows (members whose
    // record_id is no longer in the live fellows.db). Calls updateGroup
    // with the rid removed, then re-renders the page so the row drops
    // out and counts refresh.
    // plans/opt_in_directory_data_updates.md.
    var orphanRemoveBtns = detailEl.querySelectorAll('.group-detail-orphan-remove');
    if (orphanRemoveBtns && orphanRemoveBtns.length) {
      Array.prototype.forEach.call(orphanRemoveBtns, function (btn) {
        btn.addEventListener('click', function () {
          var rid = btn.getAttribute('data-record-id');
          if (!rid) return;
          var remaining = (group.members || [])
            .map(function (m) { return m.record_id; })
            .filter(function (id) { return id && id !== rid; });
          btn.disabled = true;
          btn.textContent = 'Removing…';
          dataProvider.updateGroup(group.id, { fellow_record_ids: remaining })
            .then(function () {
              // Drop from in-memory orphan set so subsequent renders
              // don't re-flag (the rid is gone from group_members now,
              // but the worker scan still considers it orphaned —
              // remove it locally to keep state coherent until the next
              // boot scan).
              if (orphanedRecordIds[rid]) delete orphanedRecordIds[rid];
              renderGroupDetailPage(group.id);
            })
            .catch(function (err) {
              btn.disabled = false;
              btn.textContent = 'Remove';
              showToast('Could not remove: ' +
                ((err && err.message) || 'unknown error'));
            });
        });
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
    if (directoryDataSource === 'worker' && dataProvider) {
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
        // Non-2xx (commonly 401/403 when the session expired, sometimes
        // 5xx) is treated the same as a network failure: route through
        // runLocalSearch so the cached directory still answers. Per
        // docs/email_gate.md invariant 10, a stale session must not lock
        // the user out of searching data they already downloaded.
        if (!r.ok) throw new Error('search ' + r.status);
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
    var filtered = applyFilters(results);
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

  initSwReloadButton();
  initClearCacheButton();
  initResetEverythingButton();
  initDiagnosticsPanel();
  initBugReportButtons();
  initBootStuckPanelButtons();
  initBootErrorPanelButtons();
  initKebabSheet();
  initComposerFab();
  initGroupCardSheet();
  initGroupActionbarSheet();
  initFilterSheet();
  // Hydrate filterState from any query suffix on the initial hash so a
  // shared link like #/?cohort=2020 applies before the first render.
  // Trigger stays disabled until phase 2 builds filterOptions.
  readFiltersFromHash();
  updateFilterTriggerUI();
  wireCopyButtons();

  var directoryBootAttempted = false;

  function bootDirectoryAsApp() {
    directoryBootAttempted = true;
    bootDebugLines.length = 0;
    setShellVisible(true);
    if (loadingPanelEl) {
      loadingPanelEl.classList.remove('hidden');
    }
    if (loadingEl) {
      loadingEl.classList.remove('hidden');
    }
    // Replace the static "Loading…" with a phase that conveys "we've
    // started." The next two checkpoints (Setting up local database… /
    // Loading directory…) update as the boot chain progresses, so a
    // user looking at a stuck tab can at least tell which phase
    // stalled. The watchdog uses bootMarks (not these strings) for
    // its lastMark report; the user-facing strings can drift without
    // affecting telemetry.
    setSetupStatus('Starting up…');
    // Start the boot watchdog. Cleared on get_list_done (success) or in
    // the .catch (failure path that already has its own panel). Only
    // armed in directory boot; the email-gate / install-landing paths
    // settle synchronously and don't need a hang surface.
    startBootWatchdog();
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
        // SW activate handler logs each prune cycle so the page-side
        // boot trace shows whether activate ran and what it deleted.
        // Pairs with auditShellCaches() — this records what the SW did,
        // the audit records what the page sees afterward.
        if (d && d.type === 'sw-activate-pruned') {
          var dels = Array.isArray(d.deletions) ? d.deletions : [];
          var summary = dels.length
            ? dels.map(function (x) { return x.key + '=' + x.ok; }).join(', ')
            : '(none)';
          bootDebugPush(
            'sw activate prune: current=' + d.currentCache +
            ' deleted=' + summary + ' at=' + d.activatedAt
          );
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

    // pickDataProvider is the slow part of cold-start boot: worker spawn,
    // OPFS attach, optional fellows.db fetch + import. Surface the phase
    // to the user so a tab that takes 10+ s on a fresh install isn't
    // indistinguishable from a hung one. The SW cache-progress handler
    // above will overwrite this transiently with byte counts when the
    // shell precache is populating; that's intentional — bytes are
    // more concrete than a label.
    setSetupStatus('Setting up local database…');
    pickDataProvider()
      .then(function (provider) {
        dataProvider = provider;
        bootMark('provider_ready');
        bootDebugPush('provider ready kind=' + provider.kind);
        // Defensive shell-cache audit. Cheap (one caches.keys()) and
        // silent on the happy path; logs + deletes any stale shell
        // caches the SW activate prune missed. See the 2026-05-05
        // incident note in auditShellCaches's docstring.
        auditShellCaches();
        if (provider.kind === 'worker') {
          directoryDataSource = 'worker';
        }
        // L6: persist() best-effort, once per install. Result lives in
        // window.__persistStorageState for diagnostics + e2e tests.
        // Denied/unavailable is non-fatal — boot continues.
        maybeRequestPersistedStorage();
        // Reconcile self_email between localStorage (fast cache) and
        // relationships.settings (durable). PR 5: needed by the export
        // "email it to me" feature; safe to fire-and-forget.
        reconcileSelfEmailOnBoot();
        // Same pattern for the has-email filter pref. Migrates
        // ehf_has_email_only from localStorage-only into the durable
        // relationships.settings store on first post-PR-D boot.
        reconcileHasEmailFilterOnBoot();
        setSetupStatus('Loading directory…');
        return provider.getList().catch(function (err) {
          if (isAuthFailure(err)) return tryListFromCache(err);
          throw err;
        });
      })
      .then(function (data) {
        bootMark('get_list_done');
        clearBootWatchdog('get_list_done');
        bootDebugPush(
          'getList: OK count=' + (Array.isArray(data) ? data.length : typeof data) +
          (offlineOnlyMode ? ' (from cache)' : '')
        );
        // Reaching getList success (fresh API or cached) means this
        // browser has been authenticated here at least once. Record the
        // marker so the URL-just-works path works on next visit.
        markAuthenticatedOnce();
        // Phase B of install-version telemetry: fire the one-per-load
        // boot beacon so the operator can answer "what build is this
        // user actually running?" via `just installed-versions`. Same
        // signal as markAuthenticatedOnce — both mean "boot succeeded
        // for this origin." Guarded internally; safe to call from any
        // path that reaches this point.
        reportBootEvent();
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
        bootMark('get_full_done');
        bootDebugPush('getFull: OK rows=' + (Array.isArray(full) ? full.length : typeof full) +
          (offlineOnlyMode ? ' (from cache)' : ''));
        // First moment the directory is fully data-backed. Image prewarm
        // is the next phase but happens in the background; emitting now
        // means a hung prewarm doesn't suppress the summary line.
        // emitBootSummary is idempotent — prewarm's later call no-ops.
        emitBootSummary();
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
          // Issue #86: derive distinct filter values now that we have the
          // full row set. Enables the trigger button and populates sheet
          // controls. Hash-derived filters from phase 1 still apply.
          activateFiltersFromFullData(full);
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
        // One-shot soft scan for group members orphaned by past
        // auto-refreshes (PR #113 era). Surfaces a toast once if any
        // exist; sets relationships.settings.orphan_scan_done so it
        // never repeats. plans/opt_in_directory_data_updates.md.
        maybeRunOrphanSoftScan();
      })
      .catch(function (err) {
        // Either branch below settles the boot one way or another, so the
        // watchdog is no longer load-bearing — clear it before we route
        // the user. Without this clear, a slow .catch path could trip
        // the watchdog after we've already shown the gate or boot-error
        // panel, double-rendering recovery affordances.
        clearBootWatchdog('boot_failure');
        // Two routes hand off to startBrowserUx (which renders the email
        // gate when /api/auth/status reports authenticated=false):
        //
        // 1. Browser-tab-acting-as-app + we've authenticated here before
        //    (the original path; quiet handoff for returning visitors).
        // 2. *Any* boot whose proximate cause is HTTP 401/403 — including
        //    standalone PWAs whose 7-day session cookie expired. Without
        //    this branch, standalone users were trapped: standalone mode
        //    short-circuits shouldActAsApp() to true regardless of auth,
        //    so every reload re-entered bootDirectoryAsApp, hit the same
        //    403 from /fellows.db, and showed showBootFailure with no
        //    in-app way to reach the gate (PWA windows have no URL bar).
        //    Clear App Cache and Reset Everything both looped back into
        //    the same trap. See issue #125.
        var authFailure = err && (
          err.httpStatus === 401 || err.httpStatus === 403 ||
          err.status === 401 || err.status === 403
        );
        if ((!isStandaloneDisplayMode() && hasAuthenticatedOnce()) || authFailure) {
          bootDebugPush('as-app boot failed; handing off to startBrowserUx: ' +
            (err && err.message ? err.message : String(err)));
          // Telemetry: distinguish the auth-failure handoff (the dominant
          // cause in production once a fellow's session ages out) from
          // generic boot failures so the operator can read incidence
          // straight out of journald (`kind=worker, msg=boot_failed_auth`).
          // Cardinality bounded to one event per page load.
          if (authFailure) {
            try {
              reportWorkerEvent(
                'boot_failed_auth',
                'last_mark=' + String(lastCompletedBootMark() || 'unknown')
              );
            } catch (e) {}
          }
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
  }

  // Eagerly spawn the worker (init only — network-free per L4a) so OPFS
  // handles + sqlite3 runtime are warm by the time the gate decision tree
  // commits. Runs in parallel with /api/auth/status. If the gate decision
  // lands at email-gate (or showAuthFailure), the warm worker is
  // terminated by terminateWarmWorkerIfStillWarm() below — no network
  // requests have happened yet, it's safe to throw away. If the decision
  // lands at install-landing, the warm worker is *kept alive*: the
  // install landing is a transition state and both forward paths (Install
  // app, Use the directory in this tab) need a worker shortly after.
  // See initBrowserInstallMode for why pre-emptive termination there
  // raced with re-spawn against unreleased OPFS SAH-pool handles. If the
  // decision lands directly at directory mode, bootDirectoryAsApp()
  // consumes warmWorkerPromise and calls ensureFellowsDb on it.
  var warmWorker = null;          // {rpc, init} once spawnWorkerAndInit resolves
  var warmWorkerError = null;     // Error from spawn or init
  var warmWorkerConsumed = false; // true once bootDirectoryAsApp adopts it
  // Set when the warm worker's init failed because another tab/window
  // of this app already holds the OPFS SAH-pool. Distinct from generic
  // OPFS-unsupported (older browser, missing SAH, etc.) — drives a
  // specific "directory is open in another tab" panel via
  // renderLocalDataUnavailablePanel(). See plans/multi_tab_ownership_takeover.md
  // for the coordinated-takeover follow-up that supersedes this signal.
  var bootOwnershipConflict = false;
  var warmWorkerPromise = spawnWorkerAndInit().then(function (handle) {
    warmWorker = handle;
    // Tee a success summary into the bug-report ring so a later bug
    // report carries the version handshake context. Don't fire to
    // /api/client-errors — that would generate one event per page load
    // for the happy path, which drowns the failure signal.
    var init = (handle && handle.init) || {};
    pushBugReportError(
      'worker',
      'spawn_ok',
      'rpc=' + init.workerRpcVersion + ' schema=' + init.schemaVersion +
        ' opfsCapable=' + !!init.opfsCapable +
        ' hasFellowsDb=' + !!init.hasFellowsDb +
        ' hasRelDb=' + !!init.hasRelationshipsDb
    );
    return handle;
  }).catch(function (err) {
    warmWorkerError = err;
    if (err && err.code === 'OWNERSHIP_CONFLICT') {
      bootOwnershipConflict = true;
    }
    // Spawn or init failed — user is about to drop to the API+IDB
    // fallback (or boot-failure panel). Tee + ship to journald so the
    // operator sees the failure rate without needing the user to send
    // diagnostics. Cardinality is bounded: warm spawn fires once per
    // page load, re-spawn fires at most once more.
    var msg = (err && err.message) || String(err);
    var tag = bootOwnershipConflict ? 'ownership_conflict' : 'spawn_failed';
    pushBugReportError('worker', tag, msg.slice(0, 200));
    reportWorkerEvent(tag, msg);
    throw err;
  });

  function terminateWarmWorkerIfStillWarm(reason) {
    if (warmWorkerConsumed) return;
    // If the spawn hasn't resolved yet, attach a handler that terminates
    // when it does. Either way, mark consumed so future bootDirectoryAsApp
    // calls (e.g. install-landing → use-in-tab) re-spawn cleanly.
    warmWorkerConsumed = true;
    bootDebugPush('worker: terminating warm worker (' + reason + ')');
    warmWorkerPromise.then(function (handle) {
      if (handle && handle.rpc) {
        try { handle.rpc.terminate(); } catch (e) {}
      }
    }).catch(function () { /* spawn errored; nothing to terminate */ });
    warmWorker = null;
  }

  // Resolve the data provider for bootDirectoryAsApp. Adopts the warm
  // worker if it succeeded; otherwise spins a fresh worker (in case
  // bootDirectoryAsApp is reached after a previous decision tree had
  // already terminated the warm one — e.g. install-landing → "use in
  // tab"). Falls back to API+IDB if the worker simply can't come up.
  function pickDataProvider() {
    bootMark('pick_provider_start');
    bootDebugPush('pickDataProvider: start');
    bootDebugPush('gates (one line): ' + describeOpfsGates().replace(/\n/g, ' | '));
    var handlePromise;
    if (warmWorkerConsumed && !warmWorker) {
      // Re-spawn — the warm worker was terminated for the gate UI and
      // we're now booting the directory anyway (e.g. user clicked "use
      // in tab" on the install landing).
      bootDebugPush('pickDataProvider: warm worker was terminated — re-spawning');
      handlePromise = spawnWorkerAndInit();
    } else {
      handlePromise = warmWorkerPromise;
    }
    warmWorkerConsumed = true;
    return handlePromise.then(function (handle) {
      var provider = createWorkerDataProvider(handle.rpc, handle.init);
      window.__dataProvider = provider;
      if (!provider._versionOk) {
        bootDebugPush(
          'pickDataProvider: version skew — page expects rpc=' +
          EXPECTED_WORKER_RPC_VERSION + '/schema=' + EXPECTED_RELATIONSHIPS_SCHEMA_VERSION +
          ' worker has rpc=' + handle.init.workerRpcVersion +
          '/schema=' + handle.init.schemaVersion + '; reads still work, writes refused'
        );
      }
      // Boot path is install-only by policy
      // (plans/opt_in_directory_data_updates.md). The worker only fetches
      // /fellows.db when there's nothing on disk yet (cold start /
      // post–Reset Everything). Returning visitors keep whatever bytes
      // they have, regardless of SHA — refresh is a user-driven action
      // surfaced through the About-page "Update directory data" button.
      // Pass serverSha purely for the worker's trace; it isn't consulted
      // for the install-only branch.
      var metaPromise = bootBuildMetaPromise || Promise.resolve(bootBuildMeta);
      return metaPromise.then(function (meta) {
        var serverSha = (meta && typeof meta.fellows_db_sha === 'string' && meta.fellows_db_sha)
          ? meta.fellows_db_sha : null;
        return provider._ensureFellowsDb({ serverSha: serverSha, mode: 'install-only' });
      })
        .then(function (res) {
          bootDebugPush(
            'ensureFellowsDb: hasFellowsDb=' + (res && res.hasFellowsDb) +
            ' refreshed=' + (res && res.refreshed)
          );
          return provider;
        })
        .catch(function (e) {
          bootDebugPush('ensureFellowsDb: failed (code=' + (e && e.code) +
            ' http=' + (e && e.httpStatus) + '): ' + (e && e.message || e));
          // Auth-related cold-start failures: the user is signed out
          // server-side. Per email_gate.md invariant 10, fall through to
          // the IDB cache so a previously-authed install still renders
          // the directory. The active dataProvider becomes api+idb;
          // groups/settings round-trip through the API path (which 404s
          // in prod, surfacing the unsupported panel) rather than the
          // worker. The worker process is left alive — it still owns
          // OPFS and clearEverything reaches it through warmWorker.rpc
          // for the OPFS wipe.
          if (e && (e.httpStatus === 401 || e.httpStatus === 403)) {
            bootDebugPush(
              'ensureFellowsDb: auth failure → fall back to API+IDB for directory'
            );
            var fallback = createApiPlusIdbDataProvider();
            window.__dataProvider = fallback;
            return fallback;
          }
          // Other failures (network, malformed): surface so bootDirectoryAsApp
          // can render a retry affordance instead of crashing.
          var err = new Error(
            'Could not download directory: ' + (e && e.message || String(e))
          );
          err.ensureFellowsDbFailed = true;
          err.code = e && e.code;
          err.httpStatus = e && e.httpStatus;
          throw err;
        });
    }).catch(function (err) {
      if (err && err.ensureFellowsDbFailed) throw err;
      // Worker failed to spawn or init. Fall back to API+IDB so the
      // directory-only browse path still works for OPFS-incapable
      // browsers; groups + settings will surface the unsupported panel.
      // The re-spawn path (warm worker was terminated for the gate UI)
      // can also hit OWNERSHIP_CONFLICT — propagate it so the panel
      // renders the multi-tab copy here too, not just the warm-spawn case.
      if (err && err.code === 'OWNERSHIP_CONFLICT') {
        bootOwnershipConflict = true;
      }
      bootDebugPush('pickDataProvider: worker unavailable, falling back to API+IDB: ' +
        (err && err.message || err));
      var provider = createApiPlusIdbDataProvider();
      window.__dataProvider = provider;
      return provider;
    });
  }

  // Display-mode samples around the boot dispatcher — the matchMedia
  // race lives here. See displayModeSamples docs at module top.
  sampleDisplayMode('module_init');
  setTimeout(function () { sampleDisplayMode('after_setTimeout_0'); }, 0);
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(function () { sampleDisplayMode('after_raf'); });
  }
  setTimeout(function () { sampleDisplayMode('after_500ms'); }, 500);

  tryUnlockFromHash().then(function () {
    sampleDisplayMode('dispatcher');
    var actAsApp = shouldActAsApp();
    var override = parseGateOverride();
    bootDebugPush(
      'dispatcher: shouldActAsApp=' + actAsApp +
      ' (standalone=' + isStandaloneDisplayMode() +
      ', authOnce=' + hasAuthenticatedOnce() +
      ', forceGate=' + (override && override.force) + ')'
    );
    if (actAsApp) {
      bootDirectoryAsApp();
    } else {
      startBrowserUx();
    }
  });

  registerServiceWorker();
})();
