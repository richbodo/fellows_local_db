# E2E Test: Fellow Detail Navigation Arrows

Test the left/right arrow navigation buttons at the bottom of the fellow detail page.

## User Story

As a user browsing fellow profiles
I want to click left/right arrows at the bottom of the detail page
So that I can navigate sequentially through fellows without returning to the directory list

## Test Steps

1. Navigate to the Application URL at `/#/fellow/aaron_bird`
2. Wait for loading to complete and detail to render
3. Take a screenshot of the detail page
4. **Verify** "Aaron Bird" is shown in the detail view
5. **Verify** a `.fellow-nav` container is visible at the bottom of the detail
6. **Verify** a right arrow (`.fellow-nav-arrow--next`) is visible
7. **Verify** the left arrow (`.fellow-nav-arrow--prev`) is hidden (first fellow)
8. Click the right arrow
9. **Verify** the detail now shows the next fellow alphabetically (e.g. "Aaron McDonald")
10. Take a screenshot after navigating right
11. **Verify** the left arrow is now visible
12. Click the left arrow
13. **Verify** we are back on "Aaron Bird"
14. Take a screenshot after navigating back

## Success Criteria
- Navigation arrows appear on the detail page
- Right arrow navigates to the next fellow alphabetically
- Left arrow navigates to the previous fellow alphabetically
- Left arrow is hidden for the first fellow in the list
- Right arrow is hidden for the last fellow in the list
- 3 screenshots are taken
