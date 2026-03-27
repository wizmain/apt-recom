# 인천 데이터 통합 계획

> 인천광역시 아파트 데이터를 기존 서비스에 통합하는 단계별 실행 계획

**Goal:** 인천 아파트를 기존 서울+경기 서비스에 통합하여 지도/넛지/상세 모달에서 인천 아파트도 표시

**현재 상태:** 인천 실거래가(매매 34만건 + 전월세 58만건) 수집 완료. 나머지 모두 미구축.

---

## 필요 작업 목록

### Task 1: 인천 아파트 마스터 구축
- 인천에는 건축물대장 기반 마스터가 없으므로 **거래 데이터에서 아파트 마스터를 추출**
- 거래 데이터의 aptNm + sggCd + umdNm + jibun으로 고유 단지 목록 생성
- Vworld/Kakao 지오코딩으로 좌표 확보
- 출력: 인천 아파트 마스터 CSV (단지명, 시군구, 좌표 등)

### Task 2: 인천 시설 데이터 수집
- 기존 수집 스크립트를 인천으로 확장하여 시설 수집:
  - 병원, 학교, 공원, 지하철역, 버스정류장, 도서관, CCTV 등
  - 기존 전국 데이터 API에서 인천만 필터링
- 편의점/약국: 기존 소상공인 데이터에서 인천 필터
- 출력: `apt_eda/data/raw/*_incheon.csv`

### Task 3: 인천 시설 정규화 + 거리 계산
- 인천 시설을 정규화 스키마로 변환
- BallTree로 아파트-시설 거리 계산 (5km 반경)
- apt_facility_summary 생성
- 기존 서울+경기 데이터에 APPEND

### Task 4: 인천 학군 매핑
- hakguzi 폴더의 Shapefile에 인천 데이터가 포함되어 있는지 확인
- 포함되어 있으면 Spatial Join으로 매핑
- 없으면 학교 위치 데이터로 대체

### Task 5: SQLite DB 갱신
- apartments 테이블에 인천 아파트 추가
- facilities 테이블에 인천 시설 추가
- apt_facility_mapping, apt_facility_summary에 인천 데이터 추가
- trade_history, rent_history에 인천 거래 데이터 추가
- trade_apt_mapping에 인천 매핑 추가
- school_zones에 인천 학군 추가
- apt_price_score에 인천 가격 점수 추가
- apt_safety_score에 인천 안전 점수 추가

### Task 6: 프론트엔드 지도 범위 조정
- 지도 초기 중심/줌 레벨 조정 (서울+경기+인천 커버)
- 검색에서 인천 지역명 지원 확인

---

## 실행 순서

```
Task 1: 아파트 마스터 구축 (거래→단지 추출 + 지오코딩)
  ↓
Task 2: 시설 데이터 수집 (API 수집 + 필터링)
  ↓
Task 3: 시설 정규화 + 거리 계산 (BallTree)
  ↓
Task 4: 학군 매핑 (Spatial Join)
  ↓
Task 5: DB 갱신 (모든 테이블에 인천 APPEND)
  ↓
Task 6: 프론트엔드 조정
```

Task 1~2는 병렬 실행 가능.
