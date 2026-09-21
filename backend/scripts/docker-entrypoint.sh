#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Preparing the restricted database role (row-level security)..."
python -m app.db.roles

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Seeding database..."
  python -m app.db.seed
fi

echo "Starting API server..."
exec uvicorn app.main:app \
  --host "${BACKEND_HOST:-0.0.0.0}" \
  --port "${BACKEND_PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}" \
  --timeout-graceful-shutdown "${GRACEFUL_SHUTDOWN_SECONDS:-10}"
