---
name: apt-recom
description: 대한민국 아파트 단지 검색·상세·비교·시세동향·학군 조회. 라이프스타일 키워드(출퇴근/교육/안전/반려동물 등) 기반 NUDGE 스코어링과 실거래가·K-APT 관리비·CCTV 안전지수를 활용하려 할 때 사용.
---

# apt-recom — 집토리 아파트 데이터 MCP

대한민국 아파트 데이터를 라이프스타일 키워드 기반으로 검색·상세조회·비교·추천하는 MCP 서버 사용 방법을 설명한다.

## 데이터 출처

- 국토교통부 아파트 실거래가 (매매·전월세 이력)
- K-APT 공동주택 관리정보 (관리비, 시설, 구조)
- 공공데이터포털 CCTV 안전 지수
- 교육청 학군 배정

## 연결

| 항목 | 값 |
|---|---|
| Transport | Streamable HTTP (MCP 2025 spec) |
| Endpoint | `https://api.apt-recom.kr/mcp/` |
| Server Card | `https://apt-recom.kr/.well-known/mcp/server-card.json` |

응답은 모두 한국어 JSON 문자열, 금액은 만원 단위, 면적은 ㎡.

## Tool 목록

| 이름 | 무엇 / 언제 |
|---|---|
| `search_apartments` | 라이프스타일 키워드 + 지역으로 NUDGE 스코어 상위 단지 검색. "강남구 출퇴근 좋은 아파트". |
| `get_apartment_detail` | 단지명/PNU 로 단일 단지 상세(점수·시설·학군·거래이력 요약). |
| `compare_apartments` | 2~5 단지 매트릭스 비교. "A vs B". |
| `get_similar_apartments` | 위치/가격/라이프스타일/종합 모드의 유사 단지 top_n. |
| `get_market_trend` | 시군구 단위 월별 거래량·평균가 추이. |
| `get_school_info` | 단지의 초·중·고 학군 배정. |
| `get_dashboard_info` | 시군구 거래 동향 — 이번 달 요약 + 랭킹 + 최근 N개월 시계열. |

## NUDGE 라이프스타일 키워드

`search_apartments(nudges=[...])` 에 사용 가능한 ID:

`cost`(가성비) · `pet`(반려동물) · `commute`(출퇴근) · `newlywed`(신혼부부) · `education`(교육) · `senior`(시니어) · `investment`(투자) · `nature`(자연친화) · `safety`(안전).

생략 시 `keyword` 에서 자동 추론, 추론 실패하면 `["commute"]`.

## 전형적 사용 시나리오

1. 사용자: "공덕동에서 학군 좋은 단지 추천해줘"
   → `search_apartments(keyword="공덕동", nudges=["education"], top_n=5)`
2. 사용자: "그 중 1위 단지 학군 자세히"
   → `get_school_info(query="<단지명>")`
3. 사용자: "OO 아파트랑 XX 아파트 비교"
   → `compare_apartments(queries=["OO", "XX"])`
4. 사용자: "강남구 시세 어때?"
   → `get_market_trend(region="강남구", period="1y")`

## 인자 노트

- 면적: `min_area`, `max_area` (㎡, 전용면적)
- 가격: `min_price`, `max_price` (만원, 매매가 추정)
- 준공: `built_after` (예: 2015 → 2015년 이후)
- 지역명은 시도/시군구/동 모두 허용. 동일 지명이 여러 시군구에 있으면 후보 목록을 반환하니 사용자에게 재질의 후 `search_keyword` 로 재호출.

## 추가 자원

- 사이트: https://apt-recom.kr
- API 카탈로그: https://apt-recom.kr/.well-known/api-catalog
- OpenAPI: https://api.apt-recom.kr/openapi.json
