# 시설 데이터 수집 API 목록

## 수집 현황 요약

| # | 시설 | subtype | 현재 건수 | 범위 | 수집 방식 |
|---|------|---------|----------|------|----------|
| 1 | 버스정류장 | bus | 223,582 | 전국 | CSV 일괄등록 |
| 2 | CCTV | cctv | 221,522 | 전국 | API (JSON) |
| 3 | 보안등 | security_light | 42,822 | 수도권 | API (XML) |
| 4 | 병원 | hospital | 37,331 | 전국 | API (XML) |
| 5 | 편의점 | convenience_store | 21,480 | 수도권 | API (XML) |
| 6 | 학교 | school | 11,440 | 전국 | CSV 일괄등록 |
| 7 | 약국 | pharmacy | 9,943 | 수도권 | API (XML) |
| 8 | 공원 | park | 7,213 | 수도권 | 초기수집 |
| 9 | 반려동물시설 | pet_facility | 6,195 | 수도권 | 초기수집 |
| 10 | 동물병원 | animal_hospital | 3,933 | 전국 | CSV 일괄등록 |
| 11 | 유치원 | kindergarten | 2,617 | 수도권 | 초기수집 |
| 12 | 대형마트 | mart | 1,326 | 수도권 | API (XML) |
| 13 | 도서관 | library | 1,231 | 수도권 | 초기수집 |
| 14 | 소방서 | fire_station | 993 | 전국 | 초기수집 |
| 15 | 119안전센터 | fire_center | 769 | 전국 | 별도수집 |
| 16 | 지하철역 | subway | 756 | 수도권 | 초기수집 |
| 17 | 경찰서 | police | 81 | 수도권 | 초기수집 |

## API 수집 (`collect_facilities.py`)

### 1. 병원
- **API**: 건강보험심사평가원 병원정보서비스
- **URL**: `http://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList`
- **형식**: XML
- **파라미터**: `sidoCd=` (전체)
- **필드 매핑**: `yadmNm`→name, `YPos`→lat, `XPos`→lng, `addr`→address
- **상태**: 정상 (primary + secondary key)

### 2. CCTV
- **API**: 행정안전부 CCTV 통합관제
- **URL**: `http://apis.data.go.kr/1741000/cctv_info/info`
- **형식**: JSON (페이지당 100건 제한)
- **필드 매핑**: `MNG_INST_NM`→name, `WGS84_LAT`→lat, `WGS84_LOT`→lng, `LCTN_LOTNO_ADDR`→address
- **상태**: 정상 (secondary key)
- **주의**: 총 353,092건, 3,500+ 페이지, 수집에 약 5시간 소요

### 3. 편의점
- **API**: 소상공인시장진흥공단 상가(상권)정보
- **URL**: `http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong`
- **형식**: XML
- **파라미터**: `indsMclsCd=Q12` (편의점 업종)
- **필드 매핑**: `bizesNm`→name, `lat`→lat, `lon`→lng, `roadNmAddr`→address
- **상태**: 403 Forbidden (활용신청 승인 대기)

### 4. 약국
- **API**: 소상공인시장진흥공단 상가(상권)정보 (편의점과 동일 API)
- **URL**: `http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong`
- **형식**: XML
- **파라미터**: `indsMclsCd=Q01` (약국 업종)
- **필드 매핑**: `bizesNm`→name, `lat`→lat, `lon`→lng, `roadNmAddr`→address
- **상태**: 403 Forbidden (활용신청 승인 대기)
- **파일다룬로드주소**: https://file.localdata.go.kr/file/pharmacies/info

### 5. 대형마트
- **API**: 전국대규모점포표준데이터
- **URL**: `http://api.data.go.kr/openapi/tn_pubr_public_lrgscl_stlmnt_api`
- **형식**: XML
- **필드 매핑**: `bizplcNm`→name, `latitude`→lat, `longitude`→lng, `rdnmadr`→address
- **상태**: NO OPENAPI SERVICE ERROR (서비스 중단 또는 미등록)

### 6. 동물병원
- **API**: 농림축산식품부 동물병원정보
- **URL**: `http://apis.data.go.kr/1543061/animalHospService/getAnimalHospList`
- **형식**: XML
- **필드 매핑**: `bizPlcNm`→name, `lat`→lat, `lng`→lng, `roadNmAddr`→address
- **상태**: HTTP 500 (서버 오류)
- **대체**: CSV 일괄등록으로 전국 3,933건 등록 완료

### 7. 가로등
- **API**: 전국가로등정보표준데이터
- **URL**: `http://api.data.go.kr/openapi/tn_pubr_public_strplgc_api`
- **형식**: XML
- **필드 매핑**: `lgtPrvNm`→name, `latitude`→lat, `longitude`→lng, `rdnmadr`→address
- **상태**: NO OPENAPI SERVICE ERROR (서비스 중단 또는 미등록)

### 8. 보안등
- **API**: 전국보안등정보표준데이터
- **URL**: `http://api.data.go.kr/openapi/tn_pubr_public_securitylamp_api`
- **형식**: XML
- **필드 매핑**: `instlPlcNm`→name, `latitude`→lat, `longitude`→lng, `rdnmadr`→address
- **상태**: NO OPENAPI SERVICE ERROR (서비스 중단 또는 미등록)

### 9. 어린이보호구역
- **API**: 전국어린이보호구역표준데이터
- **URL**: `http://api.data.go.kr/openapi/tn_pubr_public_child_safety_zone_api`
- **형식**: XML
- **필드 매핑**: `fcltyNm`→name, `latitude`→lat, `longitude`→lng, `rdnmadr`→address
- **상태**: NO OPENAPI SERVICE ERROR (서비스 중단 또는 미등록)

### 10. 도시공원
- **API**: data.go.kr 전국도시공원정보표준데이터
- **주소**: https://api.data.go.kr/openapi/tn_pubr_public_cty_park_info_api

### 11. 도서관
- **API**: data.go.kr 전국도서관표준데이터
- **주소**: https://api.data.go.kr/openapi/tn_pubr_public_lbrry_api

### 12. 유치원
- **API**: data.go.kr 전국유치원표준데이터
- **주소**: https://e-childschoolinfo.moe.go.kr/api/notice/building.do

## CSV 일괄등록

### 버스정류장
- **파일**: `apt_eda/data/시설자료/국토교통부_전국 버스정류장 위치정보_20251031.csv`
- **인코딩**: EUC-KR
- **필드 매핑**: `정류장번호`→facility_id, `정류장명`→name, `위도`→lat, `경도`→lng, `도시명`→address

### 학교 (초·중·고)
- **파일**: `apt_eda/data/시설자료/재단법인한국지방교육행정연구재단_초중등학교위치_20250922.csv`
- **인코딩**: UTF-8
- **필드 매핑**: `학교ID`→facility_id, `학교명`→name, `위도`→lat, `경도`→lng, `소재지도로명주소`→address

### 동물병원
- **파일**: `apt_eda/data/수집데이터/05_병원_약국_동물병원/animal_hospital_total.csv`
- **인코딩**: UTF-8
- **좌표**: TM(EPSG:2097) → WGS84(EPSG:4326) 변환 필요 (pyproj 사용)
- **필드 매핑**: `BPLC_NM`→name, `CRD_INFO_X/Y`→lng/lat(변환), `ROAD_NM_ADDR`→address
- **필터**: `SALS_STTS_NM='영업/정상'`만 등록

### 반려동물시설
- **API**: data.go.kr 전국 반려동물 동반 가능 문화시설 위치 데이터
- **주소**: https://www.bigdata-culture.kr/bigdata/user/data_market/detail.do?id=3c3d50c0-0337-11ee-a67e-69239d37dfae

### 유치원
- **API**: data.go.kr 전국유치원표준데이터
- **주소**: http://e-childschoolinfo.moe.go.kr/openApi/openApiIntro.do?pageName=openApiIntro4

### 전국도시철도역사정보
- **API**: data.go.kr 전국도시철도역사정보표준데이터
- **주소**: https://data.kric.go.kr/rips/M_01_01/detail.do?id=32

## 전국 확장 미완료 시설 (수도권만 존재)

| 시설 | 현재 건수 | 확장 방안 |
|------|----------|----------|
| 편의점 | 21,480 | API 승인 대기 (B553077) |
| 약국 | 9,943 | API 승인 대기 (B553077, 편의점과 동일) |
| 공원 | 7,213 | `tn_pubr_public_pvspark_api` 또는 CSV |
| 반려동물시설 | 6,195 | `tn_pubr_public_pet_relat_fclty_api` 또는 CSV |
| 유치원 | 2,617 | 학교 CSV에 미포함, NEIS API 또는 별도 CSV |
| 대형마트 | 1,326 | API 서비스 중단, CSV 대체 필요 |
| 도서관 | 1,231 | `tn_pubr_public_lbrry_api` 또는 CSV |
| 보안등 | 42,822 | API 서비스 중단, CSV 대체 필요 |
| 지하철역 | 756 | 전국 지하철역 CSV 또는 TAGO API |
| 경찰서 | 81 | 전국 경찰서 CSV |

## 배치 실행 방법

```bash
# 수도권만 (기존 동작)
python -m batch.run --type quarterly

# 특정 시도
python -m batch.run --type quarterly --region 광주

# 전국
python -m batch.run --type quarterly --region all

# 시설 요약 재계산
python -c "
from batch.db import get_connection
from batch.quarterly.recalc_summary import recalc_summary
from batch.logger import setup_logger
conn = get_connection()
recalc_summary(conn, setup_logger('recalc'))
conn.close()
"
```
