#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for PostgreSQL..."
until python -c "
import os, sys
import psycopg2
url = os.environ.get('DATABASE_URL', '').replace('+asyncpg', '')
if not url:
    sys.exit(1)
conn = psycopg2.connect(url.replace('postgresql+asyncpg', 'postgresql'))
conn.close()
" 2>/dev/null; do
  sleep 2
done

echo "Running Alembic migrations..."
cd /app
alembic -c backend/db/migrations/alembic.ini upgrade head

echo "Starting uvicorn..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
