# 真实数据与模型指数说明

## 数据来源

当前版本已移除随机生成的演示批次，运行时种子数据来自 `data/real_logistics_seed.json`。

### World Bank Logistics Performance Index

- 数据源：World Bank Logistics Performance Index，Source ID `66`
- API：https://api.worldbank.org/v2/source/66
- 报告与方法：https://lpi.worldbank.org/report
- 当前使用年份：`2022`
- 当前使用指标：
  - `LP.LPI.OVRL.XQ`：综合物流绩效
  - `LP.LPI.CUST.XQ`：清关效率
  - `LP.LPI.INFR.XQ`：贸易与运输基础设施质量
  - `LP.LPI.ITRN.XQ`：安排有竞争力国际运输的便利性
  - `LP.LPI.LOGS.XQ`：物流服务能力与质量
  - `LP.LPI.TRAC.XQ`：追踪与追溯能力
  - `LP.LPI.TIME.XQ`：按预期交付频率

World Bank 指标说明中写明，LPI 采用 1-5 分量表，2023 调查由物流专业人士提供国家评估，综合分通过六个维度聚合而成。当前仓库固定采集到的最新非空值为 2022 年。

### USAID Supply Chain Shipment Pricing Data

- 目录页：https://catalog.data.gov/dataset/supply-chain-shipment-pricing-data-e75ff
- 用途：作为后续接入真实 shipment-level lead time 与价格校准的公开数据源。
- 当前状态：本工作区访问其数据 API 时 TLS 连接不稳定，因此本次没有把不可稳定抓取的记录写入运行时数据库，只保留为已核验的公开资料来源。

## GitHub / 模型参考

- Google OR-Tools：https://github.com/google/or-tools
  - 参考其图优化、路径约束与车辆路径问题建模方式。
- VROOM：https://github.com/VROOM-Project/vroom
  - 参考其 VRP、CVRP、VRPTW、pickup-delivery 和自定义矩阵的工程边界。
- PM4Py：https://github.com/process-intelligence-solutions/pm4py
  - 参考 process mining 中按事件日志计算阶段耗时、等待时间、性能瓶颈的思路。

## 指数建模

### 线路观测

`fulfillment_records` 不再表示虚构包裹，而表示公开指数驱动的线路观测：

- 编号格式：`WB-LPI-{ISO3}-{ROUTE_FAMILY}-2022`
- 目的地：美国、德国、英国、日本
- 渠道：空运、海运、快递
- 货量：`volume_index`，用于计算节拍需求，不声明为真实包裹件数
- 证据：每条观测带有 `source_id`、`source_year`、`source_url`、`evidence_note`

### 时效估计

各阶段耗时由 LPI 组件驱动：

- 国内仓出库：使用中国 `logistics_quality`
- 头程运输：使用目的地 `infrastructure`、`international_shipments`、`timeliness` 的均值
- 清关查验：使用目的地 `customs`
- 海外仓上架：使用目的地 `logistics_quality`
- 尾程妥投：使用目的地 `timeliness`

统一换算函数：

```text
score_multiplier = clamp(4.0 / score, 0.72, 1.35)
stage_hours = clamp(base_hours * score_multiplier, floor, ceiling)
```

### TOC 瓶颈诊断

诊断继续使用 TOC 约束理论，但输入来自真实指数驱动观测：

```text
score = avg_hours / target_hours * 0.45
      + coefficient_of_variation / 0.35 * 0.25
      + load_factor * 0.30
```

最高分节点为 Bottleneck。若节点超过目标时效、CV 超阈值或负荷率过高，则标记 Warn。

### 路径优化

路径优化仍采用“期望交期约束下的最低成本指数路线”：

- 先枚举简单路径
- 使用 label-setting constrained shortest path 寻找满足 `max_allowed_days` 的最低成本指数路线
- 若无可行解，自动兜底为最快路线

成本字段已改为 `成本指数`，不再显示为美元报价。
