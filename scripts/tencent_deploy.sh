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
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
cp "${APP_DIR}/deploy/tencent/lean-logistics-dashboard.service" /etc/systemd/system/lean-logistics-dashboard.service
systemctl daemon-reload
systemctl restart lean-logistics-dashboard

echo "Deploy complete."
systemctl status lean-logistics-dashboard --no-pager
