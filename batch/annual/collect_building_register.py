"""건축물대장 표제부 → 아파트 승강기/주차 집계 (라이프점수 Phase 2-1).

동(棟)별 표제부(getBrTitleInfo)를 PNU 지번으로 조회해 단지 단위로 합산한다.
PoC 실측(2026-07-04): 층화 표본 30/30 히트 — PNU 파라미터는 원값 전달
(platGbCd=pnu[10], int 변환 금지 — 변환 시 0/30).

합산 규칙:
- 주용도(mainPurpsCdNm)에 '아파트' 또는 '공동주택' 이 포함된 동만 합산
  (관리동/상가 승강기 혼입 방지). 해당 동이 하나도 없으면 전체 동 합산
  fallback (발동 시 로그 — 구식 대장의 용도 표기 편차 대응).
- elevator_count = Σ(rideUseElvtCnt + emgenUseElvtCnt)
- parking_total_count = Σ(indrAutoUtcnt + oudrAutoUtcnt + indrMechUtcnt + oudrMechUtcnt)
- parking_per_hhld = parking_total / max(register_hhld_cnt, DB total_hhld_cnt)
  (대장 세대합이 0/결측이면 DB 세대수 사용 — 분모 0 방지)

체크포인트: common_code('building_register_checkpoint', 'last_pnu') — pnu 오름차순
진행, --max-calls 도달 시 중단 후 재실행하면 이어서 진행 (rebuild_area_info 패턴).

사용법:
  .venv/bin/python -m batch.annual.collect_building_register --max-calls 100   # 표본
  .venv/bin/python -m batch.annual.collect_building_register                   # 전수(재개형)
  .venv/bin/python -m batch.annual.collect_building_register --missing-only    # 미적재만 보충
  .venv/bin/python -m batch.annual.collect_building_register --reset           # 체크포인트 초기화

일일 호출 한도(HTTP 429, 관측상 ~10,000/일): 도달 시 조기 중단되며, 미적재분은
자정(한도 리셋) 이후 --missing-only 로 보충한다.
"""

import argparse
import time
import xml.etree.ElementTree as ET

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import get_connection
from batch.logger import setup_logger

TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
CHECKPOINT_GROUP = "building_register_checkpoint"
RESIDENTIAL_PURPS_KEYWORDS = ("아파트", "공동주택")
PARKING_FIELDS = ("indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt")
MAX_RETRIES = 2
COMMIT_EVERY = 200  # 체크포인트/upsert 커밋 주기


def _params_from_pnu(pnu: str) -> dict:
    """PNU 19자리 → 표제부 API 파라미터 (원값 전달 관례 — 모듈 docstring 참조)."""
    return {
        "serviceKey": DATA_GO_KR_API_KEY,
        "sigunguCd": pnu[:5],
        "bjdongCd": pnu[5:10],
        "platGbCd": pnu[10],
        "bun": pnu[11:15],
        "ji": pnu[15:19],
        "numOfRows": "100",
        "pageNo": "1",
    }


class RateLimitExceeded(RuntimeError):
    """일일 호출 한도(HTTP 429) — 상위 루프가 조기 중단하도록 구분한다."""


def _fetch_title_items(pnu: str, logger) -> list[dict] | None:
    """표제부 동 목록 조회. 네트워크/파싱 실패 시 None (재시도 후).

    HTTP 429 는 재시도해도 소용없는 일일 한도이므로 RateLimitExceeded 를 던진다
    (2026-07-04 전수 수집에서 한도 도달 후 2만여 건이 무의미하게 skip 된 사고 재발 방지).
    """
    fields = (
        "bldNm",
        "mainPurpsCdNm",
        "hhldCnt",
        "rideUseElvtCnt",
        "emgenUseElvtCnt",
        *PARKING_FIELDS,
    )
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(TITLE_URL, params=_params_from_pnu(pnu), timeout=15)
            time.sleep(DATA_GO_KR_RATE)
            if resp.status_code == 429:
                raise RateLimitExceeded(f"{pnu}: HTTP 429 (일일 한도)")
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}")
            root = ET.fromstring(resp.text)
            code = root.findtext(".//resultCode")
            if code not in ("00",):
                raise RuntimeError(
                    f"resultCode {code}: {root.findtext('.//resultMsg')}"
                )
            return [
                {f: (it.findtext(f) or "") for f in fields}
                for it in root.findall(".//item")
            ]
        except RateLimitExceeded:
            raise  # 한도 도달 — 재시도/skip 대상 아님, 상위에서 조기 중단
        except Exception as e:  # noqa: BLE001 — 재시도 후 상위에서 skip 처리
            if attempt < MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            logger.warning(f"  {pnu}: 조회 실패 — {e}")
            return None
    return None


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _aggregate(items: list[dict], logger, pnu: str) -> dict | None:
    """동 목록 → 단지 합산. 동이 없으면 None."""
    if not items:
        return None
    residential = [
        it
        for it in items
        if any(k in it["mainPurpsCdNm"] for k in RESIDENTIAL_PURPS_KEYWORDS)
    ]
    if not residential:
        # fallback: 용도 표기 편차(구식 대장) — 전체 동 합산으로 대체
        logger.debug(f"  {pnu}: 주거용도 동 없음 → 전체 {len(items)}동 합산 fallback")
        residential = items

    elevator = sum(
        _to_int(it["rideUseElvtCnt"]) + _to_int(it["emgenUseElvtCnt"])
        for it in residential
    )
    parking_total = sum(
        sum(_to_int(it[f]) for f in PARKING_FIELDS) for it in residential
    )
    parking_indoor = sum(
        _to_int(it["indrAutoUtcnt"]) + _to_int(it["indrMechUtcnt"])
        for it in residential
    )
    hhld = sum(_to_int(it["hhldCnt"]) for it in residential)
    return {
        "elevator_count": elevator,
        "parking_total_count": parking_total,
        "parking_indoor_count": parking_indoor,
        "register_hhld_cnt": hhld,
        "register_dong_cnt": len(residential),
    }


def _load_checkpoint(cur) -> str | None:
    cur.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, "last_pnu"],
    )
    row = cur.fetchone()
    return row[0] if row else None


def _save_checkpoint(cur, pnu: str) -> None:
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, '', 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
        [CHECKPOINT_GROUP, "last_pnu", pnu],
    )


UPSERT_SQL = """
    INSERT INTO apt_building_register
        (pnu, elevator_count, parking_total_count, parking_indoor_count,
         register_hhld_cnt, register_dong_cnt, parking_per_hhld, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (pnu) DO UPDATE SET
        elevator_count = EXCLUDED.elevator_count,
        parking_total_count = EXCLUDED.parking_total_count,
        parking_indoor_count = EXCLUDED.parking_indoor_count,
        register_hhld_cnt = EXCLUDED.register_hhld_cnt,
        register_dong_cnt = EXCLUDED.register_dong_cnt,
        parking_per_hhld = EXCLUDED.parking_per_hhld,
        updated_at = NOW()
"""


def collect_building_register(
    conn, logger, max_calls: int = 0, missing_only: bool = False
) -> dict:
    """전수 수집. max_calls=0 이면 무제한.

    모드:
    - 기본: 체크포인트(pnu 오름차순) 재개형 — 최초 전수 수집용.
    - missing_only: apt_building_register 에 없는 pnu 만 대상, 체크포인트 무시.
      한도(429)로 skip 된 구간을 재수집할 때 사용 — skip 도 체크포인트를
      전진시키므로 기본 모드로는 다시 돌 수 없다 (2026-07-04 한도 사고 교훈).
    """
    cur = conn.cursor()
    params: list = []
    where = "LENGTH(a.pnu) = 19 AND a.pnu NOT LIKE 'TRADE\\_%%'"

    if missing_only:
        last_pnu = None
        where += " AND NOT EXISTS (SELECT 1 FROM apt_building_register b WHERE b.pnu = a.pnu)"
        logger.info("수집 시작 (missing-only 모드 — 미적재 pnu 만)")
    else:
        last_pnu = _load_checkpoint(cur)
        logger.info(f"수집 시작 (재개 지점: {last_pnu or '처음'})")
        if last_pnu:
            where += " AND a.pnu > %s"
            params.append(last_pnu)

    cur.execute(
        f"""SELECT a.pnu, a.total_hhld_cnt FROM apartments a
            WHERE {where} ORDER BY a.pnu""",
        params,
    )
    targets = cur.fetchall()
    logger.info(
        f"대상: {len(targets):,}건" + (f" (max_calls {max_calls})" if max_calls else "")
    )

    fetched = upserted = skipped = 0
    for pnu, db_hhld in targets:
        if max_calls and fetched >= max_calls:
            logger.info(f"max_calls {max_calls} 도달 — 중단 (재실행 시 이어서 진행)")
            break
        try:
            items = _fetch_title_items(pnu, logger)
        except RateLimitExceeded as e:
            # 일일 한도 — 이후 호출은 전부 429 이므로 즉시 중단.
            # 이 pnu 는 미처리(체크포인트 미전진) → 다음 실행에서 이어서 수집.
            logger.warning(
                f"일일 호출 한도 도달({e}) — 조기 중단. 자정 이후 재실행 필요"
            )
            break
        fetched += 1
        agg = _aggregate(items, logger, pnu) if items is not None else None
        if agg is None:
            skipped += 1
        else:
            denom = agg["register_hhld_cnt"] or (db_hhld or 0)
            ratio = round(agg["parking_total_count"] / denom, 3) if denom > 0 else None
            cur.execute(
                UPSERT_SQL,
                [
                    pnu,
                    agg["elevator_count"],
                    agg["parking_total_count"],
                    agg["parking_indoor_count"],
                    agg["register_hhld_cnt"],
                    agg["register_dong_cnt"],
                    ratio,
                ],
            )
            upserted += 1
        _save_checkpoint(cur, pnu)
        if fetched % COMMIT_EVERY == 0:
            conn.commit()
            logger.info(
                f"  진행 {fetched:,}/{len(targets):,} (적재 {upserted:,}, skip {skipped:,})"
            )

    conn.commit()
    logger.info(f"수집 완료: 호출 {fetched:,} / 적재 {upserted:,} / skip {skipped:,}")
    return {
        "fetched": fetched,
        "upserted": upserted,
        "skipped": skipped,
        "resumed_from": last_pnu,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-calls", type=int, default=0, help="최대 API 호출 수 (0=무제한)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="체크포인트 초기화 후 처음부터"
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="apt_building_register 미적재 pnu 만 재수집 (한도로 skip 된 구간 보충)",
    )
    args = parser.parse_args()

    logger = setup_logger("building_register")
    conn = get_connection()
    try:
        if args.reset:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM common_code WHERE group_id = %s", [CHECKPOINT_GROUP]
            )
            conn.commit()
            logger.info("체크포인트 초기화")
        collect_building_register(
            conn, logger, max_calls=args.max_calls, missing_only=args.missing_only
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
