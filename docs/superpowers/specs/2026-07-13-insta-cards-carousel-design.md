# 설계 — 인스타그램 카드뉴스 5개 시리즈 캐러셀 생성기

- 작성일: 2026-07-13 (rev.2 — 스키마 정합·선정 규칙·데이터 경로 리뷰 반영)
- 브랜치: `feature/instagram-content-landing`
- 관련 문서: `docs/prd/2026-07-13-instagram-content-landing.md` (랜딩 PRD — 본 설계는 그중 생성기 파트를 캐러셀 체계로 확장·선행)
- 관련 커밋: `e993477 feat(content): 인스타그램 카드 자동 생성 — 거래TOP·동네비교·숨은가성비 (#161)`

---

## 1. 목표 / 비목표

### 목표

1. 인스타그램 정기 발행 5개 시리즈를 하나의 생성기 체계로 지원한다.
   - 신규: `budget_choice`(같은 예산, 다른 선택), `lifestyle`(라이프스타일별 추천 — 넛지 프로필 파라미터화)
   - 개편: `trade_top`, `compare`, `value` (기존 단일 카드 → 캐러셀)
2. 모든 시리즈를 6~9장 캐러셀 형식으로 전환한다 (표지 → 조건 → 본문 → 주의사항 → CTA).
3. 이미지와 **동일한 실행에서 발행 스냅샷 JSON**(`publication.json`)을 산출한다 (랜딩 PRD G1 해소). 이미지와 JSON은 같은 Publication 객체를 소비한다.
4. 서사 문구(훅·이유·적합대상)는 데이터 기반 템플릿으로 자동 생성하고, YAML 오버라이드를 허용한다.

### 비목표

- `/content/[slug]` 랜딩 페이지 구현, `posts.json` 레지스트리, 프론트 딥링크 확장 — 랜딩 PRD의 후속 단계로 분리. 단, Publication은 PRD §5 스키마와 호환되게 정의해 후속 단계가 생성기를 재개편하지 않게 한다.
- cover 이미지의 `web/frontend-next/public/` 복사 (PRD G5) — 랜딩 단계에서 수행.
- LLM 문구 생성, CMS/어드민, GitHub Actions 스케줄링(로컬 DB·macOS 폰트 의존 — PRD Q7 미결 유지).
- 통근시간 표시. `/api/commute`(ODSay 실시간 검색, `web/backend/routers/commute.py:128`)가 이미 존재하므로 **기술적으로 가능**하지만, 외부 API 의존·호출량 관리가 필요해 파일럿 범위에서 제외한다. lifestyle `--destination` 옵션으로 후속 확장 (표시 전용 — 전 후보 필터링은 호출량 문제로 불가).

### PRD 후속 갱신 항목 (본 설계가 만드는 PRD 변경 필요분)

- PRD §5 `series` discriminated union에 `budget_choice`, `lifestyle` 추가 — 랜딩 단계 착수 시 PRD 갱신.

## 2. 결정 사항 요약

| 결정 | 선택 | 근거 |
|---|---|---|
| 시리즈 범위 | 신규 2종 + 기존 3종 개편 (5개 정기 체계) | 제안서 우선순위 5개 시리즈 완성 |
| 카드 형식 | 전 시리즈 6~9장 캐러셀 | 제안서 카드뉴스 구성 공식 채택 + 주의사항 장 필수화 |
| 랜딩 PRD 관계 | 카드 + 스냅샷 JSON까지, 랜딩은 후속 | 생성기 2차 개편 방지 (G1 선해소) |
| 라이프스타일 | 넛지 프로필 파라미터화, 파일럿은 `newlywed` | 서버 넛지 9종 재사용, 시리즈 1개로 변형 커버 |
| budget_choice 후보 | 실거래 기반 적격 집합 → 넛지 점수 대표 선정 + pnu 오버라이드 | §5-1 (nudge API의 max_price는 추정가라 단독 사용 불가) |
| 후보 상세 metrics | 기존 공개 API `GET /api/apartment/{pnu}` 호출 | 백엔드 무변경, sync 확장 불필요, 서비스 화면과 동일 값 (§5-4) |
| compare 비교 단위 | 지역 집계 비교표 + 각 지역 1위 단지 상세 장 | §5-3 |
| trade_top "급증" | 직전 동일 기간 대비 실제 계산 | 현행 카운트-온리 쿼리는 "급증" 미증명 (§5-5) |
| 서사 문구 | 템플릿 자동 + `--copy-file` YAML 오버라이드 | 단정 표현 위험 차단, 완전 자동 발행 가능 |
| 아키텍처 | `scripts/insta_cards/` 패키지 분리 (Pillow 유지) | 단일 파일 750줄 → 5시리즈 캐러셀 감당 불가 |

## 3. 패키지 구조와 데이터 흐름

```
scripts/insta_cards/
├── __init__.py
├── __main__.py          # python -m scripts.insta_cards 진입점 (cli.main 위임)
├── cli.py               # 인자 파싱 + 시리즈 디스패치
├── publication.py       # Publication 모델(dataclass) + validate() — 단일 진실원
├── slides.py            # 캐러셀 장 렌더러 8종 (Pillow, 1080×1080)
├── theme.py             # 폰트·그라데이션·색상·footer (기존 CardCanvas 계열 이관)
├── copywriting.py       # 서사 문구 템플릿 + 오버라이드 병합 + 금지어 검사
├── textrules.py         # 필드별 길이/줄수 한도 상수 + 줄바꿈 측정 유틸
├── datasources.py       # 로컬 DB 커넥션 + 운영 API 클라이언트 (nudge/score, apartment detail)
├── output.py            # 원자적 쓰기(임시 디렉토리 → rename) + 전역 slug 충돌 검사
└── series/
    ├── trade_top.py     # 기존 fetch 이관 + pnu 보존 (PRD G2) + 직전 기간 대비 계산
    ├── compare.py       # 지역 집계 + 1위 단지 pnu 보존 (PRD G4)
    ├── value.py         # 기존 fetch 이관
    ├── budget_choice.py # 신규
    └── lifestyle.py     # 신규
```

- 기존 `scripts/generate_insta_cards.py`는 **삭제하지 않고 shim으로 유지**: 기존 옵션을 새 CLI로 위임 + deprecation 안내 출력. 기존 실행 경로(`.venv/bin/python scripts/generate_insta_cards.py --series ...`, 운영 메모의 주간 명령) 회귀 방지.
- `scripts/__init__.py`는 이미 존재 — `python -m scripts.insta_cards` 실행 가능 (`__main__.py` 필수).

데이터 흐름 (모든 시리즈 동일):

```
series/*.py  fetch → build_publication()   ← 검증 실패 시 예외, 발행 중단 (fallback 없음)
                        │
             Publication (불변 객체)
                ├→ slides.py 렌더 ┐
                └→ JSON 직렬화    ├→ output.py: {slug}.tmp-{pid}/ 에 전체 산출
                                  └→ 검증 통과 시 atomic rename → reports/insta/{YYYY-MM-DD}/{slug}/
```

### 출력 원자성 · slug 전역 유일성 (`output.py`)

- 전체 PNG + `publication.json`을 임시 디렉토리(`{slug}.tmp-{pid}`)에 먼저 생성하고, 전부 성공 시에만 최종 디렉토리로 atomic rename. 실패 시 임시 디렉토리 삭제 — 부분 산출물이 최종 경로에 남지 않는다.
- slug 충돌 검사는 `reports/insta/*/{slug}` **전체 날짜 디렉토리를 스캔** — slug는 날짜와 무관하게 전역 유일 (랜딩 URL 키이므로).
- 동일 slug 존재 시 `--force` 필수. `--force`는 기존 디렉토리를 통째로 교체(삭제 후 rename)해 이전 슬라이드 파일이 잔존하지 않게 한다. status와 무관하게 동일 정책 (PRD G6의 published 덮어쓰기 `--force` 계약 승계).

### Publication 모델

랜딩 PRD §5 스키마와 **필드 단위로 호환**되게 정의한다 (PRD `posts.json` 레코드 = Publication 직렬화 + 랜딩 단계에서 `cover_image` 경로 치환). 명명은 snake_case.

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `schema_version` | int | Y | 시작값 1. 랜딩 소비자의 호환성 판단용 |
| `slug` | str | Y | 소문자 ASCII+하이픈, 전역 유일. 자동 생성 규칙은 §6 |
| `status` | `"draft" \| "published"` | Y | 기본 draft, `--publish` 시 published (PRD 계약) |
| `series` | Series enum | Y | 내부값 underscore: `trade_top`/`compare`/`value`/`budget_choice`/`lifestyle` |
| `title` | str | Y | |
| `eyebrow` | str | Y | 표지·조건 장의 시리즈 라벨 (PRD 계약) |
| `hook` | str | Y | 표지 훅 문장 (copywriting 산출) |
| `summary` | str | Y | 한 줄 결론 |
| `generated_at` | str (ISO 8601) | Y | 생성 실행 시각 |
| `published_at` | str (YYYY-MM-DD) \| null | published만 Y | draft는 null |
| `data_as_of` | str (YYYY-MM-DD) | Y | |
| `period_label` | str | Y | 예: "신고일 기준 최근 7일" |
| `cover_image` | str | Y | 출력 디렉토리 기준 상대경로 `01-cover.png` (랜딩 단계에서 public 경로로 치환) |
| `cover_alt` | str | Y | |
| `conditions` | `{label, value}[]` | Y(≥1) | 2번 장 조건 칩 (예산·지역·면적·기준일) |
| `items` | Item[] | Y | 시리즈별 최소 개수 규칙 (§7) |
| `secondary_items` | Item[] \| null | `trade_top`만 Y | 거래 급증 지역 랭킹. 다른 시리즈는 null |
| `comparison` | Comparison \| null | 비교형만 Y | 행: 지표 라벨, 열: 후보 값 |
| `narrative` | `{why: str[], fit_for: {a, b} \| null}` | 시리즈별 | copywriting 산출 |
| `methodology` | str[] (≥1) | Y | 시리즈별 의미론 문구 (집계 기준 포함) |
| `caveats` | str[] (≥1) | Y | 투자자문 아님 + 신고지연 + 재계산 차이 |
| `map_ctas` | MapCta[] | Y | PRD 계약과 동일 배열. compare·budget_choice는 지역별 2개, 그 외 1개. **trade_top만 빈 배열 허용** — 랭킹은 넛지 조건이 아니므로 가짜 의도 부여 금지 (PRD Q3 미결 승계, 랜딩 단계에서 결정) |

`Item`: `rank`(1부터 연속), `name`, `region`(nullable), `pnu`(19자리 or null), `metrics: {label, value, unit}[]`, `reasons: str[]`.

`MapCta` (PRD §5와 동일): `id`(게시물 내 유일), `label`, `nudges: str[]`(≥1), `sigungu_code`(nullable), `region_label`(nullable), `filters`(FilterState 9개 키 부분집합).

## 4. 캐러셀 슬라이드 템플릿

공용 렌더러 8종으로 구현하고 시리즈는 조합만 한다. 새 시리즈 추가 시 렌더 코드 변경 없이 `series/*.py`만 추가.

| # | 렌더러 | 입력 | 내용 |
|---|---|---|---|
| 1 | `render_cover` | hook, eyebrow | 훅 제목 대형 타이포 + 시리즈 라벨 |
| 2 | `render_conditions` | conditions, period_label, data_as_of | 조건 칩 + 데이터 기준일·집계 기간 (전 시리즈 필수) |
| 3 | `render_candidate` | item 1개 | 후보 상세 — 단지명·지역·metrics 표·reasons 2개 |
| 4 | `render_ranking_list` | items (≤5) | 5행 랭킹 리스트 (기존 리스트 레이아웃 이관) |
| 5 | `render_comparison_table` | comparison | A/B 비교표 |
| 6 | `render_narrative` | narrative.why 또는 fit_for | 차이 이유 3개 / 적합 대상 A/B |
| 7 | `render_caveats` | caveats, methodology | 읽을 때 주의할 점 (전 시리즈 필수 — 기준일·신고지연·재계산 고지) |
| 8 | `render_cta` | map_ctas, 투표 질문 | "여러분이라면 A vs B?" + apt-recom.kr + 면책 |

시리즈별 장 구성 (전 시리즈 6장 이상, 주의사항 장 필수):

| 시리즈 | 장 구성 (총 장수) |
|---|---|
| `budget_choice` | 표지 → 조건 → 후보A → 후보B → 비교표 → 이유 → 적합대상 → 주의 → CTA (9) |
| `lifestyle` | 표지 → 조건 → 랭킹 → 후보1~3 상세 → 주의 → CTA (7~8) |
| `value` | 표지 → 조건 → 랭킹 → 이유(왜 저렴한가) → 주의 → CTA (6) |
| `compare` | 표지 → 조건 → 지역A 1위 단지 → 지역B 1위 단지 → 비교표 → 이유 → 주의 → CTA (8) |
| `trade_top` | 표지 → 조건 → 최고가 랭킹 → 급증 지역 랭킹 → 주의 → CTA (6) |

출력 규칙:

- 파일명 `01-cover.png` ~ `NN-cta.png` (업로드 순서). 전 장 1080×1080.
- 전 장 footer 유지: `apt-recom.kr` + `공공데이터 기반 · 투자 자문이 아닙니다`.

### 텍스트 제약 (`textrules.py`)

렌더링 가능성은 검증 단계에서 보장한다 — 렌더 중 넘침 발견은 늦다.

- 필드별 최대 한도 상수: `hook`(2줄×전각 기준 폭), `conditions`(칩 6개·칩당 길이), `reasons`(항목 3개·항목당 1줄), `methodology`/`caveats`(각 4항목·항목당 2줄), `fit_for`(각 2줄), metrics(후보당 7행).
- 한도는 실제 폰트 측정(`ImageFont.getlength`) 기반으로 정의하고, 검증 시 줄바꿈 시뮬레이션으로 초과 여부를 판정한다.
- **초과 시 검증 실패로 발행 차단** (서사 필드). 예외: 데이터 유래 고유명(단지명·지역명)만 `truncate_text` 말줄임 허용.
- YAML 오버라이드: unknown key 거부, 비문자열 타입 거부, 빈 문자열 거부, 길이 한도 동일 적용.

### copywriting 규칙

- 훅·이유·적합대상은 시리즈별 템플릿 함수가 Publication 데이터로 생성. 예: `"{price_a_eok} vs {price_b_eok}, {area_a}㎡ vs {area_b}㎡ — 당신의 선택은?"`
- 이유 문구는 `top_contributors`·가격차·연식차 등 데이터에 존재하는 근거만 조합. 투자 단정 표현은 템플릿에 존재하지 않는다.
- `--copy-file {yaml}`: 지정 키(hook, why, fit_for)만 교체, 나머지 템플릿 유지. 오버라이드 문구에도 금지어·길이 검사 적용.

## 5. 시리즈별 데이터 사양

### 5-1. `budget_choice` (신규)

입력: `--budget {만원}` `--regions {sgg_a},{sgg_b}` `--area-a {㎡} --area-b {㎡}`(목표 전용면적, 밴드 ±5㎡ — `--area-tolerance`로 조정) `--nudge {profile}`(기본 `cost`) `--pnu-a/--pnu-b`(오버라이드)

**"같은 예산"의 정의** — `/api/nudge/score`의 `max_price`는 `price_per_m2 × 평균면적` **추정가**(`web/backend/routers/nudge.py:134-143`)라서 단독으로는 예산 보장이 안 된다. 따라서 실거래 집합을 먼저 만든다:

1. **적격 집합 구성 (로컬 DB)** — 지역별로 `trade_history`+`trade_apt_mapping`에서: 목표 면적 밴드 내 & **계약일(deal_year/month/day) 기준 최근 90일** & **거래가 ≤ 예산** 인 거래 보유 단지(pnu) 집합. 대표 거래 = 이 조건 내 계약일 최신, 동일 계약일이면 거래가 높은 순 (결정적 tie-break).
2. **대표 선정 (운영 API)** — `/api/nudge/score`(해당 지역, 면적 밴드 필터, top_n=50) 결과와 1의 pnu 집합을 교집합 → 넛지 점수 최상위 1개.
3. 어느 한 지역이라도 교집합이 비면 예외 중단 (조건·건수 출력).
4. `--pnu-a/--pnu-b` 오버라이드도 **1의 적격 집합에 속해야 한다** — 미속 시 예외 (지역·면적·예산·거래기간 검증 우회 불가).
5. 후보 상세 metrics는 §5-4 detail API로 채운다.

카드 표기 가격 = 1의 대표 거래가 → 예산 이하가 구성상 보장된다. 계약일 기준이므로 caveat에 신고지연 고지 필수.

### 5-2. `lifestyle` (신규)

입력: `--profile {nudge}`(필수 — pet/commute/education/senior/investment/safety/cost/newlywed/nature) `--region {sgg}` `--max-price`(선택) `--min-area/--max-area`(선택)

선정: budget_choice와 동일 패턴 — 로컬 DB에서 최근 90일(계약일) 실거래 보유(+가격·면적 조건) 적격 집합 → `/api/nudge/score`(profile, top_n=50, `min_hhld` 적용) 교집합 상위 3~5개. `value`의 min_hhld 재검증(미달 시 예외) 동일 적용.

metrics: `top_contributors` 상위 3개 + 대표 거래가 + 면적 + 준공연도 (+§5-4 detail 보강).

통근시간: `/api/commute`가 존재하므로 표시 자체는 가능하나 파일럿 제외 (§1 비목표). 조건 칩에는 "지하철·버스 접근성 반영"으로 표기 — 통근시간으로 표현하지 않는다.

### 5-3. `compare` (개편)

비교 단위를 명시한다: **비교표는 지역 집계, 후보 장은 각 지역 추천 1위 단지.**

- 비교표 행 (집계 가능한 지표만): 넛지 점수(넛지 상위 10개 단지 평균 — 기존 계약 유지), 중위 실거래가·거래 건수(로컬 DB `trade_history`, 기간 명시), 평균 연식(로컬 DB `apartments.use_apr_day` 지역 집계).
- 지역A/B 장: 각 지역 넛지 1위 단지를 `render_candidate`로 상세 표시 (pnu 보존 — PRD G4, metrics는 §5-4).
- methodology에 각 행의 집계 기준을 필수 명시 ("점수는 상위 10개 단지 평균", "가격은 최근 N일 중위 실거래가"). "지역 전체 평균" 표현 금지 (PRD 계약).
- map_ctas: 지역별 2개 (PRD :179-185 결정 승계).

### 5-4. 후보 상세 metrics 취득 — 기존 detail API

`render_candidate`·비교표의 단지 단위 지표(지하철 접근성, 배정초 유무, 안전점수, 월 관리비)는 **기존 공개 API `GET /api/apartment/{pnu}`**(`web/backend/routers/detail.py:95`)로 채운다.

- 선정 확정된 후보 2~5개에만 호출 — 호출량 무시 가능.
- 백엔드 무변경, sync 테이블 확장 불필요, 서비스 상세 화면과 동일 값 보장.
- **월 관리비 정의**: detail API의 면적별 관리비 계산(`services/mgmt_cost_calc.compute_by_area`) 결과 중 목표 면적대 값. 연간 환산 병기.
- 응답에 해당 지표가 없으면(관리비 미보고 단지 등) 해당 행 "정보 없음" 표기 — 값 생략이지 fallback 아님. detail API 자체가 실패(비200)하면 발행 중단.

### 5-5. `trade_top` (개편)

- fetch 이관 + G2(쿼리에 `m.pnu` select 추가). 최고가 랭킹 의미론 유지: **신고일(`t.created_at`) 기준** 최근 N일.
- **급증 지역 랭킹 재정의**: 현행 `fetch_top_hot_districts()`는 최근 기간 신고 건수 카운트만 있어 "급증"이 성립하지 않는다 (기존 카드 제목 "거래 신고 급증"부터 부정확). 쿼리를 **직전 동일 기간 대비**로 확장 — 현재 N일 vs 직전 N일 신고 건수, 증가 건수·증가율 계산.
- 표본 규칙 (제안서 "표본 적은 지역 제외"): 현재 기간 신고 건수 `MIN_REPORT_COUNT`(상수, 초기값 20) 미만 지역 제외. 조건 통과 지역이 5개 미만이면 발행 실패.
- 카드·methodology 표기: "직전 {N}일 대비 신고 건수 증가" — 계약일 아님을 명시.

### 5-6. `value` (개편)

- fetch 이관. 의미론 유지: `min_hhld` 재검증 + 미달 시 예외 중단, `price_per_m2` 없는 후보 제외·전부 없으면 예외, 5개 미만 발행 실패 (PRD §9 계약).
- "왜 저렴한가" 이유 장은 `top_contributors`·가격 데이터 근거만 사용.

## 6. CLI

```
# 워크스페이스 루트 기준 (.venv은 루트 공용 — 워크트리에는 없음)
.venv/bin/python -m scripts.insta_cards --series budget-choice \
    --budget 70000 --regions 11440,41135 --area-a 59 --area-b 84
.venv/bin/python -m scripts.insta_cards --series lifestyle --profile newlywed --region 41135 --max-price 70000
.venv/bin/python -m scripts.insta_cards --series value --region 11305 --min-hhld 100   # 기존 옵션 호환
공통 옵션: --slug --publish --copy-file --days --dry-run --force
```

- **series 명명 정규화**: 내부 Series enum은 underscore(`budget_choice`), CLI 인자는 하이픈(`budget-choice`) — 명시적 매핑 상수(`SERIES_CLI_NAMES`). slug 조립에는 하이픈 표기(`SERIES_SLUGS`)만 사용.
- **자동 slug 규칙** (`--slug` 미지정 시): 단일 지역 `{series_slug}-{sgg}-{yyyymmdd}`, 두 지역 `{series_slug}-{sgg_a}-vs-{sgg_b}-{yyyymmdd}`. 예: `budget-choice-11440-vs-41135-20260713`. 생성 후 slug 포맷 검증을 동일하게 통과해야 한다.
- `--dry-run`: 검증 + 선정 결과 콘솔 요약만. **파일을 일절 생성하지 않는다** (임시 디렉토리 포함).
- `--publish`: status=published + published_at 기록. 미지정 시 draft.
- 하위호환: 기존 `scripts/generate_insta_cards.py`는 shim으로 유지 (§3).
- trade_top·budget_choice·lifestyle·value는 로컬 DB(`trade_history` 등) 사용 → 실행 전 Railway→로컬 **증분 sync로 충분** (`trade_history`/`trade_apt_mapping`/`apt_price_score` 모두 증분 대상 — `batch/sync_from_railway.py`). CLI 시작 시 마지막 sync 시각을 조회해 24시간 초과면 경고 출력 (차단하지 않음 — 운영자 판단).

## 7. 검증 · 에러 처리

`Publication.validate()`가 렌더 전에 실행. 하나라도 실패하면 예외로 전체 발행 중단 (부분 발행·fallback 없음).

| 규칙 | 내용 |
|---|---|
| 필수 필드 | §3 표의 필수 컬럼 전부. published인데 published_at null이면 예외 |
| slug 포맷 | 소문자 ASCII+하이픈. `reports/insta/*/` 전역 스캔 충돌 시 `--force` 필요 |
| items | rank 1부터 연속·중복 없음. 최소 개수: trade_top·value 5, lifestyle 3, compare·budget_choice 2. trade_top은 secondary_items도 5 |
| pnu 포맷 | 존재 시 19자리 숫자, 위반 시 예외 |
| metrics 정합 | budget_choice: 비교표 행 라벨과 후보 metrics 라벨 일치. compare 는 비교표(지역 집계)와 후보 장(단지 지표)이 별개이므로 열 2개·행별 값 개수 일치만 검증 |
| map_ctas | trade_top 외 ≥1 (trade_top은 빈 배열 허용), id 게시물 내 유일, nudges ≥1, filters 키는 FilterState 9개 allowlist만 |
| 금지어 | hook/why/fit_for에 단정 표현("오를", "저평가", "무조건" 등 목록 상수) 포함 시 차단 — 오버라이드 문구 포함 |
| 텍스트 한도 | §4 textrules 초과 시 예외 (고유명 truncate 제외) |
| 기준일 | data_as_of 미래·형식 오류 시 예외 |

에러 처리:

- 데이터 부족(적격 집합 공집합·후보 미달·API 빈 응답)은 명시적 예외 + 원인 메시지(조건·건수 출력). 조용한 축소 발행 금지.
- 운영 API 실패(비200·malformed JSON·필수 키 누락)는 재시도 없이 중단 (수동 CLI — 운영자 재실행).
- 동점 후보 tie-break는 결정적으로 정의 (§5-1).

## 8. 테스트

파일: `scripts/tests/test_insta_cards.py`

검증 명령 (워크스페이스 루트 기준 — 워크트리에서는 `../../.venv` 사용):

```
.venv/bin/python -m unittest scripts.tests.test_insta_cards -v
.venv/bin/ruff check scripts/insta_cards scripts/tests
.venv/bin/ruff format --check scripts/insta_cards scripts/tests
```

(`ruff check --fix`/`ruff format`은 구현 중 수정 명령 — 검증 단계에서는 `--check`만.)

케이스:

1. 검증 규칙 단위 테스트 — §7 각 규칙별 실패 케이스가 예외를 내는지 (Publication 직접 구성, DB/API 불필요)
2. 슬라이드 계약 — 시리즈별 정확한 장 수·순서·파일명, 모든 PNG 1080×1080
3. 레이아웃 — 긴 한글 hook·단지명·이유 문구의 줄바꿈/한도 판정 (textrules 시뮬레이션과 실렌더 bounding-box 일치)
4. copywriting — 템플릿 산출물에 금지어 없음; YAML 문법 오류·unknown key·타입 오류·빈 문자열 거부; 오버라이드가 지정 키만 교체
5. 선정 로직 — budget_choice/lifestyle 적격 집합(면적 밴드·예산 이하·90일)과 교집합·tie-break를 mock 데이터로 검증; pnu 오버라이드가 적격 집합 검증을 우회하지 못하는지
6. API 응답 방어 — 200 + malformed JSON / 필수 키 누락 시 중단
7. 출력 원자성 — 중간 렌더 실패 시 최종 디렉토리 미생성; `--dry-run`이 파일을 하나도 만들지 않는지; 다른 날짜 동일 slug 충돌; `--force` 후 이전 슬라이드 잔존 없음
8. CLI — 기존 3종 옵션 파싱 동일 동작 + `scripts/generate_insta_cards.py` shim 회귀
9. trade_top — 직전 기간 대비 계산·MIN_REPORT_COUNT 필터를 mock 데이터로 검증
10. 수동 스모크 — 증분 sync만 수행한 환경에서 실 DB/API `--dry-run` 1회 + 파일럿 2건 실제 생성 후 육안 확인 (골든 이미지 테스트는 폰트 환경 의존이라 자동화하지 않고 육안 확인으로 대체 — 텍스트 배치는 3의 bounding-box 검사로 커버)

## 9. 파일럿 발행 계획

1. **"같은 7억, 서울 59㎡ vs 경기 역세권 84㎡"** (budget_choice, `--area-a 59 --area-b 84`) — 제안서 추천 1호
2. lifestyle `newlywed` 1건
3. 이후 주간 로테이션: 시세 40%(trade_top) + 비교 30%(budget_choice·compare) + 라이프스타일 30%. 운영 명령은 기존 인스타 카드 주간 플로우에 통합.

## 10. 리스크

| 리스크 | 대응 |
|---|---|
| 캐러셀 전환으로 기존 단일 카드 산출물 소멸 | shim CLI 유지 + 출력 형식 변경을 운영 메모에 기록. 기존 PNG 소비처는 수동 업로드뿐 |
| 관리비 등 metrics 결측 단지 | "정보 없음" 표기로 노출 (숨김·대체값 금지) |
| budget_choice 자동 선정이 의도와 다른 단지 선택 | `--dry-run` 사전 확인 + `--pnu-a/--pnu-b` 오버라이드 (적격 집합 검증은 유지) |
| 로컬 DB 신선도 | CLI 시작 시 마지막 sync 시각 24h 초과 경고 (§6) |
| detail API 스키마 변경 | datasources에 필수 키 검증 — 누락 시 발행 중단 (조용한 열 누락 방지) |
| 랜딩 단계 스냅샷 계약 변경 | Publication을 PRD §5와 필드 호환으로 정의 + schema_version 명시 |
