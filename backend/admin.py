from __future__ import annotations

import json
from typing import Any

from .database import create_backup, execute_write, fetch_all, fetch_one, init_db, list_backup_files, utc_now
from .settings import settings


def list_model_parameters() -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all("SELECT * FROM model_parameters ORDER BY key")]


def update_model_parameter(key: str, value: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM model_parameters WHERE key = ?", (key,))
    if not row:
        raise KeyError(key)
    execute_write(
        "UPDATE model_parameters SET value = ?, updated_at = ? WHERE key = ?",
        (value, utc_now(), key),
    )
    updated = fetch_one("SELECT * FROM model_parameters WHERE key = ?", (key,))
    return dict(updated)


def list_node_capacities() -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all("SELECT * FROM node_capacities ORDER BY node_id")]


def update_node_capacity(node_id: str, daily_capacity: int, target_lead_time: float) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM node_capacities WHERE node_id = ?", (node_id,))
    if not row:
        raise KeyError(node_id)
    execute_write(
        """
        UPDATE node_capacities
        SET daily_capacity = ?, target_lead_time = ?
        WHERE node_id = ?
        """,
        (daily_capacity, target_lead_time, node_id),
    )
    updated = fetch_one("SELECT * FROM node_capacities WHERE node_id = ?", (node_id,))
    return dict(updated)


def list_users() -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all("SELECT * FROM app_users ORDER BY created_at, user_id")]


def create_user(user_id: str, display_name: str, role: str, project_scope: str) -> dict[str, Any]:
    execute_write(
        """
        INSERT INTO app_users (user_id, display_name, role, project_scope, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, display_name, role, project_scope, "active", utc_now()),
    )
    row = fetch_one("SELECT * FROM app_users WHERE user_id = ?", (user_id,))
    return dict(row)


def list_import_jobs(limit: int = 12) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            "SELECT * FROM import_jobs ORDER BY job_id DESC LIMIT ?",
            (limit,),
        )
    ]


def list_audit_logs(limit: int = 30) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in fetch_all(
            "SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?",
            (limit,),
        )
    ]


def write_audit_log(
    actor_id: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    status: str = "success",
    detail: dict[str, Any] | str | None = None,
) -> None:
    payload = detail if isinstance(detail, str) else json.dumps(detail or {}, ensure_ascii=False)
    execute_write(
        """
        INSERT INTO audit_logs (actor_id, action, target_type, target_id, status, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (actor_id, action, target_type, target_id, status, payload[:4000], utc_now()),
    )


def list_operational_schedules() -> list[dict[str, Any]]:
    return [dict(row) for row in fetch_all("SELECT * FROM operational_schedules ORDER BY schedule_id")]


def update_operational_schedule(
    schedule_id: str,
    enabled: bool | None = None,
    cron_hint: str | None = None,
    next_run_hint: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM operational_schedules WHERE schedule_id = ?", (schedule_id,))
    if not row:
        raise KeyError(schedule_id)
    next_values = {
        "enabled": int(enabled) if enabled is not None else row["enabled"],
        "cron_hint": cron_hint if cron_hint is not None else row["cron_hint"],
        "next_run_hint": next_run_hint if next_run_hint is not None else row["next_run_hint"],
        "notes": notes if notes is not None else row["notes"],
    }
    execute_write(
        """
        UPDATE operational_schedules
        SET enabled = ?, cron_hint = ?, next_run_hint = ?, notes = ?, updated_at = ?
        WHERE schedule_id = ?
        """,
        (
            next_values["enabled"],
            next_values["cron_hint"],
            next_values["next_run_hint"],
            next_values["notes"],
            utc_now(),
            schedule_id,
        ),
    )
    updated = fetch_one("SELECT * FROM operational_schedules WHERE schedule_id = ?", (schedule_id,))
    return dict(updated)


def run_operational_schedule(schedule_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM operational_schedules WHERE schedule_id = ?", (schedule_id,))
    if not row:
        raise KeyError(schedule_id)
    job_type = row["job_type"]
    if job_type == "usaid_import":
        from .integrations import import_usaid_shipments

        result = import_usaid_shipments(settings.default_import_limit)
    elif job_type == "database_backup":
        result = create_backup()
    else:
        result = {"status": "skipped", "message": f"未知任务类型：{job_type}"}
    status = str(result.get("status") or result.get("mode") or "success")
    execute_write(
        """
        UPDATE operational_schedules
        SET last_run_at = ?, last_status = ?, updated_at = ?
        WHERE schedule_id = ?
        """,
        (utc_now(), status, utc_now(), schedule_id),
    )
    return {"schedule": dict(fetch_one("SELECT * FROM operational_schedules WHERE schedule_id = ?", (schedule_id,))), "result": result}


def external_shipments_summary() -> dict[str, Any]:
    total = fetch_one(
        """
        SELECT
            COUNT(*) AS count,
            AVG(lead_time_days) AS avg_lead_time_days,
            AVG(freight_cost_usd) AS avg_freight_cost_usd,
            AVG(weight_kg) AS avg_weight_kg
        FROM external_shipments
        """
    )
    by_mode = fetch_all(
        """
        SELECT shipment_mode, COUNT(*) AS count, AVG(lead_time_days) AS avg_lead_time_days
        FROM external_shipments
        GROUP BY shipment_mode
        ORDER BY count DESC
        LIMIT 8
        """
    )
    by_country = fetch_all(
        """
        SELECT destination_country, COUNT(*) AS count, AVG(lead_time_days) AS avg_lead_time_days
        FROM external_shipments
        GROUP BY destination_country
        ORDER BY count DESC
        LIMIT 8
        """
    )
    return {
        "total": dict(total) if total else {"count": 0},
        "by_mode": [dict(row) for row in by_mode],
        "by_country": [dict(row) for row in by_country],
    }


def runtime_status() -> dict[str, Any]:
    return {
        "database_backend": settings.database_backend,
        "auth_mode": settings.auth_mode,
        "online_imports_enabled": settings.enable_online_imports,
        "usaid_endpoint": settings.usaid_shipments_endpoint,
        "backup_dir": str(settings.backup_dir),
        "model_parameters": list_model_parameters(),
        "node_capacities": list_node_capacities(),
        "users": list_users(),
        "imports": list_import_jobs(),
        "schedules": list_operational_schedules(),
        "audit_logs": list_audit_logs(),
        "backups": list_backup_files(),
        "external_shipments": external_shipments_summary(),
    }


def rebuild_data_index() -> dict[str, str]:
    init_db(reset=True)
    return {"status": "ok", "message": "真实公开数据索引已重建"}


def backup_now() -> dict[str, Any]:
    return create_backup()
