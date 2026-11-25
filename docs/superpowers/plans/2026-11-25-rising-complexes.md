# 오르는 단지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 예산·면적대 안에서 최근 6·12개월 실거래 중위가격이 오른 수도권 단지를 보여주는 `/rising` 화면을 만든다.

**Architecture:** trade 배치가 순수 계산 모듈(`band_trend_calc`)로 단지·지역·월별 지표를 계산해 사전 집계 테이블 4개를 재생성한다. FastAPI `routers/rising.py → services/rising.py` 가 그 테이블만 조회하고, Next.js `/rising` 은 정적 셸 + 클라이언트 조회(`useRising`)로 그린다.

**Tech Stack:** Python 3.12 · psycopg2 raw SQL · PostgreSQL · FastAPI · Next.js 16 / React 19 · TypeScript · Tailwind 4 · axios · Recharts

**Spec:** `docs/superpowers/specs/2026-11-25-rising-complexes-design.md`

## Global Constraints

- raw SQL + psycopg2, `%s` placeholder. ORM 금지. 스키마는 `web/backend/database.py:create_tables()` 에 추가.
- 분류값(면적대·등급 라벨·계산 범위 시도)은 `common_code`. 임계값은 의미 있는 이름의 모듈 상수 + 근거 주석.
- 외부 노출 이름(API 필드·DB 칼럼)은 소문자 snake_case, `_` prefix 금지. TypeScript `any` 금지.
- 프론트는 `web/frontend-next` 만. `useEffect` 안 직접 API 호출 금지 — hooks 패턴.
- 금액 단위는 만원 정수. API 예산 파라미터만 억 단위(`budget_min`, `budget_max`).
- 직거래 값은 `dealing_gbn = '직거래'`(국토부 원문). NULL 은 유지.
- 운영 DB(Railway) 접속은 건별 사용자 허락. 커밋·push 는 사용자 요청 시에만 — 각 태스크의 커밋 단계는 사용자 확인 후 실행.
- 브랜치: `feature/rising-complexes`. 커밋 메시지 Conventional Commits, AI 작업자 표기 금지.
- 파이썬 포맷: `ruff format` / `ruff check --fix`. 프론트: `npm run lint`, `npm run build`.

## Review Focus

1. **변화값이 NULL 인 단지** — 6·12개월·지역 대비 정렬에서 항상 맨 뒤. (Task 4 테스트)
2. **예산 하한 > 상한** — API 는 422, UI 는 한쪽을 움직이면 다른 쪽을 밀어 항상 하한 ≤ 상한. (Task 4, Task 6)
3. **첫 배포 직후 집계 테이블이 비어 있음** — meta `base_ym = null`, 화면은 "집계 준비 중" 안내, 500 없음. (Task 4, Task 5)
4. **해당 면적대 행이 없는 단지 상세 요청** (예: 84㎡급만 있는 단지를 `area_band=125` 로) — 404, 패널은 "이 면적대 거래 없음". (Task 4, Task 7)
5. **검색어에 `%`·`_`·앞뒤 공백** — 와일드카드로 해석하지 않고 글자 그대로 검색. (Task 4)

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `web/backend/database.py` (수정) | 테이블 4개 + `common_code` 시드 |
| `batch/trade/band_trend_calc.py` (신규) | 순수 계산(기준월·창·중위·이상거래·주택형 비교·등급). DB 없음 — CI 테스트 대상 |
| `batch/trade/refresh_band_trend.py` (신규) | DB 읽기 → 혼입 제외 → calc 호출 → 테이블 재생성 |
| `batch/run.py`, `batch/sync_from_railway.py` (수정) | trade 체인 단계 등록, 로컬 동기화 후 재생성 |
| `scripts/tests/test_band_trend_calc.py` (신규) | calc 단위 테스트 |
| `web/backend/services/rising.py` (신규) | 조회 SQL·정렬·페이지 |
| `web/backend/routers/rising.py` (신규), `web/backend/main.py` (수정) | HTTP 파라미터 검증·라우팅 |
| `web/backend/tests/test_core.py` (수정) | API 통합 테스트(라이브 DB) |
| `web/frontend-next/src/types/rising.ts` | API 응답 타입 |
| `web/frontend-next/src/hooks/useRising.ts`, `useRisingDetail.ts` | 데이터 조회 훅 |
| `web/frontend-next/src/app/rising/*` | 페이지 셸·필터·지역 패널·표·상세 패널·차트 |
| `web/frontend-next/src/app/sitemap.ts` (수정) | `/rising` 추가 |
| `docs/adr/018-rising-band-trend.md`, `docs/adr/README.md`, `CLAUDE.md` | 결정 기록·실행 명령 |

**스펙 보완 (작성자 판단, 리뷰 시 확인):**
- 혼입 제외 키를 로그만이 아니라 `apt_band_trend_excluded_key` 테이블에도 남긴다 — 상세 API 의 최근 실거래도 같은 제외를 적용해야 목록과 상세가 어긋나지 않기 때문.
- `sync_from_railway` 는 새 테이블을 복사하지 않고 동기화 후 로컬에서 재생성한다 — 기존 `refresh_dashboard_stats` 와 같은 패턴.
- 국토부 매매 API 는 분양권을 포함하지 않아 `PRESALE_TOLERANCE_YEARS` 는 쓰지 않는다. 건축년도 판정은 `_BUILD_YEAR_TOLERANCE`(3년) 하나.
- 필터 상태는 v1 에서 URL 에 넣지 않는다 — 정적 셸이 쿼리별 noindex 를 할 수 없으므로 쿼리 URL 자체를 만들지 않는다. canonical `/rising`.

---

### Task 1: 스키마와 코드값

**Files:**
- Modify: `web/backend/database.py` (`create_tables()` 의 dashboard 테이블 블록 뒤)

**Interfaces:**
- Produces: 테이블 `apt_band_monthly_price`, `apt_band_trend`, `region_band_trend`, `apt_band_trend_excluded_key`; `common_code` 그룹 `rising_area_band`, `rising_region_grade`, `rising_complex_grade`, `rising_scope_sido`.

- [ ] **Step 1: 테이블 4개 추가** — 스펙 §6 칼럼 그대로. 추가분:
  - `apt_band_trend` 에 `sigungu_code TEXT NOT NULL`, 인덱스 `(area_band, median_price_3m)`, `(area_band, sigungu_code)`.
  - `apt_band_trend_excluded_key (apt_seq TEXT PRIMARY KEY, pnu TEXT, reason TEXT NOT NULL, refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW())` — reason 값은 `mapping_violation` | `build_year_mismatch`.
  - 모든 테이블 `refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- [ ] **Step 2: `common_code` 시드** — `INSERT ... ON CONFLICT (group_id, code) DO NOTHING`, `sort_order` 로 순서 고정.
  - `rising_area_band`: (code, name, extra=`"하한,상한"` 빈 상한은 무한) — `59 59㎡급 50,70` · `84 84㎡급 70,100` · `100 대형 100–125㎡ 100,125` · `125 대형 125–150㎡ 125,150` · `150 대형 150–175㎡ 150,175` · `175 대형 175㎡ 이상 175,`
  - `rising_region_grade`: S+ S S- A+ A A- B+ B B- C+ C C- D+ D D- (code=name, sort_order 1~15)
  - `rising_complex_grade`: S A B C D (sort_order 1~5)
  - `rising_scope_sido`: `11 서울`, `28 인천`, `41 경기`
- [ ] **Step 3: 로컬 적용 확인**
  Run: `.venv/bin/python -c "import sys; sys.path.insert(0,'web/backend'); from database import create_tables; create_tables()"` 후
  `psql "$DATABASE_URL" -Atc "select group_id, count(*) from common_code where group_id like 'rising_%' group by 1 order by 1"`
  Expected: `rising_area_band|6`, `rising_complex_grade|5`, `rising_region_grade|15`, `rising_scope_sido|3`. 두 번 실행해도 같은 결과.
- [ ] **Step 4: 커밋** — `feat(db): 오르는 단지 집계 테이블·코드값 추가`

### Task 2: 순수 계산 모듈

**Files:**
- Create: `batch/trade/band_trend_calc.py`
- Test: `scripts/tests/test_band_trend_calc.py`

**Interfaces:**
- Produces (모두 순수 함수, DB·네트워크 import 금지):
  - 상수: `REPORT_DEADLINE_DAYS = 30`, `WINDOW_MONTHS = 3`, `CHANGE_OFFSETS = (6, 12)`, `HISTORY_MONTHS = 60`, `TYPE_KEY_DECIMALS = 2`, `BAND_OUTLIER_MAX_DEVIATION = 0.25`, `MIN_RECENT_TRADES = 2`, `MIN_COMPARE_TRADES = 2`, `MIN_GRADE_TRADES = 3`, `MIN_REGION_TRADES = 5`, `EXCLUDED_DEALING_GBN = "직거래"` (MIN_* 은 Task 3 실측 후 조정 가능, 근거 주석 필수)
  - `class BandDef(NamedTuple): code: str; min_area: float; max_area: float | None`
  - `band_of(area: float, bands: list[BandDef]) -> str | None` — `min ≤ area < max`
  - `type_key(area: float) -> float`
  - `base_month(today: date) -> int` (YYYYMM)
  - `shift_month(ym: int, months: int) -> int`
  - `window(end_ym: int, length: int = WINDOW_MONTHS) -> list[int]`
  - `median(values: Sequence[float]) -> float`
  - `drop_outliers(prices: Sequence[float], max_deviation: float = BAND_OUTLIER_MAX_DEVIATION) -> list[float]`
  - `type_change(current: Mapping[Hashable, Sequence[float]], past: Mapping[Hashable, Sequence[float]]) -> tuple[float | None, int]` — (변화율 %, 비교 주택형 수)
  - `region_grade(rank: int, total: int, labels: Sequence[str]) -> str`
  - `complex_grade(rank: int, total: int, labels: Sequence[str]) -> tuple[str, int]` — (등급, 십분위)
  - `placement_rank(value: float, population_desc: Sequence[float]) -> int`
  - `monthly_series(prices_by_month: Mapping[int, Sequence[float]], months: Sequence[int]) -> list[tuple[int, int | None, int]]` — (ym, 중위가격 or None, 건수)

- [ ] **Step 1: 실패하는 테스트 작성** (`unittest`, `scripts/tests/test_mapping_checks.py` 형식)

```python
class TestBaseMonth(unittest.TestCase):
    def test_신고기한이_지난_달만_기준월(self):
        self.assertEqual(base_month(date(2026, 11, 25)), 202609)
        self.assertEqual(base_month(date(2026, 11, 30)), 202609)  # 10/31+30 = 11/30, 미경과
        self.assertEqual(base_month(date(2026, 12, 1)), 202610)
        self.assertEqual(base_month(date(2027, 1, 31)), 202611)

class TestWindow(unittest.TestCase):
    def test_연도를_넘는_창(self):
        self.assertEqual(window(202601), [202511, 202512, 202601])
        self.assertEqual(shift_month(202609, -12), 202509)

class TestBand(unittest.TestCase):
    BANDS = [BandDef("59", 50, 70), BandDef("84", 70, 100), BandDef("175", 175, None)]
    def test_경계는_하한_포함_상한_제외(self):
        self.assertEqual(band_of(70.0, self.BANDS), "84")
        self.assertEqual(band_of(69.99, self.BANDS), "59")
        self.assertEqual(band_of(240.0, self.BANDS), "175")
        self.assertIsNone(band_of(45.0, self.BANDS))
        self.assertIsNone(band_of(120.0, self.BANDS))

class TestOutliers(unittest.TestCase):
    def test_중앙값_25퍼센트_밖은_제외(self):
        self.assertEqual(sorted(drop_outliers([84000, 82500, 55000])), [82500, 84000])
    def test_두건이_크게_벌어지면_둘다_제외(self):
        self.assertEqual(drop_outliers([50000, 100000]), [])

class TestTypeChange(unittest.TestCase):
    def test_주택형별_비율을_최근건수로_가중(self):
        pct, matched = type_change(
            {84.52: [90000, 85000], 84.54: [85000, 89000, 85000], 84.99: [91000]},
            {84.52: [65000], 84.54: [66000, 67000]},
        )
        self.assertAlmostEqual(pct, 30.54, places=2)  # 84.99 는 과거 창에 없어 제외
        self.assertEqual(matched, 2)
    def test_공통_주택형_없으면_None(self):
        self.assertEqual(type_change({84.5: [1, 2]}, {59.9: [1, 2]}), (None, 0))
    def test_창_거래가_최소건수_미만이면_None(self):
        self.assertEqual(type_change({84.5: [90000]}, {84.5: [80000, 81000]}), (None, 0))

class TestGrades(unittest.TestCase):
    REGION = ["S+","S","S-","A+","A","A-","B+","B","B-","C+","C","C-","D+","D","D-"]
    def test_지역등급_15단계_균등분할(self):
        self.assertEqual(region_grade(1, 71, self.REGION), "S+")
        self.assertEqual(region_grade(71, 71, self.REGION), "D-")
        self.assertEqual(region_grade(30, 71, self.REGION), "B+")  # (30-1)*15//71 = 6
    def test_단지등급_십분위_두개씩(self):
        self.assertEqual(complex_grade(1, 96, list("SABCD")), ("S", 1))
        self.assertEqual(complex_grade(59, 96, list("SABCD")), ("C", 7))
        self.assertEqual(complex_grade(96, 96, list("SABCD")), ("D", 10))
    def test_12개월_대입_순위(self):
        self.assertEqual(placement_rank(70000, [90000, 80000, 70000, 60000]), 3)

class TestMonthlySeries(unittest.TestCase):
    def test_빈달은_None_0건_이상거래는_롤링창_기준_제외(self):
        series = monthly_series({202607: [80000, 82000], 202609: [83000, 50000]},
                                [202607, 202608, 202609])
        self.assertEqual(series[0], (202607, 81000, 2))
        self.assertEqual(series[1], (202608, None, 0))
        self.assertEqual(series[2], (202609, 83000, 1))  # 7~9월 창 중앙값 81000 기준 50000 제외
```


- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m unittest scripts.tests.test_band_trend_calc -v` / Expected: `ModuleNotFoundError: batch.trade.band_trend_calc`
- [ ] **Step 3: 구현** — 규칙:
  - `base_month`: `today` 이전 달부터 거슬러 올라가며 `월말일 + REPORT_DEADLINE_DAYS < today` 인 첫 달.
  - `region_grade`: `labels[(rank - 1) * len(labels) // total]`.
  - `type_change`: 양쪽 창 전체 거래 수가 각각 `MIN_COMPARE_TRADES` 미만이면 `(None, 0)`. 공통 키마다 `median(current[k]) / median(past[k])`, 가중치 `len(current[k])`, 결과 `(가중평균 − 1) × 100`.
  - `complex_grade`: `decile = ceil(rank * 10 / total)`, `labels[(decile - 1) // 2]`.
  - `monthly_series`: 각 달 m 에 대해 `window(m)` 의 모든 가격 중앙값 기준 `max_deviation` 밖인 그 달 거래 제외 후 중위·건수.
- [ ] **Step 4: 통과 확인** — 같은 명령, Expected: 전부 OK. `.venv/bin/python -m unittest discover -s scripts/tests -t .` 전체도 OK.
- [ ] **Step 5: 커밋** — `feat(batch): 면적대 가격 추세 계산 모듈`

### Task 3: 집계 배치 + 혼입 제외

**Files:**
- Create: `batch/trade/refresh_band_trend.py`
- Modify: `batch/run.py` (trade 체인 4.5 대시보드 집계 다음), `batch/sync_from_railway.py` (로컬 대시보드 재생성 다음)

**Interfaces:**
- Consumes: Task 1 테이블·코드값, Task 2 함수 전부, `batch.trade.audit_mappings.find_violations(conn, pnus=...) -> tuple[list[dict], int]`, `batch.trade.name_matching._BUILD_YEAR_TOLERANCE`. 단지 노출 조건은 batch 가 `web/backend` 를 import 하지 않으므로 이 모듈 상수 `VISIBLE_APARTMENT_CONDITIONS` 에 `web/backend/routers/apartments.py:15` `APARTMENT_VISIBLE_CONDITIONS` 와 같은 5개 조건을 두고, 두 곳이 함께 바뀌어야 한다는 주석을 양쪽에 단다
- Produces: `refresh_band_trend(logger, today: date | None = None) -> dict[str, int]` — 키 `monthly_rows`, `trend_rows`, `region_rows`, `excluded_keys`, `excluded_trades`

- [ ] **Step 1: 데이터 로드 규칙 구현**
  - 범위: `apartments.sigungu_code` 앞 2자리 ∈ `rising_scope_sido`, `group_pnu = pnu` 이고 노출 조건 통과한 대표 단지. 거래는 `trade_apt_mapping.pnu` 의 `group_pnu` 로 대표 단지에 귀속.
  - 기간: `shift_month(base, -(HISTORY_MONTHS - 1))` ~ `base`. 직거래 제외.
  - 혼입 제외: `find_violations(conn, pnus=범위 내 pnu 전체)` 의 `apt_seq` → reason `mapping_violation`. 거래 `build_year` 와 단지 준공연도(`COALESCE(NULLIF(k.use_date,''), a.use_apr_day)` 앞 4자리)의 차이가 `_BUILD_YEAR_TOLERANCE` 초과 → 그 거래 제외, 해당 apt_seq 를 reason `build_year_mismatch` 로 기록(둘 다면 `mapping_violation` 우선). 한쪽이 NULL 이면 유지.
- [ ] **Step 2: 지표 계산·적재** — 한 트랜잭션에서 4개 테이블 `DELETE` 후 `execute_values` INSERT.
  - 단지×면적대: 최근 창(`window(base)`)·6개월 전·12개월 전 창마다 `drop_outliers` 를 창 단위로 적용 후 `type_key` 로 묶어 `type_change`. 최근 창 거래 `< MIN_RECENT_TRADES` 면 `apt_band_trend` 에 넣지 않는다(월별 시계열은 넣는다).
  - 지역: 같은 방식, 비교 키 `(pnu, type_key)`. 지역 등급 모집단 = `trade_count_3m ≥ MIN_REGION_TRADES` 인 지역, 가격 내림차순 순위.
  - `relative_change_6m_pct` = 단지 `change_6m_pct` − 지역 `change_6m_pct` (어느 쪽이든 NULL 이면 NULL).
  - 단지 등급: 스펙 §5.4 작성자 판단 문단대로(6개월 모집단 순위, 미달 단지는 12개월 가격 `placement_rank` 대입·순위 비움·`grade_window_months = 12`).
  - 로그: 제외 키 수·거래 수, 면적대별 제외 비율, 거래 수 상위 10개 제외 키.
- [ ] **Step 3: 배치 연결** — `run.py` 에 `result.record("면적대 추세 집계", ...)`, 실패는 `warning`(대시보드 집계와 같은 격리). `sync_from_railway.py` 의 incremental/full 후 재생성, 실패는 warning.
- [ ] **Step 4: 로컬 실행·검증**
  Run: `.venv/bin/python -c "from batch.logger import setup_logger; from batch.trade.refresh_band_trend import refresh_band_trend; print(refresh_band_trend(setup_logger('band')))"`
  Expected: 각 카운트 > 0, 실행 시간 기록. 이어서 손계산 검증 3건(스펙 §8.3):
  `psql "$DATABASE_URL" -Atc "select a.display_name, t.median_price_3m, t.trade_count_3m, round(t.change_6m_pct::numeric,1), round(t.change_12m_pct::numeric,1), t.matched_type_count_6m from apt_band_trend t join apartments a using(pnu) where t.area_band='84' and a.display_name like '동탄역포레너스%'"`
  Expected: 중위가격 8.5억 근처, 6개월 +29% 근처, 12개월 +38% 근처(참고 서비스 값; 직거래·이상거래 처리 차이로 소폭 다를 수 있음 — 차이가 나면 원천 거래로 손계산해 우리 정의대로인지 확인하고 결과를 PR 설명에 기록). 표본 2곳 더(서울 1, 인천 1) 같은 방식 확인.
- [ ] **Step 5: MIN_* 상수 실측 조정** — 84㎡급에서 `change_6m_pct` NULL 비율, 지역 등급 미부여 지역 수, 제외 비율을 로그로 보고, 조정한 값과 근거를 상수 주석에 남긴다.
- [ ] **Step 6: 커밋** — `feat(batch): 면적대 추세 집계 + 혼입 의심 거래 자동 제외`

### Task 4: API

**Files:**
- Create: `web/backend/services/rising.py`, `web/backend/routers/rising.py`
- Modify: `web/backend/main.py` (`app.include_router(rising.router, prefix="/api")`), `web/backend/tests/test_core.py`

**Interfaces:**
- Consumes: Task 1 테이블, `common_code`(`rising_area_band`, `sigungu`).
- Produces (HTTP, 프론트 Task 5~7 이 사용):
  - `GET /api/rising/meta` → `{ base_ym: int | null, bands: [{code, name, min_area, max_area}], regions: { [band_code]: [{sigungu_code, sigungu_name, sido_code, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct, region_grade, region_rank, region_rank_total}] } }`
  - `GET /api/rising?area_band=84&budget_min=3&budget_max=10&sido=11&sgg=11215&sgg=11590&q=&sort=change_6m&page=1` → `{ base_ym, total_count, region_count, page, page_size: 20, items: [RisingItem], region_counts: { [sigungu_code]: int } }`
    - `RisingItem = {pnu, name, address, sigungu_code, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct, matched_type_count_6m, matched_type_count_12m, relative_change_6m_pct, complex_grade, complex_rank, complex_rank_total, grade_window_months, region_grade}` — `name` 은 `apartments.display_name`, `address` 는 단지 상세 기본정보가 쓰는 주소 칼럼과 동일.
    - `sort` ∈ `change_6m`(기본) `change_12m` `relative_6m` `region_price` `complex_rank` `price_asc` `budget_near`. 값 칼럼 NULL 은 항상 뒤(`NULLS LAST`). `budget_near` = `median_price_3m DESC`. `complex_rank` = `grade_window_months` 6 먼저, 그다음 `complex_rank / complex_rank_total` 오름차순.
    - `region_counts` 는 `sgg`·`q` 를 뺀 조건(면적대·예산·sido)으로 센다.
  - `GET /api/rising/{pnu}?area_band=84` → `{ pnu, name, address, item: RisingItem, monthly: [{ym, median_price, trade_count}] (60개, 빈 달 median_price null), recent_trades: [{deal_date, exclu_use_ar, floor, deal_amount, is_direct_deal}] }` — 최근 실거래는 최근 창·면적대 범위·`apt_band_trend_excluded_key` 제외 적용, 직거래는 포함하되 `is_direct_deal: true`.

- [ ] **Step 1: 실패하는 통합 테스트 작성** (`test_core.py` 의 `test()` 데코레이터·`requests` 형식)
  - `test_rising_meta`: 200, `bands` 6개, `base_ym` 이 int.
  - `test_rising_list_budget_and_band`: `area_band=84&budget_min=3&budget_max=10` → 모든 item `30000 ≤ median_price_3m ≤ 100000`, `len(items) ≤ 20`.
  - `test_rising_nulls_last`: `sort=change_6m` 전 페이지 순회 시 `change_6m_pct` 가 null 인 항목 뒤에 non-null 이 다시 나오지 않음. `sort=relative_6m` 도 같은 검사.
  - `test_rising_budget_inverted`: `budget_min=10&budget_max=3` → 422.
  - `test_rising_invalid_band_or_sort`: `area_band=60` → 422, `sort=foo` → 422.
  - `test_rising_search_literal`: `q=%` → 200 이고 `total_count == 0`(이름에 `%` 인 단지 없음). `q=  동탄  ` 결과 == `q=동탄` 결과.
  - `test_rising_detail`: 목록 첫 항목 상세 → `len(monthly) == 60`, `recent_trades` 모두 면적대 범위 안.
  - `test_rising_detail_missing_band`: 목록 84㎡급 첫 항목의 pnu 로 `area_band=175` 조회 → 해당 행이 없으면 404.
- [ ] **Step 2: 실패 확인** — 백엔드 서버 실행 후 `.venv/bin/python web/backend/tests/test_core.py` / Expected: 위 테스트 404 로 FAIL.
- [ ] **Step 3: 구현** — router 는 파라미터 검증(`area_band` 은 `rising_area_band` 코드, `sort` 는 위 목록, `page ≥ 1`, `budget_min ≤ budget_max`)만, SQL 은 service. 정렬은 `sort` → ORDER BY 조각 dict 상수(문자열 결합에 사용자 입력 금지). `q` 는 trim 후 `%`·`_`·`\` 이스케이프하고 `ILIKE ... ESCAPE '\'` 로 이름·주소 검색. 집계 테이블이 비면 meta `base_ym: null`, 목록 `items: []`, `total_count: 0` — `base_ym` 은 `SELECT MAX(base_ym)` 결과를 그대로 쓰고(NULL 이면 null), 목록 쿼리는 빈 결과를 그대로 반환하면 된다. 로컬 집계 테이블을 지워서 확인하지 않는다(리뷰로 확인).
- [ ] **Step 4: 통과 확인** — 같은 명령 / Expected: rising 테스트 전부 PASS, 기존 테스트 회귀 없음. `ruff format`, `ruff check --fix` 적용.
- [ ] **Step 5: 커밋** — `feat(api): 오르는 단지 목록·상세·메타 API`

### Task 5: 페이지 셸 · 타입 · 훅

**Files:**
- Create: `web/frontend-next/src/types/rising.ts`, `src/hooks/useRising.ts`, `src/hooks/useRisingDetail.ts`, `src/app/rising/page.tsx`, `src/app/rising/_view.tsx`, `src/app/rising/Disclaimer.tsx`
- Modify: `src/app/sitemap.ts`

**Interfaces:**
- Consumes: Task 4 응답 스키마.
- Produces:
  - 타입 `RisingMeta`, `RisingBand`, `RisingRegion`, `RisingItem`, `RisingListResponse`, `RisingDetail`, `RisingSort`(문자열 리터럴 유니온 7개), `RisingFilters = { areaBand: string; budgetMin: number; budgetMax: number; sido: string | null; sggCodes: string[]; query: string; sort: RisingSort; page: number }`
  - `useRising(filters: RisingFilters) -> { meta: RisingMeta | null; list: RisingListResponse | null; loading: boolean; error: string | null }` — `src/lib/api.ts` 의 `api` 사용, 필터 변경 시 이전 요청 취소(`isCancel`), 검색어는 디바운스 250ms.
  - `useRisingDetail(pnu: string | null, areaBand: string) -> { detail: RisingDetail | null; loading: boolean; notFound: boolean }`

- [ ] **Step 1: 타입·훅 작성** — 기존 `useApartments.ts` 의 요청·취소 패턴을 따른다.
- [ ] **Step 2: `page.tsx`** — 서버 컴포넌트, `searchParams` 를 읽지 않는다(정적 유지). `metadata`: title `오르는 단지 | 집토리`, description, `alternates.canonical: "/rising"`. 본문은 제목·한 줄 설명·`<Disclaimer />`·`<RisingView />`(client).
  Disclaimer 문구(스펙 §7.3 고정): "국토교통부 아파트 매매 실거래 신고 자료를 바탕으로 한 참고 정보입니다. 등급과 변화율은 집토리가 계산한 값이며, 신고 시점·거래 정정·거래 건수에 따라 달라질 수 있습니다. 실제 매물 조건을 확인한 뒤 매매 여부를 직접 판단해 주세요." 접이식(`<details>`).
- [ ] **Step 3: `_view.tsx`** — 필터 상태 보유(기본: `areaBand "84"`, `budgetMin 3`, `budgetMax 10`, `sort "change_6m"`), 하위 컴포넌트에 전달. `meta.base_ym === null` 이면 "집계 준비 중입니다" 안내만 표시. 기준월 표시 `YYYY.MM 계약까지`.
- [ ] **Step 4: sitemap** — `/rising` 고정 항목 추가.
- [ ] **Step 5: 확인** — Run: `cd web/frontend-next && npm run lint && npm run build` / Expected: 에러 없음, 빌드 출력에서 `/rising` 이 `○ (Static)`.
- [ ] **Step 6: 커밋** — `feat(web): 오르는 단지 페이지 셸·데이터 훅`

### Task 6: 필터 · 지역 패널 · 단지 표

**Files:**
- Create: `src/app/rising/RisingFilterBar.tsx`, `src/app/rising/BudgetRange.tsx`, `src/app/rising/RegionPanel.tsx`, `src/app/rising/ComplexTable.tsx`, `src/app/rising/GradeBadge.tsx`, `src/app/rising/ChangeCell.tsx`, `src/app/rising/format.ts`
- Modify: `src/app/rising/_view.tsx`

**Interfaces:**
- Consumes: Task 5 타입·훅·필터 상태.
- Produces:
  - `format.ts`: `formatEok(manwon: number) -> string`(예 `85000 → "8.5억"`), `formatChange(pct: number | null) -> string`(`+29.9%`, null → `—`), `formatBaseMonth(ym: number) -> string`(`202609 → "2026.09"`)
  - `ChangeCell({ pct, matchedTypeCount })` — 신뢰도 문구 규칙: `pct === null` → "비교 부족", `matchedTypeCount === 1` → "한 주택형만 비교", 그 외 문구 없음. 양수 초록·음수 빨강(Tailwind 토큰은 기존 화면과 동일 계열).
  - `GradeBadge({ grade, title })` — 지역 등급 툴팁: "지역 가격 수준 등급(상승세 아님)". `grade_window_months === 12` 이면 순위 대신 "12개월 참고".

- [ ] **Step 1: `BudgetRange`** — 하한·상한 숫자 입력 + 이중 슬라이더(3~100억, 15억을 트랙 중앙에 두는 비선형 눈금) + 프리셋(3·5·7·10·15·20·30억 상한). 한쪽을 움직여 역전되면 다른 쪽을 같은 값으로 민다(하한 ≤ 상한 불변).
- [ ] **Step 2: `RisingFilterBar`** — 면적대 세그먼트(59㎡급·84㎡급·대형 ▾ → 대형 4구간 선택), `BudgetRange`.
- [ ] **Step 3: `RegionPanel`** — 시도 탭(전체·서울·경기·인천), 지역 목록은 `meta.regions[areaBand]` 를 등급순으로, 각 행에 `region_counts` 단지 수(0곳은 흐리게). 여러 지역 다중 선택, "선택 해제".
- [ ] **Step 4: `ComplexTable`** — 열: 단지(이름·`시군구 동`)·지역 등급·지역 내 단지 등급(`rank/total`)·3개월 중위가격(아래 `N건`)·6개월·12개월. 정렬 드롭다운(7개, 라벨: 6개월 변화율 높은 순 / 12개월 변화율 높은 순 / 지역 대비 상승률 높은 순 / 지역 가격대 높은 순 / 지역 내 가격 순위 / 가격 낮은 순 / 예산 상한에 가까운 순), 검색창, 20개 페이지네이션, 결과 0건이면 "조건에 맞는 단지가 없습니다". 모바일(<768px)은 카드 리스트, 지역 패널은 상단 시트.
- [ ] **Step 5: 확인** — `npm run lint && npm run build` 통과. 로컬 백엔드 + `npm run dev` 로 `/rising` 열어: 예산 하한을 상한보다 크게 입력하면 상한이 따라 올라감, 84㎡급·3~10억 결과가 API 직접 호출 결과와 같은 첫 페이지, 6개월 정렬에서 "비교 부족" 행이 맨 뒤.
- [ ] **Step 6: 커밋** — `feat(web): 오르는 단지 필터·지역 패널·단지 표`

### Task 7: 단지 상세 패널 · 차트

**Files:**
- Create: `src/app/rising/ComplexDetailPanel.tsx`, `src/app/rising/BandPriceChart.tsx`
- Modify: `src/app/rising/_view.tsx`, `src/app/rising/ComplexTable.tsx`(행 클릭 → 선택 pnu)

**Interfaces:**
- Consumes: `useRisingDetail`, `format.ts`, `GradeBadge`, `ChangeCell`.
- Produces: `ComplexDetailPanel({ pnu, areaBand, onClose })`, `BandPriceChart({ monthly })`

- [ ] **Step 1: 패널** — 상단 주소·면적대·단지명, 지표 5칸(지역 등급+`N곳 중 M위` / 지역 내 단지 등급+`N곳 중 M위·가격 상위 X–Y%`(십분위) / 3개월 중위가격+`N건 기준` / 6개월 변화+`비교 주택형 N개` / 12개월 변화), 차트, "월별 가격·거래량 표"(접이식), 최근 실거래 표(계약일·전용면적·층·거래가격, 직거래는 "직거래" 표시), 하단 버튼 **"이 단지 자세히 보기"** → `/apartment/[pnu]`. `notFound` 면 "이 면적대 거래 없음".
- [ ] **Step 2: `BandPriceChart`** — Recharts `ComposedChart`: 중위가격 선(빈 달은 끊기지 않게 `connectNulls`) + 거래량 막대(보조 축), x축 `YY.MM`, 마지막 점 강조, 캡션 "2021.11 이전 거래 유형 미분류 포함".
- [ ] **Step 3: 확인** — `npm run lint && npm run build`. 브라우저에서 동탄역포레너스 84㎡급 열어 60개월 차트·최근 실거래가 Task 3 검증 값과 일치, "이 단지 자세히 보기"가 상세로 이동, ESC·닫기 버튼으로 닫힘.
- [ ] **Step 4: 커밋** — `feat(web): 오르는 단지 상세 패널·가격 차트`

### Task 8: 결정 기록 · 운영 문서

**Files:**
- Create: `docs/adr/018-rising-band-trend.md`
- Modify: `docs/adr/README.md`, `CLAUDE.md`(실행 정책 표)

- [ ] **Step 1: ADR-018** — 맥락(실수요자 예산 탐색), 결정(사전 집계 4테이블·면적대·주택형 기준 변화율·혼입 자동 제외·정적 셸), 대안(정적 JSON·대시보드 탭), 트레이드오프(오탐 제외 가능성·해제 거래 미반영), 후속(스펙 §10).
- [ ] **Step 2: CLAUDE.md** — 표에 `면적대 추세 집계 (수동) | .venv/bin/python -c "..."`(Task 3 Step 4 명령) 추가.
- [ ] **Step 3: 커밋** — `docs: ADR-018 오르는 단지 집계 결정 기록`

### Task 9: 출시 게이트 (운영 — 사용자 허락 필요)

코드 변경 없음. 각 단계의 운영 DB 접속은 목적·SQL·영향 범위를 제시하고 건별 허락을 받는다.

- [ ] **Step 1: Railway rekey** — `docs/guides/trade-key-rekey-runbook.md` 순서(remap → rekey → VACUUM FULL). 완료 기록을 PR 설명에 남긴다.
- [ ] **Step 2: 배포 후 운영 집계 1회 실행** — trade 배치 또는 수동 명령. Railway 자동배포 누락 여부는 `--service apt-recom` 로 확인.
- [ ] **Step 3: 상위 50 점검** — `GET /api/rising?area_band=84&budget_min=3&budget_max=100&sort=change_6m` 상위 50개를 단지 상세 거래와 대조해 혼입·이상 급등 0건 확인. 걸린 건은 `reflect_*` 방식 교정 후 재집계·재점검. 자동 제외 오탐(정상 단지가 빠짐)은 목록으로 남겨 제외 규칙 조정 이슈로 분리.
- [ ] **Step 4: 출시** — 점검 통과 후 진입 링크 노출 여부를 사용자와 결정(홈·지역 허브 링크는 후속 범위).
