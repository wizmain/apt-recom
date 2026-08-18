"""배치 파이프라인 설정."""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# DB
DATABASE_URL = os.getenv("DATABASE_URL")

# API Keys
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
DATA_GO_KR_API_SECONDARY_KEY = os.getenv("DATA_GO_KR_API_SECONDARY_KEY", "")
DATA_GO_KR_API_THIRD_KEY = os.getenv("DATA_GO_KR_API_THIRD_KEY", "")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")
KOSIS_API_KEY = os.getenv("KOSIS_API_KEY", "")
NEIS_API_KEY = os.getenv("NEIS_API_KEY", "")

# Rate limits (seconds)
DATA_GO_KR_RATE = 0.15
KAKAO_RATE = 0.1

# 거래 수집 호출 예산 (2026-08-17)
# 실패 콜 하나의 비용이 전체 런타임을 지배한다. 정상 응답은 약 1초인데, 이전 설정
# (timeout 30 × retries 3 + 백오프)은 실패 콜 하나에 92초를 썼다. 254 시군구 × 2콜
# = 508콜 중 33콜(6%)만 재시도를 소진해도 60분 벽을 넘겼다(8/17 실측).
DATA_GO_KR_TIMEOUT = 15  # 정상 1초의 15배 여유
DATA_GO_KR_RETRIES = 2  # 최악 콜 = 15 + 백오프 1 + 15 = 31초
DATA_GO_KR_RETRY_BACKOFF = 1.0  # 지수 백오프 기준 (1, 2, 4…)

# 수집 단계의 시간 상한. 초과하면 남은 시군구를 남기고 정상 반환한다 —
# 그래야 적재·점수 재계산 등 후속 단계가 실행되고 부분 수집분이 보존된다.
# 워크플로 timeout-minutes(60) = 수집 35 + 후속 약 7 + 여유.
COLLECT_BUDGET_MINUTES = 35

# 실패율이 이 값을 넘으면 수집 요약에 경고를 남긴다 (예산 초과의 선행 지표).
COLLECT_FAILURE_WARN_RATIO = 0.05
KOSIS_RATE = 2.0
NEIS_RATE = 0.1

# 거래 데이터 API
TRADE_URL = (
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
)
RENT_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

# 수도권 시도 코드 (서울 11, 경기 41, 인천 28)
METRO_SIDO_PREFIXES = ("11", "41", "28")

# KOSIS 시도 코드 (전국 17개 시도) — 인구 통계 수집용
KOSIS_SIDO_CODES = {
    "11": "서울특별시",
    "26": "부산광역시",
    "27": "대구광역시",
    "28": "인천광역시",
    "29": "광주광역시",
    "30": "대전광역시",
    "31": "울산광역시",
    "36": "세종특별자치시",
    "41": "경기도",
    "51": "강원특별자치도",  # KOSIS: 42 → 51 (특별자치도 전환)
    "43": "충청북도",
    "44": "충청남도",
    "52": "전북특별자치도",  # KOSIS: 45 → 52 (특별자치도 전환)
    "46": "전라남도",
    "47": "경상북도",
    "48": "경상남도",
    "50": "제주특별자치도",
}

# 병렬 처리
ENRICH_WORKERS = int(os.getenv("ENRICH_WORKERS", "5"))
