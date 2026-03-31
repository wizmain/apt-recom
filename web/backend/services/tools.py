"""Tool functions for the chatbot — query PostgreSQL and return structured results."""

import json

from database import DictConnection
from services.scoring import (
    get_nudge_weights,
    distance_to_score,
    calculate_nudge_score,
    calculate_multi_nudge_score,
)
from services.llm.base import Tool


def _get_conn():
    return DictConnection()


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
        description="아파트에서 목적지까지 대중교통 출퇴근 시간을 조회합니다. ODSay API를 사용하여 지하철/버스 경로, 소요시간, 환승횟수, 요금을 반환합니다.",
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
    conn = _get_conn()
    try:
        # If no nudges provided, try to infer from keyword
        if not nudges:
            nudges = _infer_nudges_from_keyword(keyword)
        if not nudges:
            nudges = ["commute"]  # default

        # Search apartments by keyword with filters
        import re as _re
        kw = keyword.strip()
        norm_kw = _re.sub(r'[\s()\-·]', '', kw)
        apt_sql = (
            "SELECT a.pnu, a.bld_nm, a.lat, a.lng, a.total_hhld_cnt, a.new_plat_plc "
            "FROM apartments a "
            "LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu "
            "LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu "
            "WHERE a.lat IS NOT NULL AND a.group_pnu = a.pnu AND (a.new_plat_plc LIKE %s OR a.plat_plc LIKE %s OR a.bld_nm LIKE %s OR a.bld_nm_norm LIKE %s)"
        )
        params: list = [f"%{kw}%", f"%{kw}%", f"%{kw}%", f"%{norm_kw}%"]

        if min_area is not None:
            apt_sql += " AND ai.max_area >= %s"
            params.append(min_area)
        if max_area is not None:
            apt_sql += " AND ai.min_area <= %s"
            params.append(max_area)
        if min_price is not None:
            apt_sql += " AND ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 >= %s"
            params.append(min_price)
        if max_price is not None:
            apt_sql += " AND ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 <= %s"
            params.append(max_price)
        if min_floor is not None:
            apt_sql += " AND a.max_floor >= %s"
            params.append(min_floor)
        if built_after is not None:
            apt_sql += " AND a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int >= %s"
            params.append(built_after)

        apartments = conn.execute(apt_sql, params).fetchall()

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
                    f"SELECT pnu, facility_subtype, nearest_distance_m "
                    f"FROM apt_facility_summary "
                    f"WHERE pnu IN ({ph_pnu}) AND facility_subtype IN ({ph_sub})",
                    chunk + list(all_subtypes),
                ).fetchall()
                summary_rows.extend(rows)

        # Build facility scores
        apt_facility_scores: dict[str, dict[str, float]] = {}
        for row in summary_rows:
            pnu = row["pnu"]
            if pnu not in apt_facility_scores:
                apt_facility_scores[pnu] = {}
            apt_facility_scores[pnu][row["facility_subtype"]] = distance_to_score(
                row["nearest_distance_m"], row["facility_subtype"]
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
                        apt_facility_scores[pnu]["_price"] = row["price_score"] or 50.0
                        apt_facility_scores[pnu]["_jeonse"] = row["jeonse_ratio"] or 50.0
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
                        apt_facility_scores[pnu]["_safety"] = row["safety_score"] or 50.0
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
            # Search by name (original + normalized)
            import re as _re2
            norm_q = _re2.sub(r'[\s()\-·]', '', query)
            rows = conn.execute(
                "SELECT * FROM apartments WHERE group_pnu = pnu AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s) LIMIT 5",
                [f"%{query}%", f"%{norm_q}%"],
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

        facility_scores = {
            row["facility_subtype"]: distance_to_score(
                row["nearest_distance_m"], row["facility_subtype"]
            )
            for row in summary_rows
        }

        # Price score
        price_row = conn.execute(
            "SELECT price_score, jeonse_ratio, price_per_m2 FROM apt_price_score WHERE pnu = %s",
            [pnu],
        ).fetchone()
        if price_row:
            facility_scores["_price"] = price_row["price_score"] or 50.0
            facility_scores["_jeonse"] = price_row["jeonse_ratio"] or 50.0

        # Safety score
        try:
            safety_row = conn.execute(
                "SELECT safety_score FROM apt_safety_score WHERE pnu = %s", [pnu]
            ).fetchone()
            if safety_row:
                facility_scores["_safety"] = safety_row["safety_score"] or 50.0
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

        result = {
            "basic": {
                "pnu": apt["pnu"],
                "name": apt["bld_nm"],
                "address": address,
                "total_households": apt["total_hhld_cnt"],
                "dong_count": apt["dong_count"],
                "max_floor": apt["max_floor"],
                "built_date": apt.get("use_apr_day"),
                "lat": apt["lat"],
                "lng": apt["lng"],
            },
            "nudge_scores": scores,
            "facility_summary": facility_summary,
            "school": school,
            "recent_trades": recent_trades,
            "price_info": price_row,
        }

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
            # Try to find matching apartments to get sgg_cd
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
        trade_stats = conn.execute(
            """
            SELECT deal_year, deal_month,
                   COUNT(*) as volume,
                   ROUND(AVG(deal_amount)::numeric)::float as avg_price,
                   ROUND(AVG(deal_amount::float / exclu_use_ar)::numeric, 1)::float as avg_price_per_m2
            FROM trade_history
            WHERE sgg_cd = %s AND deal_year >= %s
            GROUP BY deal_year, deal_month
            ORDER BY deal_year, deal_month
            """,
            [sgg_cd, min_year],
        ).fetchall()

        # Rent stats
        rent_stats = conn.execute(
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
                "SELECT pnu, bld_nm FROM apartments WHERE group_pnu = pnu AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s) LIMIT 5",
                [f"%{query}%", f"%{norm_sq}%"],
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
            "SELECT bld_nm, lat, lng FROM apartments WHERE pnu = %s", [pnu]
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


# ---------------------------------------------------------------------------
# Executor mapping
# ---------------------------------------------------------------------------

TOOL_EXECUTORS = {
    "search_apartments": search_apartments,
    "get_apartment_detail": get_apartment_detail,
    "compare_apartments": compare_apartments,
    "get_market_trend": get_market_trend,
    "get_school_info": get_school_info,
    "search_knowledge": search_knowledge,
    "search_commute": search_commute,
}
