# 거래 키 국토부 고유번호 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 거래 키 `apt_seq` 를 이름 조합(`{시군구}_{단지명}`)에서 국토부 단지 고유번호(aptSeq)로 바꿔, 같은 이름의 다른 단지 거래가 섞이는 문제를 원인부터 없앤다.

**Architecture:** 키 규칙·주소 PNU 는 `batch/trade/trade_keys.py`, 과거 행 추론은 순수 함수 모듈 `trade_key_inference.py`, 새 키 → PNU 매핑은 `trade_key_mapping.py`(순수 판정 + 얇은 DB 래퍼)로 분리한다. 적재 배치는 새 키로 쓰고 매핑을 이름 매핑보다 먼저 돌린다. 과거 데이터는 `batch/rekey_trades.py` 가 구 단위 트랜잭션으로 바꾸고, 커밋 전에 검증해 실패하면 그 구를 되돌린다. 추론 불가 잔여분은 기존 백필 배치에 대상 모드를 추가해 API 로 채운다.

**Tech Stack:** Python 3.12, psycopg2(raw SQL, `%s` 바인딩), PostgreSQL, unittest(`scripts/tests`, DB·네트워크 없이 CI 실행), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md` · ADR: `docs/adr/015-trade-key-official-id.md`

## Global Constraints

- 키 규칙: aptSeq 가 있으면 `apt_seq = aptSeq`(예: `11590-57`), 없으면 `{sgg}_{apt_nm}`. **키는 불투명 문자열** — 시군구는 항상 `sgg_cd` 칼럼에서 읽는다(aptSeq 앞자리 ≠ 내부 코드 331건).
- `api_apt_seq` 는 **API 원본값만** 담는다. 추론값을 넣지 않는다.
- `legacy_apt_seq` = 이름 키(`{sgg}_{apt_nm}`). `apt_seq` 가 이름 키와 다를 때만 채운다. 롤백은 `apt_seq = legacy_apt_seq`.
- `apt_seq_method` 값: `api` / `infer_single` / `infer_year` / `infer_year_area` / `infer_area` / `api_backfill`. NULL = 이름 키 그대로.
- 새 키 매핑 `match_method` 값: `api_inherit_legacy` / `api_address_pnu` / `api_name_exact` / `api_name_contains` / `api_name_core`.
- 매핑 실패 시 fallback 매핑 금지 — 미매핑으로 두고 로그에 개수·목록.
- 주소 PNU: `{sgg}{umd_cd}{산여부}{bonbun 4자리}{bubun 4자리}`, 산여부는 API `landCd == "2"` 이면 `1`, 아니면 `0`.
- 스키마 변경은 `web/backend/database.py` 의 `create_tables()` 안 `ALTER TABLE … ADD COLUMN IF NOT EXISTS` 로만 한다(ORM·마이그레이션 프레임워크 없음).
- 운영(Railway) DB 실행은 사용자가 한다. 에이전트는 로컬(`--target local`)까지만 실행한다.
- 커밋 메시지는 Conventional Commits, AI 작업자 표기 금지. 브랜치 접두어 `feature/`·`bugfix/`·`docs/`, main 직접 push 금지.
- 테스트 실행: `.venv/bin/python -m unittest discover -s scripts/tests -t .` (프로젝트 루트). Python 포맷: `uvx ruff format {파일}` / `uvx ruff check {파일}`.

## Review Focus

1. API 가 aptSeq 를 빈 문자열·공백으로 주는 행 — 이름 키로 남아야 한다(빈 키 금지). → Task 2 테스트
2. 같은 주택형 면적이 행마다 소수 자리만 다르게 기록됨(84.9234 vs 84.92) — 같은 서명으로 취급해야 추론이 깨지지 않는다. → Task 4 테스트
3. 한 aptSeq 가 이름 변형 때문에 서로 다른 PNU 로 매핑된 기존 키 2개 이상에 걸침 — 상속하지 말고 2순위 이하로 판정해야 한다. → Task 5 테스트
4. 키 변경 스크립트 실행 중 거래 배치가 돈다 — 배치는 조용히 진행하지 말고 실패로 기록하고 멈춰야 한다. → Task 6 테스트
5. 전월세 대상 행: 기존 키는 단일 고유번호인데 그 면적이 한 번도 관측되지 않음 — 이름 키 그대로 둬야 한다(추측 금지). → Task 4 테스트

---

## File Structure

| 파일 | 상태 | 책임 |
|---|---|---|
| `batch/trade/trade_keys.py` | 신규 | 키 규칙(`resolve_trade_key`), 이름 키, 주소 PNU, 키 방법 상수, 거래 쓰기 잠금 |
| `batch/trade/trade_key_inference.py` | 신규 | 과거 행 → 고유번호 추론(순수 함수) |
| `batch/trade/trade_key_mapping.py` | 신규 | 새 키 → PNU 판정(순수 함수) + DB 래퍼 `map_api_keys` |
| `batch/rekey_trades.py` | 신규 | 과거 데이터 키 변경 CLI(구 단위·검증·롤백·체크포인트) |
| `batch/trade/load_trades.py` | 수정 | 새 키 규칙으로 적재, 전월세 `build_year` |
| `batch/trade/collect_trades.py` | 수정(조건부) | `RENT_COL_MAP` 에 `buildYear` |
| `batch/trade/recalc_price.py` | 수정 | 이름 매핑이 새 키를 건드리지 않게 |
| `batch/trade/backfill_trades.py` | 수정 | `trade_key` 대상 모드 |
| `batch/run.py` | 수정 | 잠금, 새 키 매핑 단계, 백필 모드 인자 |
| `batch/db.py` | 수정 | `vacuum_tables` 공용화 |
| `batch/purge_old_trades.py` | 수정 | `vacuum_tables` 사용 |
| `batch/sync_from_railway.py` | 수정 | 동기화 칼럼 추가 |
| `web/backend/database.py` | 수정 | 칼럼 3개 추가 |
| `scripts/register_missing_apartments.py` | 수정 | 키 문자열 파싱 제거 |
| `.github/workflows/batch-backfill-trade-key.yml` | 신규 | 잔여 API 수집 |
| `scripts/tests/test_trade_keys.py` 외 4개 | 신규 | 단위 테스트 |
| `docs/guides/trade-key-rekey-runbook.md` | 신규 | 운영 실행 런북 |

PR 묶음(설계 4-4): **PR 1** = Task 1~7, **PR 2** = Task 8~9, **PR 3** = Task 10, **PR 4** = Task 11(운영 후).

---

### Task 1: 전월세 API `buildYear` 확인 (설계 4-1 의 구현 전 확인)

**Files:**
- Modify (조건부): `batch/trade/collect_trades.py` (`RENT_COL_MAP`)

**Interfaces:**
- Produces: 결정값 `RENT_HAS_BUILD_YEAR` (이 Task 결과를 Task 3 이 따른다). 코드 상수가 아니라 Task 3 의 분기 지시다.

- [ ] **Step 1: API 1회 호출로 응답 필드 확인** (로컬, 읽기 전용)

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
.venv/bin/python - <<'EOF'
import requests, re
from dotenv import load_dotenv; load_dotenv(".env")
from batch.config import DATA_GO_KR_API_KEY, RENT_URL
xml = requests.get(RENT_URL, params={"serviceKey": DATA_GO_KR_API_KEY, "LAWD_CD": "11590",
      "DEAL_YMD": "202609", "pageNo": "1", "numOfRows": "5"}, timeout=30).text
item = re.search(r"<item>(.*?)</item>", xml, re.S)
print(sorted(set(re.findall(r"<(\w+)>", item.group(1)))) if item else xml[:500])
EOF
```
Expected: 태그 목록 출력. `buildYear` 포함 여부를 기록한다.

- [ ] **Step 2: 결과에 따라 분기**

`buildYear` 가 있으면 `RENT_COL_MAP`(`batch/trade/collect_trades.py:95`)의 `"aptSeq": "aptSeq",` 바로 위에 추가:

```python
    "buildYear": "buildYear",
```

없으면 코드 변경 없음. 설계서 4-1 의 해당 문단을 "전월세 API 에 buildYear 없음 — `rent_history.build_year` 미도입"으로 고치고 Task 2·3 의 `rent_history.build_year` 관련 줄을 모두 생략한다.

- [ ] **Step 3: Commit** (변경이 있을 때만)

```bash
git add batch/trade/collect_trades.py docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md
git commit -m "feat(batch): 전월세 수집에 buildYear 필드 추가"
```

---

### Task 2: 키 규칙 모듈 + 스키마 칼럼

**Files:**
- Create: `batch/trade/trade_keys.py`
- Modify: `web/backend/database.py` (create_tables 의 ALTER 블록, 433행 부근)
- Test: `scripts/tests/test_trade_keys.py`

**Interfaces:**
- Produces:
  - `name_key(sgg: str, apt_nm: str) -> str`
  - `resolve_trade_key(sgg: str, apt_nm: str, api_apt_seq: str | None) -> TradeKey`
  - `TradeKey(NamedTuple)`: `apt_seq: str`, `legacy_apt_seq: str | None`, `apt_seq_method: str | None`
  - `address_pnu(sgg, umd_cd, land_cd, bonbun, bubun) -> str | None`
  - 상수 `KEY_METHOD_API`, `KEY_METHOD_INFER_SINGLE`, `KEY_METHOD_INFER_YEAR`, `KEY_METHOD_INFER_YEAR_AREA`, `KEY_METHOD_INFER_AREA`, `KEY_METHOD_API_BACKFILL`, `TRADE_WRITE_LOCK_ID: int`
  - `try_trade_write_lock(conn) -> bool` (세션 advisory lock, 실패 시 False)

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_trade_keys.py`

```python
"""거래 키 규칙(ADR-015) — DB·네트워크 없이 확인 (CI 대상)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_keys import (  # noqa: E402
    KEY_METHOD_API,
    TradeKey,
    address_pnu,
    name_key,
    resolve_trade_key,
    try_trade_write_lock,
)


class ResolveTradeKeyTest(unittest.TestCase):
    def test_api_seq_becomes_key_and_name_key_is_kept(self):
        self.assertEqual(
            resolve_trade_key("11590", "대림아파트", "11590-85"),
            TradeKey("11590-85", "11590_대림아파트", KEY_METHOD_API),
        )

    def test_missing_api_seq_keeps_name_key(self):
        self.assertEqual(
            resolve_trade_key("11590", "대림아파트", None),
            TradeKey("11590_대림아파트", None, None),
        )

    def test_blank_api_seq_is_treated_as_missing(self):
        # Review Focus 1 — 빈 키가 생기면 안 된다.
        for blank in ("", "   ", "\t"):
            self.assertEqual(
                resolve_trade_key("11590", "대림아파트", blank).apt_seq,
                "11590_대림아파트",
            )

    def test_api_seq_is_stripped(self):
        self.assertEqual(resolve_trade_key("11590", "대림", " 11590-57 ").apt_seq, "11590-57")

    def test_name_key_format(self):
        self.assertEqual(name_key("11590", "대림아파트"), "11590_대림아파트")


class AddressPnuTest(unittest.TestCase):
    def test_daebang_daelim(self):
        # 대방동 501 → 1159010800005010000 (2026-10-13 실측 PNU)
        self.assertEqual(
            address_pnu("11590", "10800", "1", "0501", "0000"), "1159010800005010000"
        )

    def test_mountain_lot_uses_1(self):
        self.assertEqual(address_pnu("11590", "10800", "2", "12", "3")[10], "1")

    def test_pads_short_numbers(self):
        self.assertEqual(address_pnu("11590", "10800", "1", "501", None), "1159010800005010000")

    def test_missing_parts_return_none(self):
        self.assertIsNone(address_pnu("11590", None, "1", "0501", "0000"))
        self.assertIsNone(address_pnu("11590", "10800", "1", None, "0000"))

    def test_non_numeric_returns_none(self):
        self.assertIsNone(address_pnu("11590", "10800", "1", "산12", "0"))


class TradeWriteLockTest(unittest.TestCase):
    def test_returns_lock_result(self):
        class Cur:
            def __init__(self, got):
                self.got = got
                self.sql = None

            def execute(self, sql, params):
                self.sql, self.params = sql, params

            def fetchone(self):
                return (self.got,)

        class Conn:
            def __init__(self, got):
                self.cur = Cur(got)

            def cursor(self):
                return self.cur

        self.assertTrue(try_trade_write_lock(Conn(True)))
        busy = Conn(False)
        self.assertFalse(try_trade_write_lock(busy))
        self.assertIn("pg_try_advisory_lock", busy.cur.sql)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_keys -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'batch.trade.trade_keys'`

- [ ] **Step 3: Write minimal implementation** — `batch/trade/trade_keys.py`

```python
"""거래 키(apt_seq) 규칙 — ADR-015.

이름 조합 키 "{시군구}_{단지명}" 은 같은 구의 동명 단지 거래를 합친다(2026-10-13 동작구
대방대림+상도1동대림). 국토부 단지 고유번호(aptSeq)가 있으면 그것을 키로 쓴다.
키는 불투명 문자열이다 — aptSeq 앞자리가 내부 시군구 코드와 다를 수 있으므로
(실측 331건) 시군구는 항상 sgg_cd 칼럼에서 읽는다.
"""

from __future__ import annotations

from typing import NamedTuple

KEY_METHOD_API = "api"
KEY_METHOD_INFER_SINGLE = "infer_single"
KEY_METHOD_INFER_YEAR = "infer_year"
KEY_METHOD_INFER_YEAR_AREA = "infer_year_area"
KEY_METHOD_INFER_AREA = "infer_area"
KEY_METHOD_API_BACKFILL = "api_backfill"

# 거래 테이블 쓰기 상호 배제 — 거래 배치(batch.run --type trade)와
# 키 변경(batch.rekey_trades)이 같은 행을 동시에 바꾸지 않게 한다. ADR 번호에서 딴 고정값.
TRADE_WRITE_LOCK_ID = 15001

PNU_LENGTH = 19
_MOUNTAIN_LAND_CD = "2"


class TradeKey(NamedTuple):
    apt_seq: str
    legacy_apt_seq: str | None
    apt_seq_method: str | None


def name_key(sgg: str, apt_nm: str) -> str:
    """기존 이름 조합 키."""
    return f"{sgg}_{apt_nm}"


def resolve_trade_key(sgg: str, apt_nm: str, api_apt_seq: str | None) -> TradeKey:
    """적재 행의 키. aptSeq 가 비어 있으면 이름 키를 쓴다."""
    legacy = name_key(sgg, apt_nm)
    api = (api_apt_seq or "").strip()
    if api:
        return TradeKey(api, legacy, KEY_METHOD_API)
    return TradeKey(legacy, None, None)


def address_pnu(sgg, umd_cd, land_cd, bonbun, bubun) -> str | None:
    """거래 주소 필드로 만든 19자리 PNU. 필드가 부족하거나 숫자가 아니면 None."""
    if not (sgg and umd_cd and bonbun):
        return None
    mountain = "1" if str(land_cd) == _MOUNTAIN_LAND_CD else "0"
    pnu = f"{sgg}{umd_cd}{mountain}{str(bonbun).zfill(4)}{str(bubun or '0').zfill(4)}"
    if len(pnu) != PNU_LENGTH or not pnu.isdigit():
        return None
    return pnu


def try_trade_write_lock(conn) -> bool:
    """세션 advisory lock. 다른 세션이 잡고 있으면 즉시 False."""
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", [TRADE_WRITE_LOCK_ID])
    return bool(cur.fetchone()[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_keys -v`
Expected: PASS (12 tests)

- [ ] **Step 5: 스키마 칼럼 추가** — `web/backend/database.py` 의 `-- 기존 레거시 테이블에 누락 컬럼 추가` 블록 마지막 `ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS avg_supply_area …;` 다음 줄에:

```sql
        -- ADR-015 거래 키 전환: 이름 키 보존·키 결정 방법·전월세 준공연도
        ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS legacy_apt_seq TEXT;
        ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS apt_seq_method TEXT;
        ALTER TABLE rent_history ADD COLUMN IF NOT EXISTS legacy_apt_seq TEXT;
        ALTER TABLE rent_history ADD COLUMN IF NOT EXISTS apt_seq_method TEXT;
        ALTER TABLE rent_history ADD COLUMN IF NOT EXISTS build_year INTEGER;
```
(Task 1 에서 buildYear 없음이면 마지막 줄 생략)

- [ ] **Step 6: 로컬 스키마 적용 확인**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom/web/backend
../../.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('../../.env')
from database import get_connection, create_tables
c = get_connection(use_pool=False); create_tables(c); c.close()
c = get_connection(use_pool=False); cur = c.cursor()
cur.execute(\"SELECT table_name, column_name FROM information_schema.columns WHERE column_name IN ('legacy_apt_seq','apt_seq_method','build_year') AND table_name IN ('trade_history','rent_history') ORDER BY 1,2\")
print(cur.fetchall()); c.close()"
```
Expected: `trade_history` 2개(+기존 build_year), `rent_history` 3개 칼럼 출력.

- [ ] **Step 7: Commit**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
uvx ruff format batch/trade/trade_keys.py scripts/tests/test_trade_keys.py
git add batch/trade/trade_keys.py scripts/tests/test_trade_keys.py web/backend/database.py
git commit -m "feat(batch): 거래 키 규칙 모듈 + legacy_apt_seq·apt_seq_method 칼럼 (ADR-015)"
```

---

### Task 3: 적재가 새 키 규칙을 쓰도록

**Files:**
- Modify: `batch/trade/load_trades.py` (매매 94행·INSERT 124~130행, 전월세 186행·INSERT 214~220행)
- Test: `scripts/tests/test_load_trades_keys.py`

**Interfaces:**
- Consumes: `resolve_trade_key` (Task 2)
- Produces: 적재 행에 `apt_seq`·`legacy_apt_seq`·`apt_seq_method`(·전월세 `build_year`) 기록

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_load_trades_keys.py`

```python
"""load_trades 가 ADR-015 키 규칙으로 행을 만드는지 — DB 없이 SQL·행 캡처."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade import load_trades as mod  # noqa: E402


class _Logger:
    def info(self, *_a, **_k):
        pass


def _trade(apt_seq_api):
    return {
        "sggCd": "11590", "aptNm": "대림아파트", "excluUseAr": "84.89", "floor": "13",
        "dealYear": "2026", "dealMonth": "7", "dealDay": "2", "dealAmount": "105,000",
        "buildYear": "1995", "aptSeq": apt_seq_api,
    }


def _rent(apt_seq_api):
    return {
        "sggCd": "11590", "aptNm": "대림아파트", "excluUseAr": "84.89", "floor": "13",
        "dealYear": "2026", "dealMonth": "7", "dealDay": "2", "deposit": "50,000",
        "monthlyRent": "0", "buildYear": "1995", "aptSeq": apt_seq_api,
    }


class LoadTradesKeyTest(unittest.TestCase):
    def _run(self, trade_rows, rent_rows):
        captured = []

        def fake_exec(conn, sql, rows, chunk_size=10000):
            captured.append((sql, rows))
            return len(rows)

        with patch.object(mod, "query_all", return_value=[]), \
             patch.object(mod, "load_aliases", return_value={}), \
             patch.object(mod, "execute_values_chunked", fake_exec):
            mod.load_trades(None, trade_rows, rent_rows, _Logger())
        return captured

    def test_trade_with_api_seq_uses_it(self):
        (sql, rows), = self._run([_trade("11590-85")], [])
        self.assertIn("legacy_apt_seq, apt_seq_method", sql)
        row = rows[0]
        self.assertEqual(row[0], "11590-85")
        self.assertEqual(row[-2:], ("11590_대림아파트", "api"))

    def test_trade_without_api_seq_keeps_name_key(self):
        (sql, rows), = self._run([_trade("")], [])
        self.assertEqual(rows[0][0], "11590_대림아파트")
        self.assertEqual(rows[0][-2:], (None, None))

    def test_rent_with_api_seq_and_build_year(self):
        (sql, rows), = self._run([], [_rent("11590-85")])
        self.assertIn("build_year", sql)
        row = rows[0]
        self.assertEqual(row[0], "11590-85")
        self.assertEqual(row[-3:], (1995, "11590_대림아파트", "api"))


if __name__ == "__main__":
    unittest.main()
```
(Task 1 에서 buildYear 없음이면 세 번째 테스트의 `build_year` 단언과 `row[-3]` 을 빼고 `row[-2:]` 만 검사)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_load_trades_keys -v`
Expected: FAIL — 첫 테스트에서 `"legacy_apt_seq, apt_seq_method"` 가 SQL 에 없음

- [ ] **Step 3: 매매 적재 수정** — `load_trades.py` 상단 import 에 추가:

```python
from batch.trade.trade_keys import resolve_trade_key
```

매매 루프의 `apt_seq = f"{sgg}_{apt_nm}"` 를 다음으로 교체:

```python
            key = resolve_trade_key(sgg, apt_nm, r.get("aptSeq"))
```

`new_rows.append((` 튜플의 첫 원소 `apt_seq,` 를 `key.apt_seq,` 로, 마지막 원소 `r.get("aptSeq") or None,` 뒤에 두 줄 추가:

```python
                    key.legacy_apt_seq,
                    key.apt_seq_method,
```

※ 기존 코드에 이미 중복 판정용 `key = (sgg, apt_nm, exclu, …)` 변수가 있다. 이름 충돌을 피하려고 중복 판정 변수를 `dedup_key` 로 바꾼다(정의와 `if key in existing_keys` 두 곳).

INSERT 문 칼럼 목록 끝 `…, rgst_date, api_apt_seq)` 를 `…, rgst_date, api_apt_seq, legacy_apt_seq, apt_seq_method)` 로 바꾼다.

- [ ] **Step 4: 전월세 적재 수정** — 같은 방식으로 전월세 루프의 중복 판정 변수를 `dedup_key` 로, `apt_seq = f"{sgg}_{apt_nm}"` 를 `key = resolve_trade_key(sgg, apt_nm, r.get("aptSeq"))` 로, 튜플 첫 원소를 `key.apt_seq,` 로, 마지막 `r.get("aptSeq") or None,` 뒤에:

```python
                    _to_int(r.get("buildYear")),
                    key.legacy_apt_seq,
                    key.apt_seq_method,
```

INSERT 칼럼 목록 끝 `…, use_rr_right, api_apt_seq)` → `…, use_rr_right, api_apt_seq, build_year, legacy_apt_seq, apt_seq_method)`.

모듈 상단 주석(40행 부근 "apt_seq 가 "{sgg}_{apt_nm}" 조합이라…")을 다음으로 고친다:

```python
    # 이름 키 "{sgg}_{apt_nm}"(aptSeq 없을 때의 키, legacy_apt_seq)가 시군구 코드를
    # 포함하므로 여기서 접어야 하류(매핑·등록)까지 구코드로 일관된다.
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m unittest scripts.tests.test_load_trades_keys scripts.tests.test_trade_keys -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uvx ruff format batch/trade/load_trades.py scripts/tests/test_load_trades_keys.py
git add batch/trade/load_trades.py scripts/tests/test_load_trades_keys.py
git commit -m "feat(batch): 거래 적재 키를 국토부 aptSeq 로 (없으면 이름 키)"
```

---

### Task 4: 과거 행 추론 (순수 함수)

**Files:**
- Create: `batch/trade/trade_key_inference.py`
- Test: `scripts/tests/test_trade_key_inference.py`

**Interfaces:**
- Consumes: `KEY_METHOD_INFER_*` (Task 2)
- Produces:
  - `KnownRow(NamedTuple)`: `legacy_key: str`, `api_apt_seq: str`, `build_year: int | None`, `area: float | None`
  - `TargetRow(NamedTuple)`: `row_id: int`, `legacy_key: str`, `build_year: int | None`, `area: float | None`
  - `Inference(NamedTuple)`: `api_apt_seq: str`, `method: str`
  - `infer_keys(known: Iterable[KnownRow], targets: Iterable[TargetRow], use_build_year: bool) -> dict[int, Inference]`
  - `AREA_PRECISION = 2`

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_trade_key_inference.py`

```python
"""과거 거래 → 국토부 고유번호 추론 규칙 (설계 4-3) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_key_inference import (  # noqa: E402
    Inference,
    KnownRow,
    TargetRow,
    infer_keys,
)

L = "11590_대림아파트"
DAEBANG, SANGDO = "11590-57", "11590-85"

# 혼입 키: 대방(1993, 59.84·84.92) + 상도(1995, 66.59·84.89)
MIXED_KNOWN = [
    KnownRow(L, DAEBANG, 1993, 84.92),
    KnownRow(L, DAEBANG, 1993, 59.84),
    KnownRow(L, SANGDO, 1995, 84.89),
    KnownRow(L, SANGDO, 1995, 66.59),
]


class TradeInferenceTest(unittest.TestCase):
    def test_single_id_key_with_matching_year(self):
        known = [KnownRow("K", "1-1", 2005, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", 2005, 59.0)], use_build_year=True)
        self.assertEqual(out, {1: Inference("1-1", "infer_single")})

    def test_single_id_key_with_other_year_is_left_alone(self):
        known = [KnownRow("K", "1-1", 2005, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", 1980, 84.0)], use_build_year=True)
        self.assertEqual(out, {})

    def test_mixed_key_resolved_by_year(self):
        targets = [TargetRow(1, L, 1993, 114.0), TargetRow(2, L, 1995, 66.59)]
        out = infer_keys(MIXED_KNOWN, targets, use_build_year=True)
        self.assertEqual(out[1], Inference(DAEBANG, "infer_year"))
        self.assertEqual(out[2], Inference(SANGDO, "infer_year"))

    def test_mixed_key_same_year_resolved_by_area(self):
        known = [KnownRow("M", "A", 2000, 59.0), KnownRow("M", "B", 2000, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.0)], use_build_year=True)
        self.assertEqual(out, {1: Inference("B", "infer_year_area")})

    def test_mixed_key_ambiguous_is_left_alone(self):
        known = [KnownRow("M", "A", 2000, 84.0), KnownRow("M", "B", 2000, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.0)], use_build_year=True)
        self.assertEqual(out, {})

    def test_key_never_seen_with_id_is_left_alone(self):
        out = infer_keys(MIXED_KNOWN, [TargetRow(1, "other", 1993, 84.92)], use_build_year=True)
        self.assertEqual(out, {})

    def test_area_noise_is_rounded(self):
        # Review Focus 2 — 84.9234 와 84.92 는 같은 서명
        known = [KnownRow("M", "A", 2000, 84.9234), KnownRow("M", "B", 2000, 59.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.92)], use_build_year=True)
        self.assertEqual(out, {1: Inference("A", "infer_year_area")})


class RentInferenceTest(unittest.TestCase):
    def test_single_id_key_seen_area(self):
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, 84.0)], use_build_year=False)
        self.assertEqual(out, {1: Inference("1-1", "infer_single")})

    def test_single_id_key_unseen_area_is_left_alone(self):
        # Review Focus 5 — 관측 안 된 면적은 추측하지 않는다
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, 135.0)], use_build_year=False)
        self.assertEqual(out, {})

    def test_mixed_key_resolved_by_area(self):
        out = infer_keys(MIXED_KNOWN, [TargetRow(1, L, None, 66.59)], use_build_year=False)
        self.assertEqual(out, {1: Inference(SANGDO, "infer_area")})

    def test_mixed_key_shared_area_is_left_alone(self):
        known = [KnownRow("M", "A", None, 84.0), KnownRow("M", "B", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", None, 84.0)], use_build_year=False)
        self.assertEqual(out, {})

    def test_none_area_target_is_left_alone(self):
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, None)], use_build_year=False)
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_key_inference -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation** — `batch/trade/trade_key_inference.py`

```python
"""과거 거래 행 → 국토부 고유번호 추론 (설계 4-3). DB 접근 없음.

기존 이름 키 안에서 고유번호가 있는 행(known)으로 서명을 학습하고, 고유번호가 없는 행
(target)이 **유일하게** 한 번호를 가리킬 때만 그 번호를 돌려준다. 모호하면 결과에서
빠진다(호출자는 이름 키를 그대로 둔다 — 기존 매핑 그대로라 현재보다 나빠지지 않는다).

서명: 매매 = 준공연도 → 준공연도+면적, 전월세 = 면적(전월세 과거분에는 준공연도가 없다).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from batch.trade.trade_keys import (
    KEY_METHOD_INFER_AREA,
    KEY_METHOD_INFER_SINGLE,
    KEY_METHOD_INFER_YEAR,
    KEY_METHOD_INFER_YEAR_AREA,
)

# 면적 서명 비교 자리수 — 같은 주택형이 행마다 84.9234 / 84.92 로 기록되는 경우를 묶는다.
# 다른 단지 주택형 간 최소 차이(실측 84.89 vs 84.92)보다 거칠면 안 된다.
AREA_PRECISION = 2


class KnownRow(NamedTuple):
    legacy_key: str
    api_apt_seq: str
    build_year: int | None
    area: float | None


class TargetRow(NamedTuple):
    row_id: int
    legacy_key: str
    build_year: int | None
    area: float | None


class Inference(NamedTuple):
    api_apt_seq: str
    method: str


def _area(value: float | None) -> float | None:
    return None if value is None else round(float(value), AREA_PRECISION)


def _only(ids: set[str]) -> str | None:
    return next(iter(ids)) if len(ids) == 1 else None


def infer_keys(
    known: Iterable[KnownRow], targets: Iterable[TargetRow], use_build_year: bool
) -> dict[int, Inference]:
    ids_by_key: dict[str, set[str]] = defaultdict(set)
    by_year: dict[tuple, set[str]] = defaultdict(set)
    by_year_area: dict[tuple, set[str]] = defaultdict(set)
    by_area: dict[tuple, set[str]] = defaultdict(set)
    for k in known:
        area = _area(k.area)
        ids_by_key[k.legacy_key].add(k.api_apt_seq)
        by_year[(k.legacy_key, k.build_year)].add(k.api_apt_seq)
        by_year_area[(k.legacy_key, k.build_year, area)].add(k.api_apt_seq)
        by_area[(k.legacy_key, area)].add(k.api_apt_seq)

    out: dict[int, Inference] = {}
    for t in targets:
        ids = ids_by_key.get(t.legacy_key)
        if not ids:
            continue
        area = _area(t.area)
        if use_build_year:
            result = _infer_trade(t, ids, area, by_year, by_year_area)
        else:
            result = _infer_rent(t, ids, area, by_area)
        if result:
            out[t.row_id] = result
    return out


def _infer_trade(t, ids, area, by_year, by_year_area) -> Inference | None:
    year_ids = by_year.get((t.legacy_key, t.build_year), set())
    if len(ids) == 1:
        return Inference(_only(ids), KEY_METHOD_INFER_SINGLE) if year_ids else None
    hit = _only(year_ids)
    if hit:
        return Inference(hit, KEY_METHOD_INFER_YEAR)
    hit = _only(by_year_area.get((t.legacy_key, t.build_year, area), set()))
    return Inference(hit, KEY_METHOD_INFER_YEAR_AREA) if hit else None


def _infer_rent(t, ids, area, by_area) -> Inference | None:
    if area is None:
        return None
    area_ids = by_area.get((t.legacy_key, area), set())
    if len(ids) == 1:
        return Inference(_only(ids), KEY_METHOD_INFER_SINGLE) if area_ids else None
    hit = _only(area_ids)
    return Inference(hit, KEY_METHOD_INFER_AREA) if hit else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_key_inference -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
uvx ruff format batch/trade/trade_key_inference.py scripts/tests/test_trade_key_inference.py
git add batch/trade/trade_key_inference.py scripts/tests/test_trade_key_inference.py
git commit -m "feat(batch): 과거 거래 고유번호 추론 규칙 (순수 함수)"
```

---

### Task 5: 새 키 → PNU 매핑

**Files:**
- Create: `batch/trade/trade_key_mapping.py`
- Modify: `batch/trade/recalc_price.py` (`_update_mapping` 의 미매핑 조회, 29~37행)
- Test: `scripts/tests/test_trade_key_mapping.py`

**Interfaces:**
- Consumes: `address_pnu`, `KEY_METHOD_*` (Task 2), `recalc_price._normalize_name`, `recalc_price._core_name`
- Produces:
  - `MappingInput(NamedTuple)`: `apt_nm: str`, `legacy_pnus: frozenset[str]`, `address_pnu: str | None`, `name_candidates: tuple[tuple[str, str], ...]` (pnu, bld_nm)
  - `decide_mapping(inp: MappingInput) -> tuple[str, str] | None` — (pnu, match_method)
  - `map_api_keys(conn, logger, apt_seqs: list[str] | None = None) -> int` — 새 매핑 수. **커밋하지 않는다**(호출자가 커밋).

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_trade_key_mapping.py`

```python
"""새 키(국토부 고유번호) → PNU 매핑 순위 (설계 4-2) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_key_mapping import MappingInput, decide_mapping  # noqa: E402

DAEBANG = "1159010800005010000"
SANGDO = "1159010200004110000"


def inp(legacy=(), addr=None, cands=(), apt_nm="대림아파트"):
    return MappingInput(apt_nm, frozenset(legacy), addr, tuple(cands))


class DecideMappingTest(unittest.TestCase):
    def test_rank1_inherits_single_legacy_pnu(self):
        self.assertEqual(
            decide_mapping(inp(legacy=[DAEBANG], addr=SANGDO)),
            (DAEBANG, "api_inherit_legacy"),
        )

    def test_conflicting_legacy_pnus_skip_inheritance(self):
        # Review Focus 3 — 이름 변형 키 둘이 다른 PNU 면 상속하지 않는다
        self.assertEqual(
            decide_mapping(inp(legacy=[DAEBANG, SANGDO], addr=SANGDO)),
            (SANGDO, "api_address_pnu"),
        )

    def test_rank2_address_pnu(self):
        self.assertEqual(decide_mapping(inp(addr=SANGDO)), (SANGDO, "api_address_pnu"))

    # 기대값은 recalc_price._normalize_name/_core_name 실측(2026-10-13)에 맞춘 것:
    # "상도 대림"→norm "상도대림" / "대방대림아파트"→norm 그대로·core "대방대림" / "대림아파트 "→core "대림"
    def test_rank3_exact_name_in_dong(self):
        cands = [(SANGDO, "상도 대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="상도대림")), (SANGDO, "api_name_exact")
        )

    def test_rank3_contains_unique(self):
        cands = [(DAEBANG, "대방대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="대방대림아파트")),
            (DAEBANG, "api_name_contains"),
        )

    def test_rank3_core_unique(self):
        cands = [(SANGDO, "대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="대림아파트 ")), (SANGDO, "api_name_core")
        )

    def test_rank3_same_name_twice_in_dong_is_unmapped(self):
        # 기존 이름 매칭은 정확 일치에서 첫 후보를 골랐다 — 동명 단지 혼입의 원인과 같다.
        cands = [(DAEBANG, "대림"), (SANGDO, "대림")]
        self.assertIsNone(decide_mapping(inp(cands=cands, apt_nm="대림")))

    def test_rank4_nothing_is_unmapped(self):
        self.assertIsNone(decide_mapping(inp()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_key_mapping -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation** — `batch/trade/trade_key_mapping.py`

```python
"""새 키(국토부 고유번호) → PNU 매핑 (설계 4-2).

원칙: 혼입이 증명된 키만 귀속을 바꾸고 나머지는 기존 이름 키의 매핑을 상속한다 —
manual_fix·ADR-011·ADR-014 교정을 잃지 않기 위해서다. 판정 실패 시 아무 단지에나
붙이지 않는다(미매핑으로 남기고 로그 — enrich_new_apartments 가 단지 등록을 시도한다).

순위: 1 상속(이름 키 안 고유번호가 이 키 하나뿐이고 PNU 하나) → 2 주소 PNU →
3 같은 법정동 이름 매칭(정확·포함·핵심명, 유일할 때만) → 4 미매핑.
"""

from __future__ import annotations

from typing import NamedTuple

import psycopg2.extras

from batch.db import query_all
from batch.trade.recalc_price import _core_name, _normalize_name
from batch.trade.trade_keys import address_pnu

MIN_CONTAINS_LEN = 3  # recalc_price 포함 매칭과 같은 하한
MIN_CORE_LEN = 2


class MappingInput(NamedTuple):
    apt_nm: str
    legacy_pnus: frozenset[str]
    address_pnu: str | None
    name_candidates: tuple[tuple[str, str], ...]


def decide_mapping(inp: MappingInput) -> tuple[str, str] | None:
    if len(inp.legacy_pnus) == 1:
        return next(iter(inp.legacy_pnus)), "api_inherit_legacy"
    if inp.address_pnu:
        return inp.address_pnu, "api_address_pnu"
    return _match_name(inp.apt_nm, inp.name_candidates)


def _match_name(apt_nm: str, candidates) -> tuple[str, str] | None:
    norm, core = _normalize_name(apt_nm), _core_name(apt_nm)
    cands = [(pnu, _normalize_name(nm), _core_name(nm)) for pnu, nm in candidates]
    # 정확 일치도 유일할 때만 — 같은 법정동 동명 단지 둘이면 고르지 않는다
    # (recalc_price 의 이름 매칭은 첫 후보를 골라 혼입을 만들 수 있다).
    found = [pnu for pnu, c_norm, _ in cands if c_norm and c_norm == norm]
    if len(found) == 1:
        return found[0], "api_name_exact"
    if norm:
        found = [
            pnu for pnu, c_norm, _ in cands
            if c_norm and len(min(norm, c_norm, key=len)) >= MIN_CONTAINS_LEN
            and (norm in c_norm or c_norm in norm)
        ]
        if len(found) == 1:
            return found[0], "api_name_contains"
    if core and len(core) >= MIN_CORE_LEN:
        found = [pnu for pnu, _, c_core in cands if c_core == core]
        if len(found) == 1:
            return found[0], "api_name_core"
    return None


# ── DB 래퍼 ──

_UNMAPPED_SQL = """
    SELECT DISTINCT ON (apt_seq) apt_seq, legacy_apt_seq, sgg_cd, apt_nm,
           umd_cd, land_cd, bonbun, bubun
    FROM (
        SELECT apt_seq, legacy_apt_seq, sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun
        FROM trade_history t
        WHERE apt_seq_method IS NOT NULL {seq_filter}
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
        UNION ALL
        SELECT apt_seq, legacy_apt_seq, sgg_cd, apt_nm, NULL, NULL, NULL, NULL
        FROM rent_history r
        WHERE apt_seq_method IS NOT NULL {seq_filter}
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
    ) u
    ORDER BY apt_seq, umd_cd NULLS LAST
"""

# 이름 키별 관측된 고유번호(API 원본만) — 상속 조건 "고유번호가 이 키 하나뿐" 판정용
_LEGACY_IDS_SQL = """
    SELECT lk, ARRAY_AGG(DISTINCT api_apt_seq) AS ids FROM (
        SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, api_apt_seq FROM trade_history
        WHERE api_apt_seq IS NOT NULL
          AND (legacy_apt_seq = ANY(%(lks)s) OR apt_seq = ANY(%(lks)s))
        UNION ALL
        SELECT COALESCE(legacy_apt_seq, apt_seq), api_apt_seq FROM rent_history
        WHERE api_apt_seq IS NOT NULL
          AND (legacy_apt_seq = ANY(%(lks)s) OR apt_seq = ANY(%(lks)s))
    ) x GROUP BY lk
"""


def map_api_keys(conn, logger, apt_seqs: list[str] | None = None) -> int:
    """매핑 없는 새 키를 판정해 trade_apt_mapping 에 넣는다. 커밋하지 않는다."""
    seq_filter = "AND apt_seq = ANY(%(seqs)s)" if apt_seqs else ""
    params = {"seqs": list(apt_seqs)} if apt_seqs else {}
    rows = query_all(conn, _UNMAPPED_SQL.format(seq_filter=seq_filter), params or None)
    if not rows:
        return 0

    legacy_keys = sorted({r["legacy_apt_seq"] for r in rows if r["legacy_apt_seq"]})
    ids_by_legacy = {
        r["lk"]: set(r["ids"])
        for r in query_all(conn, _LEGACY_IDS_SQL, {"lks": legacy_keys})
    } if legacy_keys else {}
    legacy_pnu = {
        r["apt_seq"]: r["pnu"]
        for r in query_all(
            conn, "SELECT apt_seq, pnu FROM trade_apt_mapping WHERE apt_seq = ANY(%s)",
            [legacy_keys],
        )
    } if legacy_keys else {}

    addr = {
        r["apt_seq"]: address_pnu(r["sgg_cd"], r["umd_cd"], r["land_cd"], r["bonbun"], r["bubun"])
        for r in rows
    }
    addr_values = sorted({p for p in addr.values() if p})
    existing_pnus = {
        r["pnu"] for r in query_all(
            conn, "SELECT pnu FROM apartments WHERE pnu = ANY(%s)", [addr_values]
        )
    } if addr_values else set()

    bjds = sorted({f"{r['sgg_cd']}{r['umd_cd']}" for r in rows if r["umd_cd"]})
    cands_by_bjd: dict[str, list[tuple[str, str]]] = {}
    if bjds:
        for a in query_all(
            conn,
            "SELECT pnu, COALESCE(display_name, bld_nm) AS nm, bjd_code FROM apartments "
            "WHERE bjd_code = ANY(%s) AND pnu NOT LIKE 'TRADE%%'",
            [bjds],
        ):
            cands_by_bjd.setdefault(a["bjd_code"], []).append((a["pnu"], a["nm"] or ""))

    new_rows, unmapped = [], []
    for r in rows:
        key, lk = r["apt_seq"], r["legacy_apt_seq"]
        single = lk and ids_by_legacy.get(lk) == {key} and lk in legacy_pnu
        a_pnu = addr.get(key)
        decision = decide_mapping(MappingInput(
            apt_nm=r["apt_nm"] or "",
            legacy_pnus=frozenset([legacy_pnu[lk]]) if single else frozenset(),
            address_pnu=a_pnu if a_pnu in existing_pnus else None,
            name_candidates=tuple(cands_by_bjd.get(f"{r['sgg_cd']}{r['umd_cd']}", ()))
            if r["umd_cd"] else (),
        ))
        if decision:
            new_rows.append((key, decision[0], r["apt_nm"], r["sgg_cd"], decision[1]))
        else:
            unmapped.append(key)

    if new_rows:
        psycopg2.extras.execute_values(
            conn.cursor(),
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
            "VALUES %s ON CONFLICT (apt_seq) DO NOTHING",
            new_rows,
        )
    logger.info(f"  고유번호 키 매핑 {len(new_rows):,}건, 미매핑 {len(unmapped):,}건")
    if unmapped:
        logger.warning(f"  미매핑 고유번호 키(최대 50): {unmapped[:50]}")
    return len(new_rows)
```

> 같은 키가 여러 이름 키에 걸치는 경우(이름 변형 6건)는 `DISTINCT ON` 이 대표 1행만 보므로 상속 대상이 하나로 정해진다. 이름 변형 키 둘이 서로 다른 PNU 인 경우를 정확히 반영하려면 대표 행 하나가 아니라 모든 `legacy_apt_seq` 를 모아야 한다 — Step 3b 에서 반영한다.

- [ ] **Step 3b: 이름 변형 키 전체 반영** — `_UNMAPPED_SQL` 결과와 별도로 키별 이름 키 집합을 모은다. `map_api_keys` 의 `rows = …` 다음에 추가:

```python
    lks_by_key: dict[str, set[str]] = {}
    for r in query_all(
        conn,
        "SELECT DISTINCT apt_seq, legacy_apt_seq FROM trade_history "
        "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL "
        "UNION SELECT DISTINCT apt_seq, legacy_apt_seq FROM rent_history "
        "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL",
        {"s": [r["apt_seq"] for r in rows]},
    ):
        lks_by_key.setdefault(r["apt_seq"], set()).add(r["legacy_apt_seq"])
```

`legacy_keys = …` 를 `legacy_keys = sorted(set().union(*lks_by_key.values())) if lks_by_key else []` 로 바꾸고, 루프 안의 `single = …` / `legacy_pnus=…` 두 줄을 다음으로 교체:

```python
        inherit = {
            legacy_pnu[lk]
            for lk in lks_by_key.get(key, ())
            if ids_by_legacy.get(lk) == {key} and lk in legacy_pnu
        }
```
```python
            legacy_pnus=frozenset(inherit),
```
(이제 서로 다른 PNU 두 개면 `decide_mapping` 1순위가 건너뛴다 — Review Focus 3.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest scripts.tests.test_trade_key_mapping -v`
Expected: PASS (8 tests)

- [ ] **Step 5: 이름 매핑이 새 키를 건드리지 않게** — `batch/trade/recalc_price.py` `_update_mapping` 의 미매핑 조회 두 SELECT 각각의 `WHERE NOT EXISTS (…)` 앞에 조건을 넣는다:

```python
    # 새 키(apt_seq_method 가 있는 행)는 trade_key_mapping.map_api_keys 가 담당한다 —
    # 여기서 이름으로 매칭하면 동명 단지 혼입이 되살아난다 (ADR-015).
    unmapped = query_all(conn, """
        SELECT DISTINCT t.apt_seq, t.sgg_cd, t.apt_nm
        FROM trade_history t
        WHERE t.apt_seq_method IS NULL
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
        UNION
        SELECT DISTINCT r.apt_seq, r.sgg_cd, r.apt_nm
        FROM rent_history r
        WHERE r.apt_seq_method IS NULL
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
    """)
```

- [ ] **Step 6: 로컬 DB 스모크** (읽기 + 롤백)

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
.venv/bin/python - <<'EOF'
from dotenv import load_dotenv; load_dotenv(".env")
from batch.db import get_connection
from batch.logger import setup_logger
from batch.trade.trade_key_mapping import map_api_keys
conn = get_connection()
print("mapped:", map_api_keys(conn, setup_logger("smoke")))
conn.rollback(); conn.close()
EOF
```
Expected: 예외 없이 건수 출력(로컬은 아직 새 키 행이 없어 0 이 정상).

- [ ] **Step 7: Commit**

```bash
uvx ruff format batch/trade/trade_key_mapping.py scripts/tests/test_trade_key_mapping.py batch/trade/recalc_price.py
git add batch/trade/trade_key_mapping.py scripts/tests/test_trade_key_mapping.py batch/trade/recalc_price.py
git commit -m "feat(batch): 고유번호 키 → PNU 매핑 (상속·주소·법정동 이름), 이름 매핑은 이름 키만"
```

---

### Task 6: 거래 배치 연결 (잠금 + 새 키 매핑 단계)

**Files:**
- Modify: `batch/run.py` (`run_trade`)
- Test: `scripts/tests/test_run_trade_lock.py`

**Interfaces:**
- Consumes: `try_trade_write_lock` (Task 2), `map_api_keys` (Task 5)

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_run_trade_lock.py`

```python
"""거래 배치는 키 변경 스크립트가 잠금을 쥐고 있으면 실패로 기록하고 멈춘다 (Review Focus 4)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch import run as mod  # noqa: E402


class RunTradeLockTest(unittest.TestCase):
    def test_busy_lock_records_critical_and_skips_collection(self):
        result = MagicMock()
        conn = MagicMock()
        with patch.object(mod, "get_connection", return_value=conn), \
             patch("batch.trade.trade_keys.try_trade_write_lock", return_value=False), \
             patch("batch.trade.collect_trades.collect_trades") as collect:
            mod.run_trade(SimpleNamespace(dry_run=False), MagicMock(), result)
        collect.assert_not_called()
        status = result.record.call_args[0][1]
        self.assertEqual(status, "critical")
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_run_trade_lock -v`
Expected: FAIL — `collect` 가 호출됨

- [ ] **Step 3: Implement** — `run_trade` 의 import 블록에 추가:

```python
    from batch.trade.trade_keys import try_trade_write_lock
    from batch.trade.trade_key_mapping import map_api_keys
```

`conn = get_connection()` / `try:` 바로 다음, `# 1. 수집` 앞에:

```python
        # 키 변경(batch.rekey_trades)과 동시에 거래 테이블을 쓰지 않는다 (ADR-015).
        # 조용히 진행하면 같은 행을 두 쪽이 바꾼다 — 실패로 기록하고 멈춘다.
        if not try_trade_write_lock(conn):
            logger.error("거래 쓰기 잠금 점유 중(키 변경 실행 중) — 이번 회차 중단")
            result.record("거래 쓰기 잠금", "critical", error="rekey_trades 실행 중")
            return
```

`# 3. 가격 점수 재계산` 앞에:

```python
        # 2.5. 고유번호 키 매핑 — recalc_price 의 이름 매핑보다 먼저 (ADR-015)
        t0 = time.time()
        mapped = map_api_keys(conn, logger)
        conn.commit()
        result.record(
            "고유번호 키 매핑", "success", rows=mapped, duration=time.time() - t0
        )
```

(`return` 이 `try` 안이라 기존 `finally: conn.close()` 가 실행된다. 세션 잠금은 연결 종료 시 해제된다.)

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest discover -s scripts/tests -t .`
Expected: OK (기존 테스트 포함 전부 통과)

- [ ] **Step 5: Commit**

```bash
uvx ruff format scripts/tests/test_run_trade_lock.py
git add batch/run.py scripts/tests/test_run_trade_lock.py
git commit -m "feat(batch): 거래 배치에 쓰기 잠금 + 고유번호 키 매핑 단계"
```

---

### Task 7: 키 문자열 파싱 제거 + 동기화 칼럼 + PR 1

**Files:**
- Modify: `scripts/register_missing_apartments.py:548`
- Modify: `batch/sync_from_railway.py:27-36` (`SYNC_TABLES`)
- Test: `scripts/tests/test_trade_keys.py` (추가 케이스), 전수 점검 결과

**Interfaces:**
- Produces: `register_missing_apartments._sgg_of(cur, apt_seq) -> str | None`

- [ ] **Step 1: 키 문자열 가정 전수 점검**

Run:
```bash
cd /Users/wizmain/Documents/workspace/apt-recom
grep -rn "apt_seq" batch scripts web/backend --include='*.py' | grep -v "__pycache__\|/tests/" | grep -E "split\(|partition|\[:5\]|startswith|LIKE|_\{" 
```
Expected: `scripts/register_missing_apartments.py:548` 만 해당(2026-10-13 기준). 다른 줄이 나오면 같은 방식(`sgg_cd` 칼럼 조회)으로 이 Task 에서 함께 고친다.

- [ ] **Step 2: register_missing 수정** — 파일 상단 함수 영역에 추가:

```python
def _sgg_of(cur, apt_seq: str) -> str | None:
    """거래 키의 시군구 — 키는 불투명 문자열이라 문자열로 해석하지 않는다 (ADR-015)."""
    cur.execute(
        "SELECT sgg_cd FROM trade_history WHERE apt_seq = %s "
        "UNION SELECT sgg_cd FROM rent_history WHERE apt_seq = %s LIMIT 1",
        [apt_seq, apt_seq],
    )
    row = cur.fetchone()
    return row["sgg_cd"] if row else None
```

548행 `"sgg_cd": r["apt_seq"].split("_", 1)[0],` → `"sgg_cd": _sgg_of(cur, r["apt_seq"]),`
(이 파일의 `cur` 는 RealDictCursor — 같은 함수 안 530행 `existing = {r["pnu"]: …}` 가 dict 접근을 쓴다.)

- [ ] **Step 3: 동기화 칼럼 추가** — `SYNC_TABLES` 를 다음으로 교체(`created_at` 은 반드시 마지막 — 증분 동기화가 `row[-1]` 로 읽는다):

```python
SYNC_TABLES = [
    (
        "trade_history",
        "apt_seq, sgg_cd, apt_nm, deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day, build_year,"
        " dealing_gbn, api_apt_seq, legacy_apt_seq, apt_seq_method, created_at",
    ),
    (
        "rent_history",
        "apt_seq, sgg_cd, apt_nm, deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day,"
        " build_year, api_apt_seq, legacy_apt_seq, apt_seq_method, created_at",
    ),
]
```
(Task 1 에서 buildYear 없음이면 rent 의 `build_year,` 제거.) 위 주석에 한 줄 추가: `# ADR-015 칼럼과 dealing_gbn 은 2026-10-13 추가 — 이전 행은 full sync 전까지 로컬에 NULL.`

- [ ] **Step 4: 로컬 증분 동기화 스모크**

Run: `.venv/bin/python -m batch.sync_from_railway`
Expected: 오류 없이 완료. (운영에 아직 새 칼럼이 없으면 Railway SELECT 가 실패한다 — **이 Step 은 PR 1 배포 후** 실행하고, 배포 전에는 건너뛴다.)

- [ ] **Step 5: 전체 테스트 + 린트**

Run:
```bash
.venv/bin/python -m unittest discover -s scripts/tests -t .
uvx ruff check batch/trade/trade_keys.py batch/trade/trade_key_inference.py batch/trade/trade_key_mapping.py batch/trade/load_trades.py
```
Expected: OK / 변경 줄 경고 없음

- [ ] **Step 6: Commit + PR 1**

```bash
git add scripts/register_missing_apartments.py batch/sync_from_railway.py
git commit -m "fix(batch): 거래 키 문자열 파싱 제거 + 동기화에 ADR-015 칼럼·dealing_gbn 추가"
git push -u origin feature/trade-key-official-id
gh pr create --base main --title "feat(batch): 거래 키를 국토부 고유번호로 — 적재·매핑 전환 (ADR-015 1단계)" --body "설계: docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md 4-1·4-2. 머지·배포 후 새 거래는 고유번호 키로 들어오고 새 혼입이 멈춘다. 과거 데이터는 2단계(PR 2)."
```

- [ ] **Step 7: 배포 확인 (머지 후, 거래 배치 사이 시간에 머지)**

`railway deployment list --service apt-recom` 로 머지 커밋 배포 SUCCESS 확인, `railway logs --service apt-recom | grep "schema migration"` 에 `완료` 확인 → 다음 거래 배치 로그에서 `고유번호 키 매핑 N건, 미매핑 M건` 확인. 미매핑 목록이 있으면 사용자에게 보고(다음 배치의 `enrich_new_apartments` 가 단지 등록을 시도한다).

---

### Task 8: VACUUM 공용화 + 키 변경 스크립트

**Files:**
- Modify: `batch/db.py` (끝에 `vacuum_tables`), `batch/purge_old_trades.py:138-163`
- Create: `batch/rekey_trades.py`
- Test: `scripts/tests/test_rekey_trades.py`

**Interfaces:**
- Consumes: `infer_keys`, `KnownRow`, `TargetRow` (Task 4), `map_api_keys` (Task 5), `try_trade_write_lock`, `KEY_METHOD_API` (Task 2), `audit` (`batch.trade.audit_mappings`)
- Produces:
  - `vacuum_tables(url: str, tables: list[str], logger, full: bool = False) -> None` (batch/db.py)
  - `plan_sgg(trade_known, trade_api_rows, trade_targets, rent_known, rent_api_rows, rent_targets) -> dict[str, list[tuple[int, str, str]]]` — 테이블별 (id, new_key, method). `*_api_rows` 는 `list[tuple[int, str]]` (id, aptSeq)
  - `check_invariants(before: Snapshot, after: Snapshot, allowed_pnus: set[str], audit_before: int, audit_after: int) -> list[str]` — 실패 사유 목록(빈 목록 = 통과)
  - `Snapshot(NamedTuple)`: `rows: dict[str, int]`, `unmapped: int`, `pnu_counts: dict[str, int]`

- [ ] **Step 1: vacuum 공용화** — `batch/purge_old_trades.py` 의 `_vacuum` 함수 본문을 그대로 `batch/db.py` 끝으로 옮기고 이름을 `vacuum_tables` 로 바꾼다(`import time` 과 `psycopg2` 는 batch/db.py 상단에 추가). purge_old_trades 에서는 `_vacuum` 정의를 지우고 `from batch.db import vacuum_tables` 후 호출부 `_vacuum(` 를 `vacuum_tables(` 로 바꾼다.

Run: `.venv/bin/python -m batch.purge_old_trades --target local --dry-run`
Expected: 기존과 같은 dry-run 출력(동작 불변)

- [ ] **Step 2: Write the failing test** — `scripts/tests/test_rekey_trades.py`

```python
"""키 변경 스크립트의 순수 로직 — 구 단위 계획과 커밋 전 불변식 (설계 4-3·4-5)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.rekey_trades import Snapshot, check_invariants, plan_sgg  # noqa: E402
from batch.trade.trade_key_inference import KnownRow, TargetRow  # noqa: E402

L = "11590_대림아파트"


class PlanSggTest(unittest.TestCase):
    def test_api_rows_and_inferred_rows(self):
        trade_known = [KnownRow(L, "11590-57", 1993, 84.92), KnownRow(L, "11590-85", 1995, 84.89)]
        trade_targets = [TargetRow(1, L, 1993, 114.0), TargetRow(2, L, 2001, 84.0)]
        plan = plan_sgg(
            trade_known=trade_known,
            trade_api_rows=[(9, "11590-85")],
            trade_targets=trade_targets,
            rent_known=trade_known,
            rent_api_rows=[],
            rent_targets=[TargetRow(5, L, None, 84.89)],
        )
        self.assertEqual(
            sorted(plan["trade_history"]),
            [(1, "11590-57", "infer_year"), (9, "11590-85", "api")],
        )
        self.assertEqual(plan["rent_history"], [(5, "11590-85", "infer_area")])


class CheckInvariantsTest(unittest.TestCase):
    def snap(self, rows=10, unmapped=0, pnus=None):
        return Snapshot({"trade_history": rows, "rent_history": rows}, unmapped, pnus or {"A": 5, "B": 5})

    def test_clean_change_passes(self):
        after = self.snap(pnus={"A": 4, "B": 6})
        self.assertEqual(check_invariants(self.snap(), after, {"A", "B"}, 0, 0), [])

    def test_row_count_change_fails(self):
        self.assertTrue(check_invariants(self.snap(), self.snap(rows=9), set(), 0, 0))

    def test_more_unmapped_fails(self):
        self.assertTrue(check_invariants(self.snap(), self.snap(unmapped=1), set(), 0, 0))

    def test_change_outside_allowed_fails(self):
        after = self.snap(pnus={"A": 4, "B": 6})
        self.assertTrue(check_invariants(self.snap(), after, {"A"}, 0, 0))

    def test_audit_increase_fails(self):
        self.assertTrue(check_invariants(self.snap(), self.snap(), set(), 1, 2))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_rekey_trades -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'batch.rekey_trades'`

- [ ] **Step 4: Write implementation** — `batch/rekey_trades.py`

```python
"""과거 거래 키를 국토부 고유번호로 바꾼다 (ADR-015, 설계 4-3·4-4·4-5).

구(sgg) 하나를 한 트랜잭션으로 처리하고, **커밋 전에** 불변식을 검사해 실패하면 그 구를
롤백한다. 원래 키는 legacy_apt_seq 에 남아 사후 롤백(--rollback)도 가능하다.

    python -m batch.rekey_trades --target local --dry-run            # 계획 건수만
    python -m batch.rekey_trades --target local --apply              # 로컬 적용
    python -m batch.rekey_trades --target railway --apply --limit 20 # 운영(사용자 실행)
    python -m batch.rekey_trades --target local --rollback --sgg 11590
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import NamedTuple

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from batch.db import query_all, vacuum_tables
from batch.logger import setup_logger
from batch.trade.audit_mappings import audit
from batch.trade.trade_key_inference import KnownRow, TargetRow, infer_keys
from batch.trade.trade_key_mapping import map_api_keys
from batch.trade.trade_keys import KEY_METHOD_API, try_trade_write_lock

CHECKPOINT_GROUP = "rekey_trades_checkpoint"
TABLES = ("trade_history", "rent_history")
DEFAULT_VACUUM_EVERY = 20  # 구 N개마다 VACUUM (ANALYZE) — 운영 1GB 캡 bloat 완화


class Snapshot(NamedTuple):
    rows: dict[str, int]
    unmapped: int
    pnu_counts: dict[str, int]


def plan_sgg(trade_known, trade_api_rows, trade_targets, rent_known, rent_api_rows, rent_targets):
    """테이블별 (id, new_key, method). *_api_rows 는 이미 고유번호가 있는 이름 키 행 (id, api)."""
    plan = {}
    for table, known, api_rows, targets, use_year in (
        ("trade_history", trade_known, trade_api_rows, trade_targets, True),
        ("rent_history", rent_known, rent_api_rows, rent_targets, False),
    ):
        items = [(rid, api, KEY_METHOD_API) for rid, api in api_rows]
        items += [
            (rid, inf.api_apt_seq, inf.method)
            for rid, inf in infer_keys(known, targets, use_build_year=use_year).items()
        ]
        plan[table] = items
    return plan


def check_invariants(before, after, allowed_pnus, audit_before, audit_after) -> list[str]:
    errors = []
    if before.rows != after.rows:
        errors.append(f"행 수 변화 {before.rows} → {after.rows}")
    if after.unmapped > before.unmapped:
        errors.append(f"미매핑 행 증가 {before.unmapped} → {after.unmapped}")
    changed = {
        p for p in set(before.pnu_counts) | set(after.pnu_counts)
        if before.pnu_counts.get(p, 0) != after.pnu_counts.get(p, 0)
    }
    outside = changed - allowed_pnus
    if outside:
        errors.append(f"혼입 키와 무관한 PNU 귀속 변화 {sorted(outside)[:20]}")
    if audit_after > audit_before:
        errors.append(f"감사 위반 증가 {audit_before} → {audit_after}")
    return errors


# ── DB ──

def _db_url(target: str) -> str:
    url = os.getenv("DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL")
    if not url:
        raise SystemExit(f"{target} DB URL 미설정 (.env 확인)")
    return url


def _sggs(conn) -> list[str]:
    rows = query_all(conn, """
        SELECT sgg_cd, SUM(n) AS n FROM (
            SELECT sgg_cd, COUNT(*) n FROM trade_history GROUP BY 1
            UNION ALL SELECT sgg_cd, COUNT(*) FROM rent_history GROUP BY 1) x
        GROUP BY 1 ORDER BY 2""")  # 작은 구부터 — 초반 실패를 싸게 발견
    return [r["sgg_cd"] for r in rows]


def _known(conn, sgg, table, with_year):
    year = "build_year" if with_year else "NULL::int"
    return [
        KnownRow(r["lk"], r["api_apt_seq"], r["by"], r["area"])
        for r in query_all(conn, f"""
            SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, api_apt_seq, {year} AS by,
                   exclu_use_ar AS area
            FROM {table} WHERE sgg_cd = %s AND api_apt_seq IS NOT NULL""", [sgg])
    ]


def _targets(conn, sgg, table, with_year):
    year = "build_year" if with_year else "NULL::int"
    rows = query_all(conn, f"""
        SELECT id, apt_seq, api_apt_seq, {year} AS by, exclu_use_ar AS area
        FROM {table} WHERE sgg_cd = %s AND apt_seq_method IS NULL""", [sgg])
    api_rows = [(r["id"], r["api_apt_seq"]) for r in rows if r["api_apt_seq"]]
    targets = [TargetRow(r["id"], r["apt_seq"], r["by"], r["area"]) for r in rows if not r["api_apt_seq"]]
    return api_rows, targets


def _snapshot(conn, sgg) -> Snapshot:
    rows, pnu_counts, unmapped = {}, Counter(), 0
    for t in TABLES:
        rows[t] = query_all(conn, f"SELECT COUNT(*) c FROM {t} WHERE sgg_cd = %s", [sgg])[0]["c"]
        for r in query_all(conn, f"""
            SELECT m.pnu, COUNT(*) c FROM {t} x LEFT JOIN trade_apt_mapping m ON m.apt_seq = x.apt_seq
            WHERE x.sgg_cd = %s GROUP BY m.pnu""", [sgg]):
            if r["pnu"] is None:
                unmapped += r["c"]
            else:
                pnu_counts[r["pnu"]] += r["c"]
    return Snapshot(rows, unmapped, dict(pnu_counts))


def _allowed_pnus(conn, sgg, trade_known, rent_known) -> set[str]:
    """귀속이 바뀌어도 되는 PNU — 혼입 이름 키(고유번호 2개+)의 기존 매핑 대상."""
    ids = {}
    for k in list(trade_known) + list(rent_known):
        ids.setdefault(k.legacy_key, set()).add(k.api_apt_seq)
    mixed = sorted(lk for lk, s in ids.items() if len(s) > 1)
    if not mixed:
        return set()
    return {r["pnu"] for r in query_all(
        conn, "SELECT pnu FROM trade_apt_mapping WHERE apt_seq = ANY(%s)", [mixed])}


def _apply(conn, table, items):
    psycopg2.extras.execute_values(conn.cursor(), f"""
        UPDATE {table} t SET legacy_apt_seq = t.apt_seq, apt_seq = v.new_key, apt_seq_method = v.method
        FROM (VALUES %s) AS v(id, new_key, method) WHERE t.id = v.id""",
        items, template="(%s::int, %s, %s)", page_size=5000)


def _save_checkpoint(conn, sgg, status, detail):
    conn.cursor().execute("""
        INSERT INTO common_code (group_id, code, name, extra, sort_order) VALUES (%s, %s, %s, %s, 0)
        ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [CHECKPOINT_GROUP, sgg, status, json.dumps(detail, ensure_ascii=False)])
    conn.commit()


def _done(conn) -> set[str]:
    return {r["code"] for r in query_all(conn,
        "SELECT code FROM common_code WHERE group_id = %s AND name IN ('done', 'failed')",
        [CHECKPOINT_GROUP])}


def rekey_sgg(conn, sgg, logger, apply: bool) -> str:
    tk, rk = _known(conn, sgg, "trade_history", True), _known(conn, sgg, "rent_history", False)
    t_api, t_tg = _targets(conn, sgg, "trade_history", True)
    r_api, r_tg = _targets(conn, sgg, "rent_history", False)
    plan = plan_sgg(tk, t_api, t_tg, tk + rk, r_api, r_tg)
    counts = {t: dict(Counter(m for _, _, m in items)) for t, items in plan.items()}
    logger.info(f"[{sgg}] 계획 {counts}")
    if not apply:
        return "planned"

    allowed = _allowed_pnus(conn, sgg, tk, rk)
    before = _snapshot(conn, sgg)
    audit_before = len(audit(conn, logger, pnus=sorted(allowed))) if allowed else 0
    for table, items in plan.items():
        if items:
            _apply(conn, table, items)
    new_keys = sorted({k for items in plan.values() for _, k, _ in items})
    if new_keys:
        map_api_keys(conn, logger, apt_seqs=new_keys)
        # 상속(api_inherit_legacy)이 아닌 새 매핑은 귀속이 바뀌는 게 정상이다 — 예: 매핑이 없던
        # 상도1동대림이 주소 PNU 로 처음 거래를 갖는다. 혼입 키 기존 PNU 와 함께 허용 목록에 넣는다.
        allowed |= {r["pnu"] for r in query_all(conn, """
            SELECT pnu FROM trade_apt_mapping
            WHERE apt_seq = ANY(%s) AND match_method <> 'api_inherit_legacy'""", [new_keys])}
    after = _snapshot(conn, sgg)
    audit_after = len(audit(conn, logger, pnus=sorted(allowed))) if allowed else 0
    errors = check_invariants(before, after, allowed, audit_before, audit_after)
    if errors:
        conn.rollback()
        logger.error(f"[{sgg}] 검증 실패 → 롤백: {errors}")
        _save_checkpoint(conn, sgg, "failed", {"errors": errors, "plan": counts})
        return "failed"
    conn.commit()
    _save_checkpoint(conn, sgg, "done", {"plan": counts})
    return "done"


def rollback_sgg(conn, sgg, logger):
    """사후 롤백 — 이 구의 모든 키를 이름 키로 되돌리고 남는 고유번호 매핑을 지운다."""
    for t in TABLES:
        conn.cursor().execute(f"""
            UPDATE {t} SET apt_seq = legacy_apt_seq, legacy_apt_seq = NULL, apt_seq_method = NULL
            WHERE sgg_cd = %s AND apt_seq_method IS NOT NULL AND legacy_apt_seq IS NOT NULL""", [sgg])
    conn.cursor().execute(r"""
        DELETE FROM trade_apt_mapping m WHERE m.sgg_cd = %s AND m.match_method LIKE 'api\_%%'
          AND NOT EXISTS (SELECT 1 FROM trade_history t WHERE t.apt_seq = m.apt_seq)
          AND NOT EXISTS (SELECT 1 FROM rent_history r WHERE r.apt_seq = m.apt_seq)""", [sgg])
    conn.commit()
    _save_checkpoint(conn, sgg, "rolled_back", {})
    logger.info(f"[{sgg}] 롤백 완료")


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    p.add_argument("--sgg", action="append", help="대상 시군구(반복 가능). 생략 시 전체")
    p.add_argument("--limit", type=int, default=0, help="이번 실행 최대 구 수")
    p.add_argument("--vacuum-every", type=int, default=DEFAULT_VACUUM_EVERY)
    args = p.parse_args()
    logger = setup_logger("rekey_trades")

    url = _db_url(args.target)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        if not try_trade_write_lock(conn):
            raise SystemExit("거래 배치 실행 중 — 배치 사이 시간에 다시 실행")
        if args.rollback:
            if not args.sgg:
                raise SystemExit("--rollback 은 --sgg 필수")
            for sgg in args.sgg:
                rollback_sgg(conn, sgg, logger)
            return
        todo = args.sgg or [s for s in _sggs(conn) if s not in _done(conn)]
        if args.limit:
            todo = todo[: args.limit]
        summary = Counter()
        for i, sgg in enumerate(todo, 1):
            summary[rekey_sgg(conn, sgg, logger, apply=args.apply)] += 1
            if args.apply and args.vacuum_every and i % args.vacuum_every == 0:
                vacuum_tables(url, list(TABLES) + ["trade_apt_mapping"], logger)
        if args.apply:
            vacuum_tables(url, list(TABLES) + ["trade_apt_mapping"], logger)
        logger.info(f"완료: {dict(summary)} (대상 {len(todo)}개 구)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests**

Run: `.venv/bin/python -m unittest scripts.tests.test_rekey_trades -v` → PASS (6 tests)
Run: `.venv/bin/python -m unittest discover -s scripts/tests -t .` → OK

- [ ] **Step 6: Commit**

```bash
uvx ruff format batch/rekey_trades.py batch/db.py batch/purge_old_trades.py scripts/tests/test_rekey_trades.py
git add batch/rekey_trades.py batch/db.py batch/purge_old_trades.py scripts/tests/test_rekey_trades.py
git commit -m "feat(batch): 과거 거래 키 변경 스크립트 (구 단위·커밋 전 검증·롤백)"
```

---

### Task 9: 로컬 실행·검증 + PR 2 + 운영 런북

**Files:**
- Create: `docs/guides/trade-key-rekey-runbook.md`
- Modify: `CLAUDE.md` (실행 정책 표)

**Interfaces:**
- Consumes: `batch.rekey_trades` CLI (Task 8)

> 선행: PR 1 배포 후 로컬 `--mode full` 동기화가 끝나 있어야 로컬에 고유번호가 충분하다. 운영 칼럼(`legacy_apt_seq` 등)이 생긴 뒤 사용자에게 `.venv/bin/python -m batch.sync_from_railway --mode full` 실행을 요청한다(로컬 전용 변경 유실 확인 먼저 — 현재 `apt_facility_summary` 로컬 +104행, 2026-10-13 임시 분리 `11590_대림아파트(411)`).

- [ ] **Step 1: 로컬 dry-run**

Run: `.venv/bin/python -m batch.rekey_trades --target local --dry-run 2>&1 | tail -5`
Expected: 구별 계획 건수 로그 + `완료: {'planned': N}`. 전체 합계를 설계서 4-3 커버리지 표와 대조(같은 자릿수여야 정상).

- [ ] **Step 2: 로컬 소규모 적용** (사용자 승인 후 — 로컬 DB 데이터 변경)

Run: `.venv/bin/python -m batch.rekey_trades --target local --apply --sgg 11590`
Expected: `[11590] … done`. 실패면 사유 로그를 사용자에게 보고하고 멈춘다.

- [ ] **Step 3: 기준 사례 검증**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom/web/backend
../../.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv('../../.env')
from database import DictConnection
c=DictConnection()
for pnu in ('1159010800005010000','1159010200004110000'):
    print(pnu, [dict(r) for r in c.execute("""SELECT t.build_year, COUNT(*) n FROM trade_history t
      JOIN trade_apt_mapping m ON m.apt_seq=t.apt_seq WHERE m.pnu=%s GROUP BY 1 ORDER BY 1""",[pnu]).fetchall()])
EOF
```
Expected: 대방대림 `1993: 600(±동기화 신규분)`, 상도1동대림 `1995: 130(±)` — 다른 준공연도 섞임 없음.

- [ ] **Step 4: 로컬 전체 적용 + 실행 시간·용량·가격 변화 측정** (사용자 승인 후)

가격 변화 비교용으로 PNU 별 ㎡당 평균(= `recalc_price` 의 price_per_m2 공식, 면적 범위 검증 포함)을 적용 전후 JSON 으로 남긴다. DB 에는 쓰지 않는다.

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
mkdir -p reports/rekey
cat > reports/rekey/ppm2_snapshot.py <<'EOF'
import json, sys
from dotenv import load_dotenv; load_dotenv(".env")
from batch.db import get_connection, query_all
conn = get_connection()
rows = query_all(conn, """
    SELECT m.pnu, AVG(t.deal_amount * 10000.0 / t.exclu_use_ar) AS ppm2, COUNT(*) AS n
    FROM trade_history t JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
    LEFT JOIN apt_area_info ai ON m.pnu = ai.pnu
    WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
      AND (ai.pnu IS NULL OR (t.exclu_use_ar >= ai.min_area * 0.9 AND t.exclu_use_ar <= ai.max_area * 1.1))
    GROUP BY m.pnu""")
json.dump({r["pnu"]: [float(r["ppm2"]), r["n"]] for r in rows}, open(sys.argv[1], "w"))
conn.close()
EOF
.venv/bin/python reports/rekey/ppm2_snapshot.py reports/rekey/ppm2_before.json
psql "$DATABASE_URL" -c "SELECT pg_size_pretty(pg_total_relation_size('trade_history')), pg_size_pretty(pg_total_relation_size('rent_history'))"
time .venv/bin/python -m batch.rekey_trades --target local --apply
psql "$DATABASE_URL" -c "SELECT pg_size_pretty(pg_total_relation_size('trade_history')), pg_size_pretty(pg_total_relation_size('rent_history'))"
.venv/bin/python reports/rekey/ppm2_snapshot.py reports/rekey/ppm2_after.json
.venv/bin/python - <<'EOF'
import json
b, a = json.load(open("reports/rekey/ppm2_before.json")), json.load(open("reports/rekey/ppm2_after.json"))
diff = sorted(((abs(a.get(p, [0, 0])[0] - b.get(p, [0, 0])[0]), p, b.get(p), a.get(p)) for p in set(a) | set(b)), reverse=True)
for d, p, x, y in diff[:30]:
    print(p, round(d / 1e4), "만원/㎡", x, "→", y)
print("변화 PNU 수:", sum(1 for d, *_ in diff if d > 0))
EOF
```
Expected: `failed` 0 이 목표. failed 구는 사유를 보고 원인 분석(사용자 보고). 실행 시간·전후 크기, 가격 변화 상위 30(대방대림·상도1동대림이 포함돼야 정상)을 사용자에게 공유하고 런북에 기록. (`reports/` 는 gitignore — 커밋하지 않는다.)

- [ ] **Step 5: 런북 작성** — `docs/guides/trade-key-rekey-runbook.md`

```markdown
# 거래 키 변경(ADR-015) 운영 런북

## 전제
- PR 1(적재·매핑 전환) 배포 완료, 운영 스키마에 legacy_apt_seq·apt_seq_method 존재
- 로컬 측정: 전체 적용 {Step 4 실측 시간}, 테이블 크기 {전}→{후}

## 실행 (사용자, 거래 배치 사이 시간 — 매일 12:00·00:00 KST 회차를 피한다)
1. `.venv/bin/python -m batch.rekey_trades --target railway --dry-run` — 구별 계획 확인
2. `.venv/bin/python -m batch.rekey_trades --target railway --apply --limit 20` — 작은 구 20개
3. 결과의 failed 가 0 이면 `--limit` 을 늘려 반복(체크포인트로 이어서 실행)
4. 실행 중 거래 배치가 시작되면 배치가 "거래 쓰기 잠금 점유" 로 실패 기록 — 정상(다음 회차에 진행)

## 검증
- 기준 사례 SQL(대방대림 1993 / 상도1동대림 1995) — 이 문서 하단
- 다음 거래 배치 로그: 고유번호 키 매핑·가격 점수 재계산 성공

## 롤백
- 특정 구: `--target railway --rollback --sgg {코드}`
- 롤백 후 그 구는 체크포인트 rolled_back — 재실행 대상에 다시 포함된다
```
(중괄호 자리는 Step 4 실측값으로 채운다 — 채우기 전에는 커밋하지 않는다.)

- [ ] **Step 6: CLAUDE.md 실행 정책 표에 행 추가** (`| **사장된 PNU 정리 (수동)** |` 행 다음)

```markdown
| **거래 키 변경 (ADR-015, 수동)** | `.venv/bin/python -m batch.rekey_trades --target local --dry-run` (적용 `--apply`, 운영은 `--target railway` 사용자 실행, 롤백 `--rollback --sgg`) |
```

- [ ] **Step 7: Commit + PR 2**

```bash
git add docs/guides/trade-key-rekey-runbook.md CLAUDE.md
git commit -m "docs: 거래 키 변경 운영 런북 + 실행 정책"
git push
gh pr create --base main --title "feat(batch): 과거 거래 키 변경 스크립트 (ADR-015 2단계)" --body "로컬 적용 결과: {Step 4 요약}. 운영 실행은 docs/guides/trade-key-rekey-runbook.md 를 따라 사용자가 수행."
```

---

### Task 10: 잔여 API 수집 모드 + 워크플로 (PR 3)

**Files:**
- Modify: `batch/trade/backfill_trades.py` (`_get_backfill_targets`, `backfill_trades`)
- Modify: `batch/run.py` (`run_backfill`, argparse)
- Create: `.github/workflows/batch-backfill-trade-key.yml`
- Test: `scripts/tests/test_backfill_trade_key.py`

**Interfaces:**
- Consumes: `resolve_trade_key`, `KEY_METHOD_API_BACKFILL` (Task 2), `map_api_keys` (Task 5)
- Produces: `backfill_trades(conn, logger, max_calls=900, dry_run=False, mode="columns")`; `mode="trade_key"`

- [ ] **Step 1: Write the failing test** — `scripts/tests/test_backfill_trade_key.py`

```python
"""trade_key 백필 모드 — 대상 SQL·체크포인트 그룹·키 갱신 SQL (DB 없이 캡처)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade import backfill_trades as mod  # noqa: E402


class TradeKeyModeTest(unittest.TestCase):
    def test_targets_only_mixed_unresolved_rows(self):
        captured = []
        with patch.object(mod, "query_all", lambda c, sql, p=None: captured.append(sql) or []):
            mod._get_backfill_targets(None, mode="trade_key")
        sql = captured[0]
        self.assertIn("apt_seq_method IS NULL", sql)
        self.assertIn("HAVING COUNT(DISTINCT api_apt_seq) > 1", sql)

    def test_checkpoint_group_is_separate(self):
        self.assertNotEqual(mod._checkpoint_group("trade_key"), mod._checkpoint_group("columns"))

    def test_rekey_sql_sets_backfill_method(self):
        cur = MagicMock()
        cur.rowcount = 1
        conn = MagicMock()
        conn.cursor.return_value = cur
        rows = [{"sggCd": "11590", "aptNm": "대림아파트", "excluUseAr": "84.89", "floor": "13",
                 "dealYear": "2016", "dealMonth": "3", "dealDay": "2", "dealAmount": "50,000",
                 "aptSeq": "11590-85"}]
        self.assertEqual(mod._rekey_trade_rows(conn, rows), 1)
        sql, params = cur.execute.call_args[0]
        self.assertIn("apt_seq_method = %s", sql)
        self.assertIn("apt_seq_method IS NULL", sql)
        self.assertIn("api_backfill", params)
        self.assertIn("11590-85", params)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_backfill_trade_key -v`
Expected: FAIL — `_get_backfill_targets() got an unexpected keyword argument 'mode'`

- [ ] **Step 3: Implement** — `backfill_trades.py`

import 추가:

```python
from batch.trade.trade_keys import KEY_METHOD_API_BACKFILL
```

`CHECKPOINT_GROUP = "backfill_trade_checkpoint"` 를 다음으로 교체하고, `_load_checkpoint`/`_save_checkpoint` 에 `mode` 인자를 받아 `CHECKPOINT_GROUP` 대신 `_checkpoint_group(mode)` 를 쓰게 한다:

```python
_CHECKPOINT_GROUPS = {
    "columns": "backfill_trade_checkpoint",        # 기존: 주소·거래구분 칼럼 보충
    "trade_key": "backfill_trade_key_checkpoint",  # ADR-015: 혼입 키 잔여분 고유번호 수집
}


def _checkpoint_group(mode: str) -> str:
    return _CHECKPOINT_GROUPS[mode]
```

`_get_backfill_targets` 를 교체:

```python
_TRADE_KEY_TARGETS_SQL = """
    WITH ids AS (
        SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, api_apt_seq FROM trade_history
        WHERE api_apt_seq IS NOT NULL
        UNION SELECT COALESCE(legacy_apt_seq, apt_seq), api_apt_seq FROM rent_history
        WHERE api_apt_seq IS NOT NULL
    ),
    mixed AS (SELECT lk FROM ids GROUP BY lk HAVING COUNT(DISTINCT api_apt_seq) > 1)
    SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym FROM trade_history
    WHERE apt_seq_method IS NULL AND apt_seq IN (SELECT lk FROM mixed)
    UNION
    SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month FROM rent_history
    WHERE apt_seq_method IS NULL AND apt_seq IN (SELECT lk FROM mixed)
    ORDER BY ym, sgg_cd
"""

_COLUMNS_TARGETS_SQL = """
    SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym
    FROM trade_history WHERE umd_cd IS NULL
    UNION
    SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym
    FROM rent_history WHERE umd_nm IS NULL
    ORDER BY ym, sgg_cd
"""


def _get_backfill_targets(conn, mode: str = "columns"):
    """mode=columns: 주소 칼럼 NULL 인 (구, 월). mode=trade_key: 혼입 키 미해결 행의 (구, 월)."""
    sql = _TRADE_KEY_TARGETS_SQL if mode == "trade_key" else _COLUMNS_TARGETS_SQL
    return [(str(r["sgg_cd"]), str(r["ym"])) for r in query_all(conn, sql)]
```

키 갱신 함수 추가(`_update_rent_rows` 다음):

```python
def _rekey_trade_rows(conn, api_rows) -> int:
    """API 응답의 aptSeq 로 이름 키 행을 고유번호 키로 바꾼다 (ADR-015 잔여 수집)."""
    return _rekey_rows(conn, "trade_history", "deal_amount", "dealAmount", api_rows)


def _rekey_rent_rows(conn, api_rows) -> int:
    return _rekey_rows(conn, "rent_history", "deposit", "deposit", api_rows)


def _rekey_rows(conn, table, amount_col, amount_field, api_rows) -> int:
    cur = conn.cursor()
    updated = 0
    for r in api_rows:
        api = (r.get("aptSeq") or "").strip()
        exclu = _to_float(r.get("excluUseAr"))
        dy, dm, dd = _to_int(r.get("dealYear")), _to_int(r.get("dealMonth")), _to_int(r.get("dealDay"))
        amount = _clean_amount(r.get(amount_field))
        if not (api and exclu is not None and dy and dm):
            continue
        cur.execute(f"""
            UPDATE {table} SET legacy_apt_seq = apt_seq, apt_seq = %s,
                   apt_seq_method = %s, api_apt_seq = %s
            WHERE sgg_cd = %s AND apt_nm = %s AND exclu_use_ar = %s AND floor = %s
              AND deal_year = %s AND deal_month = %s AND deal_day = %s AND {amount_col} = %s
              AND apt_seq_method IS NULL
        """, [api, KEY_METHOD_API_BACKFILL, api, str(r.get("sggCd", "")), str(r.get("aptNm", "")),
              exclu, _to_int(r.get("floor")), dy, dm, dd, amount])
        updated += cur.rowcount
    return updated
```

`backfill_trades` 시그니처를 `def backfill_trades(conn, logger, max_calls=900, dry_run=False, mode="columns"):` 로 바꾸고, `targets = _get_backfill_targets(conn, mode)`, `_load_checkpoint(conn, mode)`, `_save_checkpoint(conn, completed, mode)` 로 호출을 맞춘다. `if not dry_run:` 블록을 다음으로 교체:

```python
        if not dry_run:
            if mode == "trade_key":
                t_updated = _rekey_trade_rows(conn, trade_rows) if trade_rows else 0
                r_updated = _rekey_rent_rows(conn, rent_rows) if rent_rows else 0
            else:
                t_updated = _update_trade_rows(conn, trade_rows) if trade_rows else 0
                r_updated = _update_rent_rows(conn, rent_rows) if rent_rows else 0
            total_trade_updated += t_updated
            total_rent_updated += r_updated
```

마지막 `if not dry_run: conn.commit()` 직전에 trade_key 모드 매핑을 넣는다:

```python
    if not dry_run and mode == "trade_key":
        from batch.trade.trade_key_mapping import map_api_keys
        map_api_keys(conn, logger)
```

남은 대상이 없을 때 `_verify_and_fix_mappings` 호출은 `mode == "columns"` 일 때만 실행되게 조건을 추가한다.

- [ ] **Step 4: run.py 연결** — `run_backfill` 의 호출에 `mode=args.backfill_mode` 추가, argparse 에:

```python
    parser.add_argument(
        "--backfill-mode", choices=["columns", "trade_key"], default="columns",
        help="backfill 대상: columns(주소 칼럼 보충, 기본) / trade_key(ADR-015 혼입 키 잔여 고유번호)",
    )
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m unittest scripts.tests.test_backfill_trade_key -v` → PASS (3 tests)
Run: `.venv/bin/python -m unittest discover -s scripts/tests -t .` → OK

- [ ] **Step 6: 워크플로** — `.github/workflows/batch-backfill-trade-key.yml`

```yaml
name: Backfill Trade Keys (ADR-015)

# 혼입 키 잔여분의 국토부 고유번호를 API 재수집으로 채운다 — 대상 약 7,100콜(2026-10-13 로컬 추정).
# 보조키 900콜/일. 대상이 0 이 되면 "백필 완료 — 남은 대상 없음" 로그 후 이 워크플로를 비활성화한다.
on:
  schedule:
    - cron: '0 20 * * *'  # 매일 20:00 UTC (한국 05:00) — 거래 배치(12:00·00:00 KST)와 겹치지 않음
  workflow_dispatch:

jobs:
  backfill-trade-key:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install psycopg2-binary requests python-dotenv
      - name: Backfill trade keys (max 900 calls)
        run: python -m batch.run --type backfill --backfill-mode trade_key --max-calls 900
        env:
          DATABASE_URL: ${{ secrets.RAILWAY_DATABASE_URL }}
          DATA_GO_KR_API_KEY: ${{ secrets.DATA_GO_KR_API_KEY }}
          DATA_GO_KR_API_SECONDARY_KEY: ${{ secrets.DATA_GO_KR_API_SECONDARY_KEY }}
```

> 사용자 확인 필요: 저장소 시크릿에 `DATA_GO_KR_API_SECONDARY_KEY` 가 있는지(`gh secret list`). 없으면 사용자가 등록한다.

- [ ] **Step 7: 로컬 dry-run** (API 호출 2콜만)

Run: `.venv/bin/python -m batch.run --type backfill --backfill-mode trade_key --max-calls 2 --dry-run`
Expected: `백필 대상: N쌍` 로그(로컬 전체 키 변경 후라 설계 추정 7,100콜보다 작거나 비슷).

- [ ] **Step 8: Commit + PR 3**

```bash
uvx ruff format batch/trade/backfill_trades.py scripts/tests/test_backfill_trade_key.py
git add batch/trade/backfill_trades.py batch/run.py scripts/tests/test_backfill_trade_key.py .github/workflows/batch-backfill-trade-key.yml
git commit -m "feat(batch): 혼입 키 잔여분 고유번호 API 수집 모드 (ADR-015 3단계)"
git push
gh pr create --base main --title "feat(batch): 혼입 키 잔여분 API 수집 (ADR-015 3단계)" --body "운영 키 변경(2단계) 완료 후 머지. 매일 900콜, 대상 0 이 되면 워크플로 비활성화."
```

---

### Task 11: 마무리 (운영 반영 후, PR 4)

**Files:**
- Modify: `docs/adr/015-trade-key-official-id.md`, `docs/adr/README.md`, `docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md`

- [ ] **Step 1: 운영 결과 확인** — 사용자 보고(런북 실행 결과, failed 구 0, 기준 사례 SQL 통과) + 잔여 수집 워크플로 "남은 대상 없음" 확인
- [ ] **Step 2: 사용자에게 `sync_from_railway --mode full` 요청** — 로컬을 운영과 일치시킨다
- [ ] **Step 3: 운영 가격 변화 리포트** — full sync 후 `.venv/bin/python reports/rekey/ppm2_snapshot.py reports/rekey/ppm2_prod_after.json` 을 실행하고, Task 9 Step 4 의 비교 스크립트에서 `ppm2_after.json` 대신 `ppm2_prod_after.json` 을 넣어 상위 30 을 사용자에게 공유(로컬 적용 결과와 크게 다르면 원인 분석)
- [ ] **Step 4: 문서 상태 갱신** — ADR-015 `**상태**: Accepted`, README 표의 `Proposed` → `Accepted`, 설계서 상태 줄 → `구현 완료(PR #…)`
- [ ] **Step 5: Commit + PR 4**

```bash
git add docs/adr/015-trade-key-official-id.md docs/adr/README.md docs/superpowers/specs/2026-10-13-trade-key-official-id-design.md
git commit -m "docs: ADR-015 Accepted — 거래 키 국토부 고유번호 전환 완료"
```
