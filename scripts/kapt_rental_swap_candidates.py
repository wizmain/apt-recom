"""K-APT 임대 레코드가 실제 PNU 를 차지하고 분양 레코드가 더미로 밀린 단지의 검수 목록.

읽기 전용 — 데이터를 바꾸지 않는다. 설계: docs/adr/014-kapt-sale-rental-pnu-contention.md

배경
  `apt_kapt_info` 는 PK 가 pnu 라 PNU 당 K-APT 레코드 1건만 붙는다. 분양·임대 혼합 단지는
  K-APT 단지코드가 따로 있는데, 임대 쪽이 실제 PNU 를 먼저 차지하면 분양 쪽은
  `KAPT_<단지코드>` 더미 PNU 로 남는다. 그 결과 sale_type·세대수·주택형·관리비가 임대 기준이
  되고, 넛지 모집단의 임대전용 제외 가드가 단지를 통째로 뺀다 (2026-09-20 발견).

짝짓기
  더미(sale_type 분양·혼합) ↔ 실제 PNU 의 임대 레코드를 **주소**로 잇는다. 단지코드 접두는
  쓰지 않는다 — 이웃 단지가 같은 접두를 공유해 과매칭된다(837 PNU·2,474쌍, 2026-09-20 실측).
    addr_road   도로명주소 일치
    addr_lot    시군구·동·본번 일치 (부번은 다를 수 있다 — 옥수삼성 250 / 250-5)
  검증 신호(짝을 만들지는 않고 신뢰도만 올린다)
    name        이름 핵심부 포함 관계 (`신당남산타운(분양)` ↔ `신당남산타운임대`)
    area        그 PNU 의 실거래 면적이 **분양 레코드의 주택형**과 맞는 비율
                (mapping_checks.area_match_ratio — 매핑 감사와 같은 판정 기준)

신뢰도
  HIGH    주소 일치 + 이름 관계 + 면적 일치율 >= AREA_MATCH_MIN_RATIO + 1:1 (PNU 당 후보 1건)
  MEDIUM  주소 일치이나 이름이 다르거나, 면적 근거가 없거나(거래·주택형 부재), 후보가 여럿
  LOW     주소 일치인데 면적이 어긋남 — 다른 단지일 가능성. 교체 대상 아님

  이름 관계가 HIGH 의 필수 조건인 이유(2026-09-20 dry-run 실측): 주소와 면적만 맞는 16건이 전부
  **이웃한 다른 단지**였다 — `하남주공1단지`(임대) ↔ `하남주공2단지`(분양), `보라1단지` ↔ `보라2단지`.
  같은 모필지를 쓰는 주공 단지들이라 주소가 겹치고 거래 면적도 맞는다. 이걸 교체하면 1단지 PNU 가
  2단지 레코드로 바뀌고 세대수가 두 단지의 합이 된다.

사용
  .venv/bin/python -m scripts.kapt_rental_swap_candidates
  .venv/bin/python -m scripts.kapt_rental_swap_candidates --out reports/kapt_swap_candidates.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

from batch.db import get_connection, query_all
from batch.kapt.pnu_contention import (
    DUMMY_PNU_PREFIX,
    RENTAL_SALE_TYPE,
    names_related,
)
from batch.logger import setup_logger
from batch.trade.mapping_checks import AREA_MATCH_MIN_RATIO, area_match_ratio

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
# 더미 중 교체 후보가 될 수 있는 분양형태. '임대'·'사택 및 관사 등'·미상은 대상이 아니다.
SWAP_IN_SALE_TYPES = ("분양", "혼합")

# 세대수 합산 여부 (combine_households 컬럼). 교체 여부와 별개다.
#   yes     같은 단지의 임대동 → 합산한다
#   no      이웃한 다른 단지 → 합산하지 않는다
#   review  이름이 달라 자동 판정이 안 되고 사람의 판정도 아직 없다 → 합산하지 않는다
# 이름이 이어지면 자동으로 yes. 이름이 다르면 같은 단지일 수도(돈암한신한진 ↔ 동소문한진임대),
# 이웃 단지일 수도(군자주공14단지 ↔ 안산군자13단지) 있어 DECISIONS_FILE 의 사람 판정을 따른다.
COMBINE_YES = "yes"
COMBINE_NO = "no"
COMBINE_REVIEW = "review"

# 사람이 내린 합산 판정 — (pnu, rental_kapt_code) → yes/no + 근거. **추적되는 파일**이다.
# 검수 목록 CSV 는 매번 다시 생성되고 *.csv 는 gitignore 대상이라 판정을 거기에 둘 수 없다.
DECISIONS_FILE = Path(__file__).resolve().parent / "kapt_swap_decisions.yaml"
BASIS_AUTO_NAME = "auto:name"
BASIS_DECISION = "decision"

_LOT_RE = re.compile(r"^\d+(?:-\d+)?$")

DUMMY_SQL = f"""
SELECT k.pnu, k.kapt_code, k.kapt_name, k.sale_type, k.ho_cnt, k.jibun_addr, k.road_addr
FROM apt_kapt_info k
WHERE k.pnu LIKE '{DUMMY_PNU_PREFIX}%%' AND k.sale_type = ANY(%s)
"""

RENTAL_SQL = f"""
SELECT k.pnu, k.kapt_code, k.kapt_name, k.ho_cnt, k.jibun_addr, k.road_addr,
       a.bld_nm, a.total_hhld_cnt
FROM apt_kapt_info k
JOIN apartments a ON a.pnu = k.pnu
WHERE k.sale_type = %s AND k.pnu NOT LIKE '{DUMMY_PNU_PREFIX}%%'
"""

AREA_TYPES_SQL = "SELECT pnu, exclusive_area FROM apt_area_type WHERE pnu = ANY(%s)"

TRADE_AREAS_SQL = """
SELECT m.pnu, ROUND(t.exclu_use_ar::numeric, 2) AS area, COUNT(*) AS n
FROM trade_apt_mapping m
JOIN trade_history t ON t.apt_seq = m.apt_seq
WHERE m.pnu = ANY(%s) AND t.deal_amount > 0 AND t.exclu_use_ar > 0
GROUP BY 1, 2
"""


def lot_key(jibun_addr: str | None) -> tuple[str, str] | None:
    """지번주소 → (지역+동, 본번). `서울특별시 중구 신당동 844 신당남산타운` → ('서울특별시 중구 신당동', '844')."""
    tokens = (jibun_addr or "").split()
    for i, token in enumerate(tokens):
        if _LOT_RE.match(token) and i > 0:
            return " ".join(tokens[:i]), token.split("-")[0]
    return None


def road_key(road_addr: str | None) -> str | None:
    return " ".join((road_addr or "").split()) or None


def load_decisions(path: Path = DECISIONS_FILE) -> dict[tuple[str, str], str]:
    """사람의 합산 판정을 읽는다. yes/no 가 아닌 값이 있으면 중단한다 — 오타가 조용히 review 로
    떨어지면 판정을 내렸는데도 반영되지 않는다."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    decisions: dict[tuple[str, str], str] = {}
    for row in data.get("decisions") or []:
        raw = row.get("combine_households")
        # YAML 은 따옴표 없는 yes/no 를 불리언으로 읽는다 — 손으로 고치는 파일이라 둘 다 받는다.
        if isinstance(raw, bool):
            value = COMBINE_YES if raw else COMBINE_NO
        else:
            value = str(raw or "").strip().lower()
        if value not in (COMBINE_YES, COMBINE_NO):
            raise SystemExit(
                f"{path.name}: combine_households 는 yes/no 여야 함 — "
                f"{row.get('pnu')} 의 값 {raw!r}"
            )
        key = (str(row["pnu"]).strip(), str(row["rental_kapt_code"]).strip())
        decisions[key] = value
    return decisions


def resolve_combine(names_are_related: bool, decision: str | None) -> tuple[str, str]:
    """(combine_households, 근거). 사람의 판정이 자동 판정보다 우선한다."""
    if decision is not None:
        return decision, BASIS_DECISION
    if names_are_related:
        return COMBINE_YES, BASIS_AUTO_NAME
    return COMBINE_REVIEW, ""


def classify(
    addr_matched: bool,
    ratio: float | None,
    candidates_on_pnu: int,
    name_related: bool,
) -> str:
    if not addr_matched:
        return "NONE"
    if ratio is not None and ratio < AREA_MATCH_MIN_RATIO:
        return "LOW"
    if ratio is not None and candidates_on_pnu == 1 and name_related:
        return "HIGH"
    return "MEDIUM"


def build_candidates(conn) -> list[dict]:
    dummies = query_all(conn, DUMMY_SQL, [list(SWAP_IN_SALE_TYPES)])
    rentals = query_all(conn, RENTAL_SQL, [RENTAL_SALE_TYPE])

    by_road: dict[str, list[dict]] = defaultdict(list)
    by_lot: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rentals:
        if (rk := road_key(r["road_addr"])) is not None:
            by_road[rk].append(r)
        if (lk := lot_key(r["jibun_addr"])) is not None:
            by_lot[lk].append(r)

    pairs: list[tuple[dict, dict, list[str]]] = []
    for d in dummies:
        matched: dict[str, tuple[dict, list[str]]] = {}
        for r in by_road.get(road_key(d["road_addr"]) or "", []):
            matched.setdefault(r["pnu"], (r, []))[1].append("addr_road")
        for r in by_lot.get(lot_key(d["jibun_addr"]) or ("", ""), []):
            matched.setdefault(r["pnu"], (r, []))[1].append("addr_lot")
        for r, signals in matched.values():
            pairs.append((d, r, signals))

    if not pairs:
        return []

    real_pnus = sorted({r["pnu"] for _, r, _ in pairs})
    dummy_pnus = sorted({d["pnu"] for d, _, _ in pairs})

    dummy_types: dict[str, list[float]] = defaultdict(list)
    for row in query_all(conn, AREA_TYPES_SQL, [dummy_pnus]):
        dummy_types[row["pnu"]].append(float(row["exclusive_area"]))

    trade_areas: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for row in query_all(conn, TRADE_AREAS_SQL, [real_pnus]):
        trade_areas[row["pnu"]].append((float(row["area"]), int(row["n"])))

    per_pnu = Counter(r["pnu"] for _, r, _ in pairs)
    decisions = load_decisions()

    out = []
    for d, r, signals in pairs:
        deals = trade_areas.get(r["pnu"], [])
        ratio = area_match_ratio(deals, dummy_types.get(d["pnu"]))
        related = names_related(d["kapt_name"], r["kapt_name"]) or names_related(
            d["kapt_name"], r["bld_nm"]
        )
        if related:
            signals = [*signals, "name"]
        combine, combine_basis = resolve_combine(
            names_related(d["kapt_name"], r["kapt_name"]),
            decisions.get((r["pnu"], r["kapt_code"])),
        )
        out.append(
            {
                "confidence": classify(True, ratio, per_pnu[r["pnu"]], related),
                "pnu": r["pnu"],
                "bld_nm": r["bld_nm"],
                "rental_kapt_code": r["kapt_code"],
                "rental_kapt_name": r["kapt_name"],
                "rental_hhld": r["ho_cnt"],
                "current_total_hhld_cnt": r["total_hhld_cnt"],
                "sale_kapt_code": d["kapt_code"],
                "sale_kapt_name": d["kapt_name"],
                "sale_type": d["sale_type"],
                "sale_hhld": d["ho_cnt"],
                "signals": "+".join(sorted(set(signals))),
                "combine_households": combine,
                "combine_basis": combine_basis,
                "sale_trades": sum(n for _, n in deals),
                "area_match_ratio": "" if ratio is None else f"{ratio:.2f}",
                "candidates_on_pnu": per_pnu[r["pnu"]],
            }
        )
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda x: (order[x["confidence"]], -x["sale_trades"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--out",
        type=Path,
        default=REPORT_DIR / f"kapt_swap_candidates_{date.today():%Y%m%d}.csv",
    )
    args = ap.parse_args()

    logger = setup_logger("kapt_rental_swap_candidates")
    conn = get_connection()
    try:
        rows = build_candidates(conn)
    finally:
        conn.close()

    if not rows:
        logger.info("후보 없음")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_conf = Counter(r["confidence"] for r in rows)
    pnus = {c: len({r["pnu"] for r in rows if r["confidence"] == c}) for c in by_conf}
    logger.info(f"후보 {len(rows)}쌍 → {args.out}")
    for conf in ("HIGH", "MEDIUM", "LOW"):
        if conf in by_conf:
            logger.info(f"  {conf:6s} {by_conf[conf]:4d}쌍 / {pnus[conf]:4d} PNU")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
