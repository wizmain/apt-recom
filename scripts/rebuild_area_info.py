"""전체 아파트 `apt_area_info` 재구축 — 건축물대장 전유부 ground truth 기반.

사용법:
  # 첫 실행 (체크포인트 없음 → 처음부터)
  .venv/bin/python -m scripts.rebuild_area_info --max-calls 800

  # 이어서 실행 (체크포인트에서 재개)
  .venv/bin/python -m scripts.rebuild_area_info --max-calls 800

  # 특정 PNU 1건 테스트
  .venv/bin/python -m scripts.rebuild_area_info --pnu 1141011000010170000

대상:
  - apartments 테이블의 모든 정규 PNU (TRADE_*, KAPT_* 제외 — 건축물대장 조회 불가)
  - apt_area_info.source 가 'bld_expos' 가 아닌 레코드 우선 (stale 교체)

입력 파라미터 추출:
  pnu 19자리 → sigungu_cd(5) + bjdong_cd(5) + plat_gb(1) + bun(4) + ji(4)

체크포인트:
  common_code.group_id = 'rebuild_area_checkpoint', code = 'last_pnu'
"""

from __future__ import annotations

import argparse
import json
import time

from batch.config import DATA_GO_KR_RATE
from batch.db import get_connection, get_dict_cursor, query_all, query_one
from batch.logger import setup_logger
from batch.trade.collect_area_info import fetch_area_info, upsert_area_info

CHECKPOINT_GROUP = "rebuild_area_checkpoint"


def _parse_pnu(pnu: str) -> dict | None:
    """정규 19자리 PNU → bld_params dict."""
    if not pnu or len(pnu) != 19 or not pnu.isdigit():
        return None
    return {
        "sigungu_cd": pnu[0:5],
        "bjdong_cd": pnu[5:10],
        "plat_gb_cd": pnu[10:11],
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }


def _load_checkpoint(conn) -> str | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, "last_pnu"],
    )
    row = cur.fetchone()
    return row[0] if row else None


def _save_checkpoint(conn, pnu: str, progress: dict) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET
               name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [CHECKPOINT_GROUP, "last_pnu", pnu, json.dumps(progress, ensure_ascii=False)],
    )
    conn.commit()


def _select_targets(conn, last_pnu: str | None) -> list[str]:
    """우선순위:
       1) apt_area_info.source != 'bld_expos' 또는 apt_area_info 미존재 아파트
       2) pnu 오름차순으로 체크포인트 이후
    """
    q = """
        SELECT a.pnu FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.pnu NOT LIKE 'TRADE_%%' AND a.pnu NOT LIKE 'KAPT_%%'
          AND LENGTH(a.pnu) = 19
          AND (ai.source IS NULL OR ai.source != 'bld_expos')
    """
    params: list = []
    if last_pnu:
        q += " AND a.pnu > %s"
        params.append(last_pnu)
    q += " ORDER BY a.pnu"
    return [r["pnu"] for r in query_all(conn, q, params)]


def process_one(conn, pnu: str, logger) -> str:
    """단일 PNU 재구축. 결과: 'ok' | 'nodata' | 'skip' | 'error'."""
    bp = _parse_pnu(pnu)
    if not bp:
        return "skip"
    try:
        info = fetch_area_info(bp["sigungu_cd"], bp["bjdong_cd"],
                               bp["plat_gb_cd"], bp["bun"], bp["ji"])
    except Exception as e:
        logger.warning(f"  {pnu} 호출 실패: {e}")
        return "error"
    if not info:
        return "nodata"
    upsert_area_info(conn, pnu, info)
    conn.commit()
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="apt_area_info 전체 재구축 (건축물대장 전유부)")
    parser.add_argument("--max-calls", type=int, default=800,
                        help="이번 실행 최대 API 호출 수 (기본 800)")
    parser.add_argument("--pnu", type=str, default=None,
                        help="단일 PNU만 처리 (테스트)")
    parser.add_argument("--reset", action="store_true",
                        help="체크포인트 초기화")
    args = parser.parse_args()

    logger = setup_logger("rebuild_area")
    conn = get_connection()

    if args.reset:
        cur = conn.cursor()
        cur.execute("DELETE FROM common_code WHERE group_id = %s", [CHECKPOINT_GROUP])
        conn.commit()
        logger.info("체크포인트 초기화")

    # 단건 테스트 모드
    if args.pnu:
        result = process_one(conn, args.pnu, logger)
        info = query_one(conn, "SELECT * FROM apt_area_info WHERE pnu = %s", [args.pnu])
        logger.info(f"{args.pnu}: {result}  {dict(info) if info else 'None'}")
        conn.close()
        return 0

    last_pnu = _load_checkpoint(conn)
    if last_pnu:
        logger.info(f"체크포인트 재개: last_pnu = {last_pnu}")
    else:
        logger.info("신규 실행 — 처음부터")

    targets = _select_targets(conn, last_pnu)
    logger.info(f"남은 대상: {len(targets)}건, 최대 {args.max_calls}콜 처리")

    stats = {"ok": 0, "nodata": 0, "skip": 0, "error": 0}
    for i, pnu in enumerate(targets):
        if stats["ok"] + stats["nodata"] + stats["error"] >= args.max_calls:
            logger.info(f"한도 도달 ({args.max_calls}콜). 다음 실행에서 이어서.")
            break

        result = process_one(conn, pnu, logger)
        stats[result] += 1
        time.sleep(DATA_GO_KR_RATE)

        if (i + 1) % 50 == 0:
            _save_checkpoint(conn, pnu, stats)
            logger.info(f"  진행: {i + 1}건 — {stats}")

    # 최종 체크포인트
    if targets:
        _save_checkpoint(conn, pnu, stats)

    logger.info(f"완료: {stats}")
    # 전체 진행률
    total = query_one(conn, "SELECT COUNT(*) AS n FROM apartments WHERE pnu NOT LIKE 'TRADE_%%' AND pnu NOT LIKE 'KAPT_%%' AND LENGTH(pnu) = 19")["n"]
    done = query_one(conn, "SELECT COUNT(*) AS n FROM apt_area_info WHERE source = 'bld_expos'")["n"]
    logger.info(f"전체 진행률: {done}/{total} ({done * 100 // max(total, 1)}%)")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
