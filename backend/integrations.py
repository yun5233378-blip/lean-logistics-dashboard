from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .database import finish_import_job, insert_import_job, upsert_external_shipments
from .settings import settings


USAID_SOURCE_ID = "USAID_SCMS_REFERENCE"


def parse_float(value: Any) -> float | None:
    if value in (None, "", "Freight Included in Commodity Cost"):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:26], fmt)
        except ValueError:
            continue
    return None


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def normalize_usaid_row(row: dict[str, Any]) -> dict[str, Any] | None:
    record_id = first_present(row, "id", ":id", "row_id")
    country = first_present(row, "country", "destination_country")
    mode = first_present(row, "shipment_mode", "mode_of_shipment", "fulfill_via") or "未知"
    scheduled = first_present(row, "scheduled_delivery_date")
    delivered = first_present(row, "delivered_to_client_date", "delivery_recorded_date")
    scheduled_dt = parse_date(scheduled)
    delivered_dt = parse_date(delivered)
    lead_time_days = None
    if scheduled_dt and delivered_dt:
        lead_time_days = max(0.0, (delivered_dt - scheduled_dt).total_seconds() / 86400)

    if not record_id or not country:
        return None

    return {
        "source_id": USAID_SOURCE_ID,
        "source_record_id": str(record_id),
        "destination_country": str(country),
        "shipment_mode": str(mode),
        "lead_time_days": round(lead_time_days, 2) if lead_time_days is not None else None,
        "freight_cost_usd": parse_float(first_present(row, "freight_cost_usd", "freight_cost")),
        "line_item_value_usd": parse_float(first_present(row, "line_item_value", "line_item_value_usd")),
        "weight_kg": parse_float(first_present(row, "weight_kilograms", "weight_kg")),
        "scheduled_delivery_date": str(scheduled) if scheduled else None,
        "delivered_to_client_date": str(delivered) if delivered else None,
        "raw_payload": row,
    }


def import_usaid_shipments(limit: int | None = None) -> dict[str, Any]:
    if not settings.enable_online_imports:
        return {
            "status": "disabled",
            "source_id": USAID_SOURCE_ID,
            "imported_count": 0,
            "message": "在线导入已通过 ENABLE_ONLINE_IMPORTS 关闭。",
        }

    requested_limit = max(1, min(limit or settings.default_import_limit, 5000))
    job_id = insert_import_job(USAID_SOURCE_ID, requested_limit)
    try:
        params = {
            "$limit": requested_limit,
            "$order": "id",
        }
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(settings.usaid_shipments_endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
        rows = [item for item in (normalize_usaid_row(row) for row in payload) if item]
        imported_count = upsert_external_shipments(rows)
        finish_import_job(job_id, "success", imported_count)
        return {
            "status": "success",
            "job_id": job_id,
            "source_id": USAID_SOURCE_ID,
            "requested_limit": requested_limit,
            "imported_count": imported_count,
            "endpoint": settings.usaid_shipments_endpoint,
        }
    except Exception as exc:
        finish_import_job(job_id, "failed", 0, str(exc))
        return {
            "status": "failed",
            "job_id": job_id,
            "source_id": USAID_SOURCE_ID,
            "requested_limit": requested_limit,
            "imported_count": 0,
            "endpoint": settings.usaid_shipments_endpoint,
            "error": str(exc),
        }
