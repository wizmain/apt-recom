"""Kakao 건물/아파트 POI 좌표 후보 생성 및 안전 적용.

전체 apartments 좌표를 Kakao 건물 좌표로 바꾸기 위한 staged pipeline.

사용 예:
  # 후보 테이블 생성 + 로컬 100건 후보 생성만
  .venv/bin/python -m batch.kakao_poi_coord_pipeline generate --target local --limit 100

  # 자동 승인 후보만 로컬 적용
  .venv/bin/python -m batch.kakao_poi_coord_pipeline apply --target local --limit 100

  # 로컬에서 검증 후 Railway까지 같은 후보 적용
  .venv/bin/python -m batch.kakao_poi_coord_pipeline apply --target both --limit 1000
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from batch.config import KAKAO_API_KEY, KAKAO_RATE
from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
AUTO_APT_SOURCE = "kakao_apt_poi_auto"
AUTO_PLACE_SOURCE = "kakao_place_poi_auto"

BAD_PLACE_WORDS = (
    "상가",
    "관리사무소",
    "경비",
    "경로당",
    "어린이집",
    "유치원",
    "정문",
    "후문",
    "주차장",
    "배드민턴장",
    "노인정",
    "충전소",
)

VERIFIED_SOURCES = (
    "kakao_apt_poi_verified",
    "kakao_place_poi_verified",
)

PROTECTED_SOURCES = VERIFIED_SOURCES + (
    AUTO_APT_SOURCE,
    AUTO_PLACE_SOURCE,
)


@dataclass
class Candidate:
    pnu: str
    rank: int
    query: str
    place_id: str
    place_name: str
    category_name: str
    address_name: str
    road_address_name: str
    lat: float
    lng: float
    distance_m: float | None
    name_score: float
    address_score: float
    total_score: float
    match_status: str
    reason: str
    coord_source: str


def _connect(url: str):
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _ensure_tables(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS apt_coord_candidates (
            pnu TEXT NOT NULL,
            rank INTEGER NOT NULL,
            query TEXT NOT NULL,
            kakao_place_id TEXT NOT NULL,
            place_name TEXT NOT NULL,
            category_name TEXT,
            address_name TEXT,
            road_address_name TEXT,
            lat DOUBLE PRECISION NOT NULL,
            lng DOUBLE PRECISION NOT NULL,
            distance_m DOUBLE PRECISION,
            name_score DOUBLE PRECISION NOT NULL,
            address_score DOUBLE PRECISION NOT NULL,
            total_score DOUBLE PRECISION NOT NULL,
            match_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            coord_source TEXT NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (pnu, kakao_place_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS apt_coord_history (
            id BIGSERIAL PRIMARY KEY,
            pnu TEXT NOT NULL,
            old_lat DOUBLE PRECISION,
            old_lng DOUBLE PRECISION,
            old_coord_source TEXT,
            new_lat DOUBLE PRECISION NOT NULL,
            new_lng DOUBLE PRECISION NOT NULL,
            new_coord_source TEXT NOT NULL,
            kakao_place_id TEXT,
            place_name TEXT,
            match_status TEXT,
            total_score DOUBLE PRECISION,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            method TEXT NOT NULL DEFAULT 'kakao_poi_coord_pipeline'
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_apt_coord_candidates_status ON apt_coord_candidates(match_status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_apt_coord_candidates_pnu_score ON apt_coord_candidates(pnu, total_score DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_apt_coord_history_pnu ON apt_coord_history(pnu)")
    conn.commit()


def _norm(value: str | None) -> str:
    s = value or ""
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace(" ", "").replace("-", "").replace("·", "")
    s = s.replace("아파트", "").replace("APT", "")
    s = s.lower()
    return s


def _addr_norm(value: str | None) -> str:
    s = value or ""
    s = s.replace("경기도", "경기").replace("서울특별시", "서울").replace("인천광역시", "인천")
    s = s.replace("번지", "")
    return re.sub(r"\s+", "", s)


def _name_similarity(a: str | None, b: str | None) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _distance_m(lat1: float | None, lng1: float | None, lat2: float, lng2: float) -> float | None:
    if lat1 is None or lng1 is None:
        return None
    r = 6371000.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _address_score(doc: dict[str, Any], apt: dict[str, Any]) -> tuple[float, str]:
    doc_road = _addr_norm(doc.get("road_address_name"))
    doc_jibun = _addr_norm(doc.get("address_name"))
    apt_road = _addr_norm(apt.get("new_plat_plc"))
    apt_jibun = _addr_norm(apt.get("plat_plc"))
    if apt_road and doc_road and (apt_road == doc_road or apt_road in doc_road or doc_road in apt_road):
        return 1.0, "road_address_match"
    if apt_jibun and doc_jibun and (apt_jibun == doc_jibun or apt_jibun in doc_jibun or doc_jibun in apt_jibun):
        return 1.0, "jibun_address_match"
    if apt_road and doc_road:
        # 같은 도로명까지는 일치하지만 건물번호가 다른 경우를 약한 후보로 남긴다.
        road_name = re.sub(r"\d.*$", "", apt_road)
        if len(road_name) >= 6 and road_name in doc_road:
            return 0.45, "road_name_partial"
    return 0.0, "address_mismatch"


def _queries_for(apt: dict[str, Any]) -> list[str]:
    names = []
    for key in ("display_name", "bld_nm"):
        value = (apt.get(key) or "").strip()
        if value and value not in names:
            names.append(value)
    addrs = []
    for key in ("new_plat_plc", "plat_plc"):
        value = (apt.get(key) or "").strip()
        if value and value not in addrs:
            addrs.append(value)

    queries: list[str] = []
    for name in names:
        for addr in addrs:
            queries.append(f"{addr} {name}")
        queries.append(name)
    return queries[:5]


def _kakao_keyword(query: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    for attempt in range(3):
        try:
            r = requests.get(
                KAKAO_KEYWORD_URL,
                headers=headers,
                params={"query": query, "size": 15},
                timeout=8,
            )
            time.sleep(KAKAO_RATE)
            if r.status_code == 200:
                return r.json().get("documents", [])
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(1 + attempt)
                continue
            return []
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            return []
    return []


def _score_doc(apt: dict[str, Any], doc: dict[str, Any], rank: int, query: str) -> Candidate | None:
    if not doc.get("x") or not doc.get("y") or not doc.get("id"):
        return None

    place_name = doc.get("place_name") or ""
    category = doc.get("category_name") or ""
    lat = float(doc["y"])
    lng = float(doc["x"])
    distance = _distance_m(apt.get("lat"), apt.get("lng"), lat, lng)

    base_name = apt.get("display_name") or apt.get("bld_nm") or ""
    name_score = max(
        _name_similarity(base_name, place_name),
        _name_similarity(apt.get("bld_nm"), place_name),
    )
    address_score, addr_reason = _address_score(doc, apt)
    is_apt = "부동산 > 주거시설 > 아파트" in category
    has_bad_word = any(word in place_name for word in BAD_PLACE_WORDS)

    total = 0.0
    total += name_score * 30
    total += address_score * 35
    total += 25 if is_apt else 8
    if distance is not None:
        if distance <= 250:
            total += 10
        elif distance <= 500:
            total += 6
        elif distance <= 1000:
            total += 2
        else:
            total -= 20
    if has_bad_word:
        total -= 60

    reasons = [addr_reason]
    if is_apt:
        reasons.append("apt_category")
    if has_bad_word:
        reasons.append("bad_place_word")
    if distance is not None:
        reasons.append(f"distance={distance:.1f}m")
    reasons.append(f"name={name_score:.2f}")

    if (
        total >= 82
        and is_apt
        and not has_bad_word
        and address_score >= 1.0
        and (distance is None or distance <= 1000)
    ):
        status = "auto_approved"
        source = AUTO_APT_SOURCE
    elif (
        total >= 78
        and not has_bad_word
        and address_score >= 1.0
        and (distance is None or distance <= 500)
    ):
        status = "auto_approved"
        source = AUTO_PLACE_SOURCE
    else:
        status = "needs_review"
        source = AUTO_APT_SOURCE if is_apt else AUTO_PLACE_SOURCE

    return Candidate(
        pnu=apt["pnu"],
        rank=rank,
        query=query,
        place_id=str(doc["id"]),
        place_name=place_name,
        category_name=category,
        address_name=doc.get("address_name") or "",
        road_address_name=doc.get("road_address_name") or "",
        lat=lat,
        lng=lng,
        distance_m=distance,
        name_score=name_score,
        address_score=address_score,
        total_score=total,
        match_status=status,
        reason=";".join(reasons),
        coord_source=source,
    )


def _select_targets(conn, args) -> list[dict[str, Any]]:
    cur = _dict_cursor(conn)
    where = [
        "pnu NOT LIKE 'TRADE\\_%%' ESCAPE '\\'",
        "pnu NOT LIKE 'KAPT\\_%%' ESCAPE '\\'",
        "LENGTH(pnu) = 19",
        "(display_name IS NOT NULL OR bld_nm IS NOT NULL)",
    ]
    params: list[Any] = []
    if not args.include_verified:
        where.append("(coord_source IS NULL OR coord_source NOT IN %s)")
        params.append(VERIFIED_SOURCES)
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        where.append("coord_source = ANY(%s)")
        params.append(sources)
    if args.sigungu_prefix:
        where.append("sigungu_code LIKE %s")
        params.append(f"{args.sigungu_prefix}%")
    if args.only_missing_candidates:
        where.append(
            """
            NOT EXISTS (
                SELECT 1 FROM apt_coord_candidates c
                WHERE c.pnu = apartments.pnu
            )
            """
        )
    sql = f"""
        SELECT pnu, display_name, bld_nm, plat_plc, new_plat_plc,
               sigungu_code, lat, lng, coord_source
        FROM apartments
        WHERE {' AND '.join(where)}
        ORDER BY pnu
    """
    if args.limit:
        sql += " LIMIT %s"
        params.append(args.limit)
    cur.execute(sql, params)
    return list(cur.fetchall())


def _upsert_candidates(conn, candidates: list[Candidate]) -> None:
    if not candidates:
        return
    rows = [
        (
            c.pnu,
            c.rank,
            c.query,
            c.place_id,
            c.place_name,
            c.category_name,
            c.address_name,
            c.road_address_name,
            c.lat,
            c.lng,
            c.distance_m,
            c.name_score,
            c.address_score,
            c.total_score,
            c.match_status,
            c.reason,
            c.coord_source,
        )
        for c in candidates
    ]
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO apt_coord_candidates (
            pnu, rank, query, kakao_place_id, place_name, category_name,
            address_name, road_address_name, lat, lng, distance_m,
            name_score, address_score, total_score, match_status, reason,
            coord_source
        )
        VALUES %s
        ON CONFLICT (pnu, kakao_place_id) DO UPDATE SET
            rank = EXCLUDED.rank,
            query = EXCLUDED.query,
            place_name = EXCLUDED.place_name,
            category_name = EXCLUDED.category_name,
            address_name = EXCLUDED.address_name,
            road_address_name = EXCLUDED.road_address_name,
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            distance_m = EXCLUDED.distance_m,
            name_score = EXCLUDED.name_score,
            address_score = EXCLUDED.address_score,
            total_score = EXCLUDED.total_score,
            match_status = EXCLUDED.match_status,
            reason = EXCLUDED.reason,
            coord_source = EXCLUDED.coord_source,
            generated_at = now()
        """,
        rows,
        page_size=500,
    )
    conn.commit()


def generate(args) -> None:
    logger = setup_logger("kakao_poi_coord_generate")
    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        sys.exit(1)
    url = _db_url(args.target)
    conn = _connect(url)
    try:
        _ensure_tables(conn)
        targets = _select_targets(conn, args)
        logger.info(f"후보 생성 대상: {len(targets)}건 target={args.target}")
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        generated = 0
        auto_approved = 0
        for i, apt in enumerate(targets, 1):
            seen: set[str] = set()
            candidates: list[Candidate] = []
            for query in _queries_for(apt):
                docs = _kakao_keyword(query, headers)
                for doc in docs:
                    place_id = str(doc.get("id") or "")
                    if not place_id or place_id in seen:
                        continue
                    seen.add(place_id)
                    cand = _score_doc(apt, doc, len(candidates) + 1, query)
                    if cand:
                        candidates.append(cand)
            candidates.sort(key=lambda c: c.total_score, reverse=True)
            for rank, cand in enumerate(candidates[:5], 1):
                cand.rank = rank
            chosen = candidates[:5]
            _upsert_candidates(conn, chosen)
            generated += len(chosen)
            auto_approved += sum(1 for c in chosen if c.match_status == "auto_approved")
            if i % 25 == 0 or i == len(targets):
                logger.info(f"진행 {i}/{len(targets)} 후보={generated} 자동승인후보={auto_approved}")
    finally:
        conn.close()


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
    else:
        raise ValueError("single DB target expected")
    if not url:
        raise ValueError(f"{target} DB URL 미설정")
    return url


def _apply_one_db(conn, limit: int | None, dry_run: bool, logger) -> int:
    _ensure_tables(conn)
    cur = _dict_cursor(conn)
    sql = """
        WITH ranked AS (
            SELECT DISTINCT ON (c.pnu)
                   c.*, a.lat AS old_lat, a.lng AS old_lng, a.coord_source AS old_coord_source
            FROM apt_coord_candidates c
            JOIN apartments a ON a.pnu = c.pnu
            WHERE c.match_status = 'auto_approved'
              AND (a.coord_source IS NULL OR a.coord_source NOT IN %s)
            ORDER BY c.pnu, c.total_score DESC, c.rank ASC
        )
        SELECT *
        FROM ranked
        ORDER BY total_score DESC, pnu
    """
    params: list[Any] = [PROTECTED_SOURCES]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    rows = list(cur.fetchall())
    logger.info(f"적용 대상 자동승인 후보: {len(rows)}건 dry_run={dry_run}")
    if dry_run or not rows:
        return len(rows)

    write_cur = conn.cursor()
    applied = 0
    for r in rows:
        write_cur.execute(
            """
            INSERT INTO apt_coord_history (
                pnu, old_lat, old_lng, old_coord_source,
                new_lat, new_lng, new_coord_source,
                kakao_place_id, place_name, match_status, total_score
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                r["pnu"],
                r["old_lat"],
                r["old_lng"],
                r["old_coord_source"],
                r["lat"],
                r["lng"],
                r["coord_source"],
                r["kakao_place_id"],
                r["place_name"],
                r["match_status"],
                r["total_score"],
            ],
        )
        write_cur.execute(
            "UPDATE apartments SET lat=%s, lng=%s, coord_source=%s WHERE pnu=%s",
            [r["lat"], r["lng"], r["coord_source"], r["pnu"]],
        )
        applied += write_cur.rowcount
    conn.commit()
    return applied


def apply(args) -> None:
    logger = setup_logger("kakao_poi_coord_apply")
    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for target in targets:
        conn = _connect(_db_url(target))
        try:
            applied = _apply_one_db(conn, args.limit, args.dry_run, logger)
            logger.info(f"[{target}] {'dry-run ' if args.dry_run else ''}적용: {applied}건")
        finally:
            conn.close()


def summary(args) -> None:
    for target in (["local", "railway"] if args.target == "both" else [args.target]):
        conn = _connect(_db_url(target))
        try:
            _ensure_tables(conn)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT match_status, coord_source, count(*)
                FROM apt_coord_candidates
                GROUP BY match_status, coord_source
                ORDER BY match_status, coord_source
                """
            )
            print(f"DB={target}")
            for row in cur.fetchall():
                print(row)
        finally:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate")
    gen.add_argument("--target", choices=["local", "railway"], default="local")
    gen.add_argument("--limit", type=int)
    gen.add_argument("--sources", help="대상 coord_source 콤마 목록")
    gen.add_argument("--sigungu-prefix", help="시군구 prefix 예: 41113")
    gen.add_argument("--include-verified", action="store_true")
    gen.add_argument(
        "--include-existing-candidates",
        action="store_false",
        dest="only_missing_candidates",
        default=True,
        help="이미 후보가 있는 PNU도 다시 생성",
    )
    gen.set_defaults(func=generate)

    app = sub.add_parser("apply")
    app.add_argument("--target", choices=["local", "railway", "both"], default="local")
    app.add_argument("--limit", type=int)
    app.add_argument("--dry-run", action="store_true")
    app.set_defaults(func=apply)

    summ = sub.add_parser("summary")
    summ.add_argument("--target", choices=["local", "railway", "both"], default="local")
    summ.set_defaults(func=summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
