from __future__ import annotations

from typing import Any

from .database import create_backup, execute_write, fetch_all, fetch_one, init_db, utc_now
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
        "users": list_users(),
        "imports": list_import_jobs(),
        "external_shipments": external_shipments_summary(),
    }


def rebuild_data_index() -> dict[str, str]:
    init_db(reset=True)
    return {"status": "ok", "message": "真实公开数据索引已重建"}


def backup_now() -> dict[str, Any]:
    return create_backup()
