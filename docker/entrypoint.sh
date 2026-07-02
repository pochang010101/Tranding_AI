#!/usr/bin/env bash
set -e

echo "=== Atlas v5.0 Starting ==="

# Wait for PostgreSQL
if [ -n "$ATLAS_DB_HOST" ]; then
    echo "Waiting for PostgreSQL at ${ATLAS_DB_HOST}:${ATLAS_DB_PORT:-5432}..."
    for i in $(seq 1 30); do
        if python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${ATLAS_DB_HOST}', ${ATLAS_DB_PORT:-5432}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "PostgreSQL is ready."
            break
        fi
        echo "  attempt $i/30..."
        sleep 2
    done
fi

# Wait for Redis
if [ -n "$ATLAS_REDIS_HOST" ]; then
    echo "Waiting for Redis at ${ATLAS_REDIS_HOST}:${ATLAS_REDIS_PORT:-6379}..."
    for i in $(seq 1 15); do
        if python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${ATLAS_REDIS_HOST}', ${ATLAS_REDIS_PORT:-6379}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "Redis is ready."
            break
        fi
        echo "  attempt $i/15..."
        sleep 2
    done
fi

# Run Alembic migrations (if alembic.ini exists)
if [ -f "alembic.ini" ] && [ -n "$ATLAS_DATABASE_URL" ]; then
    echo "Running database migrations..."
    python -m alembic upgrade head || echo "  WARNING: Alembic migration failed"
fi

echo "=== Starting application ==="
exec "$@"
