# 云端部署与 GitHub 开发说明

当前项目采用单服务部署：

- `backend.app:app` 是 FastAPI 应用
- `/` 直接返回前端 `index.html`
- `/api/*` 提供后端接口
- 启动时自动创建公开数据驱动索引；默认 SQLite，配置 `DATABASE_URL` 后使用 PostgreSQL

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

当前仓库还配置了自动部署工作流：

- `CI`：每次推送到 `main` 后运行后端验证。
- `Deploy Tencent Cloud`：当 `main` 分支的 CI 成功后，通过 SSH 登录腾讯云并执行 `sudo bash scripts/tencent_deploy.sh`。

需要在 GitHub 仓库 Secrets 中配置：

- `TENCENT_HOST`
- `TENCENT_SSH_PORT`
- `TENCENT_USER`
- `TENCENT_SSH_KEY`

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

定时任务检查：

```bash
sudo cat /etc/cron.d/lean-logistics-dashboard
sudo APP_DIR=/opt/lean-logistics-dashboard /opt/lean-logistics-dashboard/scripts/run_scheduled_job.sh nightly_database_backup
```

后台管理页现在支持：

- 粘贴 CSV/JSON 业务运单数据并写入 `fulfillment_records`
- 校准 TOC 节点日产能和目标处理时长
- 查看和手动执行定时导入/备份任务
- 查看备份文件与后台操作审计

主看板默认不展示公开样本或派生观测。未导入业务 CSV/JSON 前，总览、时效、瓶颈、路径、异常和线路观测页面会显示空状态；导入后才按 `BUSINESS_UPLOAD` 数据实时计算。

腾讯云安全组需要放行：

- `22`：SSH
- `80`：HTTP
- `443`：HTTPS，正式域名启用 Caddy 自动证书时必需

如果服务器已有 Caddy/Nginx 占用 `80/443`，不要把本项目挂到其他项目域名的路径下面。建议添加独立站点块：

```caddyfile
logistics.void52.site {
    encode gzip
    reverse_proxy 172.19.0.1:8000
}
```

同时在 DNS 中添加：

```text
logistics.void52.site  A  43.156.180.164
```

上线验收地址：

- 前端：https://logistics.void52.site/
- API 文档：https://logistics.void52.site/docs
- 健康检查：https://logistics.void52.site/api/health

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

`lean_logistics.db` 是本地默认运行库，已加入 `.gitignore`。生产环境建议在 `/etc/lean-logistics-dashboard.env` 中配置 `DATABASE_URL`、`ADMIN_API_TOKEN`、`BACKUP_DIR`。后台管理接口使用 `Authorization: Bearer <ADMIN_API_TOKEN>`，部署脚本会在更新前尝试执行 `scripts/backup_database.sh`。
