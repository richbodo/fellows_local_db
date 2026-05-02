# Porting Notes — Mockups → `app/static/styles.css` + `app/static/app.js`

A line-by-line guide from the mockup files in `mockups/` to concrete
edits in the existing app, organized so Phase 3 can ship route-by-route
without rearchitecting. Constraint reminder: vanilla JS, single IIFE,
single CSS file, no build step.

This is the only doc Phase 3 needs alongside the mockups. Read top-to-
bottom, then implement in the suggested order at the bottom.

---

## 1. Fonts: keep what's there

The redesign uses the existing system font stack — no `@font-face`,
no CDN imports, no `app/static/fonts/` directory. The `:root` block
in `mockups/styles.css` declares two families:

```css
--font-body: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
--font-mono: ui-monospace, "Cascadia Code", Menlo, Monaco, Consolas, monospace;
```

These match `app/static/styles.css:3` and the various mono
declarations already in the file. Once the token block lands, search
the existing CSS for the literal font stacks and replace with
`var(--font-body)` / `var(--font-mono)` for consistency — but that's
a cleanup, not a prerequisite for the mobile redesign.

---

## 2. Token block + brand color swap (lavender → blue)

Lift the entire `:root { … }` block at the top of
`mockups/styles.css` into `app/static/styles.css`, ordered before
the existing rules so subsequent rules can pick up the variables.

**The redesign changes the brand color** from `#4a2c6a` (lavender
purple) to `#0066cc` (bright blue) — and that means a coordinated
search-replace pass across the existing CSS. The existing app uses
the lavender literal in ~30 places, plus several supporting tints
(`#dcd6e8` borders, `#ede7f3` hover bg, `#faf8fc` wash, `#7a6f91`
muted) that all need to slide over to their blue equivalents.

The mapping:

| Existing literal | Used for | New token | New value |
|---|---|---|---|
| `#4a2c6a` | brand purple, primary button bg | `var(--accent)` | `#0066cc` |
| `#3b2355`, `#3a2050`, `#3d2460` | purple hover | `var(--accent-hover)` | `#004499` |
| `#2d1f3d` | deepest purple-black, headings | `var(--ink-deep)` | `#0a1220` |
| `#3b2355` (text) | text-on-lavender | `var(--accent-deeper)` | `#003366` |
| `#ede7f3`, `#f4eef9`, `#f0ecf5` | lavender wash, hover bg | `var(--accent-soft)` | `#dbeafe` |
| `#dcd6e8` | lavender border | `var(--border)` | `#c4d0e0` |
| `#c9c2d4` | strong lavender border | `var(--border-strong)` | `#a8b8cc` |
| `#faf8fc` | lavender wash bg | `var(--surface-soft)` | `#f5f8fc` |
| `#7a6f91` | lavender muted text | `var(--muted-soft)` | `#64748b` |
| `#5a4578` | lavender italic loading text | `var(--muted-soft)` | `#64748b` |
| `#0066cc`, `#004499` | link blue | `var(--link)`, `var(--link-hover)` | unchanged |
| `#222`, `#1e1e1e` | body text | `var(--ink)` | `#0f172a` |
| `#444`, `#555`, `#666` | secondary text | `var(--subink)` / `var(--muted)` | `#334155` / `#475569` |
| `#fff3cd / #ffe69c / #664d03` | warning yellow | `var(--warn-*)` | unchanged |
| `#7a1f1f / #5b1212 / #fde2e2` | danger red | `var(--danger*)` | unchanged |

Recommended porting sequence:
1. **Drop the `:root` token block** at the top of `styles.css`.
   Visually nothing changes yet — the file still uses literals.
2. **Search-replace the lavender purples first**, in this order:
   `#4a2c6a` → `var(--accent)`, then the hover variants, then
   `#2d1f3d` → `var(--ink-deep)`, then the wash/border lavenders.
   After this pass, reload the dev server — the entire app turns
   blue at once.
3. **Sanity check** the install landing, gate banner, group rail,
   and groups index — those have the densest brand-color usage.
4. **(Optional)** also swap the body, secondary, and muted text
   literals over to tokens — improves consistency but doesn't
   visually change anything if values were chosen to match.

A handful of literals appear as borders or shadow rgbs in the
original CSS (e.g. `rgba(74, 44, 106, 0.12)` in `.install-landing-
inner`). Update those to use the new accent in rgba form:
`rgba(0, 102, 204, 0.12)`. There aren't many.

```bash
# Quick audit of what's still hard-coded after the swap:
grep -n '#4a2c6a\|#3b2355\|#2d1f3d\|#ede7f3\|#dcd6e8\|#c9c2d4\|#faf8fc\|#7a6f91' app/static/styles.css
```

The PWA service worker caches `styles.css` aggressively. After
porting, `just build` then `just deploy-fast` (or a hard-reload of
the dev server) — and verify the build badge updates so users see
the new bundle.

---

## 3. Body classes for every route — `app.js` change

The mockups assume `route()` adds *exactly one* `route-*` class for
every route, not just the four groups variants currently handled at
`app/static/app.js:3528`.

**Edit in `app.js` `route()` (around line 3528):**

```js
body.classList.remove(
  // ADD: every route variant the CSS now targets
  'route-directory', 'route-about', 'route-settings',
  'route-fellow',
  'route-groups-list', 'route-group-detail',
  'route-group-edit', 'route-group-directory'
);

if (directoryMatch)       body.classList.add('route-group-directory');
else if (groupMatch)      body.classList.add('route-group-detail');
else if (editMatch)       body.classList.add('route-group-edit');
else if (hash === '#/groups')   body.classList.add('route-groups-list');
else if (hash === '#/about')    body.classList.add('route-about');     // NEW
else if (hash === '#/settings') body.classList.add('route-settings');  // NEW
else if (hash.indexOf('#/fellow/') === 0) body.classList.add('route-fellow'); // NEW
else                            body.classList.add('route-directory'); // NEW (default)
```

That's the *entire* JS change for focus-mode-by-default. Once every
route paints exactly one body class, the CSS in §4 takes over.

---

## 4. Focus-mode-by-default at phone breakpoint

The pattern is "hide directory chrome by default at ≤480px, re-show
only on `body.route-directory`". In `app/static/styles.css`,
introduce one media block:

```css
@media (max-width: 480px) {
  /* Anything that's part of the directory chrome — search bar,
     "has email" filter, fellows list, the right-rail composer.
     Use whatever the existing IDs/classes are. */
  body:not(.route-directory) #has-email-filter-wrap,
  body:not(.route-directory) #directory,
  body:not(.route-directory) .composer-rail,
  body:not(.route-directory) #search-input-wrap {
    display: none;
  }

  /* The bottom-floating chrome (Diagnostics + Report bug + Clear
     App Cache) is always hidden on mobile — moved into the kebab. */
  #diagnostics-button,
  #bug-report-button,
  #clear-cache-button {
    display: none;
  }
  /* Build badge: hidden on mobile (lives inside the kebab sheet). */
  #build-badge { display: none; }
}
```

Verify the actual element IDs by grepping `app/static/index.html` and
`app/static/app.js` for `#diagnostics`, `#build-badge`, etc. — the
names above are placeholders matching the conventional IDs likely
already in use.

---

## 5. App bar + tab nav — new persistent DOM

Currently the app's top region is implicit (a header inside
`index.html`'s body, with the title element and nav links inline
with the search bar). To get the mockup's app bar + tab strip:

**`app/static/index.html`** — restructure the very top of `<body>`
to:

```html
<header class="appbar">
  <h1 class="appbar__title" id="appbar-title">Directory</h1>
  <button class="appbar__kebab" id="appbar-kebab" aria-label="More" aria-expanded="false">
    <!-- inline 3-dot SVG -->
  </button>
</header>
<nav class="tabs">
  <a class="tabs__tab" href="#/" data-tab="directory">Directory</a>
  <a class="tabs__tab" href="#/groups" data-tab="groups">Groups</a>
  <a class="tabs__tab" href="#/settings" data-tab="settings">Settings</a>
  <a class="tabs__tab" href="#/about" data-tab="about">About</a>
</nav>
```

**`app.js`** — at the bottom of `route()`, set the title and
active-tab class:

```js
function setShellChrome(routeKey, title) {
  document.getElementById('appbar-title').textContent = title;
  document.querySelectorAll('.tabs__tab').forEach(function (el) {
    el.classList.toggle('tabs__tab--active', el.dataset.tab === routeKey);
  });
}
// Examples:
// renderAboutPage(): setShellChrome('about', 'About')
// renderSettingsPage(): setShellChrome('settings', 'Settings')
// renderGroupsPage(): setShellChrome('groups', 'Groups')
// renderGroupDetailPage(group): setShellChrome('groups', group.name || 'Group')
// updateDetailFromHash(): setShellChrome('directory', 'Fellow')   (sub-route of directory)
// default (#/): setShellChrome('directory', 'Directory')
```

The styles for `.appbar` and `.tabs` are in `mockups/styles.css`
lines ~145-205 — copy as-is. Tablet (≤768px) inherits the mobile bar;
desktop (>768px) is where the existing layout pattern resumes — wrap
the mobile-shell rules in an `@media (max-width: 768px)` block.

---

## 6. Kebab → bottom sheet

One bottom sheet, dynamically populated. The existing JS state for
"is the sheet open" can be a single boolean + a `<dialog>` element
(or a div with `display: none`). Skeleton:

```html
<!-- once at the bottom of body -->
<div class="scrim" id="kebab-scrim" hidden></div>
<div class="sheet" id="kebab-sheet" role="dialog" aria-labelledby="kebab-sheet-title" hidden>
  <div class="sheet__handle"></div>
  <div class="sheet__head">
    <div class="sheet__title" id="kebab-sheet-title">App info</div>
  </div>
  <ul class="diag-list" id="kebab-build-list"></ul>
  <div class="sheet__divider"></div>
  <button class="sheet-action" data-action="diagnostics">…Diagnostics</button>
  <button class="sheet-action" data-action="report-bug">…Report a bug</button>
  <button class="sheet-action sheet-action--danger" data-action="clear-cache">…Clear app cache & reload</button>
</div>
```

```js
document.getElementById('appbar-kebab').addEventListener('click', openKebabSheet);
document.getElementById('kebab-scrim').addEventListener('click', closeKebabSheet);
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closeKebabSheet();
});
```

Wire each `data-action` to the *existing* handlers that the floating
buttons currently call. Don't reimplement; just rebind.

The same scrim+sheet markup pattern is reused for the per-card kebab
on the Groups index and the action-bar overflow on Group detail —
just swap the contents.

---

## 7. Selection FAB + composer sheet

The current right-rail composer is a `<aside>` (or similar) elsewhere
in the DOM. Strategy: keep that DOM intact, conditionally wrap it
into the bottom-sheet at the phone breakpoint with CSS.

**Markup change** — wrap the composer in a known element so CSS can
target it:

```html
<aside id="composer-rail" class="composer-rail">
  <!-- existing composer DOM unchanged -->
</aside>
```

**CSS** — at desktop, it's a sidebar; at mobile, it's a bottom sheet
that's only visible when the FAB triggers it.

```css
@media (max-width: 768px) {
  .composer-rail {
    position: fixed;
    inset: auto 0 0 0;
    border-radius: 24px 24px 0 0;
    background: var(--surface);
    box-shadow: var(--shadow-lg);
    padding: 16px 16px calc(20px + env(safe-area-inset-bottom, 0));
    transform: translateY(100%);
    transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
    z-index: 12;
  }
  body.composer-open .composer-rail { transform: translateY(0); }
  body.composer-open::before {
    content: "";
    position: fixed;
    inset: 0;
    background: rgba(31,27,22,0.32);
    z-index: 11;
  }
}

/* FAB only renders on directory + when selection is non-empty.
   The body class .has-selection is already set/cleared by the
   selection-management code; piggyback on that. */
.fab { display: none; }
@media (max-width: 768px) {
  body.route-directory.has-selection .fab { display: flex; }
}
```

Existing app.js code that reads/writes the right-rail keeps working
unchanged; only its CSS positioning changes at mobile. The FAB is a
new element — add it once at the top level of `<body>`:

```html
<button class="fab" id="open-composer" aria-label="Open composer" aria-controls="composer-rail" aria-expanded="false" hidden>
  <span><span class="fab__count" id="fab-count">0</span><span class="fab__caption">selected</span></span>
</button>
```

Wire `#open-composer` to toggle `body.classList.toggle('composer-
open')`. Wire the existing "save group" success path to also
`body.classList.remove('composer-open')`.

`fab-count` reads from whatever variable already tracks selection
size — there's already a count rendered in the rail header today; reuse
that source of truth.

---

## 8. Groups index: table → cards

The existing markup is a `<table class="groups-table">` (around
`app.js:3625`). Two paths:

**Path A — render both, let CSS choose (lower-risk).** Generate a
`<ul class="groups-card-list">` next to the existing table, both
populated from the same group array. `display: none` on `.groups-
table` at ≤768px, `display: none` on `.groups-card-list` at >768px.
Pros: no behavior changes on desktop. Cons: double-render, two DOM
shapes to keep in sync.

**Path B — replace the table outright with cards at all widths.**
The card pattern works fine on desktop too (just with wider gutters
or a 2-column grid). Pros: one DOM shape. Cons: a desktop reviewer
might prefer the dense table.

I'd ship **A** for the redesign cycle (least surprise on desktop)
and revisit **B** later once there's user feedback that the cards
work everywhere.

The card markup matches the mockup at `mockups/route_groups.html`
lines ~30-72. Each card is a `<article class="group-card">` with
`group-card__title` / `group-card__meta` / `group-card__note` /
`group-card__actions`. The title is wrapped in an `<a>` to the group
detail; the action buttons attach the same handlers as the existing
table actions.

---

## 9. Group detail: action bar pinned to bottom

Currently the action bar (Mail / CC-BCC / Copy / Edit / Export) is
inline inside the group-detail render. To pin to bottom on mobile,
wrap it in `<div class="actionbar">` and add:

```css
@media (max-width: 768px) {
  body.route-group-detail .actionbar {
    position: fixed;
    inset: auto 0 0 0;
    z-index: 9;
  }
  body.route-group-detail main.content { padding-bottom: 96px; }
}
```

Two primary buttons in the bar (Mail, Export); the rest move into
`actionbar__more` (a kebab button that opens the same scrim+sheet
pattern as §6). The CC/BCC pill toggle becomes a labelled radio pair
inside that sheet — see `mockups/route_group_detail.html` lines
~135-145.

---

## 10. Fellow detail: minor polish

Most of the structure is already correct. Mobile-specific changes:

- Photo: existing `<img>` gets `class="fellow-photo"` and a fallback
  initials block when no image. Mockup uses a 200×200 square with
  12px radius; current app uses circular full-width — both are valid;
  pick what looks right with real photos.
- Action bar at bottom: a slim version with just `[✉ Mail]` and
  `[+ Add to selection]`. Same `actionbar` class as group detail.
- Prev / next arrows: the existing `#/fellow` route already supports
  navigation between adjacent fellows (per the e2e test
  `tests/e2e/test_detail_view.py`). Surface them as kebab-sized
  buttons in the app bar (mockup lines ~14-21).

---

## 11. Implementation order (recommended)

Each step is a green PR with passing snapshot baselines committed at
the end. Don't merge a step until the matching mockup matches the
running app at narrow-360.

1. **Tokens + fonts** — drop in `:root`, web-font choice, no DOM
   changes. Verify: nothing visually breaks at any width.
2. **App bar + tab nav** — DOM restructure, `setShellChrome()` call
   at every render path. Verify: title and active tab update on
   every hash change.
3. **Body class for every route** — the `app.js` change in §3.
   Verify: `document.body.className` shows `route-*` on every route.
4. **Focus-mode-by-default CSS** — the `@media (max-width: 480px)`
   block in §4. Verify: About + Settings + Groups no longer show
   directory list at 360px width. Snapshot baselines start to
   commit here.
5. **Kebab + bottom-sheet shell** — §6 plumbing, no behavior
   changes (just visual move from floating buttons to sheet).
6. **FAB + composer sheet** — §7. Verify: rail still works on
   desktop, FAB+sheet works on mobile, save round-trip is
   identical.
7. **Groups card list** — §8 path A. Verify: groups table still
   renders correctly on desktop, cards render on mobile, all four
   actions reachable.
8. **Group-detail action bar** — §9. Sticky at bottom, kebab
   overflow works.
9. **Fellow detail polish** — §10.
10. **Snapshot baselines committed** — `tests/e2e/mobile/__snapshots__/`
    populated, `tests/e2e/mobile/current_state/` deleted from gitignore
    or kept as before-pictures with a `before/` prefix in a separate
    PR.

Each step is small enough to ship in a day and revert independently
if it goes sideways.

---

## 12. What the mockups deliberately don't show

- **Loading and error states.** Existing `#loading` overlay and the
  unsupported-browser panel still apply; the mockups assume happy
  path.
- **The install landing page.** Out of scope — this redesign is for
  the installed-PWA experience.
- **Magic-link gate.** Lives at `?gate=1`, not a hash route.
  Untouched.
- **Visual portrait directory** (`#/groups/<id>/directory`). The
  existing yearbook grid layout already works at narrow widths
  (verified in `tests/e2e/mobile/current_state/group-visual-
  directory--narrow-360.png`); only minor app-bar work needed (use
  the same shell shown in `route_group_detail.html`).
- **Diagnostics view** (`?diag=1`). It's already a separate panel; it
  would migrate from a floating button to a kebab sheet entry in
  step 5 above. The panel itself doesn't need redesign.

---

## 13. Sanity-check checklist before shipping each PR

- [ ] At narrow-360 the title doesn't overlap the kebab.
- [ ] Tab strip is exactly 44px tall, visible bottom border on
  active tab.
- [ ] Every interactive control measures ≥44px in DevTools.
- [ ] Focus rings visible on every control under keyboard nav.
- [ ] `body.classList` contains exactly one `route-*` class.
- [ ] No floating buttons on screen at ≤480px.
- [ ] On group detail, action bar stays pinned during scroll.
- [ ] Bottom sheet dismisses on Esc and tap-outside.
- [ ] `tests/e2e/mobile/test_routes.py` still passes.
- [ ] `docs/users_manual.md` updated for any user-visible flow
  change (per CLAUDE.md). The composer-via-FAB pattern in
  particular needs a paragraph in the Groups → Composing a group
  section.
