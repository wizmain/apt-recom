"""Sitemap / robots.txt 엔드포인트.

AAO(Assistive Agent Optimization) Phase 1의 일부로, 프론트와 같은 host에서
제공될 sitemap.xml의 원본과 백엔드 도메인용 robots.txt를 서빙한다.

- sitemap.xml: 프론트(Cloudflare Pages)가 `_redirects`로 프록시하여
  `https://apt-recom.kr/sitemap.xml` 주소에서 노출한다. URL은 모두
  `FRONTEND_BASE_URL`(프론트 host) 기준으로 생성된다.
- robots.txt: 백엔드 도메인 자체는 agent 크롤링 대상이 아님을 명시한다
  (권위 있는 robots는 프론트 host에서 제공).
"""

import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, StreamingResponse

from database import DictConnection

router = APIRouter()

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://apt-recom.kr").rstrip("/")


# 좌표가 있고 PNU 스펙(19자리 숫자)에 맞는 아파트만 sitemap에 노출.
# TRADE_ 접두 PNU는 거래 데이터 파생의 비정상 값이므로 제외.
_SITEMAP_APT_SQL = """
    SELECT pnu
    FROM apartments
    WHERE lat IS NOT NULL
      AND lng IS NOT NULL
      AND pnu NOT LIKE 'TRADE_%%'
      AND pnu ~ '^[0-9]{19}$'
    ORDER BY pnu
"""


def _iter_sitemap_bytes():
    """sitemap.xml 본문을 청크 단위로 yield. StreamingResponse용."""
    yield b'<?xml version="1.0" encoding="UTF-8"?>\n'
    yield b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # 홈 URL
    yield f"  <url><loc>{FRONTEND_BASE_URL}/</loc></url>\n".encode("utf-8")

    # 아파트 상세 URL (PNU는 19자리 숫자이므로 XML 이스케이프 불필요)
    conn = DictConnection()
    try:
        rows = conn.execute(_SITEMAP_APT_SQL).fetchall()
        for row in rows:
            loc = f"{FRONTEND_BASE_URL}/apartment/{row['pnu']}"
            yield f"  <url><loc>{loc}</loc></url>\n".encode("utf-8")
    finally:
        conn.close()

    yield b"</urlset>\n"


@router.get("/sitemap.xml")
def sitemap_xml():
    """전체 아파트 상세 URL을 포함한 sitemap."""
    return StreamingResponse(
        _iter_sitemap_bytes(),
        media_type="application/xml; charset=utf-8",
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> str:
    """백엔드 API 도메인용 robots.txt.

    프론트(`apt-recom.kr`)의 robots.txt가 실제 agent 크롤링 정책의 권위 있는 소스다.
    백엔드 도메인은 JSON API 전용이므로 agent가 크롤링할 HTML이 없다.
    agent 혼란을 방지하기 위해 백엔드 도메인에서는 Disallow-all 을 반환한다.
    """
    return "User-agent: *\nDisallow: /\n"
