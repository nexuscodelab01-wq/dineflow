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

## Still to do (roadmap stage A1/A2)
Off-site backup automation, a staging environment, Redis-backed rate limiting, object storage for uploads, transactional email, a job runner.
