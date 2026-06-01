from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .settings import ROOT_DIR, settings


DB_PATH = ROOT_DIR / "lean_logistics.db"
SEED_PATH = ROOT_DIR / "data" / "real_logistics_seed.json"
SCMS_SAMPLE_PATH = ROOT_DIR / "data" / "scms_delivery_history_sample.json"
SCHEMA_VERSION = 3


def is_postgres() -> bool:
    return settings.database_backend == "postgresql"


def normalize_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def translate_query(query: str) -> str:
    return query.replace("?", "%s") if is_postgres() else query


@contextmanager
def connect() -> Iterator[Any]:
    if is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL mode requires psycopg[binary] in requirements.txt") from exc

        conn = psycopg.connect(normalize_pg_url(settings.database_url), row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def execute(conn: Any, query: str, params: Sequence[object] = ()) -> Any:
    return conn.execute(translate_query(query), tuple(params))


def executemany(conn: Any, query: str, rows: Iterable[Sequence[object]]) -> None:
    conn.executemany(translate_query(query), list(rows))


def execute_script(conn: Any, statements: str) -> None:
    if is_postgres():
        with conn.cursor() as cur:
            for statement in [part.strip() for part in statements.split(";") if part.strip()]:
                cur.execute(statement)
    else:
        conn.executescript(statements)


def init_db(reset: bool = False) -> None:
    with connect() as conn:
        if reset or current_schema_version(conn) != SCHEMA_VERSION:
            drop_tables(conn)

        create_tables(conn)
        has_data = execute(conn, "SELECT COUNT(*) AS count FROM fulfillment_records").fetchone()["count"] > 0
        if not has_data:
            seed_data(conn)
        seed_default_admin_config(conn)
        upsert_schema_meta(conn, "schema_version", str(SCHEMA_VERSION))


def current_schema_version(conn: Any) -> int:
    if not table_exists(conn, "schema_meta"):
        return 0
    value = execute(conn, "SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    raw = value["value"] if value else "0"
    return int(raw) if str(raw).isdigit() else 0


def table_exists(conn: Any, name: str) -> bool:
    if is_postgres():
        row = execute(
            conn,
            "SELECT to_regclass(?) AS table_name",
            (f"public.{name}",),
        ).fetchone()
        return bool(row and row["table_name"])
    row = execute(conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return bool(row)


def drop_tables(conn: Any) -> None:
    suffix = " CASCADE" if is_postgres() else ""
    execute_script(
        conn,
        f"""
        DROP TABLE IF EXISTS external_shipments{suffix};
        DROP TABLE IF EXISTS import_jobs{suffix};
        DROP TABLE IF EXISTS model_parameters{suffix};
        DROP TABLE IF EXISTS app_users{suffix};
        DROP TABLE IF EXISTS fulfillment_records{suffix};
        DROP TABLE IF EXISTS node_capacities{suffix};
        DROP TABLE IF EXISTS routing_matrix{suffix};
        DROP TABLE IF EXISTS data_sources{suffix};
        DROP TABLE IF EXISTS model_references{suffix};
        DROP TABLE IF EXISTS lpi_country_scores{suffix};
        DROP TABLE IF EXISTS schema_meta{suffix};
        """,
    )


def create_tables(conn: Any) -> None:
    if is_postgres():
        create_postgres_tables(conn)
    else:
        create_sqlite_tables(conn)


def upsert_schema_meta(conn: Any, key: str, value: str) -> None:
    if is_postgres():
        execute(
            conn,
            """
            INSERT INTO schema_meta (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
    else:
        execute(conn, "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)", (key, value))


def create_sqlite_tables(conn: Any) -> None:
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS data_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            publisher TEXT NOT NULL,
            url TEXT NOT NULL,
            license TEXT NOT NULL,
            coverage_note TEXT NOT NULL,
            method_note TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_references (
            ref_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            use_in_model TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lpi_country_scores (
            iso3 TEXT PRIMARY KEY,
            country TEXT NOT NULL,
            year INTEGER NOT NULL,
            overall REAL NOT NULL,
            customs REAL NOT NULL,
            infrastructure REAL NOT NULL,
            international_shipments REAL NOT NULL,
            logistics_quality REAL NOT NULL,
            tracking REAL NOT NULL,
            timeliness REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fulfillment_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_no TEXT NOT NULL UNIQUE,
            channel_type TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            cbm REAL NOT NULL,
            ts_order_created TEXT NOT NULL,
            ts_domestic_out TEXT NOT NULL,
            ts_head_arrive TEXT NOT NULL,
            ts_customs_clear TEXT NOT NULL,
            ts_oversea_in TEXT NOT NULL,
            ts_last_mile_del TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_year INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            record_type TEXT NOT NULL,
            evidence_note TEXT NOT NULL,
            volume_index INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_capacities (
            node_id TEXT PRIMARY KEY,
            node_name TEXT NOT NULL,
            daily_capacity INTEGER NOT NULL,
            target_lead_time REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS routing_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_node TEXT NOT NULL,
            end_node TEXT NOT NULL,
            carrier_name TEXT NOT NULL,
            transit_time_days REAL NOT NULL,
            unit_cost_cbm REAL NOT NULL,
            route_tag TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_parameters (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            value_type TEXT NOT NULL DEFAULT 'number',
            description TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            project_scope TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_limit INTEGER NOT NULL,
            imported_count INTEGER NOT NULL,
            error_message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS external_shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            source_record_id TEXT NOT NULL UNIQUE,
            destination_country TEXT NOT NULL,
            shipment_mode TEXT NOT NULL,
            lead_time_days REAL,
            freight_cost_usd REAL,
            line_item_value_usd REAL,
            weight_kg REAL,
            scheduled_delivery_date TEXT,
            delivered_to_client_date TEXT,
            raw_payload TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        """,
    )


def create_postgres_tables(conn: Any) -> None:
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS data_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            publisher TEXT NOT NULL,
            url TEXT NOT NULL,
            license TEXT NOT NULL,
            coverage_note TEXT NOT NULL,
            method_note TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_references (
            ref_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            use_in_model TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lpi_country_scores (
            iso3 TEXT PRIMARY KEY,
            country TEXT NOT NULL,
            year INTEGER NOT NULL,
            overall DOUBLE PRECISION NOT NULL,
            customs DOUBLE PRECISION NOT NULL,
            infrastructure DOUBLE PRECISION NOT NULL,
            international_shipments DOUBLE PRECISION NOT NULL,
            logistics_quality DOUBLE PRECISION NOT NULL,
            tracking DOUBLE PRECISION NOT NULL,
            timeliness DOUBLE PRECISION NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fulfillment_records (
            id SERIAL PRIMARY KEY,
            batch_no TEXT NOT NULL UNIQUE,
            channel_type TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            cbm DOUBLE PRECISION NOT NULL,
            ts_order_created TEXT NOT NULL,
            ts_domestic_out TEXT NOT NULL,
            ts_head_arrive TEXT NOT NULL,
            ts_customs_clear TEXT NOT NULL,
            ts_oversea_in TEXT NOT NULL,
            ts_last_mile_del TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_year INTEGER NOT NULL,
            source_url TEXT NOT NULL,
            record_type TEXT NOT NULL,
            evidence_note TEXT NOT NULL,
            volume_index INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_capacities (
            node_id TEXT PRIMARY KEY,
            node_name TEXT NOT NULL,
            daily_capacity INTEGER NOT NULL,
            target_lead_time DOUBLE PRECISION NOT NULL
        );

        CREATE TABLE IF NOT EXISTS routing_matrix (
            id SERIAL PRIMARY KEY,
            start_node TEXT NOT NULL,
            end_node TEXT NOT NULL,
            carrier_name TEXT NOT NULL,
            transit_time_days DOUBLE PRECISION NOT NULL,
            unit_cost_cbm DOUBLE PRECISION NOT NULL,
            route_tag TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_parameters (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            value_type TEXT NOT NULL DEFAULT 'number',
            description TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            project_scope TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_jobs (
            job_id SERIAL PRIMARY KEY,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_limit INTEGER NOT NULL,
            imported_count INTEGER NOT NULL,
            error_message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS external_shipments (
            id SERIAL PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_record_id TEXT NOT NULL UNIQUE,
            destination_country TEXT NOT NULL,
            shipment_mode TEXT NOT NULL,
            lead_time_days DOUBLE PRECISION,
            freight_cost_usd DOUBLE PRECISION,
            line_item_value_usd DOUBLE PRECISION,
            weight_kg DOUBLE PRECISION,
            scheduled_delivery_date TEXT,
            delivered_to_client_date TEXT,
            raw_payload TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        """,
    )


def load_seed() -> dict[str, Any]:
    with SEED_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_scms_sample() -> dict[str, Any]:
    with SCMS_SAMPLE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def seed_data(conn: Any) -> None:
    seed = load_seed()
    seed_sources(conn, seed)
    seed_model_references(conn, seed)
    seed_lpi_scores(conn, seed)
    seed_capacities(conn, seed)
    seed_routes(conn, seed)
    seed_lane_observations(conn, seed)
    seed_external_shipments(conn)


def seed_sources(conn: Any, seed: dict[str, Any]) -> None:
    sources = [dict(row) for row in seed["sources"]]
    usaid = next((row for row in sources if row["source_id"] == "USAID_SCMS_REFERENCE"), None)
    if usaid:
        usaid["url"] = settings.usaid_shipments_endpoint
        usaid["coverage_note"] = (
            "USAID shipment-level public data exposed through Socrata view mm7d-nzmf. "
            "Admin imports persist raw shipment rows, lead-time fields, shipment mode, freight cost, and weight. "
            "The runtime seed also includes five public SCMS Delivery History sample rows for offline availability."
        )
        usaid["method_note"] = (
            "Used as a runtime import source when ENABLE_ONLINE_IMPORTS is enabled. "
            "If the upstream endpoint is unreachable, existing imported rows remain available."
        )

    executemany(
        conn,
        """
        INSERT INTO data_sources
            (source_id, name, publisher, url, license, coverage_note, method_note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["source_id"],
                row["name"],
                row["publisher"],
                row["url"],
                row["license"],
                row["coverage_note"],
                row["method_note"],
            )
            for row in sources
        ],
    )


def seed_model_references(conn: Any, seed: dict[str, Any]) -> None:
    executemany(
        conn,
        """
        INSERT INTO model_references (ref_id, name, url, use_in_model)
        VALUES (?, ?, ?, ?)
        """,
        [(row["ref_id"], row["name"], row["url"], row["use_in_model"]) for row in seed["model_references"]],
    )


def seed_lpi_scores(conn: Any, seed: dict[str, Any]) -> None:
    executemany(
        conn,
        """
        INSERT INTO lpi_country_scores (
            iso3, country, year, overall, customs, infrastructure,
            international_shipments, logistics_quality, tracking, timeliness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["iso3"],
                row["country"],
                row["year"],
                row["overall"],
                row["customs"],
                row["infrastructure"],
                row["international_shipments"],
                row["logistics_quality"],
                row["tracking"],
                row["timeliness"],
            )
            for row in seed["lpi_scores"]
        ],
    )


def seed_lane_observations(conn: Any, seed: dict[str, Any]) -> None:
    countries = {row["country"]: row for row in seed["lpi_scores"]}
    origin = countries["中国"]
    source = next(row for row in seed["sources"] if row["source_id"] == "WB_LPI_2022")
    base_time = datetime(2022, 1, 3, 8, 0, 0)
    rows = []

    for index, lane in enumerate(seed["lanes"]):
        destination = countries[lane["destination"]]
        created = base_time + timedelta(days=index * 14)
        domestic_hrs = score_to_hours(10.0, origin["logistics_quality"], floor=6.0, ceiling=16.0)
        head_hrs = lane["base_head_hours"] * score_multiplier(
            (destination["infrastructure"] + destination["international_shipments"] + destination["timeliness"]) / 3
        )
        customs_hrs = score_to_hours(24.0, destination["customs"], floor=10.0, ceiling=42.0)
        oversea_hrs = score_to_hours(28.0, destination["logistics_quality"], floor=14.0, ceiling=44.0)
        last_mile_hrs = score_to_hours(40.0, destination["timeliness"], floor=18.0, ceiling=58.0)

        domestic = created + timedelta(hours=domestic_hrs)
        head = domestic + timedelta(hours=head_hrs)
        customs = head + timedelta(hours=customs_hrs)
        oversea = customs + timedelta(hours=oversea_hrs)
        last_mile = oversea + timedelta(hours=last_mile_hrs)
        cbm = round(lane["volume_index"] / 48, 2)
        batch_no = f"WB-LPI-{destination['iso3']}-{lane['route_family'].upper()}-2022"
        evidence = (
            f"World Bank LPI 2022: {lane['destination']} customs={destination['customs']}, "
            f"infrastructure={destination['infrastructure']}, logistics={destination['logistics_quality']}, "
            f"timeliness={destination['timeliness']}; China origin logistics={origin['logistics_quality']}."
        )

        rows.append(
            (
                batch_no,
                lane["channel_type"],
                "中国",
                lane["destination"],
                lane["volume_index"],
                cbm,
                created.isoformat(timespec="seconds"),
                domestic.isoformat(timespec="seconds"),
                head.isoformat(timespec="seconds"),
                customs.isoformat(timespec="seconds"),
                oversea.isoformat(timespec="seconds"),
                last_mile.isoformat(timespec="seconds"),
                source["source_id"],
                destination["year"],
                source["url"],
                "公开指数驱动线路观测",
                evidence,
                lane["volume_index"],
            )
        )

    executemany(
        conn,
        """
        INSERT INTO fulfillment_records (
            batch_no, channel_type, origin, destination, piece_count, cbm,
            ts_order_created, ts_domestic_out, ts_head_arrive,
            ts_customs_clear, ts_oversea_in, ts_last_mile_del,
            source_id, source_year, source_url, record_type, evidence_note, volume_index
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def seed_external_shipments(conn: Any) -> None:
    sample = load_scms_sample()
    rows = []
    for row in sample["rows"]:
        raw_payload = {
            **row.get("raw_payload", {}),
            "sample_source_url": sample["sample_source_url"],
            "sample_note": sample["note"],
        }
        rows.append(
            (
                sample["source_id"],
                row["source_record_id"],
                row["destination_country"],
                row["shipment_mode"],
                row.get("lead_time_days"),
                row.get("freight_cost_usd"),
                row.get("line_item_value_usd"),
                row.get("weight_kg"),
                row.get("scheduled_delivery_date"),
                row.get("delivered_to_client_date"),
                json.dumps(raw_payload, ensure_ascii=False),
                utc_now(),
            )
        )

    executemany(
        conn,
        """
        INSERT INTO external_shipments (
            source_id, source_record_id, destination_country, shipment_mode,
            lead_time_days, freight_cost_usd, line_item_value_usd, weight_kg,
            scheduled_delivery_date, delivered_to_client_date, raw_payload, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def seed_capacities(conn: Any, seed: dict[str, Any]) -> None:
    scores = {row["country"]: row for row in seed["lpi_scores"]}
    origin = scores["中国"]
    destinations = [row for row in seed["lpi_scores"] if row["country"] != "中国"]
    avg_customs = sum(row["customs"] for row in destinations) / len(destinations)
    avg_infra = sum(row["infrastructure"] for row in destinations) / len(destinations)
    avg_logs = sum(row["logistics_quality"] for row in destinations) / len(destinations)
    avg_time = sum(row["timeliness"] for row in destinations) / len(destinations)
    capacities = [
        ("Domestic_PickPack", "国内仓出库", capacity_from_score(origin["logistics_quality"], 760), 10.0),
        ("Head_Transit", "头程运输", capacity_from_score(avg_infra, 530), 96.0),
        ("Customs_Clearance", "清关查验", capacity_from_score(avg_customs, 480), 22.0),
        ("Oversea_Inbound", "海外仓上架", capacity_from_score(avg_logs, 420), 24.0),
        ("Last_Mile", "尾程妥投", capacity_from_score(avg_time, 620), 40.0),
    ]
    capacity_sql = (
        """
        INSERT INTO node_capacities (node_id, node_name, daily_capacity, target_lead_time)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (node_id) DO UPDATE SET
            node_name = excluded.node_name,
            daily_capacity = excluded.daily_capacity,
            target_lead_time = excluded.target_lead_time
        """
        if is_postgres()
        else "INSERT OR REPLACE INTO node_capacities (node_id, node_name, daily_capacity, target_lead_time) VALUES (?, ?, ?, ?)"
    )
    executemany(conn, capacity_sql, capacities)


def seed_routes(conn: Any, seed: dict[str, Any]) -> None:
    scores = {row["country"]: row for row in seed["lpi_scores"]}
    usa = scores["美国"]
    germany = scores["德国"]
    japan = scores["日本"]
    us_factor = score_multiplier((usa["international_shipments"] + usa["timeliness"]) / 2)
    eu_factor = score_multiplier((germany["international_shipments"] + germany["timeliness"]) / 2)
    jp_factor = score_multiplier((japan["international_shipments"] + japan["timeliness"]) / 2)
    routes = [
        ("中国", "香港机场", "LPI空运基准", round(0.4 * us_factor, 2), cost_index(180, usa), "air"),
        ("香港机场", "美西清关", "LPI跨太平洋空运", round(2.2 * us_factor, 2), cost_index(330, usa), "air"),
        ("美西清关", "美东海外仓", "LPI美国尾程", round(2.8 * score_multiplier(usa["timeliness"]), 2), cost_index(230, usa), "lastmile"),
        ("中国", "盐田港", "LPI海运集港", round(0.6 * us_factor, 2), cost_index(45, usa), "sea"),
        ("盐田港", "洛杉矶港", "LPI跨太平洋海运", round(9.8 * us_factor, 2), cost_index(180, usa), "sea"),
        ("洛杉矶港", "美西清关", "LPI港口转运", round(1.2 * score_multiplier(usa["customs"]), 2), cost_index(65, usa), "port"),
        ("洛杉矶港", "备用海外仓", "LPI备用仓处理", round(1.5 * score_multiplier(usa["logistics_quality"]), 2), cost_index(95, usa), "warehouse"),
        ("备用海外仓", "美东海外仓", "LPI美国卡车基准", round(3.7 * score_multiplier(usa["timeliness"]), 2), cost_index(175, usa), "lastmile"),
        ("香港机场", "芝加哥中转", "LPI快递中转基准", round(2.7 * us_factor, 2), cost_index(350, usa), "express"),
        ("芝加哥中转", "美东海外仓", "LPI区域快运基准", round(2.1 * score_multiplier(usa["timeliness"]), 2), cost_index(190, usa), "lastmile"),
        ("中国", "欧洲多式联运口岸", "LPI中欧多式联运", round(5.2 * eu_factor, 2), cost_index(130, germany), "rail"),
        ("欧洲多式联运口岸", "德国海外仓", "LPI欧洲尾程基准", round(3.2 * score_multiplier(germany["timeliness"]), 2), cost_index(180, germany), "lastmile"),
        ("中国", "东京中转", "LPI近洋快线", round(1.4 * jp_factor, 2), cost_index(110, japan), "express"),
        ("东京中转", "日本海外仓", "LPI日本尾程基准", round(0.9 * score_multiplier(japan["timeliness"]), 2), cost_index(90, japan), "lastmile"),
    ]
    executemany(
        conn,
        """
        INSERT INTO routing_matrix
            (start_node, end_node, carrier_name, transit_time_days, unit_cost_cbm, route_tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        routes,
    )


def seed_default_admin_config(conn: Any) -> None:
    now = utc_now()
    parameters = [
        ("toc_cv_warn_threshold", "0.35", "number", "TOC 诊断中 CV 超过该阈值时标记预警。"),
        ("toc_load_warn_threshold", "0.90", "number", "TOC 诊断中负荷率超过该阈值时标记预警。"),
        ("route_cost_weight", "0.45", "number", "路径综合评分中的成本权重。"),
        ("route_time_weight", "0.40", "number", "路径综合评分中的时效权重。"),
        ("usaid_default_import_limit", str(settings.default_import_limit), "integer", "后台导入 USAID shipment 数据的默认条数。"),
    ]
    for row in parameters:
        execute(conn, insert_ignore_sql("model_parameters", "key", 5), (*row, now))

    execute(conn, insert_ignore_sql("app_users", "user_id", 6), ("admin", "系统管理员", "owner", "全部项目", "active", now))
    execute(conn, insert_ignore_sql("app_users", "user_id", 6), ("planner", "物流计划员", "planner", "线路观测与路径优化", "active", now))


def insert_ignore_sql(table: str, conflict_column: str, value_count: int) -> str:
    columns = {
        "model_parameters": "key, value, value_type, description, updated_at",
        "app_users": "user_id, display_name, role, project_scope, status, created_at",
    }[table]
    placeholders = ", ".join("?" for _ in range(value_count))
    if is_postgres():
        return f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT ({conflict_column}) DO NOTHING"
    return f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})"


def score_multiplier(score: float) -> float:
    return max(0.72, min(1.35, 4.0 / max(score, 0.1)))


def score_to_hours(base_hours: float, score: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, base_hours * score_multiplier(score)))


def capacity_from_score(score: float, base_capacity: int) -> int:
    return round(base_capacity * max(0.75, min(1.18, score / 3.8)))


def cost_index(base_cost: float, destination_score: dict[str, Any]) -> float:
    score = (destination_score["international_shipments"] + destination_score["logistics_quality"]) / 2
    return round(base_cost * score_multiplier(score), 2)


def fetch_all(query: str, params: Iterable[object] = ()) -> list[Any]:
    with connect() as conn:
        return execute(conn, query, tuple(params)).fetchall()


def fetch_one(query: str, params: Iterable[object] = ()) -> Any | None:
    with connect() as conn:
        return execute(conn, query, tuple(params)).fetchone()


def execute_write(query: str, params: Iterable[object] = ()) -> None:
    with connect() as conn:
        execute(conn, query, tuple(params))


def execute_many_write(query: str, rows: Iterable[Sequence[object]]) -> None:
    with connect() as conn:
        executemany(conn, query, rows)


def insert_import_job(source_id: str, requested_limit: int) -> int:
    with connect() as conn:
        started_at = utc_now()
        if is_postgres():
            row = execute(
                conn,
                """
                INSERT INTO import_jobs (source_id, status, requested_limit, imported_count, started_at)
                VALUES (?, ?, ?, ?, ?)
                RETURNING job_id
                """,
                (source_id, "running", requested_limit, 0, started_at),
            ).fetchone()
            return int(row["job_id"])

        cursor = execute(
            conn,
            """
            INSERT INTO import_jobs (source_id, status, requested_limit, imported_count, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_id, "running", requested_limit, 0, started_at),
        )
        return int(cursor.lastrowid)


def finish_import_job(job_id: int, status: str, imported_count: int, error_message: str | None = None) -> None:
    execute_write(
        """
        UPDATE import_jobs
        SET status = ?, imported_count = ?, error_message = ?, finished_at = ?
        WHERE job_id = ?
        """,
        (status, imported_count, error_message, utc_now(), job_id),
    )


def upsert_external_shipments(rows: Iterable[dict[str, Any]]) -> int:
    normalized = [
        (
            row["source_id"],
            row["source_record_id"],
            row["destination_country"],
            row["shipment_mode"],
            row.get("lead_time_days"),
            row.get("freight_cost_usd"),
            row.get("line_item_value_usd"),
            row.get("weight_kg"),
            row.get("scheduled_delivery_date"),
            row.get("delivered_to_client_date"),
            json.dumps(row["raw_payload"], ensure_ascii=False),
            utc_now(),
        )
        for row in rows
    ]
    if not normalized:
        return 0

    conflict = (
        """
        ON CONFLICT (source_record_id) DO UPDATE SET
            destination_country = excluded.destination_country,
            shipment_mode = excluded.shipment_mode,
            lead_time_days = excluded.lead_time_days,
            freight_cost_usd = excluded.freight_cost_usd,
            line_item_value_usd = excluded.line_item_value_usd,
            weight_kg = excluded.weight_kg,
            scheduled_delivery_date = excluded.scheduled_delivery_date,
            delivered_to_client_date = excluded.delivered_to_client_date,
            raw_payload = excluded.raw_payload,
            imported_at = excluded.imported_at
        """
    )
    execute_many_write(
        f"""
        INSERT INTO external_shipments (
            source_id, source_record_id, destination_country, shipment_mode,
            lead_time_days, freight_cost_usd, line_item_value_usd, weight_kg,
            scheduled_delivery_date, delivered_to_client_date, raw_payload, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        {conflict}
        """,
        normalized,
    )
    return len(normalized)


def create_backup() -> dict[str, Any]:
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if is_postgres():
        manifest = settings.backup_dir / f"postgres-backup-{stamp}.json"
        manifest.write_text(
            json.dumps(
                {
                    "created_at": stamp,
                    "database_backend": "postgresql",
                    "note": "Use pg_dump with DATABASE_URL on the server for a full logical backup.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"path": str(manifest), "database_backend": "postgresql", "mode": "manifest"}

    target = settings.backup_dir / f"lean_logistics-{stamp}.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, target)
    else:
        target.write_bytes(b"")
    return {"path": str(target), "database_backend": "sqlite", "mode": "file-copy"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
