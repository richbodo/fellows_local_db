// EHF Fellows local DB — sqlite-wasm worker (relationships.db only).
//
// Runs sqlite-wasm + OPFS-SAH-Pool in dedicated-worker scope. Used as a
// fallback when the main thread can't init SAH-pool because Chrome's
// configuration strips FileSystemFileHandle.prototype.createSyncAccessHandle
// from the main-thread prototype (PR #95–#98 found this on a vanilla
// Chrome 147 install). Workers expose the API even when the main thread
// hides it.
//
// Scope: relationships.db only. The fellows directory (read-only contact
// data) keeps using the API provider on the main thread — no need to
// re-download a ~1.5MB fellows.db into the worker just to read it.
// The hybrid provider on the main thread (createHybridApiAndWorkerProvider
// in app.js) routes fellows queries to API and relationships queries here.
//
// Protocol:
//   main → worker: { id, op, args }
//   worker → main: { id, ok: true,  result }
//                  { id, ok: false, error, errorName?, stack? }
//
// First message must be op='init' with { gitSha }.

'use strict';

// Sibling import — this file lives in /vendor/ alongside sqlite3.js.
// The relative path is what makes sqlite-wasm's scriptDirectory resolve
// to /vendor/, so its internal locateFile('sqlite3.wasm') finds the
// companion /vendor/sqlite3.wasm. (Earlier this worker lived at
// /sqlite-worker.js and the wasm look-up resolved to /sqlite3.wasm — 404.)
importScripts('./sqlite3.js');

// ===== Constants (mirrored from app.js — keep in sync) ======================

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

var BACKUP_PREFIX = 'relationships.db.bak.';
var BACKUP_SENTINEL = 'last_seen_sha.txt';
var BACKUP_KEEP = 3;
var RESTORE_STAGING_SLOT = 'relationships.db.restore-staging';
var REQUIRED_RESTORE_TABLES = ['groups', 'group_members', 'fellow_tags', 'fellow_notes', 'settings'];

// ===== State ================================================================

var sqlite3 = null;
var poolUtil = null;
var relDb = null;
var gitSha = null;
var bootTrace = [];

function trace(msg) { bootTrace.push(new Date().toISOString() + ' ' + String(msg)); }

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
  db.exec(RELATIONSHIPS_SCHEMA_SQL);
  db.exec('PRAGMA user_version = 1');
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

async function maybeBackupRelationshipsDb() {
  if (!gitSha) {
    trace('backup: skipped (no build SHA)');
    return { backedUp: false, reason: 'no SHA' };
  }
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  var hasRelDb = poolFiles.indexOf('relationships.db') !== -1;
  var prevSha = await _opfsReadText(BACKUP_SENTINEL);
  if (!hasRelDb) {
    try { await _opfsWriteText(BACKUP_SENTINEL, gitSha); } catch (e) {}
    trace('backup: skipped (no relationships.db yet)');
    return { backedUp: false, reason: 'first install' };
  }
  if (prevSha === gitSha) {
    trace('backup: skipped (no SHA change)');
    return { backedUp: false, reason: 'no SHA change' };
  }
  var bytes;
  try { bytes = poolUtil.exportFile('relationships.db'); }
  catch (e) {
    trace('backup: exportFile failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'export failed' };
  }
  if (!bytes || !bytes.byteLength) {
    try { await _opfsWriteText(BACKUP_SENTINEL, gitSha); } catch (e) {}
    return { backedUp: false, reason: 'empty file' };
  }
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _opfsWriteBinary(backupName, bytes); }
  catch (e) {
    trace('backup: write failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'write failed' };
  }
  await _rotateRelationshipsBackups();
  try { await _opfsWriteText(BACKUP_SENTINEL, gitSha); } catch (e) {}
  trace(
    'backup: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes); ' +
    'sentinel ' + (prevSha || '<none>') + ' → ' + gitSha
  );
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

async function snapshotRelationshipsDbToBackup() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf('relationships.db') === -1) {
    return { backedUp: false, reason: 'no relationships.db' };
  }
  var bytes;
  try { bytes = poolUtil.exportFile('relationships.db'); }
  catch (e) { return { backedUp: false, reason: 'export failed: ' + (e && e.message || e) }; }
  if (!bytes || !bytes.byteLength) return { backedUp: false, reason: 'empty file' };
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _opfsWriteBinary(backupName, bytes); }
  catch (e) { return { backedUp: false, reason: 'write failed: ' + (e && e.message || e) }; }
  await _rotateRelationshipsBackups();
  trace('snapshot: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes)');
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

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

// ===== RPC handlers =========================================================

var handlers = {};

handlers.init = async function (args) {
  args = args || {};
  gitSha = args.gitSha || null;
  trace('init: starting');
  if (typeof globalThis.sqlite3InitModule !== 'function') {
    throw new Error('sqlite3InitModule missing in worker (vendor/sqlite3.js failed to load?)');
  }
  sqlite3 = await globalThis.sqlite3InitModule();
  trace('sqlite3InitModule: OK');
  if (typeof sqlite3.installOpfsSAHPoolVfs !== 'function') {
    throw new Error('sqlite3.installOpfsSAHPoolVfs missing in worker build');
  }
  poolUtil = await sqlite3.installOpfsSAHPoolVfs();
  trace('installOpfsSAHPoolVfs: OK');

  // Auto-backup before opening relationships.db for app use, mirrors what
  // the main-thread sqlite provider does on initOpfsDataProvider.
  await maybeBackupRelationshipsDb();

  try {
    relDb = new poolUtil.OpfsSAHPoolDb('relationships.db');
    bootstrapRelationshipsSchema(relDb);
    trace('relationships.db: open + schema OK');
  } catch (relErr) {
    trace('relationships.db: open failed (' + (relErr && relErr.message || relErr) + ')');
    relDb = null;
  }

  return {
    ok: true,
    relDbOpen: !!relDb,
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
  // its in-memory cache (populated by getList/getFull). Mirrors how the
  // main-thread sqlite provider does it (attachMemberNames in app.js).
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
  relDb.exec('BEGIN');
  try {
    dbRun(relDb, 'INSERT INTO groups(name, note, created_at, updated_at) VALUES (?, ?, ?, ?)',
          [name, note, now, now]);
    var idRow = dbSelectOne(relDb, 'SELECT last_insert_rowid() AS id', null);
    var gid = idRow && idRow.id;
    for (var i = 0; i < ids.length; i++) {
      dbRun(relDb, 'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)', [gid, ids[i]]);
    }
    relDb.exec('COMMIT');
    return await handlers.getGroup({ id: gid });
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
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
    return await handlers.getGroup({ id: id });
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
};

handlers.deleteGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
  if (!existing) return false;
  dbRun(relDb, 'DELETE FROM groups WHERE id = ?', [id]);
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
  return { key: key, value: value };
};

// ----- Backup / restore -----------------------------------------------------

handlers.exportRelationshipsBytes = async function () {
  if (!poolUtil) throw new Error('pool util unavailable');
  return poolUtil.exportFile('relationships.db');
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
  poolUtil.importDb('relationships.db', bytes);
  relDb = new poolUtil.OpfsSAHPoolDb('relationships.db');
  bootstrapRelationshipsSchema(relDb);
  return {
    counts: inspection.counts,
    preRestoreSnapshot: snap && snap.backedUp ? snap.name : null
  };
};

handlers.listRelationshipsBackups = async function () {
  if (!poolUtil) return [];
  var raw = await listRelationshipsBackups();
  var out = [];
  // Sequential — staging slot is shared across inspects.
  for (var i = 0; i < raw.length; i++) {
    var entry = raw[i];
    try {
      var bytes = await _opfsReadBinary(entry.name);
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
  var backups = await listRelationshipsBackups();
  var match = null;
  for (var i = 0; i < backups.length; i++) {
    if (backups[i].name === name) { match = backups[i]; break; }
  }
  if (!match) throw new Error('Backup not found: ' + name);
  var bytes = await _opfsReadBinary(name);
  return await handlers.importRelationshipsBytes({ bytes: bytes });
};

// Diagnostics — pulls the worker's own boot trace.
handlers.getTrace = async function () { return bootTrace.slice(); };

// TEMPORARY: Phase 0 COOP/COEP precheck. Verifies the worker scope inherits
// crossOriginIsolated from the owner page (Caddy + dev server set COOP/COEP).
// SAH-pool gates SharedArrayBuffer / Atomics on this, so a false here means
// the local-first worker plan stalls until the proxy/server is fixed. Remove
// this handler once dev + prod return both flags true.
handlers.probeCoi = async function () {
  return {
    crossOriginIsolated:
      typeof self.crossOriginIsolated !== 'undefined' ? self.crossOriginIsolated : null,
    hasSAB: typeof SharedArrayBuffer !== 'undefined'
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
      stack: e && e.stack
    });
  }
};
