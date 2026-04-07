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

# 병렬 처리
ENRICH_WORKERS = int(os.getenv("ENRICH_WORKERS", "5"))
