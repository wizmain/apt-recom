"""신 행정구역 코드로 유입된 미정규화 행 일괄 삭제 (재수집 전제).

발동 배경(2026-08-29 실측): 국토부 RTMS 응답 ``sggCd`` 가 신코드(광주·전남
12xxx, 인천 28275/28290)를 반환하기 시작했는데 적재 경계에 정규화가 없어
trade/rent 2,706건이 원코드 그대로 들어왔고, ``apt_seq``("{sgg}_{apt_nm}")를
타고 trade_apt_mapping·apartments(TRADE_* placeholder + 신코드 PNU 등록)까지
오염이 확산됐다. ADR-013(내부 표준 = 구코드) 위반 상태.

리네임(신→구코드 UPDATE)이 아니라 **삭제 후 재수집**을 택한 이유:
apt_seq·PNU·mapping PK 에 코드가 배어 있어 리네임은 기존 구코드 행과의
중복 병합 로직이 필요하다. 거래는 재수집 가능한 외부 데이터이므로
(CLAUDE.md 외부 데이터 연동 원칙), 정규화가 들어간 적재 경로
(``batch.trade.load_trades``, 같은 PR)로 다시 태우는 쪽이 경로가 하나다.

재수집 경위: ``batch.run --type trade`` 의 수집 월 창은
``MAX(deal_year*100+deal_month)`` 부터 현재월까지다. 삭제 대상의 거래 연월이
이 창을 벗어나면 재수집되지 않고 유실되므로 실행 전에 검사해 abort 한다.

대상 선정은 데이터 주도: 시군구 레지스트리(common_code sigungu)에 없으면서
별칭으로 구코드 환원이 **가능한** 코드만 지운다. 환원 불가능한 미지 코드는
삭제해도 같은 원코드로 재적재될 뿐이므로 보고만 하고 남긴다
(audit_unknown_codes 감시 대상).

사용:
    python -m batch.purge_unnormalized_region_rows --target local --dry-run
    python -m batch.purge_unnormalized_region_rows --target both --dry-run
    python -m batch.purge_unnormalized_region_rows --target both --confirm  # 실제 삭제
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.logger import setup_logger
from batch.region_codes import load_aliases, normalize_sigungu_code

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# 오염 행이 pnu 로 참조되는 파생 테이블 — 삭제 후 배치가 재계산한다.
PNU_DERIVED_TABLES = (
    "apt_facility_summary",
    "apt_price_score",
    "apt_safety_score",
    "school_zones",
)


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
    else:
        raise ValueError(f"unknown target: {target}")
    if not url:
        raise ValueError(f"{target} DB URL 미설정")
    return url


def _find_purgeable_codes(conn) -> tuple[list[str], list[str]]:
    """(환원 가능해 삭제할 코드, 환원 불가라 보고만 할 코드)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT sgg_cd FROM (
            SELECT sgg_cd FROM trade_history
            UNION SELECT sgg_cd FROM rent_history
            UNION SELECT sgg_cd FROM trade_apt_mapping
            UNION SELECT LEFT(sigungu_code, 5) FROM apartments
        ) s
        WHERE sgg_cd IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM common_code c
            WHERE c.group_id = 'sigungu' AND c.code = s.sgg_cd
          )
        """
    )
    unknown = [r[0] for r in cur.fetchall()]

    aliases = load_aliases(conn)
    purgeable = [c for c in unknown if normalize_sigungu_code(c, aliases) != c]
    unresolved = [c for c in unknown if c not in purgeable]
    return sorted(purgeable), sorted(unresolved)


def _verify_recollect_window(cur, codes: list[str]) -> tuple[int | None, int | None]:
    """(삭제 대상 최소 거래 ym, 잔존 데이터 기준 재수집 시작 ym)."""
    cur.execute(
        "SELECT MIN(deal_year * 100 + deal_month) FROM ("
        "  SELECT deal_year, deal_month FROM trade_history WHERE sgg_cd = ANY(%s)"
        "  UNION ALL"
        "  SELECT deal_year, deal_month FROM rent_history WHERE sgg_cd = ANY(%s)"
        ") d",
        [codes, codes],
    )
    doomed_min = cur.fetchone()[0]
    cur.execute(
        "SELECT MAX(deal_year * 100 + deal_month) FROM trade_history "
        "WHERE NOT (sgg_cd = ANY(%s))",
        [codes],
    )
    recollect_start = cur.fetchone()[0]
    return doomed_min, recollect_start


def _collect_counts(cur, codes: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("trade_history", "rent_history", "trade_apt_mapping"):
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE sgg_cd = ANY(%s)", [codes])
        counts[table] = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM apartments WHERE LEFT(sigungu_code, 5) = ANY(%s)",
        [codes],
    )
    counts["apartments"] = cur.fetchone()[0]
    for table in PNU_DERIVED_TABLES:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} WHERE pnu IN ("
            "  SELECT pnu FROM apartments WHERE LEFT(sigungu_code, 5) = ANY(%s)"
            ")",
            [codes],
        )
        counts[table] = cur.fetchone()[0]
    return counts


def _process_target(target: str, args, logger) -> None:
    url = _db_url(target)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        purgeable, unresolved = _find_purgeable_codes(conn)
        if unresolved:
            logger.warning(
                f"  [{target}] 환원 불가 미지 코드 {unresolved} — 삭제하지 않음"
                " (audit_unknown_codes 감시 대상, 별칭 확보 후 재실행)"
            )
        if not purgeable:
            logger.info(f"  [{target}] 삭제 대상 코드 없음 — 종료")
            return
        logger.info(f"  [{target}] 삭제 대상 코드: {purgeable}")

        doomed_min, recollect_start = _verify_recollect_window(cur, purgeable)
        if doomed_min and recollect_start and doomed_min < recollect_start:
            logger.error(
                f"  [{target}] 삭제 대상 최소 거래월 {doomed_min} 이 재수집 시작월 "
                f"{recollect_start} 이전 — 삭제하면 재수집되지 않는다. abort"
            )
            return
        logger.info(
            f"  [{target}] 재수집 창 검증 통과: 대상 최소월 {doomed_min} ≥ "
            f"재수집 시작월 {recollect_start}"
        )

        counts = _collect_counts(cur, purgeable)
        for table, n in counts.items():
            logger.info(f"  [{target}] {table}: {n:,}건")

        if args.dry_run:
            logger.info(f"  [{target}] DRY-RUN 종료 — 실제 삭제 없음")
            return

        # 파생 테이블 → 본체 순으로 삭제 (pnu 부분집합이 apartments 에 의존)
        total = 0
        for table in PNU_DERIVED_TABLES:
            cur.execute(
                f"DELETE FROM {table} WHERE pnu IN ("
                "  SELECT pnu FROM apartments WHERE LEFT(sigungu_code, 5) = ANY(%s)"
                ")",
                [purgeable],
            )
            total += cur.rowcount
            logger.info(f"  [{target}] {table}: {cur.rowcount:,}건 삭제")
        cur.execute(
            "DELETE FROM apartments WHERE LEFT(sigungu_code, 5) = ANY(%s)",
            [purgeable],
        )
        total += cur.rowcount
        logger.info(f"  [{target}] apartments: {cur.rowcount:,}건 삭제")
        for table in ("trade_apt_mapping", "trade_history", "rent_history"):
            cur.execute(f"DELETE FROM {table} WHERE sgg_cd = ANY(%s)", [purgeable])
            total += cur.rowcount
            logger.info(f"  [{target}] {table}: {cur.rowcount:,}건 삭제")
        conn.commit()
        logger.info(
            f"  [{target}] 합계 {total:,}건 삭제 완료 — 다음 trade 배치가"
            " 정규화 경로로 재수집한다"
        )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="신 행정구역 코드로 유입된 미정규화 행 삭제 (재수집 전제)"
    )
    parser.add_argument(
        "--target", choices=["local", "railway", "both"], default="local"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 삭제 없이 대상 코드·건수만 출력",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="실제 삭제 실행에 필수 (dry-run 이 아니면 항상 요구)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        parser.error("실제 삭제는 --confirm 이 필요합니다 (검토는 --dry-run)")

    logger = setup_logger("purge_unnormalized_region_rows")
    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for t in targets:
        _process_target(t, args, logger)


if __name__ == "__main__":
    main()
