#!/bin/sh
set -e

echo "Attente de PostgreSQL..."
python <<'PYEOF'
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2

url = urlparse(os.environ["DATABASE_URL"])
for tentative in range(30):
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
        print("PostgreSQL prêt.")
        sys.exit(0)
    except psycopg2.OperationalError:
        time.sleep(1)
print("Impossible de se connecter à PostgreSQL après 30 tentatives.", file=sys.stderr)
sys.exit(1)
PYEOF

echo "Application des migrations..."
python manage.py migrate --noinput

echo "Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

echo "Démarrage du serveur..."
# Phase 0 (dev/portabilité) : runserver suffit. La Phase 3 (mise en
# production réelle) passera à gunicorn + un service statique dédié
# (whitenoise ou Nginx) — pas nécessaire tant que le frontend n'est pas
# séparé.
exec python manage.py runserver 0.0.0.0:8000
