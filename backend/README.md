# 精益物流决策看板后端

## 启动

```powershell
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

默认使用本地 SQLite。设置 `DATABASE_URL=postgresql://...` 后会切换到 PostgreSQL。

## 环境变量

- `DATABASE_URL`：为空时使用 SQLite；PostgreSQL 时填写连接串。
- `ADMIN_API_TOKEN`：后台管理接口 Bearer Token，生产环境必须配置。
- `ENABLE_ONLINE_IMPORTS`：是否允许在线导入 USAID shipment 数据。
- `USAID_SHIPMENTS_ENDPOINT`：默认 `https://data.usaid.gov/resource/mm7d-nzmf.json`。
- `BACKUP_DIR`：备份输出目录。

## 核心接口

- `GET /api/health`：健康检查。
- `GET /api/sources`：数据来源、LPI 指标、模型参考、真实运单统计。
- `GET /api/options`：渠道、目的地、异常场景选项。
- `GET /api/dashboard`：总览聚合数据。
- `GET /api/diagnostics`：TOC 瓶颈诊断。
- `GET /api/routes/optimize`：带期望交期约束的路径优化。
- `GET /api/batches`：线路观测和风险等级。
- `GET /api/ops/status`：生产运行状态摘要。

## 后台接口

以下接口需要 `Authorization: Bearer <ADMIN_API_TOKEN>`。

- `GET /api/admin/runtime`：后台运行时、数据源、参数、用户、导入任务。
- `PUT /api/admin/model-parameters/{key}`：更新模型参数。
- `GET /api/admin/users`：查看用户/角色配置。
- `POST /api/admin/users`：创建用户/角色配置。
- `POST /api/admin/data/import/usaid`：导入 USAID shipment-level 数据。
- `POST /api/admin/data/reset`：重建公开数据索引。
- `POST /api/admin/backup`：触发数据库备份。

## 验证

```powershell
python -m backend.verify_backend
```
