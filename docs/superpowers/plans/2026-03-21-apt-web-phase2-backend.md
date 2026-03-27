# Phase 2: FastAPI 백엔드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 아파트 추천 웹서비스의 FastAPI 백엔드 API 서버를 구현한다.

**Architecture:** FastAPI 앱이 SQLite DB(`apt_web.db`)를 쿼리하여 4개 API 엔드포인트를 제공한다. 넛지 스코어링은 `apt_facility_summary` 요약 테이블을 활용하여 실시간 계산한다.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, sqlite3

**Spec:** `docs/superpowers/specs/2026-03-21-apt-web-design.md`

---

## Task 0: FastAPI 기본 설정

**Files:**
- Create: `web/backend/main.py`
- Create: `web/backend/requirements.txt`

- [ ] **Step 1: 패키지 설치**

```bash
uv pip install fastapi uvicorn --python .venv/bin/python
```

- [ ] **Step 2: main.py — FastAPI 앱 진입점**

```python
"""아파트 추천 웹서비스 API 서버"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import apartments, nudge, detail

app = FastAPI(title="아파트 추천 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apartments.router, prefix="/api")
app.include_router(nudge.router, prefix="/api")
app.include_router(detail.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 3: 실행 테스트**

```bash
cd web/backend
../../.venv/bin/python -m uvicorn main:app --reload --port 8000
# 별도 터미널에서:
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

---

## Task 1: 아파트 목록 API

**Files:**
- Create: `web/backend/routers/__init__.py`
- Create: `web/backend/routers/apartments.py`

- [ ] **Step 1: apartments.py 구현**

```python
"""아파트 목록/검색 API"""

from fastapi import APIRouter, Query
from database import get_connection

router = APIRouter()


@router.get("/apartments")
def get_apartments(
    sw_lat: float = Query(None),
    sw_lng: float = Query(None),
    ne_lat: float = Query(None),
    ne_lng: float = Query(None),
):
    """아파트 목록 조회 (지도 마커용). bounds 파라미터로 영역 필터링 가능."""
    conn = get_connection()
    try:
        if all([sw_lat, sw_lng, ne_lat, ne_lng]):
            rows = conn.execute("""
                SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code
                FROM apartments
                WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
                AND lat IS NOT NULL
            """, (sw_lat, ne_lat, sw_lng, ne_lng)).fetchall()
        else:
            rows = conn.execute("""
                SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code
                FROM apartments WHERE lat IS NOT NULL
            """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 2: routers/__init__.py 생성** (빈 파일)

- [ ] **Step 3: 테스트**

```bash
curl "http://localhost:8000/api/apartments?sw_lat=37.5&sw_lng=127.0&ne_lat=37.6&ne_lng=127.1" | python -m json.tool | head -20
```

---

## Task 2: 넛지 스코어링 API

**Files:**
- Create: `web/backend/services/__init__.py`
- Create: `web/backend/services/scoring.py`
- Create: `web/backend/routers/nudge.py`

- [ ] **Step 1: scoring.py — 넛지 스코어링 엔진**

```python
"""넛지별 스코어 계산 엔진"""

# 시설 유형별 최대 거리 (점수 계산용, 미터)
MAX_DISTANCES = {
    "subway": 2000, "bus": 1000, "mart": 3000,
    "school": 1500, "kindergarten": 1500, "police": 5000,
    "fire_station": 5000, "library": 3000, "park": 2000,
    "convenience_store": 1000, "pharmacy": 1500,
    "hospital": 3000, "animal_hospital": 3000, "pet_facility": 3000,
}

# 넛지별 기본 가중치 (시설 유형 → 가중치)
NUDGE_WEIGHTS = {
    "cost": {
        "subway": 15, "bus": 5, "convenience_store": 10,
        "mart": 5, "hospital": 5,
        "_price": 30, "_jeonse": 20, "_unit_size": 10,
    },
    "pet": {
        "animal_hospital": 25, "pet_facility": 25, "park": 20,
        "convenience_store": 5, "hospital": 5,
    },
    "commute": {
        "subway": 30, "bus": 15, "convenience_store": 10,
        "pharmacy": 5,
    },
    "newlywed": {
        "kindergarten": 20, "school": 20, "hospital": 15,
        "park": 15, "convenience_store": 5, "pharmacy": 5,
    },
    "education": {
        "school": 25, "library": 15, "kindergarten": 10,
        "convenience_store": 5, "subway": 10,
    },
    "senior": {
        "hospital": 25, "pharmacy": 15, "park": 15,
        "convenience_store": 10, "bus": 5, "mart": 5,
    },
    "investment": {
        "subway": 15, "bus": 5, "convenience_store": 5,
        "_price": 25, "_jeonse": 20, "_age": 10,
    },
    "nature": {
        "park": 30, "hospital": 10, "subway": 5,
        "convenience_store": 5,
    },
}


def distance_to_score(distance_m, facility_subtype):
    """거리를 0~100 점수로 변환 (가까울수록 높은 점수)"""
    max_d = MAX_DISTANCES.get(facility_subtype, 3000)
    if distance_m is None:
        return 0
    return max(0, 100 - (distance_m / max_d * 100))


def calculate_nudge_score(facility_scores, nudge_id, custom_weights=None):
    """
    넛지별 스코어 계산.
    facility_scores: {facility_subtype: distance_score}
    custom_weights: 사용자 커스텀 가중치 (없으면 기본값)
    """
    weights = custom_weights or NUDGE_WEIGHTS.get(nudge_id, {})
    # 시설 관련 가중치만 추출 (_로 시작하는 것은 가격 등 비시설 지표)
    facility_weights = {k: v for k, v in weights.items() if not k.startswith("_")}

    if not facility_weights:
        return 0

    total_weight = sum(facility_weights.values())
    if total_weight == 0:
        return 0

    score = sum(
        facility_scores.get(ft, 0) * w / total_weight
        for ft, w in facility_weights.items()
    )
    return round(score, 1)


def calculate_multi_nudge_score(facility_scores, nudge_ids, custom_weights=None):
    """복수 넛지 선택 시 단순 평균"""
    if not nudge_ids:
        return 0
    scores = [
        calculate_nudge_score(facility_scores, nid, custom_weights)
        for nid in nudge_ids
    ]
    return round(sum(scores) / len(scores), 1)
```

- [ ] **Step 2: nudge.py — 스코어링 API**

```python
"""넛지 스코어링 API"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from database import get_connection
from services.scoring import (
    distance_to_score, calculate_nudge_score,
    calculate_multi_nudge_score, NUDGE_WEIGHTS
)

router = APIRouter()


class NudgeRequest(BaseModel):
    nudges: list[str]                           # ["pet", "nature"]
    weights: Optional[dict[str, int]] = None    # 커스텀 가중치
    top_n: int = 5
    sw_lat: Optional[float] = None
    sw_lng: Optional[float] = None
    ne_lat: Optional[float] = None
    ne_lng: Optional[float] = None


@router.post("/nudge/score")
def score_apartments(req: NudgeRequest):
    conn = get_connection()
    try:
        # 1. 대상 아파트 필터 (bounds)
        if all([req.sw_lat, req.sw_lng, req.ne_lat, req.ne_lng]):
            apts = conn.execute("""
                SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code
                FROM apartments
                WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
                AND lat IS NOT NULL
            """, (req.sw_lat, req.ne_lat, req.sw_lng, req.ne_lng)).fetchall()
        else:
            apts = conn.execute("""
                SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code
                FROM apartments WHERE lat IS NOT NULL
            """).fetchall()

        # 2. 각 아파트의 시설 요약 가져오기
        pnu_list = [a["pnu"] for a in apts]
        apt_map = {a["pnu"]: dict(a) for a in apts}

        # 배치로 요약 데이터 로드
        summaries = {}
        batch_size = 500
        for i in range(0, len(pnu_list), batch_size):
            batch = pnu_list[i:i+batch_size]
            placeholders = ",".join(["?"] * len(batch))
            rows = conn.execute(f"""
                SELECT pnu, facility_subtype, nearest_distance_m
                FROM apt_facility_summary
                WHERE pnu IN ({placeholders})
            """, batch).fetchall()
            for r in rows:
                if r["pnu"] not in summaries:
                    summaries[r["pnu"]] = {}
                summaries[r["pnu"]][r["facility_subtype"]] = r["nearest_distance_m"]

        # 3. 스코어링
        results = []
        for pnu in pnu_list:
            distances = summaries.get(pnu, {})
            facility_scores = {
                ft: distance_to_score(dist, ft)
                for ft, dist in distances.items()
            }
            score = calculate_multi_nudge_score(
                facility_scores, req.nudges, req.weights
            )
            score_breakdown = {
                ft: round(distance_to_score(distances.get(ft), ft), 1)
                for ft in set().union(*(
                    NUDGE_WEIGHTS.get(n, {}).keys() for n in req.nudges
                )) if not ft.startswith("_")
            }

            apt = apt_map[pnu]
            results.append({
                "pnu": pnu,
                "bld_nm": apt["bld_nm"],
                "lat": apt["lat"],
                "lng": apt["lng"],
                "total_hhld_cnt": apt["total_hhld_cnt"],
                "score": score,
                "score_breakdown": score_breakdown,
            })

        # 4. 정렬 + Top N
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:req.top_n]
    finally:
        conn.close()


@router.get("/nudge/weights")
def get_default_weights():
    """넛지별 기본 가중치 조회"""
    return NUDGE_WEIGHTS
```

- [ ] **Step 3: 테스트**

```bash
curl -X POST "http://localhost:8000/api/nudge/score" \
  -H "Content-Type: application/json" \
  -d '{"nudges":["pet"],"top_n":5}' | python -m json.tool
```

---

## Task 3: 아파트 상세 정보 API

**Files:**
- Create: `web/backend/routers/detail.py`

- [ ] **Step 1: detail.py 구현**

```python
"""아파트 상세 정보 API"""

from fastapi import APIRouter, HTTPException
from database import get_connection
from services.scoring import distance_to_score, calculate_nudge_score, NUDGE_WEIGHTS

router = APIRouter()


@router.get("/apartment/{pnu}")
def get_apartment_detail(pnu: str):
    """아파트 상세 정보 (기본정보 + 스코어 + 시설 + 학군)"""
    conn = get_connection()
    try:
        # 기본정보
        apt = conn.execute(
            "SELECT * FROM apartments WHERE pnu = ?", (pnu,)
        ).fetchone()
        if not apt:
            raise HTTPException(status_code=404, detail="아파트를 찾을 수 없습니다")

        # 시설 요약
        summaries = conn.execute("""
            SELECT facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km
            FROM apt_facility_summary WHERE pnu = ?
        """, (pnu,)).fetchall()

        facility_summary = {r["facility_subtype"]: dict(r) for r in summaries}

        # 넛지별 스코어
        distances = {r["facility_subtype"]: r["nearest_distance_m"] for r in summaries}
        facility_scores = {
            ft: distance_to_score(dist, ft) for ft, dist in distances.items()
        }
        scores = {}
        for nudge_id in NUDGE_WEIGHTS:
            scores[nudge_id] = calculate_nudge_score(facility_scores, nudge_id)

        # 주변 시설 Top 목록 (가까운 순, 유형별 3개)
        nearby = conn.execute("""
            SELECT m.facility_subtype, m.facility_id, m.distance_m,
                   f.name, f.lat, f.lng
            FROM apt_facility_mapping m
            JOIN facilities f ON m.facility_id = f.facility_id
            WHERE m.pnu = ? AND m.distance_m <= 2000
            ORDER BY m.facility_subtype, m.distance_m
        """, (pnu,)).fetchall()

        # 유형별 가까운 3개만
        facilities_by_type = {}
        for r in nearby:
            ft = r["facility_subtype"]
            if ft not in facilities_by_type:
                facilities_by_type[ft] = []
            if len(facilities_by_type[ft]) < 3:
                facilities_by_type[ft].append({
                    "name": r["name"],
                    "distance_m": r["distance_m"],
                    "lat": r["lat"], "lng": r["lng"],
                })

        # 학군
        school = conn.execute(
            "SELECT * FROM school_zones WHERE pnu = ?", (pnu,)
        ).fetchone()

        return {
            "basic": dict(apt),
            "scores": scores,
            "facility_summary": facility_summary,
            "nearby_facilities": facilities_by_type,
            "school": dict(school) if school else None,
        }
    finally:
        conn.close()


@router.get("/apartment/{pnu}/trades")
def get_trades(pnu: str):
    """매매/전세 거래 내역"""
    conn = get_connection()
    try:
        # PNU → apt_seq 매핑
        mapping = conn.execute(
            "SELECT apt_seq FROM trade_apt_mapping WHERE pnu = ?", (pnu,)
        ).fetchone()

        trades = []
        rents = []

        if mapping:
            apt_seq = mapping["apt_seq"]
            trades = [dict(r) for r in conn.execute("""
                SELECT deal_year, deal_month, deal_day, deal_amount,
                       exclu_use_ar, floor, build_year
                FROM trade_history WHERE apt_seq = ?
                ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
            """, (apt_seq,)).fetchall()]

            rents = [dict(r) for r in conn.execute("""
                SELECT deal_year, deal_month, deal_day, deposit,
                       monthly_rent, exclu_use_ar, floor
                FROM rent_history WHERE apt_seq = ?
                ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
            """, (apt_seq,)).fetchall()]
        else:
            # apt_seq 매핑이 없으면 sgg_cd + apt_nm으로 직접 검색
            apt = conn.execute(
                "SELECT bld_nm, sigungu_code FROM apartments WHERE pnu = ?", (pnu,)
            ).fetchone()
            if apt and apt["bld_nm"]:
                trades = [dict(r) for r in conn.execute("""
                    SELECT deal_year, deal_month, deal_day, deal_amount,
                           exclu_use_ar, floor, build_year
                    FROM trade_history
                    WHERE sgg_cd = ? AND apt_nm LIKE ?
                    ORDER BY deal_year DESC, deal_month DESC
                    LIMIT 100
                """, (apt["sigungu_code"], f"%{apt['bld_nm'][:4]}%")).fetchall()]

                rents = [dict(r) for r in conn.execute("""
                    SELECT deal_year, deal_month, deal_day, deposit,
                           monthly_rent, exclu_use_ar, floor
                    FROM rent_history
                    WHERE sgg_cd = ? AND apt_nm LIKE ?
                    ORDER BY deal_year DESC, deal_month DESC
                    LIMIT 100
                """, (apt["sigungu_code"], f"%{apt['bld_nm'][:4]}%")).fetchall()]

        return {"trades": trades, "rents": rents}
    finally:
        conn.close()
```

- [ ] **Step 2: 테스트**

```bash
# 아파트 상세
curl "http://localhost:8000/api/apartment/1111010100000560045" | python -m json.tool | head -30

# 거래 내역
curl "http://localhost:8000/api/apartment/1111010100000560045/trades" | python -m json.tool | head -20
```

---

## Task 4: 서버 실행 및 전체 API 통합 테스트

- [ ] **Step 1: 서버 시작**

```bash
cd web/backend
../../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: 전체 API 테스트**

```bash
# Health
curl http://localhost:8000/api/health

# 아파트 목록 (전체)
curl "http://localhost:8000/api/apartments" | python -c "import sys,json; d=json.load(sys.stdin); print(f'총: {len(d)}건')"

# 아파트 목록 (bounds)
curl "http://localhost:8000/api/apartments?sw_lat=37.5&sw_lng=126.9&ne_lat=37.6&ne_lng=127.0" | python -c "import sys,json; d=json.load(sys.stdin); print(f'bounds 내: {len(d)}건')"

# 넛지 스코어링 - 반려동물
curl -X POST "http://localhost:8000/api/nudge/score" -H "Content-Type: application/json" -d '{"nudges":["pet"],"top_n":5}'

# 넛지 스코어링 - 복수 넛지
curl -X POST "http://localhost:8000/api/nudge/score" -H "Content-Type: application/json" -d '{"nudges":["commute","cost"],"top_n":5}'

# 기본 가중치 조회
curl "http://localhost:8000/api/nudge/weights"

# 상세 정보 (첫 번째 아파트 PNU 사용)
PNU=$(curl -s "http://localhost:8000/api/apartments" | python -c "import sys,json; print(json.load(sys.stdin)[0]['pnu'])")
curl "http://localhost:8000/api/apartment/$PNU"
curl "http://localhost:8000/api/apartment/$PNU/trades"
```

- [ ] **Step 3: Swagger UI 확인**

브라우저에서 http://localhost:8000/docs 접속하여 자동 생성된 API 문서 확인.
