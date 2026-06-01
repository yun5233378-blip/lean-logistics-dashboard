# 下一阶段开发记录

## 五个任务落地范围

1. 数据模型深化
   - 新增 USAID Supply Chain Shipment Pricing Data 在线导入能力。
   - 新增 `external_shipments` 表，保存真实 shipment-level 目的国、运输方式、交付日期、运费、重量和原始 payload。
   - 内置 5 条公开 SCMS Delivery History 样本行作为可审计运行时 seed，避免上游 Socrata DNS/访问异常时真实运单统计为空。
   - `/api/sources` 和 `/api/ops/status` 会暴露真实运单统计。

2. PostgreSQL 持久化
   - 默认 SQLite 仍可本地零配置启动。
   - 配置 `DATABASE_URL=postgresql://...` 后自动使用 PostgreSQL schema。
   - schema version 升级到 `3`，启动时会按版本重建索引。

3. 用户/权限/项目配置
   - 新增 Bearer Token 管理权限。
   - 新增 `app_users` 表，保存用户、角色、项目范围与状态。
   - 后台接口统一通过 `ADMIN_API_TOKEN` 鉴权。

4. 后台管理端
   - 前端新增“后台管理”页面。
   - 支持保存管理员 Token、刷新运行状态、导入 USAID 数据、触发备份、重建索引、编辑模型参数、查看角色。

5. 生产部署加固
   - 新增 `/api/ops/status` 运维状态接口。
   - 新增请求日志、安全响应头、systemd `EnvironmentFile`。
   - 新增 `scripts/backup_database.sh`，部署脚本会在更新前尝试备份。
   - 腾讯云 bootstrap/deploy 脚本会自动创建 `/etc/lean-logistics-dashboard.env`。

## 管理端默认访问

本地开发默认 Token 是：

```text
dev-admin-token
```

生产环境会在首次 bootstrap/deploy 时自动生成 `ADMIN_API_TOKEN` 并写入：

```bash
/etc/lean-logistics-dashboard.env
```

## 验证命令

```powershell
python -m backend.verify_backend
```

```powershell
node --% -e "const fs=require('fs'); const html=fs.readFileSync('index.html','utf8'); const start='<script type=\"text/babel\">'; const a=html.indexOf(start); const b=html.indexOf('</script>', a); const jsx=html.slice(a+start.length,b); fetch('https://unpkg.com/@babel/standalone/babel.min.js').then(r=>r.text()).then(code=>{ const module={exports:{}}; Function('module','exports',code)(module,module.exports); module.exports.transform(jsx,{presets:['react']}); console.log('JSX transform passed'); })"
```
