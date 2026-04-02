"""facilities 테이블 갱신 (subtype별 DELETE → INSERT)."""

import psycopg2.extras
from batch.db import query_all


def update_facilities(conn, facility_rows, logger):
    """시설 데이터 갱신: subtype별 기존 삭제 → 신규 INSERT.

    facility_id가 비즈니스 키(좌표+이름 해시) 기반이므로
    같은 시설은 같은 ID로 재생성됨.
    """
    if not facility_rows:
        logger.info("갱신할 시설 데이터 없음")
        return 0

    cur = conn.cursor()

    # 수집된 subtype의 기존 데이터 삭제
    subtypes = set(r["facility_subtype"] for r in facility_rows)
    for st in subtypes:
        cur.execute("DELETE FROM facilities WHERE facility_subtype = %s", [st])
    conn.commit()

    # facility_id + 좌표+subtype 중복 제거
    seen_id = set()
    seen_coord = set()
    deduped = []
    for r in facility_rows:
        fid = r["facility_id"]
        coord_key = (r["facility_subtype"], round(r["lat"], 10), round(r["lng"], 10))
        if fid not in seen_id and coord_key not in seen_coord:
            seen_id.add(fid)
            seen_coord.add(coord_key)
            deduped.append(r)

    if len(deduped) < len(facility_rows):
        logger.info(f"  좌표 중복 제거: {len(facility_rows):,} → {len(deduped):,}건")

    # INSERT
    rows = [
        (r["facility_id"], r["facility_type"], r["facility_subtype"],
         r["name"], r["lat"], r["lng"], r["address"])
        for r in deduped
    ]

    sql = """INSERT INTO facilities (facility_id, facility_type, facility_subtype, name, lat, lng, address)
             VALUES %s
             ON CONFLICT (facility_id) DO UPDATE SET
                 name = EXCLUDED.name, lat = EXCLUDED.lat, lng = EXCLUDED.lng,
                 address = EXCLUDED.address"""

    total = 0
    chunk_size = 10000
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        psycopg2.extras.execute_values(cur, sql, chunk, page_size=chunk_size)
        total += len(chunk)
    conn.commit()

    logger.info(f"시설 갱신 완료: {total:,}건")
    return total
