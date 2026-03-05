# Feature: Fellow Detail Navigation Arrows

## Feature Description
Add large left-facing and right-facing arrow buttons at the bottom of a fellow's detail page. These arrows allow users to navigate to the previous or next fellow in the alphabetical list without returning to the directory sidebar. This provides a fluid browsing experience, especially on mobile where the directory list may be scrolled out of view.

## User Story
As a user browsing fellow profiles
I want to click left/right arrows at the bottom of a fellow's detail page
So that I can quickly move through fellows alphabetically without scrolling back to the directory list

## Problem Statement
Currently, browsing through fellows requires clicking each name in the sidebar list. There is no way to sequentially navigate between fellows from the detail view, which is cumbersome when reviewing multiple profiles in order.

## Solution Statement
Add a navigation bar at the bottom of the detail view with two large arrow buttons (left = previous, right = next). The buttons use the `list` array (already sorted alphabetically) to determine the previous and next fellow by slug. Clicking an arrow updates `window.location.hash` to navigate to the adjacent fellow. At the boundaries (first/last fellow), the corresponding arrow is hidden or disabled. The navigation bar is rendered inside `renderDetail()` as part of the detail HTML.

## Relevant Files
Use these files to implement the feature:

- `app/static/app.js` — The single IIFE containing all frontend logic. The `renderDetail(fellow)` function builds the detail HTML and must be extended to include the nav arrows. The `list` array holds the alphabetically sorted fellows used to determine prev/next.
- `app/static/styles.css` — All styles for the app. New CSS rules are needed for the navigation bar and arrow buttons.
- `app/static/index.html` — The HTML shell. No changes expected (arrows are rendered dynamically inside `#detail`).
- `tests/e2e/test_detail_view.py` — Existing Playwright e2e tests for the detail view. New tests for arrow navigation should be added here.

### New Files
- `.claude/commands/e2e/test_fellow_nav_arrows.md` — E2E test spec for validating arrow navigation works correctly.

## Implementation Plan
### Phase 1: Foundation
- Determine the index of the current fellow in the `list` array by matching on `slug`.
- Compute previous and next slugs from the sorted list.
- Design the nav arrow UI: a flex container at the bottom of the detail view with two large arrow buttons.

### Phase 2: Core Implementation
- Extend `renderDetail()` in `app.js` to append a navigation bar with left/right arrow links after the detail grid.
- Add CSS for the `.fellow-nav` bar: centered flex layout, large clickable arrow buttons with hover states, disabled state for boundary fellows.
- The arrows should use `<a>` tags with `href="#/fellow/<slug>"` so standard hash navigation works (no extra JS event handling needed).

### Phase 3: Integration
- The existing `hashchange` listener already calls `updateDetailFromHash()`, so clicking an arrow link will naturally re-render the detail view with the new fellow and new arrows.
- Verify that the arrows work correctly when the full fellows list hasn't loaded yet (Phase 1 minimal list is sufficient since it contains slugs).
- Mobile layout: ensure arrows are visible and tappable on narrow screens.

## Step by Step Tasks

### Step 1: Read existing E2E test examples for reference
- Read `.claude/commands/e2e/test_basic_query.md` and `.claude/commands/e2e/test_complex_query.md` to understand E2E test file format.

### Step 2: Create E2E test spec for arrow navigation
- Create `.claude/commands/e2e/test_fellow_nav_arrows.md` with test steps:
  1. Navigate to `/#/fellow/aaron_bird` (known first-ish fellow alphabetically).
  2. Verify detail page loads with "Aaron Bird".
  3. Verify a right arrow button is visible at the bottom of the detail.
  4. Verify no left arrow (or disabled) if Aaron Bird is the first fellow.
  5. Click the right arrow.
  6. Verify the detail now shows the next fellow alphabetically.
  7. Verify a left arrow is now visible.
  8. Click the left arrow.
  9. Verify we are back on "Aaron Bird".
  10. Take screenshots at key steps.

### Step 3: Add CSS for navigation arrows
- Add styles to `app/static/styles.css`:
  - `.fellow-nav` — flex container, `justify-content: space-between`, full width, margin-top, padding.
  - `.fellow-nav-arrow` — large button/link style, font-size ~2rem, padding, border-radius, background color matching the purple theme (`#4a2c6a`), white text, cursor pointer, min-width for easy tapping.
  - `.fellow-nav-arrow:hover` — darker background.
  - `.fellow-nav-arrow--hidden` — `visibility: hidden` (keeps layout stable, hides button at boundaries).
  - Responsive: ensure arrows are comfortably tappable on mobile (min 44x44px touch target).

### Step 4: Add navigation arrows to renderDetail() in app.js
- In the `renderDetail(fellow)` function, after building the detail grid HTML:
  - Find the current fellow's index in `list` by matching `fellow.slug`.
  - Determine `prevSlug` (index - 1) and `nextSlug` (index + 1), or null at boundaries.
  - Build a nav bar HTML string with left arrow (`&#x2190;` or `&larr;`) linking to `#/fellow/<prevSlug>` and right arrow (`&#x2192;` or `&rarr;`) linking to `#/fellow/<nextSlug>`.
  - If prevSlug is null, add `fellow-nav-arrow--hidden` class to the left arrow.
  - If nextSlug is null, add `fellow-nav-arrow--hidden` class to the right arrow.
  - Append the nav bar HTML after the `.detail-grid` div in the detail innerHTML.

### Step 5: Add Playwright e2e tests for arrow navigation
- Add new test methods to `tests/e2e/test_detail_view.py`:
  - `test_nav_arrows_visible_on_detail` — navigate to a fellow, verify `.fellow-nav` container exists with two arrow elements.
  - `test_right_arrow_navigates_to_next_fellow` — navigate to a fellow, click right arrow, verify URL and detail content change to next fellow.
  - `test_left_arrow_navigates_to_previous_fellow` — navigate to a non-first fellow, click left arrow, verify navigation back.
  - `test_first_fellow_hides_left_arrow` — navigate to the first fellow in the list, verify left arrow is hidden.
  - `test_last_fellow_hides_right_arrow` — navigate to the last fellow in the list, verify right arrow is hidden.

### Step 6: Run validation commands
- Run all tests to ensure zero regressions and new tests pass.

## Testing Strategy
### Unit Tests
- No new unit tests needed; the logic is minimal (index lookup in an array) and is best validated via e2e tests that exercise the full rendering pipeline.

### Edge Cases
- First fellow in list: left arrow should be hidden, right arrow should work.
- Last fellow in list: right arrow should be hidden, left arrow should work.
- Single fellow in list: both arrows hidden.
- Fellow loaded via direct hash URL before full list loads: arrows should still work since the minimal `list` (Phase 1) contains slugs.
- Fellow not found in list (e.g., accessed by record_id): arrows should be hidden gracefully rather than crashing.

## Acceptance Criteria
- Left and right arrow buttons are visible at the bottom of every fellow detail page.
- Clicking the right arrow navigates to the next fellow alphabetically and re-renders the detail.
- Clicking the left arrow navigates to the previous fellow alphabetically and re-renders the detail.
- The left arrow is hidden when viewing the first fellow in the list.
- The right arrow is hidden when viewing the last fellow in the list.
- Arrows are large and easily tappable on mobile devices (min 44x44px).
- All existing tests pass with zero regressions.
- New e2e tests validate arrow navigation.

## Validation Commands
Execute every command to validate the feature works correctly with zero regressions.

```bash
# Run all existing tests (database, API, e2e)
pytest tests/ -v

# Run just the detail view e2e tests (includes new arrow tests)
pytest tests/e2e/test_detail_view.py -v

# Run all e2e tests
pytest tests/e2e/ -v
```

## Notes
- The arrows use `<a href="#/fellow/...">` tags so they integrate with the existing hash-based routing. No new event listeners are needed.
- The `list` array is populated from Phase 1 (minimal list fetch), so arrows work immediately even before the full data load completes.
- Using `visibility: hidden` (not `display: none`) for boundary arrows keeps the layout stable so the remaining arrow doesn't jump position.
- No new pip dependencies or libraries are required.
