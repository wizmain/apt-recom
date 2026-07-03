# 기획 제안: 첫 방문 진입장벽 낮추기 — 5가지 방향

- 작성일: 2026-07-03
- 대상 서비스: 집토리(apt-recom.kr)
- 상태: E + D 구현 완료 (feature/entry-friction-quickwins), C/A/B 는 데이터 확보 후 결정
- 대체 문서: `2026-06-28-first-visit-action-guidance.md` (시나리오 카드 + 코치마크 안)를 폐기하고 방향을 재검토한 결과물이다.

---

## 1. 배경 / 문제 정의

집토리의 핵심 가치는 라이프스타일(nudge) 기반 아파트 추천이다. 그러나 현재 첫 진입 화면은 핵심 가치를 숨기고, 그와 무관한 관문(검색)을 앞세운다.

### 현재 첫 진입 경험 (코드 근거)

**빈 세션 첫 페인트 상태:**
- 첫 화면은 지도 뷰. `viewMode` 초기값 `"map"` — `web/frontend-next/src/lib/store/mapSlice.ts:25`
- 아파트 목록은 지역/바운즈 없으면 조회하지 않음 — `searchSlice.ts:74-75` (`if (!mapBounds && !selectedRegion) return;`)
- 추천은 nudge 미선택 시 즉시 반환 → 결과 0 — `nudgeSlice.ts:91-94`. 결과 0이면 `ResultCards`는 아무것도 렌더링하지 않음 — `ResultCards.tsx:14`
- nudge 칩은 키워드/지역 없으면 비활성 — `NudgeBar.tsx:34` (`hasAnyKeyword`), `:377`, `:426`. 비활성 칩 클릭 시 `alert('지역명 또는 단지명을 먼저 입력해주세요.')` — `NudgeBar.tsx:443-445`
- 빈 화면의 유일한 능동 요소인 `RecentTradesBanner`는 상세 모달/대시보드로만 연결되고 추천으로 이어지지 않음 — `RecentTradesBanner.tsx:90-93`, `:126-131`

**숨은 2단계 (첫 추천 도달 경로):**
검색(지역/단지 입력) → nudge 칩 활성화 → 칩 클릭 → `useNudge`가 자동 재스코어 (`useNudge.ts:29-31`). 핵심 가치를 보려면 최소 2번의 명시적 액션 + 검색 서브스텝을 통과해야 한다.

### 재사용 가능 자산 (비용 산정의 핵심)

| 자산 | 위치 | 의미 |
|------|------|------|
| 딥링크 부트스트랩 훅 | `useBridgeParams.ts:30-76` (쿼리 `nudges`, `sigungu_code`, `region_label` 소비), `HomeShell.tsx:122-124`에 마운트 | 프리셋→자동추천 파이프라인 완성품 (#127) |
| 일괄 세팅 액션 | `nudgeSlice.ts:63-70` (`setSelectedNudges`), `searchSlice.ts:61-68` (`selectRegion`) | 값만 넣으면 `useNudge`가 추천 자동 실행 |
| 클라이언트 이벤트 로깅 | `POST /log/event` (`log.py:24-38`, event_type enum 제약 없음), `POST /events` (`events.py:20-72`) | 신규 event_type을 DB 변경 없이 즉시 적재 |
| 챗봇 인프라 | `chatSlice.ts:21-23` (`openChat`+`setInitialMessage`), SSE 스트리밍 + tools | 시드 메시지+오픈 패턴 존재 (`HomeShell.tsx:85-89`) |
| 9개 nudge 코드 | cost, pet, commute, newlywed, education, senior, investment, nature, safety | 라벨/이모지는 common_code `group_id='nudge'` + `GET /codes/{group}` (`codes.py:9-18`) |

---

## 2. 제안 A — 온보딩 게이트: 지도-우선 → 라이프스타일 셀렉터 우선 (L)

### 문제 가설
지도-우선 첫 화면(`mapSlice.ts:25`)이 신규 사용자에게 "검색부터 하라"고 강요한다. 첫 화면이 핵심 가치(라이프스타일 추천)를 숨기고 무관한 관문(검색)을 앞세운다.

### 제안 내용
지도 진입 전, 전체화면 온보딩 게이트를 첫 화면으로 노출한다.

1. "어떤 삶을 원하세요?" → nudge 칩 1~3개 선택 (검색 불필요)
2. 가벼운 지역 선택 (기존 `/api/apartments/search` region_candidates 재사용, 또는 "인기 지역" 기본값)
3. 완료 시 **이미 결과가 채워진 상태**로 지도에 착지

산출된 `{nudges, region}`은 기존 `setSelectedNudges` + `selectRegion` 단일 진입 액션으로 흘려보내고, `useNudge`가 자동 추천한다.

- 단계 수: 착지 → (1) 라이프스타일 칩 → (2) 지역(기본값 수락 시 0) → 추천. **실질 1~2 액션**
- 재방문/봇 처리: `localStorage`로 1회성, 지도 즉시 스킵 링크, 크롤러엔 게이트 미노출(SEO 보호)

### 예상 효과 / 측정 지표 (`/log/event`)
- 신규 `onboarding_view` → `onboarding_complete` → 기존 `nudge_score` (`nudge.py:52-64`) 퍼널 전환율
- 세션→첫 `nudge_score` 도달률(activation), time-to-first-recommendation 단축
- 게이트 스킵률(`onboarding_skip`)로 거부감 모니터

### 구현 범위 (L)
- FE: 신규 온보딩 화면 컴포넌트 + `mapSlice` `viewMode` 확장(또는 별도 게이트 상태) + `HomeShell` 분기 + 지역 미니피커 + 스킵/재방문 가드. 추천 실행부는 재사용(신규 코드 0)
- Backend / DB: 없음 (event_type만 추가)

### 리스크 / 트레이드오프
- 재방문 사용자·직접 지도 목적 사용자에게 마찰 → 스킵/기억 필수
- 첫 화면 패러다임 변경은 되돌리기 비용이 큼 → **채택 시 ADR 작성 대상**
- 모바일/데스크톱 레이아웃 이원화 부담

---

## 3. 제안 B — 제로클릭 자동 추천: 빈 지도를 없앤다 (M)

### 문제 가설
지도-우선을 유지하더라도, 첫 화면이 "빈 지도"라는 것이 진짜 장벽이다. 지역 없으면 목록 미조회(`searchSlice.ts:74-75`), nudge 없으면 추천 0(`nudgeSlice.ts:91-94`), 칩은 비활성(`NudgeBar.tsx:377`) — 세 관문이 동시에 "볼 게 없는 화면"을 만든다.

### 제안 내용
첫 로드에서 키워드가 없을 때 **기본 지역 시드**(geolocation → 시군구 역매핑, 실패 시 기본 인기 지역 상수) + **균형형 기본 nudge 세트**를 자동 세팅해, 착지하는 순간 추천 카드가 이미 떠 있게 한다. 사용자는 칩을 바꿔가며 "조정"만 한다 (선택→조정 모델).

- 단계 수: 착지 → **0 클릭으로 추천 노출**. 이후 조정은 선택
- 핵심 변경: nudge 활성 조건을 "키워드 존재"에서 "지역 존재"로 완화 (`NudgeBar.tsx:34`의 `hasAnyKeyword` 의미 재정의)

### 예상 효과 / 측정 지표
- 첫 화면 이탈률(첫 `nudge_score` 없이 종료) 감소. `default_seed_applied` / `geo_seed_success` 이벤트
- 기본 프리셋 유지 vs 조정 비율 (`nudge_score` payload의 `nudges`를 기본셋과 비교 — `nudge.py:57-63`에 이미 적재)

### 구현 범위 (M)
- FE: 기본 지역/기본 nudge 시드 로직(신규 부트스트랩, 상수로 명명), nudge 활성 조건 완화, geolocation 처리(권한 거부 폴백)
- Backend: 좌표→시군구 역매핑 필요 시 경량 엔드포인트 (기존 경로 존재 여부 확인 필요 — 오픈이슈 Q1)
- DB: 없음

### 리스크 / 트레이드오프
- **모든 사용자의 기본 동작을 바꾼다** → 회귀 위험 최상. 기본 nudge 선택이 곧 "서비스의 의견"이 되어 편향 논란
- geolocation 권한 프롬프트가 오히려 거부감. 폴백 지역이 사용자와 무관하면 신뢰 저하 (폴백 발동조건/영향 명시 필수)
- "내가 안 골랐는데 추천이 떴다"는 오해 → 근거 라벨("현재 위치 기준" 등) 필수. **채택 시 ADR 작성 대상** (기본 추천 정책)

---

## 4. 제안 C — 대화형 진입: 자연어 한 문장 → 의도 추론 → 추천 (M)

### 문제 가설
칩 선택 UI는 "내 상황을 9개 코드 중 무엇으로 표현하지?"라는 번역 부담을 준다. 신규 사용자는 자기 말("애 키우기 좋고 회사 가까운 강남 근처")로 시작하고 싶은데, 현재 챗봇은 상세 분석 시드(`HomeShell.tsx:85-89`)로만 쓰이고 첫 추천 엔진으로는 노출되어 있지 않다.

### 제안 내용
첫 화면 상단에 자연어 프롬프트 바("어떤 집을 찾으세요?"). 한 문장 입력 → LLM이 의도를 nudge 코드 + 지역으로 매핑 → 동일한 `setSelectedNudges` + `selectRegion` 진입 액션으로 추천 실행. 챗 모달의 SSE/tools 재사용, 결과는 지도 카드로도 반영.

- 단계 수: 착지 → (1) 문장 입력 → 추천. **1 액션**

### 예상 효과 / 측정 지표
- `nl_prompt_submit` → `nudge_score` 전환율, 매핑 성공률(nudge 추론 후 결과>0 비율)
- 프롬프트 사용 세션의 activation vs 칩 세션 비교

### 구현 범위 (M)
- Backend (S~M): 챗 결과를 추천 프리셋으로 넘기는 경로 — `tools.py`에 `set_recommendation_preset` tool 신설 또는 의도→nudge 매핑 서비스. 스코어링 로직 불변
- FE (M): 첫 화면 프롬프트 바 + tool 결과를 store(`selectedNudges`, `selectedRegion`)로 반영하는 브릿지. `openChat`/`setInitialMessage`/ChatModal 재사용
- DB: 없음

### 리스크 / 트레이드오프
- LLM 지연·비용이 첫 진입 크리티컬 패스에 들어감 → 캐시/타임아웃 + 실패 시 칩 UI 폴백(발동조건 명시)
- 의도→nudge 매핑 오류 시 엉뚱한 추천 → 매핑 결과를 칩으로 시각화해 "수정 가능"하게
- 프롬프트 인젝션/무관 질의 방어 필요

---

## 5. 제안 D — 큐레이션 딥링크 진입점: "지역 × 라이프스타일" 프리셋 갤러리 (S~M)

### 문제 가설
신규 사용자는 "무엇을 검색해야 할지" 자체를 모른다 (cold start). 현재 유일한 능동 요소인 `RecentTradesBanner`는 상세/대시보드로만 빠지고 추천으로 데려가지 못한다 (`RecentTradesBanner.tsx:90-93`, `:126-131`). 탐색의 출발점(examples)이 없다.

### 제안 내용
"강남 · 교육/안전", "판교 · 출퇴근", "은퇴 · 자연/시니어" 같은 큐레이션 타일 갤러리를 첫 화면의 별도 서페이스(지도 오버레이 카드가 아닌 전용 섹션 또는 `/explore` 라우트)로 제공한다.

각 타일은 `/?nudges=education,safety&sigungu_code=11680&region_label=강남구` 형태의 딥링크일 뿐이고, **이미 존재하는 `useBridgeParams`(`useBridgeParams.ts:30-76`)가 그대로 소비**해 추천을 자동 실행한다. 추가 배관 거의 없음. 부수효과로 각 타일은 공유·SEO 랜딩이 된다.

- 단계 수: 착지 → (1) 타일 탭 → 추천. **1 액션**

### 예상 효과 / 측정 지표
- 타일별 CTR (`explore_tile_click`, payload에 preset), 타일→`nudge_score` 전환
- 어떤 지역×라이프스타일 조합이 신규 유입을 activation시키는지 학습 → 큐레이션 개선 루프

### 구현 범위 (S~M)
- FE: 타일 갤러리 컴포넌트 + 진입 배치. 딥링크 소비 로직은 재사용(신규 0)
- 데이터: 프리셋 목록은 common_code 또는 경량 프리셋 테이블/설정으로 관리 (하드코딩 금지). 라벨/이모지는 `codes.py` 재사용
- Backend: 정적/설정 기반이면 없음. 프리셋을 DB로 둘 경우 조회 엔드포인트 S

### 리스크 / 트레이드오프
- 폐기된 "시나리오 카드" 안과의 차별화 필수 — 지도 오버레이·코치마크가 아닌 독립 서페이스로, 정적 고정이 아니라 데이터 기반 큐레이션으로
- 큐레이션 유지보수 부담 → 실거래 트렌드 기반 반자동 생성 검토
- 타일이 특정 지역에 편중되면 비인기 지역 사용자 소외

---

## 6. 제안 E — 빠른 적용: 기존 관문의 마찰 제거 (S)

### 문제 가설
패러다임을 바꾸지 않아도 즉시 줄일 수 있는 마찰이 있다. 비활성 칩 클릭 시 `alert()`(`NudgeBar.tsx:444`)는 막다른 피드백이고, 빈 결과 영역(`ResultCards.tsx:14`)과 빈 지도는 다음 행동을 알려주지 않는다.

### 제안 내용
점진적 노출로 기존 2단계를 "설명이 붙은 2단계"로 만든다.

1. 비활성 칩 클릭 시 `alert` 제거 → 검색창을 하이라이트하는 인라인 코치 ("먼저 지역을 고르면 추천이 켜져요")
2. 빈 결과 영역/빈 지도에 첫 실행 힌트 ("① 지역 검색 → ② 라이프스타일 선택") 슬롯
3. `RecentTradesBanner` 확장 뷰에 "이 지역 추천 보기" 액션 추가 → 해당 시군구 `selectRegion` + 기본 nudge 세팅 (딥링크 파이프라인 재사용). 데드엔드를 추천 런처로 전환

- 단계 수: 여전히 2단계지만 각 단계의 드롭오프를 낮춘다 (마이크로 개선)

### 예상 효과 / 측정 지표
- 비활성 칩 클릭 후 이탈률 → 검색 시작률 (`search_hint_shown` / `search_start`)
- 배너→추천 전환 (`recent_banner_recommend_click` → `nudge_score`)

### 구현 범위 (S)
- FE만: `NudgeBar`(alert 대체), 빈 상태 힌트, `RecentTradesBanner` 액션 1개. 전부 기존 store 액션 재사용
- Backend / DB: 없음

### 리스크 / 트레이드오프
- 근본적 패러다임 문제는 그대로 (임팩트 상한 낮음). 다른 큰 안의 대체가 아니라 징검다리/보완
- 힌트가 과하면 노이즈 → 첫 세션 1회만 노출

---

## 7. 비교표

| 제안 | 접근 축 | 첫 추천까지 액션 | 임팩트 | 구현 비용 | 리스크 | 재사용 자산 | 우선순위 |
|------|---------|:---:|:---:|:---:|:---:|------|:---:|
| **A** 온보딩 게이트 | 안내형 진입 (명시 선택) | 1~2 | 높음 | L | 높음 (패러다임·SEO·재방문) | setSelectedNudges / selectRegion / useNudge | 3 |
| **B** 제로클릭 자동추천 | 암묵 기본값 | 0 | 높음 | M | 매우 높음 (전체 기본동작·편향·geo) | useNudge, 활성조건 완화 | 4 |
| **C** 대화형 진입 | 자연어 의도추론 | 1 | 중~높음 | M (BE+FE) | 중 (LLM 지연/비용/매핑오류) | 챗 SSE/tools | 2 |
| **D** 큐레이션 딥링크 | 큐레이션 탐색 | 1 | 중 | S~M | 중 (유지보수) | **useBridgeParams 완성품** | **1** |
| **E** 마찰 제거 | 인플레이스 폴리싱 | 2 (저마찰) | 낮~중 | S | 낮음 | 기존 store 액션 | **1 (병행)** |

---

## 8. 추천 실행 순서

### 1순위 — E + D 병행 (빠른 검증 레이어)
둘 다 저비용이고, 딥링크 파이프라인(`useBridgeParams`)·클라이언트 로깅(`/log/event`)이 이미 완성되어 있어 거의 신규 배관 없이 붙는다. E는 즉시 드롭오프를 줄이고, D는 "1 액션으로 추천 도달"을 낮은 리스크로 검증한다. 이 단계에서 `session→nudge_score` 퍼널과 타일별 CTR로 **어떤 라이프스타일×지역 조합이 신규 유입을 activation시키는지 데이터를 확보**한다.

### 2순위 — C (대화형) 실험
챗 인프라가 이미 있어 중간 비용으로 "자연어 진입"이라는 구조적으로 다른 가설을 검증할 수 있다. D의 큐레이션 데이터가 nudge 매핑 품질 튜닝에 재활용된다.

### 최후 — A vs B 중 택1 (패러다임 전환)은 데이터 확보 후
A(명시적 게이트)와 B(암묵적 기본값)는 임팩트 상한이 가장 높지만 각각 재방문 마찰 / 전체 기본동작 변경이라는 큰 리스크를 진다. E·D·C로 얻은 "선호 프리셋·activation 곡선"이 있어야 A의 초기 화면 구성이나 B의 기본 nudge 세트를 근거 있게 정할 수 있다. 데이터 없이 A/B부터 착수하는 것은 폐기된 시나리오-카드 PRD와 같은 실수(가설을 UI로 먼저 고정)를 반복할 위험이 있다.

### ADR 정책
A 또는 B를 채택해 첫 진입 정보구조/기본 추천 정책을 바꾸는 시점에 ADR을 작성한다 (구조적 결정). E·D·C 단계는 기존 딥링크/로깅 패턴 재사용이므로 ADR 불필요.

---

## 9. 오픈 이슈 (구현 착수 전 확인)

- **Q1 (B)**: 좌표→시군구 역매핑 경로가 레포에 존재하는지 미확인. 없으면 B는 백엔드 S 추가
- **Q2 (C)**: 챗봇이 현재 `selectedNudges`/`selectedRegion` store를 세팅하는 경로가 있는지 미확인 (`tools.py` 상세 미열람) — C는 브릿지 신설 전제
- **Q3 (D)**: 프리셋 정의 소유 위치 (common_code vs 신규 프리셋 테이블) — db-architect 협의
- **Q4 (A)**: 온보딩 게이트와 SSR/SEO·`useUrlSyncedPnu` 라우팅 가드 상호작용 확인 필요

## 10. 관련 파일

- `web/frontend-next/src/lib/store/mapSlice.ts`, `nudgeSlice.ts`, `searchSlice.ts`
- `web/frontend-next/src/hooks/useNudge.ts`, `useBridgeParams.ts`
- `web/frontend-next/src/app/_home/HomeShell.tsx`, `NudgeBar.tsx`, `ResultCards.tsx`, `RecentTradesBanner.tsx`
- `web/backend/routers/nudge.py`, `log.py`, `events.py`, `codes.py`
- `web/backend/services/activity_log.py`
- `docs/prd/2026-06-30-detail-to-recommendation-bridge.md` (딥링크 선례)
