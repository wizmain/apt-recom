"""연수솔밭마을(인천 연수동 582-2) — Phase C 경합 교체 뒤 남은 임대 레코드 잔재를 정리한다.

2026-09-30 `ingest_full_kapt --register-new` 가 분양 레코드 `연수솔밭마을`(A40676206)을 실제 PNU 에
올리고 임대 레코드 `연수1차시영임`(A40681704)을 더미로 밀어냈다. 그런데 밀려난 레코드의 매핑이
메모리에 옛 PNU 로 남아, 뒤이은 Phase B 가 임대 주택형을 분양 PNU 에 다시 써넣었다(적재 코드는
같은 날 수정). 남은 잔재 세 가지를 고친다.

  1. apt_area_type — 분양 PNU 에 섞인 임대 주택형(더미에 같은 행이 있는 것만) 삭제
  2. apt_area_info — 남은 주택형으로 재계산
  3. apartments — display_name(임대 이름) 과 도로명주소(임대 쪽 212) 를 분양 레코드 값으로

세대수 합산은 하지 않는다(scripts/kapt_swap_decisions.yaml: no) — 두 단지는 같은 지번을 쓰는
별개 단지다. 임대 레코드와 그 관리비·주택형은 더미 키에 그대로 남는다.

전제가 어긋나면(다른 레코드가 PNU 를 차지, 더미 없음) 아무것도 바꾸지 않고 중단한다. 재실행해도
결과가 같다.

⚠️ `--target railway --apply` 는 production 쓰기 — 사용자가 직접 실행한다.

사용 (기본 dry-run):
  .venv/bin/python -m scripts.fix_yeonsu_solbat_eviction_residue --target local
  .venv/bin/python -m scripts.fix_yeonsu_solbat_eviction_residue --target local --apply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.kapt.ingest_full_kapt import recalc_area_info
from batch.kapt.pnu_contention import dummy_pnu

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PNU = "2818510300005820002"
SALE_KAPT_CODE = "A40676206"
RENTAL_KAPT_CODE = "A40681704"
RENTAL_DISPLAY_NAME = "연수1차시영임"
RAILWAY_URL_MARKER = "railway"

AREA_INFO_COLUMNS = "min_area, max_area, avg_area, unit_count, area_types"


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    else:
        url = os.getenv("RAILWAY_DATABASE_URL")
        if url and RAILWAY_URL_MARKER not in url:
            raise SystemExit(
                "RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단"
            )
    if not url:
        raise SystemExit(f"{target} DB URL 미설정")
    return url


def _one(cur, sql: str, params: list):
    cur.execute(sql, params)
    return cur.fetchone()


def _check_preconditions(cur) -> None:
    """분양 레코드가 실제 PNU 에, 임대 레코드가 더미에 있어야 한다."""
    at_real = _one(cur, "SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [PNU])
    if not at_real or at_real[0] != SALE_KAPT_CODE:
        raise SystemExit(
            f"{PNU} 의 K-APT 레코드가 {SALE_KAPT_CODE} 가 아님 (현재 {at_real})"
        )
    dummy = dummy_pnu(RENTAL_KAPT_CODE)
    at_dummy = _one(cur, "SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [dummy])
    if not at_dummy or at_dummy[0] != RENTAL_KAPT_CODE:
        raise SystemExit(
            f"{dummy} 에 {RENTAL_KAPT_CODE} 레코드가 없음 (현재 {at_dummy})"
        )


def _snapshot(cur) -> dict:
    cur.execute(
        "SELECT exclusive_area, unit_count FROM apt_area_type WHERE pnu = %s ORDER BY 1",
        [PNU],
    )
    area_types = cur.fetchall()
    area_info = _one(
        cur, f"SELECT {AREA_INFO_COLUMNS} FROM apt_area_info WHERE pnu = %s", [PNU]
    )
    apartment = _one(
        cur,
        "SELECT bld_nm, display_name, new_plat_plc, total_hhld_cnt FROM apartments WHERE pnu = %s",
        [PNU],
    )
    return {"area_types": area_types, "area_info": area_info, "apartment": apartment}


def _print_snapshot(label: str, snap: dict) -> None:
    print(f"[{label}]")
    print(f"  주택형(㎡, 세대): {snap['area_types']}")
    print(f"  면적 요약({AREA_INFO_COLUMNS}): {snap['area_info']}")
    print(f"  apartments(bld_nm, display_name, 도로명, 세대수): {snap['apartment']}")


def _apply_fix(cur) -> None:
    # 더미에 같은 (면적, 세대수) 행이 있는 것만 지운다 — 임대 레코드 것임이 확인된 행.
    cur.execute(
        """
        DELETE FROM apt_area_type t
         USING apt_area_type d
         WHERE t.pnu = %s AND d.pnu = %s
           AND d.exclusive_area = t.exclusive_area AND d.unit_count = t.unit_count
        """,
        [PNU, dummy_pnu(RENTAL_KAPT_CODE)],
    )
    print(f"  apt_area_type 삭제: {cur.rowcount}행")
    recalc_area_info(cur, PNU)
    # 표시명은 임대 이름일 때만 바꾼다. 도로명은 K-APT 분양 레코드 주소의 시도 표기를 기존 형식으로.
    cur.execute(
        """
        UPDATE apartments a
           SET display_name = a.bld_nm,
               new_plat_plc = regexp_replace(k.road_addr, '^인천광역시', '인천')
          FROM apt_kapt_info k
         WHERE a.pnu = %s AND k.pnu = a.pnu AND a.display_name = %s
        """,
        [PNU, RENTAL_DISPLAY_NAME],
    )
    print(f"  apartments 갱신: {cur.rowcount}행")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("local", "railway"), required=True)
    parser.add_argument(
        "--apply", action="store_true", help="반영 (기본 dry-run — 롤백)"
    )
    args = parser.parse_args()

    conn = psycopg2.connect(_db_url(args.target))
    try:
        cur = conn.cursor()
        _check_preconditions(cur)
        _print_snapshot(f"{args.target} 변경 전", _snapshot(cur))
        _apply_fix(cur)
        _print_snapshot(f"{args.target} 변경 후", _snapshot(cur))
        if args.apply:
            conn.commit()
            print("✅ 반영 완료")
        else:
            conn.rollback()
            print("dry-run — 롤백했습니다 (--apply 로 반영)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
