# Lock My User Data — opt-in encryption-at-rest for `relationships.db`

**Status:** plan, not yet implemented. Tier 2 #3 of the security review
(`security_review/2026-05-08_local_vs_saas_risk.md`), following SRI (PR
#143) and signed bundles (PR #146).

**Scope:** user-driven, opt-in app-layer encryption of the user-authored
`relationships.db` and its OPFS backups. `fellows.db` is *not* encrypted
— it's shared directory data, gated by the magic link.

**Non-scope:**
- Forced passphrase at install. This is "I'm being paranoid right now,"
  not "everyone always."
- Auto-lock on tab-hidden / quit timers / `pagehide`. v1 is **manual
  lock only** — the user clicks **Lock now** in Settings (or the topbar
  chip) to encrypt. This is the conscious trade-off: the user is
  **aware** of every lock transition rather than having silent ones.
  The silent-failure gap (forgetting to click Lock Now before closing
  the tab leaves that session's data plaintext on disk until the next
  explicit lock) is filed as issue
  [#154](https://github.com/richbodo/fellows_local_db/issues/154) for
  follow-up design — addressing it well needs a separate conversation
  about how to message the transition to the user.
- Passphrase recovery. Forgotten passphrase = effectively wiped; the
  user's recovery path is **Reset Everything** (already shipped). This
  is honest scoping, not a gap.
- `fellows.db` encryption.

## Threat model — what this defends, what it does not

**Defends against:**
- A discarded or stolen device read offline (drive imaging, OPFS file
  extraction).
- A drive image taken while the OS is locked.

**Does NOT defend against:**
- Live malware on the unlocked OS — the encryption key is in worker
  memory while unlocked.
- Shoulder-surfing / screen capture while unlocked.
- Weak passphrases. The KDF makes offline cracking expensive but not
  infeasible against `password123`.
- A forgotten passphrase. There is no recovery.

This boundary lives in user-facing copy on the Settings panel and in
`docs/users_manual.md` § Updates → Lock my user data.

## Crypto primitives

- **KDF:** PBKDF2-SHA256, 600 000 iterations (OWASP 2023 PBKDF2-SHA256
  recommendation), 16-byte random salt per file format version. WebCrypto
  native — no new vendored dependency. Format header carries the KDF id
  + iteration count + salt so a future migration to Argon2id (vendored
  wasm) lands without breaking existing locked DBs.
- **Cipher:** AES-256-GCM with 96-bit random IV per ciphertext (a
  different IV for every locked file even though the key is shared).
  128-bit auth tag, the WebCrypto default.
- **Key material:** the derived `CryptoKey` is non-extractable and lives
  only in worker memory. The user's plaintext passphrase string is
  zeroed (best-effort — JS doesn't guarantee zeroing) and the reference
  dropped as soon as the key is derived. The main thread never holds the
  derived key.

## Locked-file envelope (`v1`)

Self-describing binary blob, written as one OPFS file. The format is
versioned so v2 (e.g. Argon2id) can land later.

```
Offset  Length    Field
0       8         Magic: "EHFLOCK\0"   (so a misfiled blob is diagnosable)
8       1         Format version       (= 1)
9       1         KDF id               (1 = PBKDF2-SHA256)
10      4         KDF iterations       (uint32 big-endian; = 600000 for v1)
14      2         Salt length          (uint16 big-endian; = 16 for PBKDF2)
16      <Slen>    Salt bytes
16+Slen 12        AES-GCM IV (96-bit nonce)
28+Slen <rest>    AES-GCM ciphertext (plaintext bytes + 16-byte auth tag)
```

The auth tag is part of the ciphertext per WebCrypto convention; a wrong
passphrase fails decrypt atomically with `OperationError`. There is no
separate "verifier" blob — the GCM tag is the verifier.

## OPFS layout

**Unlocked (today's layout):**
```
/relationships.db                  (SAH-pool slot, live RW)
/relationships.db.bak.<ISO>        (OPFS root, plaintext)
/fellows.db                        (read-only, never touched by lock)
/fellows.db.meta.json
```

**Locked:**
```
/relationships.db.locked           (OPFS root, encrypted blob)
/relationships.db.bak.<ISO>.locked (OPFS root, each backup individually encrypted)
/fellows.db                        (unchanged)
/fellows.db.meta.json
```

**Lock-state detection** is by file presence:
- `.locked` siblings present → locked (or lock-in-progress, see below).
- Plaintext `relationships.db` in SAH pool present → unlocked.
- Neither → first install.

This avoids a separate "lock enabled" sentinel that could disagree with
the actual file state.

## Lock-in-progress recovery

A naïve lock sequence (`encrypt all → delete all plaintext`) can leave
half-encrypted state on crash. Order matters because a backup ciphertext
must replace its plaintext atomically before we delete the source.

**Lock sequence (worker):**
1. For each `relationships.db.bak.<ISO>` (oldest first):
   - Read plaintext, encrypt, write `relationships.db.bak.<ISO>.locked`.
   - Read back, decrypt-and-verify (auth tag check).
   - `removeEntry` the plaintext.
2. Export live `relationships.db` from the SAH pool, encrypt, write
   `relationships.db.locked` at OPFS root.
3. Read back, decrypt-and-verify.
4. Close `relDb` handle, `removeEntry` the SAH-pool slot.

**Boot-time recovery:** on `init`, if both plaintext and `.locked`
siblings exist for the same logical file (e.g. `bak.2026-05-13T...`
*and* `bak.2026-05-13T....locked`), trust the `.locked` (it survived
crash + auth-tag verifies) and delete the plaintext. If the `.locked`
exists but auth tag fails on the resume check, log + leave both in
place; the user sees an unlock failure with a diagnostic message and
can use **Reset Everything**.

## Worker RPCs

Added to `app/static/vendor/sqlite-worker.js`. All mutating ops require
WORKER_RPC_VERSION + RELATIONSHIPS_SCHEMA_VERSION match (per the
existing guard pattern):

| RPC | Inputs | Outputs | Notes |
|---|---|---|---|
| `getLockState` | — | `{enabled, locked, kdf, iters, formatVersion}` | Read-only. Safe to call before unlock. Reads file presence; doesn't decrypt anything. |
| `enableLock` | `{passphrase}` | `{ok: true}` | Derives key, encrypts live DB + all backups, deletes plaintext. Errors if already enabled. Closes `relDb` — caller should `unlock` to resume. |
| `unlock` | `{passphrase}` | `{ok: true, counts}` | Decrypts `.db.locked` → SAH pool → opens `relDb`. Backup `.locked` files stay encrypted until used (lazy). Wrong passphrase → throws `wrong-passphrase` error. |
| `lock` | — | `{ok: true}` | Re-encrypts live DB + any new backups created since unlock; deletes plaintext. Errors if not currently unlocked. |
| `changePassphrase` | `{oldPassphrase, newPassphrase}` | `{ok: true}` | Verifies old, derives new key + new salt, re-encrypts every `.locked` file with the new key. All-or-nothing: write new files alongside, verify all, then delete old. |
| `disableLock` | `{passphrase}` | `{ok: true}` | Decrypts every `.locked` file → plaintext OPFS files → deletes ciphertext. Future backups are plaintext. |

The `CryptoKey` lives in worker module scope as `lockKey`; cleared on
`lock` and `disableLock`.

## Discoverability — out of the way by default

The feature must not get in the way of users who don't want it. Concretely:

- **No boot-time prompt, banner, or toast** advertises the feature.
  Users who never enable it see the app exactly as they do today.
- **No code path even runs.** WebCrypto calls, lock-state probes, and
  the unlock card are entered only when a "lock is enabled" marker is
  present (see § OPFS layout — file-presence detection).
- **One entry point: `#/settings`.** A single closed section sits below
  *Your saved data*. Users who don't read Settings don't discover it
  until they go looking.

## Settings UI (main thread)

New panel on `#/settings`, after the existing "Your saved data" section.
Three states:

1. **Disabled** (default — what every non-user sees forever).
   - Header: **Lock my saved data**.
   - One-line copy: "Encrypt your groups, notes, and tags with a
     password you choose. Off by default."
   - Button: **Set up locking…** → "honesty-first" modal (next subsection).

2. **Enabled, currently unlocked** (after the user has set it up).
   - Status row: **"Lock is set up. Your data is currently unlocked."**
     (load-bearing copy: the user is aware that "set up" ≠ "encrypted
     right now").
   - Buttons: **Lock now**, **Change password…**, **Turn off locking…**.
   - **Lock now** → `lock` RPC → page re-renders into locked-boot UX
     (next section).
   - **Change password** → modal: current password + new + confirm new.
   - **Turn off locking** → modal: current password + plain-language
     copy ("This decrypts your saved data and returns it to its
     unencrypted state on this device.").

3. **Enabled, currently locked.** The Settings route is gated behind
   the unlock card; this state isn't reachable on the panel itself.

### The set-up modal (honesty-first)

Two steps, single modal. Step 1 is plain-language acknowledgement of
the trade-off **before** any password field appears.

**Step 1 — "Before you turn this on"**

> **Before you turn this on**
>
> Locking encrypts your saved groups, notes, and tags so that if someone
> steals or images this device, they can't read them.
>
> It does **not** protect against malware running on this device, or
> against someone using the device while it's unlocked.
>
> **There is no password recovery.** If you forget your password, your
> saved data is gone. Your only option will be to reset everything. The
> fellow directory itself is not affected.
>
> It's a good idea to store this password in a password manager — like
> Google Password Manager, 1Password, Bitwarden, or a local password
> database that you back up — rather than relying on memory.
>
> ☐ I understand there is no password recovery.
>
> [ Cancel ]  [ Continue ]

**Step 2 — password entry**

- `Password` (type=password, autocomplete=new-password) with a
  "Show password" toggle.
- `Confirm password`.
- No strength meter (theater; the KDF is the real defense).
- Submit → `enableLock` RPC (encrypts live DB + any existing backups in
  place, deletes plaintext) → immediately reloads into the locked-boot
  flow so the very next thing the user sees is the unlock card. This
  self-demos the steady-state: "ah, *this* is what happens every time I
  open the app from now on."

## Locked-boot UX

When `getLockState().locked === true` on app boot, `bootDirectoryAsApp`
takes the "**unlock gate with browse-directory-only escape hatch**"
branch:

- A full-page unlock card renders before any route handler runs:
  - Title: "Your saved data is locked"
  - Password input (autofocus, `type=password`,
    `autocomplete=current-password` so password managers can fill it)
    with a "Show password" toggle.
  - Primary button: **Unlock my data**.
  - Secondary link: **Browse directory only** → boots into a degraded
    mode (next bullet).
  - Footer link: **Forgot password? Reset everything** → routes through
    the existing destructive-action confirm dialog with its current
    copy. Same affordance the user already knows.
- "Browse directory only" mode:
  - `window.__lockedMode = "directory-only"` flag set; `lockKey` stays
    `null` in the worker.
  - `#/`, `#/about`, `#/fellow/<slug>` render normally from `fellows.db`.
  - `#/groups`, `#/groups/<id>`, `#/edit/<id>`, `#/settings` render a
    small panel: "Locked — Unlock your saved data to view." with an
    **Unlock** button that re-opens the unlock card.
  - The topbar gains a discreet **🔒 Unlock** chip on locked-mode
    routes only; clicking it re-opens the unlock card.
- Wrong-password error in the card: "Wrong password." No counter, no
  delay, no progressive lockout — the KDF cost is the rate limit.

Slow-boot watchdog already covers stuck-PWA cases (`bootMarks`); a
locked-state boot adds a `lock_gate_shown` mark.

## Topbar awareness chips

Because v1 is manual-lock-only, users must be **aware** of which state
they're in. Two narrow topbar affordances cover this without
introducing noise for non-users:

- **Disabled lock (default).** No chip. Nothing in the topbar.
- **Enabled + currently unlocked.** A small **🔓 Lock** chip in the
  topbar's right corner. Click → confirm modal "Lock now?" → `lock`
  RPC → page re-renders to the unlock card. This is the same action
  as the Settings *Lock now* button, surfaced where the user already
  is.
- **Enabled + currently locked (directory-only mode).** A small
  **🔒 Unlock** chip in the same place. Click → unlock card.

Chips are only rendered when `getLockState().enabled === true`. Users
who never enable lock never see them.

## Backup behavior

- When lock is **disabled**: today's behavior. Auto-backup at boot
  (debounced 1h), keep newest 5, all plaintext.
- When lock is **enabled and unlocked**: same rotation cadence, but
  `maybeBackupRelationshipsDb` encrypts the snapshot before writing
  `relationships.db.bak.<ISO>.locked`. The 5-newest rotation is by
  `.locked` filename suffix-stripped timestamp.
- When lock is **enabled and locked**: no auto-backup. The plaintext
  `relationships.db` doesn't exist; we have no key to make new backups
  with.
- On `enableLock`: any existing plaintext backups get encrypted in-place
  (the lock sequence above handles this).
- On `disableLock`: every `.locked` backup gets decrypted to plaintext.

## Diagnostics (`?diag=1`)

Add to the diagnostics panel:
- `Lock enabled: yes/no`
- `Currently locked: yes/no`
- `Lock format: v1 (PBKDF2-SHA256, 600000 iters)`
- Backup list shows `.locked` suffix where present.

## Documentation

Per CLAUDE.md convention ("UI/UX changes belong in `docs/users_manual.md`"):
- New § "Locking your saved data" in `docs/users_manual.md` covering
  enable / unlock / lock / change-passphrase / disable + the threat-
  model boundary.
- `docs/persistence_and_upgrades.md` storage-layer table gains rows for
  `relationships.db.locked` and `relationships.db.bak.<ISO>.locked`.
- `docs/Architecture.md` § Worker-owned OPFS notes the lock RPCs.
- `SECURITY.md` defensive-controls table gains a row for app-layer
  encryption of `relationships.db`.

## Implementation phases (one PR; phased commits)

1. **Crypto primitives + envelope.** Module-local `lockCrypto.js`-shape
   helpers inside `vendor/sqlite-worker.js` (we don't add a new vendored
   file): `deriveKey(passphrase, salt, iters)`, `encryptBlob(key, plain)`,
   `decryptBlob(key, blob)`, header pack/unpack. Unit-style tests via a
   tiny e2e Playwright test that drives the worker's RPCs.
2. **Worker RPCs.** `getLockState`, `enableLock`, `unlock`, `lock`,
   `changePassphrase`, `disableLock`. Lock-in-progress recovery on
   `init`.
3. **Backup encryption.** Extend `maybeBackupRelationshipsDb` +
   `snapshotRelationshipsDbToBackup` to honor lock state.
4. **Settings UI.** Three-state panel + four modals (enable, change,
   disable, unlock-when-already-on-settings).
5. **Locked-boot UX.** Unlock card before `bootDirectoryAsApp`'s normal
   route dispatch; browse-directory-only mode; topbar Unlock button on
   locked routes.
6. **Diagnostics + docs.** `?diag=1` rows, `users_manual.md` section,
   `persistence_and_upgrades.md` table rows, `Architecture.md` note,
   `SECURITY.md` row.
7. **E2E tests.** Enable → reload → unlock-gate → wrong-passphrase →
   right-passphrase → directory-only escape → unlock from gate →
   change-passphrase → disable. Verify on-disk `.locked` files via the
   worker RPC (we can't poke OPFS directly from the test runner, but
   `getLockState` + `listRelationshipsBackups` cover it).

## Open follow-ups (NOT in v1)

- **Auto-lock on tab close.** Filed as
  [#154](https://github.com/richbodo/fellows_local_db/issues/154).
  Needs a separate design conversation about how to message the
  silent transition to the user before it can land.
- **Argon2id migration (envelope v2).** Format header is already
  versioned; ship when vendoring a wasm Argon2 build is worthwhile.
- **Encrypted-bundle download.** Settings' "Download my user data" today
  emits plaintext bytes. When lock is enabled, the download should be
  the `.locked` envelope (already on disk) — trivial follow-up but adds
  UX questions about labeling.

## Pointers

- Worker file: `app/static/vendor/sqlite-worker.js`
- Main-thread Settings rendering: `app/static/app.js`
- Existing export/import seam: `handlers.exportRelationshipsBytes` /
  `handlers.importRelationshipsBytes`
- Backup rotation: `listRelationshipsBackups`,
  `maybeBackupRelationshipsDb`, `snapshotRelationshipsDbToBackup`
- Memory: `~/.claude/.../memory/project_lock_my_data.md`
- Predecessor work: PR #143 (SRI), PR #146 (signed bundles)
