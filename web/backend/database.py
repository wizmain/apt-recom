"""PostgreSQL connection utility with table/index creation for apartment recommendation app."""

import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('USER', 'postgres')}@localhost:5432/apt_recom",
)


def get_connection(db_path=None):
    """Create and return a PostgreSQL connection.

    db_path is accepted but ignored (kept for backward compatibility).
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def get_dict_cursor(conn):
    """Return a cursor that returns rows as dicts."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


class DictConnection:
    """Wrapper that mimics sqlite3 connection with row_factory=dict.

    Usage:
        conn = get_dict_connection()
        rows = conn.execute("SELECT ...", [param]).fetchall()
        conn.close()
    """

    def __init__(self):
        self._conn = psycopg2.connect(DATABASE_URL)
        self._conn.autocommit = True

    def execute(self, sql, params=None):
        """Execute SQL and return a cursor (supports fetchone/fetchall)."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def create_tables(conn) -> None:
    """Create all tables (without indexes)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS apartments (
            pnu TEXT PRIMARY KEY,
            bld_nm TEXT,
            total_hhld_cnt INTEGER,
            dong_count INTEGER,
            max_floor INTEGER,
            use_apr_day TEXT,
            plat_plc TEXT,
            new_plat_plc TEXT,
            bjd_code TEXT,
            sigungu_code TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            group_pnu TEXT
        );

        CREATE TABLE IF NOT EXISTS facilities (
            facility_id TEXT PRIMARY KEY,
            facility_type TEXT,
            facility_subtype TEXT,
            name TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            address TEXT
        );

        CREATE TABLE IF NOT EXISTS apt_facility_mapping (
            pnu TEXT,
            facility_id TEXT,
            facility_type TEXT,
            facility_subtype TEXT,
            distance_m DOUBLE PRECISION,
            PRIMARY KEY (pnu, facility_id)
        );

        CREATE TABLE IF NOT EXISTS apt_facility_summary (
            pnu TEXT,
            facility_subtype TEXT,
            nearest_distance_m DOUBLE PRECISION,
            count_1km INTEGER,
            count_3km INTEGER,
            count_5km INTEGER,
            PRIMARY KEY (pnu, facility_subtype)
        );

        CREATE TABLE IF NOT EXISTS trade_history (
            id SERIAL PRIMARY KEY,
            apt_seq TEXT,
            sgg_cd TEXT,
            apt_nm TEXT,
            deal_amount INTEGER,
            exclu_use_ar DOUBLE PRECISION,
            floor INTEGER,
            deal_year INTEGER,
            deal_month INTEGER,
            deal_day INTEGER,
            build_year INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS rent_history (
            id SERIAL PRIMARY KEY,
            apt_seq TEXT,
            sgg_cd TEXT,
            apt_nm TEXT,
            deposit INTEGER,
            monthly_rent INTEGER,
            exclu_use_ar DOUBLE PRECISION,
            floor INTEGER,
            deal_year INTEGER,
            deal_month INTEGER,
            deal_day INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS trade_apt_mapping (
            apt_seq TEXT PRIMARY KEY,
            pnu TEXT,
            apt_nm TEXT,
            sgg_cd TEXT,
            match_method TEXT
        );

        CREATE TABLE IF NOT EXISTS school_zones (
            pnu TEXT PRIMARY KEY,
            elementary_school_name TEXT,
            elementary_school_id TEXT,
            elementary_school_full_name TEXT,
            elementary_zone_id TEXT,
            middle_school_zone TEXT,
            middle_school_zone_id TEXT,
            high_school_zone TEXT,
            high_school_zone_id TEXT,
            high_school_zone_type TEXT,
            edu_office_name TEXT,
            edu_district TEXT
        );

        CREATE TABLE IF NOT EXISTS apt_price_score (
            pnu TEXT PRIMARY KEY,
            price_per_m2 DOUBLE PRECISION,
            sgg_avg_price_per_m2 DOUBLE PRECISION,
            price_score DOUBLE PRECISION,
            jeonse_ratio DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS apt_safety_score (
            pnu TEXT PRIMARY KEY,
            safety_score DOUBLE PRECISION,
            cctv_count_500m INTEGER,
            cctv_count_1km INTEGER,
            nearest_cctv_m DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS population_by_district (
            sigungu_code TEXT,
            sigungu_name TEXT,
            sido_name TEXT,
            age_group TEXT,
            total_pop INTEGER,
            male_pop INTEGER,
            female_pop INTEGER,
            PRIMARY KEY (sigungu_code, age_group)
        );

        CREATE TABLE IF NOT EXISTS common_code (
            group_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            extra TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            PRIMARY KEY (group_id, code)
        );

        CREATE TABLE IF NOT EXISTS chat_feedback (
            id SERIAL PRIMARY KEY,
            user_message TEXT NOT NULL,
            assistant_message TEXT NOT NULL,
            tool_calls TEXT DEFAULT '[]',
            rating INTEGER NOT NULL,
            tags TEXT[] DEFAULT '{}',
            comment TEXT DEFAULT '',
            session_id TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    print("Tables created.")


def create_indexes(conn) -> None:
    """Create indexes after all data is loaded."""
    cur = conn.cursor()
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_mapping_pnu ON apt_facility_mapping(pnu)",
        "CREATE INDEX IF NOT EXISTS idx_mapping_type ON apt_facility_mapping(facility_subtype)",
        "CREATE INDEX IF NOT EXISTS idx_summary_pnu ON apt_facility_summary(pnu)",
        "CREATE INDEX IF NOT EXISTS idx_trade_sgg ON trade_history(sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_trade_seq ON trade_history(apt_seq)",
        "CREATE INDEX IF NOT EXISTS idx_trade_year ON trade_history(deal_year)",
        "CREATE INDEX IF NOT EXISTS idx_rent_sgg ON rent_history(sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_rent_seq ON rent_history(apt_seq)",
        "CREATE INDEX IF NOT EXISTS idx_apt_sigungu ON apartments(sigungu_code)",
        "CREATE INDEX IF NOT EXISTS idx_trade_map_pnu ON trade_apt_mapping(pnu)",
        "CREATE INDEX IF NOT EXISTS idx_apt_group_pnu ON apartments(group_pnu)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_rating ON chat_feedback(rating)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_created ON chat_feedback(created_at)",
    ]
    for sql in indexes:
        cur.execute(sql)
        name = sql.split("idx_")[1].split(" ON")[0]
        print(f"  {name} done")
    conn.commit()
    print("All indexes created.")
