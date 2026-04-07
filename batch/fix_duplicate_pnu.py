"""동일 도로명 주소에 중복 등록된 PNU 통합.

동일 주소에 법정동 코드/번지 차이로 별도 PNU가 생성된 경우,
거래 건수가 가장 많은 PNU를 주력으로 선정하고 나머지를 병합.

사용법:
  python -m batch.fix_duplicate_pnu           # dry-run (기본)
  python -m batch.fix_duplicate_pnu --execute  # 실제 실행
"""

import argparse
import math
import re
from collections import defaultdict

from batch.db import get_connection, get_dict_cursor, query_all, query_one
from batch.logger import setup_logger

# 안전장치: 좌표 거리 임계값 (미터)
MAX_DISTANCE_M = 500

# 이관 대상 테이블 (주력에 없을 때만 이관)
MIGRATE_TABLES = [
    ("apt_area_info", "pnu"),
    ("apt_kapt_info", "pnu"),
    ("apt_mgmt_cost", "pnu"),
    ("school_zones", "pnu"),
]

# 파생 데이터 테이블 (비주력 삭제 → 재계산)
DERIVED_TABLES = [
    "apt_facility_summary",
    "apt_safety_score",
    "apt_price_score",
    "apt_vectors",
]


def _haversine_m(lat1, lng1, lat2, lng2):
    """두 좌표 간 거리 (미터)."""
    if not all([lat1, lng1, lat2, lng2]):
        return float("inf")
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_trade_count(conn, pnu):
    """매매 + 전월세 거래 건수."""
    row = query_one(conn, """
        SELECT COUNT(*) as cnt FROM (
            SELECT t.id FROM trade_history t
            JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq WHERE m.pnu = %s
            UNION ALL
            SELECT r.id FROM rent_history r
            JOIN trade_apt_mapping m ON r.apt_seq = m.apt_seq WHERE m.pnu = %s
        ) sub
    """, [pnu, pnu])
    return row["cnt"] if row else 0


def _normalize_address(addr):
    """도로명 주소 정규화 — 괄호(동명) 제거, 공백 정리."""
    if not addr:
        return ""
    # "(오금동)" 같은 괄호 부분 제거
    normalized = re.sub(r"\s*\(.*?\)\s*$", "", addr.strip())
    return normalized


def _find_duplicate_groups(conn, logger):
    """동일 도로명 주소에 복수 PNU가 있는 그룹 탐지."""
    # 괄호 제거한 주소로 그룹핑
    all_apts = query_all(conn, """
        SELECT pnu, new_plat_plc FROM apartments
        WHERE new_plat_plc IS NOT NULL AND pnu NOT LIKE 'TRADE_%%'
    """)

    addr_groups = defaultdict(list)
    for r in all_apts:
        norm = _normalize_address(r["new_plat_plc"])
        if norm:
            addr_groups[norm].append(r["pnu"])

    rows = [{"new_plat_plc": addr, "pnus": pnus} for addr, pnus in addr_groups.items() if len(pnus) > 1]

    groups = []
    for r in rows:
        address = r["new_plat_plc"]
        pnus = r["pnus"]

        members = []
        for pnu in pnus:
            apt = query_one(conn, "SELECT pnu, bld_nm, lat, lng FROM apartments WHERE pnu = %s", [pnu])
            trade_cnt = _get_trade_count(conn, pnu)
            members.append({
                "pnu": pnu,
                "bld_nm": apt["bld_nm"] or "",
                "lat": apt["lat"],
                "lng": apt["lng"],
                "trade_count": trade_cnt,
            })

        # 거래 건수 내림차순 → 첫 번째가 주력
        members.sort(key=lambda x: x["trade_count"], reverse=True)
        primary = members[0]
        secondaries = members[1:]

        # 안전 검증: 좌표 거리
        max_dist = 0
        for s in secondaries:
            dist = _haversine_m(primary["lat"], primary["lng"], s["lat"], s["lng"])
            max_dist = max(max_dist, dist)

        skip = max_dist > MAX_DISTANCE_M
        display_dist = round(max_dist) if max_dist != float("inf") else -1

        groups.append({
            "address": address,
            "primary": primary,
            "secondaries": secondaries,
            "max_distance_m": display_dist,
            "skip": skip,
        })

    return groups


def _migrate_or_delete(cur, table, pk_col, from_pnu, to_pnu):
    """주력에 없으면 이관, 있으면 삭제."""
    # 주력에 이미 있는지 확인
    cur.execute(f"SELECT 1 FROM {table} WHERE {pk_col} = %s LIMIT 1", [to_pnu])
    has_primary = cur.fetchone() is not None

    if has_primary:
        # 주력이 이미 보유 → 비주력 삭제
        cur.execute(f"DELETE FROM {table} WHERE {pk_col} = %s", [from_pnu])
        return "deleted"
    else:
        # 주력에 없음 → 이관
        cur.execute(f"UPDATE {table} SET {pk_col} = %s WHERE {pk_col} = %s", [to_pnu, from_pnu])
        return "migrated"


def _merge_group(conn, group, logger, dry_run):
    """단일 그룹 통합 (트랜잭션 단위)."""
    primary_pnu = group["primary"]["pnu"]
    address = group["address"]

    if group["skip"]:
        logger.warning(f"  SKIP: {address} — 좌표 거리 {group['max_distance_m']}m > {MAX_DISTANCE_M}m")
        return False

    if dry_run:
        logger.info(f"  [DRY-RUN] {address}")
        logger.info(f"    주력: {primary_pnu} ({group['primary']['bld_nm']}) — {group['primary']['trade_count']}건")
        for s in group["secondaries"]:
            dist = _haversine_m(group["primary"]["lat"], group["primary"]["lng"], s["lat"], s["lng"])
            logger.info(f"    비주력: {s['pnu']} ({s['bld_nm']}) — {s['trade_count']}건, 거리 {round(dist)}m")
        return True

    cur = get_dict_cursor(conn)

    for sec in group["secondaries"]:
        sec_pnu = sec["pnu"]

        # 1. trade_apt_mapping 이관
        cur.execute(
            "UPDATE trade_apt_mapping SET pnu = %s WHERE pnu = %s",
            [primary_pnu, sec_pnu])
        mapping_cnt = cur.rowcount

        # 2. 이관 가능 테이블
        migrate_log = []
        for table, pk_col in MIGRATE_TABLES:
            result = _migrate_or_delete(cur, table, pk_col, sec_pnu, primary_pnu)
            migrate_log.append(f"{table}={result}")

        # 3. 파생 데이터 삭제
        for table in DERIVED_TABLES:
            cur.execute(f"DELETE FROM {table} WHERE pnu = %s", [sec_pnu])

        # 4. apartments 삭제
        cur.execute("DELETE FROM apartments WHERE pnu = %s", [sec_pnu])

        logger.info(
            f"    병합: {sec_pnu} → {primary_pnu} "
            f"(매핑 {mapping_cnt}건 이관, {', '.join(migrate_log)})"
        )

    return True


def main():
    parser = argparse.ArgumentParser(description="동일 주소 중복 PNU 통합")
    parser.add_argument("--execute", action="store_true", help="실제 실행 (기본: dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute
    logger = setup_logger("fix_dup_pnu")
    conn = get_connection()

    try:
        groups = _find_duplicate_groups(conn, logger)
        logger.info(f"중복 그룹: {len(groups)}개 {'(DRY-RUN)' if dry_run else '(EXECUTE)'}")

        merged = 0
        skipped = 0

        for group in groups:
            if dry_run:
                _merge_group(conn, group, logger, dry_run=True)
                if group["skip"]:
                    skipped += 1
                else:
                    merged += 1
            else:
                try:
                    success = _merge_group(conn, group, logger, dry_run=False)
                    if success:
                        conn.commit()
                        merged += 1
                    else:
                        skipped += 1
                except Exception as e:
                    conn.rollback()
                    logger.error(f"  ROLLBACK: {group['address']} — {e}")
                    skipped += 1

        logger.info(f"완료: 통합 {merged}건, 스킵 {skipped}건")

        if not dry_run and merged > 0:
            logger.info("후속 재계산이 필요합니다:")
            logger.info("  1. recalc_price (가격점수)")
            logger.info("  2. recalc_summary (시설집계 + 안전점수)")
            logger.info("  3. build_all_vectors (유사도 벡터)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
