from __future__ import annotations

from fastapi.testclient import TestClient

from .app import app
from .database import init_db


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

    diag = client.get("/api/diagnostics", params={"scenario": "warehouse"})
    assert diag.status_code == 200, diag.text
    payload = diag.json()
    assert payload["stages"], "diagnostics should return stage rows"
    assert payload["summary"]["bottleneck_node"]["stage_id"] == "Oversea_Inbound"

    route = client.get("/api/routes/optimize", params={"scenario": "warehouse", "max_allowed_days": 4})
    assert route.status_code == 200, route.text
    route_payload = route.json()
    assert route_payload["fallback"] is True
    assert route_payload["selected_route"]["nodes"][0] == "深圳工厂"

    dashboard = client.get("/api/dashboard", params={"scenario": "customs", "channel_type": "空运"})
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["kpis"]["bottleneck_node"]

    batches = client.get("/api/batches", params={"risk_level": "高风险", "limit": 10})
    assert batches.status_code == 200, batches.text
    assert "items" in batches.json()

    print("backend verification passed")


if __name__ == "__main__":
    main()
