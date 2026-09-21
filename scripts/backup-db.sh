#!/bin/sh
# Dump the PostgreSQL database to a compressed, timestamped file.
#
#   scripts/backup-db.sh                       # dev stack  -> backups/dineflow-<time>.sql.gz
#   COMPOSE_FILE=docker-compose.prod.yml scripts/backup-db.sh
#
# Prints the path of the backup on success. Schedule this (cron / CI) and copy the files
# OFF the server (object storage) — a backup on the same disk is not a backup.
set -eu

cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
OUT_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$OUT_DIR"

FILE="$OUT_DIR/dineflow-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

# --clean/--if-exists make the dump restorable over an existing database; --no-owner keeps it
# portable between environments with different database roles.
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists' \
  | gzip > "$FILE"

gzip -t "$FILE"                       # the archive itself is intact
[ "$(wc -c < "$FILE")" -gt 1024 ] || { echo "Backup is suspiciously small: $FILE" >&2; rm -f "$FILE"; exit 1; }
echo "$FILE"
