"""배정초등학교 거리 계산 → apt_facility_summary('assigned_elementary') 적재.

education 넛지의 1급 지표(1-1). school_zones 의 배정초교명을 facilities 의
school POI 와 매칭해 아파트→배정초교 거리를 계산한다.

매칭 규칙:
- 배정명 정규화: '~초' → '~초등학교' (예: '대구매호초' → '대구매호초등학교')
- 동명 학교 다수 시 아파트에서 가장 가까운 후보 선택 (3km 초과면 오매칭으로 간주)
- 실측(2026-07): 정규화 정확 일치 97% — 분모는 배정명 보유 행 기준
  (school_zones 미보유 포함 전체 아파트 기준 매칭 비율은 ~72%)

fallback (발동 조건을 반환 통계와 로그로 남김):
- school_zones 미보유(전체의 ~29%) 또는 매칭 실패(공동배정 '~공동(일방)' 표기 등)
  → 기존 summary 의 최근접 school 거리를 프록시로 사용.
  근거: 최근접 초등학교가 배정교인 경우가 다수 — 정확도보다 커버리지 우선,
  Phase 2(학교알리미 학교코드 좌표)에서 정밀화 예정.
- 프록시(school 행)도 없으면 행을 만들지 않는다 (런타임 결측 정책에 위임).

사용법:
  .venv/bin/python -m batch.quarterly.assigned_school            # 단독 실행
  (batch/run.py --type quarterly 의 4단계로도 호출됨)
"""

import math

from psycopg2.extras import execute_values

from batch.db import get_connection
from batch.logger import setup_logger

SUBTYPE = "assigned_elementary"
# 동명 학교 후보 중 이 거리(m)를 넘는 최근접 후보는 오매칭으로 간주
MATCH_MAX_DISTANCE_M = 3000.0
EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _normalize_school_name(name: str) -> str:
    """배정초교 축약명 → facilities 정식명 ('~초' → '~초등학교')."""
    name = name.strip()
    if name.endswith("초"):
        return name + "등학교"
    return name


def recalc_assigned_school(conn, logger, pnu_list: list[str] | None = None) -> dict:
    """배정초교 거리 재계산. 반환: {"matched": n, "fallback": n, "total": n}.

    pnu_list 지정 시 해당 아파트만 재계산 — trade 배치의 신규 아파트 경로용
    (미지정 시 quarterly 전체 재계산; 신규 단지를 다음 quarterly 까지 최대
    3개월 중립 50 으로 방치하지 않기 위한 즉시 등록 경로, 2026-07-05 감사).
    """
    cur = conn.cursor()

    # 1. school POI 인덱스 (이름 → [(lat, lng), ...])
    cur.execute(
        "SELECT name, lat, lng FROM facilities "
        "WHERE facility_subtype = 'school' AND lat IS NOT NULL AND lng IS NOT NULL"
    )
    school_index: dict[str, list[tuple[float, float]]] = {}
    for name, lat, lng in cur.fetchall():
        school_index.setdefault(name, []).append((lat, lng))
    logger.info(f"school POI 인덱스: {len(school_index):,}개 이름")

    # 2. 아파트 좌표 + 배정초교명 + 최근접 school 거리(프록시용)
    target_filter = ""
    params: list = []
    if pnu_list:
        target_filter = " AND a.pnu = ANY(%s)"
        params.append(list(pnu_list))
    cur.execute(
        f"""
        SELECT a.pnu, a.lat, a.lng, z.elementary_school_name, s.nearest_distance_m
        FROM apartments a
        LEFT JOIN school_zones z ON a.pnu = z.pnu
        LEFT JOIN apt_facility_summary s
               ON a.pnu = s.pnu AND s.facility_subtype = 'school'
        WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL{target_filter}
        """,
        params,
    )
    rows = cur.fetchall()

    matched = 0
    fallback = 0
    skipped = 0
    upsert_rows: list[tuple] = []

    for pnu, lat, lng, zone_name, nearest_school_m in rows:
        distance_m: float | None = None

        if zone_name:
            candidates = school_index.get(_normalize_school_name(zone_name))
            if candidates:
                best = min(_haversine_m(lat, lng, c[0], c[1]) for c in candidates)
                if best <= MATCH_MAX_DISTANCE_M:
                    distance_m = best
                    matched += 1

        if distance_m is None:
            # fallback: 최근접 school 거리 프록시 (발동 조건: 배정정보 미보유/매칭 실패)
            if nearest_school_m is not None:
                distance_m = float(nearest_school_m)
                fallback += 1
            else:
                skipped += 1
                continue

        # 단일 시설 지표: count_Nkm 은 밀도가 아니라 "해당 반경 내 존재 여부"(0/1).
        # count_1km 은 scoring 의 density factor 100 과 결합해 도보권 보너스로 쓰인다.
        within_1km = 1 if distance_m <= 1000.0 else 0
        within_3km = 1 if distance_m <= 3000.0 else 0
        within_5km = 1 if distance_m <= 5000.0 else 0
        upsert_rows.append(
            (pnu, SUBTYPE, round(distance_m, 1), within_1km, within_3km, within_5km)
        )

    # 3. upsert (PK: pnu, facility_subtype)
    execute_values(
        cur,
        """
        INSERT INTO apt_facility_summary
            (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km)
        VALUES %s
        ON CONFLICT (pnu, facility_subtype) DO UPDATE SET
            nearest_distance_m = EXCLUDED.nearest_distance_m,
            count_1km = EXCLUDED.count_1km,
            count_3km = EXCLUDED.count_3km,
            count_5km = EXCLUDED.count_5km
        """,
        upsert_rows,
        page_size=1000,
    )
    conn.commit()

    total = len(upsert_rows)
    logger.info(
        f"assigned_elementary 적재 {total:,}건 "
        f"(배정 매칭 {matched:,} / school 프록시 fallback {fallback:,} / 생략 {skipped:,})"
    )
    return {"matched": matched, "fallback": fallback, "total": total}


def main() -> None:
    logger = setup_logger("assigned_school")
    conn = get_connection()
    try:
        recalc_assigned_school(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
