"""특정 PNU의 좌표를 Kakao POI(verified)로 수동 갱신하는 일회용 스크립트.

수동 검증한 Kakao POI 좌표를 로컬·Railway DB의 apartments에 UPDATE하고,
감사 추적을 위해 apt_coord_candidates 테이블에 동일 정보를 manual_verified
match_status로 UPSERT한다. coord_source는 kakao_place_poi_verified 로 두어
batch.kakao_poi_coord_pipeline 의 PROTECTED_SOURCES 에 포함되어 자동 파이프라인이
다시 덮어쓰지 못하도록 보호한다.

사용:
  .venv/bin/python scripts/manual_verify_kakao_poi.py            # dry-run
  .venv/bin/python scripts/manual_verify_kakao_poi.py --apply    # 실제 UPDATE
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# 수동 매칭 결정값 — 변경 시 이 블록만 수정
PNU = "3611011500003780004"
NEW_LAT = 36.5270626890008
NEW_LNG = 127.26194728244253
NEW_COORD_SOURCE = "kakao_place_poi_verified"

CANDIDATE = {
    "pnu": PNU,
    "rank": 1,
    "query": "산울마을도심형주택2단지",
    "kakao_place_id": "1724903300",
    "place_name": "산울마을도심형주택2단지아파트",
    "category_name": "부동산 > 주거시설 > 아파트",
    "address_name": "세종특별자치시 산울동 산 14",
    "road_address_name": "",
    "lat": NEW_LAT,
    "lng": NEW_LNG,
    "distance_m": 81.2,
    # apt_coord_candidates.{name_score,address_score,total_score} NOT NULL — 수동 확정은 만점으로 기록
    "name_score": 1.0,
    "address_score": 1.0,
    "total_score": 2.0,
    "match_status": "manual_verified",
    "reason": (
        "manual override: Kakao 아파트 POI 이름 완전일치(name=1.00). "
        "기존 좌표는 vworld 가 지번 산울동 378-4 를 지오코딩한 값이고, "
        "Kakao POI 는 지번을 산울동 산 14 로 기재해 address_mismatch 로 needs_review 였다. "
        "같은 단지의 1단지가 이미 kakao_apt_poi_auto 좌표를 쓰고 있어 표기를 맞춘다."
    ),
    "coord_source": NEW_COORD_SOURCE,
}


def _connect(url: str):
    return psycopg2.connect(url)


def _cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _show_before(conn, label: str) -> None:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT pnu, bld_nm, new_plat_plc, lat, lng, coord_source
        FROM apartments WHERE pnu = %s
        """,
        (PNU,),
    )
    row = cur.fetchone()
    print(f"[{label}] BEFORE: {dict(row) if row else 'NOT FOUND'}")


def _show_after(conn, label: str) -> None:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT pnu, lat, lng, coord_source
        FROM apartments WHERE pnu = %s
        """,
        (PNU,),
    )
    row = cur.fetchone()
    print(f"[{label}] AFTER : {dict(row) if row else 'NOT FOUND'}")


def _apply_update(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE apartments
           SET lat = %s, lng = %s, coord_source = %s
         WHERE pnu = %s
        """,
        (NEW_LAT, NEW_LNG, NEW_COORD_SOURCE, PNU),
    )
    # apt_coord_candidates 에 (pnu, rank) UNIQUE 가 없어 단순 DELETE→INSERT 로 단일 manual_verified 행을 남긴다.
    cur.execute("DELETE FROM apt_coord_candidates WHERE pnu = %s", (PNU,))
    cur.execute(
        """
        INSERT INTO apt_coord_candidates (
            pnu, rank, query, kakao_place_id, place_name, category_name,
            address_name, road_address_name, lat, lng, distance_m,
            name_score, address_score, total_score,
            match_status, reason, coord_source, generated_at
        ) VALUES (
            %(pnu)s, %(rank)s, %(query)s, %(kakao_place_id)s, %(place_name)s, %(category_name)s,
            %(address_name)s, %(road_address_name)s, %(lat)s, %(lng)s, %(distance_m)s,
            %(name_score)s, %(address_score)s, %(total_score)s,
            %(match_status)s, %(reason)s, %(coord_source)s, NOW()
        )
        """,
        CANDIDATE,
    )


def run(target_label: str, url: str | None, apply: bool) -> None:
    if not url:
        print(f"[{target_label}] URL 미설정 — 스킵")
        return
    conn = _connect(url)
    conn.autocommit = False
    try:
        _show_before(conn, target_label)
        if apply:
            _apply_update(conn)
            conn.commit()
            _show_after(conn, target_label)
        else:
            print(f"[{target_label}] dry-run — 변경 없음")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true", help="실제 UPDATE 수행 (기본은 dry-run)"
    )
    args = parser.parse_args()

    print(
        f"target pnu={PNU}\n"
        f"  → lat={NEW_LAT}, lng={NEW_LNG}, coord_source={NEW_COORD_SOURCE}\n"
        f"  POI: {CANDIDATE['place_name']} ({CANDIDATE['road_address_name']})\n"
    )

    run("LOCAL  ", os.getenv("DATABASE_URL"), args.apply)
    run("RAILWAY", os.getenv("RAILWAY_DATABASE_URL"), args.apply)


if __name__ == "__main__":
    main()
