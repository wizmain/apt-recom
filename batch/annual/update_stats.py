"""인구/범죄 DB 갱신."""

from batch.db import execute_values_chunked


def update_population(conn, pop_rows, logger):
    """population_by_district UPSERT."""
    if not pop_rows:
        return 0

    rows = [
        (r["sigungu_code"], r["sigungu_name"], r["sido_name"],
         r["age_group"], r["total_pop"], r["male_pop"], r["female_pop"])
        for r in pop_rows
    ]

    cnt = execute_values_chunked(conn,
        """INSERT INTO population_by_district
           (sigungu_code, sigungu_name, sido_name, age_group, total_pop, male_pop, female_pop)
           VALUES %s
           ON CONFLICT (sigungu_code, age_group) DO UPDATE SET
               total_pop = EXCLUDED.total_pop, male_pop = EXCLUDED.male_pop, female_pop = EXCLUDED.female_pop""",
        rows)

    logger.info(f"인구 DB 갱신: {cnt:,}건")
    return cnt


def update_crime(conn, crime_rows, logger):
    """sigungu_crime_score UPSERT."""
    if not crime_rows:
        return 0

    # 범죄 데이터 → 시군구별 점수 계산
    from collections import defaultdict
    sgg_crimes = defaultdict(lambda: {"total": 0, "murder": 0, "robbery": 0,
                                       "sexual_assault": 0, "theft": 0, "violence": 0})

    for r in crime_rows:
        sgg = str(r.get("sggCd", r.get("sigungu_code", "")))[:5]
        if not sgg:
            continue
        sgg_crimes[sgg]["total"] += int(float(r.get("totalCrime", r.get("total_crime", 0)) or 0))
        sgg_crimes[sgg]["murder"] += int(float(r.get("murder", 0) or 0))
        sgg_crimes[sgg]["robbery"] += int(float(r.get("robbery", 0) or 0))
        sgg_crimes[sgg]["sexual_assault"] += int(float(r.get("sexualAssault", r.get("sexual_assault", 0)) or 0))
        sgg_crimes[sgg]["theft"] += int(float(r.get("theft", 0) or 0))
        sgg_crimes[sgg]["violence"] += int(float(r.get("violence", 0) or 0))

    if not sgg_crimes:
        logger.info("범죄 데이터 파싱 결과 없음")
        return 0

    # 점수 계산 (범죄율 기반 0-100, 낮을수록 안전)
    max_total = max(v["total"] for v in sgg_crimes.values()) or 1
    rows = []
    for sgg, crimes in sgg_crimes.items():
        score = round(max(0, 100 - (crimes["total"] / max_total * 100)), 1)
        rows.append((sgg, score))

    cur = conn.cursor()
    cur.execute("DELETE FROM sigungu_crime_score")
    execute_values_chunked(conn,
        "INSERT INTO sigungu_crime_score (sigungu_code, crime_safety_score) VALUES %s",
        rows)

    logger.info(f"범죄 DB 갱신: {len(rows):,}건")
    return len(rows)
