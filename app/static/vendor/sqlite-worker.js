// EHF Fellows local DB — sqlite-wasm worker (sole OPFS owner).
//
// Runs sqlite-wasm + OPFS-SAH-Pool in dedicated-worker scope and is the
// only context in the app permitted to call navigator.storage.getDirectory
// or open a FileSystemSyncAccessHandle. The main thread is an RPC client
// per plans/local_first_worker_architecture.md (Phase 1) and
// docs/Architecture.md § Worker-owned OPFS.
//
// Two databases live here:
//   - relationships.db (read-write user-authored data: groups, members,
//     fellow_tags, fellow_notes, settings)
//   - fellows.db (read-only contact data; cached locally, refreshed by the
//     page-driven ensureFellowsDb RPC; SHA-keyed refresh ships in Phase 3)
//
// Protocol:
//   main → worker: { id, op, args }
//   worker → main: { id, ok: true,  result }
//                  { id, ok: false, error, errorName?, stack? }
//
// First message must be op='init'. The init response is a handshake blob:
//   { ok, workerRpcVersion, schemaVersion, buildLabel,
//     opfsCapable, hasFellowsDb, hasRelationshipsDb,
//     poolFiles, trace }
// The page reads workerRpcVersion + schemaVersion and refuses mutating
// RPCs on mismatch (passive — the SW's existing reload banner is the
// canonical update affordance).

'use strict';

// Sibling import — this file lives in /vendor/ alongside sqlite3.js.
// The relative path is what makes sqlite-wasm's scriptDirectory resolve
// to /vendor/, so its internal locateFile('sqlite3.wasm') finds the
// companion /vendor/sqlite3.wasm.
importScripts('./sqlite3.js');

// ===== Compatibility constants ==============================================
// Bumped only when the request/response shape of any RPC changes (parameters,
// return shape, error semantics). A pure code refactor that preserves the
// wire shape leaves it alone. Page reads this in the init handshake and
// refuses mutating RPCs on mismatch.
//
// v2 (Phase 3): ensureFellowsDb({serverSha}) gained an optional serverSha
// arg and SHA-keyed refresh semantics. Page bumps its expected value in
// lockstep; a stale page paired with this worker (or vice versa) refuses
// mutations and waits for the SW's "New version available" reload banner.
// v3 (issue #165 P1): user-folder durable storage RPCs added —
// setFolderHandle / getFolderState / clearFolderHandle / checkFolderPermission /
// getFolderHandleForReconnect / writeRelationshipsToFolder /
// readRelationshipsFromFolder. Reads (getFolderState, checkFolderPermission)
// are version-tolerant — the page is allowed to read folder state even
// against a stale worker — but the mutating ops are version-gated alongside
// the existing relationships.db writes.
var WORKER_RPC_VERSION = 3;

// Same value as relationships.db's PRAGMA user_version. Bumped only on
// schema migrations. Mirrored from app/relationships.py:SCHEMA_VERSION.
var RELATIONSHIPS_SCHEMA_VERSION = 1;

// Substituted at build time by build/build_pwa.py and at serve time by
// app/server.py (same substitution path as app.js / sw.js). If you ever
// see the literal `__FELLOWS_UI_DIAG__` in diagnostics, the build pipeline
// didn't touch this file.
var BUILD_LABEL = '__FELLOWS_UI_DIAG__';

// ===== Schema (mirrored from app.js — keep in sync) =========================

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

// ===== Fellows.db column / label tables (mirrored from app/server.py) =======

var FELLOW_COLUMNS = [
  'record_id', 'slug', 'name', 'bio_tagline', 'fellow_type', 'cohort',
  'contact_email', 'key_links', 'key_links_urls', 'image_url',
  'currently_based_in', 'search_tags', 'fellow_status', 'gender_pronouns',
  'ethnicity', 'primary_citizenship', 'global_regions_currently_based_in',
  'has_image'
];

// Friendly labels used by getStats — mirror app/server.py:get_stats.
var COL_LABELS = {
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

var EXTRA_LABELS = {
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

// ===== Backup / staging / meta-file constants ===============================

var BACKUP_PREFIX = 'relationships.db.bak.';
// Per Phase 0 Q-C resolution: rotation increased from 3 to 5 (files are
// tiny — tens of KB even for an active user). Rationale lives in
// docs/persistence_and_upgrades.md § Auto-backup of `relationships.db`.
var BACKUP_KEEP = 5;
// Per Phase 0 Q-C: skip the per-boot snapshot if the most recent
// backup is younger than this. Keeps debug-session reloads from
// thrashing the rotation.
var BACKUP_DEBOUNCE_MS = 60 * 60 * 1000;

// One-time cleanup target. The pre-Phase-1 main-thread auto-backup wrote
// this sentinel; the worker-owned debounce derives its trigger from the
// newest bak.<ISO> filename instead. Kept so we can removeEntry() it on
// the first boot of a P1+ build.
var LEGACY_SENTINEL = 'last_seen_sha.txt';

// SAH-pool VFS internally canonicalizes filenames to leading-slash form,
// so importDb('foo') stores under 'foo' but new OpfsSAHPoolDb('foo')
// opens '/foo'. The mismatch silently allocates a fresh empty SAH for
// '/foo', and the imported bytes are unreachable. Use leading-slash
// names consistently so importDb and OpfsSAHPoolDb hit the same SAH.
var RELATIONSHIPS_DB_SLOT = '/relationships.db';
var FELLOWS_DB_SLOT = '/fellows.db';
var RESTORE_STAGING_SLOT = '/relationships.db.restore-staging';
var FELLOWS_STAGING_SLOT = '/fellows.db.staging';
// Distinct from FELLOWS_STAGING_SLOT — the boot-path ensureFellowsDb
// staging slot is short-lived (open, validate, swap, close in one tick)
// while the user-driven swap can sit pending across the confirm dialog.
// Using separate slots avoids any chance of one path stomping the other,
// even though under the opt-in policy ensureFellowsDb only fires at cold
// start.
var FELLOWS_SWAP_STAGING_SLOT = '/fellows.db.swap-staging';
var FELLOWS_META_FILE = 'fellows.db.meta.json';

var REQUIRED_RESTORE_TABLES = ['groups', 'group_members', 'fellow_tags', 'fellow_notes', 'settings'];

// ===== State ================================================================

var sqlite3 = null;
var poolUtil = null;
var relDb = null;
var fellowsDb = null;
var bootTrace = [];

// Storage mode for relationships.db, resolved during init. Two values:
//   'opfs'   — OPFS-resident SAH-pool VFS is the source of truth. Today's
//              behavior for Safari / Firefox / iOS / Android Chrome users
//              without a folder picker, plus the brief window where a
//              capable user hasn't yet set up a data folder.
//   'folder' — User's filesystem folder is the source of truth. The OPFS
//              slot is used as a synchronous working buffer that is
//              hydrated from folder bytes on boot and written back
//              atomically to the folder after every committed mutation.
//              The buffer is reset from the folder on every session boot —
//              folder is canonical, OPFS is transient.
// See plans/user_folder_storage.md § Architecture (revised 2026-05-22)
// and docs/ac_decisions_log.md § 2026-05-22 — User-folder storage uses
// pure-folder semantics for folder-mode users, not a hybrid OPFS+folder
// mirror.
var _storageMode = 'opfs';

// User-driven directory-data update, between previewFellowsDbSwap and
// applyFellowsDbSwap / cancelFellowsDbSwap. Holds the SHA + an opaque
// stagingId that the page must echo back. Bytes live in the staging
// slot, not in JS memory.
var pendingFellowsDbSwap = null;

function trace(msg) { bootTrace.push(new Date().toISOString() + ' ' + String(msg)); }

// Recognize the SAH ownership-conflict failure that
// installOpfsSAHPoolVfs() throws when another tab's worker already holds
// the pool's capacity-file SAHs. Detection is name-first (Chrome surfaces
// it as DOMException 'NoModificationAllowedError') with a message-substring
// fallback for engines that haven't standardized the name yet. Conservative
// — anything not matching falls through as a generic init failure.
function isOwnershipConflictError(e) {
  if (!e) return false;
  if (e.name === 'NoModificationAllowedError') return true;
  var msg = String((e && e.message) || e || '');
  return /another open (?:Access Handle|Writable stream)/i.test(msg) ||
         /Access Handles? cannot be created/i.test(msg);
}

// ===== SQL helpers ==========================================================

function dbSelectAll(db, sql, bind) {
  var st = db.prepare(sql);
  var out = [];
  try {
    if (bind !== undefined && bind !== null) st.bind(bind);
    while (st.step()) out.push(st.get({}));
  } finally { st.finalize(); }
  return out;
}

function dbSelectOne(db, sql, bind) {
  var rows = dbSelectAll(db, sql, bind);
  return rows.length ? rows[0] : null;
}

function dbRun(db, sql, bind) {
  var st = db.prepare(sql);
  try {
    if (bind !== undefined && bind !== null) st.bind(bind);
    st.step();
  } finally { st.finalize(); }
}

function bootstrapRelationshipsSchema(db) {
  // PRAGMA foreign_keys is per-connection and defaults OFF. Without it,
  // group_members.group_id's `ON DELETE CASCADE` is silently inert and
  // deleteGroup leaves orphan rows in OPFS forever. Mirrors
  // app/relationships.py:296. Must run on every relDb open (init +
  // post-restore importRelationshipsBytes) since this resets each time
  // a connection is closed.
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec(RELATIONSHIPS_SCHEMA_SQL);
  db.exec('PRAGMA user_version = ' + RELATIONSHIPS_SCHEMA_VERSION);
}

function nowIsoSecond() {
  return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
}

function dedupeRecordIds(ids) {
  var seen = {}, out = [];
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

// Mirrors app/server.py:row_to_fellow. Parses the key_links_urls JSON
// column and merges extra_json into the top-level object so the API
// returns all original fields without per-field schema knowledge.
function rowToFellow(row) {
  var out = {};
  for (var i = 0; i < FELLOW_COLUMNS.length; i++) {
    var key = FELLOW_COLUMNS[i];
    var val = row[key];
    if (key === 'key_links_urls' && val !== null && val !== undefined) {
      try { out[key] = JSON.parse(val); } catch (e) { out[key] = val; }
    } else {
      out[key] = val !== undefined ? val : null;
    }
  }
  if (row.extra_json) {
    try {
      var extra = JSON.parse(row.extra_json);
      if (extra && typeof extra === 'object' && !Array.isArray(extra)) {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) out[k] = extra[k];
        }
      }
    } catch (e2) {}
  }
  return out;
}

// ===== OPFS root file helpers ===============================================

async function _opfsRoot() { return await self.navigator.storage.getDirectory(); }

async function _opfsReadText(name) {
  try {
    var root = await _opfsRoot();
    var fh = await root.getFileHandle(name);
    var f = await fh.getFile();
    return await f.text();
  } catch (e) { return null; }
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

async function _opfsRemoveEntry(name) {
  try {
    var root = await _opfsRoot();
    await root.removeEntry(name);
    return true;
  } catch (e) {
    return false;
  }
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
  } catch (e) { return []; }
}

async function _rotateRelationshipsBackups() {
  var backups = await listRelationshipsBackups();
  var root = await _opfsRoot();
  while (backups.length > BACKUP_KEEP) {
    var oldest = backups.shift();
    try {
      await root.removeEntry(oldest.name);
      trace('backup: rotated out ' + oldest.name);
    } catch (e) {
      trace('backup: rotate removeEntry failed for ' + oldest.name);
    }
  }
}

// ----- Backup store routing (Phase 2 pivot) ---------------------------------
//
// In folder mode the auto-backup ring lives in the user's folder
// (siblings of relationships.db). In OPFS-only mode it stays in
// OPFS, unchanged. The dynamic check below mirrors the per-commit
// hook in _maybeWriteFolderAfterCommit — a user who attached a
// folder mid-session sees subsequent backups land in the folder
// alongside the per-commit writes; a user whose permission lapsed
// gets OPFS-resident backups as a fallback. Source of truth for
// the ring at any moment is whichever store the per-commit hook
// would also be writing to.
//
// Dependencies (defined later in the user-folder-storage section
// — JS function-declaration hoisting means call order is fine,
// but they're noted here for orientation):
//   _listFolderBackups, _folderReadBackup, _rotateFolderBackups,
//   _writeBytesToFolder, _folderQueryPermission, folderRecord.

async function _isFolderBackupActive() {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) return false;
  var perm = await _folderQueryPermission();
  return perm === 'granted';
}

async function _listActiveBackups() {
  if (await _isFolderBackupActive()) return await _listFolderBackups();
  return await listRelationshipsBackups();
}

async function _writeBackupToActiveStore(name, bytes) {
  if (await _isFolderBackupActive()) {
    // Reuse _writeBytesToFolder — it handles atomic write semantics
    // and only updates folderRecord.lastSavedAt for the canonical
    // relationships.db filename, so backup writes don't muddy that
    // signal.
    await _writeBytesToFolder(bytes, name);
    return;
  }
  await _opfsWriteBinary(name, bytes);
}

async function _rotateActiveBackups() {
  if (await _isFolderBackupActive()) {
    await _rotateFolderBackups();
    return;
  }
  await _rotateRelationshipsBackups();
}

async function _readActiveBackup(name) {
  if (await _isFolderBackupActive()) return await _folderReadBackup(name);
  return await _opfsReadBinary(name);
}

// One-time migration of the OPFS-resident backup ring into the
// user's folder. Runs whenever we boot in folder mode AND find
// stragglers in OPFS (opportunistic — naturally idempotent because
// the migration deletes the OPFS originals, so subsequent boots
// find nothing left to move). Per Rich's "rip the band-aid off"
// call (2026-05-22 conversation): we DO delete the OPFS originals,
// but we copy the bytes to the folder first so backup history is
// preserved in a discoverable place.
async function _maybeMigrateOpfsBackupsToFolder() {
  if (!(await _isFolderBackupActive())) return;
  var opfsBackups = await listRelationshipsBackups();
  if (!opfsBackups.length) return;
  trace('backup-ring: migrating ' + opfsBackups.length +
    ' OPFS bak.* file(s) into folder/' + folderRecord.subfolderName + '/');
  var migrated = 0;
  for (var i = 0; i < opfsBackups.length; i++) {
    var entry = opfsBackups[i];
    try {
      var bytes = await _opfsReadBinary(entry.name);
      await _writeBytesToFolder(bytes, entry.name);
      await _opfsRemoveEntry(entry.name);
      migrated++;
    } catch (e) {
      trace('backup-ring: migrate ' + entry.name + ' failed (' +
        (e && e.message || e) + ') — leaving OPFS copy in place for safety');
    }
  }
  if (migrated) {
    trace('backup-ring: migrated ' + migrated + '/' + opfsBackups.length +
      ' OPFS backups → folder; rotating to ' + BACKUP_KEEP + ' newest');
    await _rotateFolderBackups();
  }
}

// ===== Auto-backup (debounced per-boot) =====================================

// Per Phase 0 Q-C: trigger flips from "build-SHA differs" to "newest
// bak.<ISO> older than 1 hour." Recovery use case ("undo what I just
// did") is keyed to user-edit cadence, not deploy cadence. The
// last_seen_sha.txt sentinel is retired; debounce reads the most recent
// bak filename's timestamp instead.
async function maybeBackupRelationshipsDb() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) === -1) {
    trace('backup: skipped (no relationships.db yet — first install)');
    return { backedUp: false, reason: 'first install' };
  }
  // Active store is folder when folder-mode permission is granted,
  // otherwise OPFS. The debounce timer reads "newest bak.<ISO>" from
  // whichever store we're actually writing to, so it stays consistent
  // across mode transitions (e.g., a user who attached a folder
  // mid-session and just migrated existing OPFS backups into it).
  var backups = await _listActiveBackups();
  if (backups.length) {
    var newest = backups[backups.length - 1];
    var ageMs = Date.now() - newest.lastModified;
    if (ageMs >= 0 && ageMs < BACKUP_DEBOUNCE_MS) {
      trace('backup: skipped (newest ' + newest.name + ' is ' +
            Math.round(ageMs / 1000) + 's old, debounce ' +
            Math.round(BACKUP_DEBOUNCE_MS / 1000) + 's)');
      return { backedUp: false, reason: 'debounced' };
    }
  }
  var bytes;
  try { bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT); }
  catch (e) {
    trace('backup: exportFile failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'export failed' };
  }
  if (!bytes || !bytes.byteLength) {
    return { backedUp: false, reason: 'empty file' };
  }
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _writeBackupToActiveStore(backupName, bytes); }
  catch (e) {
    trace('backup: write failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'write failed' };
  }
  await _rotateActiveBackups();
  var storeLabel = (await _isFolderBackupActive()) ? 'folder' : 'opfs';
  trace('backup: wrote ' + backupName + ' to ' + storeLabel + ' (' + bytes.byteLength + ' bytes)');
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

async function snapshotRelationshipsDbToBackup() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) === -1) {
    return { backedUp: false, reason: 'no relationships.db' };
  }
  var bytes;
  try { bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT); }
  catch (e) { return { backedUp: false, reason: 'export failed: ' + (e && e.message || e) }; }
  if (!bytes || !bytes.byteLength) return { backedUp: false, reason: 'empty file' };
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _writeBackupToActiveStore(backupName, bytes); }
  catch (e) { return { backedUp: false, reason: 'write failed: ' + (e && e.message || e) }; }
  await _rotateActiveBackups();
  var storeLabel = (await _isFolderBackupActive()) ? 'folder' : 'opfs';
  trace('snapshot: wrote ' + backupName + ' to ' + storeLabel + ' (' + bytes.byteLength + ' bytes)');
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

// ===== fellows.db.meta.json (freshness sidecar) =============================
// Sibling of fellows.db at the OPFS root, outside the SAH-pool dir, so a
// relationships.db restore can't desync fellows.db freshness. The page
// passes the server-reported `fellows_db_sha` (read from /build-meta.json)
// into ensureFellowsDb; the worker compares it to `meta.sha` to decide
// whether to re-fetch.

async function readFellowsMeta() {
  var raw = await _opfsReadText(FELLOWS_META_FILE);
  if (!raw) return null;
  try {
    var obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') return obj;
  } catch (e) {}
  return null;
}

async function writeFellowsMeta(meta) {
  await _opfsWriteText(FELLOWS_META_FILE, JSON.stringify(meta));
}

// SubtleCrypto digest of `bytes` as lowercase hex. Identical output to the
// build pipeline's `hashlib.sha256(...).hexdigest()` — the comparison hinges
// on byte-for-byte agreement between the dist DB and what the worker
// fetches over the wire, so the digest function on both sides has to round
// to the same string.
async function _sha256Hex(bytes) {
  var buf = await crypto.subtle.digest('SHA-256', bytes);
  var view = new Uint8Array(buf);
  var hex = '';
  for (var i = 0; i < view.length; i++) {
    var b = view[i];
    hex += (b < 16 ? '0' : '') + b.toString(16);
  }
  return hex;
}

// ===== Inspect bytes (used by import + listRelationshipsBackups) =============

async function inspectBytes(bytes) {
  if (!poolUtil) return { valid: false, error: 'pool util unavailable' };
  if (!bytes || !bytes.byteLength) return { valid: false, error: 'File is empty.' };
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
    var tableRows = dbSelectAll(tmp, "SELECT name FROM sqlite_master WHERE type='table'", null);
    var tableNames = tableRows.map(function (r) { return r.name; });
    var missing = REQUIRED_RESTORE_TABLES.filter(function (t) { return tableNames.indexOf(t) === -1; });
    if (missing.length) {
      return {
        valid: false,
        error: 'File is missing expected tables: ' + missing.join(', ') +
          '. Is this a relationships.db backup?'
      };
    }
    return {
      valid: true,
      counts: {
        groups: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM groups', null).n,
        members: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM group_members', null).n,
        tags: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
        notes: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
        settings: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM settings', null).n
      }
    };
  } catch (e) {
    return { valid: false, error: (e && e.message) || String(e) };
  } finally {
    if (tmp) { try { tmp.close(); } catch (e2) {} }
  }
}

// ===== fellows.db lifecycle =================================================

function _openFellowsDbIfPresent() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(FELLOWS_DB_SLOT) === -1) {
    return false;
  }
  try {
    fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
    trace('fellows.db: open OK');
    return true;
  } catch (e) {
    trace('fellows.db: open failed (' + (e && e.message || e) + ')');
    fellowsDb = null;
    return false;
  }
}

// ===== RPC handlers =========================================================

var handlers = {};

handlers.init = async function () {
  trace('init: starting (build=' + BUILD_LABEL + ')');
  if (typeof globalThis.sqlite3InitModule !== 'function') {
    throw new Error('sqlite3InitModule missing in worker (vendor/sqlite3.js failed to load?)');
  }
  sqlite3 = await globalThis.sqlite3InitModule();
  trace('sqlite3InitModule: OK');
  if (typeof sqlite3.installOpfsSAHPoolVfs !== 'function') {
    throw new Error('sqlite3.installOpfsSAHPoolVfs missing in worker build');
  }
  try {
    poolUtil = await sqlite3.installOpfsSAHPoolVfs();
    trace('installOpfsSAHPoolVfs: OK');
  } catch (poolErr) {
    // The SAH-pool VFS opens a fixed pool of OPFS capacity files via
    // FileSystemFileHandle.createSyncAccessHandle(). If another tab or
    // window of this app is already running, its worker holds those
    // handles and ours can't acquire them — Chrome throws a
    // NoModificationAllowedError DOMException with message "Access
    // Handles cannot be created if there is another open Access Handle
    // or Writable stream associated with the same file."
    //
    // Tag that case with code='OWNERSHIP_CONFLICT' so the page can
    // render a specific "directory is open in another tab" panel
    // instead of the misleading "your browser doesn't support this"
    // copy. Other init failures stay generic. See
    // plans/multi_tab_ownership_takeover.md for the full coordinated
    // takeover this is the cheap-fix predecessor of.
    if (isOwnershipConflictError(poolErr)) {
      trace('installOpfsSAHPoolVfs: OWNERSHIP_CONFLICT (' + ((poolErr && poolErr.message) || String(poolErr)) + ')');
      var conflictErr = new Error(
        'Could not acquire OPFS lock — another tab or window of this app is already open. ' +
        'Original: ' + ((poolErr && poolErr.message) || String(poolErr))
      );
      conflictErr.code = 'OWNERSHIP_CONFLICT';
      conflictErr.name = (poolErr && poolErr.name) || 'NoModificationAllowedError';
      throw conflictErr;
    }
    trace('installOpfsSAHPoolVfs: FAILED (' + ((poolErr && poolErr.message) || String(poolErr)) + ')');
    throw poolErr;
  }

  // One-time cleanup of the pre-P1 build-SHA sentinel (now retired).
  // No-op on profiles that never had it (clean installs, post-P1 boots).
  var sentinelRemoved = await _opfsRemoveEntry(LEGACY_SENTINEL);
  if (sentinelRemoved) trace('cleanup: removed legacy ' + LEGACY_SENTINEL);

  // Hydrate the user-folder handle from IDB so we know which storage
  // mode applies BEFORE opening relDb. (Phase 1 hydrated after relDb
  // was open; the pivot needs the order reversed so we can populate
  // the OPFS buffer from folder bytes before SAH-pool acquires the slot.)
  await _hydrateFolderRecord();

  // Resolve storage mode. Folder mode requires both a persisted handle
  // and a currently-granted readwrite permission. 'prompt' and 'denied'
  // states fall back to OPFS-only mode for this session — the page will
  // surface a "Reconnect folder" CTA, and a successful reconnect kicks
  // off a re-init via a separate code path (handled in a follow-up PR;
  // for now, the user clicks Save manually after reconnecting).
  var folderPermission = 'no-handle';
  if (folderRecord.parentHandle) {
    folderPermission = await _folderQueryPermission();
  }
  if (folderRecord.parentHandle && folderPermission === 'granted') {
    _storageMode = 'folder';
  } else {
    _storageMode = 'opfs';
  }
  trace('storageMode=' + _storageMode +
    ' (handle=' + (folderRecord.parentHandle ? 'yes' : 'no') +
    ' permission=' + folderPermission + ')');

  // Mobile de-migration. The durable-folder feature is not offered on
  // phones (see _isMobileWorker). If a folder handle survives — from a
  // build that used to offer the picker on Android, or a desktop handle
  // synced over — bring the worker back in line with the OPFS-only page
  // UI rather than silently keep writing to a Downloads subfolder the UI
  // claims doesn't exist. When the folder is readable, pull its (canonical
  // in folder mode) bytes into the OPFS working buffer first; then retire
  // the IDB handle and force OPFS-only for this and every future mobile
  // session. The physical folder file is never deleted — clearFolderHandle
  // only drops the IDB record — so it stays in Downloads as a recoverable
  // artifact and this path cannot lose data.
  if (_isMobileWorker() && folderRecord.parentHandle) {
    if (folderPermission === 'granted') {
      try {
        await _hydrateOpfsBufferFromFolder();
        trace('mobile de-migration: pulled folder data into OPFS before retiring handle');
      } catch (e) {
        trace('mobile de-migration: folder hydrate failed (' +
          ((e && e.message) || e) +
          '); folder file left in place, retiring handle anyway');
      }
    } else {
      trace('mobile de-migration: folder permission=' + folderPermission +
        ' — cannot read folder; retiring handle (folder file left in place)');
    }
    folderRecord = _emptyFolderRecord();
    try { await _folderIdbDelete(); }
    catch (e) { trace('mobile de-migration: folder IDB delete failed: ' + ((e && e.message) || e)); }
    _storageMode = 'opfs';
    folderPermission = 'no-handle';
  }

  // Folder mode: one-time migration (if Phase 1 hybrid state exists)
  // for relationships.db, then OPFS→folder backup-ring migration, then
  // hydrate the OPFS working buffer from folder bytes. After this
  // block, the OPFS slot reflects the folder file's content — opening
  // relDb against the slot gives us the folder's data, and the
  // auto-backup that fires next lands in the correct store (folder).
  if (_storageMode === 'folder') {
    try {
      await _maybeRunPivotMigration();
    } catch (migrateErr) {
      trace('pivot-migration: FAILED — ' + ((migrateErr && migrateErr.message) || migrateErr) +
        ' (continuing in folder mode; user can recover via Settings)');
    }
    try {
      await _maybeMigrateOpfsBackupsToFolder();
    } catch (backupMigErr) {
      trace('backup-ring migration: FAILED — ' +
        ((backupMigErr && backupMigErr.message) || backupMigErr) +
        ' (OPFS backups stay in place; new backups go to folder)');
    }
    try {
      await _hydrateOpfsBufferFromFolder();
    } catch (hydrateErr) {
      // Hard failure on hydration: surface to the page so the user
      // sees a clear "Folder unreadable" state rather than a blank app.
      trace('folder hydrate: FAILED — ' + ((hydrateErr && hydrateErr.message) || hydrateErr));
      // Don't throw; we'll proceed and open relDb against whatever's in
      // OPFS (which may be empty, in which case schema bootstrap creates
      // an empty DB). The page-side badge surfaces the lastError.
    }
  }

  // Auto-backup runs before opening relationships.db for app use, so the
  // snapshot reflects the user's last-saved state, not anything mutated
  // this session. Failure is non-fatal — logged via bootTrace. The
  // routing inside maybeBackupRelationshipsDb sends the snapshot to
  // whichever store is active for this session: folder when folder mode
  // resolved successfully above, OPFS otherwise. Folder-mode users no
  // longer accumulate OPFS-resident backups after this PR.
  await maybeBackupRelationshipsDb();

  var hasRelationshipsDb = false;
  try {
    relDb = new poolUtil.OpfsSAHPoolDb(RELATIONSHIPS_DB_SLOT);
    bootstrapRelationshipsSchema(relDb);
    hasRelationshipsDb = true;
    trace('relationships.db: open + schema OK (mode=' + _storageMode + ')');
  } catch (relErr) {
    trace('relationships.db: open failed (' + (relErr && relErr.message || relErr) + ')');
    relDb = null;
  }

  // Folder mode + fresh install (no folder file yet): the schema was
  // just bootstrapped into an empty OPFS buffer. Write it out to the
  // folder so the file exists from the start. Failure here is
  // non-fatal — the user sees the badge flip to write-failed and can
  // retry. (Same code path as the per-commit write.)
  if (_storageMode === 'folder' && hasRelationshipsDb && !folderRecord.lastSavedAt) {
    await _maybeWriteFolderAfterCommit();
  }

  // Open fellows.db if it's already on disk. Cold-start fetch is the
  // page-driven ensureFellowsDb RPC, gated behind directory-mode commit
  // (per L4a). Init is network-free.
  // fellows.db stays OPFS-resident in both storage modes (refreshable
  // shared data, not user-authored — per plan § Non-goals).
  var hasFellowsDb = _openFellowsDbIfPresent();

  return {
    ok: true,
    workerRpcVersion: WORKER_RPC_VERSION,
    schemaVersion: RELATIONSHIPS_SCHEMA_VERSION,
    buildLabel: BUILD_LABEL,
    opfsCapable: true,
    hasRelationshipsDb: hasRelationshipsDb,
    relDbOpen: hasRelationshipsDb,
    hasFellowsDb: hasFellowsDb,
    hasFolderHandle: !!folderRecord.parentHandle,
    folderParentName: folderRecord.parentName,
    folderSubfolderName: folderRecord.subfolderName,
    folderLastSavedAt: folderRecord.lastSavedAt,
    storageMode: _storageMode,
    poolFiles: (function () { try { return poolUtil.getFileNames(); } catch (e) { return []; } })(),
    trace: bootTrace.slice()
  };
};

// ----- Relationships (groups + settings) ------------------------------------

handlers.listGroups = async function () {
  if (!relDb) throw new Error('relationships db not open');
  return dbSelectAll(
    relDb,
    'SELECT g.id, g.name, g.note, g.created_at, g.updated_at, ' +
      'COUNT(gm.fellow_record_id) AS count ' +
      'FROM groups g LEFT JOIN group_members gm ON gm.group_id = g.id ' +
      'GROUP BY g.id ORDER BY g.updated_at DESC, g.id DESC',
    null
  );
};

handlers.getGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var row = dbSelectOne(relDb, 'SELECT * FROM groups WHERE id = ?', [id]);
  if (!row) return null;
  // Members come back as record_ids only; main thread resolves names from
  // its in-memory cache (populated by getList/getFull).
  var members = dbSelectAll(
    relDb, 'SELECT fellow_record_id AS record_id FROM group_members WHERE group_id = ?', [id]
  );
  row.members = members;
  return row;
};

handlers.createGroup = async function (data) {
  if (!relDb) throw new Error('relationships db not open');
  var name = data && data.name;
  var note = (data && typeof data.note === 'string') ? data.note : '';
  var ids = dedupeRecordIds(data && data.fellow_record_ids);
  var now = nowIsoSecond();
  var gid;
  relDb.exec('BEGIN');
  try {
    dbRun(relDb, 'INSERT INTO groups(name, note, created_at, updated_at) VALUES (?, ?, ?, ?)',
          [name, note, now, now]);
    var idRow = dbSelectOne(relDb, 'SELECT last_insert_rowid() AS id', null);
    gid = idRow && idRow.id;
    for (var i = 0; i < ids.length; i++) {
      dbRun(relDb, 'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)', [gid, ids[i]]);
    }
    relDb.exec('COMMIT');
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
  // Commit succeeded; mirror to folder if we're in folder mode. The
  // hook handles its own errors — it sets folderRecord.lastError but
  // does not throw, so a folder-write failure surfaces in the badge
  // without rolling back the OPFS-resident commit.
  await _maybeWriteFolderAfterCommit();
  return await handlers.getGroup({ id: gid });
};

handlers.updateGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var patch = (args && args.patch) || {};
  var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
  if (!existing) return null;
  var sets = ['updated_at = ?'];
  var params = [nowIsoSecond()];
  if (typeof patch.name === 'string') { sets.push('name = ?'); params.push(patch.name); }
  if (typeof patch.note === 'string') { sets.push('note = ?'); params.push(patch.note); }
  params.push(id);
  relDb.exec('BEGIN');
  try {
    dbRun(relDb, 'UPDATE groups SET ' + sets.join(', ') + ' WHERE id = ?', params);
    if (Array.isArray(patch.fellow_record_ids)) {
      dbRun(relDb, 'DELETE FROM group_members WHERE group_id = ?', [id]);
      var ids = dedupeRecordIds(patch.fellow_record_ids);
      for (var i = 0; i < ids.length; i++) {
        dbRun(relDb, 'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)', [id, ids[i]]);
      }
    }
    relDb.exec('COMMIT');
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
  await _maybeWriteFolderAfterCommit();
  return await handlers.getGroup({ id: id });
};

handlers.deleteGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
  if (!existing) return false;
  dbRun(relDb, 'DELETE FROM groups WHERE id = ?', [id]);
  await _maybeWriteFolderAfterCommit();
  return true;
};

handlers.getSetting = async function (args) {
  if (!relDb) return null;
  var row = dbSelectOne(relDb, 'SELECT value FROM settings WHERE key = ?', [args && args.key]);
  return row ? row.value : null;
};

handlers.getSettings = async function () {
  if (!relDb) return {};
  var rows = dbSelectAll(relDb, 'SELECT key, value FROM settings', null);
  var bag = {};
  rows.forEach(function (r) { bag[r.key] = r.value; });
  return bag;
};

handlers.setSetting = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var key = args && args.key;
  var value = args && args.value;
  if (value === null || value === undefined || value === '') {
    dbRun(relDb, 'DELETE FROM settings WHERE key = ?', [key]);
  } else {
    dbRun(
      relDb,
      'INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
      [key, value]
    );
  }
  await _maybeWriteFolderAfterCommit();
  return { key: key, value: value };
};

// ----- Backup / restore -----------------------------------------------------

handlers.exportRelationshipsBytes = async function () {
  if (!poolUtil) throw new Error('pool util unavailable');
  return poolUtil.exportFile(RELATIONSHIPS_DB_SLOT);
};

handlers.inspectRelationshipsBytes = async function (args) {
  return inspectBytes(args && args.bytes);
};

handlers.countRelationships = async function () {
  if (!relDb) return null;
  return {
    groups: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM groups', null).n,
    members: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM group_members', null).n,
    tags: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
    notes: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
    settings: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM settings', null).n
  };
};

handlers.importRelationshipsBytes = async function (args) {
  if (!poolUtil) throw new Error('pool util unavailable');
  var bytes = args && args.bytes;
  var inspection = await inspectBytes(bytes);
  if (!inspection.valid) {
    var err = new Error(inspection.error || 'invalid relationships.db file');
    err.invalidBackup = true;
    throw err;
  }
  var snap = await snapshotRelationshipsDbToBackup();
  if (relDb) {
    try { relDb.close(); } catch (e) {}
    relDb = null;
  }
  poolUtil.importDb(RELATIONSHIPS_DB_SLOT, bytes);
  relDb = new poolUtil.OpfsSAHPoolDb(RELATIONSHIPS_DB_SLOT);
  bootstrapRelationshipsSchema(relDb);
  // A whole-DB replace is the biggest mutation we do. Mirror to folder
  // immediately so the user's badge reflects the new state.
  await _maybeWriteFolderAfterCommit();
  return {
    counts: inspection.counts,
    preRestoreSnapshot: snap && snap.backedUp ? snap.name : null
  };
};

handlers.listRelationshipsBackups = async function () {
  if (!poolUtil) return [];
  // Active store is folder when folder-mode permission is granted,
  // otherwise OPFS. After PR backup-ring migration, folder-mode
  // users never see OPFS-resident backups here (migrated + cleared).
  var raw = await _listActiveBackups();
  var out = [];
  // Sequential — staging slot is shared across inspects.
  for (var i = 0; i < raw.length; i++) {
    var entry = raw[i];
    try {
      var bytes = await _readActiveBackup(entry.name);
      var insp = await inspectBytes(bytes);
      out.push({
        name: entry.name, size: entry.size, lastModified: entry.lastModified,
        counts: insp.valid ? insp.counts : null,
        invalid: !insp.valid,
        error: insp.valid ? null : insp.error
      });
    } catch (e) {
      out.push({
        name: entry.name, size: entry.size, lastModified: entry.lastModified,
        counts: null, invalid: true, error: (e && e.message) || String(e)
      });
    }
  }
  return out;
};

handlers.restoreRelationshipsBackup = async function (args) {
  if (!poolUtil) throw new Error('pool util unavailable');
  var name = args && args.name;
  var backups = await _listActiveBackups();
  var match = null;
  for (var i = 0; i < backups.length; i++) {
    if (backups[i].name === name) { match = backups[i]; break; }
  }
  if (!match) throw new Error('Backup not found: ' + name);
  var bytes = await _readActiveBackup(name);
  return await handlers.importRelationshipsBytes({ bytes: bytes });
};

// ----- fellows.db query handlers (sole local read source post-cutover) ------

function _requireFellowsDb() {
  if (!fellowsDb) {
    var err = new Error('fellows.db not open — page must call ensureFellowsDb first');
    err.code = 'fellows_db_not_open';
    throw err;
  }
  return fellowsDb;
}

handlers.getList = async function () {
  var db = _requireFellowsDb();
  var rows = dbSelectAll(
    db,
    'SELECT record_id, slug, name, ' +
      "CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END " +
      'AS has_contact_email FROM fellows ORDER BY name ASC',
    null
  );
  return rows.map(function (r) {
    return {
      record_id: r.record_id,
      slug: r.slug,
      name: r.name,
      has_contact_email: !!r.has_contact_email
    };
  });
};

handlers.getFull = async function () {
  var db = _requireFellowsDb();
  var rows = dbSelectAll(db, 'SELECT * FROM fellows ORDER BY name ASC', null);
  return rows.map(rowToFellow);
};

handlers.getOne = async function (args) {
  var db = _requireFellowsDb();
  var slugOrId = args && args.slug;
  if (!slugOrId) return null;
  var row = dbSelectOne(
    db,
    'SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1',
    [slugOrId, slugOrId]
  );
  return row ? rowToFellow(row) : null;
};

handlers.search = async function (args) {
  var db = _requireFellowsDb();
  var q = args && args.q;
  if (!q || !q.replace(/^\s+|\s+$/g, '')) return [];
  q = q.replace(/^\s+|\s+$/g, '');
  if (q.length > 200) q = q.slice(0, 200);
  var rows = dbSelectAll(
    db,
    'SELECT f.* FROM fellows f WHERE f.rowid IN (' +
      'SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?' +
      ') ORDER BY f.name ASC',
    [q]
  );
  return rows.map(rowToFellow);
};

handlers.getStats = async function () {
  var db = _requireFellowsDb();
  var total = dbSelectOne(db, 'SELECT COUNT(*) AS n FROM fellows', null).n;

  function groupCounts(sql) {
    return dbSelectAll(db, sql, null).map(function (r) {
      // sqlite-wasm returns objects keyed by column expression string when
      // there's no alias. Pull the first non-COUNT key as the label.
      var keys = Object.keys(r);
      var labelKey = null;
      var countKey = null;
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (k.toUpperCase().indexOf('COUNT') === 0) countKey = k;
        else labelKey = k;
      }
      return { label: r[labelKey], count: r[countKey] };
    });
  }

  // Region counts: split comma-separated global_regions_currently_based_in
  // so dual-region fellows are counted in each region.
  var regionRows = dbSelectAll(
    db,
    'SELECT global_regions_currently_based_in AS regions FROM fellows ' +
      "WHERE global_regions_currently_based_in IS NOT NULL " +
      "AND global_regions_currently_based_in != ''",
    null
  );
  var regionCounter = {};
  for (var i = 0; i < regionRows.length; i++) {
    var parts = String(regionRows[i].regions).split(',');
    for (var j = 0; j < parts.length; j++) {
      var region = parts[j].replace(/^\s+|\s+$/g, '');
      if (region) regionCounter[region] = (regionCounter[region] || 0) + 1;
    }
  }
  var byRegion = Object.keys(regionCounter)
    .map(function (r) { return { label: r, count: regionCounter[r] }; })
    .sort(function (a, b) { return b.count - a.count; });

  // Field completeness: count non-empty values for each DB column and
  // each known extra_json key.
  var fieldCounts = [];
  var colKeys = Object.keys(COL_LABELS);
  for (var ci = 0; ci < colKeys.length; ci++) {
    var col = colKeys[ci];
    // Column names come from a controlled allow-list (COL_LABELS keys), so
    // string concat is safe — same pattern as app/server.py:get_stats.
    var n = dbSelectOne(
      db,
      'SELECT COUNT(*) AS n FROM fellows WHERE ' + col + ' IS NOT NULL AND ' + col + ' != \'\'',
      null
    ).n;
    fieldCounts.push({ label: COL_LABELS[col], count: n });
  }
  var extraKeys = Object.keys(EXTRA_LABELS);
  for (var ei = 0; ei < extraKeys.length; ei++) {
    var ekey = extraKeys[ei];
    var jsonPath = '$.' + ekey;
    var n2 = dbSelectOne(
      db,
      'SELECT COUNT(*) AS n FROM fellows WHERE extra_json IS NOT NULL ' +
        "AND json_extract(extra_json, ?) IS NOT NULL " +
        "AND json_extract(extra_json, ?) != ''",
      [jsonPath, jsonPath]
    ).n;
    fieldCounts.push({ label: EXTRA_LABELS[ekey], count: n2 });
  }
  fieldCounts.sort(function (a, b) { return b.count - a.count; });

  return {
    total: total,
    by_fellow_type: groupCounts(
      'SELECT fellow_type, COUNT(*) FROM fellows ' +
        'WHERE fellow_type IS NOT NULL ' +
        'GROUP BY fellow_type ORDER BY COUNT(*) DESC'
    ),
    by_cohort: groupCounts(
      'SELECT cohort, COUNT(*) FROM fellows ' +
        'WHERE cohort IS NOT NULL ' +
        'GROUP BY cohort ORDER BY COUNT(*) DESC'
    ),
    by_region: byRegion,
    field_completeness: fieldCounts
  };
};

// ----- ensureFellowsDb (page-driven cold-start fetch — opt-in policy) ------
// Page calls this on every boot, only after the gate decision tree
// resolves to directory mode. The boot path is install-only by design
// (plans/opt_in_directory_data_updates.md): on a returning visitor with
// fellows.db already on disk, the worker never auto-fetches, regardless
// of SHA. The user has to explicitly request a refresh via the About
// page → previewFellowsDbSwap → applyFellowsDbSwap RPCs.
//
//   - args.mode: 'install-only' (default) — fetch only when fellowsDb
//     is not open (cold start, post-Reset Everything). Returns the
//     existing handle untouched otherwise. SHA is ignored in this mode
//     beyond an informational trace.
//   - args.mode: 'refresh' — pre-PR-#113 behavior, kept for the
//     applyFellowsDbSwap RPC's internal use only. Fetch + validate +
//     atomic replace + meta update. `args.serverSha`, if provided, is
//     stamped into the trace; the actual SHA written to meta is the
//     digest of the bytes we received.
//   - Unknown / missing mode coerces to 'install-only'.
//
// On fetch / validation failure, `meta.last_failure_at` and
// `last_failure_reason` are recorded; the previously-live fellows.db
// stays open. The error is also thrown so the page can surface a soft
// warning, but `relationships.db` operations remain unaffected (G3 / L5).

async function _writeMetaFailure(reason) {
  var existing = (await readFellowsMeta()) || {
    sha: null,
    fetched_at: null,
    last_failure_at: null,
    last_failure_reason: null
  };
  existing.last_failure_at = new Date().toISOString();
  existing.last_failure_reason = String(reason || '');
  try { await writeFellowsMeta(existing); }
  catch (we) { trace('ensureFellowsDb: meta-failure write failed: ' + (we && we.message || we)); }
  return existing;
}

// Fetch /fellows.db, validate, atomically replace the live slot, write
// meta. Throws on any failure with a code-tagged Error; on throw the
// previously-live fellowsDb stays open and meta records the failure.
// Used by both ensureFellowsDb's cold-start branch and (via raw bytes
// already on disk) applyFellowsDbSwap.
async function _fetchValidateAndImportFellowsDb(serverShaHint, kind) {
  trace('fellows.db ' + kind + ': fetch /fellows.db'
    + (serverShaHint ? ' (serverSha=' + serverShaHint.slice(0, 12) + '…)' : ''));

  var resp;
  try {
    resp = await fetch('/fellows.db', { credentials: 'include', cache: 'no-store' });
  } catch (e) {
    var netReason = 'network: ' + (e && e.message || e);
    var failedMeta = await _writeMetaFailure(netReason);
    var nerr = new Error('Network fetch /fellows.db failed: ' + (e && e.message || e));
    nerr.code = 'fellows_db_fetch_network';
    nerr.meta = failedMeta;
    throw nerr;
  }
  if (!resp.ok) {
    var httpReason = 'HTTP ' + resp.status;
    var failedMetaH = await _writeMetaFailure(httpReason);
    var herr = new Error('GET /fellows.db returned HTTP ' + resp.status);
    herr.code = 'fellows_db_fetch_http';
    herr.httpStatus = resp.status;
    herr.meta = failedMetaH;
    throw herr;
  }
  var buf = await resp.arrayBuffer();
  var bytes = new Uint8Array(buf);
  if (!bytes.byteLength) {
    var emptyMeta = await _writeMetaFailure('empty response');
    var eerr = new Error('Empty /fellows.db response');
    eerr.code = 'fellows_db_fetch_empty';
    eerr.meta = emptyMeta;
    throw eerr;
  }

  // Validate the fetched bytes in a staging slot before touching the live
  // slot. If validation fails, the previous fellowsDb is still open and
  // the error path leaves it untouched.
  var verifyDb = null;
  try {
    poolUtil.importDb(FELLOWS_STAGING_SLOT, bytes);
    verifyDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_STAGING_SLOT);
    var qc = dbSelectOne(verifyDb, 'PRAGMA quick_check', null);
    var qcResult = qc && (qc.quick_check || qc['quick_check']);
    if (qcResult !== 'ok') {
      throw new Error('quick_check failed: ' + (qcResult || 'unknown'));
    }
  } catch (verr) {
    if (verifyDb) { try { verifyDb.close(); } catch (e2) {} }
    var invalidReason = 'invalid bytes: ' + (verr && verr.message || verr);
    var invalidMeta = await _writeMetaFailure(invalidReason);
    var ierr = new Error('Validation of fetched fellows.db failed: ' + (verr && verr.message || verr));
    ierr.code = 'fellows_db_invalid';
    ierr.meta = invalidMeta;
    throw ierr;
  }
  if (verifyDb) { try { verifyDb.close(); } catch (e3) {} }

  // Compute the digest of what we actually got. This is the value that
  // ends up in meta.sha — not the hint — so a server that lies about
  // its SHA can't desync the local copy.
  var fetchedSha = await _sha256Hex(bytes);

  // Promote staging → live slot. importDb requires the live slot's SAH
  // to be released first, so close the current handle (if any).
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e4) {}
    fellowsDb = null;
  }
  poolUtil.importDb(FELLOWS_DB_SLOT, bytes);
  fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
  trace('fellows.db ' + kind + ': imported ' + bytes.byteLength + ' bytes, sha=' + fetchedSha.slice(0, 12) + '…');

  var newMeta = {
    sha: fetchedSha,
    fetched_at: new Date().toISOString(),
    last_failure_at: null,
    last_failure_reason: null
  };
  try { await writeFellowsMeta(newMeta); }
  catch (we) { trace('fellows.db ' + kind + ': meta write failed: ' + (we && we.message || we)); }
  return { bytes: bytes, sha: fetchedSha, meta: newMeta };
}

handlers.ensureFellowsDb = async function (args) {
  args = args || {};
  var mode = args.mode === 'refresh' ? 'refresh' : 'install-only';
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  var localMeta = await readFellowsMeta();

  // Install-only is the boot-path policy under
  // plans/opt_in_directory_data_updates.md: never auto-refresh a
  // returning visitor's fellows.db, regardless of SHA. The user opts
  // in via previewFellowsDbSwap → applyFellowsDbSwap.
  if (mode === 'install-only' && fellowsDb) {
    return { hasFellowsDb: true, refreshed: false, meta: localMeta || null };
  }

  // Cold-start (no local fellows.db) under either mode: fetch.
  // Refresh under either condition: fetch.
  var kind = fellowsDb ? 'refresh' : 'cold-start';
  var imported = await _fetchValidateAndImportFellowsDb(serverSha, kind);
  return { hasFellowsDb: true, refreshed: true, meta: imported.meta };
};

// ----- Opt-in directory-data update flow ------------------------------------
// plans/opt_in_directory_data_updates.md. Flow:
//   1. compareFellowsDbSha({serverSha}) → quick read of meta.sha vs server.
//   2. previewFellowsDbSwap({serverSha}) → fetch + validate + write to
//      swap-staging slot. Compute affected group members. Return.
//   3. applyFellowsDbSwap({stagingId}) → promote staging → live slot.
//      OR cancelFellowsDbSwap({stagingId}) → discard.
//
// The staging slot persists between (2) and (3) so the dialog can sit
// open without holding bytes in JS memory. `pendingFellowsDbSwap` holds
// the metadata + an opaque id the page must echo back; a stale id
// (page reloaded, worker restarted) makes apply 400.

function _newStagingId() {
  // 16 hex chars from crypto.getRandomValues — opaque, unguessable enough
  // for a same-process correlation handle.
  var arr = new Uint8Array(8);
  crypto.getRandomValues(arr);
  var hex = '';
  for (var i = 0; i < arr.length; i++) {
    var b = arr[i];
    hex += (b < 16 ? '0' : '') + b.toString(16);
  }
  return hex;
}

function _clearSwapStagingSlot() {
  if (!poolUtil) return;
  try {
    if (typeof poolUtil.unlink === 'function') {
      poolUtil.unlink(FELLOWS_SWAP_STAGING_SLOT);
    }
  } catch (e) { /* slot may not exist; non-fatal */ }
}

handlers.compareFellowsDbSha = async function (args) {
  args = args || {};
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  var meta = await readFellowsMeta();
  var localSha = (meta && typeof meta.sha === 'string') ? meta.sha : null;
  // dataUpdateAvailable is only true when we have a local DB AND a
  // local SHA AND a server SHA AND they differ. Cold-start (no local
  // DB) is not an "update" — that's the install path. Server unreachable
  // (serverSha null) returns null so the UI can show "couldn't check"
  // distinctly from "up to date".
  var dataUpdateAvailable = false;
  if (!serverSha) {
    dataUpdateAvailable = null;
  } else if (fellowsDb && localSha) {
    dataUpdateAvailable = (localSha !== serverSha);
  }
  return {
    hasFellowsDb: !!fellowsDb,
    localSha: localSha,
    serverSha: serverSha,
    fetchedAt: (meta && meta.fetched_at) || null,
    dataUpdateAvailable: dataUpdateAvailable
  };
};

handlers.previewFellowsDbSwap = async function (args) {
  args = args || {};
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  if (!fellowsDb) {
    var nerr = new Error('No local fellows.db to swap from');
    nerr.code = 'no_local_fellows_db';
    throw nerr;
  }
  // A previous pending swap is implicitly discarded: we only support one
  // outstanding swap at a time. Later attempts re-fetch.
  if (pendingFellowsDbSwap) {
    _clearSwapStagingSlot();
    pendingFellowsDbSwap = null;
  }

  // Fetch into the swap-staging slot. Reuse the validation path by writing
  // to the existing staging slot first, but copy into the swap-staging
  // slot afterwards so the boot-path slot stays free for any future
  // ensureFellowsDb call.
  trace('previewFellowsDbSwap: fetch /fellows.db'
    + (serverSha ? ' (serverSha=' + serverSha.slice(0, 12) + '…)' : ''));
  var resp;
  try {
    resp = await fetch('/fellows.db', { credentials: 'include', cache: 'no-store' });
  } catch (e) {
    var nferr = new Error('Network fetch /fellows.db failed: ' + (e && e.message || e));
    nferr.code = 'fellows_db_fetch_network';
    throw nferr;
  }
  if (!resp.ok) {
    var herr = new Error('GET /fellows.db returned HTTP ' + resp.status);
    herr.code = 'fellows_db_fetch_http';
    herr.httpStatus = resp.status;
    throw herr;
  }
  var buf = await resp.arrayBuffer();
  var bytes = new Uint8Array(buf);
  if (!bytes.byteLength) {
    var eerr = new Error('Empty /fellows.db response');
    eerr.code = 'fellows_db_fetch_empty';
    throw eerr;
  }

  // Validate by importing into the swap-staging slot directly and running
  // PRAGMA quick_check + a fellows-table sanity probe.
  var stagingDb = null;
  var fetchedSha;
  var stagedIdSet; // map: record_ids present in the staged fellows.db
  try {
    poolUtil.importDb(FELLOWS_SWAP_STAGING_SLOT, bytes);
    stagingDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_SWAP_STAGING_SLOT);
    var qc = dbSelectOne(stagingDb, 'PRAGMA quick_check', null);
    var qcResult = qc && (qc.quick_check || qc['quick_check']);
    if (qcResult !== 'ok') {
      throw new Error('quick_check failed: ' + (qcResult || 'unknown'));
    }
    // Smoke-check the schema. A zero-row DB is technically valid SQLite
    // but would silently orphan every existing group member; reject it.
    var totalRow = dbSelectOne(stagingDb, 'SELECT COUNT(*) AS n FROM fellows', null);
    if (!totalRow || !totalRow.n) {
      throw new Error('staged fellows.db has zero rows');
    }
    fetchedSha = await _sha256Hex(bytes);

    // Compute affected group members: every record_id in group_members
    // that has no matching record in the staged fellows.db. We need
    // (a) the set of record_ids in the staged DB (b) every (member,
    // group) pair from relationships.db (c) human-readable names from
    // the *live* fellows.db so the dialog can show "Alice Smith" not
    // a record_id.
    var stagedIdsRows = dbSelectAll(stagingDb, 'SELECT record_id FROM fellows', null);
    stagedIdSet = {};
    for (var i = 0; i < stagedIdsRows.length; i++) stagedIdSet[stagedIdsRows[i].record_id] = true;
  } catch (verr) {
    if (stagingDb) { try { stagingDb.close(); } catch (e2) {} }
    _clearSwapStagingSlot();
    var ierr = new Error('Validation of staged fellows.db failed: ' + (verr && verr.message || verr));
    ierr.code = 'fellows_db_invalid';
    throw ierr;
  }
  try { stagingDb.close(); } catch (e3) {}

  // Resolve affected members from the page's perspective. Read
  // group_members + group names from relationships.db, drop any whose
  // record_id is in the staged set, then look up display names in the
  // *live* fellows.db.
  var affected = []; // [{ recordId, name, groups: [{id, name}] }]
  if (relDb) {
    var memberRows = dbSelectAll(
      relDb,
      'SELECT gm.fellow_record_id AS rid, gm.group_id AS gid, g.name AS gname ' +
        'FROM group_members gm JOIN groups g ON g.id = gm.group_id',
      null
    );
    var byRid = {};
    for (var m = 0; m < memberRows.length; m++) {
      var row = memberRows[m];
      if (stagedIdSet[row.rid]) continue; // still present after swap
      if (!byRid[row.rid]) byRid[row.rid] = { recordId: row.rid, name: null, groups: [] };
      byRid[row.rid].groups.push({ id: row.gid, name: row.gname });
    }
    var ridKeys = Object.keys(byRid);
    if (ridKeys.length && fellowsDb) {
      // Resolve names from the live DB. Bind one at a time — the count is
      // expected to be small (members lost between consecutive deploys).
      for (var rk = 0; rk < ridKeys.length; rk++) {
        var rid = ridKeys[rk];
        var nrow = dbSelectOne(fellowsDb, 'SELECT name FROM fellows WHERE record_id = ?', [rid]);
        byRid[rid].name = (nrow && nrow.name) || null;
        affected.push(byRid[rid]);
      }
      affected.sort(function (a, b) {
        var an = (a.name || '').toLowerCase();
        var bn = (b.name || '').toLowerCase();
        return an < bn ? -1 : an > bn ? 1 : 0;
      });
    }
  }

  var stagingId = _newStagingId();
  pendingFellowsDbSwap = {
    stagingId: stagingId,
    sha: fetchedSha,
    fetchedAt: new Date().toISOString(),
    serverShaHint: serverSha
  };
  trace('previewFellowsDbSwap: staged sha=' + fetchedSha.slice(0, 12) +
    '… affectedMembers=' + affected.length + ' stagingId=' + stagingId);

  return {
    stagingId: stagingId,
    newSha: fetchedSha,
    affectedGroups: affected
  };
};

handlers.applyFellowsDbSwap = async function (args) {
  args = args || {};
  var stagingId = args.stagingId;
  if (!pendingFellowsDbSwap || !stagingId || pendingFellowsDbSwap.stagingId !== stagingId) {
    var serr = new Error('No matching pending swap (stagingId mismatch or expired)');
    serr.code = 'staging_id_mismatch';
    throw serr;
  }
  var pending = pendingFellowsDbSwap;
  // Read bytes back from the staging slot. exportFile returns a fresh
  // Uint8Array; importDb-into-live releases the SAH after we close the
  // current live handle.
  var bytes;
  try {
    bytes = poolUtil.exportFile(FELLOWS_SWAP_STAGING_SLOT);
  } catch (e) {
    pendingFellowsDbSwap = null;
    _clearSwapStagingSlot();
    var rerr = new Error('Could not read staged bytes: ' + (e && e.message || e));
    rerr.code = 'staging_export_failed';
    throw rerr;
  }
  if (!bytes || !bytes.byteLength) {
    pendingFellowsDbSwap = null;
    _clearSwapStagingSlot();
    var berr = new Error('Staged bytes are empty');
    berr.code = 'staging_empty';
    throw berr;
  }
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e2) {}
    fellowsDb = null;
  }
  poolUtil.importDb(FELLOWS_DB_SLOT, bytes);
  fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
  var newMeta = {
    sha: pending.sha,
    fetched_at: pending.fetchedAt,
    last_failure_at: null,
    last_failure_reason: null
  };
  try { await writeFellowsMeta(newMeta); }
  catch (we) { trace('applyFellowsDbSwap: meta write failed: ' + (we && we.message || we)); }
  pendingFellowsDbSwap = null;
  _clearSwapStagingSlot();
  trace('applyFellowsDbSwap: live slot promoted to sha=' + pending.sha.slice(0, 12) + '…');
  return { ok: true, newSha: pending.sha, meta: newMeta };
};

handlers.cancelFellowsDbSwap = async function (args) {
  args = args || {};
  var stagingId = args.stagingId;
  // Be lenient on cancel — if the page sends a stale id, just clear
  // anyway. The intent ("don't apply the staged update") is unambiguous.
  if (pendingFellowsDbSwap && stagingId && pendingFellowsDbSwap.stagingId !== stagingId) {
    trace('cancelFellowsDbSwap: stagingId mismatch — clearing pending anyway');
  }
  pendingFellowsDbSwap = null;
  _clearSwapStagingSlot();
  return { ok: true };
};

// Soft scan invoked once on first boot of the new code (gated by the
// `orphan_scan_done` setting on the page side). Returns the same shape
// as previewFellowsDbSwap.affectedGroups so the same UI patterns apply.
handlers.findOrphanedGroupMembers = async function () {
  if (!relDb || !fellowsDb) return { orphans: [] };
  var memberRows = dbSelectAll(
    relDb,
    'SELECT gm.fellow_record_id AS rid, gm.group_id AS gid, g.name AS gname ' +
      'FROM group_members gm JOIN groups g ON g.id = gm.group_id',
    null
  );
  if (!memberRows.length) return { orphans: [] };
  var fellowRows = dbSelectAll(fellowsDb, 'SELECT record_id FROM fellows', null);
  var existing = {};
  for (var i = 0; i < fellowRows.length; i++) existing[fellowRows[i].record_id] = true;
  var byRid = {};
  for (var j = 0; j < memberRows.length; j++) {
    var r = memberRows[j];
    if (existing[r.rid]) continue;
    if (!byRid[r.rid]) byRid[r.rid] = { recordId: r.rid, name: null, groups: [] };
    byRid[r.rid].groups.push({ id: r.gid, name: r.gname });
  }
  var orphans = [];
  var keys = Object.keys(byRid);
  for (var k = 0; k < keys.length; k++) orphans.push(byRid[keys[k]]);
  orphans.sort(function (a, b) {
    return a.recordId < b.recordId ? -1 : a.recordId > b.recordId ? 1 : 0;
  });
  return { orphans: orphans };
};

// ----- Diagnostics ----------------------------------------------------------

handlers.getTrace = async function () { return bootTrace.slice(); };

handlers.getVersions = async function () {
  return {
    workerRpcVersion: WORKER_RPC_VERSION,
    schemaVersion: RELATIONSHIPS_SCHEMA_VERSION,
    buildLabel: BUILD_LABEL
  };
};

// Read-only view of fellows.db.meta.json for diagnostics + the About
// page's "Last update check" line. Pure read — never triggers a fetch
// or import; that's ensureFellowsDb's job. Returns null when the meta
// file doesn't exist yet (cold-start before first ensureFellowsDb).
handlers.getFellowsDbMeta = async function () {
  return await readFellowsMeta();
};

// Reset Everything's nuclear path. Closes both DB handles, tears down the
// SAH-pool VFS via removeVfs() (which releases every SAH and recursively
// removes the pool's opaque storage dir), then sweeps sibling files we
// create at OPFS root (relationships.db.bak.*, fellows.db.meta.json, any
// orphaned LEGACY_SENTINEL). Caller is expected to reload the page after
// — the worker is unusable post-wipe (poolUtil reset to null).
//
// Restores the pre-cutover Reset Everything semantics: L1 forbids the
// page from opening OPFS, so the page can't iterate the root itself.
// This op is the worker-side replacement.
handlers.wipeAll = async function () {
  if (relDb) {
    try { relDb.close(); } catch (e) {}
    relDb = null;
  }
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e) {}
    fellowsDb = null;
  }
  var removedVfs = false;
  if (poolUtil) {
    try { removedVfs = await poolUtil.removeVfs(); }
    catch (e) { trace('wipeAll: removeVfs failed: ' + (e && e.message || e)); }
  }
  var rootEntriesRemoved = [];
  var rootEntriesFailed = [];
  try {
    var root = await self.navigator.storage.getDirectory();
    var names = [];
    for await (var entry of root.values()) names.push(entry.name);
    for (var i = 0; i < names.length; i++) {
      try {
        await root.removeEntry(names[i], { recursive: true });
        rootEntriesRemoved.push(names[i]);
      } catch (e2) {
        rootEntriesFailed.push({ name: names[i], error: (e2 && e2.message) || String(e2) });
        trace('wipeAll: removeEntry ' + names[i] + ' failed: ' + (e2 && e2.message || e2));
      }
    }
  } catch (e3) {
    trace('wipeAll: root iteration failed: ' + (e3 && e3.message || e3));
  }
  poolUtil = null;
  trace('wipeAll: removedVfs=' + removedVfs + ' rootRemoved=' + rootEntriesRemoved.length +
        ' rootFailed=' + rootEntriesFailed.length);
  return {
    removedVfs: removedVfs,
    rootEntriesRemoved: rootEntriesRemoved,
    rootEntriesFailed: rootEntriesFailed
  };
};

// Returns a snapshot of every OPFS root entry plus the SAH-pool slot
// inventory. Used by the ?diag=1 panel post-Phase-1 so the maintainer
// can see exactly what's on disk without main-thread OPFS access.
handlers.getOpfsInventory = async function () {
  var rootEntries = [];
  try {
    var root = await _opfsRoot();
    for await (var entry of root.values()) {
      var item = { name: entry.name, kind: entry.kind };
      if (entry.kind === 'file') {
        try {
          var f = await entry.getFile();
          item.size = f.size;
          item.lastModified = f.lastModified;
        } catch (fe) {}
      }
      rootEntries.push(item);
    }
    rootEntries.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
  } catch (e) {}
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e2) {}
  return { root: rootEntries, poolFiles: poolFiles };
};

// ===== User-folder durable storage (issue #165 Phase 1) =====================
// The worker is the owner of the user-picked FileSystemDirectoryHandle: it
// persists the handle in its own IndexedDB and performs every read/write
// against the folder. The page is the user-gesture gateway — it calls
// showDirectoryPicker / requestPermission on its own (those APIs require
// transient user activation) and either ships the handle in or borrows
// the worker's copy back for a one-shot permission request.
//
// Subfolder layout: user picks a *parent* folder; we own a "Fellows/"
// subfolder inside it. On collision (Fellows/ already has a
// relationships.db) the page shows the open-existing vs create-Fellows-N
// dialog; the page then re-invokes setFolderHandle with the explicit mode.
// One file lives in the subfolder for Phase 1: relationships.db. (Backups
// migrate in Phase 2.)
//
// "Saved" semantics: the badge flips to Saved only after a successful
// createWritable → write → close round-trip — that's atomic per the
// FileSystem Access spec (the browser writes through a temp file and
// renames on close).

var FOLDER_IDB_NAME = 'fellows-fs-handles';
var FOLDER_IDB_STORE = 'handles';
var FOLDER_IDB_KEY = 'relationships-folder';
var FOLDER_SUBFOLDER_DEFAULT = 'Fellows';
var FOLDER_RELATIONSHIPS_FILE = 'relationships.db';
// Web Locks name guarding folder writes. Lock is scoped per-origin
// per-browser-profile; agents in the same context (this worker + its
// page) share the namespace, so a page-side test or future takeover-
// handoff window cannot race the worker's _writeBytesToFolder.
var FOLDER_WRITE_LOCK_NAME = 'fellows-relationships-folder-write';

// True when this worker is running on a phone/tablet. The durable-folder
// feature is NOT offered on mobile: Android's directory picker routes
// through the Storage Access Framework, which forces the user into a
// Downloads subfolder the OS can clear at will (so it fails the feature's
// whole durability promise), and iOS has no directory picker at all. On
// mobile the app is OPFS-only + manual backup. The page UI hides the
// feature (see app.js isMobileDevice / folderStorageOffered); this lets the
// worker make the same call so the two never disagree about storage mode.
// Mirrors the UA/touch heuristic used page-side. Workers expose navigator.
function _isMobileWorker() {
  var ua = (self.navigator && self.navigator.userAgent) || '';
  return /iPad|iPhone|iPod|Android/.test(ua) ||
    (self.navigator && self.navigator.platform === 'MacIntel' &&
     self.navigator.maxTouchPoints > 1);
}

// In-memory mirror of what's persisted in IDB. Reloaded on init, mutated
// alongside every IDB write. Shape: see _emptyFolderRecord().
var folderRecord = _emptyFolderRecord();

function _emptyFolderRecord() {
  return {
    parentHandle: null,    // FileSystemDirectoryHandle (the parent the user picked)
    parentName: null,      // string — handle.name (for diag / UI)
    subfolderName: null,   // string — e.g. "Fellows" or "Fellows 2"
    lastSavedAt: null,     // ISO string of most recent successful write
    lastError: null,       // { at, reason } of most recent failed read/write
    lastPermission: null,  // 'granted' | 'prompt' | 'denied' — most recent queryPermission result
    pivotMigratedAt: null  // ISO string set after the one-time Phase 1 → pure-folder migration completes
  };
}

// ----- IDB plumbing ---------------------------------------------------------

function _folderIdbOpen() {
  return new Promise(function (resolve, reject) {
    if (!self.indexedDB) {
      reject(new Error('indexedDB unavailable in worker'));
      return;
    }
    var req = self.indexedDB.open(FOLDER_IDB_NAME, 1);
    req.onupgradeneeded = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains(FOLDER_IDB_STORE)) {
        db.createObjectStore(FOLDER_IDB_STORE);
      }
    };
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { reject(req.error || new Error('IDB open failed')); };
  });
}

function _folderIdbGet() {
  return _folderIdbOpen().then(function (db) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(FOLDER_IDB_STORE, 'readonly');
      var store = tx.objectStore(FOLDER_IDB_STORE);
      var req = store.get(FOLDER_IDB_KEY);
      req.onsuccess = function () { resolve(req.result || null); };
      req.onerror = function () { reject(req.error || new Error('IDB get failed')); };
      tx.oncomplete = function () { try { db.close(); } catch (e) {} };
    });
  });
}

function _folderIdbPut(value) {
  return _folderIdbOpen().then(function (db) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(FOLDER_IDB_STORE, 'readwrite');
      var store = tx.objectStore(FOLDER_IDB_STORE);
      var req = store.put(value, FOLDER_IDB_KEY);
      req.onsuccess = function () { resolve(true); };
      req.onerror = function () { reject(req.error || new Error('IDB put failed')); };
      tx.oncomplete = function () { try { db.close(); } catch (e) {} };
    });
  });
}

function _folderIdbDelete() {
  return _folderIdbOpen().then(function (db) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(FOLDER_IDB_STORE, 'readwrite');
      var store = tx.objectStore(FOLDER_IDB_STORE);
      var req = store.delete(FOLDER_IDB_KEY);
      req.onsuccess = function () { resolve(true); };
      req.onerror = function () { reject(req.error || new Error('IDB delete failed')); };
      tx.oncomplete = function () { try { db.close(); } catch (e) {} };
    });
  });
}

// Re-persist `folderRecord` to IDB. Stores only the fields IDB cares
// about; everything else is derived.
function _folderRecordPersist() {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    // Nothing to persist — defensive guard. Caller should _folderIdbDelete()
    // explicitly when disconnecting.
    return Promise.resolve(false);
  }
  return _folderIdbPut({
    parentHandle: folderRecord.parentHandle,
    parentName: folderRecord.parentName || null,
    subfolderName: folderRecord.subfolderName,
    lastSavedAt: folderRecord.lastSavedAt || null,
    lastError: folderRecord.lastError || null,
    pivotMigratedAt: folderRecord.pivotMigratedAt || null
  });
}

// Hydrate `folderRecord` from IDB on init. Non-fatal on any failure — the
// app continues in OPFS-only mode and the page renders the
// "Browser-only" badge.
async function _hydrateFolderRecord() {
  try {
    var rec = await _folderIdbGet();
    if (rec && rec.parentHandle && rec.subfolderName) {
      folderRecord.parentHandle = rec.parentHandle;
      folderRecord.parentName = rec.parentName || (rec.parentHandle && rec.parentHandle.name) || null;
      folderRecord.subfolderName = rec.subfolderName;
      folderRecord.lastSavedAt = rec.lastSavedAt || null;
      folderRecord.lastError = rec.lastError || null;
      folderRecord.pivotMigratedAt = rec.pivotMigratedAt || null;
      trace('folder: hydrated handle parent=' + folderRecord.parentName +
        ' subfolder=' + folderRecord.subfolderName +
        ' lastSavedAt=' + (folderRecord.lastSavedAt || '(never)') +
        ' pivotMigratedAt=' + (folderRecord.pivotMigratedAt || '(never)'));
    } else {
      trace('folder: no persisted handle (browser-only mode)');
    }
  } catch (e) {
    trace('folder: IDB hydrate failed: ' + (e && e.message || e));
  }
}

// ----- Subfolder helpers ----------------------------------------------------

async function _findOrCreateSubfolder(parentHandle, mode) {
  // mode: 'open-existing' → must use the existing default name; throws if
  //   it doesn't exist or doesn't contain relationships.db.
  // 'create-new' → pick the lowest-numbered unused name from "Fellows",
  //   "Fellows 2", "Fellows 3", ...
  // 'auto' (or null) → if "Fellows" exists with a relationships.db,
  //   return { requiresChoice: true, ... }; otherwise behave like
  //   'create-new' picking "Fellows".
  var name = FOLDER_SUBFOLDER_DEFAULT;
  if (mode === 'open-existing') {
    var existing;
    try {
      existing = await parentHandle.getDirectoryHandle(name);
    } catch (e) {
      var nfErr = new Error('"' + name + '" subfolder not found in this folder');
      nfErr.code = 'subfolder_missing';
      throw nfErr;
    }
    return { handle: existing, subfolderName: name };
  }
  if (mode === 'create-new') {
    var n = 1;
    while (true) {
      var candidate = (n === 1) ? FOLDER_SUBFOLDER_DEFAULT : (FOLDER_SUBFOLDER_DEFAULT + ' ' + n);
      var exists = await _subfolderExists(parentHandle, candidate);
      if (!exists) {
        var created = await parentHandle.getDirectoryHandle(candidate, { create: true });
        return { handle: created, subfolderName: candidate };
      }
      n++;
      if (n > 999) {
        throw new Error('could not find unused subfolder name after 999 tries');
      }
    }
  }
  // 'auto': probe "Fellows" — if it already exists with a relationships.db
  // we need the page to confirm.
  var probed = await _probeSubfolder(parentHandle, FOLDER_SUBFOLDER_DEFAULT);
  if (probed.exists && probed.hasFile) {
    var suggestion = await _suggestNextName(parentHandle);
    return {
      requiresChoice: true,
      existing: {
        subfolderName: FOLDER_SUBFOLDER_DEFAULT,
        counts: probed.counts,
        invalid: probed.invalid,
        invalidReason: probed.invalidReason,
        size: probed.size,
        lastModified: probed.lastModified
      },
      suggestion: suggestion
    };
  }
  // Empty default subfolder (or no subfolder at all) — happy path.
  var fresh = await parentHandle.getDirectoryHandle(FOLDER_SUBFOLDER_DEFAULT, { create: true });
  return { handle: fresh, subfolderName: FOLDER_SUBFOLDER_DEFAULT };
}

async function _subfolderExists(parentHandle, name) {
  try {
    await parentHandle.getDirectoryHandle(name);
    return true;
  } catch (e) { return false; }
}

async function _suggestNextName(parentHandle) {
  var n = 2;
  while (n < 999) {
    var candidate = FOLDER_SUBFOLDER_DEFAULT + ' ' + n;
    var exists = await _subfolderExists(parentHandle, candidate);
    if (!exists) return candidate;
    n++;
  }
  return FOLDER_SUBFOLDER_DEFAULT + ' ' + n;
}

// Read relationships.db out of a candidate subfolder and run inspectBytes
// over it (without touching the live OPFS pool slot). Used both by the
// collision probe and by readRelationshipsFromFolder.
async function _probeSubfolder(parentHandle, subfolderName) {
  var out = { exists: false, hasFile: false, counts: null, invalid: false, invalidReason: null, size: 0, lastModified: null };
  var sub;
  try {
    sub = await parentHandle.getDirectoryHandle(subfolderName);
  } catch (e) {
    return out; // subfolder doesn't exist
  }
  out.exists = true;
  var fh;
  try {
    fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE);
  } catch (e) {
    return out; // subfolder exists but no relationships.db
  }
  out.hasFile = true;
  try {
    var f = await fh.getFile();
    out.size = f.size;
    out.lastModified = f.lastModified;
    var bytes = new Uint8Array(await f.arrayBuffer());
    var inspection = await inspectBytes(bytes);
    if (inspection.valid) {
      out.counts = inspection.counts;
    } else {
      out.invalid = true;
      out.invalidReason = inspection.error || 'unreadable';
    }
  } catch (e) {
    out.invalid = true;
    out.invalidReason = (e && e.message) || String(e);
  }
  return out;
}

// ----- queryPermission wrapper ---------------------------------------------
async function _folderQueryPermission() {
  if (!folderRecord.parentHandle) return 'no-handle';
  if (typeof folderRecord.parentHandle.queryPermission !== 'function') {
    // Older browsers / non-FSA shims — treat as granted since the only way
    // we got here is via showDirectoryPicker on a browser that supports it.
    return 'granted';
  }
  try {
    var state = await folderRecord.parentHandle.queryPermission({ mode: 'readwrite' });
    folderRecord.lastPermission = state;
    return state;
  } catch (e) {
    folderRecord.lastPermission = 'denied';
    return 'denied';
  }
}

// ----- State snapshot for the page -----------------------------------------

async function _folderStateSnapshot() {
  var state = {
    hasHandle: !!folderRecord.parentHandle,
    parentName: folderRecord.parentName,
    subfolderName: folderRecord.subfolderName,
    permission: 'no-handle',
    lastSavedAt: folderRecord.lastSavedAt,
    lastError: folderRecord.lastError,
    fileLastModified: null,
    fileSize: null
  };
  if (!folderRecord.parentHandle) return state;
  state.permission = await _folderQueryPermission();
  if (state.permission === 'granted') {
    try {
      var sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
      var fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE);
      var f = await fh.getFile();
      state.fileLastModified = f.lastModified;
      state.fileSize = f.size;
    } catch (e) {
      // File missing or unreadable; not fatal — page surfaces empty state.
    }
  }
  return state;
}

// ----- Storage-mode helpers (Phase 2 pivot) ---------------------------------
//
// Folder-mode boot: read folder's relationships.db into the OPFS slot used
// by OpfsSAHPoolDb, so opening relDb against the slot sees the folder's
// content. The slot is treated as a transient working buffer — overwritten
// by the folder file on every boot. Folder is canonical.

async function _hydrateOpfsBufferFromFolder() {
  // Returns true if the slot was populated from folder bytes; false if the
  // folder file doesn't exist yet (caller bootstraps an empty schema).
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    return false;
  }
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
  } catch (e) {
    trace('folder: subfolder not found at boot — bootstrapping empty');
    return false;
  }
  var fh;
  try {
    fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE);
  } catch (e) {
    trace('folder: relationships.db not in subfolder at boot — bootstrapping empty');
    return false;
  }
  var bytes;
  try {
    var f = await fh.getFile();
    bytes = new Uint8Array(await f.arrayBuffer());
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'boot read: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    throw new Error('Could not read folder relationships.db at boot: ' + ((e && e.message) || e));
  }
  if (!bytes || !bytes.byteLength) {
    trace('folder: empty relationships.db at boot — bootstrapping empty');
    return false;
  }
  // Inspect before importing so we don't pollute the working buffer with
  // garbage and silently break the session.
  var inspection = await inspectBytes(bytes);
  if (!inspection.valid) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'boot inspect: ' + (inspection.error || 'unreadable') };
    await _folderRecordPersist();
    throw new Error('Folder relationships.db failed validation: ' + (inspection.error || 'unreadable'));
  }
  // If relDb is already open against the slot (shouldn't be at boot, but
  // defensive), close it first — importDb on an open slot is undefined
  // behavior on some SAH-pool versions.
  if (relDb) { try { relDb.close(); } catch (e) {} relDb = null; }
  poolUtil.importDb(RELATIONSHIPS_DB_SLOT, bytes);
  trace('folder: hydrated OPFS buffer from folder file (' + bytes.byteLength + ' bytes, ' +
    inspection.counts.groups + ' groups)');
  return true;
}

// One-time migration for users coming from Phase 1's hybrid state.
// On first boot in folder mode after the pivot, both the OPFS slot AND
// the folder file may contain valid data — possibly divergent if a
// previous-session sync failed. Resolve by trusting the newer copy and
// preserving the loser as `pre-pivot-<ISO>.<existing-name>.bak` so the
// user can manually recover if our newer-wins heuristic picked wrong.
async function _maybeRunPivotMigration() {
  if (folderRecord.pivotMigratedAt) return;
  // Check OPFS slot for existing data.
  var opfsHasData = false;
  var opfsBytes = null;
  try {
    var poolFiles = poolUtil.getFileNames();
    if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) !== -1) {
      opfsBytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT);
      if (opfsBytes && opfsBytes.byteLength) {
        var opfsInspect = await inspectBytes(opfsBytes);
        opfsHasData = opfsInspect.valid && (
          opfsInspect.counts.groups + opfsInspect.counts.members +
          opfsInspect.counts.tags + opfsInspect.counts.notes +
          opfsInspect.counts.settings) > 0;
      }
    }
  } catch (e) {
    trace('pivot-migration: OPFS inspect failed (' + (e && e.message || e) + ')');
  }
  // Check folder for existing data.
  var folderHasData = false;
  var folderBytes = null;
  var folderFileLastModified = 0;
  try {
    var sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
    var fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE);
    var f = await fh.getFile();
    folderFileLastModified = f.lastModified;
    folderBytes = new Uint8Array(await f.arrayBuffer());
    if (folderBytes && folderBytes.byteLength) {
      var folderInspect = await inspectBytes(folderBytes);
      folderHasData = folderInspect.valid && (
        folderInspect.counts.groups + folderInspect.counts.members +
        folderInspect.counts.tags + folderInspect.counts.notes +
        folderInspect.counts.settings) > 0;
    }
  } catch (e) {
    // Subfolder or file missing — common case, not an error.
  }
  if (!opfsHasData && !folderHasData) {
    trace('pivot-migration: fresh install or empty (OPFS + folder both empty); nothing to migrate');
    folderRecord.pivotMigratedAt = new Date().toISOString();
    await _folderRecordPersist();
    return;
  }
  if (opfsHasData && !folderHasData) {
    trace('pivot-migration: OPFS has data, folder empty — writing OPFS to folder');
    await _writeBytesToFolder(opfsBytes);
    folderRecord.pivotMigratedAt = new Date().toISOString();
    await _folderRecordPersist();
    return;
  }
  if (!opfsHasData && folderHasData) {
    trace('pivot-migration: folder has data, OPFS empty — boot will hydrate from folder');
    folderRecord.pivotMigratedAt = new Date().toISOString();
    await _folderRecordPersist();
    return;
  }
  // Both have data. Pick newer.
  // Heuristic: folder's lastModified comes from the OS; OPFS doesn't expose
  // a sibling mtime. Use folderRecord.lastSavedAt as a proxy for "folder
  // was successfully written at this time" — if both folderFileLastModified
  // and OPFS state are present, lastSavedAt being absent OR stale means
  // OPFS likely has unsynced post-Phase-1 mutations. Conservative:
  // compare hash; if equal, treat folder as canonical; if different,
  // preserve OPFS as the pre-pivot backup AND adopt folder as canonical
  // (Phase 1 manual-save users almost always have folder == OPFS).
  var opfsHash = await _sha256Hex(opfsBytes);
  var folderHash = await _sha256Hex(folderBytes);
  if (opfsHash === folderHash) {
    trace('pivot-migration: OPFS and folder content match; folder is canonical');
    folderRecord.pivotMigratedAt = new Date().toISOString();
    await _folderRecordPersist();
    return;
  }
  // Genuinely divergent. Preserve OPFS state as a pre-pivot backup
  // sibling in the folder, then continue with folder as canonical.
  // (A user who realizes the wrong side won can copy the .bak back
  // into place via Settings → Restore.)
  trace('pivot-migration: OPFS and folder content DIFFER (opfs hash=' + opfsHash.slice(0, 8) +
    ' folder hash=' + folderHash.slice(0, 8) + ') — preserving OPFS as pre-pivot.bak, keeping folder');
  try {
    var ts = new Date().toISOString().replace(/[:.]/g, '-');
    var bakName = BACKUP_PREFIX + 'pre-pivot-' + ts;
    await _writeBytesToFolder(opfsBytes, bakName);
    trace('pivot-migration: preserved OPFS as folder/' + folderRecord.subfolderName + '/' + bakName);
  } catch (e) {
    trace('pivot-migration: pre-pivot bak write failed: ' + (e && e.message || e) +
      ' — proceeding with folder as canonical anyway (OPFS state may be unrecoverable)');
  }
  folderRecord.pivotMigratedAt = new Date().toISOString();
  await _folderRecordPersist();
}

// Atomic folder-file write helper. Used by the pivot migration and by
// the per-commit hook. Default filename is the live relationships.db;
// caller can override for backup writes. Updates folderRecord.lastSavedAt
// on success / lastError on failure.
//
// Serialized via the Web Locks API on the name FOLDER_WRITE_LOCK_NAME.
// Same-tab JS callers are already serial (single-threaded worker), but
// the lock matters across agents in the same browser context — both
// for defense-in-depth against future code paths that bypass the OPFS
// SAH-pool exclusivity, and as the load-bearing serialization point
// when the multi-tab takeover plan ships (graceful handoff window
// where two workers briefly coexist). `ifAvailable: true` fails fast
// rather than queueing — a stuck writer must surface as a visible
// error, not a hung mutation. Callers translate the resulting
// FOLDER_LOCKED error code into the write-failed badge state.
async function _writeBytesToFolder(bytes, filename) {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    var ne = new Error('no folder configured');
    ne.code = 'no_folder';
    throw ne;
  }
  return await navigator.locks.request(
    FOLDER_WRITE_LOCK_NAME,
    { mode: 'exclusive', ifAvailable: true },
    async function (lock) {
      if (!lock) {
        folderRecord.lastError = {
          at: new Date().toISOString(),
          reason: 'folder write blocked: another tab or window is editing this folder'
        };
        await _folderRecordPersist();
        var le = new Error('Folder write blocked by another agent holding ' + FOLDER_WRITE_LOCK_NAME);
        le.code = 'folder_locked_by_another_tab';
        throw le;
      }
      return await _writeBytesToFolderUnlocked(bytes, filename);
    }
  );
}

async function _writeBytesToFolderUnlocked(bytes, filename) {
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName, { create: true });
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'subfolder open: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var se = new Error('Could not open subfolder ' + folderRecord.subfolderName + ': ' + ((e && e.message) || e));
    se.code = 'subfolder_open_failed';
    throw se;
  }
  var targetName = filename || FOLDER_RELATIONSHIPS_FILE;
  try {
    var fh = await sub.getFileHandle(targetName, { create: true });
    var writable = await fh.createWritable();
    await writable.write(bytes);
    await writable.close();
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'write ' + targetName + ': ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var we = new Error('Folder write to ' + targetName + ' failed: ' + ((e && e.message) || e));
    we.code = 'write_failed';
    throw we;
  }
  // Only update lastSavedAt for the canonical file, not backup siblings.
  if (targetName === FOLDER_RELATIONSHIPS_FILE) {
    folderRecord.lastSavedAt = new Date().toISOString();
    folderRecord.lastError = null;
    await _folderRecordPersist();
  }
}

// ----- Folder-resident backup ring helpers ---------------------------------
//
// In folder mode the auto-backup ring lives alongside relationships.db
// in the user's Fellows/ subfolder, as `relationships.db.bak.<ISO>`
// siblings. Visible in Finder; the user can see + recover their own
// backups without opening the app. OPFS-only-mode users keep today's
// OPFS-resident ring, unchanged. See plans/user_folder_storage.md
// § Architecture → Auto-backup ring (folder mode).

async function _listFolderBackups() {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) return [];
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
  } catch (e) {
    return [];
  }
  var out = [];
  try {
    for await (var entry of sub.values()) {
      if (entry.kind === 'file' && entry.name.indexOf(BACKUP_PREFIX) === 0) {
        try {
          var f = await entry.getFile();
          out.push({ name: entry.name, size: f.size, lastModified: f.lastModified });
        } catch (e) {
          // File disappeared between iteration and getFile — skip.
        }
      }
    }
  } catch (e) {
    return [];
  }
  // Sort lexicographically — backup filenames embed an ISO timestamp
  // after BACKUP_PREFIX so this is also chronological order.
  out.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
  return out;
}

async function _folderReadBackup(name) {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    throw new Error('no folder configured');
  }
  var sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
  var fh = await sub.getFileHandle(name);
  var f = await fh.getFile();
  return new Uint8Array(await f.arrayBuffer());
}

async function _rotateFolderBackups() {
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) return;
  var backups = await _listFolderBackups();
  if (backups.length <= BACKUP_KEEP) return;
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
  } catch (e) { return; }
  while (backups.length > BACKUP_KEEP) {
    var oldest = backups.shift();
    try {
      await sub.removeEntry(oldest.name);
      trace('folder-backup: rotated out ' + oldest.name);
    } catch (e) {
      trace('folder-backup: rotate removeEntry failed for ' + oldest.name);
    }
  }
}

// ----- Post-commit folder write (Phase 2 pivot) -----------------------------
//
// Dynamic check (vs. the boot-time `_storageMode` global) is intentional:
// a user who booted without a folder handle and then attached one
// mid-session via Settings → Choose data folder (Phase 1 UX) should have
// their subsequent mutations land in the folder, not just OPFS. Same for
// the reconnect-after-permission-lapse case.
//
// Failures populate folderRecord.lastError but do NOT throw — the
// mutation succeeded in OPFS, the user just needs to retry the save
// (Settings → Save now button). The page sees the badge flip to
// "Last save failed" on its next getFolderState poll.
async function _maybeWriteFolderAfterCommit() {
  if (!poolUtil) return;
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) return;
  var perm = await _folderQueryPermission();
  if (perm !== 'granted') {
    // Folder configured but currently inaccessible. The badge already
    // shows that state via the page's getFolderState poll. Don't try
    // to write — would just fail and populate lastError with noise.
    return;
  }
  var bytes;
  try {
    bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT);
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'post-commit export: ' + ((e && e.message) || e) };
    trace('folder: post-commit export failed: ' + ((e && e.message) || e));
    return;
  }
  if (!bytes || !bytes.byteLength) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'post-commit export was empty' };
    return;
  }
  try {
    await _writeBytesToFolder(bytes);
  } catch (e) {
    // lastError already populated by the helper. Don't rethrow — the
    // OPFS commit is the user's data; they need to retry the folder
    // write, not redo the mutation. Override the message for the
    // lock-held case so the badge tells the user something actionable
    // ("close the other window") instead of a raw exception string.
    if (e && e.code === 'folder_locked_by_another_tab') {
      folderRecord.lastError = {
        at: new Date().toISOString(),
        reason: 'Another window has this folder open — close it, then make any change to retry the save.'
      };
      await _folderRecordPersist();
    }
    trace('folder: post-commit folder write failed: ' + ((e && e.message) || e));
  }
}

// ----- Folder RPCs ----------------------------------------------------------

handlers.getFolderState = async function () {
  return _folderStateSnapshot();
};

// Step one of the picker flow. Page passes the handle returned by
// window.showDirectoryPicker. `mode` controls the collision policy:
//   - undefined / 'auto' — happy path; if the default subfolder already
//     contains a relationships.db, return { requiresChoice, existing,
//     suggestion } so the page can show the open-existing vs Create
//     Fellows N dialog without committing anything.
//   - 'open-existing' — open the default subfolder. Throws if it doesn't
//     exist or doesn't have relationships.db.
//   - 'create-new' — create the next-numbered subfolder.
handlers.setFolderHandle = async function (args) {
  var parentHandle = args && args.handle;
  if (!parentHandle) throw new Error('missing handle');
  // queryPermission/requestPermission live on FileSystemHandle. The picker
  // call should have returned 'granted', but verify so a stale call (e.g.
  // the page restored a stub) fails cleanly.
  var perm = 'granted';
  if (typeof parentHandle.queryPermission === 'function') {
    try { perm = await parentHandle.queryPermission({ mode: 'readwrite' }); }
    catch (e) { perm = 'denied'; }
  }
  if (perm !== 'granted') {
    var permErr = new Error('Picker returned a handle without readwrite permission (' + perm + ')');
    permErr.code = 'permission_not_granted';
    throw permErr;
  }
  var mode = (args && args.mode) || 'auto';
  var result = await _findOrCreateSubfolder(parentHandle, mode);
  if (result.requiresChoice) {
    // Page will re-invoke with mode='open-existing' or 'create-new'.
    // Don't persist anything yet.
    return {
      ok: false,
      requiresChoice: true,
      parentName: parentHandle.name || null,
      existing: result.existing,
      suggestion: result.suggestion
    };
  }
  folderRecord.parentHandle = parentHandle;
  folderRecord.parentName = parentHandle.name || null;
  folderRecord.subfolderName = result.subfolderName;
  // Don't clobber lastSavedAt — open-existing legitimately keeps it null
  // until the user explicitly saves.
  if (mode === 'create-new' || folderRecord.lastSavedAt === undefined) {
    folderRecord.lastSavedAt = null;
  }
  folderRecord.lastError = null;
  await _folderRecordPersist();
  trace('folder: set parent=' + folderRecord.parentName + ' subfolder=' + folderRecord.subfolderName + ' mode=' + mode);
  return {
    ok: true,
    parentName: folderRecord.parentName,
    subfolderName: folderRecord.subfolderName
  };
};

handlers.clearFolderHandle = async function () {
  folderRecord = _emptyFolderRecord();
  try { await _folderIdbDelete(); } catch (e) { trace('folder: IDB delete failed: ' + (e && e.message || e)); }
  trace('folder: cleared');
  return { ok: true };
};

handlers.checkFolderPermission = async function () {
  var state = await _folderQueryPermission();
  return { permission: state };
};

// Re-hands the in-memory handle to the page so the page can call
// requestPermission inside a user-gesture handler. The handle is
// structured-cloned across; the worker keeps its own copy. Returns null
// when no handle is persisted.
handlers.getFolderHandleForReconnect = async function () {
  if (!folderRecord.parentHandle) return { handle: null };
  return { handle: folderRecord.parentHandle };
};

handlers.writeRelationshipsToFolder = async function () {
  if (!poolUtil) throw new Error('pool util unavailable');
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    var ne = new Error('no folder configured');
    ne.code = 'no_folder';
    throw ne;
  }
  var perm = await _folderQueryPermission();
  if (perm !== 'granted') {
    var pe = new Error('folder permission not granted (' + perm + ')');
    pe.code = 'permission_required';
    pe.permission = perm;
    throw pe;
  }
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) === -1) {
    var nde = new Error('no relationships.db to save (worker hasn\'t opened it yet)');
    nde.code = 'no_relationships_db';
    throw nde;
  }
  var bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT);
  if (!bytes || !bytes.byteLength) {
    var ee = new Error('relationships.db export was empty');
    ee.code = 'empty_export';
    throw ee;
  }
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName, { create: true });
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'subfolder open: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var se = new Error('Could not open subfolder ' + folderRecord.subfolderName + ': ' + ((e && e.message) || e));
    se.code = 'subfolder_open_failed';
    throw se;
  }
  // FileSystemWritableFileStream.close() commits atomically per spec —
  // the browser writes to a temp file and renames on close. No need to
  // do .tmp + rename ourselves.
  var fh;
  try {
    fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE, { create: true });
    var writable = await fh.createWritable();
    await writable.write(bytes);
    await writable.close();
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'write: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var we = new Error('Folder write failed: ' + ((e && e.message) || e));
    we.code = 'write_failed';
    throw we;
  }
  var now = new Date().toISOString();
  folderRecord.lastSavedAt = now;
  folderRecord.lastError = null;
  await _folderRecordPersist();
  trace('folder: wrote ' + bytes.byteLength + ' bytes to ' +
    folderRecord.subfolderName + '/' + FOLDER_RELATIONSHIPS_FILE + ' at ' + now);
  return { ok: true, bytesWritten: bytes.byteLength, lastSavedAt: now };
};

handlers.readRelationshipsFromFolder = async function () {
  if (!poolUtil) throw new Error('pool util unavailable');
  if (!folderRecord.parentHandle || !folderRecord.subfolderName) {
    var ne = new Error('no folder configured');
    ne.code = 'no_folder';
    throw ne;
  }
  var perm = await _folderQueryPermission();
  if (perm !== 'granted') {
    var pe = new Error('folder permission not granted (' + perm + ')');
    pe.code = 'permission_required';
    pe.permission = perm;
    throw pe;
  }
  var sub;
  try {
    sub = await folderRecord.parentHandle.getDirectoryHandle(folderRecord.subfolderName);
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'subfolder open: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var se = new Error('Could not open subfolder ' + folderRecord.subfolderName + ': ' + ((e && e.message) || e));
    se.code = 'subfolder_open_failed';
    throw se;
  }
  var fh;
  try {
    fh = await sub.getFileHandle(FOLDER_RELATIONSHIPS_FILE);
  } catch (e) {
    var nfe = new Error('No relationships.db in ' + folderRecord.subfolderName + ' yet');
    nfe.code = 'no_file_in_folder';
    throw nfe;
  }
  var bytes;
  var fileLastModified = null;
  try {
    var f = await fh.getFile();
    fileLastModified = f.lastModified;
    bytes = new Uint8Array(await f.arrayBuffer());
  } catch (e) {
    folderRecord.lastError = { at: new Date().toISOString(), reason: 'read: ' + ((e && e.message) || e) };
    await _folderRecordPersist();
    var re = new Error('Folder read failed: ' + ((e && e.message) || e));
    re.code = 'read_failed';
    throw re;
  }
  // Reuse importRelationshipsBytes — it inspects, snapshots the current
  // OPFS state into the auto-backup ring (so reading-back-a-stale-folder
  // is undoable), then atomically replaces the OPFS slot.
  var result = await handlers.importRelationshipsBytes({ bytes: bytes });
  // After a successful read, the OPFS working copy matches the folder
  // file — "saved" semantics hold. Tag lastSavedAt with the file's
  // mtime so the badge flips to Saved with the file's authoring time
  // (more honest than `now` for an open-existing flow — the user
  // didn't author this version *now*).
  if (fileLastModified) {
    folderRecord.lastSavedAt = new Date(fileLastModified).toISOString();
  }
  folderRecord.lastError = null;
  await _folderRecordPersist();
  return {
    counts: result.counts,
    preRestoreSnapshot: result.preRestoreSnapshot,
    bytesRead: bytes.byteLength,
    lastSavedAt: folderRecord.lastSavedAt
  };
};

// ===== Dispatcher ===========================================================

self.onmessage = async function (ev) {
  var data = ev.data || {};
  var id = data.id;
  var op = data.op;
  var args = data.args;
  var handler = handlers[op];
  if (!handler) {
    self.postMessage({ id: id, ok: false, error: 'unknown op: ' + op });
    return;
  }
  try {
    var result = await handler(args);
    self.postMessage({ id: id, ok: true, result: result });
  } catch (e) {
    self.postMessage({
      id: id, ok: false,
      error: (e && e.message) || String(e),
      errorName: e && e.name,
      errorCode: e && e.code,
      httpStatus: e && e.httpStatus,
      // ensureFellowsDb attaches the post-failure meta blob (with
      // last_failure_at / last_failure_reason populated) so the page
      // can surface a soft warning without a second RPC roundtrip.
      meta: e && e.meta,
      stack: e && e.stack
    });
  }
};
