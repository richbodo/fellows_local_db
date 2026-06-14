# Data Retention

A transparency accounting of **what the production server keeps, where, and
for how long** — and a pointer to how a user removes the app and all its data
from their own device. This is a transparency doc, **not** a legal artifact
(no GDPR posture or formal privacy policy is claimed here).

It complements the user-facing side, which lives in the user guide:
[*Where your data is stored*](./users_manual.md#where-your-data-is-stored),
[*Clearing app data*](./users_manual.md#clearing-app-data), and
[*Your device is now the directory*](./users_manual.md#your-device-is-now-the-directory).
Server-side, this doc is the accounting; the auth-flow event *schema* and
operator runbook live in [`./email_system_management.md`](./email_system_management.md),
and the privacy boundary of the client-error sink in
[`./email_gate.md` § Client error reporting](./email_gate.md#client-error-reporting).

## The bright line: no per-user storage on the server

Production (`deploy/server.py`) is a **delivery channel, not a service**: it
authenticates a magic-link request, hands over the bundle + `fellows.db`, and
steps back. There is **no per-user resource on the server** — no account, no
profile, no saved state. All user-authored private data (groups, notes, tags,
settings) lives in `relationships.db` in the browser's OPFS on the user's own
device and **never reaches the server**. There is nothing per-user on prod to
retain, breach, or hand over.

What the server *does* keep falls into three buckets: **journald events**
(operational logs), **files on disk**, and **in-memory state** (lost on
restart). Each is enumerated below.

## journald events

The app service (`fellows-pwa`) and Caddy write to **stderr**, which systemd
routes to **journald**. These structured log lines are the only durable record
of server activity. Each event is a single-line JSON object; the table lists
every event the server emits and whether it carries anything user-identifying.

| Event | Emitted by | Fields | User-identifying? |
|---|---|---|---|
| `send_unlock_email` | `deploy/server.py` (`_handle_send_unlock`) | `result`, `email_hash_prefix` (first 12 hex of the HMAC), `token_prefix` (first 12), `postmark` subset (`status`, `message_id`, `error_code`, `message`, `submitted_at`) | **No raw email.** The raw recipient is in the outbound Postmark response (`meta["to"]`) but is **deliberately not logged** — only a PII-free subset is. The recipient is recoverable *out-of-band* by joining `email_hash_prefix` against `fellows.db` (`just prod-stats --include-emails`) or via the Postmark API. |
| `verify_token` | `deploy/magic_link_auth.py` (`verify_token_event`) | `result` (enum `ok`/`expired`/`invalid`), `token_prefix` (join key back to `send_unlock_email`), `user_agent`, `build_label` | UA only. Email is **not** stored; it is recovered at query time via the `token_prefix` join. |
| `auth_status` | `deploy/server.py` | operational status fields | No. |
| `mcpb_download` | `deploy/server.py` | `name`, `size_bytes`, `user_agent` (truncated to 240 chars) | UA only. |
| `client_error` | `deploy/server.py` (`_handle_client_errors`) | `client_ip_prefix` (truncated) plus the **sanitized** client payload (kind allow-list, build, route with slugs/tokens redacted, `lastSubmitHashPrefix`, UA) | Truncated IP prefix + UA only; the sanitizer (`deploy/client_error_sanitizer.py`) strips emails, slugs, and magic-link tokens before the line is written. |
| `build_meta` | `deploy/server.py` | the build blob (label, git SHA) | No. |

**Caddy** logs only errors; access logging is **off** (no `log` directive in
`ansible/roles/caddy/templates/Caddyfile.j2`), so there is no per-request IP/URL
access log.

## On disk

| Path | Contents | Per-user? |
|---|---|---|
| `…/deploy/dist/fellows.db` | Imported **contact data** (the shared mirror) — no user-authored rows. | No. |
| `…/deploy/dist/` (rest of bundle) | Static app shell, profile images, `manifest.json` + `.sig`, `build-meta.json`. Public. | No. |
| `/etc/fellows/fellows-pwa.env` | **Secrets** — `FELLOWS_ALLOWLIST_HMAC_KEY`, `FELLOWS_SESSION_SECRET`, Postmark token. Root/`fellows`-readable only. | No. |
| sqlite WAL/journal under `dist/` | Transient SQLite sidecar files for the read path. | No. |

There is **no** `relationships.db` on the server, and (since the allowlist is
built in memory by HMAC-ing `fellows.db` at startup) **no** `allowed_emails.json`
artifact ships in `dist/`.

## In-memory state (lost on restart)

Held only in the running process; **not persisted** and gone on every service
restart or reboot. Defined on `AuthState` in `deploy/magic_link_auth.py`:

- `AuthState.tokens` — issued magic-link tokens (`token → expiry`); a token is
  redeemable for the remainder of its `TOKEN_TTL` (30 min) and cleaned up once
  it ages past that.
- `AuthState.rate_buckets` — per-`email_hash` timestamp lists backing the
  send-unlock rate limit.
- `AuthState.sessions` — the session registry (`session_id → {expires_at, …}`);
  `SESSION_MAX_AGE` is 7 days. A leaked session secret alone can't mint a
  working cookie without a matching entry here.

## Retention window (journald)

The Ansible config sets **no journald retention override** — the only
journald-related task adds the operator to the `systemd-journal`/`adm` read
groups (`ansible/roles/common/tasks/main.yml`). So the droplet runs Ubuntu's
**default** journald policy:

- **Size-bounded, not time-bounded.** `SystemMaxUse` defaults to ~10% of the
  filesystem (capped at 4 GB); `MaxRetentionSec` is unset, so there is **no
  fixed time window**. Entries persist until the size cap is reached, then the
  **oldest are vacuumed first**. On the small (1 vCPU / ~961 MB) droplet the
  practical window is whatever that size cap holds at the current event volume.
- **Persistence** follows the default `Storage=auto`: persistent across reboots
  if `/var/log/journal` exists, otherwise volatile in `/run` (lost on reboot).
- A journal reset (or, if volatile, a reboot) clears everything.

To pin the exact current figures, an operator can run (prod, out of band):

```bash
journalctl --disk-usage      # current journal size on disk
ls -la /var/log/journal      # exists → persistent; absent → volatile (/run)
```

If a bounded retention window is ever desired, set `SystemMaxUse=` /
`MaxRetentionSec=` in `/etc/systemd/journald.conf` via the `common` role.

## Third-party transport (Postmark)

Magic-link emails are sent through **Postmark**. The outbound message and the
Postmark dashboard/API retain the **raw recipient address** and message
metadata per **Postmark's own retention policy** — this is off-droplet, in a
third-party transport, and outside the server's control. It is the one place a
plaintext recipient list is reconstructable without joining against
`fellows.db`. See [`./email_system_management.md`](./email_system_management.md).

## Removing the app and its data (user side)

Server-side there is nothing per-user to delete. On the **device**, the full
removal paths (Clear App Cache vs. Reset Everything vs. browser-level site-data
deletion vs. deleting an installed PWA) are documented for users in
[*Clearing app data*](./users_manual.md#clearing-app-data) and
[*Your device is now the directory*](./users_manual.md#your-device-is-now-the-directory).

## See also

- [`./email_gate.md`](./email_gate.md) — auth-flow behavioural spec and the client-error sink's privacy boundary.
- [`./email_system_management.md`](./email_system_management.md) — magic-link operator runbook and journald event schema.
- [`./Architecture.md`](./Architecture.md) — the AC-8 (anti-enumeration + abuse-bounded analytics) attestation this accounting backs.
- [`../SECURITY.md`](../SECURITY.md) — threat model and the "no per-user server storage" bright line in context.
