# PWA Release Plan

Local-first PWA for distributing the EHF Fellows Directory to ~500 fellows. Data is static (snapshot). Offline support is critical. Desktop-first development, Android as first mobile target.

## Core UX Principle: This Is a Local App

The VPS is a **distribution server**, not a web app. Fellows never "use the website." The user journey:

1. Fellow receives email: "The EHF Fellows Directory is ready. Tap to install."
2. Magic link opens the VPS URL in their browser — they see an **install page**, not the directory
3. They tap "Install" → OS install dialog → app appears in their dock / app drawer
4. They open the installed app → data downloads once in background → done
5. From then on, they tap the app icon. It works offline. It never feels like a website.

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

1. **Vendor sqlite-wasm** — Download `sqlite3.js` + `sqlite3.wasm` from the [official SQLite WASM release](https://sqlite.org/wasm/doc/trunk/index.md). Place in `app/static/vendor/`. Load via `<script src="/vendor/sqlite3.js">` in `index.html` before `app.js`.

2. **Data provider abstraction** — In `app.js`, add a function-based data layer (no classes per CLAUDE.md):
   ```javascript
   // API provider: fetches from server.py (dev mode, current behavior)
   // OPFS provider: queries sqlite-wasm on OPFS (PWA mode)
   // All UI code calls dataProvider.getList(), dataProvider.search(q), etc.
   ```
   Detection: if running in standalone mode and `window.sqlite3` and `navigator.storage.getDirectory` exist, use OPFS provider. Otherwise fall back to API provider. Local dev with `server.py` continues to work unchanged.

3. **Build script** — `build/build_pwa.py` (Python stdlib only):
   - Copies `app/static/*` into `dist/`
   - Copies `app/static/vendor/*` into `dist/vendor/`
   - Copies `fellows.db` into `dist/`
   - Copies profile images into `dist/images/`
   - Output: self-contained `dist/` directory ready to serve

4. **SW caches DB + images** — Extend `sw.js`:
   - On install, fetch `/fellows.db` and cache it (~450KB)
   - Images: cache-on-fetch strategy (cached when first viewed, not bulk pre-downloaded)
   - Report download progress to client via `postMessage`

5. **OPFS provider implementation** — On first app launch (standalone mode):
   - Fetch `/fellows.db` from SW cache
   - Write to OPFS via `navigator.storage.getDirectory()` + `FileSystemFileHandle.createWritable()`
   - Open with sqlite-wasm
   - Implement `getList()`, `getFull()`, `getOne(slug)`, `search(q)` running SQL queries locally
   - FTS5 works in sqlite-wasm — same queries as `server.py`

6. **Progress UI** — On first launch, show download/setup progress ("Setting up your local directory...") before revealing the app.

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

**Test on:** Digital Ocean VPS, desktop Chrome, then Android Chrome

Deploy to the VPS so Chrome can mint a WebAPK (requires HTTPS) and fellows can access the install page.

### Tasks

1. **Production server** — `deploy/server.py` (Python stdlib `http.server`):
   - Serves static files from `deploy/dist/`
   - `Cache-Control` headers: long-lived for hashed assets, `no-cache` for `sw.js`
   - Health check at `GET /healthz`
   - Request logging
   - This server serves only static files — no API endpoints needed (all data access is local via sqlite-wasm in the installed PWA)

2. **Caddy config** — `deploy/Caddyfile`:
   - Automatic Let's Encrypt SSL for the domain
   - Reverse proxy to `localhost:8765`
   - HSTS headers

3. **Deployment automation** — `deploy/setup.sh` or Ansible playbook:
   - Install Caddy
   - Create systemd unit for `deploy/server.py`
   - Enable auto-start on reboot
   - Deploy `dist/` directory

4. **Build + deploy workflow**:
   ```bash
   python build/build_pwa.py          # produces dist/
   rsync dist/ user@vps:deploy/dist/  # or ansible/scp
   ```

5. **Domain setup** — Point domain (or subdomain) to the VPS IP. Caddy handles SSL automatically.

### Architecture

```
Fellow's browser                    VPS (Digital Ocean)
─────────────────                   ───────────────────
Visit URL              ──HTTPS──>   Caddy (Let's Encrypt)
                                      │
See install page       <────────    deploy/server.py
Tap "Install"                         serves dist/
                                        ├── index.html
PWA installed locally                   ├── app.js, styles.css, sw.js
App downloads DB       <────────        ├── fellows.db
App caches images      <────────        ├── images/
                                        └── vendor/sqlite3.*
Offline from here.
VPS no longer needed
for this user.
```

### Milestone Test

- Visit `https://your-domain/` in desktop Chrome → see install page, not directory
- Install PWA → open standalone → directory works
- Visit `https://your-domain/` on Android Chrome → install prompt appears → install → standalone app works
- Go offline → browse fellows, search, cached images all work
- Lighthouse PWA audit: full score

---

## Phase 4: Auth (Magic Link)

**Test on:** VPS

Gate access so only authorized fellows can reach the install page. Unauthorized visitors see a branded "this is a private app" page.

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
- **Port 8765**: Unchanged for local dev and production
- **No new pip deps for app**: Build-time deps go in `requirements-dev.txt`
- **`deploy/server.py`** is a separate file for production; `app/server.py` stays clean

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
deploy/
  server.py                        # Production static file server + auth endpoints
  Caddyfile                        # Caddy reverse proxy config
  setup.sh                         # VPS bootstrap script
  dist/                            # Built output (gitignored)
    fellows.db                     # DB (plaintext until F1)
    allowed_emails.json            # SHA-256 hashed email allowlist
    (+ all static files, icons, vendor, images)
```
