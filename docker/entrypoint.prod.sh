#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."

python <<'PYEOF'
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2

url = urlparse(os.environ["DATABASE_URL"])

for _ in range(30):
    try:
        conn = psycopg2.connect(
            dbname=url.path.lstrip("/"),
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port or 5432,
            connect_timeout=3,
        )
        conn.close()
        print("PostgreSQL is ready.")
        sys.exit(0)
    except psycopg2.OperationalError:
        time.sleep(1)

print("Database unavailable.", file=sys.stderr)
sys.exit(1)
PYEOF

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."

exec gunicorn racine.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers=3 \
    --timeout=120