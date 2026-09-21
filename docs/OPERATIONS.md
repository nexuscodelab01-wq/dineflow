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
  --color "#c0392b" --logo /path/to/logo.png --template pizzeria     # templates: generic | pizzeria | cafe
```
It creates the restaurant with a starter menu, tables and hours, an admin account (a random password is printed once), turns on `custom_branding`, and prints the site address (`http://luigis.localhost:3000` in dev, `https://luigis.<PLATFORM_DOMAIN>` in production). Nothing is created if the slug, colour or logo is invalid. If the owner email already belongs to a staff account, that account is given access to the new restaurant instead. The logo path must be readable *inside* the container (copy it in with `docker compose cp`).
A very light brand colour is darkened just enough for white button text to stay readable. Change a colour later with `PATCH /admin/settings` (`primary_color`).

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
