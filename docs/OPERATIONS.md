# Operations runbook

Short, practical notes for running DineFlow. Keep this current — it is what you read at 9pm on a Friday.

## Health checks
| URL | Meaning |
|---|---|
| `GET /api/v1/health` | The process is up (liveness). |
| `GET /api/v1/health/ready` | Up **and** can reach the database (readiness). Returns 503 otherwise. Used by the production Docker healthcheck. |

Every response carries an `X-Request-ID`. If a user reports an error, ask for that id (500 responses include it in the body too) and search the logs for it.

## Logs
- Development: readable text lines. Production: set `LOG_FORMAT=json` for one JSON object per line (`ts`, `level`, `logger`, `message`, `request_id`).
- Ship them somewhere searchable (Loki, Datadog, CloudWatch). Container logs alone vanish on redeploy.

## Error reporting (Sentry)
1. Create a project at sentry.io and copy its DSN.
2. Set `SENTRY_DSN` in `.env` and rebuild the backend image (the `sentry-sdk` package ships in `requirements.txt`).
3. Unhandled 500s now appear in Sentry. Personal data is not sent (`send_default_pii=False`).
If the DSN is set but the package is missing, the app logs a warning and keeps running.

## Production safety guard
With `ENVIRONMENT=production` the API **refuses to start** if `JWT_SECRET` / `JWT_REFRESH_SECRET` are placeholders, shorter than 32 characters, or identical, or if `DATABASE_URL` still uses the dev password. Generate secrets with `openssl rand -hex 32`.

## Rate limits
Per client IP: login 20/min (and 8 per 10 min per account), sign-up 10 per 10 min, order 30 per 10 min, booking 20 per 10 min, availability search 90/min. Over the limit returns `429` with a `Retry-After` header.
- The limiter is **per process**. With several workers the effective limit multiplies; move it to Redis when scaling out.
- Behind a reverse proxy set `TRUST_PROXY_HEADERS=true`, otherwise every visitor looks like the proxy's IP. Never enable it when the API is exposed directly.

## Live updates (kitchen screen)
The kitchen screen updates the moment an order is placed, using Server-Sent Events (`GET /api/v1/admin/kitchen/stream`, staff only).

**How it works.** Order code calls `publish(...)`, which sends a Postgres `NOTIFY` inside the same transaction — so it is delivered **only if the order commits**. Every API worker keeps one `LISTEN` connection and forwards events to the browsers connected to *it*. This is why it works with several workers or servers without Redis. Events are hints ("something changed"); the screen refetches, so a missed event never leaves it wrong.

**Behind a reverse proxy** (nginx, Caddy, a load balancer) the stream must not be buffered or cut:
- nginx: `proxy_buffering off; proxy_read_timeout 3600s;` (the API already sends `X-Accel-Buffering: no`)
- any proxy/LB: idle timeout above ~30 s (the server sends a heartbeat every 15 s)

**Limits and safety nets**
- Each worker holds at most `REALTIME_MAX_STREAMS` (default 200) open streams, then answers 503.
- The browser reconnects with backoff, detects a silently dead connection (no heartbeat for 45 s), and refetches on every reconnect.
- The page also polls: every 60 s while live, every 15 s while not — so a broken stream degrades to slower updates, never to a stale screen.

**Debugging**: `docker logs <backend> | grep "Realtime listener"` shows connects/losses. The screen's badge reads *Live* / *Reconnecting…* / *Offline*. Open connections count against Postgres `max_connections` (one per worker for LISTEN, not one per browser).

## Rebuilding after dependency changes
`backend/requirements.txt` gained **Pillow** (image processing), **boto3** (S3 storage) and **sentry-sdk**. The app runs without them (uploads are stored unresized, S3 and Sentry stay off) so development keeps working, but rebuild to get the full behaviour — and always in production:
```sh
docker compose up --build            # development
docker compose -f docker-compose.prod.yml up --build -d
```

## Restarts and deploys
Live streams (kitchen screens) are closed the instant the server gets a stop signal, so a deploy or a dev auto-reload never waits on an open tab; browsers reconnect by themselves. As a backstop uvicorn force-closes anything still open after `--timeout-graceful-shutdown` (5 s in development, `GRACEFUL_SHUTDOWN_SECONDS`, default 10 s, in production).

## File storage (uploads)
Every image is checked by its **content** (not the browser's claimed type). With Pillow it is rotated upright, stripped of metadata (GPS/camera info), scaled to at most `IMAGE_MAX_SIDE` px (1600), re-encoded as WebP, and a 400 px thumbnail is stored next to it. SVG and other formats are refused (SVG can carry scripts).

Files live under `tenants/<restaurant_id>/…` (`menu/`, `branding/`), are named with random ids, and are served with a 1-year immutable cache header. A tenant can only ever delete its own files, and replaced/removed logos and menu photos are deleted automatically.

| Setting | Meaning |
|---|---|
| `STORAGE_BACKEND=local` | `backend/uploads` on this server. Fine for development or a single server; **lost on redeploy** unless the folder is a persistent volume, and shared by nobody else. |
| `STORAGE_BACKEND=s3` | Any S3-compatible service. Needs `S3_BUCKET`, `STORAGE_PUBLIC_URL` (the public/CDN URL of the bucket) and credentials; `S3_ENDPOINT_URL` for R2/MinIO/Spaces. |

**Moving to S3** later: copy `backend/uploads/*` into the bucket keeping the same paths, set the variables, and change stored URLs from `/uploads/...` to the new base (a one-line SQL `UPDATE`). Old `menu/r<id>-…` files keep working until then.

## Background jobs
A small queue in Postgres (table `jobs`) — no Redis. Code queues work with `enqueue(db, "type", payload)` **inside the same transaction** as the change that caused it, so a job exists only if that change committed, and can't be lost after it did. Workers claim jobs with `FOR UPDATE SKIP LOCKED`, so any number of workers or servers can run at once and each job runs once.

- **Retries:** a failed job is retried after 30 s, 2 min, 10 min, 1 h, then 6 h; after `max_attempts` (5) it is parked as `dead` for you to inspect. The error is kept in `last_error`.
- **Crash recovery:** a job stuck `running` for `JOB_STUCK_MINUTES` (10) is put back in the queue.
- **Wake-up:** new work wakes idle workers immediately (Postgres NOTIFY); they also poll every `JOB_POLL_SECONDS` as a safety net.
- **Where it runs:** by default a worker thread inside each API process. For a dedicated worker set `RUN_JOB_WORKER=false` on the API and run `python -m app.worker` (or `python -m app.worker --once` from cron to drain and exit).

Look at the queue:
```sql
SELECT status, count(*) FROM jobs GROUP BY status;
SELECT id, type, attempts, last_error, run_at FROM jobs WHERE status IN ('queued','dead') ORDER BY id DESC LIMIT 20;
UPDATE jobs SET status='queued', attempts=0, run_at=now() WHERE id = 123;   -- retry a dead job
DELETE FROM jobs WHERE status='succeeded' AND finished_at < now() - interval '30 days';   -- tidy up occasionally
```

## Email
Order confirmations and reservation confirmed/cancelled emails are queued as `send_email` jobs, so a slow or broken mail server can never slow down or fail an order. Guests are only emailed if we have their address; walk-ins and provisional holds are not emailed.

- **Development:** `EMAIL_BACKEND=console` prints each message in the API logs.
- **Production:** `EMAIL_BACKEND=smtp` with your provider's SMTP settings (Amazon SES, Postmark, Mailgun, Gmail…). Mail is sent **from** `EMAIL_FROM_ADDRESS` with the restaurant's name as the display name and the restaurant's email as Reply-To. Set up SPF/DKIM for that sender domain with your provider or mail will land in spam.
- Times in emails are shown in **UTC** until restaurants have a timezone setting (roadmap stage B5).
- All guest-supplied text is HTML-escaped, and header values are stripped of line breaks (no header injection).

## Backups
```sh
scripts/backup-db.sh                                   # -> backups/dineflow-<utc time>.sql.gz
COMPOSE_FILE=docker-compose.prod.yml scripts/backup-db.sh
scripts/backup-drill.sh                                # back up, restore into a throwaway DB, compare every table's row count
```
- **Schedule it** (cron / CI) and **copy the files off the server** (S3-compatible storage). A backup on the same disk dies with the disk.
- **Run the drill regularly** — an untested backup is a hope, not a backup. It only reads the live database.
- Backup files contain personal data (emails, password hashes). `backups/` is git-ignored; encrypt them at rest off-site.

### Restoring
```sh
scripts/restore-db.sh backups/<file>.sql.gz                       # into scratch DB "dineflow_restore" — inspect it first
FORCE_LIVE=1 scripts/restore-db.sh backups/<file>.sql.gz "$POSTGRES_DB"   # OVERWRITES the live database
```
Restoring over the live database needs `FORCE_LIVE=1` and the exact database name on purpose. Stop the backend first, restore, run `alembic upgrade head`, start it again.

## Tenants (one site per restaurant)
A restaurant's site is `<slug>.PLATFORM_DOMAIN`, or its own `custom_domain` (set on the restaurant row; point the domain's DNS at the frontend and add it to `CORS_ORIGINS`). The frontend asks `GET /api/v1/tenant?host=…` once per page load.
- Dev: `PLATFORM_DOMAIN=localhost` and `DEFAULT_TENANT_SLUG=bella-vista-kitchen` → `http://localhost:3000` and `http://bella-vista-kitchen.localhost:3000` both work.
- Production: set `PLATFORM_DOMAIN` to your domain, add a wildcard DNS record + wildcard TLS certificate, and leave `DEFAULT_TENANT_SLUG` empty (unknown hosts then show a "no restaurant here" page). `RESERVED_SUBDOMAINS` (www, admin, api…) never resolve to a restaurant.
- Customers are per restaurant (the same email can sign up at two restaurants); staff and platform admins are global. Access tokens carry a `tenant` claim, so **everyone is signed out once when this ships** (old tokens have none).
- Restrict the database role before onboarding a real client: RLS is not enforced while the app connects as a superuser (see ROADMAP A3).

## Creating a restaurant (demo or real)
```sh
docker compose exec backend python -m app.cli create-tenant \
  --name "Luigi's Trattoria" --slug luigis --owner owner@luigis.com --owner-name "Luigi Rossi" \
  --color "#c0392b" --secondary-color "#f1c40f" --logo /path/to/logo.png --template pizzeria \  # templates: generic | pizzeria | cafe
  --timezone "America/Los_Angeles" --custom-domain order.luigis.com                             # both optional
```
It creates the restaurant with a starter menu, tables and a placeholder weekly schedule (edit the real hours in Settings afterwards), an owner admin account, turns on `custom_branding`, and prints the site address (`http://luigis.localhost:3000` in dev, `https://luigis.<PLATFORM_DOMAIN>` in production). Nothing is created if the slug, colour, logo or timezone is invalid. If the owner email already belongs to a staff account, that account is given access to the new restaurant instead. The logo path must be readable *inside* the container (copy it in with `docker compose cp`).
A very light brand colour is darkened just enough for white button text to stay readable. `--secondary-color` is an optional accent for badges and highlights — it falls back to a default amber until set. Change either colour later from the restaurant's own Settings page or with `PATCH /admin/settings` (`primary_color`, `secondary_color`).

**Or without a terminal:** sign in as a platform admin (`SUPER_ADMIN` role — the seed data's is `superadmin@dineflow.demo` / `Demo1234!`) and open **`/platform`**. It lists every restaurant and has a **New restaurant** form asking for the same things the command does — name, slug, owner, branding, template, timezone, an optional custom domain — and shows the site link and the owner's one-time set-password link when it's done.

## Custom domains (mocked verification)
A restaurant can point its own domain at the platform (`order.theirrestaurant.com`) — set it from the restaurant's own **Settings** page or when creating it on `/platform`. It must look like a real domain and be unique across restaurants; the database itself enforces the uniqueness (`uq_restaurants_custom_domain`), so a race between two admins can't both claim the same one.

There is **no real DNS or TLS check yet** — that's Stage E work. What exists today is a placeholder: the domain is stored, resolution already works (`core.tenancy.resolve_tenant` matches it, same as it always has since Stage A3), and a platform admin can click **Mark verified** on `/platform` (or `POST /platform/restaurants/{id}/verify-domain`) to flip a status badge from "Pending verification" to "Verified" — that's it, no DNS lookup happens. Changing the domain clears the verified status, so a stale "Verified" badge never survives a domain change. Before relying on this for anything real, replace that endpoint with an actual DNS TXT-record check and automatic TLS issuance.

## Waiter view
**Waiter view** (admin sidebar, needs `qr_table_ordering`) is the floor at a glance: the seating plan with each table's tab total on it. A table glows yellow and is listed under *Needs you now* when a guest has called the waiter or asked for the bill, or when the kitchen has finished a round nobody has served yet (longest-waiting first). Tap a table for its panel:
- the rounds ordered so far with their status; **Mark served** when you have brought a finished round;
- requests, each with **Done**;
- **Add items for the table**: pick dishes (options and notes supported) and send them to the kitchen as a round on the table's behalf (shown as *Staff*); useful for guests without a phone;
- **Move to another table**: pick a free table; the tab keeps its rounds, the kitchen and requests follow, the guests' phones keep working, the old table goes to *Cleaning* and its QR code is replaced;
- **Close tab & clean table**; and **Seat guests here** for a free table.
Positions come from **Floor plan**; new restaurants made with `create-tenant` get a tidy default layout.

## Kitchen screen (stations, bump, 86)
Open **Kitchen** in the admin area (works full screen on a cheap tablet: use the *Full screen* button). Pick a station tab — *All stations*, *Kitchen*, *Bar* or *Dessert* — and the screen remembers it. Each dish has a station, set on the dish in **Menu → Made at** (new restaurants get sensible defaults: drinks → Bar, desserts → Dessert). A ticket shows only that station's dishes.
- **Bump:** tap a dish when it is done (tap again to recall it). When every dish is bumped the order becomes *Ready* by itself, and the customer or table sees it live. *Bump all* bumps a ticket (only this station's dishes on a station screen). In the *All stations* view, *Served — clear* finishes a ready order.
- **Timers:** each ticket counts up from when it was placed, turning amber after 8 minutes and red after 15 (`WARN_MINUTES` / `LATE_MINUTES` in `frontend/app/utils/kitchen.ts`).
- **Sound:** *Sound on* plays a ding for each new ticket. Browsers only allow sound after a tap, so after reloading a tablet touch the screen once.
- **86:** the *Still to make* list shows what is open across the tickets shown; **86** takes a dish off every menu and QR ordering at once (guests already at the table get a clear "unavailable" message if they send it). *Sold out* lists dishes that are off, with *Bring back*. Kitchen staff may 86; editing the menu itself stays admin-only.

## Live updates (customers and guests)
Besides the kitchen screen, a signed-in customer's order page (`GET /api/v1/orders/{id}/stream`, owner only) and a table's guests (`GET /api/v1/table-session/stream`, table pass only) follow their order over the same SSE channel. Status changes, new rounds and closing a tab reach them immediately; the pages also re-fetch every 30–60 s in case the connection dropped. Each open stream counts toward `REALTIME_MAX_STREAMS`.

## QR table ordering
Switch it on per restaurant: `python -m app.cli features <slug> qr_table_ordering on`. Then, in the admin area, open **Table ordering** *from the restaurant's own address* (the printed codes use the address you are on): **Print table tents** prints one card per table with the restaurant's logo and a QR code. Put the cards on the tables.
- **How a table works:** a guest scans the code → by default ordering is open only while staff have marked the table **Occupied** (Tables page) → the guest starts a shared tab (name optional), picks dishes and taps *Send to kitchen*. Each send is a round that shows on the kitchen screen as a table order. Everyone at the table sees the same tab and total. Payment is settled with staff at the end (pay-at-table comes later).
- **Waiter and bill:** on the *Our table* tab a guest can tap **Call a waiter** or **Ask for the bill** (the bill needs at least one round). Staff see these at the top of the **Table ordering** page under *Waiting for you*, with a count badge on that menu item on every admin page, and tap **Done** when handled; the guest's button resets by itself. Tapping twice is one request. Closing a tab clears its requests.
- **Closing:** when the party leaves, click **Close tab & clean table** (Table ordering page). Guest phones stop working, the table goes to *Cleaning*, and its QR code is replaced, so a photo of the old code is useless. **Replace code** does the same for one table without closing anything (lost tent, suspected abuse); reprint afterwards.
- **Policy:** `restaurants.qr_access_policy` is `SEATED` (default) or `OPEN` (anyone with the code can order at any time). There is no settings screen for it yet; change it in the database.
- **Limits:** one round can't exceed `QR_MAX_ORDER_TOTAL` (default 500); guests are rate-limited per IP.

## Testing on a phone (same Wi-Fi)
`localhost` and `<slug>.localhost` only exist on your computer, so a phone can't open them. Run `scripts/lan-dev.sh on luigis` (any restaurant slug): it points the site and API at your computer's Wi-Fi address, allows that origin, and makes that restaurant the default one there. Then open `http://<your-ip>:3000` on the phone. Open the admin **Table ordering** page from that same address so the printed QR codes carry it. `scripts/lan-dev.sh off` restores your `.env`. If the phone can't connect, allow incoming connections for Docker in the macOS firewall. This is for development only: with a real domain, tenants are found by subdomain (see *Tenants* above).

## Opening hours, timezone and closures
A restaurant's `timezone` (IANA name, e.g. `America/Los_Angeles`) and `opening_hours` (a day -> `"HH:MM-HH:MM"` or `"closed"` map) live on the restaurant row and are edited from **Settings → Hours & timezone**. A restaurant with no `opening_hours` set at all is **always open** — the same as before this feature existed — so nothing changes until an admin sets real hours. `closures` is a list of whole extra days shut (`{"date": "2026-12-25", "label": "Christmas"}`), which override the weekly hours regardless of what they say.

- **Enforced on:** a customer placing an order, and a guest booking a table (`GET`/`POST .../reservations`). Both are checked against the restaurant's local time at the moment in question (now, for an order; the requested slot, for a booking).
- **Not enforced on:** staff creating a reservation (`POST /admin/reservations`, including walk-ins) — private events and corrections shouldn't need a settings change first. Table QR ordering (a guest already seated) is likewise unaffected.
- **The rule lives in one place:** `backend/app/core/hours.py` (pure, no database) and its frontend port `frontend/app/utils/hours.ts` (for the "Open now" badge on the menu page, computed client-side from the same data so it doesn't need a round trip). Keep them in step if the rule ever changes.
- **A window that crosses midnight** (e.g. `"18:00-01:00"`) is read correctly; a date in `closures` beats the weekly hours for that whole day.

## Booking reminders
A reservation confirmed with at least ~3.5 hours' notice gets a reminder email scheduled for 3 hours before the visit (`REMINDER_LEAD_HOURS` in `reservation_service.py`), through the same job queue as every other email. Rescheduling the booking moves the reminder; cancelling it, or the guest being seated or the visit ending, drops it (`dedupe_key` = `email:reservation:{id}:reminder`, cancelled with `jobs.cancel_by_dedupe_key`). A booking made too close to its time gets no separate reminder — the confirmation email already told the guest soon enough.

## Confirm/cancel links (no account needed)
The confirmation and reminder emails carry a link to `/reservations/manage?token=…`. The token is a signed, stateless JWT (`app.core.security.create_reservation_action_token`, type `reservation_action`) naming the reservation and restaurant — nothing is stored for it, so there's nothing to clean up. It expires a few hours after the booking's start time (`ReservationService._issue_action_token`). From that page a guest can tap **I'll be there** (sets `reservations.guest_confirmed_at`, shown to staff as a ✓ next to the guest's name on the admin Reservations page) or **cancel** (same effect as cancelling while signed in — the cancellation email still goes out). The link stops working once the booking is cancelled, completed or expired, or once the token itself expires; none of this needs the guest to have an account.

## Waitlist (walk-in queue)
**Waitlist** (admin sidebar, gated by the `reservations` feature) is for guests with no table free yet. Staff add a name and party size (`POST /admin/waitlist`), **Notify** when a table opens up (emails "your table is ready" if the guest left an address, `notify_waitlist_ready` — same job queue as every other email; no email on file just marks them notified for the board), then **Seat** onto a specific table. Seating hands off to `ReservationService.create_admin_reservation` with `seat_immediately=True`, so it becomes an ordinary SEATED reservation — the table, kitchen and floor-plan logic don't need to know a waitlist was ever involved. **Remove** cancels an entry without seating it. Entries are per-restaurant (`waitlist_entries`, its own row-level security policy) and the list only ever shows those still `WAITING`/`NOTIFIED`, oldest first.

## Guest profiles
**Customers** (admin sidebar) lists every registered customer of the restaurant, not only those who have ordered — someone who has only booked a table, or who has just signed up, shows up too, since a customer account already lives in that restaurant's own table (`users.restaurant_id`). "Last seen" is the more recent of their last order and last booking. Open a customer to see their order and booking history and set **notes**, **allergies** and a **VIP** tag — staff-only, never shown to the guest. A customer's own account page has no access to this (`GET`/`PATCH /admin/customers/{id}` are staff routes).

## Row-level security (the database keeps restaurants apart)
Besides the checks in the code, PostgreSQL itself refuses to show or change another restaurant's rows. Every tenant table has a policy; when a request is *bound to a restaurant* the database only exposes that restaurant's rows, even if a query forgets its `WHERE restaurant_id = …`.
- **Which requests are bound:** staff routes (the restaurant they are working in, after the membership check), signed-in customers (their own restaurant) and table guests (their table's restaurant). Sign-in, public menus, QR lookups, background jobs and the CLI run unbound (as before) and still filter explicitly in code.
- **It only bites for the restricted role.** The owner role (`DATABASE_URL`) bypasses policies by design and is used for migrations, the seed and the CLI. The running app must connect as `dineflow_app` via `APP_DATABASE_URL`. `python -m app.db.roles` creates/updates that role (no superuser, **no** BYPASSRLS, ordinary data access only) and runs on every start, after migrations. Development does this out of the box.
- **Production:** set `APP_DB_PASSWORD` (a strong one) in `.env`; `docker-compose.prod.yml` then builds `APP_DATABASE_URL` for you. Without it the app still works but logs `Row-level security is NOT enforced` at start-up. Check the log for `Row-level security is enforced`.
- **Adding a table:** give it a policy in its migration (copy `0013_row_level_security`), or the test `test_every_tenant_table_has_a_policy` fails.
- **Running the tests safely:** the suite refuses to start unless `DATABASE_URL` (and `APP_DATABASE_URL`) point at a database whose name ends in `_test`, so it can never touch real data. Example: `docker compose exec -T -e DATABASE_URL=postgresql+psycopg://dineflow:<pw>@postgres:5432/dineflow_test -e APP_DATABASE_URL= backend python -m pytest -q tests` (empty `APP_DATABASE_URL` = run as the owner). Database roles are shared by every database on the server, so the restricted role has one password everywhere.
- **Proving it:** `backend/tests/test_row_level_security.py` connects as the restricted role and tries reads, writes, moving rows between restaurants and switching the policies off. To run the whole suite through the restricted role: create the role in the test database (`python -c "from app.db.roles import ensure_app_role; ensure_app_role(OWNER_URL, APP_URL)"`) and set `APP_DATABASE_URL`.
- **Known limits:** unbound paths (sign-in, public pages, jobs) rely on code filters; child tables are protected through their parent; `restaurants` and platform-admin routes are unbound.

## Passwords
- **Forgot password:** *Sign in → Forgot your password?* emails a link from the restaurant's own site (or its custom domain); it works **once** and expires in **1 hour**. The page gives the same answer whether or not the email has an account. Limits: 8 requests / 10 min per address, 4 / hour per account, and at most 3 links per account per hour.
- **Choosing a password** (reset, change or sign-up): at least 8 characters with a letter and a number, not a common password, and not containing the email name.
- **What a change does:** the person's other sessions are signed out (refresh tokens revoked) and they get a "your password was changed" email. An access token already issued can keep working for up to `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (30) after a change.
- **Signed in:** *Profile → Change password* needs the current password and keeps this device signed in.
- **Owners of new restaurants** get a set-password link from `create-tenant` (7 days). In development, with `EMAIL_BACKEND=console`, emailed links appear in the backend log: `docker compose logs backend | grep reset-password`. Emails need `PUBLIC_SITE_URL` (and `PLATFORM_DOMAIN`) set to your real addresses in production.

## Feature flags
Flags are declared in `backend/app/core/features.py` (key, default, description). A restaurant can deviate from a default; changes are audited.
```sh
docker compose exec backend python -m app.cli features bella-vista-kitchen                 # list the flags
docker compose exec backend python -m app.cli features bella-vista-kitchen kitchen_v2 on   # on | off | default
docker compose exec backend python -m app.cli audit bella-vista-kitchen                    # who changed what
```
The same is available to platform admins over the API (`/api/v1/platform/restaurants/{id}/features`). Turning a flag off blocks the API for that restaurant only and hides the UI for it. When a feature is on for everyone, delete the flag and its checks.

## Still to do (roadmap stage A1/A2)
Off-site backup automation, a staging environment, Redis-backed rate limiting.
