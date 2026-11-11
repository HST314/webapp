#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/plt-colorizer"
APP_USER="plt"

if [[ "${EUID}" -ne 0 ]]; then
  echo "请用 sudo 运行：sudo bash deploy/update.sh" >&2
  exit 1
fi

sudo -H -u "$APP_USER" git -C "$APP_DIR" pull --ff-only

if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  sudo -H -u "$APP_USER" env PIP_INDEX_URL="$PIP_INDEX_URL" \
    "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
  sudo -H -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

systemctl restart plt-colorizer
systemctl --no-pager --lines=5 status plt-colorizer || true

echo "更新完成。"
