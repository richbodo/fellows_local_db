# PWA Release Plan

Local-first PWA for distributing the EHF Fellows Directory to ~500 fellows. Data is static (snapshot). Offline support is critical. Desktop-first development, Android as first mobile target.

## Core UX Principle: This Is a Local App

The VPS is a **distribution server**, not a web app. Fellows never "use the website." The user journey:

1. Fellow receives email: "The EHF Fellows Directory is ready. Tap to install."
2. Magic link opens the VPS URL in their browser — they see an **install page**, not the directory
3. They tap "Install" → OS install dialog → app appears in their dock / app drawer
4. They open the installed app → data downloads once in background → done
5. From then on, they tap the app icon. It works offline. It never feels like a website.

**Production hostname for this rollout:** `https://fellows.globaldonut.com/` (subdomain on `globaldonut.com`). The VPS is a **distribution endpoint** only. For this rollout, DNS points `fellows.globaldonut.com` to the **DigitalOcean Reserved IP** and stays **Cloudflare DNS-only** while we develop and stabilize.

## Deployment Decisions (locked)

- **DNS target:** `A fellows -> 170.64.243.67` (Reserved IP)
- **Cloudflare mode:** `DNS only` until post-launch hardening
- **Linux access model:** Ansible bootstraps while SSH’d as **`rsb`** (your sudo-capable user); playbook creates dedicated **`deploy`** with **key-only** login for ongoing deploys. **sshd** is reached on port **52221** (`ansible_port` + UFW).
- **Magic-link sender:** `noreply@fellows.globaldonut.com`
- **Mail provider:** Postmark (server API token stored via vault/secret file, never in git)
- **Environment topology:** start simple with **one droplet now** (can host `fellows` and a basic apex static index if desired), and split apps into separate droplets later only if isolation/scale needs it

### Public site journey (`https://fellows.globaldonut.com/`)

End-to-end flow we are building toward (browser vs installed PWA is still Phase 1; email gate is Phase 4):

1. User opens **`https://fellows.globaldonut.com/`** in a normal browser tab.
2. They enter their **fellowship email** and submit (e.g. “Download app” / “Get access”).
3. UI shows **“check your email”** and instructions to use the **magic link** (no directory data yet).
4. They click the link in email → returns to the same origin (e.g. `/#/unlock/TOKEN`) → session established → they see the **install / PWA** page with an explicit install action.
5. They install the PWA; **standalone** opens the **full directory**; data is fetched/cached for **offline** use (Phase 2 sqlite-wasm + SW).
6. Later launches use the **installed app icon**; works **offline** without revisiting the site.

**Plan mapping:** Phase **1** defines install vs standalone UI and installability. Phase **3** is **HTTPS + static hosting + health** (no magic-link API until Phase **4**). Phase **4** adds **`/api/send-unlock`**, **`/api/verify-token`**, cookie gating, and SW rules so data only caches after auth.

**Deployments:** Nothing auto-runs. **You** (or CI) run **`ansible-playbook … --tags deploy`** after building `deploy/dist`. There is no cron in the current Ansible roles.

### Two modes, one URL

The PWA detects whether it's running installed (standalone) or in a browser tab:

```javascript
window.matchMedia('(display-mode: standalone)').matches
```

- **Browser view (not installed):** Install/download landing page only. No directory data. Branding, install button, and "Having trouble? Contact the EHF Communications Working Group."
- **Standalone view (installed):** Full app. No URL bar, no browser chrome. Data lives locally.

This means someone walking up to a computer and visiting the URL sees only the install page. The directory data is only accessible inside the installed PWA.

---

## Phase 1: Fix PWA Foundation

**Test on:** `localhost:8765` in desktop Chrome

The existing service worker and manifest have issues that prevent Chrome from recognizing the app as installable. This phase fixes them and adds the install-page / app-mode split.

### Tasks

1. **Fix SW cache naming bug** — `CACHE_VERSION` should be `'v1'`, not `'fellows-app-shell-v1'`, so `APP_SHELL_CACHE` resolves to `fellows-app-shell-v1` instead of the current redundant `fellows-app-shell-fellows-app-shell-v1`.

2. **Generate app icons** — Create `app/static/icons/icon-192.png`, `icon-512.png`, and `icon-maskable-512.png`. Can derive from the EHF logo or a simple text-based icon. Maskable icon needs safe zone padding per Android adaptive icon spec.

3. **Update manifest** — Add to `manifest.webmanifest`:
   - `"scope": "/"`
   - `"id": "/"`
   - `"description"` and `"categories"`
   - Maskable icon entry: `{ "src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }`

4. **Add HTML meta tags** to `index.html`:
   - `<meta name="theme-color" content="#4a2c6a">`
   - `<meta name="apple-mobile-web-app-capable" content="yes">`
   - `<link rel="apple-touch-icon" href="/icons/icon-192.png">`

5. **Install page vs app mode** — In `app.js`, detect `display-mode: standalone`:
   - **Standalone:** Show the full directory app (current behavior)
   - **Browser:** Show an install landing page with app branding, an "Install" button, and the support message. Hide search, directory, detail pane entirely.

6. **Install prompt UX** — Capture the `beforeinstallprompt` event. Wire it to the install page's "Install" button. After successful install, the landing page updates to "App installed — open it from your dock/app drawer."

7. **SW update notification** — When a new SW version activates, post a message to the client. `app.js` listens and shows "New version available — reload?" prompt.

8. **Support message** — On the install page and within the app's about/settings area:
   > Having trouble with the app? Contact the EHF Communications Working Group.

### Milestone Test

- Chrome DevTools → Application → Manifest shows no errors, "installable" status
- Lighthouse PWA audit passes (except HTTPS, expected on localhost)
- Visiting the URL in a browser tab shows the install page, not the directory
- Installing the PWA and opening it in standalone mode shows the full directory
- Install banner appears on the landing page; clicking it triggers Chrome's install dialog

---

## Phase 2: Local DB via sqlite-wasm

**Test on:** `localhost:8765` in desktop Chrome

The installed app queries a local SQLite DB in the browser via OPFS instead of hitting the server API. This is the core functional leap for offline support.

### Tasks

1. **Vendor sqlite-wasm** — Download `sqlite3.js` + `sqlite3.wasm` from the [official SQLite WASM release](https://sqlite.org/wasm/doc/trunk/index.md). Place in `app/static/vendor/`. Load via `<script src="/vendor/sqlite3.js">` in `index.html` before `app.js`. *(Done: official 3.50.4 jswasm bundle.)*

2. **Data provider abstraction** — In `app.js`, add a function-based data layer (no classes per CLAUDE.md):
   ```javascript
   // API provider: fetches from server.py (dev mode, current behavior)
   // OPFS provider: queries sqlite-wasm on OPFS (PWA mode)
   // All UI code calls dataProvider.getList(), dataProvider.search(q), etc.
   ```
   Detection: standalone + `sqlite3InitModule` + OPFS (`navigator.storage.getDirectory`) + secure context → `installOpfsSAHPoolVfs` + `OpfsSAHPoolDb`; otherwise API provider. Failures fall back to API + IndexedDB as before.

3. **Build script** — `build/build_pwa.py` (Python stdlib only):
   - Copies `app/static/` recursively into `deploy/dist/` (vendor included).
   - Also copies `app/fellows.db` and profile images into `deploy/dist/` and `deploy/dist/images/`.
   - Output: self-contained `dist/` directory ready to serve

4. **SW caches DB + images** — `sw.js`:
   - On install, precaches app shell including `/vendor/sqlite3.js`, `/vendor/sqlite3.wasm`, and `/fellows.db`
   - Same-origin assets and `/images/*`: cache-on-fetch
   - `postMessage` to clients during install (`sw-cache-progress`)

5. **OPFS provider implementation** — On first standalone launch:
   - Fetch `/fellows.db` (with progress text on main thread)
   - `poolUtil.importDb('fellows.db', bytes)` then `new poolUtil.OpfsSAHPoolDb('fellows.db')`
   - `getList`, `getFull`, `getOne`, `search` (FTS5), `getStats` mirror `server.py` SQL

6. **Progress UI** — Loading text: "Setting up your local directory…", download %, "Preparing offline database…"

**Dev server:** `GET /fellows.db` serves `app/fellows.db` as `application/octet-stream`.

### Data Payload

- Fellow JSON/DB: ~450KB
- Profile images: ~34MB (268 files, lazy-cached on view)
- sqlite-wasm: ~1MB
- Total first-load: ~1.5MB (app shell + DB), images loaded on demand

### Milestone Test

- Install PWA, open in standalone mode — fellows load from local DB
- DevTools → Application → OPFS shows `fellows.db`
- DevTools → Network → Offline: search works, fellow detail works, previously viewed images load
- Browser tab (not installed) still shows only the install page
- `app/server.py` still works for local dev with no changes

---

## Phase 3: VPS Deployment + HTTPS

**Test on:** DigitalOcean droplet (e.g. Ubuntu 24.04 LTS), desktop Chrome, then Android Chrome.

Deploy so Chrome can mint a WebAPK (requires **HTTPS** and a stable **origin**). **Canonical URL:** `https://fellows.globaldonut.com/`.

### Infrastructure assumptions (this project)

| Item | Notes |
|------|--------|
| **Host** | DigitalOcean Droplet (example: 1 vCPU / 1 GB / 25 GB, SYD1). |
| **Public IPv4** | Droplet-attached address (e.g. `170.64.138.50`). |
| **Reserved IP** | **Chosen:** `170.64.243.67` attached and used for `fellows` DNS target. |
| **DNS** | Cloudflare zone `globaldonut.com`. Add an **`A` record** for hostname **`fellows`** → target IPv4 (reserved or droplet public). Apex may already point at the same host; the **subdomain record is still required** so Caddy can serve TLS for `fellows.globaldonut.com`. |
| **Cloudflare proxy** | **Chosen:** keep `fellows` **DNS only** (grey cloud) through development and initial release. Revisit **Proxied** later if you want WAF/CDN; then use **Full (strict)** and ensure origin cert is valid. |
| **Automation** | **Ansible** from a control node (your laptop or CI). No requirement to run Ansible *on* the droplet. |
| **Agents (Cursor / humans)** | Same interface: SSH for ad hoc checks + `ansible-playbook` for repeatable deploy. Document inventory, vault, and smoke commands so any agent with credentials can verify milestones. |

### Tasks

1. **Production server** — `deploy/server.py` (Python stdlib `http.server`):
   - Serves static files from `deploy/dist/` (or configurable `DEPLOY_ROOT`)
   - `Cache-Control` headers: long-lived for hashed assets, `no-cache` for `sw.js` (and manifest if needed)
   - Health check at `GET /healthz`
   - Request logging to stdout (journald under systemd)
   - **Phases 1–3:** static + health only. **Phase 4** adds `/api/*` here (magic link); keep one process binding **127.0.0.1:8765** behind Caddy.

2. **Caddy config** — `deploy/Caddyfile` (template in repo; render with Ansible or sed):
   - Site block for **`fellows.globaldonut.com`** only (other subdomains on the same VM get their own `import` or separate files later).
   - **Reverse proxy** to `127.0.0.1:8765` (not `localhost` if you ever need to avoid IPv6 ambiguity — pick one and document it).
   - Automatic Let’s Encrypt (`tls` via Caddy’s ACME); set **admin email** for registration.
   - Optional: **HSTS** once you are confident you will not need plain HTTP except ACME.

3. **OS baseline (Ansible)** — Suggested layout under `ansible/`:
   - `inventory/` — e.g. `hosts.ini` with `[fellows]`, `ansible_host=<ip>`, and **`ansible_port`** / **`ansible_user`** if sshd is not on 22 (this rollout: port **52221**, bootstrap user **`rsb`**, then **`deploy`**).
   - `group_vars/fellows.yml` — `fellows_domain`, `caddy_admin_email`, `deploy_user`, `app_root` (e.g. `/opt/fellows`).
   - `roles/common` — `apt update`, install `python3`, `ufw`, enable **`OpenSSH`**, **`80/tcp`**, **`443/tcp`**, default deny inbound.
   - `roles/caddy` — Install Caddy (official apt repo or documented method), deploy templated `Caddyfile`, `systemctl enable --now caddy`.
   - `roles/fellows_app` — Create `deploy_user`, `app_root`, sync `deploy/dist/` via `ansible.builtin.copy`/`synchronize`, systemd unit **`fellows-pwa.service`**:
     - `WorkingDirectory=<app_root>/deploy`
     - `ExecStart=/usr/bin/python3 <app_root>/deploy/server.py` (or explicit venv if you add one later — stdlib-only app can use system Python)
     - `Restart=on-failure`
   - `site.yml` — ordering: common → caddy → fellows_app.
   - **Tags:** e.g. `bootstrap` (packages, firewall, users) vs `deploy` (artifacts only) so agents can run quick content updates without replaying the whole OS role.

4. **Secrets (Phase 4 prep)** — Store SMTP/API keys for magic links in **`ansible-vault`**-encrypted vars or a root-only file on the server — **not** in git plaintext. For this project, use Postmark server token + sender `noreply@fellows.globaldonut.com`. Document decrypt/run pattern for operators.

5. **Build + deploy workflow** (from dev machine):
   ```bash
   python build/build_pwa.py          # produces dist/ (see Phase 2)
   ansible-playbook -i ansible/inventory/hosts.ini ansible/site.yml --tags deploy
   ```
   Alternative: `rsync`/`scp` `dist/` to `deploy_user@app_root/deploy/dist/` then `systemctl restart fellows-pwa` (Ansible can wrap both).

6. **Domain setup** — Cloudflare **`A` `fellows` → IPv4** as above. Wait for propagation; Caddy obtains cert on first successful request to `:443` from the public Internet.

### Tooling for agents and milestone verification

These items are **documentation + small scripts** so humans and Cursor agents can validate deploys the same way:

| Tool | Purpose |
|------|--------|
| **SSH config** | Add a documented host alias (e.g. `Host fellows-globaldonut`, `HostName <ip>`, `User <deploy_user>`, `IdentityFile …`) in operator docs or a committed **example** `deploy/ssh_config.example` (no real keys). |
| **Smoke check** | `scripts/smoke_prod.sh` (or `curl` one-liner): `curl -fsS https://fellows.globaldonut.com/healthz` → expect `200` and body OK. Run after every deploy. |
| **TLS / DNS** | Optional: `scripts/check_deploy_env.sh` — `dig +short fellows.globaldonut.com A`, `curl -fsSI https://fellows.globaldonut.com/` (fail if cert name mismatch). |
| **E2E against staging URL** | Extend Playwright `base_url` via env (e.g. `E2E_BASE_URL=https://fellows.globaldonut.com`) for **read-only** smoke tests when you intentionally hit production; keep default `localhost:8765` for CI. |
| **Ansible check mode** | `ansible-playbook … --check` for dry-run when tuning tasks. |

**What “agent access” means in practice:** agents do not get a separate DigitalOcean API by default. They use **the same SSH key and inventory** you place in the workspace (or vault password in env). Restrict keys to **`deploy_user`** with **sudo only if needed** for Caddy reload; prefer **`systemctl` via passwordless sudo** for a single unit file.

### Architecture

```
Fellow's browser                    VPS (Digital Ocean)
─────────────────                   ───────────────────
Visit URL              ──HTTPS──>   Caddy (Let's Encrypt)
                                      │
See install page       <────────    127.0.0.1:8765  deploy/server.py
Tap "Install"                         serves deploy/dist/
                                        ├── index.html
PWA installed locally                   ├── app.js, styles.css, sw.js
App downloads DB       <────────        ├── fellows.db
App caches images      <────────        ├── images/
                                        └── vendor/sqlite3.*
Offline from here.
VPS no longer needed
for this user.
```

### Milestone test

**Infra / automated**

- `dig fellows.globaldonut.com A` (or `nslookup`) returns the expected IPv4 (reserved or droplet).
- `curl -fsS https://fellows.globaldonut.com/healthz` succeeds; journal shows `fellows-pwa` and `caddy` healthy.
- UFW: only 22/80/443 (and any intentional services) open; app not bound to `0.0.0.0:8765` from outside (only **Caddy** on 443).

**PWA / product**

- Visit `https://fellows.globaldonut.com/` in desktop Chrome → install page, not directory (per Phase 1 behavior).
- Install PWA → open standalone → directory works (Phase 2 sqlite-wasm when implemented).
- Android Chrome: install prompt → standalone works.
- Airplane mode / DevTools offline: browse, search, cached images behave as designed.
- Lighthouse PWA audit on **this origin** (HTTPS): aim for full installability score; investigate any mixed-content or redirect issues introduced by subdomain.

---

## Phase 4: Auth (Magic Link)

**Test on:** `https://fellows.globaldonut.com/` (same VPS as Phase 3)

Gate access so only authorized fellows can reach the install page. Unauthorized visitors see a branded "this is a private app" page.

**Deployment note:** Magic-link email deliverability may require **SPF**, **DKIM**, and (for DMARC alignment) a coherent **From** domain on `globaldonut.com`. For this rollout: sender is `noreply@fellows.globaldonut.com` via Postmark. Plan DNS/email changes with whoever administers the zone; Ansible should template secrets via **vault**, not plaintext in `group_vars`.

### Tasks

1. **Three-tier page states** — The URL now has three possible views:
   - **Unauthenticated browser:** "EHF Fellows Directory — this is a private app for EHF Fellows." No install button. Just the email input and support message.
   - **Authenticated browser:** Install page with "Install" button (current Phase 1 landing page).
   - **Standalone (installed):** Full app (unchanged).

2. **Email input on landing page** — Simple form: "Enter your fellowship email to get started." On submit, POST to `/api/send-unlock`.

3. **Email allowlist** — `build/build_pwa.py` extracts `contact_email` values from `fellows.db`, SHA-256 hashes them (lowercased), writes to `deploy/dist/allowed_emails.json`.

4. **Send-unlock endpoint** — Add to `deploy/server.py`, `POST /api/send-unlock`:
   - Accept `{ "email": "..." }` JSON body
   - Check SHA-256(lowercase(email)) against allowlist
   - If match: generate random 32-byte hex token, store with 15-min expiry
   - Send email via SMTP (configurable: Mailgun, SES, or direct)
   - Always return `200 { "sent": true }` regardless of match (prevents email enumeration)
   - Rate limit: max 3 per address per hour

5. **Verify-token endpoint** — `POST /api/verify-token`:
   - Validate token, set session cookie if valid, delete token (single-use)
   - Session cookie: HttpOnly, Secure, SameSite=Strict

6. **Magic link hash route** — `app.js` handles `#/unlock/TOKEN`:
   - POSTs token to `/api/verify-token`
   - On success: sets authenticated state, shows install page
   - On failure: shows "Link expired or invalid — request a new one"

7. **SW gates data on auth** — Service worker only caches `fellows.db` and images after the session cookie is present. Unauthenticated requests for data files return the install page.

8. **Support message** — On the unauthenticated page, the install page, and in the app's about section:
   > Having trouble with the app? Contact the EHF Communications Working Group.

### Token Flow

```
Fellow                    Browser                   VPS
─────                     ───────                   ───
                          Visit URL
                          See "Enter your email"
Enter email ──────────>   POST /api/send-unlock ──> Check allowlist
                                                    Generate token
                          "Check your email"  <──── Send magic link
Open email
Tap link ─────────────>   GET /#/unlock/TOKEN
                          POST /api/verify-token ─> Validate, set cookie
                          See install page    <──── 200 OK
Tap "Install"
                          PWA installs
Open app (standalone)     Downloads DB + images
                          Fully offline from here
```

### Milestone Test

- Unauthenticated visit: see "private app" page, no install button, no data
- Enter valid fellow email → receive magic link email within 30 seconds
- Tap magic link → see install page with "Install" button
- Enter invalid email → same "check your email" message (no enumeration)
- Token expires after 15 minutes, cannot be reused
- After install, app works offline — no further server contact needed

---

## Future Development

The following are not part of the initial release but are natural next steps.

### F1: Encryption at Rest

Encrypt the fellows DB on the VPS filesystem and in the browser's OPFS. Protects against VPS compromise and local device inspection.

**Server-side:**
- `build/encrypt_db.py` — Encrypt `fellows.db` with AES-256-GCM, key derived from passphrase via PBKDF2 (100K iterations, random salt). Output: `fellows.db.enc` with salt prepended.
- `build/build_pwa.py` ships `fellows.db.enc` instead of plaintext `fellows.db` in `dist/`.
- The encryption passphrase is a build-time secret, never stored on the VPS.

**Client-side:**
- After magic link auth, `/api/verify-token` returns the decryption passphrase (one-time, over HTTPS).
- `app.js` uses Web Crypto API: `crypto.subtle.importKey()` → `crypto.subtle.deriveKey()` (PBKDF2) → `crypto.subtle.decrypt()` (AES-GCM).
- Decrypted DB written to OPFS (origin-private, not accessible to other origins).
- Optional WebAuthn integration: user saves a hardware-bound credential; on subsequent visits, biometric auth derives the key without network contact.

**Considerations:**
- OPFS data is origin-private but not encrypted by default — a rooted device or browser exploit could read it. True at-rest encryption on the client would require re-encrypting before writing to OPFS or keeping the decrypted DB only in memory (performance trade-off to evaluate).
- Images (~34MB): could encrypt individually, bundle as BLOBs in the encrypted DB (increases size), or accept that images are lower-sensitivity than structured profile data.

### F2: AI-Powered Natural Language Search

Replace keyword search with natural language queries using Chrome's Prompt API (Gemini Nano, on-device).

**Approach:**
- Register for Chrome Built-in AI Origin Trial for the VPS domain
- Use `ai.languageModel.create()` / `session.prompt()` (replaces obsolete `window.ai` code)
- Local RAG pipeline: NL question → Prompt API generates FTS5 keywords → sqlite-wasm queries OPFS DB → top results fed back to Prompt API for conversational answer
- Graceful degradation: falls back to keyword search if Prompt API unavailable

**Considerations:**
- Prompt API availability is limited (Chrome 127+ on Android/desktop with Gemini Nano downloaded, ~1.7GB model)
- Quality of FTS5 keyword generation from NL queries needs testing
- Fits well with the local-app model — all AI processing happens on-device

### F3: iOS Support

PWAs on iOS (Safari) have limitations requiring specific handling.

**Known issues:**
- No `beforeinstallprompt` event — must instruct users to use "Add to Home Screen" manually
- OPFS support is partial in older iOS versions; may need IndexedDB fallback
- SW caches may be evicted after 7-14 days of non-use on iOS
- No WebAuthn in standalone mode on older iOS versions

**Approach:**
- Test OPFS + sqlite-wasm on Safari 17+ (iOS 17+)
- If OPFS unreliable, fall back to IndexedDB for DB storage
- Add "Add to Home Screen" instruction overlay for iOS (detect via `navigator.standalone`)
- Accept periodic re-download for iOS users due to cache eviction

---

## Constraints Preserved

- **No frameworks**: Python stdlib server, vanilla JS frontend
- **No npm/bundlers**: sqlite-wasm loaded via `<script>` tag from vendored files
- **Single IIFE**: `app.js` stays as one IIFE, no modules/classes
- **`app/server.py` unchanged**: Local dev workflow continues to work identically
- **Port 8765**: Unchanged for local dev and **behind Caddy** on the VPS (bind loopback in production)
- **No new pip deps for app**: Build-time deps go in `requirements-dev.txt`
- **`deploy/server.py`** is a separate file for production; `app/server.py` stays clean

## Plan review: gaps and how this document addresses them

| Gap | Risk | Mitigation in plan |
|-----|------|---------------------|
| **Subdomain vs apex** | Manifest `scope` / `start_url` must match the served origin. | Use **`https://fellows.globaldonut.com/`** consistently; PWA `scope: "/"` is correct for that host. |
| **Cloudflare proxy vs DNS-only** | Orange cloud can break ACME or cache SW unexpectedly. | Start with **DNS only** for `fellows`; document move to proxied + Full (strict) as a later hardening step. |
| **Ephemeral droplet IP** | DNS drift after rebuild. | Prefer **Reserved IP** in DO + DNS to that address. |
| **Phase 3 vs Phase 4 server** | One file (`deploy/server.py`) grows API routes. | Single systemd unit; Phase 4 extends same server; Caddy unchanged. |
| **SW caching auth-gated assets (Phase 4)** | Complex race between cookie and SW fetch. | Plan already specifies SW gates DB/images until session — implement with clear integration tests (manual checklist + optional e2e with auth). |
| **Agent “access”** | No magic Cursor-only channel. | **SSH + Ansible + smoke scripts** documented; operators commit **examples** only, never real keys. |
| **Email deliverability (Phase 4)** | Magic links spam-foldered or rejected. | SPF/DKIM/DMARC called out; secrets via **ansible-vault**. |

**Testing rhythm:** Local Phases 1–2 on `localhost:8765` → Phase 3 smoke (`/healthz`, TLS, DNS) → optional Playwright with `E2E_BASE_URL` → Phase 4 end-to-end on real mail.

## Project Layout (after all phases)

```
app/
  server.py                        # Local dev server (unchanged)
  static/
    index.html                     # Install page + app markup
    app.js                         # Single IIFE: mode detection, data provider, UI
    styles.css                     # Styles for install page + app
    sw.js                          # Service worker: caching, DB download, progress
    manifest.webmanifest           # PWA manifest with icons
    icons/                         # icon-192.png, icon-512.png, icon-maskable-512.png
    vendor/
      sqlite3.js                   # Vendored sqlite-wasm
      sqlite3.wasm
build/
  import_json_to_sqlite.py         # Existing: JSON → SQLite
  filter_demo_data.py              # Existing: demo data filter
  build_pwa.py                     # New: assemble deploy/dist/
ansible/
  inventory/hosts.ini              # Example inventory (no secrets)
  group_vars/                      # fellows_domain, deploy_user; vault for secrets
  roles/common, caddy, fellows_app/
  site.yml
deploy/
  server.py                        # Production static file server + auth endpoints
  Caddyfile                        # Caddy site for fellows.globaldonut.com
  ssh_config.example               # Optional: template for operator SSH config
  setup.sh                         # Optional: bootstrap if not using Ansible for first boot
  dist/                            # Built output (gitignored)
    fellows.db                     # DB (plaintext until F1)
    allowed_emails.json            # SHA-256 hashed email allowlist
    (+ all static files, icons, vendor, images)
scripts/
  smoke_prod.sh                    # curl healthz + optional TLS/DNS checks (add in Phase 3)
```
