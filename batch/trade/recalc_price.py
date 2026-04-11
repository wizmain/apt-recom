"""가격 점수 재계산 + 신규 거래-아파트 매핑."""

import re
from batch.db import query_all, query_one, execute_values_chunked


def _normalize_name(name):
    if not name:
        return ""
    return re.sub(r"[\s()\-·\d동호]", "", str(name)).strip()


def _core_name(name):
    if not name:
        return ""
    n = re.sub(r"[\s()\-·]", "", str(name))
    n = re.sub(r"\d+동?\d*호?$", "", n)
    n = re.sub(r"(아파트|APT|아이파크|자이|래미안|힐스테이트|푸르지오|e편한세상|롯데캐슬)$", "", n)
    return n.strip()


def _update_mapping(conn, logger):
    """신규 apt_seq에 대해 trade_apt_mapping 추가.

    매핑 순서: 이름 매칭(1~3순위) → PNU 직접 조합(4순위, 주소 필드 있을 때만).
    """
    # 미매핑 apt_seq 조회
    unmapped = query_all(conn, """
        SELECT DISTINCT t.apt_seq, t.sgg_cd, t.apt_nm
        FROM trade_history t
        WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
        UNION
        SELECT DISTINCT r.apt_seq, r.sgg_cd, r.apt_nm
        FROM rent_history r
        WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
    """)

    if not unmapped:
        logger.info("  매핑 대상 신규 apt_seq 없음")
        return

    logger.info(f"  미매핑 apt_seq: {len(unmapped):,}건")

    # 아파트 마스터
    apts = query_all(conn, "SELECT pnu, bld_nm, sigungu_code FROM apartments")
    apt_by_sgg: dict[str, list] = {}
    for a in apts:
        sgg = (a["sigungu_code"] or "")[:5]
        if sgg not in apt_by_sgg:
            apt_by_sgg[sgg] = []
        apt_by_sgg[sgg].append({
            "pnu": a["pnu"],
            "bld_nm": a["bld_nm"] or "",
            "norm": _normalize_name(a["bld_nm"]),
            "core": _core_name(a["bld_nm"]),
        })

    new_mappings = []
    for row in unmapped:
        sgg = str(row["sgg_cd"])[:5]
        apt_nm = str(row["apt_nm"])
        norm = _normalize_name(apt_nm)
        core = _core_name(apt_nm)
        candidates = apt_by_sgg.get(sgg, [])

        matched_pnu = None
        method = None

        # 1. 정확 매칭
        for c in candidates:
            if c["norm"] and c["norm"] == norm:
                matched_pnu, method = c["pnu"], "exact_name"
                break

        # 2. 포함 매칭
        if not matched_pnu and norm:
            found = [c for c in candidates if c["norm"] and len(min(norm, c["norm"], key=len)) >= 3 and (norm in c["norm"] or c["norm"] in norm)]
            if len(found) == 1:
                matched_pnu, method = found[0]["pnu"], "contains"

        # 3. 핵심명 매칭
        if not matched_pnu and core and len(core) >= 2:
            found = [c for c in candidates if c["core"] == core]
            if len(found) == 1:
                matched_pnu, method = found[0]["pnu"], "core_match"

        if matched_pnu:
            new_mappings.append((row["apt_seq"], matched_pnu, apt_nm, sgg, method))

    if new_mappings:
        execute_values_chunked(conn,
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) VALUES %s ON CONFLICT (apt_seq) DO NOTHING",
            new_mappings)
        logger.info(f"  신규 매핑 {len(new_mappings):,}건 추가")


def recalc_price(conn, logger):
    """apt_price_score 전체 재계산."""
    _update_mapping(conn, logger)

    cur = conn.cursor()

    # 면적 범위 밖 거래 건수 로깅
    filtered = query_one(conn, """
        SELECT COUNT(*) as cnt
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apt_area_info ai ON m.pnu = ai.pnu
        WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
          AND (t.exclu_use_ar < ai.min_area * 0.9
               OR t.exclu_use_ar > ai.max_area * 1.1)
    """)
    logger.info(f"  면적 범위 밖 거래 제외: {filtered['cnt']:,}건")

    # 가격 점수 재계산
    cur.execute("DELETE FROM apt_price_score")

    # 아파트별 ㎡당 평균 가격 (면적 범위 검증 포함)
    rows = query_all(conn, """
        SELECT m.pnu, a.sigungu_code,
               AVG(t.deal_amount * 10000.0 / t.exclu_use_ar) as price_per_m2
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON m.pnu = a.pnu
        LEFT JOIN apt_area_info ai ON m.pnu = ai.pnu
        WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
          AND (ai.pnu IS NULL
               OR (t.exclu_use_ar >= ai.min_area * 0.9
                   AND t.exclu_use_ar <= ai.max_area * 1.1))
        GROUP BY m.pnu, a.sigungu_code
    """)

    if not rows:
        logger.info("  매핑된 거래 데이터 없음")
        conn.commit()
        return 0

    # 시군구 평균
    sgg_avg: dict[str, float] = {}
    for r in rows:
        sgg = (r["sigungu_code"] or "")[:5]
        if sgg not in sgg_avg:
            sgg_avg[sgg] = []
        sgg_avg[sgg].append(r["price_per_m2"])
    sgg_avg = {k: sum(v) / len(v) for k, v in sgg_avg.items()}

    # 전세가율 (면적 범위 검증 포함)
    jeonse_map: dict[str, float] = {}
    jr = query_all(conn, """
        SELECT m.pnu, AVG(r.deposit) as avg_dep, AVG(t.deal_amount) as avg_deal
        FROM rent_history r
        JOIN trade_apt_mapping m ON r.apt_seq = m.apt_seq
        JOIN trade_history t ON t.apt_seq = m.apt_seq AND t.deal_amount > 0
        LEFT JOIN apt_area_info ai ON m.pnu = ai.pnu
        WHERE r.monthly_rent = 0 AND r.deposit > 0
          AND (ai.pnu IS NULL
               OR (t.exclu_use_ar >= ai.min_area * 0.9
                   AND t.exclu_use_ar <= ai.max_area * 1.1))
          AND (ai.pnu IS NULL
               OR (r.exclu_use_ar >= ai.min_area * 0.9
                   AND r.exclu_use_ar <= ai.max_area * 1.1))
        GROUP BY m.pnu
    """)
    for r in jr:
        if r["avg_deal"] and r["avg_deal"] > 0:
            jeonse_map[r["pnu"]] = round(r["avg_dep"] / r["avg_deal"] * 100, 1)

    # 점수 계산 + INSERT
    score_rows = []
    for r in rows:
        pnu = r["pnu"]
        ppm2 = r["price_per_m2"]
        sgg = (r["sigungu_code"] or "")[:5]
        avg = sgg_avg.get(sgg, ppm2)
        ratio = ppm2 / avg if avg > 0 else 1.0
        score = round(max(0, min(100, (2 - ratio) * 50)), 1)
        jr_val = jeonse_map.get(pnu, 0)
        score_rows.append((pnu, round(ppm2, 1), round(avg, 1), score, jr_val))

    execute_values_chunked(conn,
        "INSERT INTO apt_price_score (pnu, price_per_m2, sgg_avg_price_per_m2, price_score, jeonse_ratio) VALUES %s",
        score_rows)

    logger.info(f"  apt_price_score 재계산: {len(score_rows):,}건")
    return len(score_rows)
