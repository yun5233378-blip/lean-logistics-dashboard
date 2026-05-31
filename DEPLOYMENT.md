# 云端部署与 GitHub 开发说明

当前项目采用单服务部署：

- `backend.app:app` 是 FastAPI 应用
- `/` 直接返回前端 `index.html`
- `/api/*` 提供后端接口
- 启动时自动创建 SQLite Mock 数据库

## 1. 本地运行

```powershell
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

访问：

- 前端：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

## 2. GitHub 开发流程

初始化并推送：

```powershell
git init
git add .
git commit -m "Initial LeanLogiLens prototype"
git branch -M main
git remote add origin https://github.com/<your-org>/<your-repo>.git
git push -u origin main
```

推送后，GitHub Actions 会自动运行：

```powershell
python -m backend.verify_backend
```

## 3. 腾讯云服务器部署

适合 Ubuntu / Debian 系服务器。部署方式是：

- GitHub 托管代码
- 腾讯云服务器 `git pull`
- systemd 常驻运行 FastAPI
- Nginx 反向代理到 `127.0.0.1:8000`

首次部署：

```bash
git clone https://github.com/yun5233378-blip/lean-logistics-dashboard.git /tmp/lean-logistics-dashboard
cd /tmp/lean-logistics-dashboard
sudo bash scripts/tencent_bootstrap.sh
```

更新部署：

```bash
cd /opt/lean-logistics-dashboard
sudo bash scripts/tencent_deploy.sh
```

启用 Nginx 反代：

```bash
sudo cp /opt/lean-logistics-dashboard/deploy/tencent/nginx.conf.example /etc/nginx/sites-available/lean-logistics-dashboard
sudo ln -sf /etc/nginx/sites-available/lean-logistics-dashboard /etc/nginx/sites-enabled/lean-logistics-dashboard
sudo nginx -t
sudo systemctl reload nginx
```

服务检查：

```bash
curl http://127.0.0.1:8000/api/health
sudo systemctl status lean-logistics-dashboard --no-pager
sudo journalctl -u lean-logistics-dashboard -f
```

腾讯云安全组需要放行：

- `22`：SSH
- `80`：HTTP
- `443`：HTTPS，如果后续配置域名证书

如果服务器已有 Caddy/Nginx 占用 `80/443`，不要把本项目挂到其他项目域名的路径下面。建议添加独立站点块：

```caddyfile
http://logistics.void52.site {
    encode gzip
    reverse_proxy 172.19.0.1:8000
}
```

同时在 DNS 中添加：

```text
logistics.void52.site  A  43.156.180.164
```

如果暂时没有独立域名，也可以把服务器裸 IP 临时指向本项目：

```caddyfile
http://43.156.180.164 {
    encode gzip
    reverse_proxy 172.19.0.1:8000
}
```

## 4. Render 部署

推荐方式：在 Render 新建 Web Service，连接 GitHub 仓库。

配置：

- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
- Health Check Path：`/api/health`

仓库内已经提供 `render.yaml`，也可以用 Render Blueprint 方式导入。

## 5. Railway 部署

推荐方式：Railway 连接 GitHub 仓库后选择 Dockerfile 部署。

仓库内已经提供：

- `Dockerfile`
- `railway.json`

Railway 会使用 `$PORT` 环境变量启动服务。

## 6. Docker 本地验证

```powershell
docker build -t lean-logistics-dashboard .
docker run --rm -p 8000:8000 lean-logistics-dashboard
```

## 7. 注意

`lean_logistics.db` 是运行时生成的 Mock 数据库，已加入 `.gitignore`。云端每次冷启动会自动创建一份新的原型数据。
