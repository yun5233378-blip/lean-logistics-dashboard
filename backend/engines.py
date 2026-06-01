from __future__ import annotations

import heapq
import math
import statistics
from datetime import datetime
from typing import Any

from .database import fetch_all


STAGES = [
    {
        "id": "Domestic_PickPack",
        "name": "国内仓出库",
        "short": "国内仓",
        "start": "ts_order_created",
        "end": "ts_domestic_out",
        "value_ratio": 0.68,
    },
    {
        "id": "Head_Transit",
        "name": "头程运输",
        "short": "头程",
        "start": "ts_domestic_out",
        "end": "ts_head_arrive",
        "value_ratio": 0.76,
    },
    {
        "id": "Customs_Clearance",
        "name": "清关查验",
        "short": "清关",
        "start": "ts_head_arrive",
        "end": "ts_customs_clear",
        "value_ratio": 0.34,
    },
    {
        "id": "Oversea_Inbound",
        "name": "海外仓上架",
        "short": "海外仓",
        "start": "ts_customs_clear",
        "end": "ts_oversea_in",
        "value_ratio": 0.36,
    },
    {
        "id": "Last_Mile",
        "name": "尾程妥投",
        "short": "尾程",
        "start": "ts_oversea_in",
        "end": "ts_last_mile_del",
        "value_ratio": 0.54,
    },
]


ANOMALIES: dict[str, dict[str, Any]] = {
    "none": {
        "name": "正常运行",
        "node_id": None,
        "summary": "链路保持稳定，海外仓仍是当前约束节点。",
        "duration": {},
        "cv": {},
        "wip": {},
        "route": {},
    },
    "customs": {
        "name": "清关罢工",
        "node_id": "Customs_Clearance",
        "summary": "清关处理能力下降，查验等待显著拉长，系统约束转移至清关查验。",
        "duration": {"Customs_Clearance": 2.15, "Head_Transit": 1.12},
        "cv": {"Customs_Clearance": 0.24},
        "wip": {"Customs_Clearance": 980, "Head_Transit": 280},
        "route": {"customs": 2.4, "air": 0.7},
    },
    "warehouse": {
        "name": "海外仓爆仓",
        "node_id": "Oversea_Inbound",
        "summary": "海外仓拆柜和上架能力不足，建议启用备用仓并增加夜班产能。",
        "duration": {"Oversea_Inbound": 2.35, "Customs_Clearance": 1.08},
        "cv": {"Oversea_Inbound": 0.32},
        "wip": {"Oversea_Inbound": 1260, "Customs_Clearance": 240},
        "route": {"warehouse": 2.9, "lastmile": 0.6},
    },
    "port": {
        "name": "港口拥堵",
        "node_id": "Head_Transit",
        "summary": "头程海运等待时间上升，低成本路线时效风险扩大。",
        "duration": {"Head_Transit": 1.72},
        "cv": {"Head_Transit": 0.26},
        "wip": {"Head_Transit": 1120},
        "route": {"sea": 4.8, "port": 3.2},
    },
    "lastmile": {
        "name": "尾程派送延迟",
        "node_id": "Last_Mile",
        "summary": "尾程派送网络承压，建议切换区域承运商并提高预约波次。",
        "duration": {"Last_Mile": 1.85},
        "cv": {"Last_Mile": 0.28},
        "wip": {"Last_Mile": 740},
        "route": {"lastmile": 1.8, "express": 0.4},
    },
}


def normalize_filter(value: str | None, all_values: set[str]) -> str | None:
    if value is None or value.strip() == "" or value in all_values:
        return None
    return value


def get_records(channel_type: str | None = None, destination: str | None = None) -> list[dict[str, Any]]:
    channel_type = normalize_filter(channel_type, {"全部渠道", "全部"})
    destination = normalize_filter(destination, {"全部目的地", "全部"})
    clauses: list[str] = []
    params: list[str] = []
    if channel_type:
        clauses.append("channel_type = ?")
        params.append(channel_type)
    if destination:
        clauses.append("destination = ?")
        params.append(destination)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = fetch_all(f"SELECT * FROM fulfillment_records {where} ORDER BY id", params)
    return [dict(row) for row in rows]


def get_capacities() -> dict[str, dict[str, Any]]:
    rows = fetch_all("SELECT * FROM node_capacities")
    return {row["node_id"]: dict(row) for row in rows}


def get_routes() -> list[dict[str, Any]]:
    rows = fetch_all("SELECT * FROM routing_matrix ORDER BY id")
    return [dict(row) for row in rows]


def get_data_sources() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT * FROM data_sources
        ORDER BY CASE source_id WHEN 'WB_LPI_2022' THEN 0 ELSE 1 END, source_id
        """
    )
    return [dict(row) for row in rows]


def get_model_references() -> list[dict[str, Any]]:
    rows = fetch_all("SELECT * FROM model_references ORDER BY ref_id")
    return [dict(row) for row in rows]


def get_lpi_scores() -> list[dict[str, Any]]:
    rows = fetch_all("SELECT * FROM lpi_country_scores ORDER BY country")
    return [dict(row) for row in rows]


def build_model_metadata() -> dict[str, Any]:
    return {
        "data_mode": "真实公开数据驱动",
        "runtime_sample_policy": "已移除演示批次；当前运行数据为 World Bank LPI 2022 指标驱动的线路观测与派生诊断。",
        "sources": get_data_sources(),
        "model_references": get_model_references(),
        "lpi_scores": get_lpi_scores(),
    }


def diagnose_bottlenecks(
    channel_type: str | None = None,
    destination: str | None = None,
    scenario: str = "none",
) -> dict[str, Any]:
    scenario_cfg = ANOMALIES.get(scenario, ANOMALIES["none"])
    records = get_records(channel_type, destination)
    capacities = get_capacities()
    if not records:
        return {
            "scenario": scenario_cfg,
            "stages": [],
            "summary": {
                "total_records": 0,
                "total_pieces": 0,
                "avg_lead_time_days": 0,
                "value_added_ratio": 0,
                "bottleneck_node": None,
            },
        }

    total_pieces = sum(row["piece_count"] for row in records)
    start_times = [parse_dt(row["ts_order_created"]) for row in records]
    end_times = [parse_dt(row["ts_last_mile_del"]) for row in records]
    days_span = max(1.0, (max(end_times) - min(start_times)).total_seconds() / 86400)
    daily_demand = total_pieces / days_span
    total_duration_hours = []
    total_value_hours = 0.0
    stage_rows = []

    for stage in STAGES:
        durations = []
        for row in records:
            raw = (parse_dt(row[stage["end"]]) - parse_dt(row[stage["start"]])).total_seconds() / 3600
            adjusted = raw * scenario_cfg["duration"].get(stage["id"], 1.0)
            durations.append(max(0.1, adjusted))

        avg_hours = statistics.mean(durations)
        std_hours = statistics.pstdev(durations) if len(durations) > 1 else 0.0
        cv = (std_hours / avg_hours if avg_hours else 0.0) + scenario_cfg["cv"].get(stage["id"], 0.0)
        cv = min(1.2, max(0.0, cv))
        cap = capacities[stage["id"]]
        target = cap["target_lead_time"]
        available_seconds = 8 * 3600
        takt_time_sec = available_seconds / max(daily_demand, 1)
        standard_cycle_sec = available_seconds / cap["daily_capacity"]
        avg_cycle_time_sec = standard_cycle_sec * (avg_hours / target)
        load_factor = (avg_cycle_time_sec / takt_time_sec) * (1.15 if scenario_cfg["node_id"] == stage["id"] else 1.0)
        wip = round(daily_demand * avg_hours / 24 * (1 + cv) + scenario_cfg["wip"].get(stage["id"], 0))
        value_hours = avg_hours * stage["value_ratio"]
        wait_hours = max(0.0, avg_hours - value_hours)
        score = avg_hours / target * 0.45 + cv / 0.35 * 0.25 + load_factor * 0.3

        total_duration_hours.append(avg_hours)
        total_value_hours += value_hours
        stage_rows.append(
            {
                "stage_id": stage["id"],
                "stage_name": stage["name"],
                "stage_short_name": stage["short"],
                "avg_lead_time_hrs": round(avg_hours, 2),
                "target_lead_time_hrs": round(float(target), 2),
                "wait_time_hrs": round(wait_hours, 2),
                "value_added_time_hrs": round(value_hours, 2),
                "coefficient_of_variation": round(cv, 3),
                "daily_capacity": cap["daily_capacity"],
                "daily_demand": round(daily_demand, 1),
                "load_factor": round(load_factor, 3),
                "takt_time_sec": round(takt_time_sec, 2),
                "avg_cycle_time_sec": round(avg_cycle_time_sec, 2),
                "wip": wip,
                "score": score,
                "status": "正常",
            }
        )

    bottleneck = max(stage_rows, key=lambda item: item["score"])
    for row in stage_rows:
        warn = (
            row["avg_lead_time_hrs"] > row["target_lead_time_hrs"] * 1.2
            or row["coefficient_of_variation"] > 0.35
            or row["load_factor"] > 0.9
        )
        row["status"] = "预警" if warn else "正常"
        if row["stage_id"] == bottleneck["stage_id"]:
            row["status"] = "瓶颈"
        row.pop("score", None)

    total_hours = sum(total_duration_hours)
    value_added_ratio = total_value_hours / total_hours * 100 if total_hours else 0
    advice = build_advice(bottleneck, scenario_cfg)

    return {
        "scenario": {
            "id": scenario if scenario in ANOMALIES else "none",
            "name": scenario_cfg["name"],
            "summary": scenario_cfg["summary"],
        },
        "stages": stage_rows,
        "summary": {
            "total_records": len(records),
            "total_pieces": total_pieces,
            "avg_lead_time_days": round(total_hours / 24, 2),
            "avg_wait_time_hrs": round(sum(row["wait_time_hrs"] for row in stage_rows), 2),
            "value_added_ratio": round(value_added_ratio, 2),
            "bottleneck_node": {
                "stage_id": bottleneck["stage_id"],
                "stage_name": bottleneck["stage_name"],
                "stage_short_name": bottleneck["stage_short_name"],
            },
            "abnormal_batches": estimate_abnormal_batches(stage_rows, records),
            "toc_advice": advice,
        },
    }


def optimize_route(
    start_node: str = "中国",
    end_node: str = "美东海外仓",
    max_allowed_days: float = 8.0,
    scenario: str = "none",
    cargo_cbm: float = 1.0,
) -> dict[str, Any]:
    scenario_cfg = ANOMALIES.get(scenario, ANOMALIES["none"])
    route_penalty = scenario_cfg["route"]
    edges = []
    for edge in get_routes():
        extra_days = route_penalty.get(edge["route_tag"], 0.0)
        if edge["end_node"] == "美西清关":
            extra_days += route_penalty.get("customs", 0.0)
        adjusted_time = edge["transit_time_days"] + extra_days
        adjusted_cost = edge["unit_cost_cbm"] * cargo_cbm * (1.06 if extra_days > 0 else 1.0)
        edges.append({**edge, "time_days": adjusted_time, "cost": adjusted_cost})

    graph: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        graph.setdefault(edge["start_node"], []).append(edge)

    all_paths = enumerate_paths(graph, start_node, end_node)
    fastest = min(all_paths, key=lambda item: item["time_days"]) if all_paths else None
    cheapest = min(all_paths, key=lambda item: item["cost"]) if all_paths else None
    recommended = min(all_paths, key=lambda item: weighted_route_score(item, all_paths, max_allowed_days)) if all_paths else None
    constrained = label_setting_shortest_path(graph, start_node, end_node, max_allowed_days)
    fallback = constrained is None
    selected = fastest if fallback else constrained

    return {
        "scenario": {"id": scenario, "name": scenario_cfg["name"]},
        "start_node": start_node,
        "end_node": end_node,
        "max_allowed_days": max_allowed_days,
        "fallback": fallback,
        "message": "当前约束下无成本可行解，系统已自动切换为最快可达路线。" if fallback else "已找到满足交期约束的最低成本路线。",
        "selected_route": selected,
        "fastest_route": fastest,
        "cheapest_route": cheapest,
        "recommended_route": recommended,
        "candidate_routes": sorted(all_paths, key=lambda item: (item["time_days"] > max_allowed_days, item["cost"]))[:8],
        "feasible_count": sum(1 for item in all_paths if item["time_days"] <= max_allowed_days),
    }


def list_batches(
    channel_type: str | None = None,
    destination: str | None = None,
    scenario: str = "none",
    risk_level: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    diag = diagnose_bottlenecks(channel_type, destination, scenario)
    records = get_records(channel_type, destination)
    stage_status = {row["stage_id"]: row for row in diag["stages"]}
    bottleneck = diag["summary"]["bottleneck_node"] or {}
    bottleneck_stage = bottleneck.get("stage_id", "Oversea_Inbound")
    stage_names = {stage["id"]: stage["short"] for stage in STAGES}
    batches = []
    for idx, row in enumerate(records[: max(limit * 2, limit)]):
        elapsed_days = (parse_dt(row["ts_last_mile_del"]) - parse_dt(row["ts_order_created"])).total_seconds() / 86400
        status_row = stage_status.get(bottleneck_stage, {})
        lpi_pressure = max(0.0, 4.0 - row.get("cbm", 1.0)) * 4
        elapsed_pressure = min(16.0, elapsed_days * 1.2)
        risk_score = min(
            99,
            30
            + status_row.get("coefficient_of_variation", 0.2) * 80
            + status_row.get("load_factor", 0.8) * 22
            + lpi_pressure
            + elapsed_pressure,
        )
        risk = "高风险" if risk_score >= 76 else "中风险" if risk_score >= 58 else "低风险"
        if risk_level and risk_level not in {"全部风险", "全部"} and risk != risk_level:
            continue
        batches.append(
            {
                "batch_no": row["batch_no"],
                "channel_type": row["channel_type"],
                "origin": row["origin"],
                "destination": row["destination"],
                "piece_count": row["piece_count"],
                "volume_index": row.get("volume_index", row["piece_count"]) if isinstance(row, dict) else row["piece_count"],
                "current_node": stage_names.get(bottleneck_stage, "海外仓"),
                "elapsed_days": round(elapsed_days, 2),
                "eta_days": round(max(1.0, 14 - elapsed_days / 2 + (risk_score - 50) / 18), 1),
                "risk_level": risk,
                "risk_score": round(risk_score, 1),
                "issue": f"{stage_names.get(bottleneck_stage, '节点')}积压" if risk == "高风险" else "时效波动" if risk == "中风险" else "正常推进",
                "source_id": row.get("source_id"),
                "source_year": row.get("source_year"),
                "source_url": row.get("source_url"),
                "record_type": row.get("record_type"),
                "evidence_note": row.get("evidence_note"),
            }
        )
        if len(batches) >= limit:
            break

    return {"items": batches, "total": len(batches)}


def build_dashboard(
    channel_type: str | None = None,
    destination: str | None = None,
    scenario: str = "none",
    max_allowed_days: float = 8.0,
) -> dict[str, Any]:
    diagnostics = diagnose_bottlenecks(channel_type, destination, scenario)
    baseline = diagnose_bottlenecks(channel_type, destination, "none")
    route_plan = optimize_route(max_allowed_days=max_allowed_days, scenario=scenario)
    batches = list_batches(channel_type, destination, scenario, limit=20)
    return {
        "kpis": {
            "avg_lead_time_days": diagnostics["summary"]["avg_lead_time_days"],
            "value_added_ratio": diagnostics["summary"]["value_added_ratio"],
            "bottleneck_node": diagnostics["summary"]["bottleneck_node"],
            "abnormal_batches": diagnostics["summary"]["abnormal_batches"],
        },
        "baseline": baseline["summary"],
        "diagnostics": diagnostics,
        "route_plan": route_plan,
        "batches": batches,
        "model_metadata": build_model_metadata(),
    }


def label_setting_shortest_path(
    graph: dict[str, list[dict[str, Any]]],
    start_node: str,
    end_node: str,
    max_allowed_days: float,
) -> dict[str, Any] | None:
    queue: list[tuple[float, float, str, list[dict[str, Any]]]] = [(0.0, 0.0, start_node, [])]
    best_seen: dict[tuple[str, int], float] = {}
    while queue:
        cost, time_days, node, path = heapq.heappop(queue)
        if node == end_node:
            return serialize_path(path)
        if time_days > max_allowed_days:
            continue
        for edge in graph.get(node, []):
            if any(step["start_node"] == edge["end_node"] for step in path):
                continue
            next_time = time_days + edge["time_days"]
            next_cost = cost + edge["cost"]
            if next_time > max_allowed_days:
                continue
            key = (edge["end_node"], int(next_time * 10))
            if best_seen.get(key, math.inf) <= next_cost:
                continue
            best_seen[key] = next_cost
            heapq.heappush(queue, (next_cost, next_time, edge["end_node"], [*path, edge]))
    return None


def enumerate_paths(graph: dict[str, list[dict[str, Any]]], start: str, end: str) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []

    def visit(node: str, path: list[dict[str, Any]], seen: set[str]) -> None:
        if node == end:
            paths.append(serialize_path(path))
            return
        for edge in graph.get(node, []):
            if edge["end_node"] in seen:
                continue
            visit(edge["end_node"], [*path, edge], {*seen, edge["end_node"]})

    visit(start, [], {start})
    return paths


def serialize_path(path: list[dict[str, Any]]) -> dict[str, Any]:
    if not path:
        return {"nodes": [], "legs": [], "time_days": 0.0, "cost": 0.0, "carriers": []}
    nodes = [path[0]["start_node"], *[edge["end_node"] for edge in path]]
    carriers = list(dict.fromkeys(edge["carrier_name"] for edge in path))
    return {
        "nodes": nodes,
        "legs": [
            {
                "start_node": edge["start_node"],
                "end_node": edge["end_node"],
                "carrier_name": edge["carrier_name"],
                "time_days": round(edge["time_days"], 2),
                "cost": round(edge["cost"], 2),
                "route_tag": edge["route_tag"],
            }
            for edge in path
        ],
        "time_days": round(sum(edge["time_days"] for edge in path), 2),
        "cost": round(sum(edge["cost"] for edge in path), 2),
        "carriers": carriers,
    }


def weighted_route_score(route: dict[str, Any], routes: list[dict[str, Any]], max_allowed_days: float) -> float:
    min_cost = min(item["cost"] for item in routes)
    max_cost = max(item["cost"] for item in routes)
    min_time = min(item["time_days"] for item in routes)
    max_time = max(item["time_days"] for item in routes)
    cost_score = (route["cost"] - min_cost) / (max_cost - min_cost or 1)
    time_score = (route["time_days"] - min_time) / (max_time - min_time or 1)
    infeasible_penalty = 0.65 if route["time_days"] > max_allowed_days else 0
    return cost_score * 0.45 + time_score * 0.4 + infeasible_penalty


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def estimate_abnormal_batches(stages: list[dict[str, Any]], records: list[dict[str, Any]]) -> int:
    risk_multiplier = sum(1.8 if row["status"] == "瓶颈" else 0.9 if row["status"] == "预警" else 0.25 for row in stages)
    return max(0, round(len(records) * min(0.36, risk_multiplier / 18)))


def build_advice(bottleneck: dict[str, Any], scenario_cfg: dict[str, Any]) -> str:
    node = bottleneck["stage_name"]
    cv = bottleneck["coefficient_of_variation"]
    load = bottleneck["load_factor"]
    if scenario_cfg["node_id"]:
        return f"当前异常场景为【{scenario_cfg['name']}】，系统约束位于【{node}】。建议先冻结前序放行节奏，保护瓶颈节点产能，并启用备用承运/备用仓方案。"
    if load > 1:
        return f"当前链路瓶颈位于【{node}】，负荷率已超过 100%。建议增加临时班次或拆分批次进入备用处理区。"
    if cv > 0.35:
        return f"当前链路瓶颈位于【{node}】，主要风险来自时效波动。建议提高到货预约准确度并设置缓冲库存。"
    return f"当前链路瓶颈位于【{node}】，建议优先保障该节点人员、设备和承运资源，避免局部等待放大全链路交期。"
