"""거래 데이터 신규 컬럼 백필 + 매핑 검증/수정.

1단계: umd_cd 등 NULL인 기존 레코드를 API 재수집으로 보충
2단계: 보충된 PNU 정보로 기존 매핑 검증, 잘못된 매핑 수정

일일 API 한도를 고려하여 --max-calls로 호출 수 제한.
체크포인트를 DB(common_code)에 저장하여 이어서 실행 가능.
SECONDARY KEY 사용 (primary key와 한도 분리).

사용법:
  python -m batch.run --type backfill [--max-calls 900]
"""

import json
import re
import time

import requests

from batch.config import DATA_GO_KR_API_SECONDARY_KEY, TRADE_URL, RENT_URL, DATA_GO_KR_RATE
from batch.trade.collect_trades import _parse_xml, TRADE_COL_MAP, RENT_COL_MAP
from batch.trade.enrich_apartments import _names_overlap
from batch.db import query_all, query_one

CHECKPOINT_GROUP = "backfill_trade_checkpoint"


def _clean_amount(val):
    if not val:
        return None
    cleaned = re.sub(r"[,\s]", "", str(val))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _to_int(val):
    try:
        return int(float(val)) if val else None
    except (ValueError, TypeError):
        return None


def _to_float(val):
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def _call_api_secondary(url, lawd_cd, deal_ymd, retries=3):
    """Secondary key를 사용하는 API 호출."""
    params = {
        "serviceKey": DATA_GO_KR_API_SECONDARY_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": "1",
        "numOfRows": "10000",
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return None


def _load_checkpoint(conn):
    """DB에서 완료된 (sgg_cd, yyyymm) 세트 로드."""
    row = query_one(conn, "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
                    [CHECKPOINT_GROUP, "completed"])
    if row and row["name"]:
        return set(json.loads(row["name"]))
    return set()


def _save_checkpoint(conn, completed):
    """DB에 체크포인트 저장."""
    data = json.dumps(sorted(completed), ensure_ascii=False)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [CHECKPOINT_GROUP, "completed", data, str(len(completed))],
    )
    conn.commit()


def _get_backfill_targets(conn):
    """umd_cd IS NULL인 거래의 (sgg_cd, deal_year*100+deal_month) 조합 목록."""
    rows = query_all(conn, """
        SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym
        FROM trade_history WHERE umd_cd IS NULL
        UNION
        SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym
        FROM rent_history WHERE umd_nm IS NULL
        ORDER BY ym, sgg_cd
    """)
    return [(str(r["sgg_cd"]), str(r["ym"])) for r in rows]


def _update_trade_rows(conn, api_rows):
    """API 응답으로 trade_history의 NULL 컬럼 업데이트."""
    cur = conn.cursor()
    updated = 0
    for r in api_rows:
        sgg = str(r.get("sggCd", ""))
        apt_nm = str(r.get("aptNm", ""))
        exclu = _to_float(r.get("excluUseAr"))
        floor = _to_int(r.get("floor"))
        dy = _to_int(r.get("dealYear"))
        dm = _to_int(r.get("dealMonth"))
        dd = _to_int(r.get("dealDay"))
        amount = _clean_amount(r.get("dealAmount"))
        if not all([sgg, apt_nm, exclu is not None, dy, dm, dd, amount]):
            continue

        cur.execute("""
            UPDATE trade_history SET
                umd_nm = %s, umd_cd = %s, jibun = %s, bonbun = %s, bubun = %s, land_cd = %s,
                road_nm = %s, road_nm_bonbun = %s, road_nm_bubun = %s, apt_dong = %s,
                buyer_gbn = %s, dealing_gbn = %s, rgst_date = %s, api_apt_seq = %s
            WHERE sgg_cd = %s AND apt_nm = %s AND exclu_use_ar = %s AND floor = %s
              AND deal_year = %s AND deal_month = %s AND deal_day = %s AND deal_amount = %s
              AND umd_cd IS NULL
        """, [
            r.get("umdNm") or None, r.get("umdCd") or None,
            r.get("jibun") or None, r.get("bonbun") or None,
            r.get("bubun") or None, r.get("landCd") or None,
            r.get("roadNm") or None, r.get("roadNmBonbun") or None,
            r.get("roadNmBubun") or None, r.get("aptDong") or None,
            r.get("buyerGbn") or None, r.get("dealingGbn") or None,
            r.get("rgstDate") or None, r.get("aptSeq") or None,
            sgg, apt_nm, exclu, floor, dy, dm, dd, amount,
        ])
        updated += cur.rowcount
    return updated


def _update_rent_rows(conn, api_rows):
    """API 응답으로 rent_history의 NULL 컬럼 업데이트."""
    cur = conn.cursor()
    updated = 0
    for r in api_rows:
        sgg = str(r.get("sggCd", ""))
        apt_nm = str(r.get("aptNm", ""))
        exclu = _to_float(r.get("excluUseAr"))
        floor = _to_int(r.get("floor"))
        dy = _to_int(r.get("dealYear"))
        dm = _to_int(r.get("dealMonth"))
        dd = _to_int(r.get("dealDay"))
        deposit = _clean_amount(r.get("deposit"))
        if not all([sgg, apt_nm, exclu is not None, dy, dm]):
            continue

        cur.execute("""
            UPDATE rent_history SET
                umd_nm = %s, jibun = %s, road_nm = %s, road_nm_bonbun = %s, road_nm_bubun = %s,
                contract_type = %s, contract_term = %s, pre_deposit = %s, pre_monthly_rent = %s,
                use_rr_right = %s, api_apt_seq = %s
            WHERE sgg_cd = %s AND apt_nm = %s AND exclu_use_ar = %s AND floor = %s
              AND deal_year = %s AND deal_month = %s AND deal_day = %s AND deposit = %s
              AND umd_nm IS NULL
        """, [
            r.get("umdNm") or None, r.get("jibun") or None,
            r.get("roadNm") or None, r.get("roadNmBonbun") or None,
            r.get("roadNmBubun") or None, r.get("contractType") or None,
            r.get("contractTerm") or None,
            _clean_amount(r.get("preDeposit")),
            _clean_amount(r.get("preMonthlyRent")),
            r.get("useRRRight") or None, r.get("aptSeq") or None,
            sgg, apt_nm, exclu, floor, dy, dm, dd, deposit,
        ])
        updated += cur.rowcount
    return updated


# ── 매핑 검증/수정 ──

def _verify_and_fix_mappings(conn, logger):
    """백필된 PNU 정보(bonbun, bubun, umd_cd)로 기존 매핑을 검증하고 잘못된 것을 수정.

    검증 기준:
      1. 시군구 일치: trade_history.sgg_cd == apartments.sigungu_code
      2. PNU 직접 조합: sggCd+umdCd+landCd+bonbun+bubun → 19자리 PNU
         조합된 PNU가 매핑된 PNU와 다르면 잘못된 매핑
      3. 이름 유사도: 거래명과 아파트명 2글자 이상 공통 부분 필수
    """
    # bonbun이 채워진 매핑만 검증 대상
    rows = query_all(conn, """
        SELECT DISTINCT t.apt_seq, t.sgg_cd, t.apt_nm,
               t.umd_cd, t.bonbun, t.bubun, t.land_cd,
               m.pnu AS mapped_pnu, a.bld_nm AS mapped_bld_nm
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE t.bonbun IS NOT NULL AND t.umd_cd IS NOT NULL
          AND m.pnu NOT LIKE 'TRADE_%%'
    """)

    if not rows:
        logger.info("  매핑 검증: 대상 없음")
        return 0

    # 기존 PNU 목록 로드
    existing_pnus = set(r["pnu"] for r in query_all(conn, "SELECT pnu FROM apartments"))
    existing_names = {r["pnu"]: r["bld_nm"] or "" for r in query_all(conn, "SELECT pnu, bld_nm FROM apartments")}

    cur = conn.cursor()
    fixed_pnu = 0
    fixed_name = 0
    fixed_fallback = 0

    for r in rows:
        sgg_cd = str(r["sgg_cd"])[:5]
        umd_cd = str(r["umd_cd"]).strip()
        bonbun = str(r["bonbun"]).strip()
        bubun = str(r["bubun"] or "0").strip()
        land_cd = str(r["land_cd"] or "0").strip()
        mapped_pnu = r["mapped_pnu"]
        apt_nm = str(r["apt_nm"])

        # PNU 직접 조합
        composed_pnu = f"{sgg_cd}{umd_cd}{land_cd}{bonbun.zfill(4)}{bubun.zfill(4)}"
        if len(composed_pnu) != 19:
            continue

        # 1. 조합된 PNU와 매핑된 PNU가 다른 경우
        if composed_pnu != mapped_pnu and composed_pnu in existing_pnus:
            composed_name = existing_names.get(composed_pnu, "")
            if _names_overlap(apt_nm, composed_name):
                # 올바른 PNU로 수정
                cur.execute(
                    "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE apt_seq = %s",
                    [composed_pnu, "backfill_pnu_fix", r["apt_seq"]],
                )
                fixed_pnu += 1
                continue

        # 2. 매핑된 아파트와 이름 불일치
        mapped_name = r["mapped_bld_nm"] or ""
        if mapped_name and not _names_overlap(apt_nm, mapped_name):
            # 조합 PNU가 기존 아파트에 있으면 그쪽으로 수정
            if composed_pnu in existing_pnus:
                composed_name = existing_names.get(composed_pnu, "")
                if _names_overlap(apt_nm, composed_name):
                    cur.execute(
                        "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE apt_seq = %s",
                        [composed_pnu, "backfill_name_fix", r["apt_seq"]],
                    )
                    fixed_name += 1
                    continue

            # PNU 조합도 실패 → TRADE_ fallback
            trade_pnu = f"TRADE_{sgg_cd}_{apt_nm}"
            cur.execute(
                "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                [trade_pnu, apt_nm, sgg_cd, trade_pnu],
            )
            cur.execute(
                "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE apt_seq = %s",
                [trade_pnu, "backfill_fallback", r["apt_seq"]],
            )
            fixed_fallback += 1

    conn.commit()
    total_fixed = fixed_pnu + fixed_name + fixed_fallback
    if total_fixed > 0:
        logger.info(f"  매핑 수정: PNU교정={fixed_pnu}, 이름교정={fixed_name}, fallback={fixed_fallback}")
    else:
        logger.info("  매핑 검증: 이상 없음")
    return total_fixed


def backfill_trades(conn, logger, max_calls=900, dry_run=False):
    """기존 거래 데이터의 NULL 컬럼을 API 재수집으로 보충 + 매핑 검증."""
    targets = _get_backfill_targets(conn)
    completed = _load_checkpoint(conn)

    remaining = [(sgg, ym) for sgg, ym in targets if f"{sgg}:{ym}" not in completed]

    logger.info(f"백필 대상: {len(targets)}쌍, 완료: {len(completed)}쌍, 남은: {len(remaining)}쌍")
    logger.info(f"이번 실행 최대: {max_calls}콜 ({max_calls // 2}쌍)")

    if not remaining:
        logger.info("백필 완료 — 남은 대상 없음")
        if not dry_run:
            _verify_and_fix_mappings(conn, logger)
        return 0

    call_count = 0
    pair_count = 0
    total_trade_updated = 0
    total_rent_updated = 0

    for sgg, ym in remaining:
        if call_count >= max_calls:
            logger.info(f"한도 도달 ({call_count}콜). 다음 실행에서 이어서 처리.")
            break

        # 매매 API 호출 (secondary key)
        xml = _call_api_secondary(TRADE_URL, sgg, ym)
        trade_rows = _parse_xml(xml, TRADE_COL_MAP)
        call_count += 1
        time.sleep(DATA_GO_KR_RATE)

        # 전월세 API 호출 (secondary key)
        xml = _call_api_secondary(RENT_URL, sgg, ym)
        rent_rows = _parse_xml(xml, RENT_COL_MAP)
        call_count += 1
        time.sleep(DATA_GO_KR_RATE)

        if not dry_run:
            t_updated = _update_trade_rows(conn, trade_rows) if trade_rows else 0
            r_updated = _update_rent_rows(conn, rent_rows) if rent_rows else 0
            total_trade_updated += t_updated
            total_rent_updated += r_updated

        # 체크포인트
        completed.add(f"{sgg}:{ym}")
        pair_count += 1

        if pair_count % 50 == 0:
            if not dry_run:
                conn.commit()
            _save_checkpoint(conn, completed)
            logger.info(f"  진행: {pair_count}쌍 ({call_count}콜) | 매매 +{total_trade_updated:,}, 전월세 +{total_rent_updated:,}")

    if not dry_run:
        conn.commit()
    _save_checkpoint(conn, completed)

    logger.info(f"이번 실행 완료: {pair_count}쌍, {call_count}콜")
    logger.info(f"  매매 업데이트: {total_trade_updated:,}건, 전월세 업데이트: {total_rent_updated:,}건")
    logger.info(f"전체 진행: {len(completed)}/{len(targets)}쌍 ({len(completed) * 100 // max(len(targets), 1)}%)")

    # 매핑 검증/수정
    if not dry_run and total_trade_updated > 0:
        logger.info("매핑 검증 시작...")
        _verify_and_fix_mappings(conn, logger)

    return total_trade_updated + total_rent_updated
