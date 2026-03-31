"""facilities 테이블 UPSERT."""

from batch.db import execute_values_chunked


def update_facilities(conn, facility_rows, logger):
    """시설 데이터 UPSERT (facility_id 기준)."""
    if not facility_rows:
        logger.info("갱신할 시설 데이터 없음")
        return 0

    rows = [
        (r["facility_id"], r["facility_type"], r["facility_subtype"],
         r["name"], r["lat"], r["lng"], r["address"])
        for r in facility_rows
    ]

    cnt = execute_values_chunked(conn,
        """INSERT INTO facilities (facility_id, facility_type, facility_subtype, name, lat, lng, address)
           VALUES %s
           ON CONFLICT (facility_id) DO UPDATE SET
               name = EXCLUDED.name, lat = EXCLUDED.lat, lng = EXCLUDED.lng, address = EXCLUDED.address""",
        rows)

    logger.info(f"시설 UPSERT 완료: {cnt:,}건")
    return cnt
