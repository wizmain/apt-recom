# 라이프점수 Phase 1 (1-1/1-3/1-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1-1) 배정초교 거리를 education 넛지의 1급 지표로 반영, (1-3) 실거래가 회귀(hedonic)로 점수 타당성을 최초로 정량 측정, (1-4) ML 재학습을 배치 CLI 에 편입하고 학습된 거리 감쇠 곡선을 common_code 로 연결한다.

**Architecture:** 배치(batch/) 중심. 신규 지표는 기존 `apt_facility_summary`에 pseudo-subtype `assigned_elementary` 행으로 적재해 런타임 스코어링 파이프라인을 그대로 재사용한다(백엔드 코드 변경은 scoring.py 기본 파라미터 2줄뿐). 가중치·감쇠 파라미터는 common_code(DB) 경로로 반영 — 런타임 로더가 이미 DB 우선이므로 backend 배포 없이 적용 가능(단, 모듈 캐시로 서버 재기동 필요). hedonic 은 읽기 전용 검증 배치로 리포트 파일만 생성.

**Tech Stack:** Python(psycopg2, numpy, sklearn/xgboost 기보유 — statsmodels 미설치이므로 OLS 는 numpy 직접 구현), 기존 batch 로거/커넥션 패턴.

**Spec:** `docs/analysis/2026-07-03-life-score-adequacy-review.md` §4 Phase 1 (1-1, 1-3, 1-4). 1-2 는 hedonic 결과로 대체, 1-5(UI 슬라이더)는 후속.

## Global Constraints

- 커밋은 feature 브랜치 `feature/life-score-phase1` 에만. main 직접 push 금지. push 는 사용자 요청 시에만. Conventional Commits, **AI 작업자 표기 금지**.
- Python 은 항상 루트 `.venv` (`.venv/bin/python`). 새 pip 의존성 추가 금지 (statsmodels 설치하지 말 것 — numpy OLS 사용).
- **Railway(production) DB 접속 금지** — 모든 스크립트는 dry-run 기본, `--target railway` 는 옵션만 제공하고 실행하지 않는다.
- web/backend 코드에서 batch/ import 금지 (기존 규칙). batch 에서 web/backend import 도 하지 않는다 — 공유 값은 DB(common_code) 경유.
- 하드코딩 금지 원칙: 신규 가중치/파라미터는 common_code 로. 코드 내 기본값(fallback)은 근거 주석 필수.
- fallback 발동 조건은 로그/주석으로 남긴다 (프로젝트 fallback 규칙).
- 배치 실행 검증: 로컬 DB (`DATABASE_URL`). 테스트: `.venv/bin/python web/backend/tests/test_core.py` (백엔드 8000 이 최신 코드로 기동 중이어야 함 — `--reload` 로 이미 기동됨).
- 명명: snake_case, 의미 접두어. subtype 명은 `assigned_elementary` 로 통일.
- 실측 기준값(플랜 작성 시점): school_zones 28,966행/아파트 40,619 (71%), 배정초교명 정규화 매칭 97%(공동배정 3,216행 제외 기준), facilities school POI 11,440건.

## File Structure

| 구분 | 경로 | 책임 |
|------|------|------|
| Create | `batch/quarterly/assigned_school.py` | 배정초교 매칭·거리 계산 → apt_facility_summary upsert (1-1) |
| Create | `scripts/update_education_weights.py` | education 넛지 가중치 재배분 upsert (1-1) |
| Create | `batch/ml/hedonic_validation.py` | 실거래가 OLS 검증 리포트 생성 (1-3) |
| Create | `batch/ml/apply_curves.py` | distance_curves.json → common_code facility_decay upsert (1-4) |
| Modify | `batch/run.py` | quarterly 에 assigned_school 단계 추가 + `--type ml` 신설 (1-1, 1-4) |
| Modify | `web/backend/services/scoring.py` | assigned_elementary 기본 decay/density 등록 (2줄+주석) |
| Modify | `web/backend/tests/test_core.py` | Phase 1 회귀 테스트 추가 |

데이터 흐름: facilities(school POI) + school_zones → [assigned_school.py] → apt_facility_summary('assigned_elementary') → 기존 nudge.py/scoring.py 가 그대로 소비. trade_history → [hedonic_validation.py] → models/hedonic_report.json + docs/analysis 리포트. train_scoring 산출물 → [apply_curves.py/update_weights.py] → common_code → 런타임 로더(DB 우선, 기존 코드 무변경).

---

### Task 1: 배정초교 거리 배치 모듈 (assigned_elementary)

**Files:**
- Create: `batch/quarterly/assigned_school.py`
- Modify: `batch/run.py` (run_quarterly 4단계 추가)
- Modify: `web/backend/services/scoring.py` (_DEFAULT_FACILITY_DECAY / _DEFAULT_DENSITY_FACTOR 에 assigned_elementary)

**Interfaces:**
- Consumes: `apt_facility_summary(pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km)` PK(pnu, facility_subtype) — database.py:224. school_zones(pnu, elementary_school_name). facilities(facility_subtype='school', name, lat, lng). batch/db.get_connection, batch/logger.setup_logger.
- Produces: `recalc_assigned_school(conn, logger) -> dict` (반환: {"matched": n, "fallback": n, "total": n}) — Task 5 검증과 run.py 가 소비. summary 에 subtype `assigned_elementary` 행 (아파트당 1행, 커버리지 100%).

**설계 요점 (구현 코드에 그대로 반영):**
- 매칭 규칙: 배정초교명 정규화(`~초` → `~초등학교`) 후 facilities school 과 동명 후보 수집 → **동명 다수 시 아파트에서 가장 가까운 것 선택**, 단 3km 초과면 오매칭으로 보고 매칭 실패 처리.
- fallback(발동 조건 로그 필수): (a) school_zones 미보유(29%), (b) 공동배정(`공동` 포함) 등 매칭 실패 → 기존 summary 의 school 최근접 거리를 프록시로 사용. 프록시도 없으면 행 생략(런타임 4a/partial 규칙 적용).
- count_1km 는 {0,1}: 배정초교가 1km 이내면 1. density factor 100 과 결합해 "도보권 보너스" 역할 (밀도 개념 부적합한 단일 시설 지표).

- [ ] **Step 1: 실패하는 테스트 작성** — `web/backend/tests/test_core.py` 의 Phase 0 섹션 아래에 추가:

```python
# ============================================================
# 라이프점수 Phase 1 회귀 테스트 (2026-07-03)
# ============================================================

@test("Phase1: apt_facility_summary 에 assigned_elementary 가 전 아파트 커버")
def test_assigned_elementary_coverage():
    from database import DictConnection
    conn = DictConnection()
    total = conn.execute("SELECT COUNT(*) AS c FROM apartments").fetchone()["c"]
    covered = conn.execute(
        "SELECT COUNT(*) AS c FROM apt_facility_summary WHERE facility_subtype = 'assigned_elementary'"
    ).fetchone()["c"]
    conn.close()
    # fallback 포함 95% 이상 커버 (school 프록시도 없는 극소수 예외 허용)
    assert covered >= total * 0.95, f"assigned_elementary 커버리지 부족: {covered}/{total}"


@test("Phase1: assigned_elementary 거리가 상식 범위(0~20km)")
def test_assigned_elementary_distance_sane():
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute(
        """SELECT MIN(nearest_distance_m) AS mn, MAX(nearest_distance_m) AS mx,
                  COUNT(*) FILTER (WHERE nearest_distance_m IS NULL) AS nulls
           FROM apt_facility_summary WHERE facility_subtype = 'assigned_elementary'"""
    ).fetchone()
    conn.close()
    assert row["nulls"] == 0, f"거리 NULL {row['nulls']}건"
    assert row["mn"] is not None and row["mn"] >= 0, f"음수 거리: {row['mn']}"
    assert row["mx"] <= 20000, f"비상식적 거리: {row['mx']}m"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom && .venv/bin/python web/backend/tests/test_core.py 2>&1 | grep "Phase1"
```
Expected: 2건 FAIL (assigned_elementary 행 0건)

- [ ] **Step 3: 배치 모듈 구현** — `batch/quarterly/assigned_school.py` 생성:

```python
"""배정초등학교 거리 계산 → apt_facility_summary('assigned_elementary') 적재.

education 넛지의 1급 지표(1-1). school_zones 의 배정초교명을 facilities 의
school POI 와 매칭해 아파트→배정초교 거리를 계산한다.

매칭 규칙:
- 배정명 정규화: '~초' → '~초등학교' (예: '대구매호초' → '대구매호초등학교')
- 동명 학교 다수 시 아파트에서 가장 가까운 후보 선택 (3km 초과면 오매칭으로 간주)
- 실측(2026-07): 정규화 정확 일치 97% (공동배정 표기 제외 기준)

fallback (발동 조건을 반환 통계와 로그로 남김):
- school_zones 미보유(전체의 ~29%) 또는 매칭 실패(공동배정 '~공동(일방)' 표기 등)
  → 기존 summary 의 최근접 school 거리를 프록시로 사용.
  근거: 최근접 초등학교가 배정교인 경우가 다수 — 정확도보다 커버리지 우선,
  Phase 2(학교알리미 학교코드 좌표)에서 정밀화 예정.
- 프록시(school 행)도 없으면 행을 만들지 않는다 (런타임 결측 정책에 위임).

사용법:
  .venv/bin/python -m batch.quarterly.assigned_school            # 단독 실행
  (batch/run.py --type quarterly 의 4단계로도 호출됨)
"""

import math

from batch.db import get_connection
from batch.logger import setup_logger

SUBTYPE = "assigned_elementary"
# 동명 학교 후보 중 이 거리(m)를 넘는 최근접 후보는 오매칭으로 간주
MATCH_MAX_DISTANCE_M = 3000.0
EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _normalize_school_name(name: str) -> str:
    """배정초교 축약명 → facilities 정식명 ('~초' → '~초등학교')."""
    name = name.strip()
    if name.endswith("초"):
        return name + "등학교"
    return name


def recalc_assigned_school(conn, logger) -> dict:
    """배정초교 거리 재계산. 반환: {"matched": n, "fallback": n, "total": n}."""
    cur = conn.cursor()

    # 1. school POI 인덱스 (이름 → [(lat, lng), ...])
    cur.execute(
        "SELECT name, lat, lng FROM facilities "
        "WHERE facility_subtype = 'school' AND lat IS NOT NULL AND lng IS NOT NULL"
    )
    school_index: dict[str, list[tuple[float, float]]] = {}
    for name, lat, lng in cur.fetchall():
        school_index.setdefault(name, []).append((lat, lng))
    logger.info(f"school POI 인덱스: {len(school_index):,}개 이름")

    # 2. 아파트 좌표 + 배정초교명 + 최근접 school 거리(프록시용)
    cur.execute(
        """
        SELECT a.pnu, a.lat, a.lng, z.elementary_school_name, s.nearest_distance_m
        FROM apartments a
        LEFT JOIN school_zones z ON a.pnu = z.pnu
        LEFT JOIN apt_facility_summary s
               ON a.pnu = s.pnu AND s.facility_subtype = 'school'
        WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL
        """
    )
    rows = cur.fetchall()

    matched = 0
    fallback = 0
    skipped = 0
    upsert_rows: list[tuple] = []

    for pnu, lat, lng, zone_name, nearest_school_m in rows:
        distance_m: float | None = None

        if zone_name:
            candidates = school_index.get(_normalize_school_name(zone_name))
            if candidates:
                best = min(_haversine_m(lat, lng, c[0], c[1]) for c in candidates)
                if best <= MATCH_MAX_DISTANCE_M:
                    distance_m = best
                    matched += 1

        if distance_m is None:
            # fallback: 최근접 school 거리 프록시 (발동 조건: 배정정보 미보유/매칭 실패)
            if nearest_school_m is not None:
                distance_m = float(nearest_school_m)
                fallback += 1
            else:
                skipped += 1
                continue

        within_1km = 1 if distance_m <= 1000.0 else 0
        upsert_rows.append((pnu, SUBTYPE, round(distance_m, 1), within_1km, within_1km, within_1km))

    # 3. upsert (PK: pnu, facility_subtype)
    from psycopg2.extras import execute_values

    execute_values(
        cur,
        """
        INSERT INTO apt_facility_summary
            (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km)
        VALUES %s
        ON CONFLICT (pnu, facility_subtype) DO UPDATE SET
            nearest_distance_m = EXCLUDED.nearest_distance_m,
            count_1km = EXCLUDED.count_1km,
            count_3km = EXCLUDED.count_3km,
            count_5km = EXCLUDED.count_5km
        """,
        upsert_rows,
        page_size=1000,
    )
    conn.commit()

    total = len(upsert_rows)
    logger.info(
        f"assigned_elementary 적재 {total:,}건 "
        f"(배정 매칭 {matched:,} / school 프록시 fallback {fallback:,} / 생략 {skipped:,})"
    )
    return {"matched": matched, "fallback": fallback, "total": total}


def main() -> None:
    logger = setup_logger("assigned_school")
    conn = get_connection()
    try:
        recalc_assigned_school(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: run.py quarterly 에 단계 추가** — `run_quarterly` 의 "3. 집계 재계산" 블록 뒤에:

```python
        # 4. 배정초교 거리 재계산 (education 넛지 1급 지표 — recalc_summary 의
        #    school 최근접 거리를 fallback 프록시로 쓰므로 반드시 3단계 이후 실행)
        from batch.quarterly.assigned_school import recalc_assigned_school
        t0 = time.time()
        stats = recalc_assigned_school(conn, logger)
        result.record("배정초교 거리 재계산", "success", rows=stats["total"], duration=time.time() - t0)
```

- [ ] **Step 5: scoring.py 기본 파라미터 등록** — `_DEFAULT_FACILITY_DECAY` dict 에 항목 추가:

```python
    "assigned_elementary": 400,  # 배정초교 — school 과 동일 감쇠 (도보 통학 거리 민감)
```

`_DEFAULT_DENSITY_FACTOR` dict 에 항목 추가:

```python
    # 배정초교는 단일 시설이라 밀도 개념이 없음 — count_1km∈{0,1} 을
    # "1km 도보권 보너스"(0 또는 100)로 사용 (배치가 0/1 로 적재)
    "assigned_elementary": 100,
```

- [ ] **Step 6: 배치 실행 + 테스트 통과 확인**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
.venv/bin/python -m batch.quarterly.assigned_school
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "Phase1|결과:"
```
Expected: 적재 로그(매칭/ fallback 통계 — 매칭 비율 60% 이상 기대), Phase1 테스트 2건 PASS. 전체 결과에서 기존 실패 2건(대시보드 드리프트) 외 신규 실패 없음.

- [ ] **Step 7: Commit**

```bash
git add batch/quarterly/assigned_school.py batch/run.py web/backend/services/scoring.py web/backend/tests/test_core.py
git commit -m "feat(scoring): 배정초교 거리 지표(assigned_elementary) 배치 추가 (Phase 1-1)"
```

---

### Task 2: education 넛지 가중치 재배분

**Files:**
- Create: `scripts/update_education_weights.py`
- Test: `web/backend/tests/test_core.py` (추가)

**Interfaces:**
- Consumes: common_code `nudge_weight` 그룹 (code=`education:<subtype>`, name=subtype, extra=가중치 문자열 — batch/ml/update_weights.py:39-51 파싱 규약). Task 1 의 assigned_elementary 데이터.
- Produces: education 가중치 5종 upsert. 스코어링 런타임은 재기동 시 자동 반영(_load_nudge_weights 캐시).

**가중치 설계 (문서화 필수 — 스크립트 docstring 에 포함):**
| subtype | 기존 | 신규 | 근거 |
|---|---|---|---|
| assigned_elementary | — | 0.30 | 학군 넛지의 1급 지표 (실제 배정교 접근성) |
| school | 0.296 | 0.15 | 일반 학교 밀도는 보조 지표로 강등 |
| kindergarten | 0.253 | 0.20 | 유지(소폭 조정) |
| library | 0.251 | 0.15 | ML 인공물 의심 과대가중 완화 (진단 보고서 §3.4 유사 논리) |
| park | 0.200 | 0.20 | 유지 |
합 = 1.00. 이 초기값은 hedonic(Task 3) 결과로 재조정 가능 — 근거 기록이 목적.

- [ ] **Step 1: 실패하는 테스트 추가** — test_core.py Phase 1 섹션에:

```python
@test("Phase1: education 넛지에 assigned_elementary 가중치 반영")
def test_education_weights_include_assigned():
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute(
        "SELECT name, extra FROM common_code WHERE group_id = 'nudge_weight' AND code LIKE 'education:%'"
    ).fetchall()
    conn.close()
    weights = {r["name"]: float(r["extra"]) for r in rows}
    assert "assigned_elementary" in weights, f"assigned_elementary 없음: {sorted(weights)}"
    assert weights["assigned_elementary"] >= 0.25, f"가중치 과소: {weights['assigned_elementary']}"
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.02, f"가중치 합 이탈: {total}"


@test("Phase1: education 스코어 응답의 top_contributors 에 assigned_elementary 등장 가능")
def test_education_score_uses_assigned():
    import requests
    resp = requests.post(
        "http://localhost:8000/api/nudge/score",
        json={"nudges": ["education"], "top_n": 10, "sigungu_code": "11680"},
        timeout=30,
    )
    assert resp.status_code == 200, f"nudge/score 에러: {resp.status_code}"
    data = resp.json()
    assert len(data) > 0, "결과 없음"
    subtypes = {
        c["subtype"] for r in data for c in r.get("top_contributors", [])
    }
    assert "assigned_elementary" in subtypes, f"기여 시설에 assigned_elementary 없음: {sorted(subtypes)}"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep "Phase1"
```
Expected: Task 1 의 2건 PASS + 신규 2건 FAIL

- [ ] **Step 3: 가중치 스크립트 구현** — `scripts/update_education_weights.py` 생성 (연결/CLI 패턴은 `scripts/seed_explore_presets.py` 준용):

```python
"""education 넛지 가중치 재배분 — 배정초교(assigned_elementary) 1급 지표 반영 (Phase 1-1).

| subtype             | 기존  | 신규 | 근거                                        |
|---------------------|-------|------|---------------------------------------------|
| assigned_elementary | —     | 0.30 | 학군 넛지의 1급 지표 (실제 배정교 접근성)   |
| school              | 0.296 | 0.15 | 일반 학교 밀도는 보조 지표로 강등           |
| kindergarten        | 0.253 | 0.20 | 유지(소폭 조정)                             |
| library             | 0.251 | 0.15 | 과대가중 완화 (진단 보고서 §3.4 유사 논리)  |
| park                | 0.200 | 0.20 | 유지                                        |

초기값은 전문가 판단 — hedonic 검증(batch/ml/hedonic_validation.py) 결과로
재조정한다. 적용 후 백엔드 재기동 필요 (_load_nudge_weights 모듈 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_education_weights.py
  .venv/bin/python scripts/update_education_weights.py --apply
  .venv/bin/python scripts/update_education_weights.py --target railway --apply
    ⚠️ production 쓰기 — 사용자가 직접 실행한다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

GROUP = "nudge_weight"
NUDGE = "education"

EDUCATION_WEIGHTS: dict[str, float] = {
    "assigned_elementary": 0.30,
    "school": 0.15,
    "kindergarten": 0.20,
    "library": 0.15,
    "park": 0.20,
}

UPSERT_SQL = """
    INSERT INTO common_code (group_id, code, name, extra, sort_order)
    VALUES (%s, %s, %s, %s, 0)
    ON CONFLICT (group_id, code) DO UPDATE SET
        name = EXCLUDED.name, extra = EXCLUDED.extra
"""


def get_conn(target: str):
    env_key = "RAILWAY_DATABASE_URL" if target == "railway" else "DATABASE_URL"
    url = os.getenv(env_key)
    if not url:
        raise SystemExit(f"{env_key} 미설정 (.env 확인)")
    return psycopg2.connect(url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    total = sum(EDUCATION_WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        raise SystemExit(f"가중치 합이 1.0 이 아님: {total}")

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT code, extra FROM common_code WHERE group_id = %s AND code LIKE %s",
        [GROUP, f"{NUDGE}:%"],
    )
    current = dict(cur.fetchall())
    print(f"현재 education 가중치: {current}")

    for subtype, weight in EDUCATION_WEIGHTS.items():
        code = f"{NUDGE}:{subtype}"
        print(f"{'APPLY' if args.apply else 'DRY-RUN'} upsert: {code} = {weight}")
        if args.apply:
            cur.execute(UPSERT_SQL, [GROUP, code, subtype, str(weight)])

    # 신규 세트에 없는 기존 education:* 는 제거 (가중치 합 1.0 유지)
    stale = [c for c in current if c.split(":", 1)[1] not in EDUCATION_WEIGHTS]
    for code in stale:
        print(f"{'APPLY' if args.apply else 'DRY-RUN'} delete stale: {code}")
        if args.apply:
            cur.execute(
                "DELETE FROM common_code WHERE group_id = %s AND code = %s",
                [GROUP, code],
            )

    if args.apply:
        conn.commit()
        print(f"✅ {args.target} 반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 로컬 적용 + 백엔드 재기동 + 테스트 통과 확인**

```bash
.venv/bin/python scripts/update_education_weights.py            # dry-run 확인
.venv/bin/python scripts/update_education_weights.py --apply
# --reload 기동 상태라도 DB 값 변경은 파일 변경이 아니므로 재기동 필요:
lsof -ti :8000 | xargs kill 2>/dev/null; sleep 2
cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000 >/dev/null 2>&1 &
sleep 5; cd ../..
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "Phase1|결과:"
```
Expected: Phase1 테스트 4건 PASS

- [ ] **Step 5: 반영 전후 education 프로브 기록** (report 용 — 강남/청주/무안 top10 max/min 비교):

```bash
.venv/bin/python /private/tmp/claude-501/-Users-wizmain-Documents-workspace-apt-recom/af0e5863-55e2-416d-8a3d-7796a001ff97/scratchpad/probe_score_bias.py
```
Expected: education 행 변화 확인 (배정 매칭 데이터가 반영된 순위/점수)

- [ ] **Step 6: Commit**

```bash
git add scripts/update_education_weights.py web/backend/tests/test_core.py
git commit -m "feat(scoring): education 가중치 재배분 — 배정초교 0.30 반영 (Phase 1-1)"
```

---

### Task 3: hedonic 검증 배치 (1-3)

**Files:**
- Create: `batch/ml/hedonic_validation.py`

**Interfaces:**
- Consumes: trade_history/trade_apt_mapping(㎡당 가격 라벨 — batch/ml/train_scoring.py:35-43 과 동일 쿼리 패턴), apartments(통제변수: 연식/세대수/층수 + sigungu_code), apt_facility_summary(subtype 별 nearest_distance_m, count_1km), common_code nudge_weight (가중치 비교용).
- Produces: `models/hedonic_report.json` + `docs/analysis/hedonic-validation-latest.md` (재실행 시 덮어씀 — "latest" 파일명). CLI: `--self-test` (합성 데이터 OLS 검증), 기본 실행은 읽기 전용(DB 쓰기 없음).

**방법 (구현 코드에 반영):**
- 라벨: `ln(price_m2)` (아파트별 최근 2년 평균 ㎡당 매매가).
- 피처: subtype 별 `ln(1 + nearest_distance_m)` + `count_1km`, 통제: 연식/세대수/최고층/평균면적.
- 시군구 고정효과: y·X 를 시군구별 평균으로 demean (within estimator) — 시군구 간 가격 수준 차이를 제거하고 "같은 시군구 안에서 접근성이 가격에 주는 효과"만 추정.
- OLS: numpy 폐형해 `β=(XᵀX)⁻¹Xᵀy`, `se=√(σ²(XᵀX)⁻¹_jj)`, t=β/se. 다중공선성 참고용으로 피처 상관 상위쌍 출력.
- 산출: (a) 시설별 거리 계수(음수=가까울수록 비쌈)와 t, (b) |t| 정규화 "시장 중요도" vs 현행 넛지 가중치 비교표, (c) R².

- [ ] **Step 1: self-test 부터 작성/실행 (RED→GREEN 을 셀프테스트로 수행)** — 모듈에 `--self-test` 포함하여 생성:

```python
"""Hedonic 검증 배치 — 실거래가 회귀로 라이프점수 지표의 시장 타당성 측정 (Phase 1-3).

ln(㎡당가격) ~ 시설 접근성(ln 거리, 1km 밀도) + 통제(연식/세대/층/면적),
시군구 고정효과(within demean). 결과는 리포트 파일로만 출력 (DB 쓰기 없음).

산출물:
- models/hedonic_report.json          — 계수/t/R²/가중치 비교 (기계용)
- docs/analysis/hedonic-validation-latest.md — 사람용 요약 (재실행 시 갱신)

해석 가이드:
- dist_* 계수 음수 = 해당 시설에 가까울수록 ㎡당 가격이 높음 (시장이 프리미엄 지불)
- market_importance = |t| 정규화 — 현행 nudge_weight 와 나란히 비교해
  가중치 조정(1-2 대체)의 근거로 사용한다.

사용법:
  .venv/bin/python -m batch.ml.hedonic_validation
  .venv/bin/python -m batch.ml.hedonic_validation --self-test   # 합성 데이터 OLS 검증
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from batch.db import get_connection
from batch.logger import setup_logger

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "models" / "hedonic_report.json"
REPORT_MD = REPO_ROOT / "docs" / "analysis" / "hedonic-validation-latest.md"

# 접근성 피처로 쓸 subtype (apt_facility_summary 실보유 기준)
FEATURE_SUBTYPES = [
    "subway", "bus", "school", "assigned_elementary", "kindergarten",
    "hospital", "pharmacy", "mart", "convenience_store", "park",
    "library", "pet_facility", "animal_hospital", "cctv", "police", "fire_station",
]
MIN_SAMPLES = 3000  # 이보다 적으면 회귀 신뢰 불가로 중단


def ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS 폐형해. 반환: (beta, t_stats, r2)."""
    xtx = x.T @ x
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    dof = max(len(y) - x.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, 1e-12, None))
    t_stats = beta / se
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    r2 = 1.0 - float(resid @ resid) / ss_tot
    return beta, t_stats, r2


def self_test() -> None:
    """합성 데이터로 OLS 가 알려진 계수를 복원하는지 검증."""
    rng = np.random.default_rng(42)
    n = 5000
    x = rng.normal(size=(n, 3))
    true_beta = np.array([0.5, -1.2, 0.0])
    y = x @ true_beta + rng.normal(scale=0.1, size=n)
    beta, t_stats, r2 = ols(y, x)
    assert np.allclose(beta, true_beta, atol=0.02), f"계수 복원 실패: {beta}"
    assert abs(t_stats[2]) < 3, f"무효 피처의 t 가 과대: {t_stats[2]}"
    assert r2 > 0.95, f"R² 과소: {r2}"
    print("self-test PASS: beta=", np.round(beta, 3), "r2=", round(r2, 4))


def load_dataset(conn, logger):
    """라벨/피처/통제/시군구 로드. 반환: (y, X, feature_names, sgg_codes)."""
    cur = conn.cursor()

    cur.execute(
        """
        SELECT m.pnu, AVG(t.deal_amount / NULLIF(t.exclu_use_ar, 0)) AS price_m2
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
          AND make_date(t.deal_year, t.deal_month, 1) >= CURRENT_DATE - INTERVAL '2 years'
        GROUP BY m.pnu
        """
    )
    price_map = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] and r[1] > 0}
    logger.info(f"가격 라벨(최근 2년): {len(price_map):,}건")

    cur.execute(
        """
        SELECT a.pnu, a.sigungu_code, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, 60)
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.lat IS NOT NULL
        """
    )
    controls = {}
    for pnu, sgg, hhld, floor, apr, area in cur.fetchall():
        try:
            age = 2026 - int(str(apr)[:4]) if apr else 20
        except (ValueError, TypeError):
            age = 20
        controls[pnu] = (sgg or "", age, hhld or 100, floor or 15, float(area or 60))

    cur.execute(
        "SELECT pnu, facility_subtype, nearest_distance_m, count_1km "
        "FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
        [FEATURE_SUBTYPES],
    )
    feats: dict[str, dict[str, tuple]] = {}
    for pnu, subtype, dist, cnt in cur.fetchall():
        feats.setdefault(pnu, {})[subtype] = (dist, cnt)

    feature_names = []
    for s in FEATURE_SUBTYPES:
        feature_names += [f"dist_{s}", f"cnt1km_{s}"]
    feature_names += ["age", "hhld", "floor", "area"]

    rows_y, rows_x, sggs = [], [], []
    for pnu, price in price_map.items():
        if pnu not in controls:
            continue
        sgg, age, hhld, floor, area = controls[pnu]
        f = feats.get(pnu, {})
        xrow = []
        for s in FEATURE_SUBTYPES:
            dist, cnt = f.get(s, (None, 0))
            # 결측 거리 = max 취급(멀다) — ln(1+20km). 결측 편향은 Phase 0 정책과
            # 별개로, 회귀에서는 "없음=매우 멂"이 보수적.
            xrow.append(math.log1p(dist if dist is not None else 20000.0))
            xrow.append(float(cnt or 0))
        xrow += [float(age), float(hhld), float(floor), float(area)]
        rows_y.append(math.log(price))
        rows_x.append(xrow)
        sggs.append(sgg[:5])

    return np.array(rows_y), np.array(rows_x), feature_names, np.array(sggs)


def demean_by_group(y: np.ndarray, x: np.ndarray, groups: np.ndarray):
    """시군구 within demean (고정효과)."""
    y_out = y.astype(float).copy()
    x_out = x.astype(float).copy()
    for g in np.unique(groups):
        idx = groups == g
        y_out[idx] -= y_out[idx].mean()
        x_out[idx] -= x_out[idx].mean(axis=0)
    return y_out, x_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    logger = setup_logger("hedonic_validation")
    conn = get_connection()
    try:
        y, x, names, sggs = load_dataset(conn, logger)
    finally:
        conn.close()

    if len(y) < MIN_SAMPLES:
        raise SystemExit(f"표본 부족: {len(y)} < {MIN_SAMPLES}")
    logger.info(f"회귀 표본: {len(y):,}건, 피처 {len(names)}개")

    y_d, x_d = demean_by_group(y, x, sggs)
    beta, t_stats, r2 = ols(y_d, x_d)

    dist_idx = [i for i, n in enumerate(names) if n.startswith("dist_")]
    importance_raw = {names[i]: abs(float(t_stats[i])) for i in dist_idx}
    total_imp = sum(importance_raw.values()) or 1.0
    market_importance = {
        k.removeprefix("dist_"): round(v / total_imp, 4)
        for k, v in importance_raw.items()
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": int(len(y)),
        "r2_within": round(r2, 4),
        "coefficients": {
            names[i]: {"beta": round(float(beta[i]), 6), "t": round(float(t_stats[i]), 2)}
            for i in range(len(names))
        },
        "market_importance_by_subtype": market_importance,
    }
    REPORT_JSON.parent.mkdir(exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(f"리포트 저장: {REPORT_JSON}")

    md = ["# Hedonic 검증 리포트 (자동 생성)", "",
          f"- 생성: {report['generated_at']}",
          f"- 표본: {report['samples']:,} (아파트 단위, 최근 2년 평균 ㎡당가)",
          f"- within R² (시군구 고정효과): {report['r2_within']}", "",
          "## 거리 계수 (음수 = 가까울수록 비쌈)", "",
          "| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |", "|---|---|---|---|"]
    for s in FEATURE_SUBTYPES:
        c = report["coefficients"].get(f"dist_{s}")
        if c:
            md.append(f"| {s} | {c['beta']} | {c['t']} | {market_importance.get(s, 0)} |")
    md += ["", "> 해석: |t|≥2 면 유의. 시장 중요도는 넛지 가중치 조정의 참고 근거 (1-2 대체).", ""]
    REPORT_MD.write_text("\n".join(md))
    logger.info(f"요약 저장: {REPORT_MD}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: self-test 실행 (GREEN 확인)**

```bash
.venv/bin/python -m batch.ml.hedonic_validation --self-test
```
Expected: `self-test PASS: beta= [0.5 -1.2 0.] r2= 0.99x`

- [ ] **Step 3: 실 데이터 실행**

```bash
.venv/bin/python -m batch.ml.hedonic_validation
```
Expected: 표본 수 로그(수천~수만), `models/hedonic_report.json` + `docs/analysis/hedonic-validation-latest.md` 생성. **리포트의 핵심 수치(within R², subway/school 계수 부호)를 report 파일에 기록할 것** — subway/mart 등 핵심 시설의 거리 계수가 음수(가까울수록 비쌈)로 나오는지가 타당성 신호.

- [ ] **Step 4: Commit**

```bash
git add batch/ml/hedonic_validation.py docs/analysis/hedonic-validation-latest.md
git commit -m "feat(ml): hedonic 검증 배치 — 실거래가 회귀로 점수 타당성 측정 (Phase 1-3)"
```
(models/*.json 은 기존 .gitignore 정책 확인 후 — models/ 가 ignore 면 json 은 커밋하지 않음)

---

### Task 4: ML 재학습 파이프라인 편입 + 감쇠 곡선 DB 연결 (1-4)

**Files:**
- Create: `batch/ml/apply_curves.py`
- Modify: `batch/run.py` (`--type ml` 신설)

**Interfaces:**
- Consumes: `models/distance_curves.json` (train_scoring 산출 — subtype 별 {distances[], scores[]}), common_code `facility_decay_{metro|major_city|provincial}` 그룹 (scoring.py `_load_facility_decay_by_profile` 이 DB 우선 조회 — scoring.py:166-190), `_DECAY_MULTIPLIER` {metro 1.0, major_city 1.3, provincial 1.8} (scoring.py:116).
- Produces: `fit_decay_from_curve(distances, scores, max_d) -> float` (곡선→로그감쇠 decay 파라미터 적합), `apply_curves(conn, logger, apply: bool) -> dict`. run.py `--type ml [--apply]`.

**설계 요점:**
- 런타임은 파라메트릭 로그감쇠(`100·(1−ln(1+d/decay)/ln(1+max_d/decay))`)만 지원 → PDP 곡선을 그대로 쓰지 않고 **decay 1개 파라미터로 최소자승 적합** (grid search 50~3000, step 25 — 결정적/의존성 없음).
- ML 곡선 품질 가드: 적합 RMSE 가 20 점을 넘는 subtype 은 skip (곡선이 로그감쇠 형태가 아님 — 억지 반영 방지, 로그 남김).
- metro 값 적합 후 프로필 배율(×1.3/×1.8)로 major_city/provincial 산출 — 기존 fallback 배율 정책과 일치.
- run.py `--type ml`: train_scoring → hedonic_validation → (apply 시) apply_curves + update_weights 순. **기본 dry-run** (리포트만) — 가중치·감쇠의 무단 변경 방지. `--apply` 명시 시에만 common_code 반영.

- [ ] **Step 1: 실패하는 테스트 추가** — test_core.py Phase 1 섹션에:

```python
@test("Phase1: apply_curves 의 decay 적합이 합성 로그감쇠 곡선을 복원")
def test_fit_decay_roundtrip():
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
    import math
    from batch.ml.apply_curves import fit_decay_from_curve

    true_decay, max_d = 500.0, 3000.0
    distances = [i * 30.0 for i in range(100)]
    scores = [
        100.0 * max(0.0, 1.0 - math.log(1 + d / true_decay) / math.log(1 + max_d / true_decay))
        for d in distances
    ]
    fitted = fit_decay_from_curve(distances, scores, max_d)
    assert abs(fitted - true_decay) <= 25.0, f"decay 복원 실패: {fitted} (기대 {true_decay})"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep "Phase1"
```
Expected: 신규 1건 FAIL (모듈 없음)

- [ ] **Step 3: apply_curves 구현** — `batch/ml/apply_curves.py` 생성:

```python
"""ML 학습 거리 곡선(distance_curves.json) → common_code facility_decay 반영 (Phase 1-4).

배포 제약: Railway 백엔드는 web/backend/ 만 배포되어 models/ 파일에 접근할 수
없다 → 런타임 반영 경로는 파일이 아니라 common_code(DB). scoring.py 의
_load_facility_decay_by_profile 이 facility_decay_{profile} 그룹을 우선
조회하므로, 여기서 upsert 하면 백엔드 재기동 시 적용된다.

방법: PDP 곡선을 런타임 파라메트릭 로그감쇠(decay 1개)로 최소자승 적합.
- grid search (50~3000, step 25) — 의존성 없이 결정적.
- 적합 RMSE > 20점이면 skip (곡선이 로그감쇠 형태가 아님 — 억지 반영 방지).
- metro 적합값에 기존 프로필 배율(×1.3 / ×1.8)을 적용해 3개 프로필 산출.

사용법:
  .venv/bin/python -m batch.ml.apply_curves            # dry-run
  .venv/bin/python -m batch.ml.apply_curves --apply
  (batch/run.py --type ml 에서도 호출됨)
"""

import argparse
import json
import math
from pathlib import Path

from batch.db import get_connection
from batch.logger import setup_logger

REPO_ROOT = Path(__file__).resolve().parents[2]
CURVES_PATH = REPO_ROOT / "models" / "distance_curves.json"

RMSE_SKIP_THRESHOLD = 20.0
DECAY_GRID = [float(d) for d in range(50, 3001, 25)]
PROFILE_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.8}
DEFAULT_MAX_DISTANCE_M = 3000.0


def _log_decay_score(d: float, decay: float, max_d: float) -> float:
    if d >= max_d:
        return 0.0
    return 100.0 * max(0.0, 1.0 - math.log(1 + d / decay) / math.log(1 + max_d / decay))


def fit_decay_from_curve(
    distances: list[float], scores: list[float], max_d: float = DEFAULT_MAX_DISTANCE_M
) -> float:
    """PDP 곡선 → 로그감쇠 decay 최소자승 적합 (RMSE 최소 grid 탐색)."""
    # 곡선 점수를 0~100 으로 정규화 (PDP 원점수는 임의 스케일)
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    norm = [(s - lo) / span * 100.0 for s in scores]

    best_decay, best_rmse = DECAY_GRID[0], float("inf")
    for decay in DECAY_GRID:
        se = 0.0
        for d, s in zip(distances, norm):
            se += (_log_decay_score(d, decay, max_d) - s) ** 2
        rmse = math.sqrt(se / len(norm))
        if rmse < best_rmse:
            best_decay, best_rmse = decay, rmse
    fit_decay_from_curve.last_rmse = best_rmse  # 호출부 skip 판단용
    return best_decay


def apply_curves(conn, logger, apply: bool = False) -> dict:
    """곡선 적합 → facility_decay_{profile} upsert. 반환 {"applied": n, "skipped": n}."""
    if not CURVES_PATH.exists():
        logger.error(f"곡선 파일 없음: {CURVES_PATH} — 먼저 train_scoring 실행")
        return {"applied": 0, "skipped": 0}

    curves = json.loads(CURVES_PATH.read_text())
    cur = conn.cursor()
    applied = skipped = 0

    for subtype, curve in curves.items():
        decay = fit_decay_from_curve(curve["distances"], curve["scores"])
        rmse = fit_decay_from_curve.last_rmse
        if rmse > RMSE_SKIP_THRESHOLD:
            logger.warning(f"  {subtype:20s} skip — 적합 RMSE {rmse:.1f} > {RMSE_SKIP_THRESHOLD}")
            skipped += 1
            continue
        for profile, mult in PROFILE_MULTIPLIER.items():
            value = round(decay * mult)
            logger.info(
                f"  {'APPLY' if apply else 'DRY-RUN'} facility_decay_{profile}.{subtype} = {value} (rmse {rmse:.1f})"
            )
            if apply:
                cur.execute(
                    """
                    INSERT INTO common_code (group_id, code, name, extra, sort_order)
                    VALUES (%s, %s, %s, '', 0)
                    ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name
                    """,
                    [f"facility_decay_{profile}", subtype, str(value)],
                )
        applied += 1

    if apply:
        conn.commit()
        logger.info(f"✅ 반영 완료: {applied} subtype × 3 profiles — 백엔드 재기동 필요 (decay 캐시)")
    else:
        logger.info(f"dry-run: {applied} subtype 반영 예정, {skipped} skip")
    return {"applied": applied, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="common_code 반영 (기본 dry-run)")
    args = parser.parse_args()
    logger = setup_logger("apply_curves")
    conn = get_connection()
    try:
        apply_curves(conn, logger, apply=args.apply)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

주의: `_load_facility_decay_by_profile`(scoring.py:180-181)은 `float(r["name"])` 으로 **name 컬럼**에서 값을 읽는다 — upsert 시 값을 name 에 넣는 위 코드가 규약과 일치하는지 구현 시 재확인할 것.

- [ ] **Step 4: run.py 에 `--type ml` 추가** — `run_backfill` 함수 아래에 추가:

```python
def run_ml(args, logger, result):
    """ML 재학습 파이프라인 (Phase 1-4).

    기본 dry-run: 학습·리포트만 수행하고 common_code 는 건드리지 않는다.
    --apply 명시 시에만 감쇠(decay)·넛지 가중치를 DB 에 반영한다 —
    점수 체계의 무단 변동을 막기 위한 안전장치.
    """
    import subprocess

    steps = [
        ("ML 학습 (train_scoring)", [sys.executable, "-m", "batch.ml.train_scoring"]),
        ("Hedonic 검증", [sys.executable, "-m", "batch.ml.hedonic_validation"]),
    ]
    apply_flag = getattr(args, "apply", False)
    curves_cmd = [sys.executable, "-m", "batch.ml.apply_curves"]
    weights_cmd = [sys.executable, "-m", "batch.ml.update_weights"]
    if apply_flag:
        curves_cmd.append("--apply")
    else:
        weights_cmd.append("--dry-run")
    steps.append(("감쇠 곡선 반영", curves_cmd))
    steps.append(("넛지 가중치 갱신", weights_cmd))

    for name, cmd in steps:
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=False)
        if proc.returncode != 0:
            result.record(name, "critical", error=f"exit {proc.returncode}")
            logger.error(f"{name} 실패 — 이후 단계 중단")
            return
        result.record(name, "success", duration=time.time() - t0)
```

main() 의 choices 에 `"ml"` 추가, 분기에 `elif args.type == "ml": run_ml(args, logger, result)` 추가, argparse 에:

```python
    parser.add_argument("--apply", action="store_true",
                        help="ml 전용: 학습 결과(decay/가중치)를 common_code 에 반영 (기본 dry-run)")
```

- [ ] **Step 5: 테스트 + dry-run 파이프라인 실행 확인**

```bash
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "Phase1|결과:"
.venv/bin/python -m batch.run --type ml   # 기본 dry-run — DB 무변경 확인
```
Expected: Phase1 테스트 5건 PASS. ml 파이프라인 4단계 success (train 은 수 분 소요 가능), common_code 변경 없음(dry-run).

- [ ] **Step 6: Commit**

```bash
git add batch/ml/apply_curves.py batch/run.py web/backend/tests/test_core.py
git commit -m "feat(ml): 재학습 파이프라인 --type ml + 감쇠 곡선 common_code 반영 경로 (Phase 1-4)"
```

---

### Task 5: 통합 검증 + 문서 갱신

**Files:**
- Modify: `docs/analysis/2026-07-03-life-score-adequacy-review.md` (Phase 1 상태)

- [ ] **Step 1: 전체 테스트**

```bash
.venv/bin/python web/backend/tests/test_core.py 2>&1 | tail -12
```
Expected: Phase1 5건 포함 전체 통과 (기존 대시보드 드리프트 2건 제외)

- [ ] **Step 2: 지역 편향/차별성 프로브 재실행 + 기록**

```bash
.venv/bin/python /private/tmp/claude-501/-Users-wizmain-Documents-workspace-apt-recom/af0e5863-55e2-416d-8a3d-7796a001ff97/scratchpad/probe_score_bias.py
.venv/bin/python /private/tmp/claude-501/-Users-wizmain-Documents-workspace-apt-recom/af0e5863-55e2-416d-8a3d-7796a001ff97/scratchpad/probe_nudge_overlap.py
```
Expected: education 분포 변화 확인, 회귀(다른 넛지 흔들림) 없음. 결과를 report 에 기록.

- [ ] **Step 3: 진단 문서 상태 갱신** — `### Phase 1 — 단기` 헤딩을 `### Phase 1 — 단기 — ✅ 1-1/1-3/1-4 구현 완료 (2026-07-03, 1-2 는 hedonic 으로 대체·1-5 후속)` 로 수정. hedonic 리포트 핵심 수치(within R², 유의 시설 수)를 §4 Phase 1 표 아래에 한 줄 추가.

- [ ] **Step 4: Commit**

```bash
git add docs/analysis/2026-07-03-life-score-adequacy-review.md docs/superpowers/plans/2026-07-03-life-score-phase1.md
git commit -m "docs(analysis): 라이프점수 Phase 1 구현 상태 + hedonic 결과 반영"
```

- [ ] **Step 5: 사용자 액션 안내 (실행 금지 — 보고만)**
1. Railway 반영 (사용자 직접): `scripts/update_education_weights.py --target railway --apply` + 백엔드 재배포/재기동. assigned_elementary summary 데이터는 로컬→Railway 동기화 경로(batch.push_table_to_railway 또는 기존 sync 절차) 필요 — 방법 명시.
2. GitHub Actions quarterly 워크플로에 `--type ml`(dry-run) 정기 실행 편입 여부 결정.
3. hedonic 리포트 검토 → 가중치 재조정(1-2) 여부 결정.

---

## Self-Review 결과 (작성 시 수행)

- **Spec coverage**: 1-1(배정초교 배치+가중치+quarterly 편입)=Task 1·2, 1-3(hedonic)=Task 3, 1-4(재학습 CLI+decay DB 연결)=Task 4. 1-2 는 Task 3 리포트로 대체(승인됨), 1-5 후속(승인됨).
- **Placeholder**: 없음 — 모든 코드 스텝 완전 코드.
- **Type consistency**: `recalc_assigned_school(conn, logger) -> dict{"matched","fallback","total"}` Task 1 정의 = run.py 소비 일치. `fit_decay_from_curve(distances, scores, max_d) -> float` Task 4 정의 = 테스트 소비 일치. subtype 문자열 `assigned_elementary` 전 태스크 통일. nudge_weight 파싱 규약(code=`nudge:subtype`, extra=값)은 update_weights.py:44-51 실측과 일치.
- **알려진 리스크**: (1) 동명 학교 오매칭 — 3km 상한 가드 + 매칭 통계 로그. (2) hedonic 표본 편향(거래 있는 아파트만) — 리포트에 표본 수 명시. (3) run.py `--type ml` 의 subprocess 실행은 기존 파이프라인과 이질적이나 모듈들이 각자 main()/커넥션을 소유하므로 안전 — 대안(직접 import 호출)은 argparse 충돌 리팩토링 필요해 YAGNI. (4) decay 반영 시 전 넛지 점수 변동 — 그래서 --apply 를 기본 비활성으로 설계.
