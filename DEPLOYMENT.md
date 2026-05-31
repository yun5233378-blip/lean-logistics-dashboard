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

## 3. Render 部署

推荐方式：在 Render 新建 Web Service，连接 GitHub 仓库。

配置：

- Build Command：`pip install -r requirements.txt`
- Start Command：`uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
- Health Check Path：`/api/health`

仓库内已经提供 `render.yaml`，也可以用 Render Blueprint 方式导入。

## 4. Railway 部署

推荐方式：Railway 连接 GitHub 仓库后选择 Dockerfile 部署。

仓库内已经提供：

- `Dockerfile`
- `railway.json`

Railway 会使用 `$PORT` 环境变量启动服务。

## 5. Docker 本地验证

```powershell
docker build -t lean-logistics-dashboard .
docker run --rm -p 8000:8000 lean-logistics-dashboard
```

## 6. 注意

`lean_logistics.db` 是运行时生成的 Mock 数据库，已加入 `.gitignore`。云端每次冷启动会自动创建一份新的原型数据。

