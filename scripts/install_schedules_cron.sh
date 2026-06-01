#!/usr/bin/env bash
set -euo pipefail

APP_NAME="lean-logistics-dashboard"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
CRON_FILE="/etc/cron.d/${APP_NAME}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root: sudo bash scripts/install_schedules_cron.sh"
  exit 1
fi

cat > "${CRON_FILE}" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 2 * * * root APP_DIR=${APP_DIR} ${APP_DIR}/scripts/run_scheduled_job.sh daily_usaid_import >> ${APP_DIR}/backups/scheduler.log 2>&1
30 2 * * * root APP_DIR=${APP_DIR} ${APP_DIR}/scripts/run_scheduled_job.sh nightly_database_backup >> ${APP_DIR}/backups/scheduler.log 2>&1
CRON

chmod 644 "${CRON_FILE}"
echo "Installed ${CRON_FILE}"
