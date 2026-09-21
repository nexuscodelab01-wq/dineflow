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
