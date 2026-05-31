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
apt-get install -y python3 python3-venv python3-pip git nginx

mkdir -p "${APP_DIR}"
if [ ! -d "${APP_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" pull --ff-only
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

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

