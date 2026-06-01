#!/usr/bin/env bash
set -euo pipefail

APP_NAME="lean-logistics-dashboard"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
APP_USER="${APP_USER:-www-data}"
REPO_URL="${REPO_URL:-https://github.com/yun5233378-blip/lean-logistics-dashboard.git}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root: sudo bash scripts/tencent_bootstrap.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx postgresql-client

mkdir -p "${APP_DIR}"
if [ ! -d "${APP_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${APP_DIR}"
else
  git config --global --add safe.directory "${APP_DIR}"
  git -C "${APP_DIR}" pull --ff-only
fi

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

sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

cp "${APP_DIR}/deploy/tencent/lean-logistics-dashboard.service" /etc/systemd/system/lean-logistics-dashboard.service
systemctl daemon-reload
systemctl enable lean-logistics-dashboard
systemctl restart lean-logistics-dashboard

echo "Service started. Check status with:"
echo "  systemctl status lean-logistics-dashboard --no-pager"
echo "Local health check:"
echo "  curl http://127.0.0.1:8000/api/health"
