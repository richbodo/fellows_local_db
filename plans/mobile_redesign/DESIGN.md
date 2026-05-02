# EHF Fellows Directory — Mobile Layout System

A design spec for the Phase 2 mobile redesign. Companion mockups are in
`mockups/` (one HTML file per representative route, sharing
`mockups/styles.css`). Porting guidance for `app/static/styles.css` and
`app/static/app.js` is in `css_porting_notes.md`.

---

## 1. Aesthetic direction

**Direct, high-contrast, blue-on-white.** This is an experimental tool
used by ~15 fellows; it should look like a tool, not a polished
consumer product. The current CSS is direct and high-contrast, and
that's the right register for a small-group app under active
iteration. The redesign keeps the system-font stack and the existing
warning/danger families, but switches the brand from lavender purple
to a bright blue palette:

- **Bright blue (`#0066cc`) as the brand color** — same hex that's
  already used for links in the current app. Buttons, focus rings,
  active tab underline, FAB.
- **Muted blue wash (`#dbeafe`)** for selected rows, tag chips, and
  hover surfaces.
- **Cool blue-tinted off-white page background (`#eaf0f6`)** with
  pure white card surfaces — keeps cards visibly distinct.
- **Slate text scale** (`#0f172a` ink → `#475569` muted) — ties to
  the blue palette without going purple.
- **System font stack** (`system-ui, -apple-system, ...`) — same as
  current. No web fonts, no display serif, no "editorial" cosplay.
- **Warning yellow / danger red** kept from the current app —
  `#fff3cd / #ffe69c / #664d03` and `#7a1f1f / #fde2e2`.
- **Direct copy** — short labels, no italicized leads, no marketing
  prose.

The brand swap (lavender → blue) is the bigger change. The existing
app uses `#4a2c6a` purple in ~30 places across `app/static/styles.css`;
porting this redesign means a search-replace pass — see porting notes.

The redesign only changes things to improve **readability** and to
make the **UX patterns** work at narrow widths:

- Bump body text to 14–16px (the current app uses 0.78–0.9rem in
  many places, which reads small on phones; inputs go to 16px to
  avoid iOS auto-zoom on focus).
- Tighten contrast on muted text (`#7a6f91` is fine for large text /
  eyebrow labels but not for body — use `#444` / `#555` there).
- Use the existing brand purple as the focus ring color and the
  primary button background, with white text. Same pattern as the
  current `.group-rail-create` / `.install-pwa-button`.
- Touch targets ≥44pt — the current `.copy-btn` and other ad-hoc
  controls are too small to hit reliably on a phone.

What we **don't** do: add a new font family, introduce a paper-tone
background, dot-leader stat lines, italicized taglines, or any
"calm and refined" gestures that would push the app toward a
corporate magazine feel.

---

## 2. Tokens

### Type

| Role | Stack | Notes |
|---|---|---|
| Body / display | `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` | Same as current app. |
| Mono | `ui-monospace, "Cascadia Code", Menlo, Monaco, Consolas, monospace` | Same as current app — used for build tags, diagnostics. |

Sizes (mobile, bumped from current):

```
Display XL    24px / 1.2   — fellow name on detail
Display L     22px / 1.25  — page titles
Display M     16px / 1.3   — section heads (semibold)
Body L        16px / 1.5   — primary body, list rows, inputs (16px to avoid iOS auto-zoom)
Body M        14px / 1.45  — meta, hints
Body S        13px / 1.4   — uppercase labels, tag chips
Mono S        12px / 1.3   — build tag, diagnostics
```

### Color

```
--paper          #eaf0f6    page bg — cool blue-tinted off-white
--surface        #ffffff    cards / panels — pure white pops on paper
--surface-soft   #f5f8fc    very subtle blue wash (build-tag, hints)
--surface-alt    #d6e2ee    deeper blue tint (avatar bg, hero photo placeholder)

--border         #c4d0e0    light blue-grey
--border-strong  #a8b8cc
--border-grey    #cccccc

--ink            #0f172a    primary body — deep blue-black (slate-900)
--ink-deep       #0a1220    headings
--subink         #334155    secondary (slate-700)
--muted          #475569    tertiary, AA on white (slate-600)
--muted-soft     #64748b    slate muted — large text only (slate-500)

--accent         #0066cc    bright brand blue — primary buttons, focus ring, active tab
--accent-hover   #004499
--accent-deeper  #003366    text on light-blue tints (chips, selected rows)
--accent-soft    #dbeafe    muted blue wash — selected row, hover bg, chip bg

--link           #0066cc    same as accent (one blue, not two)
--link-hover     #004499

--warn-bg        #fff3cd    kept from current app
--warn-border    #ffe69c
--warn-text      #664d03

--danger         #7a1f1f    kept from current app
--danger-hover   #671717
--danger-bg      #fde2e2
--danger-border  #f0bcbc
```

Contrast checks (all AA-passing): `--ink` on `--paper` is 17:1 (AAA).
`--accent` on `--surface` is 5.6:1 (AA-normal). `--muted` on
`--surface` is 7.5:1 (AAA). `--accent-deeper` on `--accent-soft`
(chip text on chip bg) is 13:1 (AAA).

### Geometry

```
spacing scale  4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
radius         6 (control) / 12 (card) / 24 (sheet) / 9999 (pill)
shadow-sm      0 1px 2px rgba(31,27,22,0.06)
shadow-md      0 4px 16px rgba(31,27,22,0.08)
shadow-lg      0 12px 40px rgba(31,27,22,0.12)
touch-target   44px minimum
```

### Breakpoints

```
phone   ≤ 480px   single column, focus-mode-by-default
tablet  ≤ 768px   single column with wider gutters; rails still hidden
desktop > 768px   existing two-rail layout
```

The phone breakpoint is where the redesign rules apply. Tablet
inherits the focus-mode rules but loosens spacing.

---

## 3. Layout primitives

### App bar (top, sticky)

A 56px bar with safe-area top padding (`env(safe-area-inset-top)`).

```
┌───────────────────────────────────────────┐
│  Directory                            ⋮   │   56px
└───────────────────────────────────────────┘
```

- **Title** (left): the *current route*, set in Fraunces 19px.
  The app name "EHF Fellows Directory" lives only on the install
  landing and the About page heading — not in the persistent bar.
- **Overflow** (right, kebab): tap opens a bottom sheet containing
  build badge details (`app: <hash>`, `server: <hash>`, last update
  time), Diagnostics, Report bug, and Clear App Cache & Reload.
  These all currently float on every page; here they're consolidated.

### Tab nav (sticky, below app bar)

A 44px horizontal tab strip. Four destinations: **Directory ·
Groups · Settings · About**. Active tab gets a 2px lavender
underline and ink text; inactive tabs are subink.

Nothing scrolls horizontally yet (4 tabs fit), but the strip is
overflow-scroll so a future addition won't break the layout.

### Content area

Full-width below the tabs. Padding: 16px horizontal, 24px top/bottom.
Cards use 16px internal padding and 12px radius.

### Selection FAB (directory only, when selection is non-empty)

A 56px lavender circle, bottom-right, 16px from edges (offset by
`env(safe-area-inset-bottom)`). Shows the current selection count as
a number. Tap → expands into a **bottom sheet composer** (see below).
Hidden entirely when selection is empty — this is what fixes
problem #4: the composer doesn't exist on screen until the user has
something to compose with.

### Bottom-sheet composer

When the FAB is tapped, a 24px-radius sheet slides up from the
bottom, dimming the content behind it. Contains:

- Selection count + "clear all" link.
- Selected fellows as removable chips (tap × to drop).
- Group name input (auto-focus on open).
- "Save group" primary button.
- Drag handle at top for dismiss; tap-outside also dismisses.

This replaces the current right-rail composer entirely on mobile. On
desktop the rail returns.

### Action bar pattern (group detail, etc.)

Two primary inline actions + a kebab overflow.

```
┌──────────────────────────────────────────────┐
│  ✉ Mail group         ⬇ Export           ⋮  │
└──────────────────────────────────────────────┘
```

The kebab opens a bottom sheet of secondary actions:
- CC / BCC toggle (radio pair)
- Copy email addresses
- Edit members
- Delete group (red, separated by a divider)

Rationale: Mail and Export are the workflows users return for; CC/BCC,
Copy, Edit are configurations or one-off ops. Putting them in a sheet
keeps the bar quiet without hiding them.

---

## 4. Focus mode by default

The current app uses body classes (`route-groups-list`,
`route-group-detail`, etc.) to opt routes *into* focus mode. About
and Settings have no class, so directory chrome bleeds through.

**Fix:** at the phone breakpoint, focus mode becomes the default. The
CSS treats every route as focused unless explicitly told otherwise:

```css
@media (max-width: 480px) {
  /* Hide directory list, search bar, has-email filter,
     selection rail by default at phone widths */
  .directory-region,
  .search-region,
  .composer-rail { display: none; }

  /* Re-show only on the directory route */
  body.route-directory .directory-region,
  body.route-directory .search-region { display: block; }
}
```

This requires `route()` in `app.js` to add `route-directory` for `#/`
(currently it adds nothing). One-line change. See porting notes.

Tablet (≤768px) uses the same rules — rails stay hidden — with looser
spacing.

---

## 5. Per-route specs

### `#/` Directory

Mobile structure:
1. App bar — title "Directory", kebab.
2. Tab nav — Directory active.
3. Sticky search region: search input full-width, "has email" toggle
   below as a pill, fellow count as italic editorial line
   ("*515 fellows · 142 visible*").
4. Fellow list as alphabetical rows. Each row is a tap target ≥48px:
   - Name (Body L)
   - "+ select" button on right (44px tap target). Tapping toggles
     the fellow into the current selection without leaving the list.
5. FAB appears when ≥1 fellow is selected. Tap → composer sheet.

Removed at mobile: right-rail composer, "select all 515 results"
checkbox (lives in the composer sheet for power users).

### `#/about`

Mobile structure: focus-mode by default — no directory list bleeds
through.

1. App bar — title "About", kebab.
2. Tab nav — About active.
3. Page heading "About this app" (Display L) + paragraph text
   (Body L).
4. Stats list rendered as definition pairs, not a heavy grid:
   `Total fellows ............................. 515`
   `By cohort ..................................  9`
   etc. Editorial dot-leader style.
5. "Check for updates" as a quiet bordered button.
6. The bottom of the page links to the User Guide and the GitHub
   repo as inline body links, not buttons.

Diagnostics, Report bug, Clear App Cache live in the kebab — no
floating buttons on the page.

### `#/settings`

Same shell as About.

1. App bar — title "Settings", kebab.
2. Tab nav — Settings active.
3. Section: "Your email" with a single labeled input + Save button.
   The explanatory copy ("auto-captured from magic-link gate, used
   for email-it-to-me on group exports") lives directly under the
   field as a hint line, not a separate prose paragraph.
4. Future sections (theme, default group, etc.) stack as additional
   labelled blocks.

### `#/groups`

The current 5-column table is replaced with a **card list**. Each
card occupies full width:

```
┌──────────────────────────────────────────┐
│  Cohort 12 alumni                        │   ← name, Display L
│  12 members · created 2026-04-08         │   ← meta, Body S
│  Working on water access in Pacific…     │   ← note (2-line max)
│                                          │
│  [Visual ▤]  [Edit ✎]              [⋮]   │   ← actions
└──────────────────────────────────────────┘
```

- Tap card body → group detail page.
- Visual / Edit are inline icon-buttons (44px each).
- Kebab opens a sheet with Rename / Delete (red).
- Cards are separated by 12px gap, no rules between (white surface
  on paper background already does the work).

### `#/groups/<id>` Group detail

1. App bar — title is the *group name*; kebab.
2. Tab nav — Groups active.
3. Group meta line: member count + created date.
4. Inline note editor (textarea, auto-saves; current behavior).
5. Action bar — `[✉ Mail]` `[⬇ Export]` `[⋮]`. Sticky to the bottom
   of the viewport at mobile so it's always thumb-reachable.
6. Member list, scrollable. Each row: name + `×` remove (in edit
   mode) or just name (read-only).

The yellow "editing group" banner becomes a slim sticky bar between
the tabs and the action bar when in edit mode, with an inline
"Done editing" / "Cancel edits" pair.

### `#/fellow/<slug>` Fellow detail

1. App bar — title "Fellow", kebab.
2. Tab nav — Directory active (this is a sub-route of directory).
3. Hero: photo (square, 200×200, 12px radius) + name (Display XL)
   + tagline (italic, Body L, subink).
4. Tags as muted chips, wrapped.
5. Contact section: each email/phone on its own row with a copy
   button (44px) on the right. Existing `📋` clipboard pattern is
   preserved.
6. Free-text fields (career highlights, ventures, etc.) as labeled
   blocks with Display M section heads.
7. Bottom: "+ add to selection" full-width button.

---

## 6. Accessibility

- All interactive elements ≥44pt. Tap targets defined at the *button*
  level even when the icon is smaller — invisible padding extends
  the hit zone.
- Visible focus rings on all controls. Lavender outline (2px,
  `--accent`, 2px offset).
- Color is never the sole channel. Active tab has both color and
  underline. Danger actions have label + color + position (sheet
  bottom).
- The kebab and FAB get `aria-expanded` / `aria-controls` wired to
  their sheets.
- Bottom-sheet dismissal works with Esc and tap-outside.
- Text contrast: `--ink` on `--paper` is 13.4:1 (AAA).
  `--subink` on `--paper` is 6.6:1 (AA-large + AA-normal-pass).

---

## 7. Open questions / things deferred

- **Bottom nav vs. top tabs.** I chose top tabs to keep the FAB area
  clean and to match the existing top-nav structure. If the team
  wants iOS-app-feel, swapping to bottom nav is a contained
  CSS+app.js change post-port.
- **Selection persistence across routes.** The composer sheet
  assumes selection is a global state (which it already is). Edit
  mode (`#/edit/<id>`) reuses the same sheet but pre-filled with
  group members — nothing new to design there.
- **Web-font hosting.** Resolved — the redesign keeps the system
  font stack already in `app/static/styles.css`. No fonts to self-host.
- **Dark mode.** Out of scope for this pass. The token names
  (`--ink`, `--paper`) are intentionally non-color-bound so a dark
  variant is a one-file addition later.
- **iOS Safari quirks.** Mockups assume Chromium. Real-device
  Safari testing is Phase 4; the design accommodates `env(safe-area-
  inset-*)` already.

---

## 8. Mapping to existing code

Summary (full detail in `css_porting_notes.md`):

| Existing | Replaces / extends |
|---|---|
| `body.route-groups-list` etc. | Add `body.route-directory`, `body.route-about`, `body.route-settings`, `body.route-fellow` so focus-mode CSS can target every route, not just groups. |
| `#build-badge` floating top-right | Move into the kebab sheet at mobile. Keep current position on desktop. |
| Bottom-floating buttons (Diagnostics / Report bug / Clear App Cache) | Move into kebab sheet at mobile. Hide on `body.route-directory` direct surface. |
| Right-rail composer DOM | Same DOM, conditionally restyled into a bottom-sheet at mobile via CSS. JS state is unchanged. |
| `<table class="groups-table">` | Replace with `<ul class="groups-card-list">` at mobile. Easiest path: render both DOM forms and let CSS choose which is visible. (Or unify into card-list at all widths — see porting notes for trade-off.) |
| Action bar in `#/groups/<id>` | Two primary buttons inline + kebab. CC/BCC pill becomes a radio inside the kebab sheet. |
