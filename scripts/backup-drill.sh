#!/bin/sh
# Prove the backups work: back up, restore into a throwaway database, and compare row counts.
# Safe to run any time — it only reads the live database. Exits non-zero if anything differs.
#
#   scripts/backup-drill.sh              # dev stack
#   KEEP=1 scripts/backup-drill.sh       # keep the backup file afterwards
set -eu

cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SCRATCH="dineflow_drill_$$"
PSQL="docker compose -f $COMPOSE_FILE exec -T postgres"

FILE="$(scripts/backup-db.sh)"
echo "1/3 backup written: $FILE ($(wc -c < "$FILE") bytes)"
trap '$PSQL sh -c "psql -q -U \"\$POSTGRES_USER\" -d postgres -c \"DROP DATABASE IF EXISTS \\\"$SCRATCH\\\"\"" >/dev/null 2>&1 || true; [ "${KEEP:-0}" = "1" ] || rm -f "$FILE"' EXIT

scripts/restore-db.sh "$FILE" "$SCRATCH" >/dev/null
echo "2/3 restored into scratch database '$SCRATCH'"

# Exact row count of every table, in one query per database (no per-table loop to go wrong).
ROWS_SQL="SELECT table_name || '=' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
count_rows() {
  $PSQL sh -c "psql -At -U \"\$POSTGRES_USER\" -d \"$1\" -c \"$ROWS_SQL\""
}
LIVE_DB="$($PSQL sh -c 'printf %s "$POSTGRES_DB"')"
count_rows "$LIVE_DB" > /tmp/drill-live.$$
count_rows "$SCRATCH" > /tmp/drill-restored.$$
[ "$(wc -l < /tmp/drill-live.$$ | tr -d " ")" -ge 5 ] || { echo "DRILL FAILED: found too few tables to be meaningful" >&2; exit 1; }
if diff -u /tmp/drill-live.$$ /tmp/drill-restored.$$; then
  echo "3/3 row counts match across $(wc -l < /tmp/drill-live.$$ | tr -d ' ') tables — restore verified"
  rm -f /tmp/drill-live.$$ /tmp/drill-restored.$$
else
  rm -f /tmp/drill-live.$$ /tmp/drill-restored.$$
  echo "DRILL FAILED: restored data differs from the live database" >&2
  exit 1
fi
