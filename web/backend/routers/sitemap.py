"""Sitemap / robots.txt 엔드포인트.

AAO(Assistive Agent Optimization) Phase 1의 일부로, 프론트와 같은 host에서
제공될 sitemap.xml의 원본과 백엔드 도메인용 robots.txt를 서빙한다.

- sitemap.xml: 프론트(Cloudflare Pages)가 `_redirects`로 프록시하여
  `https://apt-recom.kr/sitemap.xml` 주소에서 노출한다. URL은 모두
  `FRONTEND_BASE_URL`(프론트 host) 기준으로 생성된다.
- robots.txt: 백엔드 도메인 자체는 agent 크롤링 대상이 아님을 명시한다
  (권위 있는 robots는 프론트 host에서 제공).
"""

import logging
import os
import threading
import time

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

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


logger = logging.getLogger(__name__)

# 생성 비용이 큼(3만+ URL, trade_history 집계 포함 ~9초) — 매 요청 생성 시
# Railway 프록시 타임아웃(502)과 크롤러 지연의 원인이 되어 인메모리 캐시로 서빙.
# TTL 은 프론트 sitemap revalidate(3600)와 동기. 본문 ~3MB 는 메모리 예산 내.
_SITEMAP_TTL_SECONDS = 3600
_sitemap_cache: dict = {"body": None, "generated_at": 0.0}
_sitemap_refresh_lock = threading.Lock()


def _refresh_sitemap_cache() -> None:
    body = b"".join(_iter_sitemap_bytes())
    _sitemap_cache["body"] = body
    _sitemap_cache["generated_at"] = time.monotonic()


def _refresh_sitemap_in_background() -> None:
    # non-blocking acquire: 이미 다른 요청이 갱신 중이면 중복 생성하지 않는다.
    if not _sitemap_refresh_lock.acquire(blocking=False):
        return
    try:
        _refresh_sitemap_cache()
    except Exception:
        # 갱신 실패 시 이전(stale) 본문 유지 — 다음 요청이 재시도한다.
        logger.exception("sitemap 백그라운드 갱신 실패 — stale 본문 유지")
    finally:
        _sitemap_refresh_lock.release()


@router.get("/sitemap.xml")
def sitemap_xml():
    """전체 아파트 상세 URL을 포함한 sitemap (인메모리 캐시, TTL 1시간).

    - 콜드 스타트: 최초 요청 1회만 동기 생성 (lock 으로 동시 생성 방지)
    - TTL 초과: stale 본문을 즉시 응답하고 백그라운드 스레드로 갱신
      (stale-while-revalidate — 만료 순간에도 502/지연 없음)
    """
    body = _sitemap_cache["body"]
    if body is None:
        with _sitemap_refresh_lock:
            if _sitemap_cache["body"] is None:
                _refresh_sitemap_cache()
            body = _sitemap_cache["body"]
    elif time.monotonic() - _sitemap_cache["generated_at"] > _SITEMAP_TTL_SECONDS:
        threading.Thread(target=_refresh_sitemap_in_background, daemon=True).start()
    return Response(
        content=body,
        media_type="application/xml; charset=utf-8",
        # CDN/크롤러 캐시 힌트 — TTL 과 동기
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> str:
    """백엔드 API 도메인용 robots.txt.

    프론트(`apt-recom.kr`)의 robots.txt가 실제 agent 크롤링 정책의 권위 있는 소스다.
    다만 홈 Link 헤더(rel="service-desc")가 이 도메인의 /openapi.json 을 가리키고
    /mcp/ 도 공개 discovery 표면이므로, robots 준수 크롤러가 그 자원들까지
    차단당하지 않도록 discovery 경로만 명시 Allow 한다 (robots longest-match
    규칙으로 Allow 가 Disallow: / 를 이긴다). 그 외(백엔드 sitemap.xml 등)는
    프론트와의 중복 색인 방지를 위해 차단 유지.
    """
    return (
        "User-agent: *\n"
        "Allow: /openapi.json\n"
        "Allow: /docs\n"
        "Allow: /mcp/\n"
        "Allow: /api/health\n"
        "Disallow: /\n"
    )
