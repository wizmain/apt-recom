"""인구 DB 갱신 (범죄는 batch/safety/load_safety_data.py 로 일원화)."""

from batch.db import execute_values_chunked


def update_population(conn, pop_rows, logger):
    """population_by_district UPSERT."""
    if not pop_rows:
        return 0

    rows = [
        (
            r["sigungu_code"],
            r["sigungu_name"],
            r["sido_name"],
            r["age_group"],
            r["total_pop"],
            r["male_pop"],
            r["female_pop"],
        )
        for r in pop_rows
    ]

    cnt = execute_values_chunked(
        conn,
        """INSERT INTO population_by_district
           (sigungu_code, sigungu_name, sido_name, age_group, total_pop, male_pop, female_pop)
           VALUES %s
           ON CONFLICT (sigungu_code, age_group) DO UPDATE SET
               total_pop = EXCLUDED.total_pop, male_pop = EXCLUDED.male_pop, female_pop = EXCLUDED.female_pop""",
        rows,
    )

    logger.info(f"인구 DB 갱신: {cnt:,}건")
    return cnt


# 범죄 갱신은 batch/safety/load_safety_data.py (sigungu_crime_detail) 로 일원화됨.
# 구 update_crime(sigungu_crime_score 77행 경로)은 2026-07-04 제거 — run.py run_annual 주석 참조.
