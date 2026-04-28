"""Tool functions for the chatbot — query PostgreSQL and return structured results."""

import json

from database import DictConnection
from services.scoring import (
    get_nudge_weights,
    get_region_profile,
    facility_score,
    calculate_nudge_score,
    calculate_multi_nudge_score,
)
from services.llm.base import Tool


def _get_conn():
    return DictConnection()


def _drop_empty(d: dict) -> dict:
    """None / 빈 컨테이너 필드를 제거한 얕은 복사본.

    agent 응답 깔끔하게 + 토큰 절약 목적. 값이 0, False, "0" 은 보존 (의미 있는 값).
    하위(중첩) dict·list 는 구조 유지; 상위 레벨의 "비어있음" 만 처리.
    """
    return {k: v for k, v in d.items() if v is not None and v != {} and v != []}


# ---------------------------------------------------------------------------
# Tool definitions (for LLM function calling)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="search_apartments",
        description="라이프 점수 기반 아파트 추천 검색. 키워드(지역명/단지명)와 라이프 항목을 조합하여 최적의 아파트를 점수순으로 반환합니다. 사용 가능한 항목: cost(가성비), pet(반려동물), commute(출퇴근), newlywed(신혼부부), education(교육), senior(시니어), investment(투자), nature(자연친화), safety(안전)",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "검색 키워드 (지역명, 동이름, 구이름 등). 예: '자양동', '강남구', '마포'",
                },
                "nudges": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "적용할 라이프 항목 ID 목록. 예: ['commute', 'cost']",
                },
                "top_n": {
                    "type": "integer",
                    "description": "반환할 최대 아파트 수 (기본 10)",
                    "default": 10,
                },
                "min_area": {
                    "type": "number",
                    "description": "최소 면적 (㎡). 예: 60",
                },
                "max_area": {
                    "type": "number",
                    "description": "최대 면적 (㎡). 예: 85",
                },
                "min_price": {
                    "type": "integer",
                    "description": "최소 매매가 (만원). 예: 50000 (5억)",
                },
                "max_price": {
                    "type": "integer",
                    "description": "최대 매매가 (만원). 예: 100000 (10억)",
                },
                "min_floor": {
                    "type": "integer",
                    "description": "최소 최고층수. 예: 15",
                },
                "built_after": {
                    "type": "integer",
                    "description": "준공연도 이후. 예: 2015",
                },
            },
            "required": ["keyword"],
        },
    ),
    Tool(
        name="get_apartment_detail",
        description="특정 아파트의 상세 정보를 조회합니다. 아파트 이름 또는 PNU 코드로 검색합니다. 기본정보, 라이프 점수, 시설 요약, 학군 정보를 포함합니다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "아파트 이름 또는 PNU 코드. 예: '래미안', '1168010100100010000'",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="compare_apartments",
        description="2~5개 아파트를 비교합니다. 각 아파트의 라이프 점수, 시설 접근성 등을 나란히 비교합니다.",
        parameters={
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "비교할 아파트 이름 또는 PNU 목록 (2~5개)",
                    "minItems": 2,
                    "maxItems": 5,
                },
            },
            "required": ["queries"],
        },
    ),
    Tool(
        name="get_market_trend",
        description="특정 지역의 부동산 시장 동향(거래량, 평균가격 추이)을 조회합니다.",
        parameters={
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "지역명 또는 시군구코드. 예: '광진구', '11215'",
                },
                "period": {
                    "type": "string",
                    "description": "조회 기간. 예: '1y'(1년), '3y'(3년), '5y'(5년)",
                    "default": "1y",
                },
            },
            "required": ["region"],
        },
    ),
    Tool(
        name="get_school_info",
        description="아파트의 학군 정보(배정 초등학교, 중학교 학군, 고등학교 학군)를 조회합니다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "아파트 이름 또는 PNU 코드",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_knowledge",
        description="부동산 관련 지식 검색 (RAG). 부동산 용어, 정책, 세금 등에 대한 질문에 답변합니다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 질문 또는 키워드",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_commute",
        description=(
            "아파트에서 목적지까지 대중교통 출퇴근 시간을 조회합니다. "
            "ODSay API를 사용하여 지하철/버스 경로, 소요시간, 환승횟수, 요금을 반환합니다. "
            "선행 조건: `pnu`는 `get_apartment_detail` 결과의 `basic.pnu`에서 가져옵니다. "
            "사용자가 아파트 이름만 제공한 경우 이 도구를 호출하기 전에 먼저 `get_apartment_detail`을 호출해 PNU를 얻으세요."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pnu": {
                    "type": "string",
                    "description": "출발 아파트의 PNU 코드",
                },
                "destination": {
                    "type": "string",
                    "description": "목적지 장소명 또는 주소. 예: '강남역', '여의도 IFC', '서울시청'",
                },
            },
            "required": ["pnu", "destination"],
        },
    ),
    Tool(
        name="get_dashboard_info",
        description="수도권/전국 아파트 거래 동향 조회. 월별 거래량, ㎡당 중위 매매가/전세가, 전월 대비 변동률, 시군구별 랭킹 등 시장 현황을 분석합니다. 특정 지역을 지정하면 해당 지역의 동향을 반환합니다.",
        parameters={
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "지역명 (예: '강남구', '해운대구', '수원'). 비어있으면 전국",
                    "default": "",
                },
                "months": {
                    "type": "integer",
                    "description": "추이 조회 개월 수 (기본 6)",
                    "default": 6,
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_similar_apartments",
        description=(
            "선택한 아파트와 유사한 아파트를 추천합니다. "
            "4가지 모드: location(입지 유사), price(가격대 유사), "
            "lifestyle(선호 인프라 랭킹), combined(종합 유사). "
            "사용자 의도에 맞는 mode를 선택하세요. "
            "lifestyle은 유사도가 아닌 선호도 랭킹입니다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "아파트명 또는 PNU 코드",
                },
                "mode": {
                    "type": "string",
                    "description": "추천 모드: location(입지), price(가격대), lifestyle(선호도), combined(종합)",
                    "enum": ["location", "price", "lifestyle", "combined"],
                    "default": "combined",
                },
                "top_n": {
                    "type": "integer",
                    "description": "추천할 아파트 수 (기본 5)",
                    "default": 5,
                },
                "nudge_weights": {
                    "type": "object",
                    "description": "lifestyle 모드 전용. 카테고리별 가중치 (예: {\"교통\": 0.9, \"교육\": 0.7})",
                },
                "exclude_same_area": {
                    "type": "boolean",
                    "description": "같은 시군구 제외 여부 (기본 false)",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool executor functions
# ---------------------------------------------------------------------------

def _infer_nudges_from_keyword(keyword: str) -> list[str]:
    """Infer nudges from natural language keywords."""
    from common_codes import get_codes
    rows = get_codes("nudge_keyword")
    inferred = []
    for r in rows:
        keywords = r["name"].split(",")
        if any(kw.strip() in keyword for kw in keywords):
            inferred.append(r["code"])
    return inferred


async def search_apartments(
    keyword: str,
    nudges: list[str] | None = None,
    top_n: int = 10,
    min_area: float | None = None,
    max_area: float | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_floor: int | None = None,
    built_after: int | None = None,
) -> str:
    """Search apartments with nudge scoring and filters."""
    from services.search_engine import search as search_apts

    conn = _get_conn()
    try:
        # If no nudges provided, try to infer from keyword
        if not nudges:
            nudges = _infer_nudges_from_keyword(keyword)
        if not nudges:
            nudges = ["commute"]  # default

        # 검색 엔진으로 아파트 조회 (지역/단지명 자동 분류)
        search_result = search_apts(conn, keyword)
        raw_results = search_result["results"]
        region_candidates = search_result.get("region_candidates")

        # 다중 지역 후보가 있으면 사용자에게 선택 요청
        if region_candidates:
            # 각 후보에 재검색 keyword 추가 (LLM이 바로 사용 가능)
            for c in region_candidates:
                parts = c["label"].split()
                # "경기도 용인시기흥구 중동" → "용인 중동"
                if len(parts) >= 3:
                    c["search_keyword"] = f"{parts[-2]} {parts[-1]}"
                elif len(parts) == 2:
                    c["search_keyword"] = f"{parts[0]} {parts[1]}"
                else:
                    c["search_keyword"] = c["label"]
            candidate_list = [f"{c['label']} ({c['count']}건)" for c in region_candidates]
            return json.dumps({
                "results": [],
                "region_candidates": region_candidates,
                "message": f"'{keyword}'은(는) 여러 지역에 있습니다: {', '.join(candidate_list)}. 사용자에게 어느 지역인지 확인 후, 해당 후보의 search_keyword로 재검색하세요.",
            }, ensure_ascii=False)

        # region_empty 제외, 좌표 있는 것만
        apartments = [r for r in raw_results if r.get("lat") and r.get("match_type") != "region_empty"]

        # 필터 적용 (면적/가격/층수/준공년도)
        if any(v is not None for v in [min_area, max_area, min_price, max_price, min_floor, built_after]):
            pnu_list = [a["pnu"] for a in apartments]
            if pnu_list:
                ph = ",".join(["%s"] * len(pnu_list))
                filter_rows = conn.execute(f"""
                    SELECT a.pnu, ai.min_area, ai.max_area, ai.avg_area,
                           ps.price_per_m2, a.max_floor, a.use_apr_day
                    FROM apartments a
                    LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
                    LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu
                    WHERE a.pnu IN ({ph})
                """, pnu_list).fetchall()
                filter_map = {r["pnu"]: r for r in filter_rows}

                filtered = []
                for apt in apartments:
                    f = filter_map.get(apt["pnu"])
                    if not f:
                        continue
                    if min_area is not None and (f.get("max_area") or 0) < min_area:
                        continue
                    if max_area is not None and (f.get("min_area") or 999) > max_area:
                        continue
                    if min_price is not None:
                        est = (f.get("price_per_m2") or 0) * (f.get("avg_area") or 60) / 10000
                        if est < min_price:
                            continue
                    if max_price is not None:
                        est = (f.get("price_per_m2") or 0) * (f.get("avg_area") or 60) / 10000
                        if est > max_price:
                            continue
                    if min_floor is not None and (f.get("max_floor") or 0) < min_floor:
                        continue
                    if built_after is not None:
                        try:
                            yr = int(str(f.get("use_apr_day", ""))[:4])
                            if yr < built_after:
                                continue
                        except (ValueError, TypeError):
                            continue
                    filtered.append(apt)
                apartments = filtered

        if not apartments:
            return json.dumps(
                {"results": [], "message": f"'{keyword}'에 해당하는 아파트를 찾을 수 없습니다."},
                ensure_ascii=False,
            )

        pnu_list = [a["pnu"] for a in apartments]
        apt_map = {a["pnu"]: a for a in apartments}

        # Collect relevant subtypes
        all_subtypes = set()
        for nid in nudges:
            all_subtypes.update(get_nudge_weights().get(nid, {}).keys())

        # Load facility summaries
        chunk_size = 500
        summary_rows = []
        for i in range(0, len(pnu_list), chunk_size):
            chunk = pnu_list[i : i + chunk_size]
            ph_pnu = ",".join("%s" for _ in chunk)
            ph_sub = ",".join("%s" for _ in all_subtypes)
            if all_subtypes:
                rows = conn.execute(
                    f"SELECT pnu, facility_subtype, nearest_distance_m, count_1km "
                    f"FROM apt_facility_summary "
                    f"WHERE pnu IN ({ph_pnu}) AND facility_subtype IN ({ph_sub})",
                    chunk + list(all_subtypes),
                ).fetchall()
                summary_rows.extend(rows)

        # Build facility scores (프로필별 파라미터 적용)
        pnu_profiles = {
            pnu: get_region_profile(apt_map[pnu].get("sigungu_code"))
            for pnu in pnu_list
        }
        apt_facility_scores: dict[str, dict[str, float]] = {}
        for row in summary_rows:
            pnu = row["pnu"]
            if pnu not in apt_facility_scores:
                apt_facility_scores[pnu] = {}
            apt_facility_scores[pnu][row["facility_subtype"]] = facility_score(
                row["nearest_distance_m"],
                row["count_1km"],
                row["facility_subtype"],
                profile=pnu_profiles.get(pnu, "metro"),
            )

        # Load price scores if needed
        price_nudges = {"cost", "investment"}
        if price_nudges & set(nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join("%s" for _ in chunk)
                try:
                    rows = conn.execute(
                        f"SELECT pnu, price_score, jeonse_ratio FROM apt_price_score WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        pnu = row["pnu"]
                        if pnu not in apt_facility_scores:
                            apt_facility_scores[pnu] = {}
                        apt_facility_scores[pnu]["score_price"] = row["price_score"] or 50.0
                        apt_facility_scores[pnu]["score_jeonse"] = row["jeonse_ratio"] or 50.0
                except Exception:
                    pass

        # Load safety scores if needed
        safety_nudges = {"cost", "newlywed", "senior"}
        if safety_nudges & set(nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join("%s" for _ in chunk)
                try:
                    rows = conn.execute(
                        f"SELECT pnu, safety_score FROM apt_safety_score WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        pnu = row["pnu"]
                        if pnu not in apt_facility_scores:
                            apt_facility_scores[pnu] = {}
                        apt_facility_scores[pnu]["score_safety"] = row["safety_score"] or 50.0
                except Exception:
                    pass

        # Calculate scores
        results = []
        for pnu in pnu_list:
            fscores = apt_facility_scores.get(pnu, {})
            breakdown = {}
            for nid in nudges:
                breakdown[nid] = calculate_nudge_score(fscores, nid)
            score = calculate_multi_nudge_score(fscores, nudges)

            apt = apt_map[pnu]
            results.append(
                {
                    "pnu": pnu,
                    "bld_nm": apt["bld_nm"],
                    "lat": apt["lat"],
                    "lng": apt["lng"],
                    "address": apt["new_plat_plc"],
                    "total_hhld_cnt": apt["total_hhld_cnt"],
                    "score": score,
                    "score_breakdown": breakdown,
                }
            )

        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:top_n]

        return json.dumps(
            {
                "results": results,
                "nudges_applied": nudges,
                "total_found": len(pnu_list),
                "returned": len(results),
            },
            ensure_ascii=False,
        )
    finally:
        conn.close()


async def get_apartment_detail(query: str) -> str:
    """Get detailed information for an apartment by name or PNU."""
    conn = _get_conn()
    try:
        # Try PNU first
        apt = conn.execute("SELECT * FROM apartments WHERE pnu = %s", [query]).fetchone()
        if not apt:
            # Search by name (원본 + 공백/특수문자 제거 + 접미사 제거 3가지로 매칭)
            import re as _re2
            from services.search_engine import normalize_apt_name
            norm_q = _re2.sub(r'[\s()\-·]', '', query)
            norm_stripped = normalize_apt_name(query)
            rows = conn.execute(
                "SELECT * FROM apartments WHERE pnu NOT LIKE 'TRADE_%%' "
                "AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s OR bld_nm_norm LIKE %s OR display_name LIKE %s) LIMIT 5",
                [f"%{query}%", f"%{norm_q}%", f"%{norm_stripped}%", f"%{query}%"],
            ).fetchall()
            if not rows:
                return json.dumps(
                    {"error": f"'{query}'에 해당하는 아파트를 찾을 수 없습니다."},
                    ensure_ascii=False,
                )
            apt = rows[0]

        pnu = apt["pnu"]

        # Facility summary
        summary_rows = conn.execute(
            "SELECT facility_subtype, nearest_distance_m, count_1km, count_3km "
            "FROM apt_facility_summary WHERE pnu = %s",
            [pnu],
        ).fetchall()

        facility_summary = {
            row["facility_subtype"]: {
                "nearest_m": round(row["nearest_distance_m"]) if row["nearest_distance_m"] is not None else None,
                "count_1km": row["count_1km"],
            }
            for row in summary_rows
        }

        detail_profile = get_region_profile(apt.get("sigungu_code"))
        facility_scores = {
            row["facility_subtype"]: facility_score(
                row["nearest_distance_m"],
                row["count_1km"],
                row["facility_subtype"],
                profile=detail_profile,
            )
            for row in summary_rows
        }

        # Price score
        price_row = conn.execute(
            "SELECT price_score, jeonse_ratio, price_per_m2 FROM apt_price_score WHERE pnu = %s",
            [pnu],
        ).fetchone()
        if price_row:
            facility_scores["score_price"] = price_row["price_score"] or 50.0
            facility_scores["score_jeonse"] = price_row["jeonse_ratio"] or 50.0

        # Safety score
        try:
            safety_row = conn.execute(
                "SELECT safety_score FROM apt_safety_score WHERE pnu = %s", [pnu]
            ).fetchone()
            if safety_row:
                facility_scores["score_safety"] = safety_row["safety_score"] or 50.0
        except Exception:
            safety_row = None

        # Nudge scores
        scores = {
            nid: calculate_nudge_score(facility_scores, nid) for nid in get_nudge_weights()
        }

        # School zone
        school = conn.execute(
            "SELECT * FROM school_zones WHERE pnu = %s", [pnu]
        ).fetchone()

        # Recent trades
        mapping = conn.execute(
            "SELECT apt_seq FROM trade_apt_mapping WHERE pnu = %s", [pnu]
        ).fetchall()
        recent_trades = []
        if mapping:
            seqs = [m["apt_seq"] for m in mapping]
            ph = ",".join("%s" for _ in seqs)
            recent_trades = conn.execute(
                f"SELECT deal_amount, exclu_use_ar, floor, deal_year, deal_month "
                f"FROM trade_history WHERE apt_seq IN ({ph}) "
                f"ORDER BY deal_year DESC, deal_month DESC LIMIT 5",
                seqs,
            ).fetchall()

        # 주소 보완: new_plat_plc가 없으면 sigungu_code로 지역명 생성
        address = apt["new_plat_plc"] or apt.get("plat_plc")
        if not address and apt.get("sigungu_code"):
            sgg = apt["sigungu_code"]
            from common_codes import get_code_map_with_extra
            sgg_codes = get_code_map_with_extra("sigungu")
            name_extra = sgg_codes.get(sgg[:5])
            address = f"{name_extra[1]} {name_extra[0]}" if name_extra else f"시군구코드 {sgg}"

        # LLM/agent 에게 전달하는 응답은 None/빈 값 필드를 제거해 가독성·토큰 효율 확보.
        # 데이터가 없는 필드 자체를 숨김으로써, 모델이 "없는 정보"를 "있다고 환각"하는 위험도 줄인다.
        basic = _drop_empty({
            "pnu": apt["pnu"],
            "name": apt.get("display_name") or apt["bld_nm"],
            "address": address,
            "total_households": apt["total_hhld_cnt"],
            "dong_count": apt["dong_count"],
            "max_floor": apt["max_floor"],
            "built_date": apt.get("use_apr_day"),
            "lat": apt["lat"],
            "lng": apt["lng"],
        })

        trades = [
            _drop_empty({
                "date": f"{t['deal_year']}.{t['deal_month']:02d}",
                "price": f"{t['deal_amount'] // 10000}억{t['deal_amount'] % 10000:,}만원" if t["deal_amount"] >= 10000 else f"{t['deal_amount']:,}만원",
                "area": f"{t['exclu_use_ar']}㎡" if t.get("exclu_use_ar") else None,
                "floor": t.get("floor"),
            })
            for t in recent_trades
        ]

        result = _drop_empty({
            "basic": basic,
            "nudge_scores": scores,
            "facility_summary": facility_summary,
            "school": school,
            "recent_trades": trades,
            "price_info": price_row,
        })

        return json.dumps(result, ensure_ascii=False)
    finally:
        conn.close()


async def compare_apartments(queries: list[str]) -> str:
    """Compare 2-5 apartments side by side."""
    results = []
    for q in queries[:5]:
        detail_json = await get_apartment_detail(q)
        detail = json.loads(detail_json)
        if "error" not in detail:
            results.append(detail)

    if not results:
        return json.dumps(
            {"error": "비교할 아파트를 찾을 수 없습니다."}, ensure_ascii=False
        )

    return json.dumps(
        {"apartments": results, "count": len(results)},
        ensure_ascii=False,
    )


async def get_market_trend(region: str, period: str = "1y") -> str:
    """Get market trends for a region."""
    conn = _get_conn()
    try:
        # Map period to years
        years_map = {"1y": 1, "3y": 3, "5y": 5}
        years = years_map.get(period, 1)
        min_year = 2026 - years  # current date context is 2026

        # Find sgg_cd from region name
        sgg_cd = region
        if not region.isdigit():
            # common_code에서 시군구명→코드 매칭
            sgg_row = conn.execute(
                "SELECT code FROM common_code WHERE group_id = 'sigungu' AND (name LIKE %s OR extra || name LIKE %s) LIMIT 1",
                [f"%{region}%", f"%{region}%"],
            ).fetchone()
            if sgg_row:
                sgg_cd = sgg_row["code"]
            else:
                # 주소에서 검색 (fallback)
                apt = conn.execute(
                    "SELECT sigungu_code FROM apartments WHERE new_plat_plc LIKE %s LIMIT 1",
                    [f"%{region}%"],
                ).fetchone()
                if apt and apt["sigungu_code"]:
                    sgg_cd = apt["sigungu_code"][:5]
                else:
                    return json.dumps(
                        {"error": f"'{region}' 지역을 찾을 수 없습니다."}, ensure_ascii=False
                    )

        # Trade volume and avg price by year-month
        trade_rows = conn.execute(
            """
            SELECT deal_year, deal_month,
                   COUNT(*) as volume,
                   ROUND(AVG(deal_amount)::numeric)::float as avg_price,
                   ROUND(AVG(deal_amount::float / NULLIF(exclu_use_ar, 0))::numeric, 1)::float as avg_price_per_m2
            FROM trade_history
            WHERE sgg_cd = %s AND deal_year >= %s
            GROUP BY deal_year, deal_month
            ORDER BY deal_year, deal_month
            """,
            [sgg_cd, min_year],
        ).fetchall()

        # Rent stats
        rent_rows = conn.execute(
            """
            SELECT deal_year, deal_month,
                   COUNT(*) as volume,
                   ROUND(AVG(deposit)::numeric)::float as avg_deposit,
                   ROUND(AVG(monthly_rent)::numeric)::float as avg_monthly_rent
            FROM rent_history
            WHERE sgg_cd = %s AND deal_year >= %s
            GROUP BY deal_year, deal_month
            ORDER BY deal_year, deal_month
            """,
            [sgg_cd, min_year],
        ).fetchall()

        def _fmt(val):
            """만원 → 억/만 변환."""
            v = int(val) if val else 0
            if v >= 10000:
                eok, rest = v // 10000, v % 10000
                return f"{eok}억{rest:,}만원" if rest else f"{eok}억"
            return f"{v:,}만원"

        trade_stats = [
            {
                "month": f"{r['deal_year']}.{r['deal_month']:02d}",
                "volume": r["volume"],
                "avg_price": _fmt(r["avg_price"]),
                "avg_price_per_m2": f"{round(r['avg_price_per_m2'] or 0):,}만원/㎡",
            }
            for r in trade_rows
        ]

        rent_stats = [
            {
                "month": f"{r['deal_year']}.{r['deal_month']:02d}",
                "volume": r["volume"],
                "avg_deposit": _fmt(r["avg_deposit"]),
                "avg_monthly_rent": f"{round(r['avg_monthly_rent'] or 0):,}만원",
            }
            for r in rent_rows
        ]

        return json.dumps(
            {
                "region": region,
                "sgg_cd": sgg_cd,
                "period": period,
                "trade_trends": trade_stats,
                "rent_trends": rent_stats,
            },
            ensure_ascii=False,
        )
    finally:
        conn.close()


async def get_school_info(query: str) -> str:
    """Get school zone information for an apartment."""
    conn = _get_conn()
    try:
        # Try PNU
        school = conn.execute(
            "SELECT * FROM school_zones WHERE pnu = %s", [query]
        ).fetchone()

        if not school:
            # Find apartment by name
            import re as _re3
            norm_sq = _re3.sub(r'[\s()\-·]', '', query)
            apt = conn.execute(
                "SELECT pnu, COALESCE(display_name, bld_nm) AS bld_nm FROM apartments "
                "WHERE pnu NOT LIKE 'TRADE_%%' "
                "AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s OR display_name LIKE %s) LIMIT 5",
                [f"%{query}%", f"%{norm_sq}%", f"%{query}%"],
            ).fetchall()
            if not apt:
                return json.dumps(
                    {"error": f"'{query}'에 해당하는 아파트를 찾을 수 없습니다."},
                    ensure_ascii=False,
                )

            results = []
            for a in apt:
                s = conn.execute(
                    "SELECT * FROM school_zones WHERE pnu = %s", [a["pnu"]]
                ).fetchone()
                if s:
                    s["bld_nm"] = a["bld_nm"]
                    results.append(s)

            if not results:
                return json.dumps(
                    {"error": f"'{query}' 아파트의 학군 정보가 없습니다."},
                    ensure_ascii=False,
                )
            return json.dumps({"schools": results}, ensure_ascii=False)

        return json.dumps({"school": school}, ensure_ascii=False)
    finally:
        conn.close()


async def search_knowledge(query: str) -> str:
    """RAG 검색 — ChromaDB에서 관련 문서를 검색합니다."""
    from services.rag import search_knowledge_rag

    try:
        result = await search_knowledge_rag(query)
        # If we got passages, return formatted answer with sources
        if result.get("passages"):
            return json.dumps(
                {
                    "answer": result["answer"],
                    "sources": result.get("sources", []),
                },
                ensure_ascii=False,
            )
        else:
            return json.dumps(
                {
                    "message": result.get(
                        "message",
                        "관련 문서를 찾을 수 없습니다. 현재는 내장된 부동산 데이터를 기반으로 답변드리겠습니다.",
                    ),
                    "query": query,
                },
                ensure_ascii=False,
            )
    except Exception as e:
        return json.dumps(
            {
                "message": f"지식 검색 중 오류가 발생했습니다: {str(e)}. 내장된 부동산 데이터를 기반으로 답변드리겠습니다.",
                "query": query,
            },
            ensure_ascii=False,
        )


async def search_commute(pnu: str, destination: str) -> str:
    """ODSay API로 아파트→목적지 대중교통 출퇴근 시간 조회."""
    import os
    import requests as req

    ODSAY_API_KEY = os.getenv("ODSAY_API_KEY", "")
    KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")

    # 1. 아파트 좌표
    conn = _get_conn()
    try:
        apt = conn.execute(
            "SELECT COALESCE(display_name, bld_nm) AS bld_nm, lat, lng FROM apartments WHERE pnu = %s",
            [pnu],
        ).fetchone()
    finally:
        conn.close()

    if not apt or not apt["lat"]:
        return json.dumps({"error": f"PNU '{pnu}' 아파트를 찾을 수 없거나 좌표가 없습니다."}, ensure_ascii=False)

    # 2. 목적지 좌표 (Kakao 키워드 검색)
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    dest_lat, dest_lng, dest_addr = None, None, destination
    for search_url in [
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        "https://dapi.kakao.com/v2/local/search/address.json",
    ]:
        try:
            resp = req.get(search_url, headers=headers, params={"query": destination, "size": 1}, timeout=5)
            docs = resp.json().get("documents", [])
            if docs:
                dest_lat = float(docs[0]["y"])
                dest_lng = float(docs[0]["x"])
                dest_addr = docs[0].get("address_name", docs[0].get("road_address_name", destination))
                break
        except Exception:
            continue

    if not dest_lat:
        return json.dumps({"error": f"'{destination}' 위치를 찾을 수 없습니다."}, ensure_ascii=False)

    # 3. ODSay 경로 검색
    odsay_url = f"https://api.odsay.com/v1/api/searchPubTransPathT?SX={apt['lng']}&SY={apt['lat']}&EX={dest_lng}&EY={dest_lat}&apiKey={ODSAY_API_KEY}"
    try:
        resp = req.get(odsay_url, timeout=15)
        data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"ODSay API 호출 실패: {e}"}, ensure_ascii=False)

    if "error" in data:
        return json.dumps({"error": "대중교통 경로를 찾을 수 없습니다."}, ensure_ascii=False)

    paths = data.get("result", {}).get("path", [])
    if not paths:
        return json.dumps({"error": "검색된 경로가 없습니다."}, ensure_ascii=False)

    from common_codes import get_code_map
    type_labels = {int(k): v for k, v in get_code_map("path_type").items()}
    routes = []
    for path in paths[:5]:
        info = path.get("info", {})
        # 경로 요약
        sub_paths = path.get("subPath", [])
        summary_parts = []
        for sp in sub_paths:
            tt = sp.get("trafficType")
            if tt == 1:
                lane = sp.get("lane", [{}])
                summary_parts.append(lane[0].get("name", "") if lane else "")
            elif tt == 2:
                lane = sp.get("lane", [{}])
                summary_parts.append(f"버스 {lane[0].get('busNo', '')}" if lane else "버스")

        routes.append({
            "type": type_labels.get(path.get("pathType", 0), "기타"),
            "total_time": info.get("totalTime", 0),
            "transit_count": info.get("busTransitCount", 0) + info.get("subwayTransitCount", 0),
            "walk_time": info.get("totalWalk", 0),
            "payment": info.get("payment", 0),
            "summary": " → ".join(p for p in summary_parts if p),
        })

    return json.dumps({
        "apartment": apt["bld_nm"],
        "destination": destination,
        "destination_address": dest_addr,
        "routes": routes,
    }, ensure_ascii=False)


async def get_dashboard_info(region: str = "", months: int = 6) -> str:
    """거래 동향 대시보드 정보 조회."""
    conn = _get_conn()
    from datetime import datetime

    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1

    # 지역 코드 매핑
    sgg_cd = ""
    sgg_name = "전국"
    if region.strip():
        from common_codes import get_codes
        codes = get_codes("sigungu")
        for c in codes:
            if region.strip() in c["name"] or region.strip() in (c["extra"] or ""):
                sgg_cd = c["code"]
                sgg_name = f"{c['name']}({c['extra']})" if c["extra"] and c["extra"] != c["name"] else c["name"]
                break

    sgg_filter = ""
    sgg_params: list = []
    if sgg_cd:
        sgg_filter = "AND sgg_cd = %s"
        sgg_params = [sgg_cd]

    # 이번 달 요약
    trade_cur = conn.execute(
        f"SELECT COUNT(*) as vol, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount / NULLIF(exclu_use_ar, 0)), 0) as med "
        f"FROM trade_history WHERE deal_year = %s AND deal_month = %s AND exclu_use_ar > 0 {sgg_filter}",
        [cur_year, cur_month] + sgg_params
    ).fetchone()

    trade_prev = conn.execute(
        f"SELECT COUNT(*) as vol, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount / NULLIF(exclu_use_ar, 0)), 0) as med "
        f"FROM trade_history WHERE deal_year = %s AND deal_month = %s AND exclu_use_ar > 0 {sgg_filter}",
        [prev_year, prev_month] + sgg_params
    ).fetchone()

    rent_cur = conn.execute(
        f"SELECT COUNT(*) as vol, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit / NULLIF(exclu_use_ar, 0)), 0) as med "
        f"FROM rent_history WHERE deal_year = %s AND deal_month = %s AND exclu_use_ar > 0 {sgg_filter}",
        [cur_year, cur_month] + sgg_params
    ).fetchone()

    # 월별 추이
    start_ym = (cur_year - 1) * 100 + cur_month if months > 12 else cur_year * 100 + max(1, cur_month - months)
    trend_params = [start_ym] + sgg_params
    trend = conn.execute(f"""
        SELECT deal_year, deal_month, COUNT(*) as vol,
               COALESCE(AVG(deal_amount), 0) as avg_price
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
        ORDER BY deal_year, deal_month
    """, trend_params).fetchall()

    conn.close()

    # 변동률
    cur_med = float(trade_cur["med"])
    prev_med = float(trade_prev["med"])
    change_pct = round((cur_med - prev_med) / prev_med * 100, 1) if prev_med > 0 else 0

    trend_text = ", ".join(
        f"{r['deal_year']}.{r['deal_month']:02d}: {r['vol']}건(평균 {round(float(r['avg_price'])):,}만원)"
        for r in trend[-6:]
    )

    return json.dumps({
        "region": sgg_name,
        "current_month": f"{cur_year}년 {cur_month}월",
        "trade_summary": {
            "volume": trade_cur["vol"],
            "median_price_m2": f"{round(cur_med):,}만/㎡ (평당 {round(cur_med * 3.3):,}만)",
            "prev_median_price_m2": f"{round(prev_med):,}만/㎡",
            "change_pct": f"{'+' if change_pct > 0 else ''}{change_pct}%",
        },
        "rent_summary": {
            "volume": rent_cur["vol"],
            "median_deposit_m2": f"{round(float(rent_cur['med'])):,}만/㎡",
        },
        "monthly_trend": trend_text,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Executor mapping
# ---------------------------------------------------------------------------

async def get_similar_apartments(
    query: str, mode: str = "combined", top_n: int = 5,
    nudge_weights: dict | None = None, exclude_same_area: bool = False,
) -> str:
    """유사 아파트 추천 (4개 모드)."""
    import numpy as np
    import re as _re
    from services.similarity import (
        calc_location, calc_price, calc_lifestyle, calc_combined,
        parse_vectors,
    )

    conn = _get_conn()

    # 아파트 검색
    apt = conn.execute("SELECT pnu FROM apartments WHERE pnu = %s", [query]).fetchone()
    if not apt:
        norm = _re.sub(r'[\s()\-·]', '', query)
        rows = conn.execute(
            "SELECT pnu, COALESCE(display_name, bld_nm) AS bld_nm FROM apartments "
            "WHERE pnu NOT LIKE 'TRADE_%%' "
            "AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s OR display_name LIKE %s) LIMIT 1",
            [f"%{query}%", f"%{norm}%", f"%{query}%"]
        ).fetchall()
        if not rows:
            conn.close()
            return json.dumps({"error": f"'{query}' 아파트를 찾을 수 없습니다."}, ensure_ascii=False)
        apt = rows[0]

    pnu = apt["pnu"]

    # 대상 벡터
    target_row = conn.execute("""
        SELECT v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               COALESCE(a.display_name, a.bld_nm) AS bld_nm, a.sigungu_code
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        WHERE v.pnu = %s
    """, [pnu]).fetchone()

    if not target_row:
        conn.close()
        return json.dumps({"error": "해당 아파트의 유사도 벡터가 없습니다."}, ensure_ascii=False)

    target_vecs = parse_vectors(target_row)
    target_sgg = (target_row["sigungu_code"] or "")[:5] if exclude_same_area else ""

    # 후보 조회
    rows = conn.execute("""
        SELECT v.pnu, v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               COALESCE(a.display_name, a.bld_nm) AS bld_nm, a.sigungu_code, p.price_per_m2
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_price_score p ON v.pnu = p.pnu
        WHERE v.pnu != %s AND a.pnu NOT LIKE 'TRADE_%%'
    """, [pnu]).fetchall()
    conn.close()

    results = []
    for r in rows:
        if target_sgg and (r["sigungu_code"] or "")[:5] == target_sgg:
            continue
        c_vecs = parse_vectors(r)

        if mode == "location":
            score = calc_location(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"
        elif mode == "price":
            score = calc_price(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"
        elif mode == "lifestyle":
            nw = nudge_weights or {"생활편의": 0.5, "교통": 0.5}
            score = calc_lifestyle(c_vecs, nw)
            score_str = f"{score:.2f}점"
        else:
            score = calc_combined(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"

        results.append({
            "name": r["bld_nm"],
            "pnu": r["pnu"],
            "score": score_str,
            "price_m2": f"{round(float(r['price_per_m2'])):,}만원/m2" if r["price_per_m2"] else "가격정보 없음",
            "_sort": score,
        })

    results.sort(key=lambda x: x["_sort"], reverse=True)
    for r in results:
        del r["_sort"]

    return json.dumps({
        "target": target_row["bld_nm"],
        "mode": mode,
        "similar_apartments": results[:top_n],
    }, ensure_ascii=False)


TOOL_EXECUTORS = {
    "search_apartments": search_apartments,
    "get_apartment_detail": get_apartment_detail,
    "compare_apartments": compare_apartments,
    "get_market_trend": get_market_trend,
    "get_school_info": get_school_info,
    "search_knowledge": search_knowledge,
    "search_commute": search_commute,
    "get_dashboard_info": get_dashboard_info,
    "get_similar_apartments": get_similar_apartments,
}
