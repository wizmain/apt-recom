"""미수집 아파트 면적 데이터 배치 수집.

PNU가 있지만 apt_area_info에 없는 아파트를 대상으로
건축물대장 전유부(getBrExposPubuseAreaInfo) API를 호출하여
호별 전용/공급 면적을 수집한다.

사용법:
  python -m batch.fill_area_info                   # 전체 미수집 대상
  python -m batch.fill_area_info --max-calls 900   # API 호출 횟수 제한
  python -m batch.fill_area_info --resume           # 마지막 중단점부터 재개
  python -m batch.fill_area_info --sgg 11680        # 특정 시군구만
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from batch.config import DATA_GO_KR_RATE
from batch.db import get_connection, query_all
from batch.trade.collect_area_info import (
    KeysExhausted,
    ensure_schema,
    fetch_area_info,
    is_exhausted,
    upsert_area_info,
)

logger = logging.getLogger("fill_area_info")

CHECKPOINT_PATH = Path(__file__).parent / ".area_checkpoint.json"
COMMIT_INTERVAL = 50  # N건마다 커밋


def _load_checkpoint() -> set[str]:
    """이전 실행에서 처리 완료된 PNU 목록 로드."""
    if not CHECKPOINT_PATH.exists():
        return set()
    try:
        data = json.loads(CHECKPOINT_PATH.read_text())
        return set(data.get("done", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _save_checkpoint(done: set[str]) -> None:
    """처리 완료 PNU 목록 저장 — 중단 시 재개용."""
    CHECKPOINT_PATH.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False)
    )


def _get_targets(conn, *, sgg_filter: str | None = None) -> list[dict]:
    """수집 대상 조회: PNU 있지만 apt_area_info 없는 아파트."""
    sql = """
        SELECT a.pnu, a.bld_nm, a.sigungu_code
        FROM apartments a
        WHERE a.pnu IS NOT NULL
          AND a.pnu NOT LIKE 'TRADE_%%'
          AND LENGTH(a.pnu) = 19
          AND NOT EXISTS (
              SELECT 1 FROM apt_area_info ai WHERE ai.pnu = a.pnu
          )
    """
    params: list = []
    if sgg_filter:
        sql += " AND LEFT(a.pnu, 5) = %s"
        params.append(sgg_filter)
    sql += " ORDER BY a.pnu"
    return query_all(conn, sql, params)


def _parse_pnu(pnu: str) -> dict | None:
    """19자리 PNU를 건축물대장 API 파라미터로 분해."""
    if not pnu or len(pnu) != 19:
        return None
    return {
        "sigungu_cd": pnu[:5],
        "bjdong_cd": pnu[5:10],
        "plat_gb": pnu[10],
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }


def run(*, max_calls: int | None = None, resume: bool = False,
        sgg_filter: str | None = None) -> None:
    conn = get_connection()
    conn.autocommit = True  # DDL 즉시 반영
    ensure_schema(conn)
    conn.autocommit = False

    targets = _get_targets(conn, sgg_filter=sgg_filter)
    logger.info(f"수집 대상: {len(targets)}건")

    if not targets:
        logger.info("수집할 대상이 없습니다.")
        return

    # 체크포인트: 이전 실행에서 완료된 PNU 스킵
    done = _load_checkpoint() if resume else set()
    if done:
        before = len(targets)
        targets = [t for t in targets if t["pnu"] not in done]
        logger.info(f"체크포인트 로드: {before - len(targets)}건 스킵, 잔여 {len(targets)}건")

    api_calls = 0
    success = 0
    no_data = 0
    errors = 0

    for i, row in enumerate(targets):
        pnu = row["pnu"]
        params = _parse_pnu(pnu)
        if not params:
            logger.warning(f"PNU 파싱 실패: {pnu}")
            errors += 1
            continue

        # API 호출 한도 체크
        if max_calls and api_calls >= max_calls:
            logger.info(f"API 호출 한도 도달 ({max_calls}건)")
            break

        # 키 소진 체크
        if is_exhausted():
            logger.warning("API 키 전부 소진 — 중단")
            break

        try:
            time.sleep(DATA_GO_KR_RATE)
            area_info = fetch_area_info(
                params["sigungu_cd"],
                params["bjdong_cd"],
                params["plat_gb"],
                params["bun"],
                params["ji"],
            )
            api_calls += 1

            if area_info:
                upsert_area_info(conn, pnu, area_info)
                success += 1
            else:
                no_data += 1

            done.add(pnu)

        except KeysExhausted:
            logger.warning("API 키 전부 소진 — 중단")
            break
        except Exception as e:
            logger.warning(f"오류 ({pnu}, {row.get('bld_nm', '')}): {e}")
            errors += 1
            done.add(pnu)  # 오류 건도 재시도 방지

        # 주기적 커밋 + 진행률 로깅
        if (i + 1) % COMMIT_INTERVAL == 0:
            conn.commit()
            _save_checkpoint(done)
            pct = (i + 1) / len(targets) * 100
            logger.info(
                f"진행: {i + 1}/{len(targets)} ({pct:.1f}%) "
                f"| API {api_calls}회 | 성공 {success} | 데이터없음 {no_data} | 오류 {errors}"
            )

    # 최종 커밋 + 체크포인트
    conn.commit()
    _save_checkpoint(done)
    conn.close()

    logger.info(
        f"완료: API {api_calls}회 | 성공 {success} | 데이터없음 {no_data} | 오류 {errors}"
    )
    if max_calls and api_calls >= max_calls:
        remaining = len(targets) - (success + no_data + errors)
        logger.info(f"잔여 미수집: ~{remaining}건 (--resume 으로 재개 가능)")


def main():
    parser = argparse.ArgumentParser(description="아파트 면적 데이터 배치 수집")
    parser.add_argument("--max-calls", type=int, default=None,
                        help="API 호출 최대 횟수 (일일 한도 관리용)")
    parser.add_argument("--resume", action="store_true",
                        help="이전 체크포인트부터 재개")
    parser.add_argument("--sgg", type=str, default=None,
                        help="특정 시군구 코드만 수집 (예: 11680)")
    parser.add_argument("--clear-checkpoint", action="store_true",
                        help="체크포인트 초기화")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.clear_checkpoint:
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()
            logger.info("체크포인트 초기화 완료")
        return

    run(
        max_calls=args.max_calls,
        resume=args.resume,
        sgg_filter=args.sgg,
    )


if __name__ == "__main__":
    main()
