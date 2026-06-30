# PRD: 단지 상세 → 라이프스타일 추천 전환 다리 (Detail-to-Recommendation Bridge)

- 작성일: 2026-06-30
- 대상 서비스: 집토리(apt-recom)
- 상태: Draft (구현 핸드오프 전)
- 범위 요약: SEO로 단지 상세 페이지에 유입된 사용자를 "이 단지가 맘에 든다면 → 비슷한 라이프스타일 아파트 추천" CTA로 핵심 추천 흐름(홈 지도 nudge score)에 진입시킨다. 이때 보고 있던 단지의 특성을 **이미 계산된 nudge 점수 기반**으로 추론해 nudge 프리셋을 미리 채운다.
- 연관 PRD: `docs/prd/2026-06-28-first-visit-action-guidance.md` (홈/지도 첫 진입 온보딩). 본 PRD와 nudge 프리셋 개념을 공유하므로 §6.FE·§8에서 소유 위치를 일관화한다.

---

## 1. 배경 / 문제

집토리의 SEO 유입 대부분은 홈이 아니라 **단지 상세 페이지**로 들어온다.

근거 (실제 코드):
- 사이트맵은 백엔드 `/sitemap.xml` 의 단지 PNU URL(좌표 있는 유효 PNU 30k+)을 가져온다 — `web/frontend-next/src/app/sitemap.ts:23-35`, 주석 `web/frontend-next/src/app/sitemap.ts:8-9`.
- 상세 페이지는 SSR + on-demand ISR 로 단지명·주소·점수·학군을 HTML 본문에 렌더하고 `ApartmentComplex` JSON-LD 를 주입한다 — `web/frontend-next/src/app/apartment/[pnu]/page.tsx:22-23`, `:85-116`, `:118-141`. 즉 색인·랜딩 타깃이다.

그런데 온보딩 노력은 홈/지도 첫 진입에만 집중돼 있다.
- 첫 방문 온보딩(시나리오 카드 + 코치마크)은 지도 뷰 한정으로 설계됨 — `docs/prd/2026-06-28-first-visit-action-guidance.md:55-69`.
- 상세 페이지(SSR `_view.tsx`)에는 추천 흐름으로 넘어가는 어떤 장치도 없다 — `web/frontend-next/src/app/apartment/[pnu]/_view.tsx:34-53` 의 섹션 조립(BasicInfo/PriceInfo/LifeScores/School/Facilities/Safety/Population/RecentTrades)에 CTA 슬롯 부재.

결과: **검색으로 단지 상세에 떨어진 사용자를 핵심 가치(라이프스타일 추천)로 넘기는 다리가 없다.** SEO 자산이 단발 조회로 끝나 이탈한다.

### 비즈니스 관점
- 가장 큰 유입 표면(상세 페이지)에서 핵심 가치(추천)로의 전환율이 0에 가깝다 → SEO 투자 대비 활성화 손실.
- 상세→추천 전환 1건은 곧 "지역+라이프스타일이 확정된 고의도 세션"으로, activation 품질이 높다.

---

## 2. 목표 / 성공지표

### 목표
1. 상세 페이지에서 **탭 1회**로, 그 단지의 특성이 미리 채워진 추천 결과(top-N)에 도달하게 한다.
2. 백엔드 추천 로직 변경 없이 기존 추천 인프라(`POST /api/nudge/score`, store 액션, `useNudge` 자동 실행)를 재사용한다.

### 성공지표 (측정 가능, YAGNI 압축)
| 지표 | 정의 | 측정 방법 |
|------|------|-----------|
| detail_cta_ctr | 상세 페이지뷰 대비 CTA 탭 비율 | (신규 이벤트) `detail_recommend_cta_click` / 기존 `detail_view`(`web/backend/routers/detail.py:94-100`) |
| bridge_activation | CTA 탭 세션 중 후속 `nudge_score` 도달 비율 | `detail_recommend_cta_click` → `nudge_score`(`web/backend/routers/nudge.py:52-64`) |
| preset_quality | 프리셋 자동 nudge 를 사용자가 유지/조정한 비율 | (선택) `nudge_score` payload 의 `nudges` 와 프리셋 비교 |

> YAGNI: A/B 실험·세그먼트 대시보드·개인화 모델은 범위 외. 기존 `user_event` 적재 + 사후 집계만.

---

## 3. 사용자 스토리 / 시나리오

- US-1: 검색으로 "○○아파트" 상세에 들어온 사용자로서, 페이지 하단/적절한 위치에서 "이 단지가 맘에 든다면 비슷한 집 추천받기" 버튼을 보고 탭하면, 이 단지의 강점(예: 학군·안전·가성비)이 미리 선택된 추천 결과를 보고 싶다.
- US-2: 추천 결과로 넘어간 사용자로서, 기본 추천 범위가 그 단지가 속한 지역(시군구)이어서 "현실적으로 갈 수 있는 비슷한 집"을 보고 싶다.
- US-3: 추천으로 넘어간 뒤 라이프스타일 칩을 조정(추가/제거)해 결과를 다듬고 싶다 (기존 NudgeBar 그대로 동작).
- US-4: 프리셋이 특정 단지의 특성을 잘 못 잡았더라도, 추천 화면에서 칩을 직접 바꿔 즉시 재추천받고 싶다.

---

## 4. 범위 (Scope)

### In scope
- 단지 상세(SSR) 페이지에 전환 CTA 섹션 추가 (`_view.tsx` 조립부 + 신규 섹션 컴포넌트).
- 상세 데이터의 **이미 계산된 nudge 점수**(`detail.scores`)에서 상위 nudge 를 추려 프리셋 생성하는 로직(데이터 기반, 하드코딩 금지).
- 상세 → 홈 진입 시 nudge 프리셋 + 지역(시군구) 컨텍스트 전달 (쿼리파라미터 기반 deep link).
- 홈 진입 시 쿼리파라미터를 1회 소비해 store(`selectedNudges`, `selectedRegion`)를 초기화하고 기존 `useNudge` 자동 추천을 태우는 부트스트랩 훅.
- 전환 효과 측정용 `user_event` 신규 event_type 적재.

### Out of scope
- nudge 가중치/스코어링 알고리즘 변경 (`web/backend/routers/nudge.py`, `web/backend/services/scoring.py` 로직 불변).
- 상세 페이지 자체의 신규 데이터(시설/거래 등) 추가.
- 좌표 기반 "내 주변" 추천 (상세는 단지 sigungu_code 가 명확하므로 지역 기준으로 충분).
- 로그인/개인화, A/B 인프라.
- 첫 방문 온보딩(시나리오 카드/코치마크) — 별도 PRD 소관. 본 PRD는 프리셋 정의 소유 위치만 공유 합의.

---

## 5. 현재 구현 분석 (file:line 인용)

### 5.1 두 개의 상세 표면 (중요)
집토리에는 단지 상세가 **두 군데** 존재한다. 본 기능의 1차 타깃은 SEO 랜딩인 (A) SSR 페이지다.

- (A) SSR 상세 페이지 = SEO 랜딩: `web/frontend-next/src/app/apartment/[pnu]/page.tsx`(Server Component, `fetchDetail`→`/api/apartment/{pnu}` `:27-38`) + `web/frontend-next/src/app/apartment/[pnu]/_view.tsx`(섹션 조립자 `:21-54`). **store(zustand) 접근 불가** — 순수 Server Component.
- (B) 홈 SPA 내 모달 상세: `web/frontend-next/src/app/_home/DetailModalClient.tsx`(`"use client"`, store 사용 `:162-166`). 홈 안에서 카드 클릭으로 열리며 `selectedPnu` store 와 연동.
- 홈 SPA 진입점: `web/frontend-next/src/app/page.tsx:1-7` → `HomeShell`. `HomeShell` 이 `useNudge()` 와 `useUrlSyncedPnu()` 를 mount — `web/frontend-next/src/app/_home/HomeShell.tsx:73-74`.

함의: CTA 는 (A) SSR 페이지에 붙어야 SEO 유입자에게 보인다. 그러나 (A)는 store 가 없으므로, **추천 컨텍스트를 store 직접 세팅으로 전달할 수 없고**, 홈으로의 네비게이션(URL) 으로 전달해야 한다(§6.2 설계).

### 5.2 상세 데이터에 이미 nudge 점수가 있다 (프리셋 데이터 소스)
- `apartment_detail` 응답은 9개 nudge 코드별 점수를 `scores` 로 반환한다 — `web/backend/routers/detail.py:183-186` (`scores = {nid: calculate_nudge_score(...) for nid in get_nudge_weights()}`).
- SSR `_view.tsx` 는 이 `scores` 를 `LifeScores` 로 이미 렌더한다 — `web/frontend-next/src/app/apartment/[pnu]/sections/LifeScores.tsx:20-37` (점수 내림차순 정렬). nudge 코드→라벨 매핑도 여기 존재 (`LifeScores.tsx:8-18`).
- 결론: "이 단지의 특성" 은 **추가 계산/추가 API 없이** `detail.scores` 의 상위 점수 nudge 로 데이터 기반 추론 가능. 정적 휴리스틱(카드별 nudge 고정) 불필요.

### 5.3 추천 트리거 메커니즘 (재사용 대상)
- `useNudge` 는 `[selectedNudges, customWeights, searchKeywords, selectedRegion, filters]` 변화 시 `scoreApartments()` 를 자동 호출 — `web/frontend-next/src/hooks/useNudge.ts:29-31`.
- `scoreApartments` 는 `selectedNudges` 가 비면 즉시 반환, 지역이 있으면 `bjd_code`/`sigungu_code` 로 `POST /api/nudge/score` — `web/frontend-next/src/lib/store/nudgeSlice.ts:60-103` (region 분기 `:83-91`).
- 결론: 홈에서 `selectedNudges` 와 `selectedRegion` 만 채워지면 **추가 추천 호출 코드 없이** 기존 `useNudge` 가 자동으로 추천을 실행한다.

### 5.4 nudge 선택 / 지역 선택 store 액션
- `toggleNudge(nudgeId)` — `web/frontend-next/src/lib/store/nudgeSlice.ts:45-50`. 일괄 세팅 액션은 현재 없음(프리셋 다건 세팅 시 toggle 반복 또는 신규 set 액션 필요 — §6.FE).
- `selectRegion(region)` — `web/frontend-next/src/lib/store/searchSlice.ts:61-68`. `region = { type: 'sigungu'|'emd', code, label }` (`web/frontend-next/src/types/apartment.ts:38-42`). region 세팅 + `fetchApartments()` await + `regionFitNonce` bump 로 지도 fit.
- 상세 데이터에 지역 키 존재: `apartment_detail.basic.sigungu_code` (`web/backend/routers/detail.py:69`, nudge.py 도 동일 컬럼 사용). 단지명도 `basic.bld_nm` 로 사용 가능.

### 5.5 상세 → 홈 라우팅 / URL 동기화
- `useUrlSyncedPnu` 는 `selectedPnu ↔ /apartment/:pnu` 양방향 동기화 — `web/frontend-next/src/hooks/useUrlSyncedPnu.ts:22-49`. 초기 mount + popstate 시 URL→store, `selectedPnu=null` 이면 `/` 로 pushState.
- 즉 홈(`/`) 진입은 표준 Next.js 네비게이션으로 가능하고, store 부트스트랩은 **쿼리파라미터를 읽는 신규 client 훅**이 담당해야 한다(현재 쿼리파라미터를 store 로 흡수하는 경로 없음 — 신규 필요).
- `selectApartment`/`clearSelection`/`selectedPnu` 는 mapSlice 에 정의 — `web/frontend-next/src/lib/store/mapSlice.ts:11,15,23,27-28`.

### 5.6 행동 로그 인프라
- `log_event(device_id, event_type, event_name, payload)` — `web/backend/services/activity_log.py:47-72`. device_id 없으면 no-op, 실패 흡수. INSERT 는 `user_event` 테이블.
- `user_event` 스키마: `event_type TEXT NOT NULL`, `payload JSONB`, **CHECK 제약 없음** — `web/backend/database.py:555-562`. 즉 신규 event_type 은 스키마 변경 없이 즉시 적재 가능. payload 는 GIN 인덱스 보유 (`database.py:675`).
- 기존 적재 지점: 상세 조회 `detail_view`(`web/backend/routers/detail.py:94-100`), 추천 `nudge_score`(`web/backend/routers/nudge.py:52-64`) — 둘 다 BackgroundTasks.
- 주의: `log_event` 는 **서버 라우터 내부에서만** 호출된다. **클라이언트가 임의 이벤트를 적재할 범용 엔드포인트는 레포에 없다**(오픈이슈 Q1). chat_log 의 `_CONTEXT_WHITELIST`(`activity_log.py:22`)는 chat_log 전용이며 user_event 와 무관.

### 5.7 백엔드 추천 API
- `POST /api/nudge/score` — `nudges`(필수) + `sigungu_code`/`bjd_code`/`keyword(s)`/bounds + 필터. 지역 지정 시 bounds 무시 — `web/backend/routers/nudge.py:20-42`, `:91-97`, `:124-128`. top_n 정렬 반환 `:322-324`.

> 결론: 본 기능은 **프론트엔드 + 경량 측정** 중심이다. 백엔드 추천/스코어링 로직 변경 불필요. DB 스키마 변경 불필요(이벤트는 기존 user_event 재사용). 유일한 백엔드 판단은 "클라이언트 이벤트 수집 엔드포인트를 새로 둘지"(Q1).

---

## 6. 변경 설계 (핸드오프별)

### DB → db-architect
**신규 테이블/컬럼 없음.** 효과 측정은 기존 `user_event`(`web/backend/database.py:555-562`)에 신규 event_type 만 적재한다 (CHECK 제약 없어 스키마 변경 불필요).

- 사용 예정 event_type / payload(jsonb):
  - `detail_recommend_cta_view` (payload: `{ pnu, top_nudges: [...] }`) — CTA 노출(선택, 노출 대비 클릭률용)
  - `detail_recommend_cta_click` (payload: `{ pnu, preset_nudges: [...], sigungu_code }`)
- 검토(권고만): 프리셋 라벨/문구를 common_code 로 둘지. 단, **§6.FE 의 프리셋은 단지별 동적**(detail.scores 기반)이므로 common_code 로 둘 대상은 "nudge 코드→라벨/이모지"뿐이며 이는 이미 `common_code group_id='nudge'`(`web/backend/routers/codes.py:9`)에 존재. 따라서 **DB 작업은 사실상 없음** — event_type 명세 확정·문서화만.

### API → api-developer
신규 추천 엔드포인트 **불필요**. 기존 `POST /api/nudge/score`, `GET /api/apartment/{pnu}`, `GET /api/codes/nudge` 로 충분.

- (조건부, Q1) 클라이언트 이벤트 수집 경로 결정:
  - 옵션 A (권장): 최소 범위 `POST /api/events` 신규 엔드포인트. **event_type 화이트리스트**(`detail_recommend_cta_view`, `detail_recommend_cta_click`)만 허용하고 그 외 거부. 내부적으로 기존 `log_event`(`web/backend/services/activity_log.py:47`) 재사용, device_id 는 기존 `get_user_identifier(request)`(`web/backend/routers/nudge.py:8`, `:46`)로 도출. BackgroundTasks 비동기 적재.
  - 옵션 B (측정 축소): CTA 클릭은 별도 적재하지 않고, 후속 `nudge_score`(이미 적재됨)의 payload 에 `source: 'detail_bridge'` 식별자를 추가해 전환을 사후 추정. 이 경우 `NudgeScoreRequest`(`web/backend/routers/nudge.py:20-42`)에 `source: str | None` 선택 필드를 추가하고, `log_event` payload 에 포함 — 신규 엔드포인트 불필요, 다만 노출/클릭 funnel 의 상단(노출·클릭) 은 측정 불가.
  - 결정 기준: detail_cta_ctr(노출 대비 클릭)까지 보려면 A, activation 만 보면 B. **본 PRD 권장은 A**(가장 큰 유입 표면의 funnel 가시성 확보).
- 어느 옵션이든 추천 스코어링 코드는 불변.

### FE → frontend-developer (핵심)
신규 컴포넌트/훅으로 분리(기존 컴포넌트에 조건문 끼워넣기 금지 — 프로젝트 표준).

#### 6.1 프리셋 추론 (설계 질문 1 — 데이터 기반)
- 입력: SSR `_view.tsx` 가 이미 보유한 `detail.scores`(9 nudge 점수, `web/backend/routers/detail.py:183-186`) + `detail.basic.sigungu_code`/`bld_nm`/`new_plat_plc`.
- 규칙(하드코딩 금지, 순수 함수로 분리 — 예: `src/lib/detailPreset.ts`):
  - `scores` 내림차순 정렬(이미 `LifeScores.tsx:27` 와 동일 정렬) 후 **상위 2개 nudge 코드**를 `preset_nudges` 로 선택.
  - 동점/저점 가드: 최고점이 임계(예: 일정 점수) 미만이면 단일 nudge 또는 안내 문구만 노출(임계값은 상수로 명명, 매직넘버 금지).
  - 카드 라벨/이모지는 nudge 코드 라벨(common_code `nudge` 또는 `LifeScores.tsx:8-18` 의 LABELS)을 재사용 — 새 라벨 사전 만들지 않음.
- 결과적으로 프리셋은 **단지마다 다르게** 산출 (정적 카드 4종 매핑과 대비). 사용자에게는 "이 단지의 강점: 학군·안전 → 비슷한 집 보기" 식으로 근거가 드러난다.

#### 6.2 상세 → 홈 컨텍스트 전달 (설계 질문 2 — 쿼리파라미터 deep link)
- SSR 페이지는 store 가 없으므로(§5.1), CTA 는 **쿼리파라미터를 실은 홈 링크**로 네비게이트한다. 형식(명명은 snake_case, 소문자 시작):
  - `/?nudges=education,safety&sigungu_code=11680&region_label=강남구&from=detail&src_pnu=<pnu>`
  - `nudges`: 콤마구분 nudge 코드. `sigungu_code`: `detail.basic.sigungu_code`. `region_label`: `detail.basic.new_plat_plc` 등에서 도출한 표시 라벨.
- 홈 부트스트랩(신규 client 훅 `useBridgeParams`, `HomeShell` 에서 1회 호출):
  1. mount 시 `useSearchParams`(Next.js)로 쿼리 읽기.
  2. `sigungu_code`+`region_label` 있으면 `selectRegion({ type:'sigungu', code, label })`(`searchSlice.ts:61`) 호출 → `selectedRegion` 세팅 + `fetchApartments` + 지도 fit.
  3. `nudges` 있으면 store 에 일괄 세팅. `toggleNudge` 반복은 경합 위험 → **신규 `setSelectedNudges(ids: string[])` 액션을 nudgeSlice 에 추가**(단일 set, `clearSelectedNudges`(`nudgeSlice.ts:110`) 와 대칭).
  4. 세팅 후 쿼리파라미터 제거(replaceState)해 재실행/뒤로가기 루프 방지. `useUrlSyncedPnu`(`useUrlSyncedPnu.ts`) 와 충돌하지 않도록 `selectedPnu` 가 없는 `/` 경로에서만 동작하도록 가드.
  5. 이후 기존 `useNudge`(`useNudge.ts:29-31`)가 `selectedNudges`/`selectedRegion` 변화를 감지해 **자동 추천** → 별도 추천 호출 코드 불필요.
- 왜 쿼리파라미터인가: (a) SSR 페이지는 store 직접 세팅 불가, (b) 표준 `<Link>`/`router.push` 로 동작, (c) 공유 가능한 deep link 부수효과, (d) `useUrlSyncedPnu` 의 기존 URL↔store 패턴과 일관.

#### 6.3 신규/수정 항목
- (신규) `src/app/apartment/[pnu]/sections/RecommendCta.tsx` — Server Component. props 로 `scores`, `sigungu_code`, `region_label`, `pnu`, `bld_nm` 받아 프리셋 추론 결과를 노출하고, 홈 deep link `<Link>` 렌더. 노출 이벤트(`detail_recommend_cta_view`)는 클릭 가능한 Client 하위 컴포넌트 또는 §6.API 옵션에 따라 처리.
- (신규) `src/lib/detailPreset.ts` — `buildDetailPreset(scores): { preset_nudges: string[] }` 순수 함수(테스트 용이). 임계값 상수 명명.
- (수정) `src/app/apartment/[pnu]/_view.tsx:34-53` — 섹션 조립부에 `<RecommendCta .../>` 추가(예: LifeScores 직후 또는 페이지 하단). `detail.scores`, `detail.basic` 이미 구조분해됨(`_view.tsx:30-32`).
- (신규) `src/hooks/useBridgeParams.ts` — §6.2 부트스트랩. `useSearchParams`/`replaceState`, SSR 안전(`"use client"`).
- (수정) `src/lib/store/nudgeSlice.ts` — `setSelectedNudges(ids: string[])` 액션 추가(타입 `NudgeSlice` 에도 시그니처 추가).
- (수정) `src/app/_home/HomeShell.tsx:73-74` — `useBridgeParams()` 호출 추가(useNudge·useUrlSyncedPnu 와 나란히).
- (선택) CTA 클릭 시 이벤트 전송 — §6.API 옵션 A 면 `POST /api/events`, 옵션 B 면 전송 없음(nudge_score source 식별로 대체).

#### 6.4 프리셋 소유 위치 — first-visit PRD 와의 공존 (설계 질문 3)
- first-visit PRD 의 프리셋은 **정적 카드(quiet/school/commute/value_new) = 고정 nudge 조합 + 기본 지역**(`docs/prd/2026-06-28-first-visit-action-guidance.md:143-151`).
- 본 PRD 의 프리셋은 **단지별 동적(detail.scores 상위 nudge) + 단지 지역**.
- 두 개념은 입력이 다르다(정적 시나리오 vs 단지 점수). 충돌을 피하기 위한 합의:
  - 공통 출력 계약을 통일: 두 경로 모두 최종적으로 `{ nudges: string[], region?: SelectedRegion }` 를 만들고, **동일한 store 진입 액션**(`setSelectedNudges` + `selectRegion`)을 사용한다. → 추천 트리거 경로는 단일.
  - 정의 모듈 분리: 정적 시나리오 = first-visit PRD 소관(`scenarioPresets` 또는 common_code), 동적 단지 프리셋 = 본 PRD `src/lib/detailPreset.ts`. **서로의 정의를 import 하지 않는다**(책임 분리).
  - 쿼리파라미터 부트스트랩(`useBridgeParams`)은 본 PRD 가 소유. first-visit 카드는 홈 내부에서 store 직접 세팅(쿼리파라미터 불필요)이므로 경로가 겹치지 않는다.
  - ADR 권고: 이 "공통 출력 계약 + 진입 액션 단일화" 결정은 두 기능에 걸치므로 기록 가치 있음(§9).

### Test → test-writer
- 단위(FE, 순수 함수 우선):
  - `buildDetailPreset(scores)`: 상위 2개 nudge 선택, 동점/저점 임계 가드, 빈 scores 처리.
  - 쿼리파라미터 직렬화/파싱: `nudges` 콤마구분 round-trip, 잘못된 nudge 코드(존재하지 않는 코드) 무시.
- 통합(FE):
  - `useBridgeParams`: `/?nudges=...&sigungu_code=...` 진입 시 `setSelectedNudges`·`selectRegion` 호출되고 쿼리파라미터가 replaceState 로 제거되는지. `selectedPnu` 존재(`/apartment/:pnu`) 시 동작 안 함(가드).
  - 부트스트랩 후 `useNudge` 가 자동으로 `scoreApartments` 를 1회 실행하는지(기존 자동 실행 활용 검증).
  - `RecommendCta` 가 `scores` 가 비면 렌더 생략, 있으면 deep link href 에 올바른 `nudges`/`sigungu_code` 포함하는지.
- 백엔드(`web/backend/tests/test_core.py` 패턴, `@test` 데코레이터):
  - (옵션 A 채택 시) `POST /api/events` 가 화이트리스트 외 event_type 을 거부하고, 허용 type 은 user_event 에 적재되는지.
  - (옵션 B 채택 시) `NudgeScoreRequest.source` 가 정상 파싱되고 추천 결과에 영향 없는지(스코어링 불변 회귀).
  - `GET /api/apartment/{pnu}` 가 `scores` 에 9개 nudge 키를 모두 반환하는지(프리셋 데이터 소스 회귀 보호 — `detail.py:183-186`).

---

## 7. 데이터 / 외부 의존

- 프리셋 데이터 소스: 기존 `apartment_detail.scores`(추가 수집/추가 API 없음).
- 지역 컨텍스트: 기존 `apartment_detail.basic.sigungu_code`.
- nudge 코드/라벨: 기존 common_code `group_id='nudge'`(`web/backend/routers/codes.py:9`) + `LifeScores.tsx:8-18`.
- 행동 로그: 기존 `user_event` + `log_event`.
- 외부 공공데이터 신규 수집 의존 없음. 좌표 역지오코딩 의존 없음(지역은 단지 sigungu_code 사용).

---

## 8. 리스크 / 오픈이슈

리스크
- R1: SSR 페이지의 노출 이벤트(`detail_recommend_cta_view`)는 Server Component 에서 device_id 가 없을 수 있다(쿠키/헤더 기반 식별 필요). → 노출 이벤트는 클릭 가능한 Client 경계 컴포넌트에서 보내거나, 노출 측정을 포기(옵션 B)하고 클릭/activation 만 측정.
- R2: 쿼리파라미터 부트스트랩이 `useUrlSyncedPnu` 의 URL↔store effect 와 경합할 수 있음 → `useBridgeParams` 는 `/` 경로 + `selectedPnu===null` 일 때만 동작, 처리 후 replaceState 로 쿼리 제거(§6.2-4).
- R3: 프리셋이 단지 점수만 보므로 "지역 점수 vs 단지 점수" 의미 차이를 사용자가 오해할 수 있음 → CTA 문구에 "이 단지의 강점" 임을 명시.
- R4: 상위 2개 nudge 가 항상 의미 있는 차별점이 아닐 수 있음(점수가 평탄한 단지) → 임계 가드(§6.1)로 저점 시 단일/안내 처리.
- R5: 동적 프리셋과 first-visit 정적 프리셋이 별도 진입 경로를 가지면 추천 트리거가 분기될 수 있음 → 공통 출력 계약 + 단일 진입 액션으로 통일(§6.4).

오픈이슈 (추정 금지 — 확인/결정 필요)
- Q1: **[결정됨 — 옵션 A, 2026-06-30]** 클라이언트 이벤트 수집 엔드포인트로 화이트리스트 기반 `POST /api/events` 를 신설한다. 허용 event_type 은 `detail_recommend_cta_view`, `detail_recommend_cta_click` 만이며 그 외는 거부. 내부적으로 기존 `log_event`(`activity_log.py:47`) 재사용, BackgroundTasks 비동기 적재. (옵션 B nudge_score source 식별은 미채택.)
- Q2: SSR 페이지에서 device_id 식별 방식. `get_user_identifier`(`web/backend/services/identity.py`) 가 무엇을 근거로 device_id 를 도출하는지(쿠키/헤더) 확인해 노출 이벤트 적재 가능 여부 판단 필요. (본 PRD에서 identity.py 미열람 — 확인 항목.)
- Q3: CTA 배치 위치(LifeScores 직후 vs 페이지 하단)와 문구/이모지 — 디자인 협의.
- Q4: 프리셋 nudge 개수(상위 2 고정 vs 1~3 가변)와 저점 임계값 — 데이터 분포 확인 후 상수 확정.
- Q5: region_label 도출 규칙 — `new_plat_plc` 파싱 vs common_code `sigungu` 라벨 조회(추가 호출). 단순화를 위해 sigungu_code → common_code 라벨이 더 정확할 수 있음(확인).

---

## 9. 작업 순서 + 추정

권장 순서: db-architect → api-developer → frontend-developer → test-writer (본 기능은 FE 비중이 큼; DB 는 사실상 명세 확정만).

1. db-architect (XS, ~0.25d)
   - 신규 event_type 명세 확정(`detail_recommend_cta_view`/`_click` payload). `user_event` 스키마 변경 없음 재확인(`database.py:555-562`).
2. api-developer (S, ~0.5d, 조건부)
   - Q1 결정. 옵션 A: 화이트리스트 기반 `POST /api/events` 최소 구현(`log_event` 재사용). 옵션 B: `NudgeScoreRequest.source` 선택 필드 추가 + payload 반영.
3. frontend-developer (M, ~1.5~2d, 핵심)
   - `detailPreset.ts`(순수 함수) → `RecommendCta` 섹션 → `_view.tsx` 연결.
   - `nudgeSlice.setSelectedNudges` 추가 → `useBridgeParams` → `HomeShell` 연결.
   - (옵션 A) 클릭 이벤트 전송. deep link 직렬화/replaceState 가드.
4. test-writer (S, ~0.5~1d)
   - 프리셋 순수 함수·쿼리 round-trip·부트스트랩 가드·자동 추천 1회·CTA 렌더 조건·(API 옵션별) 이벤트/source 검증·detail.scores 회귀.

> ADR 작성 권고: **권고함**. 사유 — (1) SSR 랜딩에서 SPA store 로 컨텍스트를 넘기는 "쿼리파라미터 deep link 부트스트랩" 패턴 도입(구조적), (2) 클라이언트 행동 이벤트 수집 경로(`POST /api/events` 신설 여부) 결정, (3) first-visit PRD 와 공유하는 "추천 프리셋 공통 출력 계약 + 단일 진입 액션" 결정. ADR 직접 작성은 본 PRD 범위 밖(권고만) — `docs/adr/` 참조.
