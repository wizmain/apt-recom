# 가격흐름 — 상세 팝업 새 탭 + 상단 바로가기 (설계)

- 작성일: 2026-11-26
- 상태: 사용자 승인 대기
- 관련: 오르는 단지(`docs/superpowers/specs/2026-11-25-rising-complexes-design.md`, ADR-018),
  지도 배지(`docs/superpowers/specs/2026-11-26-map-rising-indicator-design.md`)

## 1. 의도

오르는 단지 집계(면적대 중위가격·6/12개월 변화·지역/단지 등급)를 **단지를 살펴보는 자리(상세 팝업)**에서
바로 보게 하고, 홈 상단에서 **순위 화면(`/rising`)으로 가는 길**을 만든다. 지금 홈에서 `/rising` 으로 가는
길은 지도 팝업 링크 하나뿐이다.

이름은 사용자 확정으로 **"가격흐름"** — 값이 내린 단지 상세에서도 어색하지 않고, "앞으로 오른다"는 예측으로
읽히지 않으며, 상세 탭 줄의 네 글자 이름들과 길이가 맞는다.

## 2. 목표 / 비목표 / 반목표

**목표**
- 상세 팝업(`DetailModalClient`)에 **"가격흐름" 탭** 신설 — "가격분석" 바로 뒤.
- 홈 상단 [지도 | 실거래대시보드] 그룹에 **"가격흐름" 바로가기**(→ `/rising`) 추가.
- 사용자에게 보이는 이름 "오르는 단지" → "가격흐름" 통일(아래 4.3).

**비목표**
- 가격분석 탭 변경(통합하지 않는다 — 사용자 결정).
- `/rising` 진입 시 해당 단지 자동 선택, 홈 안의 세 번째 화면(viewMode) 신설.
- 단지 SEO 페이지(`/apartment/[pnu]`)에 같은 탭 추가.
- 내부 식별자(`rising` 경로·파일·타입·테이블·코드 주석) 개명, URL `/rising` 변경.

**반목표**
- 지도 배지 ▲%와 탭 첫 화면 숫자가 다른 것(같은 면적대 선택 기준을 써야 한다).
- 가격분석 탭(면적별 평균)과 숫자가 달라 보이는데 이유가 안 보이는 것.
- 대표 단지가 아닌 PNU 로 열었을 때 "집계 없음"으로 잘못 보이는 것.
- 휴대폰 폭에서 상단 바가 넘쳐 다른 버튼을 가리거나, 바로가기가 조용히 사라지는 것.

## 3. 결정 사항 (사용자 확정)

| 항목 | 결정 |
|---|---|
| 이름 | **가격흐름** — 상단 바로가기·상세 탭·`/rising` 페이지 제목·지도 팝업 링크 문구에 공통 |
| 상단 | **바로가기**(`/rising` 이동). 홈 안 화면 전환 아님 |
| 상세 | 가격분석에 통합하지 않고 **새 탭** |
| 탭 구성 | 면적대 칩 → 지표 → 월별 차트 → 월별 표·최근 거래 → `/rising` 링크 (아래 4.4) |
| 첫 면적대 | 최근 3개월 거래 최다 면적대(지도 배지·필터 없음 기준과 동일) |
| 집계 없음 | 탭은 항상 보이고 안내 문구 표시 |
| 구현 방식 | **1안**: 단지 요약 API 신설 + 면적대 상세는 기존 `GET /api/rising/{pnu}` 재사용 |

### 검토한 방식
- **1안(채택)** 요약 API(면적대 목록·첫 면적대·대표 PNU) + 기존 상세 API. 새 로직은 요약 조회 하나, 상세는
  `/rising` 드로어와 같은 경로·훅·컴포넌트. 대가는 첫 진입 요청 2회.
- 2안 모든 면적대 상세를 한 번에 — 요청 1회지만 안 볼 월별·거래까지 늘 받고, 상세 조회 로직이 중복된다.
- 제외: 프론트가 면적대마다 기존 상세 API 호출 — 비대표 PNU 는 404, 어떤 면적대가 있는지 미리 모른다.

## 4. 설계

### 4.1 API — `GET /api/rising/complex/{pnu}`
- 위치: `routers/rising.py`(경로 등록) → `services/rising.py` 신규 `get_complex_summary(conn, pnu)`.
  **라우트 등록 순서**: `/rising/complex/{pnu}` 를 `/rising/{pnu}` 보다 **먼저** 선언(아니면 "complex" 가 pnu 로 잡힌다).
- 처리:
  1. `apartments` 에서 `COALESCE(group_pnu, pnu)` 로 대표 PNU 변환. 요청 PNU 가 `apartments` 에 없으면 **404**.
  2. 대표 PNU 의 `apt_band_trend` 전 면적대 행 + `region_band_trend` 조인 — 면적대 순서는 `rising_area_band.sort_order`.
  3. 첫 면적대: **`get_map_trends(conn, [pnu], None, None)` 결과의 `area_band` 를 그대로 쓴다** — 지도 배지와
     같은 규칙(3개월 거래 DESC NULLS LAST, 동률은 면적대 순서)을 한 곳에서만 유지하기 위함.
- 응답(200):
  ```json
  {
    "base_ym": 202609,
    "pnu": "<대표 PNU>",
    "name": "...", "address": "...",
    "default_band": "84" | null,
    "bands": [
      { "area_band": "84", "area_band_name": "84㎡급",
        "item": RisingItem, "region": RisingRegion | null }
    ]
  }
  ```
  - `item` 은 기존 `_ITEM_COLUMNS_SQL` 과 같은 모양(`RisingItem`), `region` 은 `RisingRegion` 과 같은 모양
    (`DetailMetrics` 가 그대로 받는다 — 지역 순위 표시용). 지금 `get_meta` 안에 있는 지역 행 조립
    (`region_band_trend` 조회 + `_sigungu_names` 로 시군구명 부여 + `sido_code`)을 공용 함수로 추출해
    `get_meta` 와 새 함수가 함께 쓴다(같은 모양을 두 곳에서 따로 만들지 않기 위함).
  - 집계 행이 없으면 `bands: []`, `default_band: null` (200 — 프론트에서 오류와 구분해 안내 문구).
  - 집계 전(`base_ym` 없음)이면 `base_ym: null`, `bands: []`.

### 4.2 상단 바로가기 (`NudgeBar.tsx`)
- `ViewTabs` 그룹 안 세 번째 항목 **"가격흐름"** — `next/link` 로 `/rising` 이동. 화면 전환 버튼이 아니므로
  선택 상태가 되지 않는다(모양은 비선택 탭과 같게, 이동 링크임을 알 수 있게 `↗` 등 작은 표시는 빌더 판단).
- 클릭 시 `logEvent('price_flow_shortcut_click', { view_mode })` — 바로가기 효과 계측(기존 `logEvent` 패턴).
- 지도·대시보드 두 모드 모두에서 보인다.

### 4.3 이름 바꾸기 범위 (사용자에게 보이는 문구만)
- `app/rising/page.tsx` — `metadata.title`, `<h1>` → "가격흐름". 부제·description 은 의미 유지하며 이름만 맞춘다.
- `app/_home/Map/InfoWindowTrend.tsx` — "오르는 단지에서 보기 →" → "가격흐름에서 보기 →".
- `public/llms.txt` 등 외부 노출 문서에 해당 화면 언급이 있으면 함께 맞춘다(현재 없음 확인).
- 코드 주석·타입·파일명의 "오르는 단지"/`rising` 은 그대로 둔다.

### 4.4 상세 팝업 "가격흐름" 탭
- `DetailModalClient.tsx`: `TABS` 에 `'가격흐름'` 을 `'가격분석'` 다음에 추가, 분기 한 줄로 새 컴포넌트 렌더.
  탭 내용은 **별도 파일**(예: `app/_home/PriceFlowTab.tsx`) — 기존 파일(1,200줄+)에 끼워넣지 않는다.
- 데이터: 새 훅 `hooks/useRisingComplex.ts`(요약) — **탭이 처음 열릴 때** 요청(상세 팝업을 열 때마다 요청하지 않음),
  pnu 변경 시 취소·재요청. 면적대 상세는 기존 `useRisingDetail(대표PNU, 선택 면적대)`.
- 화면(위→아래):
  1. 안내 한 줄: "가격분석 탭은 면적별 평균, 여기는 면적대 중위가격(직거래·이상 거래 제외) 기준입니다."
  2. 면적대 칩 — `bands` 만, 첫 선택은 `default_band`. 선택 상태는 탭 안 로컬 상태(팝업 닫으면 초기화).
  3. 지표 — `app/rising/DetailMetrics`(`item`, `region` 은 요약 응답의 해당 면적대 값).
  4. 월별 중위가격 차트 — `app/rising/BandPriceChart`.
  5. 월별 표·최근 거래 — `app/rising/DetailTables`(`MonthlyTable`, `RecentTradesTable`).
  6. 링크 "가격흐름에서 다른 단지와 비교 →" (`/rising`).
- 상태:
  - 요약 로딩/오류 — 기존 탭들의 로딩·`EmptyState` 패턴.
  - `bands` 비어 있음 — "이 단지는 가격흐름 집계 대상이 아닙니다 (수도권 · 최근 실거래 기준)." + `/rising` 링크.
  - 면적대 상세 404(요약과 상세 사이 집계 교체 등) — 드로어와 같은 "이 면적대 거래 없음".

## 5. 검증
- 백엔드 통합 테스트(test_core): 대표 PNU 변환(비대표 PNU 요청 → 대표 PNU 집계), 면적대 정렬, `default_band` 가
  지도 API 결과와 같음, 집계 없는 단지 `bands: []`, 없는 PNU 404, `/rising/complex/x` 가 상세 라우트로 잡히지 않음.
- 프론트: lint·타입체크·빌드. 브라우저 확인 — 수도권 단지 탭(칩 전환·차트), 비대표 PNU 단지, 비수도권 단지 안내,
  지도 배지 ▲% 와 탭 첫 화면 6개월 변화 일치, 상단 바로가기 이동(지도·대시보드 모드), **360px 폭에서 상단 바 넘침 없음**.

## 6. 빌더 판단 (작성자 결정 — 바꾸려면 말씀)
- 탭 컴포넌트 파일명·위치, 칩 모양(오르는 단지 화면 면적대 선택과 같은 계열).
- 바로가기의 "이동 링크" 표시 방식.
- 360px 에서 상단 바가 넘치면 **조용히 숨기지 말고** 보고 — 배치 조정안을 사용자와 정한다.
