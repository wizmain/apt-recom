"""프론트엔드(웹) 오리진 — sitemap·content 등이 절대 URL 생성에 공유한다.

값의 단일 출처. 신규 소비 모듈은 로컬 재정의 대신 여기서 import 한다.
"""

import os

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://apt-recom.kr").rstrip("/")
