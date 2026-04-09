"""Admin authentication middleware.

ADMIN_TOKEN 환경변수 기반 Bearer 토큰 인증.
- 미설정 시: 503 Service Unavailable (우회 불가)
- 불일치 시: 401 Unauthorized
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# .env 로드 (database.py와 동일한 경로)
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path)

_bearer_scheme = HTTPBearer(auto_error=False)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


def verify_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """관리자 API 인증 의존성.

    Returns:
        인증된 토큰 문자열
    Raises:
        HTTPException 503: ADMIN_TOKEN 환경변수 미설정
        HTTPException 401: 토큰 누락 또는 불일치
    """
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="관리자 기능이 비활성화되어 있습니다. ADMIN_TOKEN 환경변수를 설정하세요.",
        )
    if credentials is None or credentials.credentials != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="유효하지 않은 관리자 토큰입니다.",
        )
    return credentials.credentials


IS_RAILWAY = os.getenv("DEPLOYMENT_ENV") == "railway"


def require_local_env() -> None:
    """배치 관련 엔드포인트 진입 시 호출. Railway에서는 503."""
    if IS_RAILWAY:
        raise HTTPException(
            status_code=503,
            detail="배치 기능은 로컬 환경에서만 사용 가능합니다.",
        )
