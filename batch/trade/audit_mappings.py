"""거래 매핑의 물리 정합성을 감사한다 — 판정만 하고 고치지 않는다.

배경
  trade_apt_mapping 은 이름 매칭으로 만들어지는데, 이후 apartments.bld_nm 이
  K-APT 적재로 갱신되면(ingest_full_kapt / register_new_apartments 의 bld_nm
  upsert) 대상이 조용히 어긋난다. 2026-08 감사에서 실적 있는 매핑 39,231건 중
  5,460건이 물리적으로 성립하지 않았다 — 산내마을1단지행복주택의 전월세
  4,043건이 산내마을8단지월드메르디앙에 붙어 있는 식이었다.

  그때는 사후에 발견해 대량으로 고쳤다. 이 모듈은 같은 일이 다시 쌓이지 않게
  "새로 만들어진 매핑"을 배치마다 검사한다.

원칙
  자동으로 고치지 않는다. 판정 기준(mapping_checks)이 완벽하지 않아 — 보정
  전에는 단독 지표 판정의 17%가 오탐이었다 — 배치가 무단으로 매핑을 바꾸면
  정상 거래가 엉뚱한 곳으로 가거나 사라질 수 있다. 위반을 로그와 배치 리포트에
  남기고, 교정은 scripts/rematch_bad_mappings.py 로 사람이 검토해 수행한다.

비용
  전체 감사는 trade_history 317만 + rent_history 659만 행을 집계해 2분 이상
  걸린다. 정기 배치에는 신규 apt_seq 만 넘겨 쓴다.

사용
  from batch.trade.audit_mappings import audit
  violations = audit(conn, logger, apt_seqs=new_seqs)

  python -m batch.trade.audit_mappings --limit 500        # 임의 표본
  python -m batch.trade.audit_mappings --pnu-file <목록>   # 특정 PNU 의 매핑
"""

from __future__ import annotations

import argparse

from batch.db import get_connection, query_all
from batch.trade.deal_stats import build_deal_stats_sql
from batch.logger import setup_logger
from batch.trade.mapping_checks import check_mapping, mismatch_confirmed

def _as_deal(row: dict) -> dict:
    return {
        "apt_nm": row["apt_nm"],
        "max_floor": row["max_floor"],
        "min_deal_year": row["min_deal_year"],
        "median_build_year": row["median_build_year"],
        "areas": row["areas"],
        # 지번 대조 근거 (mapping_checks.jibun_points_elsewhere)
        "jibun_pnus": row.get("jibun_pnus"),
        "jibun_owner_pnus": row.get("jibun_owner_pnus"),
    }


def _as_apt(row: dict) -> dict:
    return {
        "pnu": row["pnu"],
        "bld_nm": row["bld_nm"],
        "max_floor": row["apt_max_floor"],
        "use_apr_day": row["use_apr_day"],
        "areas": row["apt_areas"],
    }


def audit(conn, logger, apt_seqs: list[str] | None = None,
          pnus: list[str] | None = None) -> list[dict]:
    """물리적으로 성립하지 않는 매핑을 찾는다. 데이터는 바꾸지 않는다.

    apt_seqs / pnus 를 모두 생략하면 전체를 감사한다(느리다 — 모듈 주석 참조).
    """
    params = {}
    if apt_seqs:
        params["seqs"] = list(apt_seqs)
    if pnus:
        params["pnus"] = list(pnus)
    rows = query_all(
        conn,
        build_deal_stats_sql(by_seqs="seqs" in params, by_pnus="pnus" in params),
        params or None,
    )

    violations = []
    for r in rows:
        signals = check_mapping(_as_deal(r), _as_apt(r))
        if not mismatch_confirmed(signals):
            continue
        violations.append({
            "apt_seq": r["apt_seq"], "apt_nm": r["apt_nm"], "pnu": r["pnu"],
            "bld_nm": r["bld_nm"], "match_method": r["match_method"],
            "trades": r["trades"], "rents": r["rents"],
            "reasons": [s.detail for s in signals],
        })

    if violations:
        logger.warning(
            f"매핑 정합성 위반 {len(violations)}건 / 검사 {len(rows)}건 — "
            f"교정은 scripts/rematch_bad_mappings.py 로 검토 후 수행"
        )
        for v in sorted(violations, key=lambda x: -(x["trades"] + x["rents"]))[:10]:
            logger.warning(
                f"  {v['apt_nm']} → {v['bld_nm']} "
                f"(매매 {v['trades']}, 전월세 {v['rents']}) [{v['match_method']}] "
                f"{', '.join(v['reasons'])}"
            )
    else:
        logger.info(f"매핑 정합성 검사 {len(rows)}건 — 위반 없음")

    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pnu-file", default="", help="개행 구분 PNU 목록 — 해당 매핑만 감사")
    ap.add_argument("--limit", type=int, default=0,
                    help="apt_seq 순 표본 수 (0=전체, 전체는 2분 이상)")
    args = ap.parse_args()

    logger = setup_logger("audit_mappings")
    conn = get_connection()
    try:
        pnus = None
        if args.pnu_file:
            from pathlib import Path
            pnus = [ln.strip() for ln in Path(args.pnu_file).read_text().splitlines()
                    if ln.strip()]

        seqs = None
        if args.limit > 0:
            seqs = [r["apt_seq"] for r in query_all(
                conn, "SELECT apt_seq FROM trade_apt_mapping ORDER BY apt_seq LIMIT %s",
                [args.limit])]

        violations = audit(conn, logger, apt_seqs=seqs, pnus=pnus)
        print(f"위반 {len(violations)}건")
        for v in violations[:20]:
            print(f"  {v['apt_nm'][:26]:28s} → {v['bld_nm'][:24]:26s} "
                  f"{', '.join(v['reasons'])}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
