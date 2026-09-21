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
Off-site backup automation, a staging environment, Redis-backed rate limiting, object storage for uploads, transactional email.
