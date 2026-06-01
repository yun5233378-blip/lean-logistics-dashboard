from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import (
    finish_import_job,
    fetch_one,
    insert_import_job,
    upsert_fulfillment_records,
)


SOURCE_ID = "BUSINESS_UPLOAD"

FIELD_ALIASES = {
    "batch_no": ["batch_no", "batch", "shipment_id", "order_no", "tracking_no", "运单号", "批次号", "订单号"],
    "channel_type": ["channel_type", "channel", "mode", "shipment_mode", "运输方式", "渠道"],
    "origin": ["origin", "from", "起点", "始发地"],
    "destination": ["destination", "country", "to", "目的地", "目的国"],
    "piece_count": ["piece_count", "pieces", "quantity", "qty", "件数", "票数"],
    "cbm": ["cbm", "volume_cbm", "volume", "体积", "方数"],
    "volume_index": ["volume_index", "volume_score", "货量指数"],
    "ts_order_created": ["ts_order_created", "order_created_at", "created_at", "下单时间", "订单创建时间"],
    "ts_domestic_out": ["ts_domestic_out", "domestic_out_at", "国内出库时间"],
    "ts_head_arrive": ["ts_head_arrive", "head_arrive_at", "头程到达时间"],
    "ts_customs_clear": ["ts_customs_clear", "customs_clear_at", "清关完成时间"],
    "ts_oversea_in": ["ts_oversea_in", "oversea_in_at", "海外仓入库时间"],
    "ts_last_mile_del": ["ts_last_mile_del", "delivered_at", "delivery_at", "妥投时间", "签收时间"],
    "lead_time_days": ["lead_time_days", "total_days", "交付天数", "全链路天数"],
    "source_url": ["source_url", "数据来源"],
    "evidence_note": ["evidence_note", "备注", "数据说明"],
}

STAGE_RATIO = {
    "ts_domestic_out": 0.06,
    "ts_head_arrive": 0.52,
    "ts_customs_clear": 0.65,
    "ts_oversea_in": 0.78,
}


def import_business_records(payload: dict[str, Any], actor_id: str = "admin") -> dict[str, Any]:
    rows = load_payload_rows(payload)
    max_rows = get_business_import_limit()
    if len(rows) > max_rows:
        rows = rows[:max_rows]

    job_id = insert_import_job(SOURCE_ID, len(rows))
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for index, row in enumerate(rows, start=1):
            try:
                normalized.append(normalize_business_row(row, index, actor_id))
            except ValueError as exc:
                errors.append(str(exc))

        imported_count = upsert_fulfillment_records(normalized)
        status = "partial" if errors else "success"
        finish_import_job(job_id, status, imported_count, "; ".join(errors[:8]) if errors else None)
        return {
            "status": status,
            "job_id": job_id,
            "source_id": SOURCE_ID,
            "requested_limit": len(rows),
            "imported_count": imported_count,
            "rejected_count": len(errors),
            "errors": errors[:8],
            "message": f"业务数据导入完成：写入 {imported_count} 条，拒绝 {len(errors)} 条。",
        }
    except Exception as exc:
        finish_import_job(job_id, "failed", 0, str(exc))
        return {
            "status": "failed",
            "job_id": job_id,
            "source_id": SOURCE_ID,
            "requested_limit": len(rows),
            "imported_count": 0,
            "rejected_count": len(rows),
            "errors": [str(exc)],
            "message": "业务数据导入失败。",
        }


def load_payload_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fmt = str(payload.get("format") or "json").lower()
    if fmt == "csv":
        content = str(payload.get("content") or "").lstrip("\ufeff")
        if not content.strip():
            raise ValueError("CSV 内容为空")
        return [dict(row) for row in csv.DictReader(io.StringIO(content))]
    records = payload.get("records")
    if records is None and payload.get("content"):
        decoded = json.loads(str(payload["content"]))
        records = decoded.get("records") if isinstance(decoded, dict) else decoded
    if not isinstance(records, list):
        raise ValueError("JSON 导入需要 records 数组")
    return [dict(row) for row in records if isinstance(row, dict)]


def normalize_business_row(row: dict[str, Any], index: int, actor_id: str) -> dict[str, Any]:
    batch_no = pick(row, "batch_no")
    destination = pick(row, "destination")
    if not batch_no:
        raise ValueError(f"第 {index} 行缺少 batch_no/运单号")
    if not destination:
        raise ValueError(f"第 {index} 行缺少 destination/目的地")

    timestamps = normalize_timestamps(row, index)
    piece_count = parse_int(pick(row, "piece_count"), default=1)
    cbm = parse_float(pick(row, "cbm"), default=max(0.01, piece_count / 48))
    return {
        "batch_no": str(batch_no).strip(),
        "channel_type": str(pick(row, "channel_type") or "未分类").strip(),
        "origin": str(pick(row, "origin") or "业务系统").strip(),
        "destination": str(destination).strip(),
        "piece_count": piece_count,
        "cbm": cbm,
        "volume_index": parse_int(pick(row, "volume_index"), default=piece_count),
        "source_id": SOURCE_ID,
        "source_year": timestamps["source_year"],
        "source_url": str(pick(row, "source_url") or "user-upload://fulfillment-records"),
        "record_type": "业务导入运单",
        "evidence_note": str(pick(row, "evidence_note") or f"由 {actor_id} 通过后台导入。"),
        **{key: timestamps[key] for key in (
            "ts_order_created",
            "ts_domestic_out",
            "ts_head_arrive",
            "ts_customs_clear",
            "ts_oversea_in",
            "ts_last_mile_del",
        )},
    }


def normalize_timestamps(row: dict[str, Any], index: int) -> dict[str, Any]:
    created = parse_datetime(pick(row, "ts_order_created"))
    delivered = parse_datetime(pick(row, "ts_last_mile_del"))
    lead_time_days = parse_float(pick(row, "lead_time_days"), default=None)
    if not delivered and created and lead_time_days is not None:
        delivered = created + timedelta(days=lead_time_days)
    if not created and delivered and lead_time_days is not None:
        created = delivered - timedelta(days=lead_time_days)
    if not created or not delivered:
        raise ValueError(f"第 {index} 行缺少可识别的创建/妥投时间")
    if delivered <= created:
        raise ValueError(f"第 {index} 行妥投时间必须晚于创建时间")

    timestamps = {
        "ts_order_created": created,
        "ts_domestic_out": parse_datetime(pick(row, "ts_domestic_out")),
        "ts_head_arrive": parse_datetime(pick(row, "ts_head_arrive")),
        "ts_customs_clear": parse_datetime(pick(row, "ts_customs_clear")),
        "ts_oversea_in": parse_datetime(pick(row, "ts_oversea_in")),
        "ts_last_mile_del": delivered,
    }
    total_seconds = (delivered - created).total_seconds()
    for key, ratio in STAGE_RATIO.items():
        if not timestamps[key]:
            timestamps[key] = created + timedelta(seconds=total_seconds * ratio)

    ordered = [
        timestamps["ts_order_created"],
        timestamps["ts_domestic_out"],
        timestamps["ts_head_arrive"],
        timestamps["ts_customs_clear"],
        timestamps["ts_oversea_in"],
        timestamps["ts_last_mile_del"],
    ]
    if any(later <= earlier for earlier, later in zip(ordered, ordered[1:])):
        raise ValueError(f"第 {index} 行节点时间顺序不合法")
    return {key: to_iso(value) for key, value in timestamps.items()} | {"source_year": created.year}


def pick(row: dict[str, Any], field: str) -> Any:
    lookup = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field]:
        value = lookup.get(alias.lower())
        if value not in (None, ""):
            return value
    return None


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            parsed = parser(raw)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def to_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds")


def parse_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return default


def parse_int(value: Any, default: int = 0) -> int:
    parsed = parse_float(value, default=float(default))
    return int(round(parsed or default))


def get_business_import_limit() -> int:
    row = fetch_one("SELECT value FROM model_parameters WHERE key = ?", ("business_import_max_rows",))
    try:
        return max(1, min(int(row["value"]) if row else 2000, 10000))
    except (TypeError, ValueError):
        return 2000
