# 部署到 Ubuntu 云服务器

当前线上策略：**Ubuntu + systemd/venv + Nginx，纯 HTTP（公网 IP），无认证**。
Nginx 负责限流、上传大小限制和安全响应头，FastAPI 负责解析、渲染与像素上限保护。

## 0. 前提

- Ubuntu 22.04 / 24.04，root 或 sudo
- 云厂商安全组放行 **22** 和 **80** 端口
- 建议 **2 核 4 G** 起；若只有 2 G，见文末“资源与安全”

## 1. 推送代码到 GitHub

建议使用**私有仓库**，且仓库根目录就是 `webapp/`。不要提交客户图纸（`无纽扣开衫.plt`）和生成结果。

```bash
cd webapp
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:你的账号/plt-colorizer.git
git push -u origin main
```

## 2. 配置只读 Deploy Key（私有仓库必做）

在服务器上执行：

```bash
sudo -H -u plt ssh-keygen -t ed25519 -N "" -f /home/plt/.ssh/id_ed25519 -C "plt-colorizer deploy"
sudo -H -u plt bash -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts'
sudo -H -u plt cat /home/plt/.ssh/id_ed25519.pub
```

如果 `plt` 用户还不存在，先执行 `sudo useradd --system --create-home --shell /usr/sbin/nologin plt`。

把输出的公钥复制到 GitHub 仓库：**Settings → Deploy keys → Add deploy key**，只勾选读权限。然后用 `REPO_URL=git@github.com:...` 部署。

公开仓库可以跳过这一步，改用 HTTPS 地址。

## 3. 一键部署

```bash
cd /path/to/webapp
sudo REPO_URL=git@github.com:你的账号/plt-colorizer.git bash deploy/bootstrap.sh
```

国内服务器如果 pip 很慢，可以指定镜像：

```bash
sudo PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  REPO_URL=git@github.com:你的账号/plt-colorizer.git \
  bash deploy/bootstrap.sh
```

脚本会完成：

1. 安装 `python3-venv`、`nginx`、`git`
2. 创建 `plt` 系统用户和 `/opt/plt-colorizer`
3. 拉取代码
4. 创建 `.venv` 并安装依赖
5. 安装并启动 `plt-colorizer.service`
6. 安装 Nginx 站点配置（删除默认站点）
7. 如启用了 ufw，放行 80

## 4. 验证

```bash
curl http://服务器公网IP/api/health
# {"status":"ok"}
```

浏览器打开 `http://服务器公网IP/`，用 `samples/demo.plt` 做冒烟测试：应导出 1 张 PNG，包含 2 个色块。

## 5. 更新代码

```bash
sudo bash /opt/plt-colorizer/deploy/update.sh
```

## 6. 查看状态与日志

```bash
systemctl status plt-colorizer
journalctl -u plt-colorizer -n 50 --no-pager
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

## 7. 资源与安全

当前是**完全公开、无认证**。任何人拿到地址都能上传并消耗 CPU，为此已加：

| 限制 | 位置 | 值 |
|---|---|---|
| 请求体 | Nginx + 应用 | 25 MB |
| 单文件 | 应用 | 20 MB |
| 单张图片像素 | 应用 | 1.2 亿 |
| 整批像素 | 应用 | 4 亿 |
| 每 IP 速率 | Nginx | 2 次/秒，突发 5 |
| 每 IP 并发转换 | Nginx | 2 |
| 单边尺寸 | 应用 | 4 米 |

内存估算：1.2 亿像素的 RGBA 位图约 480 MB，转换期间还会叠加 SVG/PNG 开销。**2 G 内存的机器建议把 `MAX_PIXELS_PER_IMAGE` 调到 6000 万**，或把 systemd 的 `--limit-concurrency` 调到 1。

如果后续需要登录保护，给 Nginx 加 Basic Auth：

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd youruser
```

在 `deploy/nginx-site.conf` 的 `server` 块内加入：

```nginx
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;
```

再执行 `sudo nginx -t && sudo systemctl reload nginx`。

## 8. 常见问题

| 现象 | 排查 |
|---|---|
| 502 Bad Gateway | `systemctl status plt-colorizer`、`journalctl -u plt-colorizer` |
| 413 Request Entity Too Large | Nginx `client_max_body_size` 或应用 `MAX_REQUEST_BYTES` |
| 429 Too Many Requests | 触发了每 IP 限流，稍等或调整 `limit_req` |
| 400 像素超限 | 降低 DPI，或提高 `MAX_PIXELS_PER_IMAGE` |
| git clone 失败 | 私有仓库的 Deploy Key 未配置，或 `ssh-keyscan` 未写入 known_hosts |
| 改了代码没生效 | 运行 `deploy/update.sh`，或 `systemctl restart plt-colorizer` |
