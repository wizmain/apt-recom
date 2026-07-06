# 라이프점수 Phase 2-2: 상가(상권)정보 — 카페·키즈카페·펫샵·피트니스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 소상공인시장진흥공단 상가정보 API 로 4개 업종(카페·키즈카페·펫샵/미용·헬스)을 `facilities` 테이블에 적재하고, 기존 집계/스코어링 파이프라인으로 pet·newlywed·cost 넛지를 보강한다.

**Architecture:** 신규 점포를 기존 `facilities`(facility_id PK, subtype, 좌표) 에 적재하면 BallTree 집계·거리 스코어링·4a 결측 중립화가 전부 재사용된다. 유일한 신규 배관은 "전 아파트 × 신규 subtype 만" 집계하는 경량 헬퍼(`recalc_summary_for_subtypes` — 기존 전체 재계산은 TRUNCATE 방식이라 부적합). 수집은 업종 소분류별 전국 페이징(storeListInUpjong 계열), 키는 `DATA_GO_KR_API_SECONDARY_KEY`(PoC 확인 — primary 는 이 API 미신청 403), `batch/api_keys` 로테이터 사용 시 primary 403 이 아니라 **이 API 는 secondary 고정**이 맞음 (403은 429와 달리 로테이션 대상 아님).

**Tech Stack:** 기존 batch 인프라 (requests/psycopg2/BallTree). 신규 의존성 없음.

**Spec:** 진단 보고서 §4 Phase 2 (상가정보). 승인: 업종 4종 (헬스는 수집만 — 가중치 보류, hedonic 측정 후 결정).

## Global Constraints

- 브랜치 `feature/store-facilities`. Conventional Commits, AI 표기 금지, push/Railway 금지, 신규 pip 의존성 금지, ruff 통과. `.venv/bin/python`.
- PoC 확정 사실: sdsc2 API 대분류 25종, 카페 소분류 **I21201**. `storeListInRadius` 응답에 `indsSclsNm/bizesNm/lat/lon` 필드. secondary 키만 활용신청됨.
- facility_id 규약: `STORE_{bizesId}` (상가업소번호 — 재수집 시 안정 upsert 키).
- 신규 subtype/type 매핑 (통일 명칭): `cafe`(living), `kids_cafe`(living), `pet_shop`(pet), `fitness`(culture).
- 가중치 설계 (합 1.0 재정규화, update_quality_weights 골격 재사용):
  - pet: `pet_shop` **0.15** (기존 3축 ×0.85)
  - newlywed: `kids_cafe` **0.08** + `cafe` **0.04** (기존 ×0.88)
  - cost: `cafe` **0.05** (기존 ×0.95)
  - fitness: 가중치 없음 (수집·집계·hedonic 측정만)
- scoring.py 기본 파라미터 (근거 주석 필수): decay — cafe 300, kids_cafe 500, pet_shop 400, fitness 400 / density factor — cafe 3(밀집 업종), kids_cafe 20, pet_shop 12, fitness 10.
- 테스트: test_core.py Phase 2 섹션에 추가. 현재 83/83 기준 무회귀.
- 상가 API 도 일일 한도 가능 — 페이지 단위 진행 로그 + 실패 시 부분 커밋 유지(업종·페이지 단위 재개 가능 구조), 429 시 조기 중단 보고.

## File Structure

| 구분 | 경로 | 책임 |
|------|------|------|
| Create | `batch/quarterly/collect_store_facilities.py` | 업종별 전국 수집 → facilities upsert |
| Modify | `batch/quarterly/recalc_summary.py` | `recalc_summary_for_subtypes(conn, logger, subtypes)` 헬퍼 |
| Modify | `batch/run.py` | quarterly 에 상가 수집 + 신규 subtype 집계 단계 |
| Modify | `web/backend/services/scoring.py` | 신규 subtype decay/density 기본값 |
| Create | `scripts/update_store_weights.py` | pet/newlywed/cost 가중치 재배분 |
| Modify | `batch/ml/hedonic_validation.py` | FEATURE_SUBTYPES 에 4종 추가 |
| Modify | `web/backend/tests/test_core.py` | Phase 2 테스트 2건 |

---

### Task 1: 소분류 코드 확정 + 수집 모듈 (표본 검증까지)

**Files:** Create `batch/quarterly/collect_store_facilities.py`, Test `web/backend/tests/test_core.py`

**Interfaces:**
- Consumes: `DATA_GO_KR_API_SECONDARY_KEY`(batch/config), sdsc2 엔드포인트(`largeUpjongList`/`middleUpjongList`/`smallUpjongList`/업종별 점포 조회), facilities 스키마(facility_id PK/type/subtype/name/lat/lng/address/is_active).
- Produces: `collect_store_facilities(conn, logger, subtypes=None, max_pages=0) -> dict{"fetched","upserted","deactivated"}`, 모듈 상수 `STORE_SUBTYPE_CODES: dict[subtype, list[소분류코드]]`.

- [ ] **Step 1 (탐색 — 코드 확정):** sdsc2 `middleUpjongList`/`smallUpjongList` 를 훑어 4개 subtype 의 소분류 코드 목록을 확정한다. 확정 기준: 업종명에 카페/커피(cafe), 키즈카페/놀이(kids_cafe), 애완/펫 용품·미용(pet_shop), 헬스/피트니스/체력단련(fitness) — 각 매핑을 모듈 상수 `STORE_SUBTYPE_CODES` 에 근거 주석과 함께 기록. **전국 점포 조회 엔드포인트도 이 단계에서 확정** (후보: `storeListInUpjong` — indsSclsCd 필터 + pageNo/numOfRows; 미지원 시 시도 단위 `storeListInDong`/`storeListInArea` 대안 검토, 선택 근거를 docstring 에 기록).

- [ ] **Step 2 (실패 테스트):** test_core.py Phase 2 섹션에 추가 후 RED 확인:

```python
@test("Phase2: 상가 유래 시설(cafe/kids_cafe/pet_shop/fitness) 적재")
def test_store_facilities_loaded():
    from database import DictConnection

    conn = DictConnection()
    rows = conn.execute(
        "SELECT facility_subtype, COUNT(*) AS c FROM facilities "
        "WHERE facility_subtype = ANY(%s) AND is_active GROUP BY 1",
        [["cafe", "kids_cafe", "pet_shop", "fitness"]],
    ).fetchall()
    conn.close()
    counts = {r["facility_subtype"]: r["c"] for r in rows}
    # 전국 규모 기대 하한 (표본 아님): 카페는 수만, 나머지는 수백~수천
    assert counts.get("cafe", 0) >= 10_000, f"cafe 부족: {counts}"
    for st in ("kids_cafe", "pet_shop", "fitness"):
        assert counts.get(st, 0) >= 300, f"{st} 부족: {counts}"
```

- [ ] **Step 3 (수집 모듈):** `batch/quarterly/collect_store_facilities.py` 생성 — 핵심 계약:

```python
"""소상공인 상가(상권)정보 → facilities 적재 (라이프점수 Phase 2-2).

업종 소분류별 전국 페이징 수집. 4개 subtype 매핑은 STORE_SUBTYPE_CODES
(Step 1 탐색으로 확정, 근거 주석 포함).

키: 이 API 는 SECONDARY 키만 활용신청됨 (PoC 2026-07-06 — primary 403).
403 은 활용신청 문제라 로테이션 대상이 아니므로 secondary 를 직접 사용한다.

upsert: facility_id = 'STORE_' + 상가업소번호(bizesId). 재수집 시 사라진
점포는 is_active=FALSE 처리 (해당 subtype 한정 — 폐업 반영).

사용법:
  .venv/bin/python -m batch.quarterly.collect_store_facilities                # 전체
  .venv/bin/python -m batch.quarterly.collect_store_facilities --subtype cafe --max-pages 2  # 표본
"""
```

구현 요구사항 (코드 골격은 collect_building_register 관례 준용):
- `STORE_SUBTYPE_CODES` 상수 + `SUBTYPE_TYPE_MAP = {"cafe": "living", "kids_cafe": "living", "pet_shop": "pet", "fitness": "culture"}`.
- 페이징 루프: numOfRows 는 API 허용 최대(Step 1 에서 확인, 통상 1000). 페이지별 `time.sleep(DATA_GO_KR_RATE)`. HTTP 429 → RuntimeError 로 조기 중단 보고(부분 커밋 유지).
- 행 변환: `(f"STORE_{bizesId}", type, subtype, 상호명, lat, lon, 도로명주소, TRUE)` — 좌표 결측 행은 skip 카운트.
- upsert: `ON CONFLICT (facility_id) DO UPDATE SET name/lat/lng/address/is_active=TRUE/updated_at=NOW()`. 업종당 수집 완료 후: `UPDATE facilities SET is_active=FALSE WHERE facility_subtype=%s AND facility_id LIKE 'STORE\\_%%' AND updated_at < 실행시작시각` (폐업 비활성 — 발동 로그).
- `main()`: `--subtype`(선택), `--max-pages`(표본용, 0=무제한).

- [ ] **Step 4 (표본 실행 + GREEN 은 아직 아님):** `--subtype cafe --max-pages 2` 등으로 4개 subtype 각각 소량 수집해 필드 매핑/upsert 검증 (Step 2 테스트는 전량 수집 후 GREEN — Task 2). ruff 통과.

- [ ] **Step 5: Commit** — `feat(batch): 상가정보 수집 모듈 — 카페·키즈카페·펫샵·피트니스 (Phase 2-2)`

---

### Task 2: 전량 수집 + 신규 subtype 집계

**Files:** Modify `batch/quarterly/recalc_summary.py`, `batch/run.py`

**Interfaces:**
- Consumes: recalc_summary 의 `_build_balltree`/`_query_nearest_and_counts` 기존 헬퍼, assigned_school 의 UPSERT 패턴.
- Produces: `recalc_summary_for_subtypes(conn, logger, subtypes: list[str]) -> int` — 전 아파트 × 지정 subtype 만 upsert (TRUNCATE 없음). run.py quarterly 에 상가 수집(5단계)+부분 집계(5b) 추가.

- [ ] **Step 1:** `recalc_summary_for_subtypes` 구현 — 전 아파트(lat NOT NULL) 좌표 배열 1회 로드, subtype 별 BallTree → nearest/counts → `INSERT ... ON CONFLICT (pnu, facility_subtype) DO UPDATE` (assigned_school UPSERT_SQL 과 동일 컬럼 세트). 반환: upsert 행 수.
- [ ] **Step 2:** run.py `run_quarterly` 에 5단계 추가 (4단계 배정초교 뒤): 상가 수집 → `recalc_summary_for_subtypes(conn, logger, 신규 4종)` — 실패는 warning 격리 (quarterly 본연 기능 보호). 주석: 전체 recalc_summary 가 TRUNCATE 후 재계산이라 quarterly 정기 실행 시에는 자동 포함되지만, 상가 수집이 그보다 늦게 실행되므로 부분 집계로 즉시 반영.
- [ ] **Step 3 (전량 수집 실행):** `.venv/bin/python -m batch.quarterly.collect_store_facilities` (전체 — 카페 수만 건 포함, 페이징 수 분~수십 분 예상. 429 시 중단 지점 보고) → `recalc_summary_for_subtypes` 직접 실행 (4 subtype × 3.5만 아파트 — 수 분). Task 1 의 테스트 GREEN 확인 + 아파트 summary 행 수 검증 쿼리 결과를 report 에 기록.
- [ ] **Step 4: Commit** — `feat(batch): 상가 시설 전량 적재 + 신규 subtype 부분 집계 경로 (Phase 2-2)`

---

### Task 3: 스코어링 반영 (기본값 + 가중치 + hedonic)

**Files:** Modify `web/backend/services/scoring.py`, `batch/ml/hedonic_validation.py`, Create `scripts/update_store_weights.py`, Test `test_core.py`

- [ ] **Step 1 (실패 테스트):**

```python
@test("Phase2: 상가 축 가중치 반영 (pet/newlywed/cost) + 합 1.0")
def test_store_weights_applied():
    from database import DictConnection

    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, extra FROM common_code WHERE group_id = 'nudge_weight' "
        "AND (code LIKE %s OR code LIKE %s OR code LIKE %s)",
        ["pet:%", "newlywed:%", "cost:%"],
    ).fetchall()
    conn.close()
    weights: dict[str, dict[str, float]] = {}
    for r in rows:
        nudge, subtype = r["code"].split(":", 1)
        weights.setdefault(nudge, {})[subtype] = float(r["extra"])
    assert weights["pet"].get("pet_shop", 0) >= 0.12
    assert weights["newlywed"].get("kids_cafe", 0) >= 0.06
    assert weights["cost"].get("cafe", 0) >= 0.04
    for nudge, w in weights.items():
        assert abs(sum(w.values()) - 1.0) < 0.02, f"{nudge} 합 이탈: {sum(w.values())}"
```

- [ ] **Step 2:** scoring.py `_DEFAULT_FACILITY_DECAY` 에 cafe 300 / kids_cafe 500 / pet_shop 400 / fitness 400, `_DEFAULT_DENSITY_FACTOR` 에 cafe 3 / kids_cafe 20 / pet_shop 12 / fitness 10 추가 (근거 주석: 카페는 초밀집 업종이라 낮은 factor, 키즈카페는 희소해 높은 factor).
- [ ] **Step 3:** `scripts/update_store_weights.py` — update_quality_weights 골격 그대로, `QUALITY_ADDITIONS` 대신 다중 추가 지원: pet {pet_shop:.15}, newlywed {kids_cafe:.08, cafe:.04}, cost {cafe:.05}. 이미 존재 시 스킵(idempotent). dry-run 기본. 로컬 `--apply` + 백엔드 재기동.
- [ ] **Step 4:** hedonic FEATURE_SUBTYPES 에 cafe/kids_cafe/pet_shop/fitness 추가 → 재실행 → fitness 포함 4종의 거리 계수/t 를 report 에 기록 (fitness 가중치 결정 근거).
- [ ] **Step 5:** 전체 테스트 GREEN + pet 넛지 프로브(강남/청주 top10 — pet_shop 기여 등장 확인, 무관 넛지 불변). Commit — `feat(scoring): 상가 축 가중치 반영 — pet·newlywed·cost (Phase 2-2)`

---

### Task 4: 문서 + 최종 리뷰 준비

- [ ] 진단 문서 §4 Phase 2 표의 상가정보 행에 ✅ + 수집/집계 규모 한 줄. 후속 이슈에 "fitness 가중치 — hedonic 계수 검토 후 결정" 추가.
- [ ] Commit — `docs(analysis): Phase 2-2 상가정보 구현 상태`
- [ ] 사용자 액션 정리 (report): Railway 반영 순서 — ① facilities 신규 subtype 행 + apt_facility_summary 신규 행 동기화 방법(권장: **Railway 에서 동일 배치 실행** — GitHub Actions quarterly 수동 트리거 또는 push_table 확장 검토), ② update_store_weights --target railway --apply, ③ 재기동.

---

## Self-Review (작성 시)
- Spec coverage: 수집(1)→적재/집계(2)→스코어링/가중치/hedonic(3)→문서(4). 승인 사항(4업종, fitness 가중치 보류) 반영.
- Type consistency: `collect_store_facilities(...)->dict`, `recalc_summary_for_subtypes(...)->int`, subtype 명 4종 전 태스크 통일.
- 리스크: (1) storeListInUpjong 엔드포인트/최대 numOfRows 미확정 — Task 1 Step 1 에서 확정하고 미지원 시 대안 기록, (2) 상가 API 일일 한도 미상 — 429 조기 중단+부분 커밋으로 대응, (3) 카페 밀집으로 summary 행 +14만(3.5만 apt ×4) 증가 — 기존 규모(50만) 대비 수용 가능.
