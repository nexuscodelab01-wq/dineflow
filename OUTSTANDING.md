# Outstanding bug fixes and work

Things we noticed along the way that are not on the roadmap. We come back to these once the roadmap is complete.
Add new items at the top of the list; move finished ones to "Done" with the commit.

## Open

### 1. Customer order page doesn't update live
- **Seen:** when kitchen staff move an order to Preparing / Ready, the customer's order page doesn't change until they refresh (up to ~30 s).
- **Cause:** the live (SSE) channel only exists for staff screens (`GET /admin/stream`, needs a staff login). The customer page ([frontend/app/pages/orders/[id].vue](frontend/app/pages/orders/[id].vue)) just polls every 30 s.
- **Plan:**
  1. `GET /orders/{id}/stream`: customer token, order must belong to the caller and their restaurant; per-order topic (e.g. `order:{id}`) so a customer only hears about their own order.
  2. Publish to that topic wherever an order's status changes (staff status update, cancel), inside the same transaction as the change.
  3. Order page connects with the existing SSE client (`utils/sse.ts`), refetches on any event; keep the 30 s poll as a fallback.
  4. Tests: own order receives events; another customer / another restaurant is refused (403/404); status change publishes exactly once.
- **Size:** about an hour. Reuses the existing broker and SSE client.

### 2. Vue hydration warning on signed-in direct page loads
- **Seen:** loading any page directly (or refreshing) while signed in logs "Hydration completed but contains mismatches" in the browser console.
- **Cause:** the session token lives in localStorage, so the server renders the signed-out header and the browser then renders the signed-in one.
- **Plan:** render auth-dependent UI client-only (`<ClientOnly>` or an `isClient` flag) in the header/layout. Harmless for users today, but it hides real hydration problems.

### 3. Owner invite and password reset
- **Seen:** `create-tenant` prints a one-time password, and there is no way for anyone to change their password or reset a forgotten one.
- **Plan:** password-reset flow (emailed single-use token via the job queue, rate-limited) and use it for a "welcome, set your password" invite email from `create-tenant`; a change-password page for signed-in users. Needed before the first real client.

### 4. Branding gaps
- Colour picker and logo uploader on the admin settings page (the API already accepts `primary_color` and logo uploads).
- Apply branding to the admin area, emails (logo/colour in the templates) and the landing page (`pages/index.vue` still says "DineFlow").

## Done
- (nothing yet)
