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
from routers.apartments import APARTMENT_VISIBLE_CONDITIONS

router = APIRouter()

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://apt-recom.kr").rstrip("/")


# 지역 허브(/region/{code}) 노출 조건 — /region 인덱스·dashboard_regions.apt_count 와
# 동일 기준(APARTMENT_VISIBLE_CONDITIONS)을 공유해야 한다. 이 조건으로 걸러지는
# (=/region 인덱스에 노출되지 않는) 코드를 sitemap 에 넣으면 "인덱스에는 없는데
# sitemap 에는 있는" 모순이 생긴다.
_REGION_VISIBLE_WHERE = " AND ".join(APARTMENT_VISIBLE_CONDITIONS)

# common_code(sigungu) 와 apartments 의 교집합만 사용 — apartments.sigungu_code 가
# common_code 에 없는 값(데이터 이상)을 가리키면 /region/{code} 가 프론트에서 404가
# 되므로, sitemap 단계에서 실존 코드만 걸러낸다.
_SITEMAP_REGION_SQL = f"""
    SELECT DISTINCT c.code
    FROM common_code c
    JOIN apartments a ON a.sigungu_code = c.code
    LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
    WHERE c.group_id = %s
      AND {_REGION_VISIBLE_WHERE}
    ORDER BY c.code
"""

# 좌표가 있고 PNU 스펙(19자리 숫자)에 맞는 아파트만 sitemap에 노출.
# TRADE_ 접두 PNU는 거래 데이터 파생의 비정상 값이므로 제외.
# lastmod = 최근 실거래일 (상세 페이지의 실질 변경 시점 — 크롤러 재수집 효율).
# 거래 이력이 없는 단지는 lastmod 생략 (sitemap 규격상 선택 필드).
# make_date 가드: 월 1~12 / 일 1~28 클램프 — 원천 데이터의 0/결측 방어.
_SITEMAP_APT_SQL = """
    SELECT a.pnu, d.last_deal
    FROM apartments a
    LEFT JOIN (
        SELECT m.pnu,
               MAX(make_date(
                   t.deal_year,
                   LEAST(GREATEST(COALESCE(t.deal_month, 1), 1), 12),
                   LEAST(GREATEST(COALESCE(t.deal_day, 1), 1), 28)
               )) AS last_deal
        FROM trade_apt_mapping m
        JOIN trade_history t ON t.apt_seq = m.apt_seq
        GROUP BY m.pnu
    ) d ON d.pnu = a.pnu
    WHERE a.lat IS NOT NULL
      AND a.lng IS NOT NULL
      AND a.pnu NOT LIKE 'TRADE_%%'
      AND a.pnu ~ '^[0-9]{19}$'
    ORDER BY a.pnu
"""


def _iter_sitemap_bytes():
    """sitemap.xml 본문을 청크 단위로 yield. StreamingResponse용."""
    yield b'<?xml version="1.0" encoding="UTF-8"?>\n'
    yield b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # 홈 URL
    yield f"  <url><loc>{FRONTEND_BASE_URL}/</loc></url>\n".encode("utf-8")

    # 지역 허브 URL (/region/{code}) — 아파트 상세 URL보다 먼저 노출.
    # lastmod 생략: summary/trend 가 매일 갱신되어 의미 있는 고정 시점이 없음.
    conn = DictConnection()
    try:
        region_rows = conn.execute(_SITEMAP_REGION_SQL, ["sigungu"]).fetchall()
        for row in region_rows:
            loc = f"{FRONTEND_BASE_URL}/region/{row['code']}"
            yield f"  <url><loc>{loc}</loc></url>\n".encode("utf-8")
    finally:
        conn.close()

    # 아파트 상세 URL (PNU는 19자리 숫자이므로 XML 이스케이프 불필요)
    conn = DictConnection()
    try:
        rows = conn.execute(_SITEMAP_APT_SQL).fetchall()
        for row in rows:
            loc = f"{FRONTEND_BASE_URL}/apartment/{row['pnu']}"
            lastmod = (
                f"<lastmod>{row['last_deal'].isoformat()}</lastmod>"
                if row["last_deal"]
                else ""
            )
            yield f"  <url><loc>{loc}</loc>{lastmod}</url>\n".encode("utf-8")
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
