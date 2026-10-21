"""거래 데이터 중복 제거 후 DB 적재."""

import re
from batch.db import execute_values_chunked, query_all
from batch.region_codes import load_aliases, normalize_sigungu_code
from batch.trade.trade_keys import resolve_trade_key


def _clean_amount(val):
    """쉼표/공백 제거 후 정수 변환."""
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


def load_trades(conn, trade_rows, rent_rows, logger):
    """거래/전월세 데이터를 중복 제거 후 INSERT."""
    total_inserted = 0

    # ADR-013: 내부 표준은 구코드. 질의는 구코드(LAWD_CD)로 하지만 응답
    # sggCd 는 신코드로 올 수 있어(2026-08-29 실측: 광주·전남 12xxx,
    # 인천 28275/28290 로 2,706건 원코드 유입) 적재 경계에서 접는다.
    # 이름 키 "{sgg}_{apt_nm}"(aptSeq 없을 때의 키, legacy_apt_seq)가 시군구 코드를
    # 포함하므로 여기서 접어야 하류(매핑·등록)까지 구코드로 일관된다.
    # 미지의 코드는 그대로 두고 audit_unknown_codes 가 감시.
    aliases = load_aliases(conn)

    # ── 매매 ──
    if trade_rows:
        # 수집된 월 목록
        months = set()
        for r in trade_rows:
            y, m = _to_int(r.get("dealYear")), _to_int(r.get("dealMonth"))
            if y and m:
                months.add((y, m))

        # 해당 월의 기존 데이터 키 조회
        existing_keys = set()
        for y, m in months:
            rows = query_all(
                conn,
                "SELECT sgg_cd, apt_nm, exclu_use_ar, floor, deal_year, deal_month, deal_day, deal_amount "
                "FROM trade_history WHERE deal_year = %s AND deal_month = %s",
                [y, m],
            )
            for r in rows:
                existing_keys.add(
                    (
                        str(r["sgg_cd"]),
                        str(r["apt_nm"]),
                        str(r["exclu_use_ar"]),
                        str(r["floor"]),
                        r["deal_year"],
                        r["deal_month"],
                        r["deal_day"],
                        r["deal_amount"],
                    )
                )

        # 신규 건만 필터
        new_rows = []
        for r in trade_rows:
            sgg = normalize_sigungu_code(str(r.get("sggCd", "")), aliases)
            apt_nm = str(r.get("aptNm", ""))
            exclu = str(r.get("excluUseAr", ""))
            floor = str(r.get("floor", ""))
            dy = _to_int(r.get("dealYear"))
            dm = _to_int(r.get("dealMonth"))
            dd = _to_int(r.get("dealDay"))
            amount = _clean_amount(r.get("dealAmount"))
            if not dy or not dm or not amount:
                continue

            dedup_key = (sgg, apt_nm, exclu, floor, dy, dm, dd, amount)
            if dedup_key in existing_keys:
                continue

            key = resolve_trade_key(sgg, apt_nm, r.get("aptSeq"))
            new_rows.append(
                (
                    key.apt_seq,
                    sgg,
                    apt_nm,
                    amount,
                    _to_float(r.get("excluUseAr")),
                    _to_int(r.get("floor")),
                    dy,
                    dm,
                    dd,
                    _to_int(r.get("buildYear")),
                    r.get("umdNm") or None,
                    r.get("umdCd") or None,
                    r.get("jibun") or None,
                    r.get("bonbun") or None,
                    r.get("bubun") or None,
                    r.get("landCd") or None,
                    r.get("roadNm") or None,
                    r.get("roadNmBonbun") or None,
                    r.get("roadNmBubun") or None,
                    r.get("aptDong") or None,
                    r.get("buyerGbn") or None,
                    r.get("dealingGbn") or None,
                    r.get("rgstDate") or None,
                    r.get("aptSeq") or None,
                    key.legacy_apt_seq,
                    key.apt_seq_method,
                )
            )

        if new_rows:
            cnt = execute_values_chunked(
                conn,
                "INSERT INTO trade_history (apt_seq, sgg_cd, apt_nm, deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day, build_year,"
                " umd_nm, umd_cd, jibun, bonbun, bubun, land_cd, road_nm, road_nm_bonbun, road_nm_bubun, apt_dong, buyer_gbn, dealing_gbn, rgst_date, api_apt_seq,"
                " legacy_apt_seq, apt_seq_method) VALUES %s"
                " ON CONFLICT (sgg_cd, apt_nm, exclu_use_ar, floor, deal_year, deal_month, deal_day, deal_amount) DO NOTHING",
                new_rows,
            )
            total_inserted += cnt
            logger.info(
                f"  매매 신규 {cnt:,}건 적재 (후보 {len(new_rows):,}건 중 중복 {len(new_rows) - cnt:,}건,"
                f" 기존 키 {len(existing_keys):,}건)"
            )
        else:
            logger.info("  매매 신규 건 없음")

    # ── 전월세 ──
    if rent_rows:
        months = set()
        for r in rent_rows:
            y, m = _to_int(r.get("dealYear")), _to_int(r.get("dealMonth"))
            if y and m:
                months.add((y, m))

        existing_keys = set()
        for y, m in months:
            rows = query_all(
                conn,
                "SELECT sgg_cd, apt_nm, exclu_use_ar, floor, deal_year, deal_month, deal_day, deposit "
                "FROM rent_history WHERE deal_year = %s AND deal_month = %s",
                [y, m],
            )
            for r in rows:
                existing_keys.add(
                    (
                        str(r["sgg_cd"]),
                        str(r["apt_nm"]),
                        str(r["exclu_use_ar"]),
                        str(r["floor"]),
                        r["deal_year"],
                        r["deal_month"],
                        r["deal_day"],
                        r["deposit"],
                    )
                )

        new_rows = []
        for r in rent_rows:
            sgg = normalize_sigungu_code(str(r.get("sggCd", "")), aliases)
            apt_nm = str(r.get("aptNm", ""))
            exclu = str(r.get("excluUseAr", ""))
            floor = str(r.get("floor", ""))
            dy = _to_int(r.get("dealYear"))
            dm = _to_int(r.get("dealMonth"))
            dd = _to_int(r.get("dealDay"))
            deposit = _clean_amount(r.get("deposit"))
            if not dy or not dm:
                continue

            dedup_key = (sgg, apt_nm, exclu, floor, dy, dm, dd, deposit)
            if dedup_key in existing_keys:
                continue

            key = resolve_trade_key(sgg, apt_nm, r.get("aptSeq"))
            monthly_rent = _clean_amount(r.get("monthlyRent")) or 0
            new_rows.append(
                (
                    key.apt_seq,
                    sgg,
                    apt_nm,
                    deposit,
                    monthly_rent,
                    _to_float(r.get("excluUseAr")),
                    _to_int(r.get("floor")),
                    dy,
                    dm,
                    dd,
                    r.get("umdNm") or None,
                    r.get("jibun") or None,
                    r.get("roadNm") or None,
                    r.get("roadNmBonbun") or None,
                    r.get("roadNmBubun") or None,
                    r.get("contractType") or None,
                    r.get("contractTerm") or None,
                    _clean_amount(r.get("preDeposit")),
                    _clean_amount(r.get("preMonthlyRent")),
                    r.get("useRRRight") or None,
                    r.get("aptSeq") or None,
                    _to_int(r.get("buildYear")),
                    key.legacy_apt_seq,
                    key.apt_seq_method,
                )
            )

        if new_rows:
            cnt = execute_values_chunked(
                conn,
                "INSERT INTO rent_history (apt_seq, sgg_cd, apt_nm, deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day,"
                " umd_nm, jibun, road_nm, road_nm_bonbun, road_nm_bubun, contract_type, contract_term, pre_deposit, pre_monthly_rent, use_rr_right, api_apt_seq,"
                " build_year, legacy_apt_seq, apt_seq_method) VALUES %s"
                " ON CONFLICT (sgg_cd, apt_nm, exclu_use_ar, floor, deal_year, deal_month, deal_day, deposit) DO NOTHING",
                new_rows,
            )
            total_inserted += cnt
            logger.info(
                f"  전월세 신규 {cnt:,}건 적재 (후보 {len(new_rows):,}건 중 중복 {len(new_rows) - cnt:,}건,"
                f" 기존 키 {len(existing_keys):,}건)"
            )
        else:
            logger.info("  전월세 신규 건 없음")

    return total_inserted
