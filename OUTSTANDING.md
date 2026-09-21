# Outstanding bug fixes and work

Things we noticed along the way that are not on the roadmap. We come back to these once the roadmap is complete.
Add new items at the top of the list; move finished ones to "Done" with the commit.

## Open

### 1. Branding gaps
- Colour picker and logo uploader on the admin settings page (the API already accepts `primary_color` and logo uploads).
- Apply branding to the admin area, emails (logo/colour in the templates) and the landing page (`pages/index.vue` still says "DineFlow").

### 2. QR ordering follow-ups
- Settings screen for `qr_access_policy`; PIN and staff-approved modes; table tents as a downloadable PDF.
- Waiter/bill requests have no sound or push alert yet (B2 adds sound); the nav badge refreshes every 10 s.
- A guest's pass lasts 12 h and is bound to one session; it is kept in `localStorage`, so a second phone must scan the code itself (intended).
- Login rate limit (8 attempts / 10 min per account) is in-process: repeated automated test logins lock the account until the backend restarts.

### 3. Kitchen screen follow-ups
- Guests' open menu pages don't hide a dish the moment it is 86'd; their send is refused with a clear message. Publish a restaurant-wide "menu changed" event to the QR pages.
- Stations and the amber/red thresholds are fixed (three stations, 8/15 min); make them per-restaurant settings.
- An "expo" view (everything ready to pass, across stations), course firing, allergen tags, average ticket time.
- The kitchen screen refreshes the whole board on every event (fine for a restaurant's volume; switch to applying small updates if boards get very large).

### 4. Waiter view follow-ups
- Merge tables (large parties) and void/comp with a reason are not built; a staff round can add items but not remove them.
- No sound or push for new requests (the sidebar badge polls every 10 s).
- A guest who scans the *new* table's code joins the same tab (intended), but the old table's printed code stops working after a move, so a guest who reloads still relies on their saved pass.

### 5. Sessions after a password change
- An access token already issued keeps working until it expires (30 minutes) after a password change or reset; only refresh tokens are revoked. Add a "password changed at" check to the access token if this needs to be immediate.
- Other pages that read browser-only state directly (orders, checkout…) may still log hydration warnings; gate them with `useHydrated()` when found.

### 6. Row-level security follow-ups
- Unbound paths (sign-in, public menus/availability, QR lookups, jobs, CLI) rely on code filters. Bind more of them (a public menu could be bound by its `restaurant_id`) and consider a fail-closed default once every path is classified.
- CI should run the suite once through the restricted role (see docs/OPERATIONS.md) so a new query that only works as the owner is caught.
- `restaurants` is only bound to its own row in tenant mode; platform-admin routes run unbound.

## Done
- Password reset, change-password and owner invite links (no more printed passwords); header, sidebar and profile no longer show labels over the wrong links after a page load.
- Admin sidebar showed labels over the wrong links ("Floor plan" opened Reservations…): the server and browser rendered different menus. Both now render the full menu first and trim it after the page is live.
- Customer order page and table guests did not update live: they now follow their order over SSE (`GET /orders/{id}/stream`, `GET /table-session/stream`), with a slow poll only as a fallback. Status changes show in well under a second.
