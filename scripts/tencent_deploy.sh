#!/usr/bin/env bash
set -euo pipefail

APP_NAME="lean-logistics-dashboard"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
APP_USER="${APP_USER:-www-data}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root: sudo bash scripts/tencent_deploy.sh"
  exit 1
fi

git config --global --add safe.directory "${APP_DIR}"
git -C "${APP_DIR}" pull --ff-only
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
if [ ! -f /etc/lean-logistics-dashboard.env ]; then
  ADMIN_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  cat > /etc/lean-logistics-dashboard.env <<ENV
ADMIN_API_TOKEN=${ADMIN_TOKEN}
ENABLE_ONLINE_IMPORTS=true
DEFAULT_IMPORT_LIMIT=80
BACKUP_DIR=${APP_DIR}/backups
LOG_LEVEL=INFO
ENV
  chmod 640 /etc/lean-logistics-dashboard.env
fi
mkdir -p "${APP_DIR}/backups"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/backups"
chmod +x "${APP_DIR}/scripts/"*.sh
bash "${APP_DIR}/scripts/backup_database.sh" || true
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
cp "${APP_DIR}/deploy/tencent/lean-logistics-dashboard.service" /etc/systemd/system/lean-logistics-dashboard.service
systemctl daemon-reload
systemctl restart lean-logistics-dashboard
bash "${APP_DIR}/scripts/install_schedules_cron.sh" || true

echo "Deploy complete."
systemctl status lean-logistics-dashboard --no-pager
