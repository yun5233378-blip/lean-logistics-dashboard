from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "精益物流决策看板 API"
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    admin_api_token: str = os.getenv("ADMIN_API_TOKEN", "dev-admin-token").strip()
    backup_dir: Path = Path(os.getenv("BACKUP_DIR", ROOT_DIR / "backups"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    enable_online_imports: bool = env_bool("ENABLE_ONLINE_IMPORTS", True)
    usaid_shipments_endpoint: str = os.getenv(
        "USAID_SHIPMENTS_ENDPOINT",
        "https://data.usaid.gov/resource/mm7d-nzmf.json",
    ).strip()
    default_import_limit: int = int(os.getenv("DEFAULT_IMPORT_LIMIT", "80"))

    @property
    def database_backend(self) -> str:
        if self.database_url.startswith(("postgres://", "postgresql://")):
            return "postgresql"
        return "sqlite"

    @property
    def auth_mode(self) -> str:
        if self.admin_api_token == "dev-admin-token":
            return "development-default-token"
        return "configured-token"


settings = Settings()
