#!/usr/bin/env bash
set -euo pipefail

APP_NAME="lean-logistics-dashboard"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${BACKUP_DIR}"

if [ -f /etc/lean-logistics-dashboard.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/lean-logistics-dashboard.env
  set +a
fi

if [ -n "${DATABASE_URL:-}" ] && [[ "${DATABASE_URL}" == postgres* ]]; then
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump "${DATABASE_URL}" > "${BACKUP_DIR}/lean-logistics-${STAMP}.sql"
    echo "${BACKUP_DIR}/lean-logistics-${STAMP}.sql"
  else
    cat > "${BACKUP_DIR}/lean-logistics-${STAMP}.postgres-manifest.json" <<JSON
{"created_at":"${STAMP}","database_backend":"postgresql","note":"pg_dump is not installed on this host."}
JSON
    echo "${BACKUP_DIR}/lean-logistics-${STAMP}.postgres-manifest.json"
  fi
else
  if [ -f "${APP_DIR}/lean_logistics.db" ]; then
    cp "${APP_DIR}/lean_logistics.db" "${BACKUP_DIR}/lean_logistics-${STAMP}.db"
  else
    : > "${BACKUP_DIR}/lean_logistics-${STAMP}.db"
  fi
  echo "${BACKUP_DIR}/lean_logistics-${STAMP}.db"
fi
