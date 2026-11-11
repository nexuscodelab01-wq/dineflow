#!/bin/sh
# Deploy the checked-out code to this server's stack, safely. Run it ON the server, in the repo.
#
#   scripts/deploy.sh qa            # QA: pull, build, start, check health
#   scripts/deploy.sh prod          # production: same, but takes a database backup FIRST and stops if it fails
#   scripts/deploy.sh prod v1.4.0   # deploy a specific tag/branch/commit instead of the latest main
#
# What protects the data: the database lives in a named Docker volume that `up --build` never touches (only `down -v`
# deletes it — never use that on production), migrations only ever ADD (the app runs `alembic upgrade head` on start),
# and production gets a fresh backup before anything changes. If something is wrong afterwards see "Rolling back" in
# docs/OPERATIONS.md.
set -eu

ENV_NAME="${1:-}"
REF="${2:-origin/main}"
cd "$(dirname "$0")/.."

case "$ENV_NAME" in
  qa)   COMPOSE="docker compose -f docker-compose.qa.yml --env-file .env.qa"; COMPOSE_FILE=docker-compose.qa.yml ;;
  prod) COMPOSE="docker compose -f docker-compose.prod.yml"; COMPOSE_FILE=docker-compose.prod.yml ;;
  *) echo "usage: scripts/deploy.sh <qa|prod> [git-ref]" >&2; exit 2 ;;
esac

if [ "$ENV_NAME" = "prod" ] && [ "${CONFIRM_PROD:-}" != "yes" ]; then
  printf 'Deploy %s to PRODUCTION? Type "deploy" to continue: ' "$REF"
  read -r answer
  [ "$answer" = "deploy" ] || { echo "Cancelled."; exit 1; }
fi

BEFORE=$(git rev-parse --short HEAD)
git fetch --tags origin
git checkout --quiet "$REF" 2>/dev/null || git checkout --quiet --detach "$REF"
[ "$REF" = "origin/main" ] && git merge --quiet --ff-only origin/main 2>/dev/null || true
AFTER=$(git rev-parse --short HEAD)
echo "Deploying $AFTER (was $BEFORE) to $ENV_NAME"

if [ "$ENV_NAME" = "prod" ]; then
  echo "Backing up the database before changing anything..."
  COMPOSE_FILE="$COMPOSE_FILE" ./scripts/backup-db.sh
fi

$COMPOSE up --build -d

echo "Waiting for the API to report ready (it runs migrations first)..."
i=0
until $COMPOSE exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=3)" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 40 ]; then
    echo "The API did not become ready. Recent logs:" >&2
    $COMPOSE logs --tail=60 backend >&2
    echo "Previous version was $BEFORE — see 'Rolling back' in docs/OPERATIONS.md." >&2
    exit 1
  fi
  sleep 5
done

echo "Database is at: $($COMPOSE exec -T backend alembic current 2>/dev/null | tail -1)"
echo "Deployed $AFTER to $ENV_NAME."
