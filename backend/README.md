# 精益物流决策看板后端

## 启动

```powershell
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

启动后会自动创建 `lean_logistics.db` 并写入公开数据驱动的线路观测。数据来源与模型说明见项目根目录 `REAL_DATA_MODEL.md`。

## 核心接口

- `GET /api/health`：健康检查
- `GET /api/sources`：真实数据来源、LPI 指标与模型参考
- `GET /api/options`：渠道、目的地、异常场景选项
- `GET /api/dashboard`：总览聚合数据
- `GET /api/diagnostics`：TOC 瓶颈诊断
- `GET /api/routes/optimize`：带期望交期约束的路径优化
- `GET /api/batches`：批次明细和风险等级
- `POST /api/dev/reset`：重建公开数据索引

## 验证

```powershell
python -m backend.verify_backend
```
