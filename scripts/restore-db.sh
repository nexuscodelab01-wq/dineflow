#!/bin/sh
# Restore a backup made by backup-db.sh into a database.
#
#   scripts/restore-db.sh backups/dineflow-20260920T101500Z.sql.gz            # into scratch DB "dineflow_restore"
#   scripts/restore-db.sh <file> some_db                                       # into another scratch DB
#   FORCE_LIVE=1 scripts/restore-db.sh <file> "$POSTGRES_DB"                   # OVERWRITES the live database
#
# Restoring into the live database is deliberately hard: it needs FORCE_LIVE=1 and the exact name.
set -eu

FILE="${1:?usage: restore-db.sh <backup.sql.gz> [target_db]}"
TARGET="${2:-dineflow_restore}"
cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PSQL="docker compose -f $COMPOSE_FILE exec -T postgres"

LIVE_DB="$($PSQL sh -c 'printf %s "$POSTGRES_DB"')"
if [ "$TARGET" = "$LIVE_DB" ] && [ "${FORCE_LIVE:-0}" != "1" ]; then
  echo "Refusing to overwrite the live database '$LIVE_DB'. Set FORCE_LIVE=1 if you really mean it." >&2
  exit 1
fi

gzip -t "$FILE"
if [ "$TARGET" != "$LIVE_DB" ]; then
  $PSQL sh -c "psql -q -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS \"$TARGET\"' -c 'CREATE DATABASE \"$TARGET\"'"
fi
gunzip -c "$FILE" | $PSQL sh -c "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"$TARGET\"" >/dev/null
echo "Restored $FILE into '$TARGET'"
