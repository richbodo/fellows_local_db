# Email System Management

The production email system is a magic-link gate on `deploy/server.py`: users submit an email to `POST /api/send-unlock`, the server checks a SHA-256 hash against `deploy/dist/allowed_emails.json`, issues a short-lived token (15 minutes), and sends a Postmark email with a `/#/unlock/<token>` link. When that token is posted to `POST /api/verify-token`, the server sets a signed session cookie and the browser can access protected directory assets (`/fellows.db`, `/images/*`, directory `/api/*`). The system is stateless at deploy-time except for in-memory tokens/rate buckets, so restarts invalidate outstanding tokens by design.

## Production Setup

Environment variables used in this section: `FELLOWS_SESSION_SECRET` (long random signing key; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`), `FELLOWS_POSTMARK_TOKEN` (Postmark Server API token from your Postmark server settings), `FELLOWS_MAIL_FROM` (verified sender signature/domain in Postmark), and `FELLOWS_PUBLIC_ORIGIN` (public HTTPS origin for your deployed app, for example `https://fellows.globaldonut.com`).

1. **[Machine: local dev machine] Build fresh bundle with allowlist**
   ```bash
   cd /path/to/fellows_local_db
   python build/build_pwa.py
   ```
   Confirm `deploy/dist/allowed_emails.json` exists.

2. **[Machine: local dev machine] Install/update Ansible collection (once per machine)**
   ```bash
   ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
   ```

3. **[Machine: local dev machine] Deploy application files**
   ```bash
   ansible-playbook ansible/site.yml --tags deploy --ask-become-pass
   ```

4. **[Machine: local dev machine] Run interactive auth-env setup script (replaces old steps 4-6)**
   ```bash
   ./scripts/configure_email_auth_env.sh
   ```
   This script prompts for the required env vars, then SSHes to the app server to:
   - write `/etc/fellows/fellows-pwa.env` with correct ownership/mode,
   - install `/etc/systemd/system/fellows-pwa.service.d/10-env-file.conf` with `EnvironmentFile=/etc/fellows/fellows-pwa.env`,
   - run `systemctl daemon-reload`, restart `fellows-pwa`, and print service status.
   Use an SSH login with full sudo privileges (typically your operator account, e.g. `rsb`), not the limited `deploy` account unless you have explicitly granted it broader sudo rights.
   Keep your SSH key and sudo access for the app server available on the machine where you run the script.

5. **[Machine: local dev machine, or any client machine] Smoke test auth APIs**
   - `GET /api/auth/status` can be opened directly in a browser:
     - `https://fellows.globaldonut.com/api/auth/status`
   - Or via curl:
     ```bash
     curl -sS https://fellows.globaldonut.com/api/auth/status
     ```
   - `POST /api/send-unlock` requires curl (or another HTTP client), not direct browser navigation:
     ```bash
     curl -sS -X POST https://fellows.globaldonut.com/api/send-unlock \
       -H 'content-type: application/json' \
       -d '{"email":"you@example.com"}'
     ```
   - `POST /api/verify-token` also requires curl (or another HTTP client):
     ```bash
     curl -sS -X POST https://fellows.globaldonut.com/api/verify-token \
       -H 'content-type: application/json' \
       -d '{"token":"REPLACE_WITH_TOKEN_FROM_MAGIC_LINK"}'
     ```
   - Example expected send response:
     - `{"sent": true}` regardless of membership (anti-enumeration).

6. **[Machine: local dev machine] Optional one-command deploy path**
   ```bash
   ./scripts/deploy_pwa.sh --ask-become-pass
   ```
   Then repeat steps 4-5 if env changes were made.

## Email Debugging In Production (Postmark + Server Logs)

**Deploy / PWA drift:** After deploy, use the in-app **Diagnostics** panel (`?diag=1` or the Diagnostics button) to compare `/api/auth/status`, `/api/debug/diagnostics`, and `/build-meta.json` with response headers `X-Fellows-Build`. On the app server, `journalctl -u fellows-pwa -f` shows `event=auth_status` JSON for each auth status request and `event=build_meta` at process start.

Postmark debugging reference: [Postmark support and debugging docs](https://postmarkapp.com/support).

What you can debug reliably:

- **Server-side flow acceptance:** `journalctl -u fellows-pwa -f` now emits structured JSON for each send attempt (`event=send_unlock_email`) with result type, hashed email prefix, token prefix, and Postmark metadata.
- **Postmark API acceptance:** successful logs include Postmark response fields (`MessageID`, `ErrorCode`, `Message`, `To`, `SubmittedAt`) so you can confirm whether Postmark accepted the message.
- **API-level failures:** HTTP errors include status code and body from Postmark (`http_error` result), which is typically enough to diagnose invalid token, sender/domain issues, or malformed payloads.
- **Transport/connection failures:** URL/network/runtime failures are logged as `error` result with exception text.

What Postmark feedback does **not** fully guarantee:

- **Inbox placement:** acceptance does not guarantee inbox vs spam placement.
- **Recipient mailbox outcomes:** bounces/complaints/opens are not returned synchronously by `/email`; those require Postmark message streams/webhooks or dashboard querying using `MessageID`.
- **End-user click behavior:** link click/visit confirmation must be inferred from `verify-token` success and app logs, not from send API alone.

Recommended debug workflow:

1. **[Machine: local dev machine, or any client machine]** Trigger `POST /api/send-unlock` for a known allowlisted email:
   ```bash
   curl -sS -X POST https://fellows.globaldonut.com/api/send-unlock \
     -H 'content-type: application/json' \
     -d '{"email":"you@example.com"}'
   ```
2. **[Machine: app server]** Check logs for send diagnostics:
   ```bash
   journalctl -u fellows-pwa -n 50 --no-pager
   ```
3. If `result=sent`, use `MessageID` in Postmark dashboard/API to inspect final delivery events.
4. If `result=http_error`, fix credentials/domain/sender policy indicated by status/body.
5. If no log entry appears, verify auth is enabled (`/api/auth/status`) and that requests reach this host (Caddy/systemd logs).
