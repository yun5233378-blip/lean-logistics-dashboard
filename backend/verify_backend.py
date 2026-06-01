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
    assert runtime_payload["users"]
    assert runtime_payload["external_shipments"]["total"]["count"] >= 5

    parameter = client.put(
        "/api/admin/model-parameters/route_cost_weight",
        headers=headers,
        json={"value": "0.46"},
    )
    assert parameter.status_code == 200, parameter.text
    assert parameter.json()["value"] == "0.46"

    backup = client.post("/api/admin/backup", headers=headers)
    assert backup.status_code == 200, backup.text
    assert backup.json()["database_backend"] in {"sqlite", "postgresql"}

    print("backend verification passed")


if __name__ == "__main__":
    main()
