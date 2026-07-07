"""에어코리아 대기질(PM2.5) 수집 → apt_air_score 재계산 (라이프점수 Phase 2-4).

score_air 는 근접 "시설"이 아니라 지역 환경 지표라 facilities 가 아닌
apt_safety_score 선례처럼 score_* 전용 테이블(apt_air_score)에 적재한다.
통계 API 보유 윈도우가 최근 ~4개월뿐이라 quarterly 마다 월평균을
air_quality_monthly 에 upsert 로 누적하고, score 는 보유 구간 평균의
백분위(역방향: PM2.5 낮을수록 고점)로 계산한다 — 초기 4개월 윈도우도
전 지역 상대 순위이므로 계절 편향이 공통으로 상쇄된다(month_count 로
성숙도 추적).

PoC 확정 (2026-07-07, 실측):
- `MsrstnInfoInqireSvc/getMsrstnList` — returnType=json, totalCount 673,
  numOfRows=1000 요청 시 1페이지에 전량 반환. 필드 stationName/addr/
  dmX/dmY/mangName/item/year. **dmX가 위도, dmY가 경도 (명명 반전 주의)**.
- `ArpltnStatsSvc/getMsrstnAcctoRMmrg` — msrstnName 필터 없이 조회할 때
  **inqBginMm == inqEndMm(단일 월)이면 전 측정소 데이터가 정상 반환되지만,
  범위 조회(inqBginMm != inqEndMm)는 totalCount 는 채워지면서 items 가
  항상 빈 배열로 온다** (서버측 제약으로 추정, 스펙 문서에 명시 없음).
  그래서 fetch_monthly() 는 계획서의 "무필터 범위 페이징"이 아니라
  월 단위로 개별 호출한다(월별 1회, 실효상 1페이지로 충분 — totalCount
  <= 673 < numOfRows 1000).
- 보유 윈도우 실측: 202603~202606 (4개월), 그 밖 월은 totalCount=0
  (resultCode 는 정상 "00" — 에러 아님, 자연 skip).
- pm25Value 등은 문자열이며 결측 시 ''/'-' 로 옴 → float 변환 실패/결측
  패턴 매칭 시 NULL 저장 (0 강제 금지).

측정소 매핑 대상: mang_name IN ('도시대기', '교외대기') — 도로변대기(국지
고농도)·항만/선박권역·국가배경농도(도서)는 특수 목적 측정소라 주거지
대기질을 대표하지 못해 apt_air_score 계산에서 제외한다(단, 측정소
테이블 자체에는 전량 적재해 향후 활용 여지를 남긴다).

사용법:
  .venv/bin/python -m batch.quarterly.collect_air_quality   # 측정소+월평균+점수 전량
  (batch/run.py --type quarterly 의 7단계로도 호출됨)
"""

import time
from datetime import date

import numpy as np
import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import execute_values_chunked, get_connection, query_all
from batch.logger import setup_logger

STATION_LIST_URL = "https://apis.data.go.kr/B552584/MsrstnInfoInqireSvc/getMsrstnList"
MONTHLY_STATS_URL = "https://apis.data.go.kr/B552584/ArpltnStatsSvc/getMsrstnAcctoRMmrg"
MAX_ROWS_PER_PAGE = (
    1000  # PoC 실측: 측정소 673 / 월별 totalCount <= 673 모두 1페이지 커버
)
SUCCESS_RESULT_CODE = "00"
MAX_RETRIES = 2  # transient 오류 백오프 재시도 (STORE/HIRA 수집기 관례)
DEFAULT_LOOKBACK_MONTHS = 6  # 보유 4개월 + 여유 — 0건 월은 자연 skip

# 주거지 대표성 있는 측정망만 apt_air_score 매핑 대상으로 사용 (plan §Global Constraints).
RESIDENTIAL_MANG_NAMES = ("도시대기", "교외대기")

EARTH_RADIUS_M = 6_371_000.0


class RateLimitExceeded(RuntimeError):
    """HTTP 429(일일 한도 소진) — 재시도해도 자정까지 회복되지 않으므로 조기 중단."""


def _request_json(url: str, params: dict) -> dict:
    """공통 JSON 요청 + 429/transient 재시도 (STORE/HIRA 수집기 관례 준용)."""
    attempt = 0
    while True:
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                raise RateLimitExceeded(f"{params}: HTTP 429 (일일 한도 소진)")
            resp.raise_for_status()
            data = resp.json()
            header = data["response"]["header"]
            if header["resultCode"] != SUCCESS_RESULT_CODE:
                raise RuntimeError(
                    f"{params}: resultCode {header['resultCode']} ({header.get('resultMsg')})"
                )
            return data["response"]["body"]
        except RateLimitExceeded:
            raise  # 한도 소진 — 재시도 대상 아님, 상위에서 조기 중단
        except Exception:  # noqa: BLE001 — transient 대비 재시도 후 상위 전파
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            time.sleep(attempt)  # 1s, 2s 백오프


# ── 1. 측정소 목록 ──────────────────────────────────────────────────────

STATION_UPSERT_SQL = """INSERT INTO air_quality_station
    (station_name, addr, lat, lng, mang_name, measured_items)
    VALUES %s
    ON CONFLICT (station_name) DO UPDATE SET
        addr = EXCLUDED.addr,
        lat = EXCLUDED.lat,
        lng = EXCLUDED.lng,
        mang_name = EXCLUDED.mang_name,
        measured_items = EXCLUDED.measured_items,
        is_active = TRUE,
        updated_at = NOW()"""


def _fetch_station_page(page: int) -> tuple[list[dict], int]:
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "returnType": "json",
        "numOfRows": str(MAX_ROWS_PER_PAGE),
        "pageNo": str(page),
    }
    body = _request_json(STATION_LIST_URL, params)
    return body.get("items", []), int(body.get("totalCount", 0))


def _to_station_row(item: dict) -> tuple | None:
    """API 항목 → upsert 파라미터. dmX=위도/dmY=경도(명명 반전). 좌표 결측은 skip."""
    name = item.get("stationName")
    dm_x, dm_y = item.get("dmX"), item.get("dmY")
    if not name or dm_x is None or dm_y is None:
        return None
    try:
        lat, lng = float(dm_x), float(dm_y)
    except (TypeError, ValueError):
        return None
    return (
        name,
        (item.get("addr") or "")[:300],
        lat,
        lng,
        item.get("mangName"),
        item.get("item"),
    )


def fetch_stations(conn, logger) -> dict:
    """측정소 목록 전량 페이징 수집 + upsert.

    목록에서 사라진 측정소는 is_active=FALSE 처리(HIRA 폐업 패턴 준용).
    이 테이블은 본 함수만 전량 적재하므로 subtype 필터 없이 updated_at
    컷오프만으로 판별 가능(STORE/HIRA 처럼 표본/전량 분기 불필요).
    """
    cur = conn.cursor()
    cur.execute("SELECT NOW()")
    started_at = cur.fetchone()[0]  # DB 서버 시각 기준 — 앱/DB 시계 오차 방지

    fetched = skipped = 0
    rows: list[tuple] = []
    page = 1
    while True:
        items, total = _fetch_station_page(page)
        time.sleep(DATA_GO_KR_RATE)
        if not items:
            break
        for item in items:
            fetched += 1
            row = _to_station_row(item)
            if row is None:
                skipped += 1
                continue
            rows.append(row)
        if page * MAX_ROWS_PER_PAGE >= total:
            break
        page += 1

    upserted = execute_values_chunked(conn, STATION_UPSERT_SQL, rows) if rows else 0

    cur.execute(
        "UPDATE air_quality_station SET is_active = FALSE WHERE updated_at < %s",
        [started_at],
    )
    deactivated = cur.rowcount
    conn.commit()

    logger.info(
        f"측정소 수집 완료: 조회 {fetched:,} / 적재 {upserted:,} "
        f"/ 좌표결측skip {skipped:,} / 비활성화 {deactivated:,}"
    )
    return {
        "fetched": fetched,
        "upserted": upserted,
        "skipped": skipped,
        "deactivated": deactivated,
    }


# ── 2. 월평균 통계 ──────────────────────────────────────────────────────

MONTHLY_UPSERT_SQL = """INSERT INTO air_quality_monthly
    (station_name, measure_month, pm25, pm10, o3, no2)
    VALUES %s
    ON CONFLICT (station_name, measure_month) DO UPDATE SET
        pm25 = EXCLUDED.pm25,
        pm10 = EXCLUDED.pm10,
        o3 = EXCLUDED.o3,
        no2 = EXCLUDED.no2"""


def _fetch_monthly_page(mm: str, page: int) -> tuple[list[dict], int]:
    """단일 월(mm) 무필터 페이지 조회 — inqBginMm=inqEndMm=mm (모듈 docstring 근거 참조)."""
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "returnType": "json",
        "numOfRows": str(MAX_ROWS_PER_PAGE),
        "pageNo": str(page),
        "inqBginMm": mm,
        "inqEndMm": mm,
    }
    body = _request_json(MONTHLY_STATS_URL, params)
    return body.get("items", []), int(body.get("totalCount", 0))


def _parse_measurement(value) -> float | None:
    """API 응답 결측('' / '-' / None) → NULL. 0 으로 강제 변환 금지."""
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_monthly_row(item: dict) -> tuple | None:
    station_name, measure_month = item.get("msrstnName"), item.get("msurMm")
    if not station_name or not measure_month:
        return None
    return (
        station_name,
        measure_month,
        _parse_measurement(item.get("pm25Value")),
        _parse_measurement(item.get("pm10Value")),
        _parse_measurement(item.get("o3Value")),
        _parse_measurement(item.get("no2Value")),
    )


def _month_list(begin_mm: str, end_mm: str) -> list[str]:
    """'YYYYMM' 구간(포함) → 월 목록."""
    y, m = int(begin_mm[:4]), int(begin_mm[4:6])
    end_y, end_m = int(end_mm[:4]), int(end_mm[4:6])
    months = []
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _default_month_window(months_back: int) -> tuple[str, str]:
    """오늘 기준 최근 months_back개월 'YYYYMM' 구간(포함)."""
    today = date.today()
    end_mm = f"{today.year:04d}{today.month:02d}"
    y, m = today.year, today.month - (months_back - 1)
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}{m:02d}", end_mm


def fetch_monthly(
    conn, logger, begin_mm: str | None = None, end_mm: str | None = None
) -> dict:
    """월평균 수집. 기본 구간: 최근 DEFAULT_LOOKBACK_MONTHS개월.

    보유 윈도우가 실제로는 ~4개월뿐이라(PoC 실측) 그 밖 월은 totalCount=0 으로
    자연 skip 된다 — 에러 아님. 월 단위 개별 호출(모듈 docstring 근거 참조).
    """
    if end_mm is None or begin_mm is None:
        default_begin, default_end = _default_month_window(DEFAULT_LOOKBACK_MONTHS)
        begin_mm = begin_mm or default_begin
        end_mm = end_mm or default_end

    fetched = skipped = upserted = 0
    for mm in _month_list(begin_mm, end_mm):
        month_rows: list[tuple] = []
        page = 1
        while True:
            items, total = _fetch_monthly_page(mm, page)
            time.sleep(DATA_GO_KR_RATE)
            if not items:
                break
            for item in items:
                fetched += 1
                row = _to_monthly_row(item)
                if row is None:
                    skipped += 1
                    continue
                month_rows.append(row)
            if page * MAX_ROWS_PER_PAGE >= total:
                break
            page += 1

        if month_rows:
            upserted += execute_values_chunked(conn, MONTHLY_UPSERT_SQL, month_rows)
        logger.info(f"  {mm}: {len(month_rows):,}건 upsert (totalCount {total:,})")

    logger.info(
        f"월평균 수집 완료: 조회 {fetched:,} / 적재 {upserted:,} / 식별자결측skip {skipped:,}"
    )
    return {"fetched": fetched, "upserted": upserted, "skipped": skipped}


# ── 3. apt_air_score 재계산 ─────────────────────────────────────────────

AIR_SCORE_UPSERT_SQL = """INSERT INTO apt_air_score
    (pnu, station_name, station_distance_m, avg_pm25, month_count, score_air)
    VALUES %s
    ON CONFLICT (pnu) DO UPDATE SET
        station_name = EXCLUDED.station_name,
        station_distance_m = EXCLUDED.station_distance_m,
        avg_pm25 = EXCLUDED.avg_pm25,
        month_count = EXCLUDED.month_count,
        score_air = EXCLUDED.score_air,
        updated_at = NOW()"""


def _percentile_rank(values: np.ndarray) -> np.ndarray:
    """배열 내 각 값의 percentile rank (0~1).

    recalc_summary._percentile_rank 와 동일 알고리즘 — score_air 는 안전
    점수와 무관한 별도 수집기라 모듈 간 private 함수 결합을 피하기 위해
    로컬로 유지한다(둘 다 6줄 내외의 자명한 유틸이라 공통 모듈 추출 비용
    대비 이득이 낮음).
    """
    if len(values) == 0:
        return np.array([])
    sorted_vals = np.sort(values)
    return np.searchsorted(sorted_vals, values, side="right") / len(values)


def recalc_apt_air_score(conn, logger) -> int:
    """PM2.5 월평균 보유 측정소 기준 아파트 최근접 매핑 + 백분위(역방향) 점수 재계산.

    ① 대상 측정소(도시대기/교외대기 & PM2.5 월평균 보유)의 avg_pm25 계산
    ② BallTree(haversine)로 아파트 전체 최근접 매핑 (recalc_summary 관례)
    ③ 아파트 단위 avg_pm25 분포에서 백분위 역방향 점수 산출
       (score = (1 - percentile_rank) * 100 — PM2.5 낮을수록 고점)
    ④ apt_air_score 전량 upsert.
    """
    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        logger.error("scikit-learn 미설치 — apt_air_score 재계산 생략")
        return 0

    stations = query_all(
        conn,
        """
        SELECT s.station_name, s.lat, s.lng,
               AVG(m.pm25) AS avg_pm25, COUNT(m.pm25) AS month_count
        FROM air_quality_station s
        JOIN air_quality_monthly m ON m.station_name = s.station_name
        WHERE s.is_active
          AND s.mang_name IN %s
          AND m.pm25 IS NOT NULL
        GROUP BY s.station_name, s.lat, s.lng
        """,
        [RESIDENTIAL_MANG_NAMES],
    )
    if not stations:
        logger.warning("PM2.5 월평균 보유 측정소 없음 — apt_air_score 재계산 생략")
        return 0

    apts = query_all(
        conn,
        "SELECT pnu, lat, lng FROM apartments WHERE lat IS NOT NULL AND lng IS NOT NULL",
    )
    if not apts:
        logger.warning("좌표 보유 아파트 없음 — apt_air_score 재계산 생략")
        return 0

    station_coords = np.radians(np.array([[s["lat"], s["lng"]] for s in stations]))
    tree = BallTree(station_coords, metric="haversine")

    apt_coords = np.radians(np.array([[a["lat"], a["lng"]] for a in apts]))
    dists, idxs = tree.query(apt_coords, k=1)
    nearest_m = dists[:, 0] * EARTH_RADIUS_M
    nearest_idx = idxs[:, 0]

    avg_pm25_per_apt = np.array(
        [float(stations[i]["avg_pm25"]) for i in nearest_idx], dtype=float
    )
    score_per_apt = (1.0 - _percentile_rank(avg_pm25_per_apt)) * 100.0

    rows = [
        (
            apt["pnu"],
            stations[station_idx]["station_name"],
            round(float(dist_m), 1),
            round(float(avg_pm25), 2),
            int(stations[station_idx]["month_count"]),
            round(float(score), 2),
        )
        for apt, station_idx, dist_m, avg_pm25, score in zip(
            apts, nearest_idx, nearest_m, avg_pm25_per_apt, score_per_apt
        )
    ]

    upserted = execute_values_chunked(conn, AIR_SCORE_UPSERT_SQL, rows)
    logger.info(
        f"apt_air_score 재계산 완료: {upserted:,}건 (대상 측정소 {len(stations)}개, "
        f"평균 score_air {float(np.mean(score_per_apt)):.2f})"
    )
    return upserted


# ── 진입점 ──────────────────────────────────────────────────────────────


def collect_air_quality(conn, logger) -> dict:
    """측정소 + 월평균 수집 후 apt_air_score 재계산까지 일괄 수행.

    run.py 는 이 함수 하나만 호출한다(quarterly 7단계).
    """
    station_stats = fetch_stations(conn, logger)
    monthly_stats = fetch_monthly(conn, logger)
    scored = recalc_apt_air_score(conn, logger)
    return {
        "stations": station_stats["upserted"],
        "monthly_upserted": monthly_stats["upserted"],
        "scored": scored,
    }


def main() -> None:
    logger = setup_logger("air_quality")
    conn = get_connection()
    try:
        result = collect_air_quality(conn, logger)
        logger.info(
            f"전체 완료: 측정소 {result['stations']:,} / 월평균 {result['monthly_upserted']:,} "
            f"/ apt_air_score {result['scored']:,}"
        )
    except RateLimitExceeded as e:
        logger.warning(
            f"일일 호출 한도 도달({e}) — 자정 이후 재실행 필요, 부분 커밋 유지됨"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
