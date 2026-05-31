from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "lean_logistics.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            with connect() as conn:
                conn.executescript(
                    """
                    DROP TABLE IF EXISTS fulfillment_records;
                    DROP TABLE IF EXISTS node_capacities;
                    DROP TABLE IF EXISTS routing_matrix;
                    """
                )

    with connect() as conn:
        conn.executescript(
            """
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
                ts_last_mile_del TEXT NOT NULL
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
        has_data = conn.execute("SELECT COUNT(*) FROM fulfillment_records").fetchone()[0] > 0
        if not has_data:
            seed_data(conn)


def seed_data(conn: sqlite3.Connection) -> None:
    rng = random.Random(20260531)
    seed_capacities(conn)
    seed_routes(conn)

    channel_mix = ["空运", "海运", "快递"]
    destinations = ["美国", "德国", "英国", "日本"]
    channel_profile = {
        "空运": {"head": 62, "customs": 18, "last": 34, "cbm": (0.35, 1.2)},
        "海运": {"head": 182, "customs": 24, "last": 42, "cbm": (1.0, 3.8)},
        "快递": {"head": 48, "customs": 13, "last": 28, "cbm": (0.18, 0.9)},
    }
    destination_factor = {"美国": 1.06, "德国": 0.98, "英国": 1.02, "日本": 0.82}

    base_time = datetime(2026, 5, 20, 8, 0, 0)
    rows = []
    for i in range(240):
        channel = channel_mix[i % len(channel_mix)]
        destination = destinations[(i * 7) % len(destinations)]
        profile = channel_profile[channel]
        factor = destination_factor[destination]
        created = base_time + timedelta(hours=i * 0.82)
        domestic = created + hours(rng, 8.8 * factor, 0.18)
        head = domestic + hours(rng, profile["head"] * factor, 0.22)
        customs = head + hours(rng, profile["customs"] * factor, 0.3)
        oversea = customs + hours(rng, 24 * factor, 0.34)
        last_mile = oversea + hours(rng, profile["last"] * factor, 0.24)
        cbm_min, cbm_max = profile["cbm"]
        rows.append(
            (
                f"LL-{2600 + i:04d}",
                channel,
                "深圳工厂",
                destination,
                rng.randint(14, 42),
                round(rng.uniform(cbm_min, cbm_max), 2),
                created.isoformat(timespec="seconds"),
                domestic.isoformat(timespec="seconds"),
                head.isoformat(timespec="seconds"),
                customs.isoformat(timespec="seconds"),
                oversea.isoformat(timespec="seconds"),
                last_mile.isoformat(timespec="seconds"),
            )
        )

    conn.executemany(
        """
        INSERT INTO fulfillment_records (
            batch_no, channel_type, origin, destination, piece_count, cbm,
            ts_order_created, ts_domestic_out, ts_head_arrive,
            ts_customs_clear, ts_oversea_in, ts_last_mile_del
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def seed_capacities(conn: sqlite3.Connection) -> None:
    capacities = [
        ("Domestic_PickPack", "国内仓出库", 760, 10.0),
        ("Head_Transit", "头程运输", 530, 96.0),
        ("Customs_Clearance", "清关查验", 480, 22.0),
        ("Oversea_Inbound", "海外仓上架", 380, 24.0),
        ("Last_Mile", "尾程妥投", 620, 40.0),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO node_capacities (node_id, node_name, daily_capacity, target_lead_time) VALUES (?, ?, ?, ?)",
        capacities,
    )


def seed_routes(conn: sqlite3.Connection) -> None:
    routes = [
        ("深圳工厂", "香港机场", "顺丰空运", 0.4, 180, "air"),
        ("香港机场", "美西清关", "国泰货运", 2.2, 330, "air"),
        ("美西清关", "美东海外仓", "联邦快线", 2.8, 230, "lastmile"),
        ("深圳工厂", "盐田港", "集卡干线", 0.6, 45, "sea"),
        ("盐田港", "洛杉矶港", "马士基海运", 9.8, 180, "sea"),
        ("洛杉矶港", "美西清关", "港口转运", 1.2, 65, "port"),
        ("洛杉矶港", "备用海外仓", "临时保税仓", 1.5, 95, "warehouse"),
        ("备用海外仓", "美东海外仓", "跨州卡车", 3.7, 175, "lastmile"),
        ("香港机场", "芝加哥中转", "极兔国际", 2.7, 350, "express"),
        ("芝加哥中转", "美东海外仓", "区域快运", 2.1, 190, "lastmile"),
        ("深圳工厂", "铁路口岸", "中欧班列", 5.2, 130, "rail"),
        ("铁路口岸", "美东海外仓", "多式联运", 5.4, 260, "lastmile"),
    ]
    conn.executemany(
        """
        INSERT INTO routing_matrix
            (start_node, end_node, carrier_name, transit_time_days, unit_cost_cbm, route_tag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        routes,
    )


def hours(rng: random.Random, mean_hours: float, cv: float) -> timedelta:
    value = max(mean_hours * 0.35, rng.gauss(mean_hours, mean_hours * cv))
    return timedelta(hours=value)


def fetch_all(query: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(query, tuple(params)).fetchall()
