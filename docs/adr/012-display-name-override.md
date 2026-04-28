# ADR-012: 사용자 친화 단지명 컬럼(display_name) 도입

- **상태**: Accepted
- **날짜**: 2026-04-28

## 맥락

`apartments.bld_nm` 은 K-APT 원본 단지명을 그대로 보존하는 컬럼이지만, 일부 단지의 원본 표기가 사용자에게 친숙하지 않거나 거래 데이터(`trade_history.apt_nm`)·정규화 명칭(`bld_nm_norm`)과 일치하지 않는 케이스가 있다.

대표 사례: `pnu = 1144010200000430000`
- `bld_nm` = `'공덕2삼성임대'` (K-APT 원본)
- `bld_nm_norm` = `'삼성래미안공덕2차아파트'`
- 거래 `apt_nm` = `'공덕2삼성래미안'` (매매 338건), `'삼성래미안공덕2차'` (전월세 30건)

운영자가 `bld_nm` 을 직접 수정해도 `batch/fix_apartment_info.py` 가 다음 실행에서 Kakao keyword API 결과로 다시 덮어씌웠고, 그 과정에서 K-APT 원본 추적성도 잃었다.

## 결정

`apartments` 테이블에 사용자 친화 명칭을 보관하는 `display_name TEXT` 컬럼을 추가하고, 다음 정책을 함께 적용한다.

1. **원본 보존**: `bld_nm` 은 K-APT 원본 그대로 유지하며, 어떤 배치도 자동 갱신하지 않는다.
2. **자동 보완 트리거**: `apartments` 에 `BEFORE INSERT` 트리거(`apartments_display_name_default`) 를 두어 INSERT 시 `display_name` 이 비어 있으면 `bld_nm` 으로 자동 채운다. 다양한 INSERT 사이트(`enrich_apartments`, `backfill_trades`, `mgmt_cost_parser` 등)를 일일이 수정하지 않아도 정합성이 유지된다.
3. **신규 등록 시 Kakao 명칭 사용**: `batch/kapt/register_new_apartments.py` 는 K-APT 엑셀로 신규 단지를 등록할 때 Kakao keyword API 의 `place_name` 을 `display_name` 으로 채운다 (`bld_nm` 은 K-APT 원본).
4. **표시용 SELECT 통합**: 사용자 응답을 만드는 모든 SELECT 는 `COALESCE(a.display_name, a.bld_nm) AS bld_nm` 로 alias 한다. API 응답 필드명은 `bld_nm` 그대로 유지되어 프론트엔드 변경이 필요 없다.
5. **검색 키 확장**: `bld_nm` / `bld_nm_norm` 외에 `display_name` 도 LIKE 매칭 키로 추가한다. 운영자가 채운 표시명으로도 검색이 매칭된다.
6. **fix_apartment_info 갱신 대상 이동**: 기존에 `bld_nm` 을 Kakao keyword 결과로 갱신하던 로직을 `display_name` 으로 옮긴다.
7. **운영자 수동 보정**: 별도 admin API 나 ad-hoc 스크립트를 만들지 않고, `UPDATE apartments SET display_name = '...' WHERE pnu = '...'` SQL 로 처리한다. group_pnu 단지의 경우 대표 PNU(`group_pnu = pnu`)에만 채우면 된다.

## 근거

- **원본 추적성**: K-APT 원본을 잃지 않으면서 사용자 친화 표기를 분리 관리.
- **응답 계약 안정성**: 응답 필드명 `bld_nm` 을 유지(COALESCE alias)하여 프론트엔드/모노레포 shared 타입 변경이 필요 없다.
- **검색 회수율 향상**: 표시명까지 매칭에 포함되므로 운영자가 보정한 명칭으로도 챗봇/검색이 동작.
- **변경 범위 최소화**: BEFORE INSERT 트리거로 다수 INSERT 사이트의 코드 수정을 회피.
- **배치 멱등성**: `bld_nm` 이 더 이상 자동 갱신되지 않아 K-APT 동기화 ↔ 운영자 보정 간의 race 가 사라진다.

## 결과

### 수정 파일
- `web/backend/database.py` — `apartments.display_name` 컬럼 추가, idempotent ALTER, BEFORE INSERT 트리거 함수 + 트리거 정의.
- `web/backend/routers/apartments.py`, `dashboard.py`, `commute.py`, `similar.py`, `nudge.py`, `detail.py`, `admin.py` — 표시용 SELECT 에 `COALESCE(display_name, bld_nm) AS bld_nm` alias 적용. nudge/detail 의 fallback LIKE 에 `display_name` 추가. admin allowlist 의 `bld_nm` → `display_name` 으로 교체.
- `web/backend/services/search_engine.py` — `APT_COLS` alias 적용, 단지명 검색 LIKE 3 곳에 `display_name` 추가.
- `web/backend/services/tools.py` — 챗봇 tool 응답 SELECT 들에 alias 적용, 검색 LIKE 에 `display_name` 추가, `get_apartment_detail` 응답 `name` 필드는 `display_name` 우선.
- `batch/kapt/register_new_apartments.py` — `geocode_address` 가 Kakao `place_name` 반환, UPSERT 에 `display_name` 컬럼 + ON CONFLICT 절 추가.
- `batch/fix_apartment_info.py` — Kakao keyword 결과로 `display_name` 을 갱신 (`bld_nm` 갱신 폐지).
- `docs/adr/012-display-name-override.md` (본 문서)

### 무수정 (트리거가 자동 보완)
- `batch/trade/enrich_apartments.py`, `batch/trade/backfill_trades.py`, `batch/kapt/ingest_full_kapt.py`, `web/backend/services/mgmt_cost_parser.py`, `apt_eda/src/improve_trade_mapping.py`

### DB 1 회성 작업
```sql
-- 컬럼/트리거는 backend 부팅 시 create_tables() 에서 자동 적용.
-- 기존 행 backfill (NULL → bld_nm 복사):
UPDATE apartments SET display_name = bld_nm WHERE display_name IS NULL;

-- 첫 운영자 보정 사례:
UPDATE apartments SET display_name = '삼성래미안공덕2차' WHERE pnu = '1144010200000430000';
```

### 프론트엔드
변경 없음. 응답 필드명 `bld_nm` 유지로 `packages/shared/types/apartment.ts` 및 모든 컴포넌트가 그대로 동작.

### 모니터링
- `SELECT COUNT(*) FROM apartments WHERE display_name IS NULL` — 0 이어야 함. 0 이 아니면 트리거 누락 의심.
- `SELECT pnu, bld_nm, display_name FROM apartments WHERE display_name <> bld_nm LIMIT 50` — 운영자 보정/Kakao 갱신 결과 점검용.
