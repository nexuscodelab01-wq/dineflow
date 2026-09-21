# Outstanding bug fixes and work

Things we noticed along the way that are not on the roadmap. We come back to these once the roadmap is complete.
Add new items at the top of the list; move finished ones to "Done" with the commit.

## Open

### 1. Vue hydration warning on signed-in direct page loads
- **Seen:** loading any page directly (or refreshing) while signed in logs "Hydration completed but contains mismatches" in the browser console.
- **Cause:** the session token lives in localStorage, so the server renders the signed-out header and the browser then renders the signed-in one.
- **Plan:** render auth-dependent UI client-only (`<ClientOnly>` or an `isClient` flag) in the header/layout. Harmless for users today, but it hides real hydration problems.

### 2. Owner invite and password reset
- **Seen:** `create-tenant` prints a one-time password, and there is no way for anyone to change their password or reset a forgotten one.
- **Plan:** password-reset flow (emailed single-use token via the job queue, rate-limited) and use it for a "welcome, set your password" invite email from `create-tenant`; a change-password page for signed-in users. Needed before the first real client.

### 3. Branding gaps
- Colour picker and logo uploader on the admin settings page (the API already accepts `primary_color` and logo uploads).
- Apply branding to the admin area, emails (logo/colour in the templates) and the landing page (`pages/index.vue` still says "DineFlow").

### 4. QR ordering follow-ups
- Settings screen for `qr_access_policy`; PIN and staff-approved modes; table tents as a downloadable PDF.
- Waiter/bill requests have no sound or push alert yet (B2 adds sound); the nav badge refreshes every 10 s.
- A guest's pass lasts 12 h and is bound to one session; it is kept in `localStorage`, so a second phone must scan the code itself (intended).
- Login rate limit (8 attempts / 10 min per account) is in-process: repeated automated test logins lock the account until the backend restarts.

### 5. Kitchen screen follow-ups
- Guests' open menu pages don't hide a dish the moment it is 86'd; their send is refused with a clear message. Publish a restaurant-wide "menu changed" event to the QR pages.
- Stations and the amber/red thresholds are fixed (three stations, 8/15 min); make them per-restaurant settings.
- An "expo" view (everything ready to pass, across stations), course firing, allergen tags, average ticket time.
- The kitchen screen refreshes the whole board on every event (fine for a restaurant's volume; switch to applying small updates if boards get very large).

### 6. Waiter view follow-ups
- Merge tables (large parties) and void/comp with a reason are not built; a staff round can add items but not remove them.
- No sound or push for new requests (the sidebar badge polls every 10 s).
- A guest who scans the *new* table's code joins the same tab (intended), but the old table's printed code stops working after a move, so a guest who reloads still relies on their saved pass.

## Done
- Admin sidebar showed labels over the wrong links ("Floor plan" opened Reservations…): the server and browser rendered different menus. Both now render the full menu first and trim it after the page is live.
- Customer order page and table guests did not update live: they now follow their order over SSE (`GET /orders/{id}/stream`, `GET /table-session/stream`), with a slow poll only as a fallback. Status changes show in well under a second.
