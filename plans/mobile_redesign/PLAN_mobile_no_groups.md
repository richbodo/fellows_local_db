# Phase 3 (mobile) — No-Private-Data Mobile Reduction

**Status:** planned, not started. **Decided:** 2026-06-01.
**Companion mockups:** [`mockups_no_groups/index.html`](mockups_no_groups/index.html) + `styles.css`.
**Supersedes** the group-centric parts of [`DESIGN.md`](DESIGN.md) / [`css_porting_notes.md`](css_porting_notes.md) for phones.

---

## 1. What this is, in one paragraph

The mobile redesign described in `css_porting_notes.md` **already shipped** —
`app/static/index.html` has the `#appbar`, the `#tabs` strip, the `#kebab-sheet`,
the `#composer-fab`, the bottom-sheet `#group-rail`, and the `#filter-sheet`, all
wired in `app.js`. The maintainer's screenshot *is* that shipped state, and it's
still unusable on a phone because (a) it's saturated with group chrome that wastes
the screen, and (b) the list scrolls with no visible affordance. The
2026-06-01 decision — **no private data on mobile** — lets us *delete* the
group surface on phones rather than redesign it, freeing the space and fixing the
scroll. This plan strips groups/selection/composer/notes from the phone experience,
swaps the tab strip for a conventional hamburger drawer, rebuilds the directory as a
proper scroll container, adds Email/Call call-to-actions to the fellow profile, and
reduces mobile Settings to app-info + tools.

The end state on a phone: **search the directory → open a fellow → email or call
them.** Nothing else.

---

## 2. Decisions baked in (veto any of these before we start)

1. **Feature-gate on `isMobileDevice()`, not viewport width.** Removing groups is a
   *device* decision, gated by `isMobileDevice()` (`app.js:1226`, UA-based) — the
   same lever the shipped folder policy uses (`folderStorageOffered()`,
   `app.js:8659`). A desktop user with a narrow window keeps groups; only real
   phones lose them. **Layout** adaptation stays width-driven (the existing
   `≤1024px` media queries). Concretely: set `document.body.classList.toggle('is-phone', isMobileDevice())`
   once at boot, then gate all new behavior on `body.is-phone`. All phones are also
   `≤1024px`, so the is-phone rules *specialize* the existing mobile shell — they
   never fight it.

2. **No backup/restore on mobile Settings.** With groups, tags, and notes gone,
   `relationships.db` on a phone holds only trivial prefs (has-email toggle). There
   is nothing user-authored to lose, so the manual-backup/download/restore UI is
   removed from mobile. **This supersedes** the "keep manual backup as the only
   durability path on mobile" stance in the `mobile_folder_storage_policy` memory
   (which assumed groups still existed on phones). Non-destructive: any groups a
   user already created on a phone still live in their `relationships.db` and remain
   visible on desktop; we only hide the phone UI.

3. **Tools live in Settings; the kebab is retired on phones; the hamburger is the
   one menu.** The appbar's single right-side button becomes a hamburger that opens
   a **nav drawer** (Directory / Settings / About + build tag). Diagnostics / Report
   a bug / Clear app cache move into a "Tools" section on the Settings page (reusing
   the existing handlers). The `#kebab-sheet` is hidden on phones. Recovery is still
   reachable: the boot-stuck/boot-error panels keep their own Clear-Cache buttons,
   and `?diag=1` / `?gate=1` escapes are unchanged.

4. **Deep links to group routes redirect on phones.** `#/groups`, `#/groups/<id>`,
   `#/groups/<id>/directory`, and `#/edit/<id>` redirect to `#/` when
   `isMobileDevice()`. No dead screens.

5. **The worker and two-DB architecture are untouched.** This is a UI-gating change.
   `relationships.db`, the worker, the data-provider tiers, auth, and the SW all
   stay exactly as they are. Lower risk, easy revert.

---

## 3. Ground truth (verified file:line anchors)

Routing / shell:
- `route()` — `app.js:7171`; manages `route-*` body classes (7185-7199) and calls
  `setShellChrome(routeKey, title)` (7246-7252).
- `setShellChrome()` — `app.js:3472` (sets `#appbar-title`, toggles `.tabs__tab--active`).
- `setShellVisible()` — `app.js:3465` (toggles `.hidden` on `#site-header` + `#appbar` + `#tabs`).
- `isMobileDevice()` — `app.js:1226`. `folderStorageOffered()` — `app.js:8659`.
- Kebab sheet — `openKebabSheet()`/`closeKebabSheet()`/`initKebabSheet()` `app.js:3516-3582`;
  `data-kebab-action` proxies to the floating buttons (`#diag-toggle`,
  `#bug-report-button`, `#clear-app-cache-button`, `#reset-everything-button`).

Directory / selection / groups (all desktop-shared — gate, don't delete):
- `renderDirectoryList()` — `app.js:5779`; per-row `.dir-mark` select button at 5787-5800,
  name link at 5801-5804.
- `groupDraft` state — `app.js:70`; `toggleDraftMember()` 6306; `updateComposerFabFromDraft()`
  3592 (sets `body.has-selection`, `#composer-fab-count`).
- `#bulk-select-bar` — `updateBulkBar()` 6324, `bulkToggleVisible()` 6341.
- Composer — `renderRail()` 6258, `handleCreateGroupClick()` 6582, `openComposerSheet()`/
  `closeComposerSheet()` 3624-3646.
- Filters — `applyFilters()` 5478; has-email `#has-email-filter` (state `hasEmailOnly`,
  `app.js:27`, persisted `loadHasEmailFilter()` 5237); filter sheet `initFilterSheet()` 5698.
- Edit mode — `enterEditMode()` 6449, banner `#edit-mode-banner`.

Render paths:
- Fellow — `renderDetail()` `app.js:5888`; contact rows at 5951-5967 (`mailto:` 5951,
  `tel:` 5960, copy buttons); add-to-group link at 5906-5915.
- Settings — `renderSettingsPage()` `app.js:8975`; email field 8984, folder section 8997,
  download 9018, restore section 9037, Claude-Desktop/MCPB section 9061.
- About — `renderAboutPage()` `app.js:6698`; stats via `getStats()` ~7034.

CSS (`app/static/styles.css`):
- Desktop hides shell: `.appbar, .tabs { display:none }` at `≥1025px` (4307-4312).
- Mobile focus-mode block at `≤1024px` (4323-4372); about/settings hide `#directory`/`#group-rail`
  at all widths (4382-4385).
- FAB/composer-sheet/group-detail-actionbar mobile rules (4631-4740).
- **Scroll bug:** `.appbar` `position:sticky; top:0` (3940), `.tabs` `position:sticky; top:48px`
  (3994); `#directory` has `max-height:75vh; overflow-y:auto` on desktop (475) but at `≤700px`
  becomes `40vh` (712) and at `≤1024px` has **no height constraint** — the **body** is the
  scroll container, so the list scrolls with no affordance. This is the headline fix.

Tests / tooling:
- `tests/e2e/mobile/` — devices Pixel 5 (393×851), iPhone 13 (390×844), narrow-360 (360×720)
  in `conftest.py`. `test_mobile_layout.py` (overflow, ≥44px targets, no bottom element >40%vh),
  `test_mobile_interactions.py` (**directory→detail→FAB→composer→create-group — these break and
  must be rewritten**), `test_routes.py` (screenshot baselines in `__snapshots__/`),
  `test_folder_gate.py`. Recipes: `just test-mobile`, `just test-mobile-functional`,
  `just test-mobile-promote`, `just serve-lan`.

---

## 4. Implementation sequence (each PR independently shippable + revertible)

Ship in order. Keep `just test-fast` + `just test-mobile-functional` green at every step.
The maintainer's ship-and-iterate bias applies — PRs 1-2 are the ones that *feel* the change
on a real phone; ship those first and gather feedback before the polish PRs.

**Match-the-mock is in scope, not a later cleanup.** Each PR ports its matching component
styles from [`mockups_no_groups/styles.css`](mockups_no_groups/styles.css) so the running app
reads as the mock *at every step* (the **Match the mock** bullet in each PR lists the exact
classes to lift). This is CSS porting onto the reused DOM — no new structure, no added risk —
and it's cheaper than tuning the live UI screen-by-screen later. The only items deliberately
left for a real-device polish pass are the truly subjective calls (final photo crop, whether
the chip beats the checkbox once it's in hand).

### PR 1 — `is-phone` flag + the scroll-container shell (the headline fix; highest risk)

The one PR that fixes the screenshot. Layout reflow — QA hardest here.

- **app.js:** at boot (next to the first `setShellVisible(true)`, `app.js:11100`), add
  `document.body.classList.toggle('is-phone', isMobileDevice())`. No visible change yet.
- **styles.css:** introduce a `body.is-phone` shell that turns the page into a fixed-height
  flex column where the **content region is the only scroller**:
  ```css
  body.is-phone { height: 100dvh; overflow: hidden; display: flex; flex-direction: column; }
  body.is-phone .appbar   { flex: 0 0 48px; }      /* fixed */
  body.is-phone #site-header { flex: 0 0 auto; }   /* sticky search header on directory */
  body.is-phone #app-wrap { flex: 1 1 auto; min-height: 0; display: flex; }
  /* the one visible content child per route becomes the scroller */
  body.is-phone #directory,
  body.is-phone #detail   { flex: 1 1 auto; min-height: 0; overflow-y: auto;
                            -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }
  ```
  Remove the sticky/negative-margin treatment of `.appbar`/`.tabs` under `is-phone` (they're
  now flex items, not sticky). `min-height:0` is the load-bearing line — without it the flex
  child refuses to shrink and the scroll never appears.
- **Verify:** on a phone, the appbar stays put, the directory list scrolls *inside* its region
  with a visible scrollbar/affordance, and the search header doesn't scroll away. No
  horizontal overflow (`test_mobile_layout.py` still green). Fellow/Settings/About each scroll
  within `#detail`.
- **Match the mock:** none — PR 1 is structural only (keeps it the clean, isolated reflow).
  The directory-surface visuals (chip, chevron, row spacing) land in PR 3.
- **Risk:** `100dvh` vs `100vh` and the iOS URL-bar resize; Android keyboard insets when the
  search field is focused. Test both. Keep `#tabs` for now (removed in PR 2) so this PR is a
  pure scroll fix.

### PR 2 — Hamburger nav drawer; retire the tab strip on phones

- **index.html:** add a hamburger button to `.appbar` (or convert `#appbar-kebab` into the
  hamburger on phone) and a drawer + scrim near the other sheets:
  ```html
  <div id="nav-scrim" class="sheet-scrim hidden" hidden></div>
  <aside id="nav-drawer" class="drawer hidden" role="dialog" aria-modal="true" aria-label="Menu" hidden>
    <!-- head + Directory/Settings/About links + build-tag footer -->
  </aside>
  ```
- **app.js:** wire `openNavDrawer()`/`closeNavDrawer()` by cloning the kebab-sheet pattern
  (`app.js:3516-3582`) — click to open, scrim + Esc + link-click to close. Populate the build
  tag from the same source the About page uses. Hide `.tabs` on `body.is-phone`.
- **styles.css:** port `.drawer` / `.drawer-link` / `.drawer__foot` from
  `mockups_no_groups/styles.css`; `body.is-phone .tabs { display:none }`.
- **Decision in effect:** drawer is pure nav (no Groups). The kebab stays for now (its tools
  move in PR 5).
- **Match the mock:** port `.drawer`, `.drawer__head`, `.drawer__title`, `.drawer-link`
  (+ `--active` inset-bar state), and `.drawer__foot` / `.build-tag` verbatim from
  `mockups_no_groups/styles.css`. Reproduce the mock's drawer head ("Menu" + close ✕) and the
  build-tag footer; use the mock's hamburger glyph (three lines) for the appbar control.
- **Verify:** hamburger opens/closes the drawer; Directory/Settings/About navigate; no tab
  strip on phone; desktop unchanged (drawer never shows ≥1025px / non-phone).

### PR 3 — Strip group + selection chrome on phones; redirect group routes

- **app.js `renderDirectoryList()` (5779):** when `body.is-phone`, render rows as plain
  full-width links (no `.dir-mark` button) — matches the mockup. (JS-skip is cleaner than
  CSS-hide here: it removes a dead 44px tap target rather than leaving an invisible one.)
- **app.js `route()` (7171):** if `isMobileDevice()` and the hash is a group/edit route,
  `location.replace('#/')` (or set hash to `#/`) before dispatch. Covers `#/groups`,
  `#/groups/<id>`, `#/groups/<id>/directory`, `#/edit/<id>`.
- **styles.css `body.is-phone`:** `display:none` on `#bulk-select-bar`, `.detail-add-to-group`,
  `#composer-fab`, `#group-rail`, `#composer-scrim`, `#edit-mode-banner`, `.tabs__tab[data-tab="groups"]`
  (defensive — the tab is already gone in PR 2), and the group action/card sheets.
- **Match the mock (directory surface):**
  - Rows: apply the mock's `.directory-row` padding / `min-height: 56px`, ink-colored name, and
    add the trailing chevron (`.directory-row__go` `›` svg) so each row reads as a tap target.
  - Search region: restyle the has-email control from the current `.filter-checkbox` into the
    mock's removable `.filter-chip` (`has email ✕`) sitting next to a compact `.filter-btn`
    "Filters" control, and change the count to the `142 / 515` form (`.filterbar__count`).
    Port `.filterbar`, `.filter-btn`, `.filter-chip`, `.filter-chip__x`, and the
    `.directory-row*` rules from `mockups_no_groups/styles.css`. Function is unchanged
    (defeatable default; the chip's ✕ clears has-email exactly like unchecking did).
- **Verify:** directory rows go straight to the profile, with a chevron affordance; no
  FAB/composer ever appears; the has-email chip clears with one tap to reveal phone-only
  fellows; visiting `#/groups` on a phone lands on the directory. Desktop selection/compose
  untouched.

### PR 4 — Fellow profile: Email/Call call-to-actions

- **app.js `renderDetail()` (5888):** when `body.is-phone`, render a `.contact-cta` block near
  the top of the detail (below the name/tagline) with an **Email** button (`mailto:`, primary)
  and a **Call** button (`tel:`, ghost), each shown only when the corresponding field exists
  (`fellow.contact_email` / `fellow.mobile_number`, already the guards at 5951/5960). When email
  is absent, render the disabled "No email" state from the mockup. The existing inline contact
  rows + copy buttons stay (paste-elsewhere path). The `detail-add-to-group` link (5906-5915) is
  skipped on phone.
- **Match the mock:** port `.contact-cta` (+ the disabled "No email" state), and bring the hero
  to the mock layout — `.fellow-hero` ordering (photo, then name, then tagline), the
  `.fellow-photo` square/centered treatment with an initials fallback, `.tag-chip` chips, and
  `.section-head` for the bio/free-text blocks. Lift all of these from
  `mockups_no_groups/styles.css`. (Final photo crop — square vs the current circular — is the
  one subjective bit to confirm on a real device; default to the mock's square.)
- **Verify:** the email+phone fellow shows both CTAs and the mock hero; the phone-only fellow
  shows Call promoted and Email disabled; tapping launches the device mail/dialer.

### PR 5 — Mobile Settings: app-info + tools only; retire the kebab on phones

- **app.js `renderSettingsPage()` (8975):** when `body.is-phone`, omit the email field (8984),
  folder section (8997), download (9018), restore section (9037), and Claude-Desktop/MCPB
  section (9061). Render an **App info** block (build label, server label, fellow count, last
  update — already computed for the About page) and a **Tools** block with Diagnostics / Report
  a bug / Clear app cache, wired to the *existing* handlers (the same ones the kebab proxies to).
- **index.html / app.js:** hide `#kebab-sheet` and the kebab button on `body.is-phone`; the
  appbar's right-side control is the hamburger (PR 2). Keep Reset Everything reachable from the
  Settings Tools block (danger styling) since it's no longer in a sheet.
- **Match the mock:** render App info as a `.card` of `.stat-line` rows, the tools as
  `.tool-row` buttons (icon + label + chevron, with `--danger` for Clear cache / Reset), section
  labels as `.section-head`, and close with the mock's `.hint` line ("No folder, backup, or
  email settings on mobile…"). Port `.card`, `.stat-line`, `.tool-row`, `.section-head`, `.hint`
  from `mockups_no_groups/styles.css`.
- **Verify:** mobile Settings matches the mock — App info card + tool rows + hint; no
  email/folder/backup/MCPB; every tool works; desktop Settings unchanged.

### PR 6 — Tests, docs, snapshot baselines

- **tests/e2e/mobile/:**
  - Rewrite `test_mobile_interactions.py`: delete the FAB/composer/create-group flow; add
    *hamburger opens drawer*, *directory row → fellow detail*, *no group chrome present
    (`.dir-mark`/`#composer-fab`/`#group-rail` absent or hidden)*, *Email/Call CTAs present on a
    fellow with contact info*, *`#/groups` redirects to `#/`*, *Settings has no email/folder/backup*.
  - Keep `test_mobile_layout.py` (overflow / ≥44px / bottom-bar) — should pass unchanged and now
    also assert a real scroll container exists on the directory.
  - Re-promote `test_routes.py` snapshot baselines via `just test-mobile-promote` after visual
    review of `current_state/` (groups/group-detail baselines for phone devices either deleted or
    captured as the redirect-to-directory state). Since match-the-mock is folded into PRs 2-5,
    the promoted phone baselines should visually track `mockups_no_groups/` — eyeball them
    against the gallery before promoting.
- **Docs (per CLAUDE.md — UI/UX changes ship with the doc):**
  - `docs/users_manual.md` — mobile section: hamburger menu, no groups on mobile, Email/Call,
    reduced Settings.
  - `docs/feature_platform_matrix.md` — extend "The mobile contract" to **browse + search +
    contact** (drop "organize into groups + manual backup").
  - Update the `mobile_folder_storage_policy` memory (backup removed; no private data on mobile)
    and add a short project memory for this initiative.
- **PR description (per CLAUDE.md):** the maintainer-only QA steps — `just serve-lan`, open on a
  real Android phone, verify scroll/drawer/CTAs/redirects, and the iOS Safari pass.

> Batching: PRs 3-5 are small and could ship together if the maintainer prefers fewer reviews.
> PR 1 should stand alone (it's the riskiest reflow). PR 6 must land with whichever PR first
> changes user-visible behavior, to keep the manual + tests honest.

---

## 5. The scroll fix, expanded (because it's the risky bit)

Today the scroll model on a phone is: `<body>` (the scroller) → sticky `.appbar` (top:0) →
sticky `.tabs` (top:48px) → `#site-header` (search) → `#app-wrap` → `#directory` (no height
cap at ≤1024px). Because nothing has a bounded height, the list grows the document and the body
scrolls — but the sticky headers and the absence of an inner scroll region mean there's **no
scrollbar track the user can see**, which reads as "frozen." That's the screenshot.

The fix flips it to: `<body class="is-phone">` is a `100dvh` non-scrolling flex column → fixed
appbar → fixed search header → `#app-wrap`/`#directory` is `flex:1 1 auto; min-height:0;
overflow-y:auto`. Now the *list* scrolls inside a bounded region with a real track, the chrome
stays put, and momentum/overscroll are contained. Pitfalls to test explicitly:

- `100dvh` (dynamic viewport) vs `100vh` on iOS Safari with the collapsing URL bar.
- Android soft-keyboard insets when the search input is focused (the list region must shrink,
  not get covered).
- `min-height:0` on every flex ancestor of the scroller (without it, the child won't shrink).
- Fellow/Settings/About use `#detail` as the scroller; confirm each route's single visible
  content child gets the `overflow-y:auto` treatment (focus-mode already hides the others).

---

## 6. Out of scope / unchanged

- Desktop (any non-phone): groups, composer, tabs/site-header, Settings folders/backup/MCPB —
  **all unchanged.**
- Auth / magic-link gate, the SW, the worker, `relationships.db`, the data-provider tiers.
- The install landing and `?gate=1` / `?diag=1` flows.
- The blue rebrand (already shipped) — tokens are reused, not re-applied.

## 7. Decisions resolved (was: open questions)

1. **Hamburger side — top-right, right-sliding drawer.** Confirmed 2026-06-01 (matches the
   approved kebab position and the mock).
2. **`#/groups` on a phone — silent redirect to `#/`.** Confirmed 2026-06-01. No toast.
3. **has-email + Filters on mobile — kept.** Defeatable default as a removable chip (PR 3) plus
   the compact Filters control; the structured filter sheet (cohort/type/region/citizenship)
   stays on phones.

Remaining real-device judgment calls (decide with the build in hand, not now):
- Final fellow-photo crop (square per mock vs current circular).
- Whether the has-email chip still beats a checkbox once it's on a phone.
