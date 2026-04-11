"""아파트 검색 엔진 — 검색어를 지역/단지명으로 자동 분류하여 검색.

매칭 우선순위: 시군구 → 읍면동 → 복합(지역+단지명) → 단지명
"""

import re

APT_COLS = "pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code, new_plat_plc"
# 기본 필터: 좌표·세대수·준공일이 모두 있는 아파트만 조회
APT_BASE_FILTER = "pnu NOT LIKE 'TRADE_%%' AND lat IS NOT NULL AND total_hhld_cnt > 0 AND use_apr_day IS NOT NULL AND use_apr_day != ''"
_STRIP_SIDO = re.compile(r"(특별자치도|광역시|특별시|특별자치시)")
_STRIP_SUFFIX = re.compile(r"[시도구군읍면동 ]")


# ── 매칭 함수 ──

def match_sigungu(conn, query: str) -> tuple[list[str], str]:
    """시군구명 매칭. 반환: (코드 목록, 라벨). 미매칭 시 ([], '')."""
    pattern = f"%{query}%"
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu' "
        "AND (name LIKE %s OR extra || name LIKE %s OR extra || ' ' || name LIKE %s)",
        [pattern, pattern, pattern],
    ).fetchall()
    if rows:
        label = f"{rows[0]['extra']} {rows[0]['name']}"
        return [r["code"] for r in rows], label
    return [], ""


def match_emd(conn, query: str) -> tuple[list[str], str]:
    """읍면동명 매칭 (정확 → 접두어). 반환: (코드 목록, 라벨). 미매칭 시 ([], '')."""
    # 정확 매칭 우선
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = 'emd' AND name = %s",
        [query],
    ).fetchall()
    # 접두어 매칭 fallback (중동 → 중동1가 포함, 하중동 제외)
    if not rows:
        rows = conn.execute(
            "SELECT code, name, extra FROM common_code WHERE group_id = 'emd' AND name LIKE %s",
            [f"{query}%"],
        ).fetchall()
    if rows:
        label = f"{rows[0]['extra']} {rows[0]['name']}"
        return [r["code"] for r in rows], label
    return [], ""


def _filter_emd_by_region(emd_rows: list, head_part: str) -> list:
    """앞쪽 토큰(시도/시군구)으로 읍면동 결과를 필터."""
    head_norm = _STRIP_SUFFIX.sub("", _STRIP_SIDO.sub("", head_part))
    if not head_norm:
        return emd_rows
    return [r for r in emd_rows if head_norm in r["extra"].replace(" ", "")]


# ── 복합 검색어 분리 ──

def _split_compound(conn, tokens: list[str]) -> tuple[list[str], str, str, str | None]:
    """복합 검색어를 지역+단지명으로 분리.

    반환: (region_codes, region_type, region_label, name_keyword)
    """
    # 뒤에서부터 읍면동 매칭 (앞부분은 시도/시군구 컨텍스트)
    for split_at in range(1, len(tokens)):
        tail = " ".join(tokens[split_at:])
        codes, label = match_emd(conn, tail)
        if codes:
            head = " ".join(tokens[:split_at])
            filtered = _filter_emd_by_region(
                conn.execute(
                    "SELECT code, name, extra FROM common_code WHERE group_id = 'emd' AND code IN ({})".format(
                        ",".join(["%s"] * len(codes))),
                    codes,
                ).fetchall(),
                head,
            )
            if filtered:
                label = f"{filtered[0]['extra']} {filtered[0]['name']}"
                return [r["code"] for r in filtered], "emd", label, None

    # 앞에서부터 시군구 매칭 (나머지 = 단지명)
    for split_at in range(len(tokens), 0, -1):
        region_part = " ".join(tokens[:split_at])
        rp = f"%{region_part}%"
        rp_norm = f"%{_STRIP_SUFFIX.sub('', _STRIP_SIDO.sub('', region_part))}%"

        rows = conn.execute(
            "SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu' "
            "AND (name LIKE %s OR extra || name LIKE %s OR extra || name LIKE %s)",
            [rp, rp, rp_norm],
        ).fetchall()
        name_part = " ".join(tokens[split_at:]) or None
        max_matches = 30 if name_part else 5
        if rows and len(rows) <= max_matches:
            label = f"{rows[0]['extra']} {rows[0]['name']}"
            return [r["code"] for r in rows], "sigungu", label, name_part

    return [], "", "", None


# ── 검색어 분류 ──

def _classify(conn, query: str) -> tuple[list[str], str, str, str | None]:
    """검색어를 분석하여 (region_codes, region_type, region_label, name_keyword) 반환."""
    q = query.strip()
    tokens = q.split()

    # 1. 시군구 매칭
    codes, label = match_sigungu(conn, q)
    if codes:
        return codes, "sigungu", label, None

    # 2. 읍면동 매칭
    codes, label = match_emd(conn, q)
    if codes:
        return codes, "emd", label, None

    # 3. 복합 검색어 분리
    if len(tokens) >= 2:
        codes, rtype, label, name_kw = _split_compound(conn, tokens)
        if codes:
            return codes, rtype, label, name_kw

    # 4. 지역 매칭 없음 → 전체가 단지명
    return [], "", "", q


# ── DB 조회 함수 ──

def _fetch_region(conn, codes: list[str], region_type: str, label: str) -> list[dict]:
    """지역 코드로 아파트 조회."""
    ph = ",".join(["%s"] * len(codes))

    if region_type == "sigungu":
        rows = conn.execute(f"""
            SELECT {APT_COLS} FROM apartments
            WHERE {APT_BASE_FILTER} AND sigungu_code IN ({ph})
            LIMIT 100
        """, codes).fetchall()
        return [{**dict(r), "match_type": "region", "region_label": label} for r in rows]

    elif region_type == "emd":
        rows = conn.execute(f"""
            SELECT {APT_COLS}, bjd_code FROM apartments
            WHERE {APT_BASE_FILTER} AND bjd_code IN ({ph})
            LIMIT 100
        """, codes).fetchall()
        # 읍면동별 라벨 매핑
        emd_labels = {}
        for r in conn.execute(
            f"SELECT code, name, extra FROM common_code WHERE group_id = 'emd' AND code IN ({ph})",
            codes,
        ).fetchall():
            emd_labels[r["code"]] = f"{r['extra']} {r['name']}"
        return [{**dict(r), "match_type": "region",
                 "region_label": emd_labels.get(r.get("bjd_code", ""), label)} for r in rows]

    return []


def _fetch_region_with_name(conn, codes: list[str], region_type: str, label: str, keyword: str) -> list[dict]:
    """지역 코드 + 단지명으로 아파트 조회."""
    ph = ",".join(["%s"] * len(codes))
    norm = re.sub(r"[\s()\-·]", "", keyword)
    code_col = "sigungu_code" if region_type == "sigungu" else "bjd_code"

    rows = conn.execute(f"""
        SELECT {APT_COLS} FROM apartments
        WHERE {APT_BASE_FILTER} AND {code_col} IN ({ph})
          AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s)
        LIMIT 100
    """, [*codes, f"%{keyword}%", f"%{norm}%"]).fetchall()
    return [{**dict(r), "match_type": "name", "region_label": label} for r in rows]


def _fetch_name(conn, keyword: str) -> list[dict]:
    """단지명으로 아파트 조회."""
    norm = re.sub(r"[\s()\-·]", "", keyword)
    rows = conn.execute(f"""
        SELECT {APT_COLS} FROM apartments
        WHERE {APT_BASE_FILTER}
          AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s)
        LIMIT 100
    """, [f"%{keyword}%", f"%{norm}%"]).fetchall()
    return [{**dict(r), "match_type": "name"} for r in rows]


def _fetch_fallback(conn, query: str) -> list[dict]:
    """주소/단지명 통합 fallback 검색."""
    pattern = f"%{query}%"
    norm = re.sub(r"[\s()\-·]", "", query)
    rows = conn.execute(f"""
        SELECT {APT_COLS} FROM apartments
        WHERE {APT_BASE_FILTER}
          AND (new_plat_plc LIKE %s OR plat_plc LIKE %s OR bld_nm LIKE %s OR bld_nm_norm LIKE %s)
        LIMIT 100
    """, [pattern, pattern, pattern, f"%{norm}%"]).fetchall()
    results = []
    for r in rows:
        addr = r.get("new_plat_plc") or r.get("plat_plc") or ""
        mt = "region" if query in addr else "name"
        results.append({**dict(r), "match_type": mt})
    return results


# ── 다중 지역 후보 감지 ──

def _detect_candidates(results: list[dict]) -> list[dict]:
    """region 결과가 2개 이상 시군구에 분산되면 후보 목록 반환."""
    region_items = [r for r in results if r.get("match_type") == "region"]
    if not region_items:
        return []

    from collections import Counter
    sgg_counts: Counter[str] = Counter()
    sgg_labels: dict[str, str] = {}
    for r in region_items:
        sgg = (r.get("sigungu_code") or "")[:5]
        if sgg:
            sgg_counts[sgg] += 1
            if sgg not in sgg_labels:
                sgg_labels[sgg] = r.get("region_label", "")

    if len(sgg_counts) < 2:
        return []

    return [
        {"sigungu_code": sgg, "label": sgg_labels.get(sgg, sgg), "count": cnt}
        for sgg, cnt in sgg_counts.most_common()
    ]


# ── 메인 검색 ──

def search(conn, query: str) -> dict:
    """아파트 검색 메인. 반환: {"results": [...], "region_candidates": [...]}"""
    codes, rtype, label, name_kw = _classify(conn, query)

    results: list[dict] = []
    region_pnus: set[str] = set()

    # 지역+단지명 동시 존재 → SQL에서 함께 필터
    if codes and name_kw:
        results = _fetch_region_with_name(conn, codes, rtype, label, name_kw)
    elif codes:
        results = _fetch_region(conn, codes, rtype, label)
    elif name_kw:
        results = _fetch_name(conn, name_kw)

    # fallback (지역도 단지명도 매칭 안 된 경우)
    if not results and not name_kw:
        results = _fetch_fallback(conn, query)

    # 지역 매칭됐지만 아파트 0건 → 힌트 반환
    if not results and label:
        results = [{"match_type": "region_empty", "region_label": label,
                    "pnu": None, "bld_nm": None, "lat": None, "lng": None,
                    "total_hhld_cnt": None, "sigungu_code": None, "new_plat_plc": None}]

    # 다중 지역 후보 감지
    candidates = _detect_candidates(results)

    out: dict = {"results": results[:100]}
    if candidates:
        out["region_candidates"] = candidates
    return out
