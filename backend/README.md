# 精益物流决策看板后端

## 启动

```powershell
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

启动后会自动创建 `lean_logistics.db` 并写入 Mock 数据。

## 核心接口

- `GET /api/health`：健康检查
- `GET /api/options`：渠道、目的地、异常场景选项
- `GET /api/dashboard`：总览聚合数据
- `GET /api/diagnostics`：TOC 瓶颈诊断
- `GET /api/routes/optimize`：带期望交期约束的路径优化
- `GET /api/batches`：批次明细和风险等级
- `POST /api/dev/reset`：重置 Mock 数据

## 验证

```powershell
python -m backend.verify_backend
```

