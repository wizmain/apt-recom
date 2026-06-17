---
name: apt-recom
description: Recommend, compare, and analyze South Korean apartment complexes (아파트 단지) by lifestyle keywords. Use when a user asks to find, recommend, compare, or analyze apartments in Korea — e.g. mentions a region (지역/시군구/동), price or area range, or lifestyle priorities like 학군 (school district), 안전 (safety), 출퇴근 (commute), 가성비 (value), 자연친화 (nature), 반려동물 (pets), 신혼육아 (newlywed/childcare), 시니어 (senior), 투자 (investment). Calls the public apt-recom.kr REST API to produce answers.
compatibility: Requires network access to https://api.apt-recom.kr (public REST API, no auth).
metadata:
  homepage: https://apt-recom.kr
  openapi: https://api.apt-recom.kr/openapi.json
  version: "1.0"
---

# apt-recom (집토리) — Korean Apartment Recommendation

This skill drives the public REST API of **집토리 / apt-recom** to recommend,
compare, and analyze apartment complexes across South Korea.

- **API base**: `https://api.apt-recom.kr`
- **Auth**: none (public, read-only). All endpoints are under `/api/*`.
- **Full machine spec**: `https://api.apt-recom.kr/openapi.json` (OpenAPI 3.0) —
  fetch this for exact request/response schemas; this file is the *playbook*, not
  the full reference.

## Domain conventions (read first)

- **`pnu`** — the apartment complex id used across all detail/similar endpoints.
  Obtain it from search or list results, never invent it.
- **Amounts** are integers in **만원 (10,000 KRW)**. e.g. `deal_amount: 95000` = 9.5억.
- **Area** is in **㎡** (`exclu_use_ar`). Multiply by ~0.3025 for 평 (pyeong).
- **`sigungu_code`** is a **5-digit** district code; `bjd_code` is a 10-digit dong code.
- Some complexes have **null coordinates** (`lat`/`lng`) — handle gracefully, never
  drop a recommendation solely for missing coords.

## Nudge categories (lifestyle weights)

`POST /api/nudge/score` takes a `nudges` array of category codes. The canonical,
always-current list is `GET /api/codes/nudge` (`{code, name}` pairs) — **fetch it
first if unsure**. Current categories:

| code | meaning (KR) |
|------|--------------|
| `cost` | 가성비 (value for money) |
| `commute` | 출퇴근 (commute / transit) |
| `education` | 학군 (school district) |
| `safety` | 안전 (safety) |
| `nature` | 자연친화 (nature / green) |
| `pet` | 반려동물 (pet-friendly) |
| `newlywed` | 신혼육아 (newlywed / childcare) |
| `senior` | 시니어 (senior) |
| `investment` | 투자 (investment) |

## Workflow A — Recommend by region + lifestyle

The most common request ("조용하고 학군 좋은 곳 추천해줘 in 분당").

1. **Resolve the region** (if the user named a place):
   `GET /api/apartments/search?q={지역명}`
   → returns `{ results, region_candidates? }`. If `region_candidates` has ≥2 items,
   ask the user which one, or pick the best `match_type: "region"` entry. Use its
   `code` as `sigungu_code` (5-digit) or `bjd_code` (10-digit dong).

2. **Map lifestyle words → nudge codes** (see table above), then score:
   ```
   POST /api/nudge/score
   Content-Type: application/json
   {
     "nudges": ["education", "safety"],
     "sigungu_code": "41135",
     "top_n": 10,
     "min_area": 84, "max_area": 115,
     "max_price": 150000,
     "built_after": 2010
   }
   ```
   Optional filters: `min_area`/`max_area` (㎡), `min_price`/`max_price` (만원),
   `min_floor`, `min_hhld`/`max_hhld`, `built_after`/`built_before`,
   bbox (`sw_lat`/`sw_lng`/`ne_lat`/`ne_lng`), `keyword`.
   → returns top complexes with a 0–100 nudge score and per-category contributions.

3. **Present** ranked results: name, region, score, and the top contributing
   factors. Offer to open detail or compare.

## Workflow B — Apartment detail

`GET /api/apartment/{pnu}` → basic info, price/safety scores, transaction history,
school district, nearby facilities. For raw trades: `GET /api/apartment/{pnu}/trades`.

## Workflow C — Compare complexes

Fetch `GET /api/apartment/{pnu}` for each `pnu` (2–5 complexes) and build a metric
matrix (price per ㎡, scores, 세대수/total_hhld_cnt, 준공연도, facility distances).

## Workflow D — Find similar complexes

`GET /api/apartment/{pnu}/similar?mode=combined&top_n=5`
- `mode`: `location` | `price` | `combined`
- optional: `exclude_same_sigungu`, `area_range`, `hhld_range`, `age_range`

For lifestyle-weighted similarity: `POST /api/apartment/{pnu}/similar/lifestyle`.

## Workflow E — Market dashboard

- `GET /api/dashboard/summary` — price trend by sigungu (시군구)
- `GET /api/dashboard/trend` — monthly price & transaction-volume trend

## Endpoint quick reference

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/apartments` | List by map bbox + filters |
| GET | `/api/apartments/search?q={kw}` | Search by region or complex name |
| GET | `/api/apartment/{pnu}` | Complex detail |
| GET | `/api/apartment/{pnu}/trades` | Transaction history |
| GET | `/api/apartment/{pnu}/similar` | Similar complexes |
| POST | `/api/apartment/{pnu}/similar/lifestyle` | Lifestyle-weighted similar |
| POST | `/api/nudge/score` | Lifestyle recommendation scoring |
| GET | `/api/nudge/weights` | Nudge weight configuration |
| GET | `/api/codes/nudge` | Valid nudge category codes |
| GET | `/api/dashboard/summary` | Price trend by sigungu |
| GET | `/api/dashboard/trend` | Monthly price/volume trend |
| GET | `/openapi.json` | Full OpenAPI 3.0 spec |

## Notes

- Be explicit about units (만원, ㎡) when presenting numbers to users.
- Prefer `sigungu_code`/`bjd_code` over free-text `keyword` for precise region filtering.
- Recommendations are data-driven scores, not financial advice — say so when relevant.
- For anything not covered here, consult `https://api.apt-recom.kr/openapi.json`.
