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
- `PUT /api/admin/node-capacities/{node_id}`：校准 TOC 节点日产能和目标处理时长。
- `GET /api/admin/users`：查看用户/角色配置。
- `POST /api/admin/users`：创建用户/角色配置。
- `POST /api/admin/data/import/usaid`：导入 USAID shipment-level 数据。
- `POST /api/admin/data/import/business`：导入业务 CSV/JSON 运单节点数据。
- `POST /api/admin/data/reset`：重建公开数据索引。
- `POST /api/admin/backup`：触发数据库备份。
- `GET /api/admin/backups`：查看备份文件列表。
- `GET /api/admin/audit-logs`：查看后台操作审计。
- `GET /api/admin/schedules`：查看定时导入/备份任务。
- `PUT /api/admin/schedules/{schedule_id}`：启停定时任务或调整提示配置。
- `POST /api/admin/schedules/{schedule_id}/run`：立即执行某个定时任务。

## 业务数据导入格式

后台支持粘贴 CSV 或 JSON。最小字段：

```csv
batch_no,channel_type,origin,destination,piece_count,cbm,ts_order_created,ts_last_mile_del
BIZ-SZ-US-001,空运,深圳,美国,42,1.6,2026-05-01T08:00:00,2026-05-09T11:00:00
```

如果提供 `ts_domestic_out`、`ts_head_arrive`、`ts_customs_clear`、`ts_oversea_in`，系统会使用真实节点时间；否则会按全链路时长派生节点时间，确保 TOC 诊断可运行。

## 定时任务

腾讯云部署脚本会安装 `/etc/cron.d/lean-logistics-dashboard`，默认包含：

- `daily_usaid_import`：每日 02:00 调用后台导入 USAID 数据。
- `nightly_database_backup`：每日 02:30 调用后台备份。

也可以手动执行：

```bash
sudo APP_DIR=/opt/lean-logistics-dashboard /opt/lean-logistics-dashboard/scripts/run_scheduled_job.sh nightly_database_backup
```

## 验证

```powershell
python -m backend.verify_backend
```
