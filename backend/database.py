from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "lean_logistics.db"
SEED_PATH = ROOT_DIR / "data" / "real_logistics_seed.json"
SCHEMA_VERSION = 2


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    with connect() as conn:
        if reset or current_schema_version(conn) != SCHEMA_VERSION:
            drop_tables(conn)

        create_tables(conn)
        has_data = conn.execute("SELECT COUNT(*) FROM fulfillment_records").fetchone()[0] > 0
        if not has_data:
            seed_data(conn)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def current_schema_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    ).fetchone()
    if not exists:
        return 0
    value = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    return int(value["value"]) if value and str(value["value"]).isdigit() else 0


def drop_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS fulfillment_records;
        DROP TABLE IF EXISTS node_capacities;
        DROP TABLE IF EXISTS routing_matrix;
        DROP TABLE IF EXISTS data_sources;
        DROP TABLE IF EXISTS model_references;
        DROP TABLE IF EXISTS lpi_country_scores;
        DROP TABLE IF EXISTS schema_meta;
        """
    )


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
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
        """
    )


def load_seed() -> dict:
    with SEED_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def seed_data(conn: sqlite3.Connection) -> None:
    seed = load_seed()
    seed_sources(conn, seed)
    seed_model_references(conn, seed)
    seed_lpi_scores(conn, seed)
    seed_capacities(conn, seed)
    seed_routes(conn, seed)
    seed_lane_observations(conn, seed)


def seed_sources(conn: sqlite3.Connection, seed: dict) -> None:
    conn.executemany(
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
            for row in seed["sources"]
        ],
    )


def seed_model_references(conn: sqlite3.Connection, seed: dict) -> None:
    conn.executemany(
        """
        INSERT INTO model_references (ref_id, name, url, use_in_model)
        VALUES (?, ?, ?, ?)
        """,
        [(row["ref_id"], row["name"], row["url"], row["use_in_model"]) for row in seed["model_references"]],
    )


def seed_lpi_scores(conn: sqlite3.Connection, seed: dict) -> None:
    conn.executemany(
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


def seed_lane_observations(conn: sqlite3.Connection, seed: dict) -> None:
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

    conn.executemany(
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


def seed_capacities(conn: sqlite3.Connection, seed: dict) -> None:
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
    conn.executemany(
        "INSERT OR REPLACE INTO node_capacities (node_id, node_name, daily_capacity, target_lead_time) VALUES (?, ?, ?, ?)",
        capacities,
    )


def seed_routes(conn: sqlite3.Connection, seed: dict) -> None:
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
    conn.executemany(
        """
        INSERT INTO routing_matrix
            (start_node, end_node, carrier_name, transit_time_days, unit_cost_cbm, route_tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        routes,
    )


def score_multiplier(score: float) -> float:
    return max(0.72, min(1.35, 4.0 / max(score, 0.1)))


def score_to_hours(base_hours: float, score: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, base_hours * score_multiplier(score)))


def capacity_from_score(score: float, base_capacity: int) -> int:
    return round(base_capacity * max(0.75, min(1.18, score / 3.8)))


def cost_index(base_cost: float, destination_score: dict) -> float:
    score = (destination_score["international_shipments"] + destination_score["logistics_quality"]) / 2
    return round(base_cost * score_multiplier(score), 2)


def fetch_all(query: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(query, tuple(params)).fetchall()
