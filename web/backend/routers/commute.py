"""Commute time API using ODSay public transit search."""

import os
import logging
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

from database import DictConnection

load_dotenv(Path(__file__).resolve().parents[2].parent / ".env")

ODSAY_API_KEY = os.getenv("ODSAY_API_KEY", "")
ODSAY_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")

router = APIRouter()
logger = logging.getLogger(__name__)

def _get_path_type_labels():
    from common_codes import get_code_map
    return {int(k): v for k, v in get_code_map("path_type").items()}


class CommuteRequest(BaseModel):
    pnu: str
    destination: str  # 주소 또는 장소명 (예: "강남역", "여의도 IFC")


class CommuteRoute(BaseModel):
    path_type: str
    total_time: int
    transit_count: int
    walk_time: int
    payment: int
    first_start: str
    last_start: str
    summary: str


class CommuteResponse(BaseModel):
    apartment_name: str
    destination: str
    destination_address: str
    routes: list[CommuteRoute]


def _geocode_destination(query: str) -> tuple[float, float, str] | None:
    """Kakao 키워드 검색으로 목적지 좌표 조회."""
    if not KAKAO_API_KEY:
        return None

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    # 1) 키워드 검색 (장소명)
    resp = requests.get(
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        headers=headers,
        params={"query": query, "size": 1},
        timeout=5,
    )
    data = resp.json()
    docs = data.get("documents", [])
    if docs:
        d = docs[0]
        return float(d["y"]), float(d["x"]), d.get("address_name", query)

    # 2) 주소 검색 폴백
    resp2 = requests.get(
        "https://dapi.kakao.com/v2/local/search/address.json",
        headers=headers,
        params={"query": query},
        timeout=5,
    )
    data2 = resp2.json()
    docs2 = data2.get("documents", [])
    if docs2:
        d = docs2[0]
        return float(d["y"]), float(d["x"]), d.get("address_name", query)

    return None


def _search_transit(sx: float, sy: float, ex: float, ey: float) -> list[dict]:
    """ODSay 대중교통 경로 검색."""
    if not ODSAY_API_KEY:
        raise HTTPException(status_code=500, detail="ODSAY_API_KEY not configured")

    url = f"{ODSAY_URL}?SX={sx}&SY={sy}&EX={ex}&EY={ey}&apiKey={ODSAY_API_KEY}"
    resp = requests.get(url, timeout=15)
    data = resp.json()

    if "error" in data:
        err = data["error"]
        if isinstance(err, list):
            err = err[0]
        code = err.get("code", "")
        msg = err.get("message", "")
        if code == "-98":
            return []  # 경로 없음
        raise HTTPException(status_code=502, detail=f"ODSay 오류: {msg}")

    paths = data.get("result", {}).get("path", [])
    return paths


def _build_route_summary(path: dict) -> str:
    """경로의 요약 문자열 생성 (예: '1호선 → 환승 → 2호선')."""
    sub_paths = path.get("subPath", [])
    parts = []
    for sp in sub_paths:
        traffic_type = sp.get("trafficType")  # 1=지하철, 2=버스, 3=도보
        if traffic_type == 1:
            name = sp.get("startName", "")
            lane = sp.get("lane", [{}])
            line_name = lane[0].get("name", "") if lane else ""
            parts.append(line_name or name)
        elif traffic_type == 2:
            lane = sp.get("lane", [{}])
            bus_no = lane[0].get("busNo", "") if lane else ""
            parts.append(f"버스 {bus_no}")
    return " → ".join(parts) if parts else "도보"


@router.post("/commute", response_model=CommuteResponse)
async def search_commute(req: CommuteRequest):
    """아파트에서 목적지까지 대중교통 출퇴근 시간 조회."""
    # 1. 아파트 좌표 조회
    conn = DictConnection()
    try:
        apt = conn.execute(
            "SELECT bld_nm, lat, lng FROM apartments WHERE pnu = %s", [req.pnu]
        ).fetchone()
    finally:
        conn.close()

    if not apt:
        raise HTTPException(status_code=404, detail="아파트를 찾을 수 없습니다.")
    if not apt["lat"] or not apt["lng"]:
        raise HTTPException(status_code=400, detail="아파트 좌표 정보가 없습니다.")

    # 2. 목적지 좌표 조회 (Kakao)
    dest = _geocode_destination(req.destination)
    if not dest:
        raise HTTPException(status_code=404, detail=f"'{req.destination}' 위치를 찾을 수 없습니다.")
    dest_lat, dest_lng, dest_address = dest

    # 3. ODSay 대중교통 경로 검색
    paths = _search_transit(
        sx=apt["lng"], sy=apt["lat"],
        ex=dest_lng, ey=dest_lat,
    )

    if not paths:
        raise HTTPException(status_code=404, detail="대중교통 경로를 찾을 수 없습니다.")

    # 4. 상위 5개 경로 반환
    routes = []
    for path in paths[:5]:
        info = path.get("info", {})
        routes.append(CommuteRoute(
            path_type=_get_path_type_labels().get(path.get("pathType", 0), "기타"),
            total_time=info.get("totalTime", 0),
            transit_count=info.get("busTransitCount", 0) + info.get("subwayTransitCount", 0),
            walk_time=info.get("totalWalk", 0),
            payment=info.get("payment", 0),
            first_start=info.get("firstStartStation", ""),
            last_start=info.get("lastStartStation", ""),
            summary=_build_route_summary(path),
        ))

    return CommuteResponse(
        apartment_name=apt["bld_nm"] or "",
        destination=req.destination,
        destination_address=dest_address,
        routes=routes,
    )


@router.get("/commute/search")
async def commute_quick(
    pnu: str = Query(...),
    dest: str = Query(..., min_length=1),
):
    """GET shorthand for commute search."""
    req = CommuteRequest(pnu=pnu, destination=dest)
    return await search_commute(req)
