# Outstanding bug fixes and work

Things we noticed along the way that are not on the roadmap. We come back to these once the roadmap is complete.
Add new items at the top of the list; move finished ones to "Done" with the commit.

## Open

### 1. Branding gaps
- Apply branding to the admin area and emails (logo/colour in the templates).

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

### 7. Opening hours follow-ups
- No per-day shifts (e.g. lunch 11:00-14:00 and dinner 17:00-22:00 as two separate windows on the same day) — a day is one open/closed range.
- Reminder lead time is fixed at 3 hours (`ReservationService.REMINDER_LEAD_HOURS`), not a per-restaurant setting.
- The "Open now" badge is on the menu page only; not on the reserve or checkout pages, and there's no printable hours page.

### 8. Guest profile follow-ups
- Scoped to registered accounts: a phone/walk-in booking with only a `guest_name`/`guest_email` (no account) doesn't get a profile or show up in the customer list, so notes and allergies can't be attached to it.
- No search across notes/allergies (only name and email), no CSV export, no "add a note from the order page" shortcut.

### 9. Reservation-link follow-ups
- "Auto no-show release" only frees a table once the whole booked window has elapsed (existing behaviour); a faster release shortly after the start time, with a configurable grace period, isn't built.
- A cancelled-by-link booking that had an order attached is refused (same rule as cancelling while signed in) — the guest is told to contact the restaurant, with no in-page way to do that.

### 10. Waitlist follow-ups
- Email only — no SMS ("text me when it's ready") since no SMS provider is chosen yet.
- The 30-second poll on `/admin/waitlist` is a placeholder; move it onto the existing SSE channel if the queue gets busy enough to notice the lag.
- No quoted-wait auto-estimate (staff enter it by hand) and no "seated late" tracking.

### 11. Platform console follow-ups
- **Domain verification is a mock** — no real DNS/TLS check, just a button a platform admin clicks. Flagged clearly in the UI and docs; replace before it matters for anything real.
- No tenant status/health, no impersonation, no flag-editing UI, no list of *inactive* restaurants (the console only shows active ones), no way to deactivate or delete a restaurant from the console (only via direct database access today).
- The new-restaurant form has no client-side domain-format check before submitting — the backend rejects a bad one, but the error only shows up after a round trip.

## Done
- Colour picker (primary + secondary) and logo uploader on the admin settings page. The landing page (`pages/index.vue`) no longer says "DineFlow" for every tenant — it was unfinished Phase-2 scaffolding that never read the resolved restaurant at all.
- Password reset, change-password and owner invite links (no more printed passwords); header, sidebar and profile no longer show labels over the wrong links after a page load.
- Admin sidebar showed labels over the wrong links ("Floor plan" opened Reservations…): the server and browser rendered different menus. Both now render the full menu first and trim it after the page is live.
- Customer order page and table guests did not update live: they now follow their order over SSE (`GET /orders/{id}/stream`, `GET /table-session/stream`), with a slow poll only as a fallback. Status changes show in well under a second.
