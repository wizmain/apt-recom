"""배치용 DB 연결 유틸리티."""

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
