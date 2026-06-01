#!/usr/bin/env bash
set -euo pipefail

APP_NAME="lean-logistics-dashboard"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
ENV_FILE="${ENV_FILE:-/etc/lean-logistics-dashboard.env}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SCHEDULE_ID="${1:-nightly_database_backup}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

if [ -z "${ADMIN_API_TOKEN:-}" ]; then
  echo "ADMIN_API_TOKEN is missing; cannot run scheduled admin job." >&2
  exit 1
fi

curl -fsS \
  -X POST \
  -H "Authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H "X-Admin-User: scheduler" \
  -H "Content-Type: application/json" \
  "${BASE_URL}/api/admin/schedules/${SCHEDULE_ID}/run"

echo
