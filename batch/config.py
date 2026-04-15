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

# Rate limits (seconds)
DATA_GO_KR_RATE = 0.15
KAKAO_RATE = 0.1
KOSIS_RATE = 2.0

# 거래 데이터 API
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

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
    "51": "강원특별자치도",   # KOSIS: 42 → 51 (특별자치도 전환)
    "43": "충청북도",
    "44": "충청남도",
    "52": "전북특별자치도",   # KOSIS: 45 → 52 (특별자치도 전환)
    "46": "전라남도",
    "47": "경상북도",
    "48": "경상남도",
    "50": "제주특별자치도",
}

# 병렬 처리
ENRICH_WORKERS = int(os.getenv("ENRICH_WORKERS", "5"))
