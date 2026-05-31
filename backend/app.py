from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .database import init_db
from .engines import ANOMALIES, build_dashboard, diagnose_bottlenecks, list_batches, optimize_route


ROOT_DIR = Path(__file__).resolve().parents[1]

app = FastAPI(
    title="精益物流决策看板 API",
    description="LeanLogiLens prototype backend: lead-time analytics, TOC bottleneck diagnostics, and route optimization.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_runtime_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(ROOT_DIR / "index.html")


@app.head("/", include_in_schema=False)
def frontend_head() -> Response:
    return Response(status_code=200)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "精益物流决策看板 API"}


@app.head("/api/health", include_in_schema=False)
def health_head() -> Response:
    return Response(status_code=200)


@app.get("/api/options")
def options() -> dict[str, object]:
    return {
        "channels": ["全部渠道", "空运", "海运", "快递"],
        "destinations": ["全部目的地", "美国", "德国", "英国", "日本"],
        "scenarios": [{"id": key, "name": value["name"], "summary": value["summary"]} for key, value in ANOMALIES.items()],
    }


@app.get("/api/dashboard")
def dashboard(
    channel_type: Annotated[str | None, Query(description="渠道类型：全部渠道/空运/海运/快递")] = "全部渠道",
    destination: Annotated[str | None, Query(description="目的地：全部目的地/美国/德国/英国/日本")] = "全部目的地",
    scenario: Annotated[str, Query(description="异常场景：none/customs/warehouse/port/lastmile")] = "none",
    max_allowed_days: Annotated[float, Query(ge=1, le=30, description="期望交期约束，单位天")] = 8.0,
) -> dict[str, object]:
    return build_dashboard(channel_type, destination, scenario, max_allowed_days)


@app.get("/api/diagnostics")
def diagnostics(
    channel_type: Annotated[str | None, Query(description="渠道类型")] = "全部渠道",
    destination: Annotated[str | None, Query(description="目的地")] = "全部目的地",
    scenario: Annotated[str, Query(description="异常场景")] = "none",
) -> dict[str, object]:
    return diagnose_bottlenecks(channel_type, destination, scenario)


@app.get("/api/routes/optimize")
def routes_optimize(
    start_node: Annotated[str, Query(description="起点节点")] = "深圳工厂",
    end_node: Annotated[str, Query(description="终点节点")] = "美东海外仓",
    max_allowed_days: Annotated[float, Query(ge=1, le=30, description="最大允许交期，单位天")] = 8.0,
    scenario: Annotated[str, Query(description="异常场景")] = "none",
    cargo_cbm: Annotated[float, Query(gt=0, le=100, description="货物体积，CBM")] = 1.0,
) -> dict[str, object]:
    return optimize_route(start_node, end_node, max_allowed_days, scenario, cargo_cbm)


@app.get("/api/batches")
def batches(
    channel_type: Annotated[str | None, Query(description="渠道类型")] = "全部渠道",
    destination: Annotated[str | None, Query(description="目的地")] = "全部目的地",
    scenario: Annotated[str, Query(description="异常场景")] = "none",
    risk_level: Annotated[str | None, Query(description="风险等级：全部风险/高风险/中风险/低风险")] = "全部风险",
    limit: Annotated[int, Query(ge=1, le=200)] = 80,
) -> dict[str, object]:
    return list_batches(channel_type, destination, scenario, risk_level, limit)


@app.post("/api/dev/reset")
def reset_mock_data() -> dict[str, str]:
    init_db(reset=True)
    return {"status": "ok", "message": "Mock 数据已重置"}


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    return FileResponse(ROOT_DIR / "index.html")
