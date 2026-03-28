---
name: korean-public-data
description: 한국 공공데이터 수집 스킬. data.go.kr, KOSIS(kosis.kr), 서울열린데이터(data.seoul.go.kr), 경기데이터드림(data.gg.go.kr) 등 한국 공공데이터 포털에서 데이터를 수집할 때 사용. 사용자가 "공공데이터 수집", "data.go.kr", "KOSIS", "통계 데이터", "서울시 데이터", "경기도 데이터", "공공 API", "열린데이터", "인구 데이터", "범죄 통계", "부동산 통계", "시설 데이터" 등을 언급하면 반드시 이 스킬을 사용할 것.
---

# 한국 공공데이터 수집 가이드

이 스킬은 한국 공공데이터 포털에서 데이터를 수집하는 방법을 안내합니다.

**핵심 원칙**: 공공데이터 API는 주소, 파라미터, 응답 형식이 자주 변경됩니다. **항상 최신 API 문서를 먼저 확인**한 후 수집을 진행하세요.

---

## 사전 확인 절차 (모든 수집 전 필수)

어떤 사이트에서 수집하든 아래 절차를 먼저 수행합니다:

### 1. API 키 확인 (필수)

데이터 수집 전 **.env 파일에 필요한 API 키가 존재하는지 반드시 확인**합니다. 키가 없으면 수집을 진행하지 말고, 발급 안내를 먼저 제공합니다.

```python
import os
from dotenv import load_dotenv
load_dotenv()

# 사이트별 키 확인
keys = {
    "data.go.kr": os.getenv("DATA_GO_KR_API_KEY"),
    "KOSIS": os.getenv("KOSIS_API_KEY"),
    "서울열린데이터": os.getenv("SEOUL_API_KEY"),  # 없으면 "sample" 키 사용 가능 (5건 제한)
}

for site, key in keys.items():
    if key:
        print(f"✅ {site}: 키 존재 ({key[:10]}...)")
    else:
        print(f"❌ {site}: 키 없음 — 발급 필요")
```

**키가 없는 경우** 아래 안내를 사용자에게 제공합니다:

#### data.go.kr (공공데이터포털)
- **발급 페이지**: https://www.data.go.kr/ugs/selectPublicDataUseGuide.do
- **발급 방법**:
  1. https://www.data.go.kr 회원가입 (본인인증 필요)
  2. 원하는 데이터셋 페이지 → "활용신청" 클릭
  3. 목적 입력 후 신청 → 즉시 또는 1~2일 내 승인
  4. 마이페이지 → 오픈API → 인증키 확인
- **환경변수**: `.env`에 `DATA_GO_KR_API_KEY=발급받은키` 추가

> **키는 있지만 특정 API를 활용신청하지 않은 경우**:
> data.go.kr의 오픈API는 키 발급과 별도로 **각 데이터셋마다 활용신청**이 필요합니다.
> 키가 있어도 활용신청 없이 호출하면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 에러가 발생합니다.
>
> **활용신청 방법**:
> 1. 사용할 데이터셋 페이지로 이동 (예: `https://www.data.go.kr/data/{데이터셋ID}/openapi.do`)
> 2. "활용신청" 버튼 클릭
> 3. 활용 목적 입력 (예: "아파트 분석 프로젝트 데이터 수집")
> 4. 신청 후 즉시 승인 또는 1~2일 대기
> 5. 승인 후 기존 인증키로 해당 API 호출 가능
>
> **활용신청 현황 확인**: https://www.data.go.kr/iim/api/selectAPIAc498View.do
>
> **데이터셋 검색**: https://www.data.go.kr/tcs/dss/selectDataSetList.do
>
> 수집 중 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 에러가 발생하면:
> - 해당 데이터셋의 활용신청 여부를 확인하도록 사용자에게 안내
> - 데이터셋 ID와 함께 활용신청 URL을 제공: `https://www.data.go.kr/data/{ID}/openapi.do`

#### KOSIS (국가통계포털)
- **발급 페이지**: https://kosis.kr/openapi/index.do
- **발급 방법**:
  1. https://kosis.kr 회원가입
  2. 오픈API → API 인증키 신청
  3. 용도 입력 후 신청 → 즉시 발급
  4. 마이페이지 → 오픈API 인증키 확인
- **환경변수**: `.env`에 `KOSIS_API_KEY=발급받은키` 추가

#### 서울열린데이터 (data.seoul.go.kr)
- **발급 페이지**: https://data.seoul.go.kr/together/guide/useGuide.do
- **발급 방법**:
  1. https://data.seoul.go.kr 회원가입
  2. 데이터셋 → "오픈API" 탭 → 인증키 발급
  3. `sample` 키로 5건까지 테스트 가능 (대량 수집 시 발급 필요)
- **환경변수**: `.env`에 `SEOUL_API_KEY=발급받은키` 추가
- **참고**: `sample` 키는 모든 API에서 5건까지 무료로 사용 가능

#### 경기데이터드림 (data.gg.go.kr)
- **발급 페이지**: https://data.gg.go.kr/portal/mainPage.do
- **발급 방법**:
  1. https://data.gg.go.kr 회원가입
  2. 오픈API → 활용신청 → 인증키 발급
  3. data.go.kr 키와 공유 가능한 API도 있음
- **환경변수**: `.env`에 `GG_API_KEY=발급받은키` 추가 (또는 DATA_GO_KR_API_KEY 공유)

### 2. 최신 API 엔드포인트 확인
각 사이트의 API 문서 페이지를 **WebFetch로 직접 확인**하여 현재 유효한 URL과 파라미터를 검증합니다. API 문서 URL이 변경되었을 수 있으므로 WebSearch로 먼저 검색합니다.

### 3. 테스트 호출
소량(1~5건)을 먼저 호출하여 응답 구조를 확인한 후 대량 수집합니다.

---

## 사이트별 수집 가이드

### 1. data.go.kr (공공데이터포털)

**역할**: 중앙정부+지자체 데이터 통합 포털. API(오픈API)와 파일(CSV/Excel) 두 가지 방식 제공.

**최신 정보 확인 방법**:
```
WebSearch: "data.go.kr [데이터셋명] API 활용가이드"
WebFetch: https://www.data.go.kr/data/[데이터셋ID]/openapi.do
```

**수집 패턴 (REST API)**:
```python
import requests

API_KEY = os.getenv("DATA_GO_KR_API_KEY")

# 1. 엔드포인트와 파라미터는 data.go.kr 활용가이드에서 확인
url = "확인된_API_엔드포인트"
params = {
    "serviceKey": API_KEY,    # 인증키 (URL 디코딩 상태로 전달)
    "pageNo": 1,
    "numOfRows": 100,
    "type": "json",           # xml 또는 json (API마다 다름)
    # 추가 파라미터는 API 문서 참조
}

resp = requests.get(url, params=params, timeout=30)
```

**주의사항**:
- `serviceKey`는 URL 인코딩/디코딩 이슈가 잦음. 안 되면 `requests.get(url, params=params)` 대신 URL에 직접 삽입 시도
- XML 응답인 경우 `xml.etree.ElementTree`로 파싱
- 일부 API는 일일 호출량 제한(1,000~10,000회)이 있음
- 파일데이터(CSV)는 API가 아닌 직접 다운로드. data.go.kr 페이지에서 다운로드 링크 확인

**파일 데이터 수집 패턴**:
```python
# data.go.kr 파일데이터는 직접 다운로드 URL이 변경될 수 있음
# WebSearch로 최신 다운로드 링크 확인 후 진행
resp = requests.get(download_url, timeout=60)
with open("output.csv", "wb") as f:
    f.write(resp.content)
```

**인코딩**: data.go.kr CSV는 대부분 `cp949` 또는 `utf-8-sig`. 둘 다 시도:
```python
try:
    df = pd.read_csv(path, encoding="utf-8-sig")
except:
    df = pd.read_csv(path, encoding="cp949")
```

---

### 2. KOSIS (국가통계포털)

**역할**: 통계청 중심 국가 공식 통계. 인구, 경제, 사회, 범죄 등 모든 분야 통계.

**최신 정보 확인 방법**:
```
WebSearch: "KOSIS 오픈API [통계표명]"
WebFetch: https://kosis.kr/openapi/index.do  (API 안내 페이지)
```

**수집 패턴 (통계자료 API)**:
```python
api_key = os.getenv("KOSIS_API_KEY")

# KOSIS API는 URL에 키를 직접 삽입해야 하는 경우가 많음 (requests params 안 먹힐 수 있음)
url = f"https://kosis.kr/openapi/Param/statisticsParameterData.do"
params = {
    "method": "getList",
    "apiKey": api_key,
    "format": "json",
    "jsonVD": "Y",
    "orgId": "기관코드",     # 예: 101(통계청), 132(경찰청), 135(대검찰청)
    "tblId": "통계표ID",     # 예: DT_1B04005N
    "objL1": "ALL",          # 분류1 (ALL = 전체)
    "objL2": "ALL",          # 분류2
    "itmId": "ALL",          # 항목
    "startPrdDe": "2024",    # 시작 기간
    "endPrdDe": "2024",      # 종료 기간
    "prdSe": "Y",            # 주기: Y(연), M(월), Q(분기)
}

resp = requests.get(url, params=params, timeout=30)
data = resp.json()

# 정상 응답: list 형태
if isinstance(data, list):
    df = pd.DataFrame(data)
# 에러 응답: dict with 'err' key
elif isinstance(data, dict) and "err" in data:
    print(f"에러: {data['errMsg']}")
```

**KOSIS 주요 에러 코드**:
- `20`: 필수 파라미터 누락
- `21`: 잘못된 요청 변수
- `30`: 데이터 없음
- `31`: 40,000셀 초과 → objL1/objL2를 분할해서 요청

**통계표 찾기**:
```python
# 기관별 통계표 목록 조회
url = "https://kosis.kr/openapi/statisticsList.do"
params = {
    "method": "getList",
    "apiKey": api_key,
    "vwCd": "MT_OTITLE",     # 기관별 목록
    "parentListId": "기관코드",
    "format": "json",
    "jsonVD": "Y",
}
```

**주의사항**:
- `apiKey`에 `/`, `+` 등 특수문자가 포함될 수 있음. `requests.get(url, params=params)`로 전달하면 이중 인코딩될 수 있으므로, URL에 직접 삽입하는 것도 시도
- 40,000셀 제한: 지역×항목×기간 조합이 크면 분할 요청 필요
- `objL1=ALL`로 전체 조회 시 시도/시군구/읍면동이 모두 포함될 수 있음 → 코드 길이로 레벨 구분 (2자리=시도, 5자리=시군구, 10자리=읍면동)

---

### 3. 서울열린데이터 (data.seoul.go.kr)

**역할**: 서울시 자치구별 데이터. 인구, 범죄, 교통, 환경 등.

**최신 정보 확인 방법**:
```
WebSearch: "서울열린데이터 [데이터셋명] API"
WebFetch: https://data.seoul.go.kr/dataList/datasetList.do
```

**수집 패턴**:
```python
# 서울 열린데이터 API 형식 (sample 키 사용 가능)
api_key = os.getenv("SEOUL_API_KEY", "sample")

# URL 패턴: http://openapi.seoul.go.kr:8088/{키}/{형식}/{서비스명}/{시작}/{끝}/
url = f"http://openapi.seoul.go.kr:8088/{api_key}/json/서비스명/1/1000/"
resp = requests.get(url, timeout=10)
data = resp.json()

# 응답 구조: {"서비스명": {"list_total_count": N, "RESULT": {...}, "row": [...]}}
service_key = list(data.keys())[0]
rows = data[service_key].get("row", [])
result = data[service_key].get("RESULT", {})
if result.get("CODE") != "INFO-000":
    print(f"에러: {result.get('MESSAGE')}")
```

**주의사항**:
- `sample` 키는 5건만 반환. 대량 수집은 API 키 발급 필요
- 한번에 최대 1,000건. 페이징: `/1/1000/`, `/1001/2000/` ...
- 일부 서비스는 날짜 파라미터 필요: `/1/1000/20240101`

---

### 4. 경기데이터드림 (data.gg.go.kr)

**역할**: 경기도 시군구별 데이터.

**최신 정보 확인 방법**:
```
WebSearch: "경기데이터드림 [데이터셋명] API"
WebFetch: https://data.gg.go.kr/portal/data/dataset/searchDataset.do
```

**수집 패턴**:
```python
# 경기데이터드림 API (data.go.kr 키 공유 가능)
url = "확인된_API_엔드포인트"
params = {
    "key": os.getenv("DATA_GO_KR_API_KEY"),  # 또는 별도 키
    "type": "json",
    "pIndex": 1,
    "pSize": 100,
}
resp = requests.get(url, params=params, timeout=30)
```

**주의사항**:
- 일부 데이터는 data.go.kr과 중복 제공
- 파일 다운로드 방식이 주류 (API 없는 데이터도 많음)

---

## 공통 수집 패턴

### 대량 수집 (페이징)
```python
all_rows = []
page = 1
while True:
    params["pageNo"] = page
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()

    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    if not items:
        break

    all_rows.extend(items if isinstance(items, list) else [items])

    total = int(data["response"]["body"]["totalCount"])
    if page * params["numOfRows"] >= total:
        break

    page += 1
    time.sleep(0.1)  # API 부하 방지
```

### XML 응답 파싱
```python
import xml.etree.ElementTree as ET

resp = requests.get(url, params=params, timeout=30)
root = ET.fromstring(resp.text)

result_code = root.findtext(".//resultCode")
if result_code not in ("00", "000"):
    print(f"에러: {root.findtext('.//resultMsg')}")

items = root.findall(".//item")
for item in items:
    row = {tag.tag: tag.text for tag in item}
```

### 체크포인트 저장 (대량 수집 시)
```python
import json

CHECKPOINT_PATH = "checkpoint.json"

# 복원
if os.path.exists(CHECKPOINT_PATH):
    checkpoint = json.loads(open(CHECKPOINT_PATH).read())
else:
    checkpoint = {"last_page": 0, "rows": []}

# 저장 (매 100건)
if len(all_rows) % 100 == 0:
    checkpoint["last_page"] = page
    checkpoint["rows"] = all_rows
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(checkpoint, f, ensure_ascii=False)
```

### 결과 저장 (사용자에게 형식 확인 필수)

데이터를 저장하기 전에 **사용자에게 저장 형식을 확인**합니다:

> "수집된 데이터를 어떤 형식으로 저장할까요?
> 1. **CSV** — Excel에서 열기 편함, 가장 일반적
> 2. **JSON** — 중첩 구조 보존, API 재사용에 적합
> 3. **Excel (.xlsx)** — 시트 분리, 서식 포함 가능
> 4. **DB 직접 저장** — PostgreSQL/SQLite에 바로 INSERT
>
> 저장 경로도 지정해주세요. (기본: 현재 디렉토리)"

사용자가 별도 요청 없이 진행하라고 하면 **CSV를 기본값**으로 사용합니다.

```python
import pandas as pd

df = pd.DataFrame(all_rows)

# CSV (기본)
df.to_csv("output.csv", index=False, encoding="utf-8-sig")

# JSON
df.to_json("output.json", orient="records", force_ascii=False, indent=2)

# Excel
df.to_excel("output.xlsx", index=False, engine="openpyxl")

# DB 직접 저장 (psycopg2 예시)
# from sqlalchemy import create_engine
# engine = create_engine(os.getenv("DATABASE_URL"))
# df.to_sql("table_name", engine, if_exists="replace", index=False)
```

**파일명 규칙 권장**: `{데이터명}_{지역}_{연도}.{확장자}`
- 예: `hospital_gangnam_2024.csv`, `crime_seoul_2024.json`

---

## API 변경 대응 체크리스트

수집이 실패하면 다음 순서로 확인합니다:

1. **API 키 유효성**: 만료/비활성화 여부
2. **엔드포인트 URL**: WebSearch로 현재 URL 확인
3. **파라미터 이름/형식**: API 문서 재확인 (필드명 변경, 필수값 추가 등)
4. **인코딩**: serviceKey 인코딩 방식 변경 (URL 직접 삽입 시도)
5. **응답 형식**: JSON/XML 구조 변경 여부
6. **호출 제한**: 일일 한도 초과 여부
7. **도메인 변경**: 사이트 개편으로 도메인 변경 (WebSearch로 확인)

---

## 주요 기관코드 (KOSIS)

| 기관코드 | 기관명 | 주요 통계 |
|---------|--------|----------|
| 101 | 통계청 | 인구, 주거, 경제 |
| 116 | 행정안전부 | 주민등록인구 |
| 132 | 경찰청 | 범죄통계 |
| 135 | 대검찰청 | 범죄분석 |
| 110 | 국토교통부 | 부동산, 건축 |
| 154 | 교육부 | 학교, 교육통계 |
