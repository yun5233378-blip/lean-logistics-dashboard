from __future__ import annotations

from fastapi.testclient import TestClient

from .app import app
from .database import init_db
from .settings import settings


def main() -> None:
    init_db(reset=True)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "ok"

    root_head = client.head("/")
    assert root_head.status_code == 200, root_head.text

    health_head = client.head("/api/health")
    assert health_head.status_code == 200, health_head.text

    frontend = client.get("/diagnostics")
    assert frontend.status_code == 200, frontend.text
    assert "精益物流决策看板" in frontend.text

    sources = client.get("/api/sources")
    assert sources.status_code == 200, sources.text
    source_payload = sources.json()
    assert source_payload["data_mode"] == "真实公开数据驱动"
    assert any(item["source_id"] == "WB_LPI_2022" for item in source_payload["sources"])

    diag = client.get("/api/diagnostics", params={"scenario": "warehouse"})
    assert diag.status_code == 200, diag.text
    payload = diag.json()
    assert payload["stages"], "diagnostics should return stage rows"
    assert payload["summary"]["bottleneck_node"]["stage_id"] == "Oversea_Inbound"

    route = client.get("/api/routes/optimize", params={"scenario": "warehouse", "max_allowed_days": 4})
    assert route.status_code == 200, route.text
    route_payload = route.json()
    assert route_payload["fallback"] is True
    assert route_payload["selected_route"]["nodes"][0] == "中国"

    dashboard = client.get("/api/dashboard", params={"scenario": "customs", "channel_type": "空运"})
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["kpis"]["bottleneck_node"]
    assert dashboard.json()["model_metadata"]["data_mode"] == "真实公开数据驱动"

    batches = client.get("/api/batches", params={"risk_level": "高风险", "limit": 10})
    assert batches.status_code == 200, batches.text
    assert "items" in batches.json()

    ops = client.get("/api/ops/status")
    assert ops.status_code == 200, ops.text
    assert "external_shipments" in ops.json()
    assert ops.json()["external_shipments"]["total"]["count"] >= 5

    unauthorized = client.get("/api/admin/runtime")
    assert unauthorized.status_code == 401

    headers = {"Authorization": f"Bearer {settings.admin_api_token}"}
    runtime = client.get("/api/admin/runtime", headers=headers)
    assert runtime.status_code == 200, runtime.text
    runtime_payload = runtime.json()
    assert runtime_payload["database_backend"] in {"sqlite", "postgresql"}
    assert runtime_payload["model_parameters"]
    assert runtime_payload["node_capacities"]
    assert runtime_payload["users"]
    assert runtime_payload["schedules"]
    assert "backups" in runtime_payload
    assert "audit_logs" in runtime_payload
    assert runtime_payload["external_shipments"]["total"]["count"] >= 5

    parameter = client.put(
        "/api/admin/model-parameters/route_cost_weight",
        headers=headers,
        json={"value": "0.46"},
    )
    assert parameter.status_code == 200, parameter.text
    assert parameter.json()["value"] == "0.46"

    business_import = client.post(
        "/api/admin/data/import/business",
        headers=headers,
        json={
            "format": "json",
            "records": [
                {
                    "batch_no": "BIZ-VERIFY-001",
                    "channel_type": "空运",
                    "origin": "深圳",
                    "destination": "美国",
                    "piece_count": 24,
                    "cbm": 1.2,
                    "ts_order_created": "2026-05-01T08:00:00",
                    "ts_domestic_out": "2026-05-01T18:00:00",
                    "ts_head_arrive": "2026-05-05T09:00:00",
                    "ts_customs_clear": "2026-05-06T12:00:00",
                    "ts_oversea_in": "2026-05-07T15:00:00",
                    "ts_last_mile_del": "2026-05-09T11:00:00",
                }
            ],
        },
    )
    assert business_import.status_code == 200, business_import.text
    assert business_import.json()["imported_count"] == 1

    imported_batch = client.get("/api/batches", params={"destination": "美国", "limit": 200})
    assert imported_batch.status_code == 200, imported_batch.text
    assert any(item["batch_no"] == "BIZ-VERIFY-001" for item in imported_batch.json()["items"])

    capacity = client.put(
        "/api/admin/node-capacities/Oversea_Inbound",
        headers=headers,
        json={"daily_capacity": 512, "target_lead_time": 22.5},
    )
    assert capacity.status_code == 200, capacity.text
    assert capacity.json()["daily_capacity"] == 512

    schedule = client.put(
        "/api/admin/schedules/nightly_database_backup",
        headers=headers,
        json={"enabled": True, "next_run_hint": "每日 02:30"},
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["enabled"] == 1

    schedule_run = client.post("/api/admin/schedules/nightly_database_backup/run", headers=headers)
    assert schedule_run.status_code == 200, schedule_run.text
    assert "result" in schedule_run.json()

    backup = client.post("/api/admin/backup", headers=headers)
    assert backup.status_code == 200, backup.text
    assert backup.json()["database_backend"] in {"sqlite", "postgresql"}
    assert backup.json()["filename"]

    backups = client.get("/api/admin/backups", headers=headers)
    assert backups.status_code == 200, backups.text
    assert backups.json()["items"]

    audit_logs = client.get("/api/admin/audit-logs", headers=headers)
    assert audit_logs.status_code == 200, audit_logs.text
    assert len(audit_logs.json()["items"]) >= 3

    print("backend verification passed")


if __name__ == "__main__":
    main()
