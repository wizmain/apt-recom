# 라이프점수 Phase 2-1: 건축물대장 표제부 (승강기·주차) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 건축HUB 표제부 API 로 아파트별 승강기·주차 데이터를 수집해 `apt_building_register` 테이블에 적재하고, `score_elevator`(senior)·`score_parking`(cost·newlywed) pseudo-subtype 으로 라이프점수에 반영한다 — 현재 점수 체계에 전무한 "단지 내부 품질" 축 신설.

**Architecture:** 기존 자산 최대 재사용. API 호출은 enrich_apartments 의 `getBrTitleInfo` 패턴(활용신청 완료 키, 레이트리밋 0.15s, XML 파싱), 체크포인트는 rebuild_area_info 의 common_code 패턴, 스코어링 주입은 nudge.py 의 score_* 로더 패턴(4b/4c와 동일 — **Phase 0 의 4e 결측 중립화가 자동 적용**되므로 미수집 아파트는 중립 50점). PNU→API 파라미터는 기존 관례대로 **원값 전달** (`platGbCd=pnu[10]` — PoC 30/30 히트 실측, int-1 변환은 0/30).

**Tech Stack:** Python(requests, xml.etree, psycopg2), 기존 batch 인프라. 신규 의존성 없음.

**Spec:** `docs/analysis/2026-07-03-life-score-adequacy-review.md` §4 Phase 2-2 (건축물대장). 승인 사항: 전국 전체 수집(~31k 호출, 체크포인트 재개), senior+elevator 0.15 / cost·newlywed+parking 0.10 반영(로컬 검증까지 — Railway 는 사용자 별도 승인).

## Global Constraints

- 브랜치 `feature/building-register`. Conventional Commits, **AI 표기 금지**, push 금지, **Railway 접속 금지**(스크립트 --target 옵션만), 신규 pip 의존성 금지.
- `.venv/bin/python`, ruff format/check 통과. batch↔backend 상호 import 금지.
- **API 관례**: PNU 19자리 → sigunguCd=pnu[:5], bjdongCd=pnu[5:10], **platGbCd=pnu[10] 원값**, bun=pnu[11:15], ji=pnu[15:19]. 레이트 `DATA_GO_KR_RATE`(0.15s, batch/config.py:21) 준수.
- pseudo-subtype 명: `score_parking`, `score_elevator` (nudge.py 4e 가 `score_` prefix 로 결측 중립화하므로 반드시 이 prefix).
- 정규화 상수는 명명 상수 + 근거 주석 (scoring.py 관례). 수집 후 실측 분포로 상수 재확인(Task 4).
- 수집 대상: `LENGTH(pnu)=19 AND pnu NOT LIKE 'TRADE_%'` (~35k). 좌표 조건 불필요(대장 조회는 지번 기반).
- 로컬 백엔드 8000 이 `--reload` 기동 중 — DB 값(가중치) 변경 시 재기동 필요.
- 테스트: test_core.py "라이프점수 Phase 1" 섹션 아래 "Phase 2" 섹션 신설. 현재 80/80 기준 유지.

## File Structure

| 구분 | 경로 | 책임 |
|------|------|------|
| Modify | `web/backend/database.py` | `apt_building_register` 테이블 정의 (create_tables) |
| Create | `batch/annual/collect_building_register.py` | 표제부 수집→동 합산→upsert (체크포인트, --max-calls) |
| Modify | `batch/run.py` | `--type building_register` 타입 추가 |
| Modify | `web/backend/services/scoring.py` | `parking_ratio_to_score` / `elevator_to_score` + 상수 |
| Modify | `web/backend/routers/nudge.py` | 4f: apt_building_register 벌크로드 → score_parking/score_elevator |
| Create | `scripts/update_quality_weights.py` | senior/cost/newlywed 가중치 재배분 (dry-run 기본) |
| Modify | `web/backend/tests/test_core.py` | Phase 2 회귀 테스트 |

데이터 흐름: apartments(pnu) → [collect_building_register] → getBrTitleInfo(동별) → 주거동 필터·합산 → apt_building_register → nudge.py 4f → scoring 가중합. 전수 수집(~90분)은 Task 2 에서 컨트롤러가 백그라운드 실행 — Task 3 구현과 병렬.

---

### Task 1: 테이블 + 수집 배치 모듈 (표본 검증까지)

**Files:**
- Modify: `web/backend/database.py` (apt_vectors 정의 앞에 테이블 추가)
- Create: `batch/annual/collect_building_register.py`
- Modify: `batch/run.py` (--type building_register)
- Test: `web/backend/tests/test_core.py` (Phase 2 섹션 신설, 1건)

**Interfaces:**
- Consumes: `batch/config.py` DATA_GO_KR_API_KEY/DATA_GO_KR_RATE, `batch/db.py` get_connection/query_all, common_code 체크포인트 규약 (`scripts/rebuild_area_info.py:55-73` 패턴).
- Produces: 테이블 `apt_building_register(pnu PK, elevator_count, parking_total_count, parking_indoor_count, register_hhld_cnt, register_dong_cnt, parking_per_hhld, created_at, updated_at)`. `collect_building_register(conn, logger, max_calls) -> dict{"fetched","upserted","skipped","resumed_from"}` — run.py 와 Task 2 가 소비.

- [ ] **Step 1: 실패하는 테스트 작성** — test_core.py Phase 1 섹션 뒤에:

```python
# ============================================================
# 라이프점수 Phase 2 회귀 테스트 (2026-07-04) — 건축물대장 표제부
# ============================================================

@test("Phase2: apt_building_register 테이블 존재 + 표본 적재")
def test_building_register_table():
    from database import DictConnection
    conn = DictConnection()
    row = conn.execute(
        """SELECT COUNT(*) AS c,
                  COUNT(*) FILTER (WHERE parking_per_hhld IS NOT NULL) AS with_ratio
           FROM apt_building_register"""
    ).fetchone()
    conn.close()
    assert row["c"] >= 100, f"apt_building_register 적재 부족: {row['c']}행 (표본 100+ 기대)"
    assert row["with_ratio"] > 0, "parking_per_hhld 전부 NULL"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom && .venv/bin/python web/backend/tests/test_core.py 2>&1 | grep "Phase2"
```
Expected: FAIL (테이블 없음)

- [ ] **Step 3: 테이블 정의** — database.py 의 `CREATE TABLE IF NOT EXISTS apt_vectors` 블록 **앞**에 추가:

```sql
        -- 건축물대장 표제부 집계 (라이프점수 Phase 2-1: 승강기/주차)
        -- 수집: batch/annual/collect_building_register.py (동별 표제부 → 단지 합산)
        -- NULL 보충 전략: 미수집 pnu 는 nudge.py 4e 결측 중립화(50점)로 처리,
        -- 연 1회 재수집(--type building_register)으로 채움.
        CREATE TABLE IF NOT EXISTS apt_building_register (
            pnu TEXT PRIMARY KEY,
            elevator_count INTEGER,
            parking_total_count INTEGER,
            parking_indoor_count INTEGER,
            register_hhld_cnt INTEGER,
            register_dong_cnt INTEGER,
            parking_per_hhld DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
```

로컬 DB 반영: `.venv/bin/python -c "import sys; sys.path.insert(0, 'web/backend'); from database import create_tables; create_tables()"` (기존 테이블 IF NOT EXISTS 라 안전).

- [ ] **Step 4: 수집 모듈 구현** — `batch/annual/collect_building_register.py` 생성:

```python
"""건축물대장 표제부 → 아파트 승강기/주차 집계 (라이프점수 Phase 2-1).

동(棟)별 표제부(getBrTitleInfo)를 PNU 지번으로 조회해 단지 단위로 합산한다.
PoC 실측(2026-07-04): 층화 표본 30/30 히트 — PNU 파라미터는 원값 전달
(platGbCd=pnu[10], int 변환 금지 — 변환 시 0/30).

합산 규칙:
- 주용도(mainPurpsCdNm)에 '아파트' 또는 '공동주택' 이 포함된 동만 합산
  (관리동/상가 승강기 혼입 방지). 해당 동이 하나도 없으면 전체 동 합산
  fallback (발동 시 로그 — 구식 대장의 용도 표기 편차 대응).
- elevator_count = Σ(rideUseElvtCnt + emgenUseElvtCnt)
- parking_total_count = Σ(indrAutoUtcnt + oudrAutoUtcnt + indrMechUtcnt + oudrMechUtcnt)
- parking_per_hhld = parking_total / max(register_hhld_cnt, DB total_hhld_cnt)
  (대장 세대합이 0/결측이면 DB 세대수 사용 — 분모 0 방지)

체크포인트: common_code('building_register_checkpoint', 'last_pnu') — pnu 오름차순
진행, --max-calls 도달 시 중단 후 재실행하면 이어서 진행 (rebuild_area_info 패턴).

사용법:
  .venv/bin/python -m batch.annual.collect_building_register --max-calls 100   # 표본
  .venv/bin/python -m batch.annual.collect_building_register                   # 전수(재개형)
  .venv/bin/python -m batch.annual.collect_building_register --reset           # 체크포인트 초기화
"""

import argparse
import time
import xml.etree.ElementTree as ET

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import get_connection
from batch.logger import setup_logger

TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
CHECKPOINT_GROUP = "building_register_checkpoint"
RESIDENTIAL_PURPS_KEYWORDS = ("아파트", "공동주택")
PARKING_FIELDS = ("indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt")
MAX_RETRIES = 2
COMMIT_EVERY = 200  # 체크포인트/upsert 커밋 주기


def _params_from_pnu(pnu: str) -> dict:
    """PNU 19자리 → 표제부 API 파라미터 (원값 전달 관례 — 모듈 docstring 참조)."""
    return {
        "serviceKey": DATA_GO_KR_API_KEY,
        "sigunguCd": pnu[:5],
        "bjdongCd": pnu[5:10],
        "platGbCd": pnu[10],
        "bun": pnu[11:15],
        "ji": pnu[15:19],
        "numOfRows": "100",
        "pageNo": "1",
    }


def _fetch_title_items(pnu: str, logger) -> list[dict] | None:
    """표제부 동 목록 조회. 네트워크/파싱 실패 시 None (재시도 후)."""
    fields = ("bldNm", "mainPurpsCdNm", "hhldCnt", "rideUseElvtCnt", "emgenUseElvtCnt",
              *PARKING_FIELDS)
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(TITLE_URL, params=_params_from_pnu(pnu), timeout=15)
            time.sleep(DATA_GO_KR_RATE)
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}")
            root = ET.fromstring(resp.text)
            code = root.findtext(".//resultCode")
            if code not in ("00",):
                raise RuntimeError(f"resultCode {code}: {root.findtext('.//resultMsg')}")
            return [
                {f: (it.findtext(f) or "") for f in fields}
                for it in root.findall(".//item")
            ]
        except Exception as e:  # noqa: BLE001 — 재시도 후 상위에서 skip 처리
            if attempt < MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            logger.warning(f"  {pnu}: 조회 실패 — {e}")
            return None
    return None


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _aggregate(items: list[dict], logger, pnu: str) -> dict | None:
    """동 목록 → 단지 합산. 동이 없으면 None."""
    if not items:
        return None
    residential = [
        it for it in items
        if any(k in it["mainPurpsCdNm"] for k in RESIDENTIAL_PURPS_KEYWORDS)
    ]
    if not residential:
        # fallback: 용도 표기 편차(구식 대장) — 전체 동 합산으로 대체
        logger.debug(f"  {pnu}: 주거용도 동 없음 → 전체 {len(items)}동 합산 fallback")
        residential = items

    elevator = sum(
        _to_int(it["rideUseElvtCnt"]) + _to_int(it["emgenUseElvtCnt"])
        for it in residential
    )
    parking_total = sum(
        sum(_to_int(it[f]) for f in PARKING_FIELDS) for it in residential
    )
    parking_indoor = sum(
        _to_int(it["indrAutoUtcnt"]) + _to_int(it["indrMechUtcnt"])
        for it in residential
    )
    hhld = sum(_to_int(it["hhldCnt"]) for it in residential)
    return {
        "elevator_count": elevator,
        "parking_total_count": parking_total,
        "parking_indoor_count": parking_indoor,
        "register_hhld_cnt": hhld,
        "register_dong_cnt": len(residential),
    }


def _load_checkpoint(cur) -> str | None:
    cur.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, "last_pnu"],
    )
    row = cur.fetchone()
    return row[0] if row else None


def _save_checkpoint(cur, pnu: str) -> None:
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, '', 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
        [CHECKPOINT_GROUP, "last_pnu", pnu],
    )


UPSERT_SQL = """
    INSERT INTO apt_building_register
        (pnu, elevator_count, parking_total_count, parking_indoor_count,
         register_hhld_cnt, register_dong_cnt, parking_per_hhld, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (pnu) DO UPDATE SET
        elevator_count = EXCLUDED.elevator_count,
        parking_total_count = EXCLUDED.parking_total_count,
        parking_indoor_count = EXCLUDED.parking_indoor_count,
        register_hhld_cnt = EXCLUDED.register_hhld_cnt,
        register_dong_cnt = EXCLUDED.register_dong_cnt,
        parking_per_hhld = EXCLUDED.parking_per_hhld,
        updated_at = NOW()
"""


def collect_building_register(conn, logger, max_calls: int = 0) -> dict:
    """전수 수집 (체크포인트 재개형). max_calls=0 이면 무제한."""
    cur = conn.cursor()
    last_pnu = _load_checkpoint(cur)
    logger.info(f"수집 시작 (재개 지점: {last_pnu or '처음'})")

    params: list = []
    where = "LENGTH(a.pnu) = 19 AND a.pnu NOT LIKE 'TRADE\\_%%'"
    if last_pnu:
        where += " AND a.pnu > %s"
        params.append(last_pnu)
    cur.execute(
        f"""SELECT a.pnu, a.total_hhld_cnt FROM apartments a
            WHERE {where} ORDER BY a.pnu""",
        params,
    )
    targets = cur.fetchall()
    logger.info(f"대상: {len(targets):,}건" + (f" (max_calls {max_calls})" if max_calls else ""))

    fetched = upserted = skipped = 0
    for pnu, db_hhld in targets:
        if max_calls and fetched >= max_calls:
            logger.info(f"max_calls {max_calls} 도달 — 중단 (재실행 시 이어서 진행)")
            break
        items = _fetch_title_items(pnu, logger)
        fetched += 1
        agg = _aggregate(items, logger, pnu) if items is not None else None
        if agg is None:
            skipped += 1
        else:
            denom = agg["register_hhld_cnt"] or (db_hhld or 0)
            ratio = round(agg["parking_total_count"] / denom, 3) if denom > 0 else None
            cur.execute(
                UPSERT_SQL,
                [pnu, agg["elevator_count"], agg["parking_total_count"],
                 agg["parking_indoor_count"], agg["register_hhld_cnt"],
                 agg["register_dong_cnt"], ratio],
            )
            upserted += 1
        _save_checkpoint(cur, pnu)
        if fetched % COMMIT_EVERY == 0:
            conn.commit()
            logger.info(f"  진행 {fetched:,}/{len(targets):,} (적재 {upserted:,}, skip {skipped:,})")

    conn.commit()
    logger.info(f"수집 완료: 호출 {fetched:,} / 적재 {upserted:,} / skip {skipped:,}")
    return {"fetched": fetched, "upserted": upserted, "skipped": skipped,
            "resumed_from": last_pnu}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-calls", type=int, default=0, help="최대 API 호출 수 (0=무제한)")
    parser.add_argument("--reset", action="store_true", help="체크포인트 초기화 후 처음부터")
    args = parser.parse_args()

    logger = setup_logger("building_register")
    conn = get_connection()
    try:
        if args.reset:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM common_code WHERE group_id = %s", [CHECKPOINT_GROUP]
            )
            conn.commit()
            logger.info("체크포인트 초기화")
        collect_building_register(conn, logger, max_calls=args.max_calls)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: run.py 에 타입 추가** — `run_ml` 아래에:

```python
def run_building_register(args, logger, result):
    """건축물대장 표제부 수집 (라이프점수 Phase 2-1). 체크포인트 재개형."""
    from batch.annual.collect_building_register import collect_building_register

    conn = get_connection()
    try:
        t0 = time.time()
        stats = collect_building_register(
            conn, logger, max_calls=getattr(args, "max_calls", 0)
        )
        result.record(
            "건축물대장 수집", "success",
            rows=stats["upserted"], duration=time.time() - t0,
        )
    except Exception as e:
        logger.error(f"건축물대장 배치 실패: {e}")
        result.record("건축물대장 배치", "critical", error=str(e))
    finally:
        conn.close()
```

main() choices 에 `"building_register"` 추가 + 분기 추가. (--max-calls 는 기존 backfill 용 인자 재사용 — help 문구에 building_register 추가.)

- [ ] **Step 6: 표본 300건 수집 + 테스트 통과**

```bash
.venv/bin/python -m batch.annual.collect_building_register --max-calls 300
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "Phase2|결과:"
```
Expected: 적재 로그 (skip 율 10% 미만 기대 — 초과 시 원인 조사 후 DONE_WITH_CONCERNS), Phase2 테스트 PASS, 기존 80건 무회귀. 표본의 elevator/parking 분포 요약(SELECT percentile)을 report 에 기록.

- [ ] **Step 7: Commit**

```bash
git add web/backend/database.py batch/annual/collect_building_register.py batch/run.py web/backend/tests/test_core.py
git commit -m "feat(batch): 건축물대장 표제부 수집 — 승강기/주차 집계 테이블 (Phase 2-1)"
```

---

### Task 2: 전수 수집 (컨트롤러 직접 수행 — 서브에이전트 아님)

- [ ] 컨트롤러가 `nohup .venv/bin/python -m batch.annual.collect_building_register` 를 **백그라운드**로 시작 (~31k 호출 × 0.15s ≈ 90분, 체크포인트로 중단 안전).
- [ ] Task 3 구현과 병렬 진행. 완료 후 Task 4 에서 커버리지/분포 검증.
- [ ] 일일 호출 한도 초과(HTTP 에러 급증) 시: 로그 확인 후 다음날 재개 항목으로 사용자에게 보고.

---

### Task 3: 스코어링 반영 (score_parking / score_elevator)

**Files:**
- Modify: `web/backend/services/scoring.py` (정규화 함수 2종 + 상수)
- Modify: `web/backend/routers/nudge.py` (4f 로더)
- Create: `scripts/update_quality_weights.py`
- Test: `web/backend/tests/test_core.py` (Phase 2 섹션 추가 2건)

**Interfaces:**
- Consumes: apt_building_register (Task 1), nudge.py 4b/4c 로더 패턴, 4e score_* 결측 중립화(Phase 0), common_code nudge_weight 규약.
- Produces: `parking_ratio_to_score(parking_per_hhld: float | None) -> float`, `elevator_to_score(elevator_count: int | None, hhld_cnt: int | None) -> float` (scoring.py). nudge_weight 재배분: senior +score_elevator 0.15 / cost·newlywed +score_parking 0.10.

**정규화 설계 (구현 코드에 반영, 상수 근거 주석 필수):**
- `PARKING_RATIO_SCORE_FLOOR = 0.4` (세대당 0.4대 이하 = 0점), `PARKING_RATIO_SCORE_CEIL = 1.3` (1.3대 이상 = 100점) — 선형 클리핑. 법정 기준(세대당 1대 내외)과 표본 분포를 근거로 초기 설정, Task 4 에서 실측 분포(percentile)로 재확인.
- elevator: `ELEVATOR_HOUSEHOLDS_PER_UNIT_GOOD = 25.0` — 승강기 1대당 25세대 이하면 100점, 선형: `min(100, 100 * (elevator_count * GOOD) / hhld)`. elevator_count 0 또는 hhld 결측 시 0점(계단식 구식 단지 = 실제 열위 — 결측(행 없음)과 구분: 행 자체가 없으면 4e 중립 50).
- 두 함수 모두 입력 None → `INFRA_MISSING_NEUTRAL_SCORE` 반환 (행은 있는데 값 NULL 인 경우).

- [ ] **Step 1: 실패하는 테스트 작성** — Phase 2 섹션에 추가:

```python
@test("Phase2: parking/elevator 정규화 경계값")
def test_quality_score_normalization():
    from services.scoring import (
        parking_ratio_to_score, elevator_to_score, INFRA_MISSING_NEUTRAL_SCORE,
    )
    assert parking_ratio_to_score(None) == INFRA_MISSING_NEUTRAL_SCORE
    assert parking_ratio_to_score(0.4) == 0.0
    assert parking_ratio_to_score(1.3) == 100.0
    assert parking_ratio_to_score(2.5) == 100.0, "이상치 클립"
    mid = parking_ratio_to_score(0.85)
    assert 0.0 < mid < 100.0
    assert elevator_to_score(None, 500) == INFRA_MISSING_NEUTRAL_SCORE
    assert elevator_to_score(0, 500) == 0.0, "승강기 없음 = 0점"
    assert elevator_to_score(20, 500) == 100.0, "25세대/대 = 만점"
    assert 0.0 < elevator_to_score(10, 500) < 100.0


@test("Phase2: senior/cost 가중치에 품질 지표 반영 + 합 1.0")
def test_quality_weights_applied():
    from database import DictConnection
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, extra FROM common_code WHERE group_id = 'nudge_weight' "
        "AND (code LIKE %s OR code LIKE %s OR code LIKE %s)",
        ["senior:%", "cost:%", "newlywed:%"],
    ).fetchall()
    conn.close()
    weights: dict[str, dict[str, float]] = {}
    for r in rows:
        nudge, subtype = r["code"].split(":", 1)
        weights.setdefault(nudge, {})[subtype] = float(r["extra"])
    assert weights["senior"].get("score_elevator", 0) >= 0.12
    assert weights["cost"].get("score_parking", 0) >= 0.08
    assert weights["newlywed"].get("score_parking", 0) >= 0.08
    for nudge, w in weights.items():
        assert abs(sum(w.values()) - 1.0) < 0.02, f"{nudge} 합 이탈: {sum(w.values())}"
```

- [ ] **Step 2: RED 확인** 후 구현.

- [ ] **Step 3: scoring.py 정규화 함수** — jeonse_ratio_to_score 아래에:

```python
# 세대당 주차대수 → 0~100 선형 구간 (건축물대장 표제부 집계, Phase 2-1).
# 법정 기준이 세대당 ~1대 내외임을 근거로 0.4대 이하 = 0점, 1.3대 이상 = 100점.
# 초기값 — 전수 수집 후 실측 분포(percentile)로 재확인한다.
PARKING_RATIO_SCORE_FLOOR = 0.4
PARKING_RATIO_SCORE_CEIL = 1.3

# 승강기 1대당 담당 세대수가 이 값 이하면 만점 (승강기 대기시간 체감 근거).
ELEVATOR_HOUSEHOLDS_PER_UNIT_GOOD = 25.0


def parking_ratio_to_score(parking_per_hhld: float | None) -> float:
    """세대당 주차대수 → 0~100. 값 NULL(대장에 주차 미기재)은 중립."""
    if parking_per_hhld is None:
        return INFRA_MISSING_NEUTRAL_SCORE
    span = PARKING_RATIO_SCORE_CEIL - PARKING_RATIO_SCORE_FLOOR
    scaled = (parking_per_hhld - PARKING_RATIO_SCORE_FLOOR) / span * 100.0
    return round(min(100.0, max(0.0, scaled)), 2)


def elevator_to_score(elevator_count: int | None, hhld_cnt: int | None) -> float:
    """승강기 수 → 0~100 (세대당 밀도 기준).

    - elevator_count None (대장 미기재) → 중립
    - 0대 → 0점 (계단식 구식 단지 — 결측이 아닌 실제 열위)
    - hhld 불명이면 승강기 존재만으로 중립 이상 판단 불가 → 중립
    """
    if elevator_count is None:
        return INFRA_MISSING_NEUTRAL_SCORE
    if elevator_count <= 0:
        return 0.0
    if not hhld_cnt or hhld_cnt <= 0:
        return INFRA_MISSING_NEUTRAL_SCORE
    scaled = 100.0 * (elevator_count * ELEVATOR_HOUSEHOLDS_PER_UNIT_GOOD) / hhld_cnt
    return round(min(100.0, scaled), 2)
```

- [ ] **Step 4: nudge.py 4f 로더** — 4d(crime) 블록과 4e 사이에 (import 에 두 함수 추가):

```python
        # 4f. Building register scores (건축물대장 승강기/주차 — Phase 2-1)
        quality_nudges = {"senior", "cost", "newlywed"}
        if quality_nudges & set(req.nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join(["%s"] * len(chunk))
                try:
                    rows = conn.execute(
                        f"SELECT pnu, elevator_count, parking_per_hhld, "
                        f"register_hhld_cnt FROM apt_building_register WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        pnu = row["pnu"]
                        fscores = apt_facility_scores.setdefault(pnu, {})
                        hhld = row["register_hhld_cnt"] or apt_map[pnu].get("total_hhld_cnt")
                        fscores["score_elevator"] = elevator_to_score(
                            row["elevator_count"], hhld
                        )
                        fscores["score_parking"] = parking_ratio_to_score(
                            row["parking_per_hhld"]
                        )
                except Exception:
                    # 테이블 미생성 환경(마이그레이션 전) — 4e 결측 중립화에 위임
                    pass
```

(4e 는 이미 `score_` prefix 전체를 백필하므로 미수집 pnu 는 자동 중립 50.)

- [ ] **Step 5: 가중치 스크립트** — `scripts/update_quality_weights.py` 생성. `scripts/update_education_weights.py` 와 동일 골격 (get_conn/--target/--apply/stale 삭제 없음 — 추가만). 로직: 대상 넛지의 기존 가중치를 (1-신규가중치)배로 축소 후 신규 subtype upsert, 합 1.0 검증:

```python
"""senior/cost/newlywed 가중치 재배분 — 건축물대장 품질 지표 반영 (Phase 2-1).

| 넛지     | 신규 subtype   | 가중치 | 기존 subtype 처리      |
|----------|----------------|--------|------------------------|
| senior   | score_elevator | 0.15   | 기존 전체 × 0.85       |
| cost     | score_parking  | 0.10   | 기존 전체 × 0.90       |
| newlywed | score_parking  | 0.10   | 기존 전체 × 0.90       |

근거: 승강기는 시니어 이동성의 1차 제약(계단식 5층 = 실질 거주 불가),
세대당 주차는 자가용 세대(가성비·신혼육아)의 상시 비용/스트레스 요인.
초기값은 전문가 판단 — 다음 hedonic 실행이 이 축의 시장 계수를 자동 측정한다.
적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_quality_weights.py
  .venv/bin/python scripts/update_quality_weights.py --apply
  .venv/bin/python scripts/update_quality_weights.py --target railway --apply  # 사용자 직접
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
# 넛지별 (신규 subtype, 신규 가중치)
QUALITY_ADDITIONS: dict[str, tuple[str, float]] = {
    "senior": ("score_elevator", 0.15),
    "cost": ("score_parking", 0.10),
    "newlywed": ("score_parking", 0.10),
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

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    for nudge, (new_subtype, new_weight) in QUALITY_ADDITIONS.items():
        cur.execute(
            "SELECT code, name, extra FROM common_code "
            "WHERE group_id = %s AND code LIKE %s",
            [GROUP, f"{nudge}:%"],
        )
        current = {code.split(":", 1)[1]: float(extra) for code, _, extra in cur.fetchall()}
        if new_subtype in current:
            print(f"[{nudge}] {new_subtype} 이미 존재({current[new_subtype]}) — 재배분 스킵")
            continue

        shrink = 1.0 - new_weight
        rebalanced = {s: round(w * shrink, 4) for s, w in current.items()}
        rebalanced[new_subtype] = new_weight
        total = sum(rebalanced.values())
        print(f"[{nudge}] 재배분 합 = {total:.4f}")
        if abs(total - 1.0) > 0.02:
            raise SystemExit(f"{nudge} 가중치 합 이탈: {total}")

        for subtype, weight in rebalanced.items():
            print(f"  {'APPLY' if args.apply else 'DRY-RUN'} {nudge}:{subtype} = {weight}")
            if args.apply:
                cur.execute(UPSERT_SQL, [GROUP, f"{nudge}:{subtype}", subtype, str(weight)])

    if args.apply:
        conn.commit()
        print("✅ 반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 로컬 적용 + 백엔드 재기동 + GREEN 확인**

```bash
.venv/bin/python scripts/update_quality_weights.py            # dry-run
.venv/bin/python scripts/update_quality_weights.py --apply
lsof -ti :8000 | xargs kill 2>/dev/null; sleep 2
cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000 >/dev/null 2>&1 &
sleep 5; cd ../..
.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -E "Phase2|결과:"
```
Expected: Phase 2 테스트 3건 PASS, 기존 무회귀.

- [ ] **Step 7: Commit**

```bash
git add web/backend/services/scoring.py web/backend/routers/nudge.py scripts/update_quality_weights.py web/backend/tests/test_core.py
git commit -m "feat(scoring): 승강기/주차 품질 지표 반영 — senior·cost·newlywed (Phase 2-1)"
```

---

### Task 4: 전수 수집 완료 후 통합 검증 + 문서

**전제**: Task 2 백그라운드 수집 완료 (컨트롤러 확인).

- [ ] **Step 1: 커버리지 테스트 강화** — Phase2 테이블 테스트의 임계를 표본(100)에서 실 커버리지로 상향:

```python
    # 전수 수집 후: 실 아파트(TRADE_ 제외) 대비 85% 이상 적재 기대
```
분자/분모 모두 `pnu NOT LIKE 'TRADE_%'` 조인 기준으로 수정, 임계 0.85 (skip 율 실측으로 조정 — 미달 시 원인 보고).

- [ ] **Step 2: 분포 검증 + 정규화 상수 재확인**

```sql
SELECT percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY parking_per_hhld) FROM apt_building_register WHERE parking_per_hhld IS NOT NULL;
SELECT COUNT(*) FILTER (WHERE elevator_count = 0) AS no_elevator, COUNT(*) FROM apt_building_register;
```
parking p10/p50/p90 이 FLOOR(0.4)~CEIL(1.3) 구간을 유의미하게 커버하는지 확인 — 크게 어긋나면 상수 조정 + 근거 주석 갱신 (조정 시 테스트 경계값도 함께).

- [ ] **Step 3: 프로브 재실행** — 기존 probe_score_bias.py + senior/cost 넛지의 top10 변화, education 등 무관 넛지 불변 확인. report 에 before/after 기록.

- [ ] **Step 4: 진단 문서 갱신** — `docs/analysis/2026-07-03-life-score-adequacy-review.md` §4 Phase 2 표의 건축물대장 행에 `✅ 구현 (2026-07-04)` 표기 + 커버리지/분포 한 줄.

- [ ] **Step 5: Commit + 사용자 액션 정리 (실행 금지)**

```bash
git add web/backend/tests/test_core.py docs/analysis/2026-07-03-life-score-adequacy-review.md docs/superpowers/plans/2026-07-04-building-register-phase2.md
git commit -m "docs(analysis): Phase 2-1 건축물대장 구현 상태 + 분포 검증"
```
사용자 액션(report 에 정리만): ① apt_building_register Railway 동기화(push_table_to_railway 에 설정 추가 or 전용 스크립트), ② update_quality_weights --target railway --apply, ③ 백엔드 재기동, ④ hedonic 재실행으로 신규 축 시장 계수 측정.

---

## Self-Review 결과 (작성 시 수행)

- **Spec coverage**: 수집(테이블+배치+run.py)=Task 1·2, 스코어링(정규화+로더+가중치)=Task 3, 검증/문서=Task 4. 승인 사항(전국 전체, 가중치 제안대로, Railway 별도) 반영.
- **Placeholder**: 없음.
- **Type consistency**: `collect_building_register(conn, logger, max_calls) -> dict` 정의=run.py 소비 일치. `parking_ratio_to_score(float|None)->float` / `elevator_to_score(int|None, int|None)->float` 정의=테스트·nudge.py 소비 일치. subtype `score_parking`/`score_elevator` 전 태스크 통일 + 4e prefix 규약 준수.
- **알려진 리스크**: (1) 일일 호출 한도 — 체크포인트 재개로 대응, 한도 도달 시 사용자 보고. (2) group_pnu 분리등록 단지는 pnu 별 대장이 부분 합산될 수 있음 — register_hhld_cnt vs DB 세대수 괴리로 Task 4 에서 표본 점검, 필요 시 후속(group 합산). (3) 대장 주차 0 표기(옥외 미등재) 단지 — parking NULL 이 아닌 0 으로 적재되므로 0점 처리됨: Task 4 분포에서 0 비율 확인 후 필요 시 "0=미기재 의심 → 중립" 규칙 검토.
