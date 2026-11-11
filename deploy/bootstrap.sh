#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/plt-colorizer"
APP_USER="plt"

if [[ "${EUID}" -ne 0 ]]; then
  echo "请用 root 运行：sudo REPO_URL=... bash deploy/bootstrap.sh" >&2
  exit 1
fi

if [[ -z "${REPO_URL:-}" ]]; then
  cat >&2 <<'EOF'
缺少仓库地址。
用法：
  sudo REPO_URL=git@github.com:你的账号/plt-colorizer.git bash deploy/bootstrap.sh

私有仓库请先按 deploy/README.md 配置只读 Deploy Key。
EOF
  exit 1
fi

echo "[1/7] 安装系统依赖"
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx git

echo "[2/7] 创建运行用户"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

echo "[3/7] 拉取代码"
if [[ -d "$APP_DIR/.git" ]]; then
  sudo -H -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  if ! sudo -H -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"; then
    echo "克隆失败。私有仓库需要先配置 Deploy Key，见 deploy/README.md。" >&2
    exit 1
  fi
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "[4/7] 创建虚拟环境并安装依赖"
sudo -H -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -H -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  sudo -H -u "$APP_USER" env PIP_INDEX_URL="$PIP_INDEX_URL" \
    "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
else
  sudo -H -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

echo "[5/7] 安装并启动 systemd 服务"
install -m 0644 "$APP_DIR/deploy/plt-colorizer.service" /etc/systemd/system/plt-colorizer.service
systemctl daemon-reload
systemctl enable plt-colorizer
systemctl restart plt-colorizer

echo "[6/7] 配置 Nginx"
install -m 0644 "$APP_DIR/deploy/nginx-site.conf" /etc/nginx/sites-available/plt-colorizer
ln -sf /etc/nginx/sites-available/plt-colorizer /etc/nginx/sites-enabled/plt-colorizer
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "[7/7] 防火墙"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp
else
  echo "ufw 未启用，请确认云厂商安全组已放行 80 端口。"
fi

echo
echo "部署完成。"
echo "健康检查：http://$(hostname -I | awk '{print $1}')/api/health"
echo "注意：当前为 HTTP + 无认证，公网可访问，已在 Nginx 配置每 IP 限流。"
