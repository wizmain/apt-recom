"""소상공인 상가(상권)정보 → facilities 적재 (라이프점수 Phase 2-2).

업종 소분류별 전국 페이징 수집. 4개 subtype 매핑은 STORE_SUBTYPE_CODES
(Step 1 탐색으로 확정, 근거 주석 포함).

키: 이 API 는 SECONDARY 키만 활용신청됨 (PoC 2026-07-06 — primary 403).
403 은 활용신청 문제라 로테이션 대상이 아니므로 secondary 를 직접 사용한다.

엔드포인트 확정 (PoC 2026-07-06 실측):
- `storeListInUpjong` (`divId=indsSclsCd&key=<소분류코드>`) 사용.
  응답 header 의 description 은 "주요상권내 상가업소정보"로 되어 있으나,
  실측 결과 서울/인천/대구/경북 안동 등 전국에 분산된 업소가 반환되고
  totalCount 도 업종 규모에 부합(예: 카페 115,722건)해 사실상 전국
  데이터로 확인됨 — API 설명 문구는 레거시 네이밍으로 판단.
- numOfRows 는 1000 초과 요청해도 1000건으로 캡됨(실측: 5000 요청 시에도
  1000건 반환) — 페이지 크기 상한 1000 확정.
- totalCount 로 마지막 페이지를 계산해 종료(페이지 * 1000 >= totalCount).

upsert: facility_id = 'STORE_' + 상가업소번호(bizesId). 재수집 시 사라진
점포는 is_active=FALSE 처리 (해당 subtype 한정 — 폐업 반영). 단, --max-pages
로 표본만 수집한 경우 전국을 다 훑지 않았으므로 비활성화를 스킵한다
(전량 수집 완료 시에만 안전 — Task 2).

사용법:
  .venv/bin/python -m batch.quarterly.collect_store_facilities                # 전체
  .venv/bin/python -m batch.quarterly.collect_store_facilities --subtype cafe --max-pages 2  # 표본
"""

import argparse
import time

import psycopg2.errors
import requests

from batch.config import DATA_GO_KR_API_SECONDARY_KEY, DATA_GO_KR_RATE
from batch.db import get_connection
from batch.logger import setup_logger

STORE_API_URL = "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInUpjong"
MAX_ROWS_PER_PAGE = 1000  # PoC 실측(2026-07-06): API 상한, 초과 요청해도 캡됨
NODATA_RESULT_CODE = "03"
SUCCESS_RESULT_CODE = "00"

# 소분류 코드 확정 근거 (PoC 2026-07-06, sdsc2 middleUpjongList/smallUpjongList
# 실측 + storeListInRadius 좌표 역검증). 각 항목은 대분류/중분류 경로와
# storeListInUpjong totalCount(표본 시점 실측치)를 함께 남긴다.
STORE_SUBTYPE_CODES: dict[str, list[str]] = {
    # I2(음식) > I212(비알코올) > I21201 카페. totalCount 115,722.
    "cafe": ["I21201"],
    # R1(예술·스포츠) > R104(유원지·오락) > R10405 기타 오락장.
    # 이 taxonomy 에는 '키즈카페' 전용 소분류가 없다 — Kakao 로 확인한 실제
    # 키즈카페(꿈엔뜰키즈랜드, 색이랑아이랑 등)가 모두 이 코드로 등록되어
    # 있음을 storeListInUpjong 표본 조회로 확인. 방탈출/VR방 등 인접 실내
    # 오락업이 혼입될 수 있는 catch-all 코드라는 한계는 있음. totalCount 4,478.
    "kids_cafe": ["R10405"],
    # G2(소매) > G220(애완동물·용품 소매) > G22001 애완동물/애완용품 소매업.
    # 애견미용실 전용 소분류는 존재하지 않는다 — Kakao 로 확인한 실제
    # 애견미용실(럽포포, 포캣멍 등) 인근 좌표를 storeListInRadius 로 역검증한
    # 결과 모두 G22001 로 등록되어 있어 애완용품 소매/미용을 함께 커버함을
    # 확인. totalCount 11,186.
    "pet_shop": ["G22001"],
    # R1(예술·스포츠) > R103(스포츠 서비스) > R10307 헬스장.
    # 인접 코드 R10317(스포츠 클럽 운영업)은 전국 NODATA_ERROR(등록 0건)로
    # 확인되어 제외. totalCount 18,603.
    "fitness": ["R10307"],
}

SUBTYPE_TYPE_MAP = {
    "cafe": "living",
    "kids_cafe": "living",
    "pet_shop": "pet",
    "fitness": "culture",
}


class RateLimitExceeded(RuntimeError):
    """HTTP 429 — 이 API 는 secondary 단일 키만 사용하므로 로테이션 대상이
    아니다(활용신청 문제, PoC 2026-07-06). 발생 시 조기 중단한다."""


def _fetch_page(code: str, page: int) -> tuple[list[dict], int]:
    """소분류 코드 1페이지 조회. (items, totalCount) 반환."""
    params = {
        "serviceKey": DATA_GO_KR_API_SECONDARY_KEY,
        "type": "json",
        "divId": "indsSclsCd",
        "key": code,
        "numOfRows": str(MAX_ROWS_PER_PAGE),
        "pageNo": str(page),
    }
    resp = requests.get(STORE_API_URL, params=params, timeout=30)
    if resp.status_code == 429:
        raise RateLimitExceeded(f"{code} {page}p: HTTP 429 (일일 한도 소진)")
    resp.raise_for_status()
    data = resp.json()
    header = data.get("header", {})
    result_code = header.get("resultCode")
    if result_code == NODATA_RESULT_CODE:
        return [], 0
    if result_code != SUCCESS_RESULT_CODE:
        raise RuntimeError(
            f"{code} {page}p: resultCode {result_code} ({header.get('resultMsg')})"
        )
    body = data.get("body", {})
    return body.get("items", []), int(body.get("totalCount") or 0)


def _to_row(item: dict, facility_type: str, subtype: str) -> tuple | None:
    """API 응답 항목 → facilities upsert 파라미터. 좌표/식별자 결측은 None(skip)."""
    bizes_id = item.get("bizesId")
    lat, lon = item.get("lat"), item.get("lon")
    if not bizes_id or lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return (
        f"STORE_{bizes_id}",
        facility_type,
        subtype,
        (item.get("bizesNm") or "")[:200],
        lat_f,
        lon_f,
        (item.get("rdnmAdr") or "")[:300],
    )


UPSERT_SQL = """
    INSERT INTO facilities
        (facility_id, facility_type, facility_subtype, name, lat, lng, address, is_active, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
    ON CONFLICT (facility_id) DO UPDATE SET
        name = EXCLUDED.name,
        lat = EXCLUDED.lat,
        lng = EXCLUDED.lng,
        address = EXCLUDED.address,
        is_active = TRUE,
        updated_at = NOW()
"""


def _upsert_row(cur, row: tuple) -> bool:
    """단일 행 upsert. 성공 시 True, 좌표 중복으로 skip 시 False.

    facility_id(=STORE_+bizesId) 충돌은 정상 갱신(재수집/폐업 복귀) 대상이라
    ON CONFLICT (facility_id) 로 처리된다. 그런데 facilities 테이블에는 이와
    별개로 idx_facility_unique(facility_subtype, lat, lng) UNIQUE 제약이
    있다(2026-04-02 dedup 프로젝트 — 좌표당 대표 시설 1개만 유지가 설계
    의도). 상가 데이터는 같은 건물(예: 상가 집합건물 내 여러 점포)의 좌표가
    사업자번호만 다르고 동일한 사례가 흔해 이 제약과 충돌한다.
    한 INSERT 문은 conflict target 을 하나만 지정할 수 있으므로, 이 경우는
    SAVEPOINT 로 해당 행만 롤백해 '먼저 잡힌 점포가 그 좌표를 대표' 하도록
    skip 처리한다(페이지 커밋 전체를 되돌리지 않음).
    """
    cur.execute("SAVEPOINT store_row")
    try:
        cur.execute(UPSERT_SQL, row)
    except psycopg2.errors.UniqueViolation:
        cur.execute("ROLLBACK TO SAVEPOINT store_row")
        return False
    cur.execute("RELEASE SAVEPOINT store_row")
    return True


# 폐업 비활성화: 이번 실행에서 갱신되지 않은(재등장하지 않은) 기존 점포를 비활성 처리.
# 전량 수집(max_pages=0)일 때만 안전 — 표본 모드에서 실행하면 미수집분까지
# 오탐 비활성화되므로 호출부에서 max_pages 로 분기한다.
DEACTIVATE_SQL = """
    UPDATE facilities SET is_active = FALSE
    WHERE facility_subtype = %s AND facility_id LIKE 'STORE\\_%%' AND updated_at < %s
"""


def _collect_subtype(
    conn, logger, subtype: str, codes: list[str], facility_type: str, max_pages: int
) -> dict:
    """단일 subtype 전 소분류 코드 페이징 수집 + upsert (+ 전량 모드 비활성화)."""
    cur = conn.cursor()
    cur.execute("SELECT NOW()")
    started_at = cur.fetchone()[0]  # DB 서버 시각 기준 — 앱/DB 시계 오차 방지

    fetched = upserted = skipped = 0
    for code in codes:
        page = 1
        while True:
            if max_pages and page > max_pages:
                logger.info(f"  {subtype}/{code}: --max-pages {max_pages} 도달 — 중단")
                break
            items, total = _fetch_page(code, page)
            time.sleep(DATA_GO_KR_RATE)
            if not items:
                break
            for item in items:
                fetched += 1
                row = _to_row(item, facility_type, subtype)
                if row is None:
                    skipped += 1
                    continue
                if _upsert_row(cur, row):
                    upserted += 1
                else:
                    skipped += 1
            conn.commit()
            logger.info(
                f"  {subtype}/{code}: {page}p 완료 (누적 {fetched:,}/{total:,})"
            )
            if page * MAX_ROWS_PER_PAGE >= total:
                break
            page += 1

    deactivated = 0
    if max_pages == 0:
        cur.execute(DEACTIVATE_SQL, [subtype, started_at])
        deactivated = cur.rowcount
        conn.commit()
        if deactivated:
            logger.info(f"  {subtype}: 폐업 비활성화 {deactivated:,}건")
    else:
        logger.info(f"  {subtype}: 표본 모드(--max-pages {max_pages}) — 비활성화 스킵")

    logger.info(
        f"{subtype} 수집 완료: 호출 {fetched:,} / 적재 {upserted:,} / skip {skipped:,}"
    )
    return {"fetched": fetched, "upserted": upserted, "deactivated": deactivated}


def collect_store_facilities(
    conn, logger, subtypes: list[str] | None = None, max_pages: int = 0
) -> dict:
    """상가정보 4개 subtype(cafe/kids_cafe/pet_shop/fitness) 수집.

    subtypes 미지정 시 STORE_SUBTYPE_CODES 전체. max_pages=0 이면 전량
    (해당 subtype 완료 후 비활성화까지 수행), 그 외에는 표본 수집(비활성화 스킵).
    """
    target_subtypes = subtypes or list(STORE_SUBTYPE_CODES.keys())
    unknown = [s for s in target_subtypes if s not in STORE_SUBTYPE_CODES]
    if unknown:
        raise ValueError(f"알 수 없는 subtype: {unknown}")

    totals = {"fetched": 0, "upserted": 0, "deactivated": 0}
    for subtype in target_subtypes:
        result = _collect_subtype(
            conn,
            logger,
            subtype,
            STORE_SUBTYPE_CODES[subtype],
            SUBTYPE_TYPE_MAP[subtype],
            max_pages,
        )
        for k in totals:
            totals[k] += result[k]
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subtype",
        choices=list(STORE_SUBTYPE_CODES.keys()),
        help="특정 subtype 만 수집 (미지정 시 4종 전체)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="subtype/코드당 최대 페이지 수 (0=무제한, 표본 수집용)",
    )
    args = parser.parse_args()

    logger = setup_logger("store_facilities")
    conn = get_connection()
    try:
        subtypes = [args.subtype] if args.subtype else None
        result = collect_store_facilities(
            conn, logger, subtypes=subtypes, max_pages=args.max_pages
        )
        logger.info(
            f"전체 완료: 호출 {result['fetched']:,} / 적재 {result['upserted']:,} "
            f"/ 비활성화 {result['deactivated']:,}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
