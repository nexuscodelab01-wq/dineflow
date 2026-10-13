#!/bin/sh
# Nightly production backup: dump the database (scripts/backup-db.sh), upload it to the same R2
# bucket used for file storage (under backups/, separate from whatever prefix uploads use), then
# prune local and remote copies older than RETENTION_DAYS — so storage (and cost) never grows
# unbounded. Reads S3_* from .env, the same credentials the app itself uses for file storage.
#
#   COMPOSE_FILE=docker-compose.prod.yml RETENTION_DAYS=14 scripts/backup-and-upload.sh
#
# Meant to run from cron on the production host, in the repo root (where .env lives).
set -eu

cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

: "${S3_BUCKET:?S3_BUCKET must be set (see .env) — same bucket file uploads already use}"
: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL must be set}"
: "${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID must be set}"
: "${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY must be set}"

export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
REGION="${S3_REGION:-auto}"

FILE=$(COMPOSE_FILE="$COMPOSE_FILE" ./scripts/backup-db.sh)
NAME=$(basename "$FILE")

aws s3 cp "$FILE" "s3://$S3_BUCKET/backups/$NAME" --endpoint-url "$S3_ENDPOINT_URL" --region "$REGION"
echo "Uploaded: backups/$NAME"

# Prune local copies older than RETENTION_DAYS — the off-site copy is the real one.
find backups -name 'dineflow-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# Prune remote copies older than RETENTION_DAYS (filenames sort lexically == chronologically,
# dineflow-YYYYMMDDTHHMMSSZ.sql.gz).
CUTOFF=$(date -u -d "-$RETENTION_DAYS days" +%Y%m%dT%H%M%SZ)
aws s3 ls "s3://$S3_BUCKET/backups/" --endpoint-url "$S3_ENDPOINT_URL" --region "$REGION" | awk '{print $4}' | while read -r remote_name; do
  [ -n "$remote_name" ] || continue
  stamp=$(echo "$remote_name" | sed -E 's/dineflow-([0-9TZ]+)\.sql\.gz/\1/')
  if [ "$stamp" \< "$CUTOFF" ]; then
    aws s3 rm "s3://$S3_BUCKET/backups/$remote_name" --endpoint-url "$S3_ENDPOINT_URL" --region "$REGION"
    echo "Pruned old backup: $remote_name"
  fi
done

echo "Backup complete: $NAME"
