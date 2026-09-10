#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/eccops/apps/ecc2026"
LOG_PREFIX="[ECC SSL RENEW]"
DOCKER_BIN="/usr/bin/docker"
LOCK_FILE="/tmp/ecc-certbot-renew.lock"

exec 9>"${LOCK_FILE}"

if ! flock -n 9; then
  echo "${LOG_PREFIX} Another renewal process is already running. Exit."
  exit 0
fi

cd "${APP_DIR}"

echo "${LOG_PREFIX} Starting certificate renewal..."

${DOCKER_BIN} compose \
  --env-file .env.prod \
  -f compose.prod.yml \
  --profile certificates \
  run --rm certbot renew --quiet

echo "${LOG_PREFIX} Testing Nginx configuration..."

${DOCKER_BIN} exec ecc-shield nginx -t

echo "${LOG_PREFIX} Reloading Nginx..."

${DOCKER_BIN} exec ecc-shield nginx -s reload

echo "${LOG_PREFIX} Renewal check completed successfully."
