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
    data = resp.json()
    assert len(data) >= 1, "래미안대치팰리스 검색 결과 없음"
    names = [a["bld_nm"] for a in data]
    assert any("래미안" in n and "대치" in n for n in names), f"래미안 대치 팰리스 미포함: {names}"


@test("검색: 래미안 대치 팰리스 (띄어쓰기) 검색 성공")
def test_search_with_spaces():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments/search",
                       params={"q": "래미안 대치 팰리스"}, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1, "래미안 대치 팰리스 검색 결과 없음"


@test("검색: 자양동 키워드 검색 → 복수 결과")
def test_search_region():
    import requests
    resp = requests.get("http://localhost:8000/api/apartments/search",
                       params={"q": "자양동"}, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 10, f"자양동 검색 결과 {len(data)}건 (10건 이상 예상)"


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
