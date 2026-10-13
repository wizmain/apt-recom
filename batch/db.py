"""배치용 DB 연결 유틸리티."""

import time

import psycopg2
import psycopg2.extras
from batch.config import DATABASE_URL


def get_connection():
    """DATABASE_URL 환경변수로 PostgreSQL 연결."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
    # TCP keepalive: 거래 배치는 수집(외부 API, 13~30분+) 동안 커넥션이 완전
    # 유휴라 Railway 프록시 idle timeout 에 끊겨 적재 시점에 "SSL SYSCALL
    # error: EOF detected" 가 났다 (2026-07-19 run 29693568789). 유휴 60초마다
    # 프로브를 보내 연결을 유지한다.
    conn = psycopg2.connect(
        DATABASE_URL,
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=3,
    )
    conn.autocommit = False
    return conn


def get_dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def execute_values_chunked(conn, sql, rows, chunk_size=10000):
    """대량 INSERT를 chunk 단위로 실행."""
    cur = conn.cursor()
    total = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        psycopg2.extras.execute_values(cur, sql, chunk, page_size=chunk_size)
        total += len(chunk)
    conn.commit()
    return total


def query_one(conn, sql, params=None):
    cur = get_dict_cursor(conn)
    cur.execute(sql, params or [])
    return cur.fetchone()


def query_all(conn, sql, params=None):
    cur = get_dict_cursor(conn)
    cur.execute(sql, params or [])
    return cur.fetchall()


def get_district_codes(conn):
    """수도권 시군구 코드 목록 조회."""
    rows = query_all(
        conn,
        "SELECT DISTINCT LEFT(sigungu_code, 5) as code FROM apartments WHERE sigungu_code IS NOT NULL",
    )
    return sorted(r["code"] for r in rows)


def vacuum_tables(url: str, tables: list[str], logger, full: bool = False) -> None:
    """VACUUM 은 transaction 안에서 못 돌리므로 별도 autocommit connection.

    full=True 면 ``VACUUM (FULL, ANALYZE)`` — 테이블을 rewrite 해 디스크 공간을
    OS 로 반환한다. ACCESS EXCLUSIVE 락 + 잔존 데이터 크기만큼의 임시 디스크가
    필요하므로 트래픽 적은 시간대에 실행. 한 테이블이 실패(예: 디스크 부족)해도
    이미 회수한 앞 테이블 효과는 유지되도록 테이블별로 에러를 잡고 계속 진행한다.
    """
    mode = "FULL, ANALYZE" if full else "ANALYZE"
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for t in tables:
            logger.info(f"  VACUUM ({mode}) {t} 시작")
            start = time.time()
            try:
                cur.execute(f"VACUUM ({mode}) {t}")
            except psycopg2.Error as e:
                logger.error(f"  VACUUM ({mode}) {t} 실패: {e}")
                continue
            logger.info(f"  VACUUM ({mode}) {t} 완료 ({time.time() - start:.1f}s)")
    finally:
        conn.close()
