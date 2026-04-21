"""MCP (Model Context Protocol) 서버.

Claude Desktop / Cursor 등 MCP 클라이언트가 집토리 데이터를 직접 조회할 수 있게 해주는
Streamable HTTP 엔드포인트. 기존 `services.tools` 의 executor 함수를 얇게 감싸고,
MCP 표준 규약에 맞는 메타데이터·타입 시그니처를 제공한다.

Transport
    - Streamable HTTP (MCP 2025 spec). SSE 는 제공하지 않는다 (구 규약).
    - `stateless_http=True` 로 요청-응답 단위 처리 → 세션 저장소 불필요.

Mount
    `main.py` 에서 `app.mount("/mcp", mcp_asgi_app)` 로 FastAPI 에 붙인다.
    클라이언트 접속 URL: `https://api.apt-recom.kr/mcp/`.

Tool 선정 기준
    - agent 가 질의하는 전형적 시나리오(검색/상세/비교/유사/시장동향)를 덮는 5종만 노출.
    - 관리·디버깅용 tool(dashboard/log/feedback)은 제외.
    - 각 tool docstring 은 agent 가 언제 호출할지 판단할 수 있도록 "무엇을/언제/예시" 3가지를 포함.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from services import tools as tool_executors


def _build_transport_security() -> TransportSecuritySettings:
    """DNS rebinding 방어를 위한 Host/Origin 허용 목록 구성.

    MCP SDK 기본값은 `enable_dns_rebinding_protection=True` + 빈 allowed_hosts 라서
    production host 를 전부 거부해 421 Invalid Host header 가 반환된다.
    운영 환경에서는 Cloudflare TLS 종단 뒤에 있으므로 해당 방어는 사실상 CF 가 담당하지만,
    SDK 정책을 존중하는 차원에서 허용 목록을 명시한다.

    허용 host: 개발(localhost:8000, 127.0.0.1:8000) + 운영(api.apt-recom.kr).
    추가 host 는 `MCP_ALLOWED_HOSTS` 환경변수 (콤마 구분) 로 확장.
    """
    defaults = [
        "localhost:8000", "127.0.0.1:8000",
        "localhost:8765", "127.0.0.1:8765",  # 로컬 테스트용 포트
        "api.apt-recom.kr",
    ]
    extra_hosts = os.getenv("MCP_ALLOWED_HOSTS", "").strip()
    if extra_hosts:
        defaults.extend(h.strip() for h in extra_hosts.split(",") if h.strip())
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=defaults,
        # Origin 검사는 MCP 클라이언트가 기본적으로 Origin 을 보내지 않으므로 빈 값 유지.
        allowed_origins=[],
    )


mcp = FastMCP(
    name="apt-recom",
    instructions=(
        "대한민국 아파트 데이터(국토부 실거래가, K-APT 관리비/시설, CCTV 안전지수, "
        "학군 배정)를 라이프스타일 키워드 기반으로 검색·상세조회·비교·추천한다. "
        "모든 응답은 한국어 JSON 문자열. 금액은 만원 단위, 면적은 ㎡."
    ),
    stateless_http=True,
    streamable_http_path="/",
    transport_security=_build_transport_security(),
)


@mcp.tool()
async def search_apartments(
    keyword: str,
    nudges: list[str] | None = None,
    top_n: int = 10,
    min_area: float | None = None,
    max_area: float | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_floor: int | None = None,
    built_after: int | None = None,
) -> str:
    """라이프스타일 키워드 기반 아파트 검색·스코어링.

    무엇:
        - 지역·단지명 키워드와 라이프스타일 항목을 조합해 집토리 NUDGE 스코어 순으로 반환.
        - 좌표·세대수·점수·지역 후보 등을 포함한 JSON.

    언제:
        - 사용자가 "강남구에서 출퇴근 좋은 아파트" 같은 조건부 추천을 요청할 때.
        - 특정 지역의 상위권 단지를 추리고 싶을 때.

    인자:
        keyword: 지역명 또는 단지명 (예: '자양동', '강남구', '래미안').
        nudges: 적용할 라이프 항목 ID 목록. 가능한 값:
            cost(가성비) / pet(반려동물) / commute(출퇴근) /
            newlywed(신혼부부) / education(교육) / senior(시니어) /
            investment(투자) / nature(자연친화) / safety(안전).
            생략 시 키워드에서 자동 추론, 추론 실패 시 ['commute'].
        top_n: 반환 최대 단지 수 (기본 10).
        min_area, max_area: 전용면적 범위(㎡).
        min_price, max_price: 매매가 범위(만원).
        min_floor: 최소 최고층수.
        built_after: 준공연도 이후 (예: 2015).

    예시:
        search_apartments(keyword='자양동', nudges=['commute', 'cost'], top_n=5)
    """
    return await tool_executors.search_apartments(
        keyword=keyword,
        nudges=nudges,
        top_n=top_n,
        min_area=min_area,
        max_area=max_area,
        min_price=min_price,
        max_price=max_price,
        min_floor=min_floor,
        built_after=built_after,
    )


@mcp.tool()
async def get_apartment_detail(query: str) -> str:
    """특정 아파트의 상세 정보(기본·점수·시설·학군·거래이력 요약).

    무엇:
        - 아파트 이름 또는 PNU 코드로 단일 단지의 전체 프로필을 반환.
        - NUDGE 점수, 시설 거리, 학군 배정, 최근 거래 요약 포함.

    언제:
        - 사용자가 "○○ 아파트 알려줘" / "이 단지 상세 보여줘" 라고 할 때.
        - search_apartments 결과 중 특정 단지를 깊게 분석해야 할 때.

    인자:
        query: 단지명(부분 일치 가능) 또는 19자리 PNU 코드.
            예: '래미안대치팰리스', '1168010100100010000'.
    """
    return await tool_executors.get_apartment_detail(query)


@mcp.tool()
async def compare_apartments(queries: list[str]) -> str:
    """2~5개 아파트를 나란히 비교.

    무엇:
        - 여러 단지의 기본정보·점수·시설을 매트릭스로 비교한 JSON.

    언제:
        - 사용자가 "A 아파트랑 B 아파트 비교해줘" 라고 할 때.
        - 검색 결과 중 후보를 좁히고 싶을 때.

    인자:
        queries: 단지명 또는 PNU 목록 (2~5개).
            예: ['래미안대치팰리스', '은마아파트'].
    """
    return await tool_executors.compare_apartments(queries)


@mcp.tool()
async def get_similar_apartments(
    query: str,
    mode: str = "combined",
    top_n: int = 5,
    exclude_same_area: bool = False,
) -> str:
    """특정 아파트와 유사한 단지 추천.

    무엇:
        - 대상 아파트와 유사도가 높은 단지 top_n 개를 유사도 점수와 함께 반환.

    언제:
        - 사용자가 "이 아파트랑 비슷한 곳 추천해줘" 라고 할 때.
        - 대안 단지 후보를 제시할 때.

    인자:
        query: 기준 아파트명 또는 PNU.
        mode: 유사도 산출 방식 ('location' 위치 / 'price' 가격 /
              'lifestyle' 라이프스타일 / 'combined' 종합, 기본 combined).
        top_n: 반환 단지 수 (기본 5).
        exclude_same_area: True 면 같은 시군구는 제외.
    """
    return await tool_executors.get_similar_apartments(
        query=query,
        mode=mode,
        top_n=top_n,
        exclude_same_area=exclude_same_area,
    )


@mcp.tool()
async def get_market_trend(region: str, period: str = "1y") -> str:
    """지역 시세 동향(월별 거래량·평균가).

    무엇:
        - 지역(시군구) 기준 월별 매매 실거래 동향 JSON.

    언제:
        - 사용자가 "강남구 시세 어때?" / "최근 1년 추이 보여줘" 라고 할 때.

    인자:
        region: 지역명 (예: '강남구', '자양동').
        period: 조회 기간 ('1y', '3y', '5y'; 기본 1y).
    """
    return await tool_executors.get_market_trend(region=region, period=period)


@mcp.tool()
async def get_school_info(query: str) -> str:
    """아파트의 초·중·고 학군 배정 정보.

    무엇:
        - 특정 아파트(또는 단지명 일부 매칭 시 복수 후보)의 학군 배정 정보 JSON.
        - 초등학교·중학교·고등학교 배정 결과 포함.

    언제:
        - 사용자가 "○○ 아파트 학군 어디야?" / "어느 초등학교 배정?" 라고 할 때.
        - 자녀 교육 관점에서 단지를 검토할 때.

    인자:
        query: 아파트명(부분 일치 가능) 또는 19자리 PNU 코드.
            예: '래미안대치팰리스', '1168010100100010000'.
    """
    return await tool_executors.get_school_info(query)


@mcp.tool()
async def get_dashboard_info(region: str = "", months: int = 6) -> str:
    """시군구 거래 동향 대시보드 — 이번 달 요약 + 랭킹 + 최근 N개월 추이.

    무엇:
        - 해당 지역의 이번 달/전월 거래량·중위가 요약.
        - 매매·전월세 거래 랭킹 (시도·시군구 단위).
        - 월별 시계열 데이터 (최대 60개월).
        - `region` 생략 시 전국 대상.

    언제:
        - 사용자가 "요즘 매매 많이 되는 지역 어디야?" / "○○구 이번 달 시장 어때?" 라고 할 때.
        - 전국·지역 관점의 시장 스냅샷이 필요할 때 (단일 단지 상세가 아닌).

    인자:
        region: 지역명 (예: '강남구', '서울'). 비우면 전국 기준.
        months: 시계열 추이 길이 (기본 6, 최대 60).
    """
    return await tool_executors.get_dashboard_info(region=region, months=months)


# ── ASGI export ────────────────────────────────────────────────────────────
# main.py 에서 `app.mount("/mcp", mcp_asgi_app)` 로 마운트.
mcp_asgi_app = mcp.streamable_http_app()
