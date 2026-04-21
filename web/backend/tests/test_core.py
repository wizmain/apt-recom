"""아파트 추천 서비스 핵심 기능 통합 테스트.

실행: .venv/bin/python web/backend/tests/test_core.py
"""

import sys
import os
import json
import asyncio
from pathlib import Path

# 프로젝트 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

passed = 0
failed = 0
errors = []


def test(name):
    """테스트 데코레이터."""
    def decorator(func):
        def wrapper():
            global passed, failed
            try:
                func()
                passed += 1
                print(f"  ✅ {name}")
            except AssertionError as e:
                failed += 1
                errors.append(f"{name}: {e}")
                print(f"  ❌ {name}: {e}")
            except Exception as e:
                failed += 1
                errors.append(f"{name}: {type(e).__name__}: {e}")
                print(f"  ❌ {name}: {type(e).__name__}: {e}")
        wrapper._test_name = name
        return wrapper
    return decorator


# ============================================================
# 1. 필터링 테스트 — 필터 조건이 정확히 적용되는지
# ============================================================

@test("필터: 준공연도 2011년 이후 → 1984년 아파트 제외")
def test_filter_built_after():
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute("""
        SELECT a.pnu, a.bld_nm, a.use_apr_day
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu
        WHERE (a.bld_nm LIKE %s) AND a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int >= %s
    """, ['%우성아파트상가%', 2011]).fetchall()
    conn.close()
    for r in rows:
        year = int(r['use_apr_day'][:4])
        assert year >= 2011, f"{r['bld_nm']} 준공 {year}년이 필터를 통과함"


@test("필터: 면적 60~85㎡ → 해당 면적 아파트만 반환")
def test_filter_area():
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute("""
        SELECT a.pnu, a.bld_nm, ai.min_area, ai.max_area
        FROM apartments a
        JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE ai.max_area >= %s AND ai.min_area <= %s
        LIMIT 10
    """, [60, 85]).fetchall()
    conn.close()
    assert len(rows) > 0, "60~85㎡ 아파트가 없음"
    for r in rows:
        assert r['max_area'] >= 60, f"{r['bld_nm']} max_area={r['max_area']} < 60"
        assert r['min_area'] <= 85, f"{r['bld_nm']} min_area={r['min_area']} > 85"


@test("필터: 최고층 15 이상")
def test_filter_floor():
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute(
        "SELECT bld_nm, max_floor FROM apartments WHERE max_floor >= %s AND bld_nm LIKE %s LIMIT 5",
        [15, '%대치%']
    ).fetchall()
    conn.close()
    assert len(rows) > 0, "15층 이상 대치 아파트가 없음"
    for r in rows:
        assert r['max_floor'] >= 15, f"{r['bld_nm']} {r['max_floor']}층 < 15"


# ============================================================
# 2. 넛지 스코어링 + 필터 통합 테스트
# ============================================================

@test("넛지+필터: 대치 반려동물 + 2011이후 → 1984년 아파트 미포함")
def test_nudge_with_filter():
    import requests
    resp = requests.post("http://localhost:8000/api/nudge/score", json={
        "nudges": ["pet"],
        "top_n": 20,
        "keyword": "대치",
        "built_after": 2011,
    }, timeout=10)
    assert resp.status_code == 200, f"API 에러: {resp.status_code}"
    data = resp.json()
    for apt in data:
        assert "우성아파트상가" not in apt["bld_nm"], \
            f"우성아파트상가(1984)가 2011이후 필터에서 반환됨: {apt['bld_nm']}"


@test("넛지+필터: 면적 60~85 + 15층이상 → 조건 미달 아파트 미포함")
def test_nudge_area_floor_filter():
    import requests
    resp = requests.post("http://localhost:8000/api/nudge/score", json={
        "nudges": ["commute"],
        "top_n": 50,
        "keyword": "강남",
        "min_area": 60,
        "max_area": 85,
        "min_floor": 15,
    }, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0, "결과가 없음"
    # 반환된 아파트가 실제로 조건을 만족하는지 DB에서 확인
    from database import DictConnection
    conn = DictConnection()
    for apt in data[:5]:
        ai = conn.execute("SELECT min_area, max_area FROM apt_area_info WHERE pnu = %s", [apt['pnu']]).fetchone()
        if ai:
            assert ai['max_area'] >= 60, f"{apt['bld_nm']} max_area={ai['max_area']} < 60"
        a = conn.execute("SELECT max_floor FROM apartments WHERE pnu = %s", [apt['pnu']]).fetchone()
        if a and a['max_floor']:
            assert a['max_floor'] >= 15, f"{apt['bld_nm']} {a['max_floor']}층 < 15"
    conn.close()


# ============================================================
# 3. 검색 정규화 테스트
# ============================================================

@test("검색: 래미안대치팰리스 (붙여쓰기) 검색 성공")
def test_search_normalized():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments/search",
                       params={"q": "래미안대치팰리스"}, timeout=10)
    assert resp.status_code == 200
    # 응답 포맷: {"results": [...], "region_candidates"?: [...]}
    results = resp.json()["results"]
    assert len(results) >= 1, "래미안대치팰리스 검색 결과 없음"
    names = [a["bld_nm"] for a in results]
    assert any("래미안" in n and "대치" in n for n in names), f"래미안 대치 팰리스 미포함: {names}"


@test("검색: 래미안 대치 팰리스 (띄어쓰기) 검색 성공")
def test_search_with_spaces():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments/search",
                       params={"q": "래미안 대치 팰리스"}, timeout=10)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 1, "래미안 대치 팰리스 검색 결과 없음"


@test("검색: 자양동 키워드 검색 → 복수 결과")
def test_search_region():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments/search",
                       params={"q": "자양동"}, timeout=10)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) >= 10, f"자양동 검색 결과 {len(results)}건 (10건 이상 예상)"


# ============================================================
# 4. 챗봇 Tool 테스트
# ============================================================

@test("챗봇: get_apartment_detail 정규화 검색")
def test_tool_detail_normalized():
    from services.tools import get_apartment_detail
    result = asyncio.run(get_apartment_detail("래미안대치팰리스"))
    data = json.loads(result)
    assert "error" not in data, f"에러: {data.get('error')}"
    assert "래미안" in data["basic"]["name"], f"이름 불일치: {data['basic']['name']}"


@test("챗봇: search_apartments 필터 적용")
def test_tool_search_with_filter():
    from services.tools import search_apartments
    result = asyncio.run(search_apartments(
        keyword="대치", nudges=["pet"], top_n=20,
        built_after=2011,
    ))
    data = json.loads(result)
    results = data.get("results", [])
    for r in results:
        assert "우성아파트상가" not in r["bld_nm"], \
            f"챗봇 search: 우성아파트상가(1984)가 2011이후 필터 통과"


@test("챗봇: search_commute 실행 (ODSay)")
def test_tool_commute():
    from services.tools import search_commute
    result = asyncio.run(search_commute(
        pnu="1121510500008540000",  # 광진트라팰리스
        destination="강남역",
    ))
    data = json.loads(result)
    if "error" not in data:
        assert len(data.get("routes", [])) > 0, "경로 없음"
        assert data["routes"][0]["total_time"] > 0, "소요시간 0"
    # ODSay API 키가 없으면 에러 → 허용


# ============================================================
# 5. 안전 점수 테스트
# ============================================================

@test("안전: 범죄율 점수 존재 (서울 25구)")
def test_crime_score_coverage():
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM sigungu_crime_score WHERE sigungu_code LIKE %s", ['11%']
    ).fetchone()
    conn.close()
    cnt = row['cnt']
    assert cnt >= 25, f"서울 범죄점수 {cnt}개 (25개 이상 필요)"


@test("안전: 주간인구 보정 데이터 존재 (중구 float_pop_ratio > 1)")
def test_crime_floating_pop():
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute(
        "SELECT float_pop_ratio, effective_pop, resident_pop "
        "FROM sigungu_crime_detail WHERE sigungu_code = '11140'"
    ).fetchone()
    conn.close()
    assert row is not None, "중구 범죄상세 없음"
    assert row['float_pop_ratio'] > 1.0, \
        f"중구 float_pop_ratio={row['float_pop_ratio']} (주간인구 보정 미적용 — 업무지구라 2.0+ 예상)"
    assert row['effective_pop'] > row['resident_pop'], \
        "중구 주간인구(effective_pop)가 상주인구(resident_pop)보다 커야 함"


@test("안전: 상세 API에 crime_detail 포함")
def test_safety_detail_api():
    import requests
    resp = requests.get("http://localhost:8000/api/apartment/1111010100000560045", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    safety = data.get("safety", {})
    assert safety is not None, "safety 필드 없음"
    assert safety.get("crime_detail") is not None, "crime_detail 없음"
    cd = safety["crime_detail"]
    assert cd.get("total_crime", 0) > 0, "total_crime=0"
    assert cd.get("float_pop_ratio") is not None, "float_pop_ratio 필드 없음"


# ============================================================
# 6. 면적 정보 테스트
# ============================================================

@test("면적: apt_area_info 커버리지 > 90% (거래 매핑 아파트 기준)")
def test_area_coverage():
    from database import DictConnection
    conn = DictConnection()
    # 거래 매핑된 아파트 기준 (trade_apt_mapping에 PNU가 있는 아파트)
    total = conn.execute(
        "SELECT COUNT(DISTINCT pnu) as cnt FROM trade_apt_mapping WHERE pnu NOT LIKE %s", ['TRADE_%']
    ).fetchone()['cnt']
    area = conn.execute("SELECT COUNT(DISTINCT pnu) as cnt FROM apt_area_info").fetchone()['cnt']
    conn.close()
    coverage = area / total * 100 if total > 0 else 0
    assert coverage > 90, f"면적 커버리지 {coverage:.1f}% (거래 매핑 {total}건 기준, 90% 이상 필요)"


# ============================================================
# 7. 챗봇 스트리밍 + 추가 Tool 테스트
# ============================================================

@test("챗봇: /api/chat/stream SSE 스트리밍 응답")
def test_chat_stream():
    import requests
    resp = requests.post("http://localhost:8000/api/chat/stream", json={
        "message": "안녕하세요",
        "conversation": [],
        "context": {},
    }, stream=True, timeout=30)
    assert resp.status_code == 200, f"스트리밍 API 에러: {resp.status_code}"
    assert resp.headers.get("content-type", "").startswith("text/event-stream"), \
        f"Content-Type이 SSE가 아님: {resp.headers.get('content-type')}"
    # 최소 1개의 delta 이벤트 수신
    found_delta = False
    for line in resp.iter_lines(decode_unicode=True):
        if line and line.startswith("event: delta"):
            found_delta = True
            break
        if line and line.startswith("event: done"):
            break
    resp.close()
    assert found_delta, "delta 이벤트를 수신하지 못함"


@test("챗봇: compare_apartments tool")
def test_tool_compare():
    from services.tools import compare_apartments
    result = asyncio.run(compare_apartments(queries=["래미안대치팰리스", "은마아파트"]))
    data = json.loads(result)
    assert "error" not in data, f"에러: {data.get('error')}"
    assert data.get("count", 0) >= 1, "비교 결과 없음"


@test("챗봇: get_market_trend tool")
def test_tool_market_trend():
    from services.tools import get_market_trend
    result = asyncio.run(get_market_trend(region="강남구", period="1y"))
    data = json.loads(result)
    assert "error" not in data, f"에러: {data.get('error')}"
    assert len(data.get("trade_trends", [])) > 0 or data.get("sgg_cd"), "시세 데이터 없음"


@test("챗봇: get_school_info tool")
def test_tool_school_info():
    from services.tools import get_school_info
    result = asyncio.run(get_school_info(query="래미안대치팰리스"))
    data = json.loads(result)
    # school 또는 schools 키 존재
    has_data = data.get("school") or data.get("schools") or "error" not in data
    assert has_data, f"학군 정보 없음: {data}"


@test("챗봇: get_market_trend 금액 단위 표기 검증")
def test_tool_market_trend_price_format():
    from services.tools import get_market_trend
    result = asyncio.run(get_market_trend(region="강남구", period="1y"))
    data = json.loads(result)
    trends = data.get("trade_trends", [])
    assert len(trends) > 0, "거래 추이 데이터 없음"
    for t in trends:
        price = t.get("avg_price", "")
        assert "만원" in price or "억" in price, f"금액 단위 누락: {price}"
        assert not str(price).replace(",", "").replace(".", "").isdigit(), f"금액이 숫자만: {price} (단위 필요)"


@test("챗봇: get_apartment_detail 거래 금액 단위 검증")
def test_tool_detail_price_format():
    from services.tools import get_apartment_detail
    result = asyncio.run(get_apartment_detail("래미안대치팰리스"))
    data = json.loads(result)
    trades = data.get("recent_trades", [])
    if trades:
        for t in trades:
            price = t.get("price", "")
            assert "만원" in price or "억" in price, f"금액 단위 누락: {price}"


@test("챗봇: get_dashboard_info 금액 단위 검증")
def test_tool_dashboard_price_format():
    from services.tools import get_dashboard_info
    result = asyncio.run(get_dashboard_info(region="강남구"))
    data = json.loads(result)
    med = data.get("trade_summary", {}).get("median_price_m2", "")
    assert "만" in med or "㎡" in med, f"중위가 단위 누락: {med}"
    trend = data.get("monthly_trend", "")
    assert "만원" in trend, f"추이 금액 단위 누락: {trend}"


@test("챗봇: 안전 점수 관련 데이터 포함 응답")
def test_chat_safety_data():
    """get_apartment_detail 결과에 safety + crime_detail 포함 확인."""
    from services.tools import get_apartment_detail
    result = asyncio.run(get_apartment_detail("1111010100000560045"))  # 종로구 청운현대
    data = json.loads(result)
    assert "error" not in data, f"에러: {data.get('error')}"
    assert "nudge_scores" in data, "nudge_scores 없음"
    assert "safety" in data.get("nudge_scores", {}), "safety 넛지 점수 없음"


@test("챗봇: get_apartment_detail 응답에서 None 필드 제거")
def test_chat_detail_drops_none_fields():
    """LLM/agent 응답 깔끔함 확보를 위해 None 값 필드는 응답에서 제외한다.

    데이터 커버리지 약 4~18% 의 필드(total_households, dong_count, max_floor, built_date,
    address, school 등)가 누락된 PNU 에서, 해당 key 자체가 응답에 없어야 한다.
    """
    from services.tools import get_apartment_detail
    # 청운벽산빌리지 — total_hhld_cnt/dong_count/max_floor/use_apr_day/new_plat_plc/plat_plc 가 모두 NULL 인 희소 케이스
    result = asyncio.run(get_apartment_detail("1111010100000010000"))
    data = json.loads(result)
    assert "error" not in data, f"에러: {data.get('error')}"
    basic = data.get("basic", {})
    # NULL 필드는 basic 에서 완전히 제거
    for absent in ("total_households", "dong_count", "max_floor", "built_date"):
        assert absent not in basic, f"basic 에 NULL 필드가 남아있음: {absent}={basic.get(absent)!r}"
    # 반대로 실제 값이 있는 필드는 보존
    assert basic.get("name") == "청운벽산빌리지"
    assert basic.get("lat") is not None and basic.get("lng") is not None
    # school 데이터가 없는 케이스는 top-level 에서 제거
    assert "school" not in data or data["school"] is not None


# ============================================================
# 8. 피드백 API 테스트
# ============================================================

@test("피드백: POST /api/chat/feedback 저장")
def test_feedback_submit():
    import requests
    resp = requests.post("http://localhost:8000/api/chat/feedback", json={
        "user_message": "테스트 질문",
        "assistant_message": "테스트 답변",
        "rating": 1,
        "tags": [],
        "comment": "__test__",
    }, timeout=10)
    assert resp.status_code == 200, f"피드백 API 에러: {resp.status_code}"
    data = resp.json()
    assert data.get("id", 0) > 0, f"피드백 ID 없음: {data}"
    # 테스트 데이터 정리
    from database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_feedback WHERE id = %s", [data["id"]])
    conn.commit()
    conn.close()


@test("피드백: GET /api/chat/feedback/stats 통계")
def test_feedback_stats():
    import requests
    resp = requests.get("http://localhost:8000/api/chat/feedback/stats", timeout=10)
    assert resp.status_code == 200, f"통계 API 에러: {resp.status_code}"
    data = resp.json()
    assert "total" in data, "total 필드 없음"
    assert "likes" in data, "likes 필드 없음"
    assert "dislikes" in data, "dislikes 필드 없음"


# ============================================================
# 9. API 엔드포인트 기본 테스트
# ============================================================

@test("API: GET /api/health")
def test_api_health():
    import requests
    resp = requests.get("http://localhost:8000/api/health", timeout=5)
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


@test("API: GET /api/apartments 응답")
def test_api_apartments():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 1000, f"아파트 {len(data)}개 (1000개 이상 예상)"


@test("API: GET /api/apartment/{pnu} 상세")
def test_api_apartment_detail():
    import requests
    resp = requests.get("http://localhost:8000/api/apartment/1168010600010270000", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("basic", {}).get("bld_nm") is not None, "아파트 이름 없음"
    assert "scores" in data, "scores 없음"
    assert "facility_summary" in data, "facility_summary 없음"


@test("API: POST /api/commute 통근 조회")
def test_api_commute():
    import requests
    resp = requests.post("http://localhost:8000/api/commute", json={
        "pnu": "1121510500008540000",
        "destination": "강남역",
    }, timeout=20)
    # ODSay 키 문제일 수 있으므로 200 또는 502 허용
    assert resp.status_code in (200, 502, 404), f"예상치 못한 에러: {resp.status_code}"


# ============================================================
# 10. 유사 아파트 추천 테스트
# ============================================================

@test("유사추천: apt_vectors 서브벡터 구조 확인")
def test_vectors_schema():
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute("""
        SELECT vec_basic, vec_price, vec_facility, vec_safety, vector_version
        FROM apt_vectors LIMIT 1
    """).fetchone()
    conn.close()
    assert row is not None, "apt_vectors 테이블이 비어있음"
    assert len(row["vec_basic"]) == 4, f"basic 차원: {len(row['vec_basic'])} != 4"
    assert len(row["vec_price"]) == 3, f"price 차원: {len(row['vec_price'])} != 3"
    assert len(row["vec_facility"]) == 20, f"facility 차원: {len(row['vec_facility'])} != 20"
    assert len(row["vec_safety"]) == 3, f"safety 차원: {len(row['vec_safety'])} != 3"
    assert row["vector_version"] >= 1, "vector_version이 1 미만"


@test("유사추천: location 모드 코사인 유사도 0~1 범위")
def test_similar_location():
    from services.similarity import calc_location, parse_vectors
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute("""
        SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2
    """).fetchall()
    conn.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score = calc_location(t, c)
    assert -1 <= score <= 1, f"코사인 유사도 범위 초과: {score}"


@test("유사추천: price 모드 유클리디안 유사도 0~1 범위")
def test_similar_price():
    from services.similarity import calc_price, parse_vectors
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2").fetchall()
    conn.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score = calc_price(t, c)
    assert 0 <= score <= 1, f"유클리디안 유사도 범위 초과: {score}"


@test("유사추천: lifestyle 모드 선호도 점수 반환")
def test_similar_lifestyle():
    from services.similarity import calc_lifestyle, parse_vectors
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 1").fetchone()
    conn.close()
    c = parse_vectors(row)
    score = calc_lifestyle(c, {"교통": 0.9, "교육": 0.7})
    assert isinstance(score, float), f"점수 타입 오류: {type(score)}"


@test("유사추천: combined 모드 include_price 옵션")
def test_similar_combined_price():
    from services.similarity import calc_combined, parse_vectors
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2").fetchall()
    conn.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score_no_price = calc_combined(t, c, include_price=False)
    score_with_price = calc_combined(t, c, include_price=True)
    assert score_no_price != score_with_price, "include_price 옵션이 결과에 영향을 주지 않음"


# ============================================================
# 11. 관리자 API 테스트
# ============================================================

ADMIN_BASE = "http://localhost:8000/api/admin"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


@test("관리자: 토큰 없이 401")
def test_admin_no_token():
    import requests
    resp = requests.get(f"{ADMIN_BASE}/dashboard/summary", timeout=5)
    # ADMIN_TOKEN이 미설정이면 503, 설정되어 있으면 401
    assert resp.status_code in (401, 503), f"예상: 401 또는 503, 실제: {resp.status_code}"


@test("관리자: 잘못된 토큰 401")
def test_admin_bad_token():
    import requests
    if not ADMIN_TOKEN:
        return  # 토큰 미설정이면 스킵
    resp = requests.get(
        f"{ADMIN_BASE}/dashboard/summary",
        headers={"Authorization": "Bearer wrong_token"},
        timeout=5,
    )
    assert resp.status_code == 401, f"예상: 401, 실제: {resp.status_code}"


@test("관리자: 올바른 토큰으로 dashboard/summary 200")
def test_admin_dashboard_summary():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/dashboard/summary",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"예상: 200, 실제: {resp.status_code}"
    data = resp.json()
    assert "total_apartments" in data, "total_apartments 필드 없음"
    assert "today_trades" in data, "today_trades 필드 없음"
    assert "satisfaction_rate" in data, "satisfaction_rate 필드 없음"


@test("관리자: dashboard/quality 200")
def test_admin_dashboard_quality():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/dashboard/quality",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"예상: 200, 실제: {resp.status_code}"
    data = resp.json()
    assert "quality" in data, "quality 필드 없음"
    assert len(data["quality"]) > 0, "quality 배열 비어있음"


@test("관리자: data/{table} allowlist 위반 400")
def test_admin_data_table_invalid():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/data/users",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=5,
    )
    assert resp.status_code == 400, f"예상: 400, 실제: {resp.status_code}"


@test("관리자: data/apartments 정상 조회")
def test_admin_data_table_valid():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/data/apartments",
        params={"page": 1, "page_size": 5},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"예상: 200, 실제: {resp.status_code}"
    data = resp.json()
    assert data["table"] == "apartments"
    assert len(data["data"]) <= 5, f"page_size 초과: {len(data['data'])}"
    assert data["page"] == 1


@test("관리자: data/{table} 허용되지 않은 정렬 컬럼 400")
def test_admin_data_invalid_order():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/data/apartments",
        params={"order_by": "password"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=5,
    )
    assert resp.status_code == 400, f"예상: 400, 실제: {resp.status_code}"


@test("관리자: feedback/list 200")
def test_admin_feedback_list():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/feedback/list",
        params={"page": 1, "page_size": 3},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"예상: 200, 실제: {resp.status_code}"
    data = resp.json()
    assert "total" in data, "total 필드 없음"
    assert "data" in data, "data 필드 없음"


@test("관리자: scoring/weights 200")
def test_admin_scoring_weights():
    import requests
    if not ADMIN_TOKEN:
        return
    resp = requests.get(
        f"{ADMIN_BASE}/scoring/weights",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"예상: 200, 실제: {resp.status_code}"
    data = resp.json()
    assert "nudge_weights" in data, "nudge_weights 필드 없음"
    assert "max_distances" in data, "max_distances 필드 없음"


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("아파트 추천 서비스 통합 테스트")
    print("=" * 60)

    # ---------- 지역 프로필 기반 시설 점수 테스트 ----------

    @test("지역 프로필: 서울은 metro, 부산은 major_city, 제주는 provincial")
    def test_region_profile():
        from services.scoring import get_region_profile
        assert get_region_profile("11215") == "metro"
        assert get_region_profile("26110") == "major_city"
        assert get_region_profile("50110") == "provincial"
        assert get_region_profile(None) == "provincial"
        assert get_region_profile("") == "provincial"

    @test("지방 지하철 없는 아파트는 subway 중립점수 50점")
    def test_subway_neutral_nonmetro():
        from services.scoring import facility_score
        score_prov = facility_score(None, 0, "subway", profile="provincial")
        assert score_prov == 50.0, f"expected 50.0, got {score_prov}"
        score_major = facility_score(None, 0, "subway", profile="major_city")
        assert score_major == 50.0, f"expected 50.0, got {score_major}"
        # metro에서는 중립 아님 (기존 동작 유지)
        score_metro = facility_score(None, 0, "subway", profile="metro")
        assert score_metro == 0.0, f"expected 0.0, got {score_metro}"

    @test("동일 거리에서 provincial이 metro보다 높은 시설 점수")
    def test_provincial_higher_score_same_distance():
        from services.scoring import facility_score
        metro = facility_score(2000, 1, "mart", profile="metro")
        provincial = facility_score(2000, 1, "mart", profile="provincial")
        assert provincial > metro, f"provincial({provincial}) should > metro({metro})"

    @test("프로필 기본값: metro는 기존 동작과 동일")
    def test_metro_backward_compatible():
        from services.scoring import facility_score
        # profile 미지정 시 metro 기본값
        default_score = facility_score(500, 5, "mart")
        metro_score = facility_score(500, 5, "mart", profile="metro")
        assert default_score == metro_score, f"default({default_score}) != metro({metro_score})"

    # ---------- 관리비 면적별 안분 ----------

    @test("관리비 안분: 경희궁의아침4단지 정수 평형 그룹화(150은 2 subtype 병합)")
    def test_mgmt_cost_by_area_formula():
        from services.mgmt_cost_calc import compute_by_area
        latest = {"common_cost": 29805940, "individual_cost": 18721144, "repair_fund": 4168125}
        area_types = [
            {"exclusive_area": 124.17, "unit_count": 75, "priv_area_total": 16020.9},
            {"exclusive_area": 145.96, "unit_count": 15, "priv_area_total": 16020.9},
            {"exclusive_area": 150.48, "unit_count": 15, "priv_area_total": 16020.9},
            {"exclusive_area": 150.77, "unit_count": 15, "priv_area_total": 16020.9},
        ]
        result = compute_by_area(latest, area_types)
        # 124, 145, 150 — 150 그룹에 subtype 2개 병합
        assert result is not None and len(result) == 3, f"expected 3 groups, got {result}"
        keys = [r["exclusive_area"] for r in result]
        assert keys == [124, 145, 150], keys
        # 150 그룹: 30세대, 2 subtype
        g150 = next(r for r in result if r["exclusive_area"] == 150)
        assert g150["unit_count"] == 30 and g150["subtype_count"] == 2, g150
        # 124 그룹 세대당 관리비 40만원대
        g124 = next(r for r in result if r["exclusive_area"] == 124)
        assert 400000 <= g124["per_unit_cost"] <= 430000, g124
        # 단조 증가
        values = [r["per_unit_cost"] for r in result]
        assert values == sorted(values), f"values not sorted asc: {values}"
        # 합계 검증 (오차 < 0.1%)
        total_sum = sum(r["per_unit_cost"] * r["unit_count"] for r in result)
        actual = latest["common_cost"] + latest["individual_cost"] + latest["repair_fund"]
        err = abs(total_sum - actual) / actual
        assert err < 0.001, f"합계 오차 {err*100:.3f}% 초과: {total_sum} vs {actual}"

    @test("관리비 안분: 빈 입력/결측 데이터 방어")
    def test_mgmt_cost_by_area_edge():
        from services.mgmt_cost_calc import compute_by_area
        assert compute_by_area({}, []) is None
        assert compute_by_area({"common_cost": 100}, []) is None
        assert compute_by_area(
            {"common_cost": 100, "individual_cost": 0, "repair_fund": 0},
            [{"exclusive_area": 0, "unit_count": 0, "priv_area_total": 0}],
        ) is None

    @test("상세 API: mgmt_cost.by_area 정수 그룹, 세대 합 == 총 세대수")
    def test_detail_api_by_area():
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.get("/api/apartment/1111011800000730000")  # 경희궁의아침4단지
        assert resp.status_code == 200, resp.text
        data = resp.json()
        mc = data.get("mgmt_cost")
        assert mc is not None, "mgmt_cost 없음"
        by_area = mc.get("by_area")
        # 124, 145, 150 — 150.48/150.77 병합으로 3 그룹
        assert by_area and len(by_area) == 3, f"by_area 기대 3건, got {by_area}"
        total_units = sum(r["unit_count"] for r in by_area)
        assert total_units == 120, f"세대 합 120 기대, got {total_units}"
        keys = [r["exclusive_area"] for r in by_area]
        assert keys == [124, 145, 150], keys

    # ---------- 대시보드 성능: 집계 테이블 + 엔드포인트 ----------

    @test("대시보드: 집계 테이블 3종이 비어있지 않음")
    def test_dashboard_aggregate_tables_populated():
        from database import DictConnection
        conn = DictConnection()
        for table in ["dashboard_monthly_stats", "dashboard_window_stats", "dashboard_ranking_stats"]:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            assert row["n"] > 0, f"{table} 비어있음 — 배치 실행 필요"
        conn.close()

    @test("대시보드: dashboard_monthly_stats(ALL 최근월)의 trade_volume이 raw COUNT에 근접")
    def test_dashboard_monthly_matches_raw():
        """집계 테이블(dashboard_monthly_stats)은 배치 주기에 맞춰 갱신되므로, 가장 최근
        월은 raw trade_history 와 수십~수백 건 drift 가 정상이다. 완전 일치가 아닌
        tolerance 기반으로 검증한다.

        허용 오차: max(raw * 1%, 100 건). 이보다 크면 배치 failing 이 의심됨.
        """
        from database import DictConnection
        conn = DictConnection()
        agg = conn.execute("""
            SELECT deal_year, deal_month, trade_volume
            FROM dashboard_monthly_stats
            WHERE scope = 'ALL'
            ORDER BY deal_year DESC, deal_month DESC
            LIMIT 1
        """).fetchone()
        assert agg is not None, "monthly 집계 없음"
        raw = conn.execute(
            "SELECT COUNT(*) AS n FROM trade_history WHERE deal_year = %s AND deal_month = %s",
            [agg["deal_year"], agg["deal_month"]],
        ).fetchone()
        conn.close()

        diff = abs(agg["trade_volume"] - raw["n"])
        tolerance = max(raw["n"] // 100, 100)
        assert diff <= tolerance, (
            f"집계 drift 과다: agg={agg['trade_volume']} vs raw={raw['n']} "
            f"(diff={diff}, tolerance={tolerance}) for "
            f"{agg['deal_year']}-{agg['deal_month']:02d}. 배치 실행 확인 필요."
        )

    @test("대시보드 /summary: API 응답 volume이 window_stats 값과 일치")
    def test_dashboard_summary_matches_window():
        from routers.dashboard import dashboard_summary
        from database import DictConnection
        conn = DictConnection()
        agg = conn.execute(
            "SELECT trade_volume, rent_volume FROM dashboard_window_stats "
            "WHERE scope = 'ALL' AND window_kind = 'current'"
        ).fetchone()
        conn.close()
        assert agg is not None, "window_stats 없음"
        api = dashboard_summary(sigungu="")
        assert api["trade"]["volume"] == agg["trade_volume"], (
            f"summary.trade.volume={api['trade']['volume']} != "
            f"window.trade_volume={agg['trade_volume']}"
        )
        assert api["rent"]["volume"] == agg["rent_volume"], (
            f"summary.rent.volume={api['rent']['volume']} != "
            f"window.rent_volume={agg['rent_volume']}"
        )
        # 응답 스키마 유지 확인
        for k in ["current_period", "prev_period", "trade", "rent", "last_updated", "new_today", "data_lag_notice"]:
            assert k in api, f"응답에 {k} 없음"

    @test("대시보드 /trend: months 이내 결과 + 필수 키 포함")
    def test_dashboard_trend_structure():
        from routers.dashboard import dashboard_trend
        result = dashboard_trend(months=12, sigungu="")
        assert isinstance(result, list), "배열 아님"
        assert len(result) <= 12, f"len={len(result)} > 12"
        if result:
            for k in ["month", "trade_volume", "trade_avg_price", "trade_avg_price_m2",
                      "rent_volume", "rent_avg_deposit", "jeonse_ratio"]:
                assert k in result[0], f"응답에 {k} 없음"

    @test("대시보드 /ranking: Top 10 이하 + volume 단조 감소 + 필수 키")
    def test_dashboard_ranking_structure():
        from routers.dashboard import dashboard_ranking
        trade = dashboard_ranking(type="trade")
        assert isinstance(trade, list)
        assert len(trade) <= 10, f"len={len(trade)} > 10"
        for i in range(len(trade) - 1):
            assert trade[i]["volume"] >= trade[i + 1]["volume"], (
                f"volume 단조 감소 위반: {trade[i]['volume']} < {trade[i + 1]['volume']}"
            )
        if trade:
            for k in ["sigungu_code", "sigungu_name", "volume", "avg_price"]:
                assert k in trade[0], f"trade ranking에 {k} 없음"
        rent = dashboard_ranking(type="rent")
        if rent:
            assert "avg_deposit" in rent[0], "rent ranking에 avg_deposit 없음"

    @test("대시보드 /recent: limit 이하 + 날짜 단조 감소")
    def test_dashboard_recent_ordering():
        from routers.dashboard import dashboard_recent
        rows = dashboard_recent(type="trade", limit=20, sigungu="")
        assert isinstance(rows, list)
        assert len(rows) <= 20, f"len={len(rows)} > 20"
        # date 문자열 'YYYY.MM.DD' 형식 → 단조 감소
        for i in range(len(rows) - 1):
            assert rows[i]["date"] >= rows[i + 1]["date"], (
                f"date 단조 감소 위반: {rows[i]['date']} < {rows[i + 1]['date']}"
            )

    @test("대시보드 시군구 필터: /summary?sigungu=X의 volume이 window_stats(scope=X)와 일치")
    def test_dashboard_sigungu_filter():
        from routers.dashboard import dashboard_summary
        from database import DictConnection
        conn = DictConnection()
        # window_stats에서 scope가 실제 존재하는 시군구 하나 선택
        row = conn.execute("""
            SELECT scope, trade_volume FROM dashboard_window_stats
            WHERE window_kind = 'current' AND scope <> 'ALL' AND trade_volume > 0
            ORDER BY trade_volume DESC LIMIT 1
        """).fetchone()
        conn.close()
        if not row:
            return  # 시군구별 데이터 없으면 skip (신규 배치 전)
        api = dashboard_summary(sigungu=row["scope"])
        assert api["trade"]["volume"] == row["trade_volume"], (
            f"sigungu={row['scope']} agg={row['trade_volume']} vs api={api['trade']['volume']}"
        )

    # ---------- API 레벨 개선: Connection Pool ----------

    @test("Pool: init_pool 후 DictConnection 반복 acquire/close 시 pool leak 없음")
    def test_pool_no_leak_on_repeat():
        from database import init_pool, DictConnection
        import database as db_module
        init_pool()
        assert db_module._pool is not None, "pool 미초기화"
        pool = db_module._pool
        # 절대값 0 체크는 이전 테스트 영향을 받으니 delta 로 비교.
        used_before = len(pool._used)
        for _ in range(100):
            conn = DictConnection()
            conn.execute("SELECT 1 AS ok").fetchone()
            conn.close()
        used_after = len(pool._used)
        assert used_after == used_before, (
            f"leak delta: before={used_before}, after={used_after}"
        )

    @test("Pool: log_event 정상/예외 호출 후 conn leak 없음")
    def test_pool_no_leak_on_log_event_failure():
        from database import init_pool
        from services.activity_log import log_event
        import database as db_module
        init_pool()
        pool = db_module._pool
        used_before = len(pool._used)
        # 1) json.dumps 실패 유도 (직렬화 불가 객체) — DictConnection 생성 전 예외
        class Unserializable:
            pass
        log_event("device-test-1", "test_event", None, {"bad": Unserializable()})
        # 2) 정상 호출 100회
        for _ in range(100):
            log_event("device-test-2", "test_event_ok", None, {"n": 1})
        used_after = len(pool._used)
        assert used_after == used_before, (
            f"log_event 호출 후 conn leak: before={used_before}, after={used_after}"
        )

    @test("Pool: get_connection(use_pool=False) 는 pool 을 거치지 않음")
    def test_get_connection_bypass_pool():
        from database import init_pool, get_connection
        import database as db_module
        init_pool()
        pool = db_module._pool
        used_before = len(pool._used)
        conn = get_connection(use_pool=False)
        assert len(pool._used) == used_before, "use_pool=False 인데 pool 사용됨"
        conn.close()
        assert len(pool._used) == used_before

    @test("대시보드 Fallback: 집계 테이블 비어도 HTTP 200 + 응답 구조 유지")
    def test_dashboard_fallback_when_empty():
        """집계 테이블이 배치 전 빈 상태일 때 raw 쿼리 fallback이 동작하는지 확인.

        가장 위험한 배포 상태(배치 최초 실행 전)가 미검증으로 남는 걸 방지.
        """
        from routers.dashboard import dashboard_summary, dashboard_trend, dashboard_ranking
        from database import DictConnection

        # 백업 → TRUNCATE → 테스트 → 복원
        conn = DictConnection()
        tables = ["dashboard_monthly_stats", "dashboard_window_stats", "dashboard_ranking_stats"]
        backup = {}
        for t in tables:
            backup[t] = conn.execute(f"SELECT * FROM {t}").fetchall()
            conn.execute(f"DELETE FROM {t}")

        try:
            summary = dashboard_summary(sigungu="")
            assert summary is not None, "summary fallback 실패"
            for k in ["trade", "rent", "current_period", "prev_period"]:
                assert k in summary, f"summary fallback 응답에 {k} 없음"

            trend = dashboard_trend(months=12, sigungu="")
            assert isinstance(trend, list), "trend fallback 배열 아님"
            if trend:
                for k in ["month", "trade_volume", "rent_volume", "jeonse_ratio"]:
                    assert k in trend[0], f"trend fallback에 {k} 없음"

            ranking = dashboard_ranking(type="trade")
            assert isinstance(ranking, list)
            assert len(ranking) <= 10
            if ranking:
                for k in ["sigungu_code", "sigungu_name", "volume", "avg_price"]:
                    assert k in ranking[0], f"ranking fallback에 {k} 없음"
        finally:
            # 복원 — 집계 테이블을 원상태로 되돌림
            from psycopg2.extras import execute_values
            raw_conn = conn._raw  # DictConnection 내부 raw conn (pool wrapper 이후 속성명)
            cur = raw_conn.cursor()
            for t, rows in backup.items():
                if not rows:
                    continue
                cols = list(rows[0].keys())
                placeholders = "(" + ", ".join(["%s"] * len(cols)) + ")"
                sql = f"INSERT INTO {t} ({', '.join(cols)}) VALUES %s"
                execute_values(cur, sql, [tuple(r[c] for c in cols) for r in rows], template=placeholders)
            raw_conn.commit()
            conn.close()

    # 모든 테스트 수집
    tests = [v for v in globals().values() if callable(v) and hasattr(v, '_test_name')]

    print(f"\n{len(tests)}개 테스트 실행\n")

    for t in tests:
        t()

    print(f"\n{'=' * 60}")
    print(f"결과: ✅ {passed} 통과 / ❌ {failed} 실패 / 총 {passed + failed}")
    if errors:
        print(f"\n실패 목록:")
        for e in errors:
            print(f"  • {e}")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
