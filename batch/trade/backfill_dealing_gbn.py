"""매매 거래의 비어 있는 거래유형(dealing_gbn) 백필.

배경
  dealing_gbn(중개거래/직거래)은 국토부 매매 API 가 2021.11 계약분부터 제공하지만, 적재 코드가
  이 칼럼을 저장하기 전에 들어온 행은 값이 비어 있다. 2026-11-25 운영 조회에서 수도권 2025.07~09
  계약분은 3.6%, 2026.01~03 은 3.3% 만 값이 있었다(2026.07~09 는 100%). 직거래를 빼는 집계
  (오르는 단지 변화율, 인스타 value 시리즈)가 최근 기간에서만 직거래를 빼게 되어 비교가 기울었다.

  기존 backfill_trades 는 umd_cd 가 비어 있는 행만 대상으로 삼아(그 행들은 이미 채워져 있다) 이
  결손을 메우지 못한다. 그래서 dealing_gbn 하나만 채우는 별도 경로를 둔다.

동작
  1. dealing_gbn 이 비어 있는 거래가 있는 (시군구, 계약월) 쌍을 최근 월부터 고른다.
  2. 쌍마다 매매 API 를 1회 호출한다(보조 키 — 정기 배치 한도와 분리).
  3. 거래 고유키 8칼럼(sgg_cd, apt_nm, exclu_use_ar, floor, deal_year, deal_month, deal_day,
     deal_amount)이 같고 dealing_gbn 이 비어 있는 행에만 값을 쓴다. 다른 칼럼은 건드리지 않는다.
  4. 처리한 쌍은 체크포인트(common_code)에 남겨 다음 실행에서 건너뛴다.

사용
  python -m batch.trade.backfill_dealing_gbn --target local --dry-run
  python -m batch.trade.backfill_dealing_gbn --target local --apply --sido 11,28,41 --from-ym 202507 --to-ym 202606
  python -m batch.trade.backfill_dealing_gbn --target railway --apply ...   # 운영은 사용자 허락 후

이 모듈 상단은 DB·네트워크 의존 없이 import 된다(scripts/tests CI 대상). DB·API 의존은 실행 함수
안에서 import 한다.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date

from batch.region_codes import normalize_api_sigungu

# 국토부 매매 API 가 dealingGbn 을 제공하기 시작한 계약월 — 이보다 이전 쌍은 호출해도 채울 값이 없다.
DEALING_GBN_FIRST_YM = 202111
DEFAULT_MAX_CALLS = (
    900  # 보조 키 일 한도 안에서 하루 1회 실행 기준(backfill_trades 와 같은 값)
)
CHECKPOINT_GROUP = "backfill_dealing_gbn_checkpoint"
CHECKPOINT_CODE = "completed"
CHECKPOINT_SAVE_EVERY = 50  # 이 쌍 수마다 커밋·체크포인트 저장(중단 시 손실 범위)


# ── 순수 함수 (CI 테스트 대상) ──────────────────────────────────────────────


def _clean_amount(val) -> int | None:
    # batch/trade/load_trades._clean_amount 와 같은 규칙 — 고유키가 적재 시점과 같아야 행이 맞는다.
    if not val:
        return None
    try:
        return int(float(re.sub(r"[,\s]", "", str(val))))
    except (ValueError, TypeError):
        return None


def _to_int(val) -> int | None:
    # batch/trade/load_trades._to_int 와 같은 규칙.
    try:
        return int(float(val)) if val else None
    except (ValueError, TypeError):
        return None


def _to_float(val) -> float | None:
    # batch/trade/load_trades._to_float 와 같은 규칙.
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def update_row(
    api_row: dict, aliases: dict, emd_names: dict[str, set[str]] | None = None
) -> tuple | None:
    """API 매매 행 → (dealing_gbn, 고유키 8칼럼) 튜플. 채울 값이나 고유키가 없으면 None.

    고유키는 load_trades 의 적재 규칙(시군구 코드 정규화 포함)과 같게 만든다.
    """
    dealing_gbn = (api_row.get("dealingGbn") or "").strip()
    if not dealing_gbn:
        return None
    sgg = normalize_api_sigungu(
        str(api_row.get("sggCd", "")),
        aliases,
        umd_cd=api_row.get("umdCd"),
        umd_nm=api_row.get("umdNm"),
        emd_names=emd_names,
    )
    apt_nm = str(api_row.get("aptNm", ""))
    exclu = _to_float(api_row.get("excluUseAr"))
    floor = _to_int(api_row.get("floor"))
    deal_year = _to_int(api_row.get("dealYear"))
    deal_month = _to_int(api_row.get("dealMonth"))
    deal_day = _to_int(api_row.get("dealDay"))
    amount = _clean_amount(api_row.get("dealAmount"))
    key = (sgg, apt_nm, exclu, floor, deal_year, deal_month, deal_day, amount)
    if not sgg or not apt_nm or any(v is None for v in key[2:]):
        return None
    return (dealing_gbn, *key)


def default_to_ym(today: date) -> int:
    """기본 종료 계약월 = 지난달(이번 달은 신고가 진행 중)."""
    year, month = (
        (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    )
    return year * 100 + month


def parse_sido(value: str) -> list[str]:
    """'11,28,41' → ['11', '28', '41']. 빈 값이면 [](전국)."""
    codes = [c.strip() for c in value.split(",") if c.strip()]
    for c in codes:
        if not re.fullmatch(r"\d{2}", c):
            raise ValueError(f"시도 코드는 두 자리 숫자여야 한다: {c!r}")
    return codes


def pair_key(sgg_cd: str, ym: int) -> str:
    return f"{sgg_cd}:{ym}"


# ── DB·API (실행 경로) ─────────────────────────────────────────────────────

_TARGETS_SQL = """
    SELECT DISTINCT sgg_cd, deal_year * 100 + deal_month AS ym
    FROM trade_history
    WHERE dealing_gbn IS NULL
      AND deal_year * 100 + deal_month BETWEEN %(from_ym)s AND %(to_ym)s
      {sido_filter}
    ORDER BY ym DESC, sgg_cd
"""

# 고유키로 맞춘 행 중 아직 비어 있는 행만 대상. dry-run 은 같은 조인으로 id 만 센다.
_MATCH_VALUES = """(VALUES %s) AS v(dealing_gbn, sgg_cd, apt_nm, exclu_use_ar, floor,
                          deal_year, deal_month, deal_day, deal_amount)"""
_MATCH_WHERE = """
    WHERE t.sgg_cd = v.sgg_cd AND t.apt_nm = v.apt_nm
      AND t.exclu_use_ar = v.exclu_use_ar::double precision AND t.floor = v.floor::int
      AND t.deal_year = v.deal_year::int AND t.deal_month = v.deal_month::int
      AND t.deal_day = v.deal_day::int AND t.deal_amount = v.deal_amount::int
      AND t.dealing_gbn IS NULL
"""
_UPDATE_SQL = (
    "UPDATE trade_history t SET dealing_gbn = v.dealing_gbn FROM "
    + _MATCH_VALUES
    + _MATCH_WHERE
    + " RETURNING t.id"
)
_DRY_RUN_SQL = "SELECT t.id FROM trade_history t, " + _MATCH_VALUES + _MATCH_WHERE


def _db_url(target: str) -> str:
    import os

    url = os.getenv("DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL")
    if not url:
        raise SystemExit(f"{target} DB URL 미설정 (.env 확인)")
    return url


def _load_targets(
    conn, from_ym: int, to_ym: int, sido: list[str]
) -> list[tuple[str, int]]:
    from batch.db import query_all

    params = {"from_ym": from_ym, "to_ym": to_ym}
    sido_filter = ""
    if sido:
        sido_filter = "AND LEFT(sgg_cd, 2) = ANY(%(sido)s)"
        params["sido"] = sido
    rows = query_all(conn, _TARGETS_SQL.format(sido_filter=sido_filter), params)
    return [(str(r["sgg_cd"]), int(r["ym"])) for r in rows]


def _load_checkpoint(conn) -> set[str]:
    from batch.db import query_one

    row = query_one(
        conn,
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, CHECKPOINT_CODE],
    )
    return set(json.loads(row["name"])) if row and row["name"] else set()


def _save_checkpoint(conn, completed: set[str]) -> None:
    conn.cursor().execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [
            CHECKPOINT_GROUP,
            CHECKPOINT_CODE,
            json.dumps(sorted(completed)),
            str(len(completed)),
        ],
    )
    conn.commit()


def _apply_rows(conn, rows: list[tuple], dry_run: bool) -> int:
    """고유키로 맞춘 비어 있는 행 수(dry-run) 또는 채운 행 수 — 고유 행(id) 기준.

    API 응답에 같은 고유키 거래가 두 번 실리는 경우가 있어(같은 날·층·금액 동일 거래)
    조인 결과 건수가 아니라 고유 id 수로 센다. UPDATE 는 한 행을 한 번만 바꾼다.
    """
    from psycopg2.extras import execute_values

    if not rows:
        return 0
    returned = execute_values(
        conn.cursor(),
        _DRY_RUN_SQL if dry_run else _UPDATE_SQL,
        rows,
        page_size=1000,
        fetch=True,
    )
    return len({row[0] for row in returned})


def backfill_dealing_gbn(
    conn,
    logger,
    *,
    from_ym: int,
    to_ym: int,
    sido: list[str],
    max_calls: int,
    dry_run: bool,
) -> dict:
    """대상 쌍을 최근 월부터 처리한다. 반환: 집계 dict."""
    from batch.config import DATA_GO_KR_RATE, TRADE_URL
    from batch.region_codes import (
        api_query_codes,
        load_aliases,
        load_api_query_codes,
        load_emd_names,
    )
    from batch.trade.backfill_trades import _call_api_secondary
    from batch.trade.collect_trades import TRADE_COL_MAP, _parse_xml

    aliases = load_aliases(conn)
    emd_names = load_emd_names(conn)
    query_map = load_api_query_codes(conn)
    targets = _load_targets(conn, from_ym, to_ym, sido)
    completed = _load_checkpoint(conn)
    remaining = [(s, ym) for s, ym in targets if pair_key(s, ym) not in completed]
    logger.info(
        f"대상 쌍 {len(targets)} (기간 {from_ym}~{to_ym}, 시도 {sido or '전국'}), "
        f"체크포인트 완료 {len(completed)}, 남은 {len(remaining)}, 이번 최대 {max_calls}콜"
        + (" [dry-run]" if dry_run else "")
    )

    stats = {
        "pairs": 0,
        "calls": 0,
        "api_rows": 0,
        "with_value": 0,
        "filled": 0,
        "empty_responses": 0,
    }
    for sgg, ym in remaining:
        if stats["calls"] >= max_calls:
            logger.info(
                f"호출 한도 도달 ({stats['calls']}콜) — 다음 실행에서 이어서 처리"
            )
            break
        # 개편 지역은 내부 구코드로 조회하면 0건이라 API 조회 코드로 부른다(ADR-013 부기).
        # 병합 코드는 다른 구의 행도 섞여 오지만 고유키(정규화된 sgg_cd)로만 맞추므로 무해하다.
        api_rows = []
        for query_code in api_query_codes([sgg], query_map):
            xml = _call_api_secondary(TRADE_URL, query_code, str(ym))
            stats["calls"] += 1
            time.sleep(DATA_GO_KR_RATE)
            api_rows.extend(_parse_xml(xml, TRADE_COL_MAP))
        if not api_rows:
            # 응답 실패·빈 응답은 완료로 남기지 않는다(다음 실행에서 재시도).
            stats["empty_responses"] += 1
            logger.warning(f"  {sgg} {ym}: 응답 없음/실패 — 체크포인트 미기록")
            continue
        rows = [r for a in api_rows if (r := update_row(a, aliases, emd_names))]
        filled = _apply_rows(conn, rows, dry_run)
        stats["pairs"] += 1
        stats["api_rows"] += len(api_rows)
        stats["with_value"] += len(rows)
        stats["filled"] += filled
        logger.info(
            f"  {sgg} {ym}: API {len(api_rows)}행, 값 있음 {len(rows)}, "
            f"{'매칭' if dry_run else '채움'} {filled}"
        )
        if dry_run:
            continue
        completed.add(pair_key(sgg, ym))
        if stats["pairs"] % CHECKPOINT_SAVE_EVERY == 0:
            _save_checkpoint(conn, completed)  # 커밋 포함

    if dry_run:
        conn.rollback()
    else:
        _save_checkpoint(conn, completed)
    logger.info(f"완료: {stats}")
    return stats


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description="매매 거래유형(dealing_gbn) 백필")
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="조회·매칭만, 쓰기·체크포인트 없음"
    )
    mode.add_argument("--apply", action="store_true")
    p.add_argument(
        "--sido",
        default="",
        help="시도 코드 두 자리, 쉼표 구분 (예: 11,28,41). 생략 시 전국",
    )
    p.add_argument("--from-ym", type=int, default=DEALING_GBN_FIRST_YM)
    p.add_argument("--to-ym", type=int, default=None, help="기본: 지난달")
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    args = p.parse_args()

    import psycopg2

    from batch.logger import setup_logger

    from_ym = max(args.from_ym, DEALING_GBN_FIRST_YM)
    to_ym = args.to_ym or default_to_ym(date.today())
    logger = setup_logger(f"backfill_dealing_gbn_{args.target}")
    conn = psycopg2.connect(_db_url(args.target))
    try:
        backfill_dealing_gbn(
            conn,
            logger,
            from_ym=from_ym,
            to_ym=to_ym,
            sido=parse_sido(args.sido),
            max_calls=args.max_calls,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
