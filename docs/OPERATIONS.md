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

## Environments and deploys

Two stacks on the **same server**, sharing nothing but the machine and the proxy: production (`docker-compose.prod.yml`, `.env`) and QA (`docker-compose.qa.yml`, `.env.qa`, reached at `*.qa.dineflow.io`). QA has its own database, secrets, Stripe *test* keys and `EMAIL_BACKEND=console`, so it cannot touch a restaurant's real data, email a real customer or take a real payment. Production's Caddy serves the QA addresses too (see `caddy/Caddyfile`), so there is no second proxy, server or domain to pay for.

### How a deploy keeps production data
- The database lives in the named Docker volume `postgres_data`. `docker compose up --build` replaces the *containers* and leaves that volume alone. **Never run `docker compose down -v` on production** — `-v` is the one command that deletes the data.
- Schema changes are migrations (`alembic/versions`), applied automatically when the backend starts (`docker-entrypoint.sh` → `alembic upgrade head`). They are written to **add** (new columns with defaults, new tables), so existing rows are untouched. If you ever need to rename or drop something, do it in two releases (add the new thing and use it → later, remove the old one) — never in one.
- Every start also runs `python -m app.db.bootstrap`, which makes sure the built-in roles and **feature flags** exist (new flags added by a release appear in the platform console on their own) and changes nothing that is already there. Flags no longer depend on the demo seed.
- `RUN_SEED` can therefore be `false` in production. (The seed only loads/backfills the demo restaurant; on a database that already has restaurants it does nothing harmful, but there's no reason to run it.)
- Uploaded files are in object storage (R2) in production, not in the container, so a rebuild doesn't lose them (`STORAGE_BACKEND=s3`).
- `scripts/deploy.sh prod` takes a fresh database backup **before** changing anything and stops if the backup fails. The nightly job (see Backups) is the second safety net.

### The release flow
Two long-lived branches: **`dev`** is where changes are tried and what QA runs; **`main`** only ever holds versions that already worked on QA, and it is what production runs. If something is broken it shows up on QA, and `main` stays good. Deploys are **manual** — nothing goes anywhere just because you pushed or merged.

1. **Build on `dev`** (directly for small things, or on a branch such as `feature/split-bills` merged into `dev` through a pull request). CI runs on every push and pull request (lint, types, backend tests under both database roles, frontend tests and build, production image build) — wait for it to go green.
2. **Try it on QA**: GitHub → **Actions → Deploy → Run workflow** → environment `qa` (version blank = the latest `dev`; or any branch, tag or commit — QA is the test bench). On the server the same thing is `scripts/deploy.sh qa`. Test at `*.qa.dineflow.io`; the run summary and the script's last line show the database revision.
3. **Promote**: when QA looks right, open a pull request **`dev` → `main`** (CI runs again on it) and merge it. Now `main` contains exactly what you tested.
4. **Deploy to production**: Actions → Deploy → Run workflow → environment `prod` (blank = the latest `main`, or a tag you made). The workflow refuses a commit that isn't on `main` or whose CI run didn't pass. With required reviewers on the `prod` environment (Settings → Environments → prod) it also waits for an Approve click. The server takes a database backup first and stops if the backup fails.
5. **Tag it**: `git tag v1.4.0 && git push --tags` (on `main`), so there is always a named version to go back to.

A hotfix for a live problem: branch from `main`, fix, merge into `main` (CI must pass), deploy to prod, then merge `main` back into `dev` so the fix isn't lost.

**Protect `main`** (GitHub → Settings → Branches → Add rule for `main`): require a pull request before merging, require the status checks *Backend tests*, *Frontend tests & build* and *Production Docker build* to pass, and block force-pushes and deletion. Then nothing untested can reach production's branch, even by accident.

### One-time setup (QA on the production server)
1. **DNS (Cloudflare, "DNS only")**: A records for `qa`, `*.qa` and `api.qa` (under `dineflow.io`) → the same server IP as production. (`*.dineflow.io` does *not* cover `x.qa.dineflow.io` — a wildcard matches one label.) The Cloudflare token already in production's `.env` can issue the certificates.
2. **Proxy**: the QA blocks are already at the bottom of `caddy/Caddyfile`. They only take effect when production's Caddy reloads: `docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile` (graceful — no downtime). Until QA is running those addresses answer 502; production is unaffected.
3. **QA config**: `cp .env.qa.example .env.qa` and fill it in with **new** secrets (never production's), Stripe *test* keys, and `EDGE_NETWORK` set to production's Docker network (`docker network ls` — usually `dineflow_dineflow`).
4. **Stripe test mode**: a separate webhook endpoint `https://api.qa.dineflow.io/api/v1/webhooks/stripe` (and the Connect one) with its own signing secrets in `.env.qa`.
5. **First start**: `scripts/deploy.sh qa`. Then (optional) the GitHub secrets `QA_HOST`, `QA_USER`, `QA_SSH_KEY`, `QA_PATH` and the `PROD_*` equivalents so the Deploy workflow can reach the server; without them it fails with a message naming what's missing.

### Sharing one server safely
- **Memory**: QA containers are capped (database 384 MB, API 640 MB, web 512 MB) so a runaway test can't starve production. A small server (4 GB) is enough for both, but add swap if it isn't already (`free -h`; `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`). If memory is tight, simply stop QA when you're not testing: `docker compose -f docker-compose.qa.yml --env-file .env.qa stop`.
- **Builds** compete with production for CPU for a few minutes: deploy QA outside peak service hours.
- **Isolation**: QA's database has no route to production's, uses different credentials, and only QA's web and API containers join production's network. QA's services have unique names (`qa-backend`, `qa-frontend`, `qa-postgres`) on purpose — Docker registers a service name as a DNS alias, and a clash with production's `backend`/`frontend` would send real customers to QA.
- **Data**: QA starts with demo data (`RUN_SEED=true`). Don't copy production's database into QA — it contains real customers' emails and password hashes.

### Rolling back
A bad release is rolled back in two parts — the code and, only if needed, the data:
1. **Code**: `scripts/deploy.sh prod <previous-tag-or-commit>`. Because migrations only add columns/tables, the previous code runs fine against the newer schema; most rollbacks stop here.
2. **Data** (only if a migration or bug damaged rows): restore the backup the deploy took just before it (`backups/dineflow-<time>.sql.gz`) with `scripts/restore-db.sh` as described under Restoring — scratch database first, live only with `FORCE_LIVE=1`.

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
scripts/backup-and-upload.sh                            # backup-db.sh, then upload to R2 under backups/, then prune anything past RETENTION_DAYS (default 14) — both locally and in R2
scripts/backup-drill.sh                                # back up, restore into a throwaway DB, compare every table's row count
```
- **Scheduled on production** — root's crontab on the Hetzner box runs `backup-and-upload.sh` nightly at 03:17 UTC, logging to `/var/log/dineflow-backup.log`. It reads `S3_*` straight from `.env` — the same R2 bucket/credentials already used for file storage, just a different prefix (`backups/` vs whatever uploads use).
- **R2's IP-filtered token needs both addresses on its allow-list** if the token is IP-restricted: the server prefers IPv6 for outbound connections by default, so an IPv4-only allow-list causes a confusing `AccessDenied` on every upload. Check `curl -s https://ifconfig.me` on the box for its current outbound address if this ever recurs (e.g. after a server rebuild).
- **Run the drill regularly** — an untested backup is a hope, not a backup. It only reads the live database.
- Backup files contain personal data (emails, password hashes). `backups/` is git-ignored; encrypt them at rest off-site (R2 encrypts at rest by default).

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

## Custom domains (DNS-verified)
A restaurant can point its own domain at the platform (`order.theirrestaurant.com`) — set it from the restaurant's own **Settings** page or when creating it on `/platform`. It must look like a real domain and be unique across restaurants; the database itself enforces the uniqueness (`uq_restaurants_custom_domain`), so a race between two admins can't both claim the same one.

A platform admin verifies it from `/platform` (or `POST /platform/restaurants/{id}/verify-domain`), which now does a real check (`app/services/domain_verification.verify_dns`): the domain must currently resolve (via the stdlib's own resolver) to at least one of the same addresses `PLATFORM_DOMAIN` does — the same "point your DNS here" contract the Settings page already describes to restaurant owners. A domain that doesn't resolve, or resolves somewhere else, is refused with a 400, not silently marked verified. Changing the domain clears the verified status, so a stale "Verified" badge never survives a domain change.

This is a points-here check, not a domain-*ownership* proof (a TXT-record challenge-response would be that) — good enough to decide whether the platform can actually serve that domain's traffic. In local dev `PLATFORM_DOMAIN=localhost`, so this check can never pass until a real `PLATFORM_DOMAIN` is set for a real deployment (same prerequisite as TLS/reverse-proxy, still outstanding — see the roadmap).

## Home page content
A restaurant's own home page (`/`) shows, only when set: a photo **gallery** (`Restaurant.gallery`, uploaded via `POST /admin/uploads/gallery-image` then attached with `PATCH /admin/settings`, up to 20 photos — mirrors the logo upload pattern, including cleaning up the stored file when a photo is removed), an **about us** paragraph (`about_text`), **social links** (`social_links`, restricted to `instagram`/`facebook`/`twitter`/`tiktok`/`youtube`) and a **visit us** block (address, phone, email, a full weekly hours list with today bolded). With `latitude`/`longitude` set, that block embeds an interactive OpenStreetMap (no API key — `https://www.openstreetmap.org/export/embed.html`, a public no-auth embed); without coordinates it just shows the address text and a "Get directions" link to a Google Maps search (also no API key needed for a link, just a URL). All of this is edited from the restaurant's own Settings page ("Home page" section) — there's no separate content-management screen.

With gallery photos set, the hero becomes a full-bleed crossfade slideshow (Ken Burns zoom, dot navigation) instead of the plain gradient, with the copy and buttons on a frosted-glass card and a "Gallery" pill in the corner linking to `/gallery` — a separate page with an editorial grid and a lightbox, so the home page never repeats the photos. A "Popular dishes" section pulls `is_popular` menu items automatically — no separate setting, just tag dishes popular from the menu editor. The "Visit us" band puts the details on a glass card over a full-bleed map; that map is deliberately non-interactive (`pointer-events-none`) so scrolling the page is never caught by it, with "Get directions" as the way into real maps. Every one of these sections (and the service-highlights bar: dine-in/pickup/delivery + today's hours) only renders when there's content for it, so a freshly created restaurant's home page looks exactly like it always has until its owner fills something in. Sections fade in on scroll (`v-reveal`, `app/plugins/reveal.ts`) — a one-time IntersectionObserver-driven animation that respects `prefers-reduced-motion` and never causes a hydration mismatch (the animation class is only ever added client-side, after hydration).

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

## Allergens (menu compliance)
Every dish has an `allergens` list — tag it in **Menu → Add/Edit item** against the 14 UK/EU
declarable allergens (`backend/app/core/allergens.py`; the frontend's copy is
`frontend/app/utils/allergens.ts` — codes must match exactly). Customers see a "Contains: …" line on
the menu, the item card and the item page, and can open **Hide dishes containing…** on `/menu` to
filter out anything tagged with the allergens they pick (`GET /api/v1/menu?exclude_allergens=milk&…`,
repeatable). The kitchen ticket shows a red "Contains: …" line per dish too — copied from the dish
**at order time** (same reasoning as the dish's station), so changing a menu item's allergens later
never rewrites a ticket already sitting on a screen.

## Live updates (customers and guests)
Besides the kitchen screen, a signed-in customer's order page (`GET /api/v1/orders/{id}/stream`, owner only) and a table's guests (`GET /api/v1/table-session/stream`, table pass only) follow their order over the same SSE channel. Status changes, new rounds and closing a tab reach them immediately; the pages also re-fetch every 30–60 s in case the connection dropped. Each open stream counts toward `REALTIME_MAX_STREAMS`.

## QR table ordering
Switch it on per restaurant: `python -m app.cli features <slug> qr_table_ordering on`. Then, in the admin area, open **Table ordering** *from the restaurant's own address* (the printed codes use the address you are on): **Print table tents** prints one card per table with the restaurant's logo and a QR code. Put the cards on the tables.
- **How a table works:** a guest scans the code → by default ordering is open only while staff have marked the table **Occupied** (Tables page) → the guest starts a shared tab (name optional), picks dishes and taps *Send to kitchen*. Each send is a round that shows on the kitchen screen as a table order. Everyone at the table sees the same tab and total.
- **Waiter and bill:** on the *Our table* tab a guest can tap **Call a waiter** or **Ask for the bill** (the bill needs at least one round). Staff see these at the top of the **Table ordering** page under *Waiting for you*, with a count badge on that menu item on every admin page, and tap **Done** when handled; the guest's button resets by itself. Tapping twice is one request. Closing a tab clears its requests.
- **Paying the tab**: a guest can tap **Pay now** at any time once the total is above zero — no need to ask for the bill first. Under `PAYMENT_PROVIDER=stripe`, this is a real charge on the restaurant's own connected account, same Payment Element and webhook-confirmation flow as online checkout (see *Payments* below) — the tab closes once the webhook lands, not when the browser thinks it's done. Staff can also mark a tab **paid (cash)** from the waiter view for a counter payment; no Stripe involvement, closes immediately. Either way, one real payment is one `Payment` row (`table_session_id` set, `order_id` empty) — not split across the rounds it covers.
- **Closing:** when the party leaves without a recorded payment (walked out, comped), click **Close tab & clean table** (Table ordering page) — this alone doesn't touch payment status. Guest phones stop working, the table goes to *Cleaning*, and its QR code is replaced, so a photo of the old code is useless. **Replace code** does the same for one table without closing anything (lost tent, suspected abuse); reprint afterwards.
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

## Booking pacing and table combining
**Pacing**: a restaurant can cap total covers (summed party sizes) arriving in the same 15-minute slot (`max_covers_per_slot`, Settings → Reservations) — independent of table availability, so the kitchen doesn't get flooded even when there happen to be enough free tables. Enforced on guest availability/booking only; staff bypass it like every other guest-facing policy.

**Table combining**: a staff booking for a party too big for one table can carry `extra_table_ids` (on `/admin/reservations`, pick "Combine with other tables" once a table is selected). It's stored as JSONB on the reservation (no FK, same pattern as `Restaurant.closures`) and validated in the service on every write. Overlap checks, floor-status derivation (`RESERVED`/`OCCUPIED`) and the table-detail listing all treat a reservation as occupying its primary table *and* every combined one — see `ReservationService._table_match`. Guest self-service bookings are always a single table.

## Embeddable booking widget
`/embed/reserve` is a compact, chrome-free version of `/reserve` meant to be put in an `<iframe>` on a restaurant's own external site (Squarespace, WordPress, …) — same search → pick → confirm flow, minus the site nav and booking history. Signing in opens `/login` in a new tab so a small iframe never has to host a full page. It's the only route allowed to be framed: `nuxt.config.ts` sends `X-Frame-Options: DENY` and no `Content-Security-Policy` everywhere else, but `/embed/**` sends `Content-Security-Policy: frame-ancestors *` instead (CSP `frame-ancestors` is what lets *any* origin embed it — `X-Frame-Options` alone can't express "any origin", only none/same-origin/one named origin). Tighten `frame-ancestors` to the tenant's own domain(s) before this matters for a real client.

## Guest profiles
**Customers** (admin sidebar) lists every registered customer of the restaurant, not only those who have ordered — someone who has only booked a table, or who has just signed up, shows up too, since a customer account already lives in that restaurant's own table (`users.restaurant_id`). "Last seen" is the more recent of their last order and last booking. Open a customer to see their order and booking history and set **notes**, **allergies** and a **VIP** tag — staff-only, never shown to the guest. A customer's own account page has no access to this (`GET`/`PATCH /admin/customers/{id}` are staff routes).

## Reviews (flag: `reviews`)
A customer rates one completed order or booking out of five, with an optional comment — one review per visit; sending it again edits the existing one. **Reviews** (admin sidebar) lists everything with the reviewer's name and email: **Hide** takes a review off the site, **Reply** adds a public answer under it. Reviews are published by default, so hide is a correction, not a gate.

`/reviews` on the restaurant's site is public: any visitor reads every published review and the average. A signed-in customer also sees their own completed visits waiting to be rated, and their own reviews, above that shared list. A hidden review is still shown to the person who wrote it, marked "Only visible to you", so they aren't left wondering where it went. The home page carries the six most recent, with a link through. Reviewers appear publicly as a first name and last initial ("Sam T.") — never the full name or email.

## Loyalty points (flag: `loyalty`)
Points are credited when an order is marked **COMPLETED**, at **Settings → Loyalty → points per $1** (default 1), floored to whole points off the order total. They are credited once per order — enforced by a unique constraint, not just by care — and an order placed by a table guest with no account earns nothing. Turning the flag on does **not** backdate: orders already completed stay at zero, because points are credited at the moment of completion.

Customers see their balance and history at `/loyalty` ("Points" in the site header). **Loyalty** (admin sidebar) lists balances, most points first, and lets staff adjust one by hand for goodwill or to fix a mistake — a deduction can't take a balance below zero, and every change is a row in the ledger, so the balance can always be explained.

## Discount codes (flag: `coupons`)
**Discount codes** (admin sidebar, admin only) creates a code that is either a percentage or a fixed amount off, optionally with a minimum order, a cap on what a percentage can take off, a last day, a total number of uses and a limit per customer. Codes are stored upper-cased, so `save10` and `SAVE10` are the same code and customers can type either.

The customer enters it at checkout and sees what it is worth before paying. **The amount is never taken from the request** — only the code is sent, and the discount is worked out on the server from its own subtotal, coming off *before* tax and capped at the subtotal (so a code can reduce a bill to zero but never pay anything out; a zero-total order skips the payment gateway and records a `0.00` payment). A "first N customers" cap is checked under a database row lock, so two people checking out at the same moment can't both take the last use.

**Retire** a code that has been used rather than deleting it — past orders keep their history. An unused code is deleted outright.

## Ordering ahead and order capacity
**Settings → Order capacity** holds two things that work whether or not any flag is on:
- **Pause online ordering** stops new customer orders and shows them the message you set ("we're extremely busy tonight"). Staff can still put an order in for a guest.
- **Pause automatically at this many open orders** does the same once the kitchen has that many orders still open. Leave it empty for no limit.

With the **`scheduled_orders`** flag on, checkout also offers **Order ahead**: the customer picks a day and a collection time. Slots come from the restaurant's own opening hours, so there is nothing separate to keep in step — set the hours and the slots follow. **Settings → Ordering ahead** controls the slot length, how many orders each slot takes, how many days ahead you accept orders, and how long before the collection time the kitchen should see the ticket.

Two behaviours worth knowing:
- A customer **can order ahead while you are closed** — the slot itself proves you are open then, which is the point of pre-ordering. Ordering for *now* still requires you to be open.
- A scheduled order **stays off the kitchen screen** until it is within the lead time, so the board shows what to cook now, not everything booked for the week. Once staff start it, it stays on the board. The board is ordered by when food is wanted rather than when it was ordered, and the admin order list badges anything that is for later.

A pause stops pre-orders too — "stop taking orders" means that. The automatic busy cap does not, since a slot next Tuesday isn't in tonight's queue.

## Payments (Stripe Connect)

**Setting up a test-mode Stripe account** (see ROADMAP for why Connect, and the "direct charge" design):
1. Create a free account at stripe.com — no business verification needed for test mode. Keep **Test mode**
   switched on (orange badge, top right).
2. **Connect → Get started** (or **Connect → Settings**), choose "Platform or marketplace" — this switches
   Connect on for your platform account. You don't need to finish your own onboarding.
3. **Developers → API keys**: copy the test **Publishable key** (`pk_test_...`) and **Secret key**
   (`sk_test_...`).
4. Set in `.env`: `PAYMENT_PROVIDER=stripe`, `STRIPE_SECRET_KEY=sk_test_...`,
   `NUXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...` (same value as `STRIPE_PUBLISHABLE_KEY`, just also
   read by the frontend), then restart the backend and frontend containers.
5. **Two separate webhook secrets** — these are genuinely different Stripe subsystems, each with its own
   signing secret:
   - `STRIPE_WEBHOOK_SECRET` (v1, order confirmation). For local development, install the Stripe CLI and
     run `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe` — it prints a `whsec_...`
     secret. In production, register the URL in the Stripe dashboard (**Developers → Webhooks**) for
     `payment_intent.succeeded` and `payment_intent.payment_failed`, with "Listen to events on Connected
     accounts" switched on (a restaurant's own charges are events on *its* connected account, not the
     platform's), and use the signing secret it gives you.
   - `STRIPE_CONNECT_WEBHOOK_SECRET` (v2, Connect account status). Accounts v2 uses a separate resource
     called an **event destination**, not the classic webhook endpoint above. Create one (Dashboard:
     **Developers → Event destinations**, or `stripe.StripeClient(...).v2.core.event_destinations.create`)
     with `event_payload: "thin"`, `events_from: ["@self"]`,
     `enabled_events: ["v2.core.account[configuration.merchant].capability_status_updated"]`, pointing at
     `.../api/v1/webhooks/stripe/connect`. It has its own signing secret — put that in
     `STRIPE_CONNECT_WEBHOOK_SECRET`.

**Connecting a restaurant**: Settings → Payments → *Connect with Stripe*. This redirects to a
Stripe-hosted onboarding form (an Accounts v2 account with `dashboard: "full"` — the restaurant manages
it directly at dashboard.stripe.com; not the deprecated v1 `type: 'express'`) and back.
`dashboard: "express"` would be a lighter, DineFlow-branded dashboard, but that combination is currently
public-preview and returned `This account configuration is not supported` when tried — worth revisiting
once confirmed available. Nothing is enabled until
the `v2.core.account[configuration.merchant].capability_status_updated` event confirms it —
`stripe_charges_enabled` on the restaurant, shown as "Connected" on that same page. That event is a
**thin** payload (an id and a URL, not the account's data), so the handler always fetches the current
account before syncing anything — see `webhooks.py`'s docstring. If onboarding is abandoned partway,
the button becomes "Finish connecting with Stripe" and reuses the same account.

**Identity verification in test mode is not a rubber stamp.** `dashboard: "full"` hosted onboarding runs
real-shaped identity checks even with fake data — a plausible-looking name, SSN and address that don't
actually match each other **fails** and demands a government-ID document upload, exactly like
production. Use Stripe's own magic test values instead so it verifies immediately:
- Date of birth: `1902-01-01` (immediate successful match; `1901-01-01` also matches but isn't instant)
- SSN: `000000000` (full) or `0000` (last 4)
- Address line 1: `address_full_match` (yes, type that literal string)
- If it still asks for a document: upload Stripe's dedicated always-passes test ID image —
  `https://d37ugbyn3rpeym.cloudfront.net/docs/identity/success.png` — instead of any real photo.

Because the account was created with `identity.country: "US"` (see the code comment in
`stripe_connect_service.py` — there's no `Restaurant.country` field yet, so this is hardcoded), keep the
country as US throughout the onboarding form; a mismatched country/address is one of the realistic ways
this verification genuinely fails, not a bug.

**Checkout**: `POST /orders` returns a `client_secret` whenever a real payment still needs confirming
(a positive total, `PAYMENT_PROVIDER=stripe`) — the order already exists as `PENDING`. The checkout page
mounts a Stripe Payment Element for it and confirms the charge directly with Stripe; the order itself is
flipped to `CONFIRMED` by the `payment_intent.succeeded` webhook, not by the browser, so a customer
closing the tab mid-payment can't leave an inconsistent state — the webhook is the only thing that ever
confirms an order once a real provider is in use. Test cards: `4242 4242 4242 4242` (succeeds, any future
expiry/any CVC), `4000000000000002` (declined), `4000002500003155` (requires 3D Secure — the Payment
Element handles the challenge itself).

**Worth knowing:**
- `PAYMENT_PROVIDER` defaults to `mock` (always succeeds instantly, no Stripe involved at all) —
  every automated test runs against this, never against Stripe. `assert_production_ready()` refuses to
  boot a production deployment with `PAYMENT_PROVIDER=mock`.
- A **failed** payment leaves the order `PENDING` rather than cancelling it, so the customer can retry;
  there is currently no UI to retry the *same* order from a reload, only to place a new one (a known gap,
  not yet a problem while the failure rate is Stripe's test-mode declined-card scenarios only).
- **Cancelling an order now refunds it.** The admin order page's *Cancel order* button (previously
  didn't exist at all — cancelling was only reachable by API) refunds a completed payment in full, or
  cancels the PaymentIntent if it hadn't finished confirming yet, so a stray later confirmation can't
  still charge the card. A refund on a *direct* charge is created in the connected account's own
  context (`stripe_account` on the request), same as the original charge — easy to miss.
- **Refunding a table's whole tab exists at the API level** (`POST
  /admin/table-sessions/{id}/refund`) but isn't wired into any admin page yet — there's currently no
  page listing *past* (closed) table sessions to reach it from. Revisit alongside a session-history page.
- **Dine-in revenue is no longer invisible** — `today_revenue` and the revenue trend
  now count table-session payments too, filtered on `Payment`'s own `restaurant_id`/`created_at` rather
  than joined through `Order` (a table-session payment has no `order_id` to join through at all).
- `STRIPE_SECRET_KEY` here is a full secret key (`sk_test_...`/`sk_live_...`) for simplicity while
  building. Before real money moves, switch to a [restricted key](https://docs.stripe.com/keys.md#manage-your-api-keys)
  (`rk_live_...`) scoped to only the resources this app actually calls (PaymentIntents, and the v2
  Accounts/Account Links/Event Destinations) — a leaked restricted key can't do anything outside that
  scope, a leaked secret key can do everything on the account.
- **Pay-at-table doesn't exist yet** (Sprint 4 Phase 3) — `table_session_service.py` has no payment
  concept, so dine-in orders placed from a QR table session still report zero revenue.

## Staff management
**Staff** (admin sidebar, admin only) invites someone by email, first/last name and role (Admin or
Staff). It reuses the same invite-link mechanism as an owner's own account: a hashed, single-use, 7-day
link is emailed, and setting a password on it is what "accepts" the invite (shown as **Invite
pending** until then). An email that already belongs to a staff/admin account elsewhere is *reused*,
not duplicated — the same person can work at more than one restaurant on one login.

Deactivating someone removes their access to *that* restaurant immediately (checked on their very next
request, no need to wait for a token to expire) without touching their login elsewhere. Two rails stop
you locking a restaurant out of itself: you can't remove your own admin access, and you can't leave a
restaurant with zero active admins.

Promoting someone to Admin takes effect immediately, everywhere. Demoting them only takes away their
access *at that restaurant* — their account-wide role does not automatically step down, because a
request is already scoped to one restaurant by the time this runs (row-level security), so there is no
safe way to check whether they're still an admin somewhere else. This is a known, documented seam, not
a bug — see `restaurant_user.py`'s docstring if it ever needs revisiting.

## SEO, social sharing and legal pages
Every page gets a description, Open Graph/Twitter tags, and a canonical URL from the restaurant's own
`description`/`about_text` (`app.vue`). The home page also carries `Restaurant` JSON-LD structured
data — hours, address, phone — for search engines. `frontend/public/` holds the fallback favicon and a
default share image, used only when a restaurant hasn't turned on `custom_branding` or set a gallery
photo. `/terms`, `/privacy` and `/cookies` are generic placeholder pages, linked from the footer — meant
to be replaced with a client's own reviewed copy before it matters for a real launch.

**Worth knowing:** any URL that ends up in rendered markup (an image, the favicon, a share-image) must
be built with `resolveMediaUrl`/`getPublicApiBaseUrl()`, never `getApiBaseUrl()` directly — the latter
is for the Nuxt server's *own* outgoing requests only (it may point at an internal Docker hostname the
browser can't reach). Mixing the two up is exactly how every image on the site was silently broken in
the server-rendered HTML until client-side hydration repainted it — see ROADMAP.md §4.2 if it recurs.

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
The catalog (key, description, default) lives in the database (`Feature` model), not in code — a platform admin manages it from **`/platform/features`**: create a flag, delete one, and pick a restaurant to toggle its flags On/Off/Default. The 9 flags DineFlow originally shipped with (`reservations`, `qr_table_ordering`, `pay_at_table`, `kitchen_v2`, `custom_branding`, `reviews`, `loyalty`, `coupons`, `scheduled_orders`) are seeded idempotently by `FeatureService.ensure_defaults()` (same pattern as `RoleRepository.ensure_defaults()`), called from `db/seed.py` — not inserted by a migration, since these rows are meant to be edited/deleted afterward.

**The tradeoff of a DB-backed catalog**: creating a flag from the screen alone does *nothing* — nothing in the app checks it until a developer adds a `requires_feature(key)` (or `FeatureService(db).require(...)`) call somewhere. And there's no code list left to validate a key against, so an unknown key now resolves as **off** rather than raising — fail closed, never a crash, but also nothing to point at why a check is silently always denying. **Always create the DB flag before shipping a new `requires_feature(key)` check, never after** — and be careful deleting a flag from the screen if you're not sure something in code still checks it.

A restaurant can deviate from a flag's default; every change (create, delete, set, reset) is audited.
```sh
docker compose exec backend python -m app.cli features bella-vista-kitchen                 # list the flags
docker compose exec backend python -m app.cli features bella-vista-kitchen kitchen_v2 on   # on | off | default
docker compose exec backend python -m app.cli audit bella-vista-kitchen                    # who changed what
```
The same is available to platform admins over the API (`/api/v1/platform/features` for the catalog, `/api/v1/platform/restaurants/{id}/features` for one restaurant's overrides). Turning a flag off blocks the API for that restaurant only and hides the UI for it.

## Still to do (roadmap stage A1/A2)
Off-site backup automation, a staging environment, Redis-backed rate limiting.
