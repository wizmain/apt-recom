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
            address TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            updated_at TIMESTAMPTZ DEFAULT NOW()
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
            nearest_cctv_m DOUBLE PRECISION,
            crime_safety_score DOUBLE PRECISION,
            micro_score DOUBLE PRECISION,
            access_score DOUBLE PRECISION,
            macro_score DOUBLE PRECISION,
            complex_score DOUBLE PRECISION,
            data_reliability DOUBLE PRECISION,
            crime_hotspot_grade DOUBLE PRECISION,
            score_version INTEGER DEFAULT 2,
            complex_cctv_score DOUBLE PRECISION,
            complex_security_score DOUBLE PRECISION,
            complex_mgr_score DOUBLE PRECISION,
            complex_parking_score DOUBLE PRECISION,
            regional_safety_score DOUBLE PRECISION,
            crime_adjust_score DOUBLE PRECISION,
            complex_data_source TEXT
        );

        CREATE TABLE IF NOT EXISTS traffic_accident_hotspot (
            id SERIAL PRIMARY KEY,
            sigungu_name TEXT,
            spot_name TEXT,
            accident_cnt INTEGER,
            casualty_cnt INTEGER,
            death_cnt INTEGER,
            serious_cnt INTEGER,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            bjd_code TEXT
        );

        CREATE TABLE IF NOT EXISTS apt_kapt_info (
            pnu TEXT PRIMARY KEY,
            kapt_code TEXT,
            kapt_name TEXT,
            sigungu_code TEXT,
            -- 기본 정보
            sale_type TEXT,
            heat_type TEXT,
            builder TEXT,
            developer TEXT,
            apt_type TEXT,
            mgr_type TEXT,
            hall_type TEXT,
            structure TEXT,
            -- 면적/규모
            total_area DOUBLE PRECISION,
            priv_area DOUBLE PRECISION,
            mgmt_area DOUBLE PRECISION,
            ho_cnt INTEGER,
            dong_cnt INTEGER,
            top_floor INTEGER,
            top_floor_official INTEGER,
            base_floor INTEGER,
            use_date TEXT,
            -- 세대 구성
            sale_ho_cnt INTEGER,
            rent_ho_cnt INTEGER,
            rent_public_cnt INTEGER,
            rent_private_cnt INTEGER,
            -- 면적 구간별 세대수
            area_under_60 INTEGER,
            area_60_85 INTEGER,
            area_85_135 INTEGER,
            area_over_135 INTEGER,
            -- 관리/경비
            mgmt_company TEXT,
            general_mgmt_type TEXT,
            general_mgmt_staff INTEGER,
            security_type TEXT,
            security_staff INTEGER,
            security_company TEXT,
            -- 주차
            parking_cnt INTEGER,
            parking_ground INTEGER,
            parking_underground INTEGER,
            -- 전기차
            total_car_cnt INTEGER,
            ev_car_cnt INTEGER,
            ev_charger_cnt INTEGER,
            ev_charger_ground INTEGER,
            ev_charger_underground INTEGER,
            ev_parking_ground INTEGER,
            ev_parking_underground INTEGER,
            -- 시설/설비
            cctv_cnt INTEGER,
            elevator_cnt INTEGER,
            elevator_passenger INTEGER,
            elevator_freight INTEGER,
            elevator_mixed INTEGER,
            elevator_disabled INTEGER,
            elevator_emergency INTEGER,
            home_network TEXT,
            welfare TEXT,
            convenience_facilities TEXT,
            -- 주소/연락처
            jibun_addr TEXT,
            road_addr TEXT,
            tel TEXT,
            fax TEXT,
            homepage TEXT,
            zipcode TEXT,
            -- API 보충 (Phase 2)
            subway_info TEXT,
            bus_time TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- 전용/공급면적 정보 (호별 전유부 집계)
        CREATE TABLE IF NOT EXISTS apt_area_info (
            pnu TEXT PRIMARY KEY,
            min_area DOUBLE PRECISION,
            max_area DOUBLE PRECISION,
            avg_area DOUBLE PRECISION,
            min_supply_area DOUBLE PRECISION,   -- 공급면적 = 전용 + 주거공용
            max_supply_area DOUBLE PRECISION,
            avg_supply_area DOUBLE PRECISION,
            unit_count INTEGER,
            area_types INTEGER,
            cnt_under_40 INTEGER,
            cnt_40_60 INTEGER,
            cnt_60_85 INTEGER,
            cnt_85_115 INTEGER,
            cnt_115_135 INTEGER,
            cnt_over_135 INTEGER,
            source TEXT,               -- bld_expos / kapt_bucket / trade_fallback
            last_refreshed TIMESTAMPTZ
        );
        -- 기존 레거시 테이블에 누락 컬럼 추가
        ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS source TEXT;
        ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS last_refreshed TIMESTAMPTZ;
        ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS min_supply_area DOUBLE PRECISION;
        ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS max_supply_area DOUBLE PRECISION;
        ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS avg_supply_area DOUBLE PRECISION;

        CREATE TABLE IF NOT EXISTS apt_mgmt_cost (
            pnu TEXT,
            year_month TEXT,
            common_cost BIGINT,
            individual_cost BIGINT,
            repair_fund BIGINT,
            total_cost BIGINT,
            cost_per_unit BIGINT,
            detail JSONB,
            PRIMARY KEY (pnu, year_month)
        );

        CREATE TABLE IF NOT EXISTS population_by_district (
            sigungu_code TEXT,
            sigungu_name TEXT,
            sido_name TEXT,
            age_group TEXT,
            total_pop INTEGER,
            male_pop INTEGER,
            female_pop INTEGER,
            daytime_pop INTEGER,
            PRIMARY KEY (sigungu_code, age_group)
        );

        CREATE TABLE IF NOT EXISTS sigungu_safety_index (
            sigungu_code TEXT PRIMARY KEY,
            sido_name TEXT,
            sigungu_name TEXT,
            traffic_grade INTEGER,
            fire_grade INTEGER,
            crime_grade INTEGER,
            living_safety_grade INTEGER,
            suicide_grade INTEGER,
            infection_grade INTEGER,
            composite_score DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS apt_vectors (
            pnu TEXT PRIMARY KEY,
            vector DOUBLE PRECISION[] NOT NULL,
            feature_names TEXT DEFAULT '',
            updated_at TIMESTAMPTZ DEFAULT NOW()
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

        -- 사용자 행동 로그 (익명 device_id 기반, 90일 보관)
        CREATE TABLE IF NOT EXISTS user_event (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_name TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- 챗봇 대화 로그 (평가 여부 무관, 90일 보관)
        CREATE TABLE IF NOT EXISTS chat_log (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT,
            session_id TEXT,
            user_message TEXT NOT NULL,
            assistant_message TEXT NOT NULL,
            tool_calls JSONB DEFAULT '[]'::JSONB,
            context JSONB,
            terminated_early BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    print("Tables created.")


def ensure_logging_indexes(conn) -> None:
    """사용자 행동 로그·챗 로그 테이블의 인덱스를 보장.

    server startup 에서 호출되어 user_event / chat_log 테이블에 필요한
    인덱스가 항상 존재하도록 한다. IF NOT EXISTS 로 멱등.
    """
    cur = conn.cursor()
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_user_event_device_created ON user_event(device_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_type_created ON user_event(event_type, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_created_brin ON user_event USING brin(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_payload_gin ON user_event USING gin(payload jsonb_path_ops)",
        "CREATE INDEX IF NOT EXISTS idx_chat_log_device_created ON chat_log(device_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_chat_log_created_brin ON chat_log USING brin(created_at)",
    ]
    for sql in indexes:
        cur.execute(sql)
    conn.commit()


def create_indexes(conn) -> None:
    """Create indexes after all data is loaded."""
    cur = conn.cursor()
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_summary_pnu ON apt_facility_summary(pnu)",
        "CREATE INDEX IF NOT EXISTS idx_trade_sgg ON trade_history(sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_trade_seq ON trade_history(apt_seq)",
        "CREATE INDEX IF NOT EXISTS idx_trade_year ON trade_history(deal_year)",
        "CREATE INDEX IF NOT EXISTS idx_rent_sgg ON rent_history(sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_rent_seq ON rent_history(apt_seq)",
        "CREATE INDEX IF NOT EXISTS idx_apt_sigungu ON apartments(sigungu_code)",
        "CREATE INDEX IF NOT EXISTS idx_apt_bjd ON apartments(bjd_code)",
        "CREATE INDEX IF NOT EXISTS idx_trade_map_pnu ON trade_apt_mapping(pnu)",
        "CREATE INDEX IF NOT EXISTS idx_apt_group_pnu ON apartments(group_pnu)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_rating ON chat_feedback(rating)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_created ON chat_feedback(created_at)",
        # 대시보드 성능용 복합 인덱스
        "CREATE INDEX IF NOT EXISTS idx_trade_ymd ON trade_history(deal_year, deal_month, deal_day)",
        "CREATE INDEX IF NOT EXISTS idx_rent_ymd ON rent_history(deal_year, deal_month, deal_day)",
        "CREATE INDEX IF NOT EXISTS idx_trade_sgg_date ON trade_history(sgg_cd, deal_year, deal_month)",
        "CREATE INDEX IF NOT EXISTS idx_rent_sgg_date ON rent_history(sgg_cd, deal_year, deal_month)",
        "CREATE INDEX IF NOT EXISTS idx_trade_apt_sgg ON trade_history(apt_nm, sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_rent_apt_sgg ON rent_history(apt_nm, sgg_cd)",
        "CREATE INDEX IF NOT EXISTS idx_trade_created ON trade_history(created_at)",
        # 사용자 행동 로그 — device별 조회 + 이벤트별 집계 + 90일 퍼지(BRIN) + JSONB 분석(GIN)
        "CREATE INDEX IF NOT EXISTS idx_user_event_device_created ON user_event(device_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_type_created ON user_event(event_type, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_created_brin ON user_event USING brin(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_user_event_payload_gin ON user_event USING gin(payload jsonb_path_ops)",
        "CREATE INDEX IF NOT EXISTS idx_chat_log_device_created ON chat_log(device_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_chat_log_created_brin ON chat_log USING brin(created_at)",
    ]
    for sql in indexes:
        cur.execute(sql)
        name = sql.split("idx_")[1].split(" ON")[0]
        print(f"  {name} done")
    conn.commit()
    print("All indexes created.")
