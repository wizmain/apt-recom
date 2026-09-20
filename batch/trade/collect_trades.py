"""거래 데이터 증분 수집 (매매 + 전월세).

시간 상한 (2026-08-17): 수집 루프에는 예산이 있고, 초과하면 남은 시군구를 남긴 채
**정상 반환**한다. 예외를 올리거나 프로세스가 죽으면 메모리에 모아둔 수집분이 전량
날아가기 때문이다(적재는 collect 가 반환한 뒤에 일어난다). 월 단위 재수집은 적재
시점의 dedupe 로 멱등이라, 남긴 몫은 다음 런이 그대로 이어받는다.

시작 오프셋 회전: 시군구 코드는 오름차순이라 예산에 걸려 잘리는 쪽이 늘 뒤쪽
(비수도권)이다. 고정되면 그 지역만 결손이 누적되므로 런마다 시작 지점을 옮긴다.
"""

import time
import xml.etree.ElementTree as ET
import requests
from dataclasses import dataclass
from datetime import datetime

from batch.config import (
    COLLECT_BUDGET_MINUTES,
    COLLECT_FAILURE_WARN_RATIO,
    DATA_GO_KR_API_KEY,
    DATA_GO_KR_RATE,
    DATA_GO_KR_RETRIES,
    DATA_GO_KR_RETRY_BACKOFF,
    DATA_GO_KR_TIMEOUT,
    RENT_URL,
    TRADE_URL,
)
from batch.db import get_district_codes, query_one

# 회전 보폭. 소수라 시군구 수와 서로소가 되기 쉬워 전 구간을 고르게 돈다.
DISTRICT_ROTATION_STRIDE = 97


@dataclass
class CollectStats:
    """수집 한 번의 관측치 — 실패가 조용히 묻히지 않게 호출부까지 올린다."""

    attempted: int = 0
    failed: int = 0
    districts_done: int = 0
    districts_total: int = 0
    budget_exceeded: bool = False
    start_offset: int = 0

    @property
    def failure_ratio(self) -> float:
        return self.failed / self.attempted if self.attempted else 0.0


TRADE_COL_MAP = {
    "dealAmount": "dealAmount",
    "buildYear": "buildYear",
    "dealYear": "dealYear",
    "dealMonth": "dealMonth",
    "dealDay": "dealDay",
    "aptNm": "aptNm",
    "excluUseAr": "excluUseAr",
    "sggCd": "sggCd",
    "floor": "floor",
    "umdNm": "umdNm",
    "umdCd": "umdCd",
    "jibun": "jibun",
    "bonbun": "bonbun",
    "bubun": "bubun",
    "landCd": "landCd",
    "roadNm": "roadNm",
    "roadNmBonbun": "roadNmBonbun",
    "roadNmBubun": "roadNmBubun",
    "aptDong": "aptDong",
    "buyerGbn": "buyerGbn",
    "dealingGbn": "dealingGbn",
    "rgstDate": "rgstDate",
    "aptSeq": "aptSeq",
}

RENT_COL_MAP = {
    "deposit": "deposit",
    "monthlyRent": "monthlyRent",
    "excluUseAr": "excluUseAr",
    "aptNm": "aptNm",
    "floor": "floor",
    "dealYear": "dealYear",
    "dealMonth": "dealMonth",
    "dealDay": "dealDay",
    "sggCd": "sggCd",
    "umdNm": "umdNm",
    "jibun": "jibun",
    "roadnm": "roadNm",
    "roadnmbonbun": "roadNmBonbun",
    "roadnmbubun": "roadNmBubun",
    "contractType": "contractType",
    "contractTerm": "contractTerm",
    "preDeposit": "preDeposit",
    "preMonthlyRent": "preMonthlyRent",
    "useRRRight": "useRRRight",
    "aptSeq": "aptSeq",
}


def _call_api(url, lawd_cd, deal_ymd, logger, retries=DATA_GO_KR_RETRIES):
    """실패하면 None. **반드시 사유를 로그한다** — 조용한 결손 금지 (2026-08-17).

    이전에는 예외를 잡아 그냥 None 을 반환했고, 호출부는 _parse_xml(None) → [] 로
    흡수했다. 그래서 수집이 일부 시군구를 통째로 빠뜨려도 로그가 한 줄도 남지 않았고,
    성공으로 끝난 런조차 결손을 품고 있었는지 사후 확인이 불가능했다.
    """
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": "1",
        "numOfRows": "10000",
    }
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=DATA_GO_KR_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(DATA_GO_KR_RETRY_BACKOFF * (2**attempt))
    logger.warning(
        f"수집 실패 {lawd_cd}/{deal_ymd} — {retries}회 시도 후 포기: "
        f"{type(last_error).__name__}: {last_error}"
    )
    return None


def _rotate(codes, offset):
    if not codes:
        return list(codes)
    offset %= len(codes)
    return list(codes[offset:]) + list(codes[:offset])


def _rotation_offset(total, now=None):
    """런마다 수집 시작 지점을 옮긴다.

    12시간 주기(03/15 UTC)라 하루 2회를 서로 다른 지점에서 시작시켜야 하므로
    날짜뿐 아니라 오전/오후도 순번에 넣는다. DB 커서를 두지 않는 이유는 상태
    저장 없이도 결손 고착만 막으면 충분하기 때문이다 — 남긴 몫의 회수는 월
    재수집이 멱등이라 이미 보장된다.
    """
    if total <= 0:
        return 0
    now = now or datetime.now()
    half = 0 if now.hour < 12 else 1
    sequence = now.toordinal() * 2 + half
    return (sequence * DISTRICT_ROTATION_STRIDE) % total


def _parse_xml(xml_text, col_map):
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    result_code = root.findtext(".//resultCode")
    if result_code not in ("00", "000"):
        return []
    rows = []
    for item in root.findall(".//item"):
        row = {}
        for tag, col in col_map.items():
            el = item.find(tag)
            row[col] = el.text.strip() if el is not None and el.text else ""
        rows.append(row)
    return rows


def _get_collection_months(conn):
    """DB에서 마지막 수집월 조회 → 다음 월부터 현재월까지 목록 반환."""
    row = query_one(
        conn, "SELECT MAX(deal_year * 100 + deal_month) as last_ym FROM trade_history"
    )
    last_ym = row["last_ym"] if row and row["last_ym"] else 201601

    now = datetime.now()
    cur_ym = now.year * 100 + now.month

    # 마지막 수집월부터 (이미 수집된 달도 증분 체크를 위해 포함)
    months = []
    y, m = int(str(last_ym)[:4]), int(str(last_ym)[4:])
    while y * 100 + m <= cur_ym:
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def collect_trades(
    conn, logger, dry_run=False, *, budget_seconds=None, clock=time.monotonic, now=None
):
    """거래 데이터 증분 수집. (trade_rows, rent_rows, stats) 반환.

    예산을 넘기면 남은 시군구를 남긴 채 정상 반환한다 (모듈 docstring 참고).
    """
    codes = get_district_codes(conn)
    months = _get_collection_months(conn)

    offset = _rotation_offset(len(codes), now)
    codes = _rotate(codes, offset)

    budget = COLLECT_BUDGET_MINUTES * 60 if budget_seconds is None else budget_seconds
    deadline = clock() + budget
    stats = CollectStats(districts_total=len(codes) * len(months), start_offset=offset)

    logger.info(
        f"수집 대상: {len(codes)}개 시군구 x {len(months)}개월 ({months[0]}~{months[-1]}) "
        f"— 시작 오프셋 {offset}, 예산 {budget / 60:.0f}분"
    )

    trade_rows = []
    rent_rows = []

    for month in months:
        for code in codes:
            if clock() >= deadline:
                stats.budget_exceeded = True
                logger.warning(
                    f"수집 예산 {budget / 60:.0f}분 초과 — "
                    f"{stats.districts_done}/{stats.districts_total} 지점에서 중단합니다. "
                    "수집분은 그대로 적재하며, 남은 몫은 다음 런이 이어받습니다."
                )
                break

            # 매매
            xml = _call_api(TRADE_URL, code, month, logger)
            stats.attempted += 1
            stats.failed += xml is None
            trade_rows.extend(_parse_xml(xml, TRADE_COL_MAP))
            time.sleep(DATA_GO_KR_RATE)

            # 전월세
            xml = _call_api(RENT_URL, code, month, logger)
            stats.attempted += 1
            stats.failed += xml is None
            rent_rows.extend(_parse_xml(xml, RENT_COL_MAP))
            time.sleep(DATA_GO_KR_RATE)

            stats.districts_done += 1

        if stats.budget_exceeded:
            break

        logger.info(
            f"  {month}: 매매 누적 {len(trade_rows):,}건, 전월세 누적 {len(rent_rows):,}건"
        )

    logger.info(
        f"수집 완료: 매매 {len(trade_rows):,}건, 전월세 {len(rent_rows):,}건 — "
        f"호출 {stats.attempted:,}건 중 실패 {stats.failed:,}건 "
        f"({stats.failure_ratio:.1%})"
    )
    if stats.failure_ratio >= COLLECT_FAILURE_WARN_RATIO:
        logger.warning(
            f"수집 실패율 {stats.failure_ratio:.1%} — 실패 콜은 정상 콜보다 수십 배 비싸 "
            "예산 초과의 선행 지표입니다. API 상태를 확인하세요."
        )
    return trade_rows, rent_rows, stats
