"""PostgreSQL connection utility with table/index creation for apartment recommendation app.

Connection pool 정책
- 서버(FastAPI) 기동 시 `init_pool()` 로 `ThreadedConnectionPool` 을 1회 초기화.
- 종료 시 `close_pool()` 로 모두 정리.
- `DictConnection()` / `get_connection()` 은 pool 에서 raw conn 을 빌려오고 `close()` 시 반납.
- 배치·CLI(build_db 등 lifespan 미동작 경로)는 `get_connection(use_pool=False)` 로 pool 우회.
- raw psycopg2 conn 의 close 를 monkey-patch 하지 않고 `PooledConnection` wrapper 로 감싼다.
"""

import os
import threading
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2 import pool as psycopg2_pool
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('USER', 'postgres')}@localhost:5432/apt_recom",
)

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_pool: psycopg2_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def init_pool() -> None:
    """프로세스 당 1회 pool 초기화 (lifespan startup). 멱등."""
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = psycopg2_pool.ThreadedConnectionPool(
                _POOL_MIN, _POOL_MAX, dsn=DATABASE_URL
            )
            print(f"[db] pool initialized (min={_POOL_MIN}, max={_POOL_MAX})")


def close_pool() -> None:
    """프로세스 종료 시 pool 전체 해제 (lifespan shutdown)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
            print("[db] pool closed")


def _pool_acquire(autocommit: bool):
    """pool 에서 raw conn 을 빌려오고 autocommit 모드 세팅.

    pool 이 없으면 lazy init (개발 환경에서 lifespan 없이 DictConnection 쓰는 경우 대비).
    """
    if _pool is None:
        init_pool()
    assert _pool is not None  # init_pool 이후에는 반드시 생성됨
    raw = _pool.getconn()
    raw.autocommit = autocommit
    return raw


def _pool_release(raw) -> None:
    """raw conn 을 pool 로 반납. broken conn 은 close 로 폐기."""
    if _pool is None or raw is None:
        return
    try:
        # 미완결 트랜잭션은 pool 오염 방지를 위해 rollback
        if not raw.autocommit and raw.status != psycopg2.extensions.STATUS_READY:
            raw.rollback()
    except Exception:
        pass
    try:
        _pool.putconn(raw)
    except Exception:
        try:
            raw.close()
        except Exception:
            pass


class PooledConnection:
    """psycopg2 connection wrapper.

    raw conn 의 C 확장 메서드(close)를 monkey-patch 하지 않고, 외부에서 쓰는
    인터페이스(cursor/commit/rollback/close)만 명시 노출한다. 그 외 속성은
    `__getattr__` 로 raw 로 proxy.

    `pooled=True` 면 close() 가 pool 반납, `pooled=False` 면 raw.close() 호출.
    """

    def __init__(self, raw, pooled: bool):
        self._raw = raw
        self._pooled = pooled
        self._closed = False

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._pooled:
            _pool_release(self._raw)
        else:
            try:
                self._raw.close()
            except Exception:
                pass

    def __getattr__(self, name):
        # autocommit, status, encoding 등 자주 쓰지 않는 속성 proxy
        return getattr(self._raw, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_connection(db_path=None, use_pool: bool = True):
    """트랜잭션 경로용 conn (autocommit=False).

    - `use_pool=True` (기본, 서버 런타임): pool 에서 빌림. close() 시 반납.
    - `use_pool=False` (batch/CLI/build_db): 직접 connect. close() 시 raw close.

    db_path 는 과거 sqlite 호환용 더미 인자 (무시됨).
    """
    if use_pool:
        raw = _pool_acquire(autocommit=False)
        return PooledConnection(raw, pooled=True)
    raw = psycopg2.connect(DATABASE_URL)
    raw.autocommit = False
    return PooledConnection(raw, pooled=False)


def get_dict_cursor(conn):
    """Return a cursor that returns rows as dicts."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


class DictConnection:
    """자동커밋 + RealDictCursor 반환 래퍼. pool 기반.

    기존 호출부 호환:
        conn = DictConnection()
        rows = conn.execute("SELECT ...", [param]).fetchall()
        conn.close()
    """

    def __init__(self):
        self._raw = _pool_acquire(autocommit=True)
        self._closed = False

    def execute(self, sql, params=None):
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        return cur

    def commit(self):
        # autocommit=True 이므로 no-op. 호환용 유지.
        pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        _pool_release(self._raw)

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

        -- apt_kapt_info 보충 컬럼 (K-APT 20260417 엑셀 재적재용)
        ALTER TABLE apt_kapt_info ADD COLUMN IF NOT EXISTS joined_date TEXT;
        ALTER TABLE apt_kapt_info ADD COLUMN IF NOT EXISTS food_waste_method TEXT;
        ALTER TABLE apt_kapt_info ADD COLUMN IF NOT EXISTS cleaning_staff INTEGER;
        ALTER TABLE apt_kapt_info ADD COLUMN IF NOT EXISTS elevator_mgr_type TEXT;

        -- 주택형별 면적/세대수 (K-APT 면적 엑셀의 "주거전용면적(세부)" row)
        CREATE TABLE IF NOT EXISTS apt_area_type (
            pnu TEXT NOT NULL,
            exclusive_area DOUBLE PRECISION NOT NULL,
            unit_count INTEGER NOT NULL,
            mgmt_area_total DOUBLE PRECISION,
            priv_area_total DOUBLE PRECISION,
            last_refreshed TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (pnu, exclusive_area)
        );
        CREATE INDEX IF NOT EXISTS idx_apt_area_type_pnu ON apt_area_type(pnu);

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

        -- 대시보드 월별 집계 (trend 엔드포인트 전용)
        -- scope: 'ALL' 또는 sgg_cd 5자리. 최근 60개월 보관.
        CREATE TABLE IF NOT EXISTS dashboard_monthly_stats (
            scope TEXT NOT NULL,
            deal_year INTEGER NOT NULL,
            deal_month INTEGER NOT NULL,
            trade_volume INTEGER NOT NULL DEFAULT 0,
            trade_avg_price DOUBLE PRECISION NOT NULL DEFAULT 0,
            trade_avg_price_m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            trade_median_price_m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            rent_volume INTEGER NOT NULL DEFAULT 0,
            rent_avg_deposit DOUBLE PRECISION NOT NULL DEFAULT 0,
            rent_median_deposit_m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (scope, deal_year, deal_month)
        );

        -- 대시보드 30일 슬라이딩 윈도우 집계 (summary 엔드포인트 전용)
        -- 배치 실행 시점 기준 30~60일 전 윈도우(current)와 전년 동기(prev_year)를 저장.
        -- 매일 배치가 돌면 period_start/period_end가 하루씩 이동한다.
        CREATE TABLE IF NOT EXISTS dashboard_window_stats (
            scope TEXT NOT NULL,
            window_kind TEXT NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            trade_volume INTEGER NOT NULL DEFAULT 0,
            trade_median_price_m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            rent_volume INTEGER NOT NULL DEFAULT 0,
            rent_median_deposit_m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (scope, window_kind)
        );

        -- 대시보드 최근 3개월 시군구 랭킹 (ranking 엔드포인트 전용)
        -- API는 현재월만 반환. 3개월 보관은 월 경계 배치 타이밍 대비.
        CREATE TABLE IF NOT EXISTS dashboard_ranking_stats (
            type TEXT NOT NULL,
            deal_year INTEGER NOT NULL,
            deal_month INTEGER NOT NULL,
            sgg_cd TEXT NOT NULL,
            volume INTEGER NOT NULL,
            avg_value DOUBLE PRECISION NOT NULL DEFAULT 0,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (type, deal_year, deal_month, sgg_cd)
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


def ensure_dashboard_indexes(conn) -> None:
    """대시보드 집계 테이블 보조 인덱스를 보장.

    startup 에서 호출되어 dashboard_* 집계 테이블의 보조 인덱스가 항상
    존재하도록 한다. 행 수가 작아(수천) 부담 없음. IF NOT EXISTS 로 멱등.
    원천 테이블(trade/rent_history) 인덱스는 create_indexes() 쪽에서 관리.
    """
    cur = conn.cursor()
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_dash_ranking_lookup ON dashboard_ranking_stats(type, deal_year DESC, deal_month DESC, volume DESC)",
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
        # 대시보드 /recent 시군구 필터 + 최신순 LIMIT 20 전용
        # (Phase 0 EXPLAIN: idx_trade_ymd backward scan + sgg_cd Filter → 8145 rows filter로 제거됨, 9.7ms)
        "CREATE INDEX IF NOT EXISTS idx_trade_sgg_recent ON trade_history(sgg_cd, deal_year DESC, deal_month DESC, deal_day DESC)",
        "CREATE INDEX IF NOT EXISTS idx_rent_sgg_recent ON rent_history(sgg_cd, deal_year DESC, deal_month DESC, deal_day DESC)",
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
