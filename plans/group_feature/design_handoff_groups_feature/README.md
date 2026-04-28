# Handoff: Fellows Groups feature

A new feature for the EHF Fellows local-first directory: select arbitrary subsets of fellows into named **groups**, then contact the whole group or export the group as a portable visual directory (PDF / HTML).

This document is the implementation spec. A developer who wasn't in the design conversation should be able to build the feature from this file alone.

---

## What's in this folder

| File | What it is |
|---|---|
| `README.md` | This spec. Read first. |
| `Selection wireframes.html` | The visual design canvas — open in a browser to see all artboards. The spec refers to artboards by number (① ② ③ ④ ④ᵇ ⑤ ⑥). |
| `screen-browse.jsx` | Directory + right-rail composer + edit-mode banner. Reference for screens ① ② ③ ⑥. |
| `screen-groups.jsx` | The `/groups/` index page. Reference for screen ⑤. |
| `screen-group-detail.jsx` | The single-pane group detail page (action bar with Contact / Export / Edit). Reference for screens ④ and ④ᵇ. |
| `screen-output.jsx` | The visual portrait directory (the in-app `view directory` view + the `Export → HTML` artifact). |
| `prototype-shared.jsx` | Shared helpers (color tokens, fellow data, layout primitives) imported by all four `screen-*.jsx` files. Read this to understand the design tokens; do **not** carry it over verbatim. |

The four `screen-*.jsx` files are **visual reference only** — translate their markup, class names, and behaviour into vanilla JS appended to `app/static/app.js`. The agent must not introduce React or a build step.

## About the design files

The files in this bundle are **design references created in HTML/JSX** — they are prototypes showing the intended look and behavior, not production code to copy directly. They were authored as a presentational design canvas (multiple artboards on one zoomable page) using inline React + Babel; that wrapper is for design review only.

Your job is to **recreate these designs in the target codebase's existing environment**. The target codebase is the EHF Fellows local-first directory:

- **Backend**: Python stdlib only (`http.server`, `sqlite3`, `json`, `pathlib`). No Flask, Django, Express. Single-file server: `app/server.py`.
- **Frontend**: vanilla JS, no build tools, no npm, no bundlers, no transpilers. Single IIFE in `app/static/app.js`. No modules, no classes.
- **Data**: SQLite (`app/fellows.db`) with FTS5 for search. ~500 fellows. Two-phase load (list-only first, full rows in background).
- **Distribution**: this is a **local-only PWA**. Once installed it runs entirely offline; the only thing it ever asks the server for is an updated app build. There is no SaaS backend, no per-user account, no inbound traffic.

Use these constraints faithfully — do not introduce React, a build step, or any new pip dependency. The HTML mocks use React purely as a design tool; **the real implementation must be vanilla JS** appended to `app/static/app.js`, with new HTML markup added to `app/static/index.html` and styles added to whatever CSS file the existing app uses.

### Why every "send" is a `mailto:`

The app has no server-side mail path and never will — this is a closed group that's being wound down, with no new members joining and no contact data being added or changed. Every "Contact the whole group" / "email it to me" affordance is a `mailto:` URL that hands off to the user's own mail client. **This is the intended design, not a workaround.** Don't introduce a server-side send route.

### What's mutable vs read-only

The fellows table (names, emails, phones, citizenship, free-text answers, photos) is **read-only**. The user authored none of it; they just consume it. The only things this feature lets the user create or change are **relationship data** — groups, group memberships, optional per-fellow tags, optional per-fellow private notes. Don't expose any UI that edits a fellow's contact info.

See `CLAUDE.md` and `README.md` in the repo root for the full constraint list, including: `escapeHtml()` for all rendered user data, parameterised `?` SQL placeholders, no auth (local-only), port 8765 fixed.

---

## Fidelity

**High-fidelity.** Colors, spacing, typography, button styles, and interaction states are intentional and match the existing app's visual language (system-ui, `#4a2c6a` purple section heads, plain blue underlined links, light-grey row labels). Recreate pixel-fidelity. Where this spec gives an exact value, use it.

The one explicit *low-fidelity* element: portrait images in the visual directory output use a placeholder SVG silhouette. The real implementation should use `/images/<slug>.jpg|.png` from the existing image lookup endpoint.

---

## What's being built

### User goal
Enable a fellow to: search the directory → tap a `+` next to names to add them to an in-progress group → name the group → save it → later open the saved group to (a) email everyone, (b) export a PDF or HTML visual directory, or (c) edit the membership.

### New surfaces
1. **Right rail on the directory page** — "add to a group" composer, always visible.
2. **`+` / `✓` margin marker** next to every fellow in the directory list.
3. **"add to group" / "remove from group" link** on the open detail card.
4. **Edit-mode banner** (yellow) — appears at the top of the directory when editing a saved group.
5. **`/groups/` page** — list of saved groups (rename, delete, click name to open).
6. **`/groups/<id>` page** — group detail with a single action bar (Contact / Export / Edit) and a members table.
7. **Visual directory output** — generated HTML or PDF artifact written to disk on export.

### New data
Two new tables alongside the existing `fellows`:

```sql
CREATE TABLE groups (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,             -- display name; may start with '#' for tag-named groups
  note TEXT NOT NULL DEFAULT '',  -- optional cream note shown on the detail page
  created_at TEXT NOT NULL,       -- ISO date
  updated_at TEXT NOT NULL
);

CREATE TABLE group_members (
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  fellow_record_id TEXT NOT NULL, -- matches fellows.record_id
  PRIMARY KEY (group_id, fellow_record_id)
);

CREATE INDEX idx_group_members_group ON group_members(group_id);
```

In-progress (un-saved) drafts persist to `localStorage` only — the right rail is the draft. No "save draft" affordance.

### New API endpoints
Append to the existing routes in `app/server.py` (sketch — adapt to existing patterns):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/groups` | list all groups: `[{id, name, count, note, created_at}, ...]` |
| `POST` | `/api/groups` | create: body `{name, note, fellow_record_ids: [...]}` → returns the new group |
| `GET` | `/api/groups/<id>` | full group: `{id, name, note, created_at, updated_at, members: [{record_id, name}, ...]}` |
| `PATCH` | `/api/groups/<id>` | update: body may include `name`, `note`, `fellow_record_ids` (full replacement of membership) |
| `DELETE` | `/api/groups/<id>` | delete |
| `GET` | `/api/groups/<id>/export?format=pdf|html` | stream the export artifact |

Use parameterised `?` placeholders. No auth.

PATCH must accept a full `fellow_record_ids` list so the **cancel-edits revert** can post the entry-snapshot back. (See "Editing a group" below.)

---

## Design tokens

These match the existing app. Reuse whatever CSS variables the current `app/static/` already defines; if none, hard-code these values exactly.

### Colors
| Token | Value | Where it's used |
|---|---|---|
| `--ink` | `#222` | Body text |
| `--bg` | `#f5f5f8` | App background |
| `--paper` | `#fff` | Cards, panels, modals |
| `--muted` | `#555` | Secondary text |
| `--border` | `#ccc` | Standard 1px borders, table cell borders |
| `--row-label` | `#f0f0f0` | Background of `<td>` label cells in detail tables |
| `--purple` | `#4a2c6a` | Primary buttons, section header backgrounds, active nav |
| `--purple-dark` | `#3b2355` | Hover, sidebar emphasis text |
| `--link` | `#0066cc` | All links (always underlined) |
| `--link-hover` | `#004499` | Link hover |
| `--warn-bg` | `#fff3cd` | Edit-mode banner background |
| `--warn-border` | `#ffe69c` | Edit-mode banner border |
| `--warn-text` | `#664d03` | Edit-mode banner text |
| `--lavender-soft` | `#faf8fc` | Right-rail bg, action-bar bg, footer status bars |
| `--lavender-border` | `#dcd6e8` | Right-rail border, action-bar border |
| `--pill-bg` | `#ede7f3` | Tag pill background |
| `--pill-text` | `#3b2355` | Tag pill text |
| `--note-bg` | `#fffbe6` | Cream "my note" / group note callouts |
| `--note-border` | `#e8d77a` | Cream note dashed border (1px dashed) |
| `--auto-title-bg` | `#fff7d6` | Auto-following title field cue (group composer) |
| `--auto-title-text` | `#7a6326` | Auto-following title field text |
| `--auto-title-icon` | `#a8923a` | ✎ glyph in auto-following title field |
| `--danger` | `#7a1f1f` | "delete" link color |

### Spacing & sizing
- Body font: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- Code/mono: `ui-monospace, Menlo, monospace`
- Default font-size: `0.95rem` body, `0.88rem` table rows, `0.85rem` action bars, `0.78rem` meta/captions, `0.7rem` finest helper text
- Border-radius: `2px` for inputs/panels, `3px` for buttons, `10px` for tag pills, `50%` for portraits
- Default border: `1px solid var(--border)`
- Section heads: `0.35em 0.5em` padding, `0.95rem` `font-weight: 600`, white on `--purple`
- Buttons: `0.3rem 0.7rem` padding (`0.2rem 0.55rem` for `.small`)

### Typography rules
- All section titles use the purple `SectionHead` pattern (white text on `#4a2c6a`).
- Links are blue `#0066cc` and **always** underlined (the existing app's convention).
- Tag pills use the `--pill-*` palette and live at `0.72rem` font-size, 10px border-radius.

---

## Screens

### 1. Directory + group composer (the main page)

The existing directory page gains:
- A **right rail** ("add to a group") — `flex: 0 0 240px`, `--lavender-soft` background, `--lavender-border` 1px border, `0.55rem 0.6rem` padding.
- A **margin marker** next to every name in the sidebar list (`width: 16px`, centered, `font-weight: 700`):
  - `+` in `#bbb` when the fellow is **not** in the group.
  - `✓` in `var(--purple)` when in the group.
  - Click toggles. The marker click must `stopPropagation` so it doesn't also trigger the row's "view fellow" navigation.
- An **"add to group" / "remove from group"** plain-blue link on the open detail card, beside the fellow name.
- A **"select all N results" bar** (lavender) above the sidebar list, **only visible when results are filtered** (search query present, or "has email only" checked). Hides when the unfiltered list of all 500 is showing — too easy to mis-click. Toggling adds/removes all currently-visible fellows.

The right rail contains, top to bottom:

1. Eyebrow label (uppercase, `0.78rem`, `#7a6f91`, letter-spacing `0.04em`):
   - `add to a group` (compose mode)
   - `editing group` (edit mode)
2. **Title input** with a special "auto-following" state:
   - **When auto-following** (user hasn't typed yet): background `--auto-title-bg` (cream), text in `--auto-title-text`, a `✎` glyph in `--auto-title-icon` positioned at the left inside the input (`position: absolute; left: 6px`), input padding-left increased to `1.45rem` to clear the glyph. The value mirrors the current search query — capitalised first letter, or the literal `#tag` if the query starts with `#`. Empty if no search.
   - **When user-edited**: standard white background, no glyph, normal padding. The flip happens on the first `onChange` from the user; once flipped, the title no longer follows the search.
   - The auto-follow → manual flip is one-way per session. There is no "reset to auto" button.
3. Helper line beneath (`0.7rem`, `#7a6f91`):
   - `auto-named — click to rename · N fellows` (auto-following with query)
   - `type a name, or search to auto-fill · N fellows` (auto-following, empty query)
   - `N fellows` (user-edited)
4. **Member chip list** — each picked fellow gets a `0.78rem` row showing the name and a `×` to remove. Removals are **instant**; no undo. Rows ellipsis on overflow. Empty state: `tap + next to a name to add. Search again to add more.`
5. **Primary button**, full width:
   - `Create new group` (compose mode) — purple primary. Disabled when `picked.size === 0`.
   - `Done editing` (edit mode).
6. Helper line:
   - `saves immediately to your groups. You can rename and edit it later.` (compose)
   - `changes save automatically as you add or remove.` (edit)

#### Edit-mode banner
When the user opens a saved group via "Edit group", the directory loads with a yellow strip across the top:

```
✎ editing "<group name>" — search and tap + to add more, tap ✓ to remove.   cancel edits
```

`--warn-bg` background, `--warn-border` bottom border, `--warn-text` text, `0.4rem 0.75rem` padding. The "cancel edits" link is right-aligned and underlined; its `title` attribute reads `revert this group to the state it was in when you opened edit mode`.

In edit mode, the directory **starts unrestricted** — no initial query, "has email only" *unchecked*, all 500 fellows visible. Members of the group are pre-loaded into the right rail with `✓` markers; the user filters/searches as normal to find more.

The detail pane in edit mode shows the **same full fellow record** as the regular directory — name, status, email, tags, "How to Connect" table. No edit-specific simplification.

---

### 2. Groups index page (`/groups/`)

A simple list of saved groups.

- **Top heading**: "Groups" (h2, `1.2rem`).
- **Empty state**: "No groups yet. Build one from the directory by selecting fellows and tapping Create new group."
- **Table** (full-width, `0.88rem` rows):

| Column | Content | Notes |
|---|---|---|
| Name | underlined blue link → `/groups/<id>` (group detail page) | Clicking the name navigates to detail. |
| Members | integer count | |
| Created | ISO date in mono | `0.78rem`, `#666` |
| Note | first ~60 chars italicised, em-dash if empty | |
| (actions) | `view directory` · `rename` · `delete` · `edit`, right-aligned | See below. |

#### Row actions, in order:
1. **`view directory`** — opens the visual portrait directory (the full-page artifact in `screen-output.jsx`). Same view that `Export → HTML` produces, rendered in-app instead of as a downloaded file.
2. **`rename`** — inline rename. Replaces the name cell with an autofocus `<input>`; saves on blur via `PATCH /api/groups/<id>` with `{name: ...}`. Display name keeps the leading `#` for tag-named groups.
3. **`delete`** — in `--danger` (`#7a1f1f`). Confirm via native `confirm()` before `DELETE /api/groups/<id>`. Deleting only removes the saved group; fellows themselves are unaffected.
4. **`edit`** — opens the directory in edit mode (same as clicking "Edit group" on the detail page). Skips a stop on the detail page for users who already know what they want.

- **Footer hint** (`0.78rem`, `#7a6f91`):
  > Click a group's name to open its detail page — that's where you contact the whole group, export, or edit. Deleting only removes the saved group; the fellows themselves are unaffected.

No "create" button on this page — groups are always created from the directory composer.

---

### 3. Group detail page (`/groups/<id>`)

Single-pane, mobile-first. Whole page constrained to `max-width: 760px; margin: 0 auto`.

Vertical stack:

1. **Breadcrumb** (`0.8rem`, `--muted`):
   `groups › <group name>`
2. **Title row** — h2 group name, inline `rename` link, then meta (`N fellows · created <date>`).
3. **Action bar** (`0.5rem 0.6rem` padding, `--lavender-soft` bg, `--lavender-border` border, flex wrap, gap `8px`). Three peer buttons in this order:
   - **`✉ Contact the whole group`** — primary (purple). Wraps a `<a href="mailto:?cc=<emails>&subject=<group name>">`. **CC, not BCC** (these are within-group conversations). No expansion menu.
   - **`⬇ Export a directory`** — default (white) button. Toggles the inline export panel below.
   - **`✎ Edit group`** — default button. Navigates to the directory in edit mode.
   - Right-aligned helper text (`0.72rem`, `#7a6f91`): `mailto: opens your client with everyone in CC`.
4. **Inline export panel** — shown only when "Export a directory" is toggled on. White background, `--lavender-border`. Section head "Export a directory". Three checkboxes laid out flex-wrap with `0.6rem 1.2rem` gap:
   - PDF directory · `<slug>.pdf` (default checked)
   - HTML directory · `<slug>/` · view offline
   - email it to me · your registered address (default checked)
   - Bottom-right: `cancel` and `Export` buttons.
   - Slug rule: `name.toLowerCase().replace(/^#/, "").replace(/[^a-z0-9]+/g, "-")`. So `Climate cohort` → `climate-cohort`, `#walking` → `walking`.
5. **Note callout** (cream `--note-bg` with dashed `--note-border`, italic): the group's note text, with a small `edit` link.
6. **Members card** — `SectionHead` "Members", then a borderless table where each row is a single cell containing an underlined blue name link. Footer strip (`--lavender-soft`): left "showing all N members", right "tap **Edit group** to add or remove".

There is **no top-right button row, no right sidebar.** All three primary actions live in the single action bar. The page reads identically on mobile.

#### Mailto details
- `mailto:?cc=<comma-joined-emails>&subject=<group name URL-encoded>`
- Body left empty (let the user write it).
- For the visual-directory export, the same bar appears at the top of the exported page, also using `cc=`.

---

### 4. Visual directory output

The artifact written to disk when the user runs Export. This is what gets opened in their browser or attached to an email.

- **Layout**: simple page, max-width content area, off-white `#fafafa` background, system-ui type.
- **Header**:
  - h1 group name
  - meta line (`0.85rem`, `#666`): `N fellows · created <date> · <note text if any>`
- **Group action bar** (lavender, `#f0ecf5` bg, `#dcd6e8` border, `3px` radius): a single line — `✉ Contact the whole group` link (blue, underlined) using the same `mailto:?cc=` mechanic. Helper text: `opens your mail client with everyone in CC`.
- **Portrait grid**: CSS grid, `repeat(auto-fill, minmax(120px, 1fr))`, gap `0.9rem`. Each cell:
  - 1:1 circular portrait (`border-radius: 50%`, 1px `#ccc` border) using `/images/<slug>.jpg|.png`. Fallback: SVG silhouette placeholder (see `screen-output.jsx` for the inline SVG).
  - Below the portrait: full name in `0.78rem`.
  - Whole cell is a button — clicking opens the popup.
- **Popup modal** (centred over a `rgba(30,25,50,0.45)` scrim):
  - Card, `360px` wide, `1px solid #ccc`, `4px` radius, `1rem 1.1rem` padding.
  - Top row: 80×80 circular portrait + name (`1.05rem` bold) + tiny caption "real photo from `fellows.db` images table".
  - Close `×` top-right.
  - Two-column table (`0.85rem`, label cells `#f0f0f0`):
    - email (when present) — `mailto:` link
    - phone — `tel:` link
    - linkedin — external link
  - Click outside the card or the `×` closes.

The exported HTML must work **offline** and be **portable** — single folder, no external CDN, all images relative paths.

---

## Interactions & behavior

### Composing a group (full walkthrough)

1. User opens the directory. Right rail is empty: title field shows the auto-following cream + ✎ state with empty value, helper says `type a name, or search to auto-fill · 0 fellows`. Create button is disabled.
2. User types `environment` in the search box. Sidebar filters. Title field auto-fills to `Environment` (cream + ✎). Bulk-select bar appears above the list.
3. User clicks `+` next to Tilla Abbitt and Tina Jennen. Markers flip to `✓`. Right-rail member list grows to 2.
4. User clicks the title field and types `Environment walking club`. Cream/✎ flips off; field is plain white now and stops following the search.
5. User clears search, types `#walking`. Sidebar shows the 3 fellows tagged `walking`. Title is *not* affected (already user-edited). User clicks `+` next to Tim Derrick, Tim Moor, Trevor Squier.
6. Right rail shows 5 fellows. User clicks `Create new group`. POST `/api/groups` with `{name: "Environment walking club", fellow_record_ids: [...]}`. Server returns `{id: 5, ...}`. Client navigates to `/groups/5`.

### Editing a group later

1. From `/groups/`, user clicks the group name → `/groups/5` (detail page) → clicks `✎ Edit group`. **Or** clicks `edit` directly from the row actions on the groups page. Both routes navigate to `/?edit=5`.
2. **On entering edit mode, the client snapshots the current `fellow_record_ids` list** (and `name`, `note`) into in-memory state. Call this `editEntrySnapshot`. This is what "cancel edits" will restore.
3. Directory loads unrestricted (no query, has-email *off*). Right rail loads in edit mode with the 5 existing members pre-checked. Yellow banner: `✎ editing "Environment walking club" — search and tap + to add more, tap ✓ to remove.   cancel edits`
4. User searches, taps `+` to add, taps `✓` to remove. Each toggle PATCHes `/api/groups/5` with the new full `fellow_record_ids` list. Auto-saves; no explicit save button. The "Done editing" button at the bottom of the rail simply navigates back to `/groups/5`.
5. **"cancel edits" link in the banner**:
   - For a saved group: PATCH `/api/groups/5` with `editEntrySnapshot` (full revert of name/note/membership), clear the right-rail draft, navigate back to `/groups/5`. The group ends up exactly as it was when edit mode started.
   - For a never-saved new group (the user navigated to edit mode without first saving — currently not possible by design, but guard anyway): clear the right-rail draft, navigate to the directory front page. Nothing was ever created.

The honest tradeoff: between entering edit mode and clicking cancel, other parts of the UI (e.g. the visual directory in another tab) will see in-progress edits because they're auto-saved. For a single-user local-only PWA this is fine; the user is the only observer. Don't try to hide the edits from the user's other views.

### Contacting a group
- Click the primary `✉ Contact the whole group` button. Browser opens the user's default mail client with `mailto:?cc=<everyone>&subject=<group name>`. Empty body. **CC, not BCC** — these are intentional within-group conversations.
- This is the **only** mechanism for sending mail. There is no server-side send.
- Future feature (not in scope now): per-fellow default contact channel + override. Mentioned in design notes only.

### Exporting a group
- Click `⬇ Export a directory`. Inline panel expands.
- User checks PDF, HTML, or both, plus optionally "email it to me".
- Click `Export`. The PWA generates the artifact(s) client-side (or the server hands them back as a stream). Files land in the user's `Downloads/` folder.
- "email it to me" opens a `mailto:?to=<self>&subject=<group name>&body=<reminder of where the file landed>`. There's no server-side mail send.
- **PDF**: print-ready single document, alphabetical portrait grid, contact details listed inline.
- **HTML**: a folder containing `index.html` + `images/`, served entirely via relative paths. Works offline. The HTML version is the exact mock in this bundle's `screen-output.jsx`. This is the same artifact the **`view directory`** row action renders in-app.

### Bulk select
- Only when filtered (search query OR has-email). Shows: `select all N results` / `deselect all N results`.
- Toggles **only the currently visible** fellows — does not affect already-picked fellows outside the filter.

### Removals
- Instant. No confirmation, no undo. Both `×` in the right rail and `✓` toggle in the sidebar work the same way.

### Group naming rules
- Names may start with `#` (preserved verbatim — useful as a memory cue that the group came from a tag search).
- Slugification (export filenames only): strip leading `#`, lowercase, replace non-alphanumerics with `-`.

---

## State management (vanilla JS sketch)

Add to the existing IIFE in `app/static/app.js`:

```js
const groupDraft = {
  members: new Set(),     // record_ids picked
  title: "",              // current title value
  titleEdited: false,     // has the user typed in the title field?
  editingGroupId: null,   // null when composing new; an id when editing
  editEntrySnapshot: null // {name, note, fellow_record_ids[]} captured on edit-mode entry
};
```

Persist `groupDraft.{members, title, titleEdited}` to `localStorage` under `ehf.group_draft` on every change while composing a new group. Load on page boot. **Clear** on:
- successful `Create new group` POST
- successful "cancel edits" of a never-saved draft

`editEntrySnapshot` lives in memory only — it's cleared when edit mode exits via "Done editing" or "cancel edits".

Edit mode keys off `?edit=<id>` in the URL. On boot, if present:
1. `GET /api/groups/<id>` to populate the rail.
2. Capture `editEntrySnapshot = {name, note, fellow_record_ids: [...]}`.
3. Show the yellow banner.
4. Skip the localStorage draft restore for this session.

Routing is hash- or query-based — match whatever the existing app uses. The existing app already routes `/`, `/about`, etc.; add `/groups`, `/groups/<id>`, `/groups/<id>/directory` (visual view), and `/?edit=<id>` in the same style.

---

## Assets

- **Portrait images**: served by the existing `/images/<slug>.jpg|.png` endpoint. Fallback when missing: inline SVG silhouette (see `screen-output.jsx` line ~67 for the data URI).
- **Glyphs used inline**: `+`, `✓`, `×`, `✎`, `✉`, `⬇`, `›`. All are Unicode — no icon font, no SVG sprite. This matches the existing app's plain aesthetic.

---

## Files in this bundle

| File | What it is |
|---|---|
| `Selection wireframes.html` | The design canvas entry point. Open in a browser to see all artboards. |
| `prototype-shared.jsx` | Mock data (40 fellow names, 4 saved groups), color tokens (`C.*`), and shared primitives: `SectionHead`, `Tag`, `Btn`, `AppFrame`, `initials()`. **The values in `C.*` are the source of truth for design tokens** — match them exactly. |
| `screen-browse.jsx` | Directory + group composer (compose and edit modes). The most detailed reference. |
| `screen-groups.jsx` | Groups index page (list, rename, delete). |
| `screen-group-detail.jsx` | Group detail page (action bar, export panel, members table). |
| `screen-output.jsx` | Visual directory export — what the generated HTML file looks like. |
| `design-canvas.jsx` | Just the design-review wrapper (zoomable canvas with section labels). Ignore for implementation. |

---

## Out of scope (mentioned for context)

- Per-fellow default contact channel + per-group override on "Contact the whole group". Will be added when fellows can tag a default channel on themselves.
- Sharing a group with another fellow.
- Importing/exporting groups as JSON.
- Server-side mail send (currently `mailto:` opens the user's client).
- Tag editing UX. Tags appear in the design as a future-proofing element (`#walking` search syntax, "your tags" row on the detail card with `+ add`); the actual tag-CRUD UI is a separate feature.
