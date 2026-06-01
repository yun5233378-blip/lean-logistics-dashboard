from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .admin import backup_now, create_user, list_users, rebuild_data_index, runtime_status, update_model_parameter
from .database import init_db
from .engines import ANOMALIES, build_dashboard, build_model_metadata, diagnose_bottlenecks, list_batches, optimize_route
from .integrations import import_usaid_shipments
from .settings import settings


ROOT_DIR = Path(__file__).resolve().parents[1]
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("lean-logistics")

app = FastAPI(
    title=settings.app_name,
    description="LeanLogiLens prototype backend: lead-time analytics, TOC bottleneck diagnostics, and route optimization.",
    version="0.2.0",
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
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info("%s %s %s %sms", request.method, request.url.path, response.status_code, elapsed_ms)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


class ParameterUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=80)


class UserCreate(BaseModel):
    user_id: str = Field(min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=40)
    role: str = Field(min_length=2, max_length=24)
    project_scope: str = Field(min_length=1, max_length=80)


class ImportRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=5000)


def require_admin(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> dict[str, str]:
    token = x_admin_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token or token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要管理员 Token 才能访问后台接口。",
        )
    return {"role": "admin", "auth_mode": settings.auth_mode}


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
    return {"status": "ok", "service": settings.app_name, "database_backend": settings.database_backend}


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


@app.get("/api/sources")
def sources() -> dict[str, object]:
    return build_model_metadata()


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
    start_node: Annotated[str, Query(description="起点节点")] = "中国",
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
def reset_real_data() -> dict[str, str]:
    init_db(reset=True)
    return {"status": "ok", "message": "真实公开数据索引已重建"}


@app.get("/api/ops/status")
def ops_status() -> dict[str, object]:
    payload = runtime_status()
    return {
        "status": "ok",
        "database_backend": payload["database_backend"],
        "online_imports_enabled": payload["online_imports_enabled"],
        "external_shipments": payload["external_shipments"],
        "latest_imports": payload["imports"][:3],
    }


@app.get("/api/admin/runtime")
def admin_runtime(_: Annotated[dict[str, str], Depends(require_admin)]) -> dict[str, Any]:
    return runtime_status()


@app.put("/api/admin/model-parameters/{key}")
def admin_update_parameter(
    key: str,
    payload: ParameterUpdate,
    _: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return update_model_parameter(key, payload.value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模型参数不存在") from exc


@app.get("/api/admin/users")
def admin_users(_: Annotated[dict[str, str], Depends(require_admin)]) -> dict[str, Any]:
    return {"items": list_users()}


@app.post("/api/admin/users")
def admin_create_user(
    payload: UserCreate,
    _: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, Any]:
    try:
        return create_user(payload.user_id, payload.display_name, payload.role, payload.project_scope)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="用户已存在或字段不合法") from exc


@app.post("/api/admin/data/import/usaid")
def admin_import_usaid(
    payload: ImportRequest,
    _: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, Any]:
    return import_usaid_shipments(payload.limit)


@app.post("/api/admin/data/reset")
def admin_reset_data(_: Annotated[dict[str, str], Depends(require_admin)]) -> dict[str, str]:
    return rebuild_data_index()


@app.post("/api/admin/backup")
def admin_backup(_: Annotated[dict[str, str], Depends(require_admin)]) -> dict[str, Any]:
    return backup_now()


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    return FileResponse(ROOT_DIR / "index.html")
