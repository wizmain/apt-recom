"""심평원 병원정보서비스 → facilities 세분화 적재 (라이프점수 Phase 2-3).

진료과목/병원급 필터로 소아과·산부인과·종합병원 3개 subtype 을 전국
페이징 수집한다. collect_store_facilities 골격 준용 — 단 이 API 는 응답이
**XML** 이다(상가는 JSON, collect_building_register 의 ET 파싱 참고).

PoC 확정(2026-07-06, 실측):
- `hospInfoServicev2/getHospBasisList` + PRIMARY 키(DATA_GO_KR_API_KEY).
- dgsbjtCd=11(소아청소년과) totalCount 15,432 / dgsbjtCd=10(산부인과) 4,292 /
  clCd=01(상급종합) 47 + clCd=11(종합병원) 338 — 모두 실측 일치 확인.
- numOfRows=1000 요청이 그대로 수락됨(상가 API 와 달리 1000 캡 없음) —
  MAX_ROWS_PER_PAGE=1000 확정, 100 fallback 불필요.
- 좌표는 XPos(경도)/YPos(위도) — **X 가 경도**이므로 lat=YPos, lng=XPos 로
  매핑해야 한다(반대로 매핑하면 좌표가 뒤집힌다).
- ykiho 는 80자 암호화 문자열이지만 재수집 시 안정적인 기관 식별자.

facility_id: 'HIRA_' + ykiho + subtype 약어 접미사('_PED'/'_OBG'/'_GEN').
한 기관이 여러 진료과목(예: 소아과+산부인과)을 동시에 표방할 수 있어 이
접미사로 subtype 별 행을 구분한다(상가와 달리 facility_id 만으로는
subtype 이 유일하지 않음).

general_hospital 은 clCd 01(상급종합)+11(종합병원) 두 쿼리를 합산한다
(HIRA_SUBTYPE_FILTERS 값이 list 인 경우).

사용법:
  .venv/bin/python -m batch.quarterly.collect_hira_hospitals                       # 전체
  .venv/bin/python -m batch.quarterly.collect_hira_hospitals --subtype pediatric_clinic --max-pages 2  # 표본
"""

import argparse
import time
import xml.etree.ElementTree as ET

import psycopg2.errors
import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import get_connection
from batch.logger import setup_logger

HOSP_API_URL = "http://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"
MAX_ROWS_PER_PAGE = 1000  # PoC 실측(2026-07-06): 상가 API 와 달리 1000 그대로 수락됨
SUCCESS_RESULT_CODE = "00"
MAX_RETRIES = 2  # transient 오류 백오프 재시도 (collect_store_facilities 관례)

# 필터 상수 (PoC 2026-07-06 실측 근거는 모듈 docstring 참조).
# 소아과/산부인과는 진료과목 필터(단일 쿼리), 종합병원은 병원급 필터
# 2건(상급종합+종합병원)을 합산한다 — 값이 list 인 경우가 그 표시.
HIRA_SUBTYPE_FILTERS: dict[str, dict | list[dict]] = {
    # 진료과목 필터 — 해당 과목을 "표방"하는 전 기관 (병원급 무관, 통원 접근성 관점)
    "pediatric_clinic": {"dgsbjtCd": "11"},  # 소아청소년과 (PoC 15,432)
    "obgyn_clinic": {"dgsbjtCd": "10"},  # 산부인과 (PoC 4,292)
    # 병원급 필터 — 응급/중증 대응 프록시 (상급종합 01 + 종합병원 11, PoC 385)
    "general_hospital": [{"clCd": "01"}, {"clCd": "11"}],
}

SUBTYPE_SUFFIX = {
    "pediatric_clinic": "PED",
    "obgyn_clinic": "OBG",
    "general_hospital": "GEN",
}

SUBTYPE_TYPE_MAP = {
    "pediatric_clinic": "medical",
    "obgyn_clinic": "medical",
    "general_hospital": "medical",
}


class RateLimitExceeded(RuntimeError):
    """HTTP 429(일일 한도) — collect_store_facilities 관례와 동일하게 조기 중단.

    이 API 는 PRIMARY 키로 정상 활용신청되어 로테이션 대상이 아니다
    (403 활용신청 문제가 아니라 순수 일일 호출량 초과이므로, 자정 리셋
    이후 재실행 대상).
    """


def _fetch_page(params: dict, page: int, logger) -> tuple[list[dict], int]:
    """필터 파라미터 1페이지 조회. (items, totalCount) 반환.

    응답이 XML — collect_building_register 의 ET 파싱 패턴 준용.
    """
    query = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "numOfRows": str(MAX_ROWS_PER_PAGE),
        "pageNo": str(page),
        **params,
    }
    attempt = 0
    while True:
        try:
            resp = requests.get(HOSP_API_URL, params=query, timeout=30)
            if resp.status_code == 429:
                raise RateLimitExceeded(f"{params} {page}p: HTTP 429 (일일 한도 소진)")
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            result_code = root.findtext(".//resultCode")
            if result_code != SUCCESS_RESULT_CODE:
                raise RuntimeError(
                    f"{params} {page}p: resultCode {result_code} "
                    f"({root.findtext('.//resultMsg')})"
                )
            items = [
                {
                    "yadmNm": it.findtext("yadmNm") or "",
                    "ykiho": it.findtext("ykiho") or "",
                    "XPos": it.findtext("XPos"),
                    "YPos": it.findtext("YPos"),
                    "addr": it.findtext("addr") or "",
                }
                for it in root.findall(".//item")
            ]
            total = int(root.findtext(".//totalCount") or 0)
            return items, total
        except RateLimitExceeded:
            raise  # 한도 소진 — 재시도 대상 아님, 상위에서 조기 중단
        except Exception:  # noqa: BLE001 — transient 대비 재시도 후 상위 전파
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            time.sleep(attempt)  # 1s, 2s 백오프


def _to_row(item: dict, facility_type: str, subtype: str) -> tuple | None:
    """API 응답 항목 → facilities upsert 파라미터. 좌표/식별자 결측은 None(skip)."""
    ykiho = item.get("ykiho")
    x_pos, y_pos = item.get("XPos"), item.get("YPos")  # XPos=경도, YPos=위도
    if not ykiho or x_pos is None or y_pos is None:
        return None
    try:
        lng, lat = float(x_pos), float(y_pos)
    except (TypeError, ValueError):
        return None
    facility_id = f"HIRA_{ykiho}_{SUBTYPE_SUFFIX[subtype]}"
    return (
        facility_id,
        facility_type,
        subtype,
        (item.get("yadmNm") or "")[:200],
        lat,
        lng,
        (item.get("addr") or "")[:300],
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

    idx_facility_unique(facility_subtype, lat, lng) 제약 충돌 시 SAVEPOINT 로
    해당 행만 롤백해 skip 처리 (collect_store_facilities 와 동일 관례 —
    한 건물에 입주한 여러 기관이 같은 좌표를 공유하는 사례 대응).
    """
    cur.execute("SAVEPOINT hira_row")
    try:
        cur.execute(UPSERT_SQL, row)
    except psycopg2.errors.UniqueViolation:
        cur.execute("ROLLBACK TO SAVEPOINT hira_row")
        return False
    cur.execute("RELEASE SAVEPOINT hira_row")
    return True


# 폐업 비활성화: 이번 실행에서 갱신되지 않은(재등장하지 않은) 기존 기관을 비활성 처리.
# 전량 수집(max_pages=0)일 때만 안전 (collect_store_facilities 관례 — 표본 모드에서
# 실행하면 미수집분까지 오탐 비활성화되므로 호출부에서 max_pages 로 분기한다).
DEACTIVATE_SQL = """
    UPDATE facilities SET is_active = FALSE
    WHERE facility_subtype = %s AND facility_id LIKE 'HIRA\\_%%' AND updated_at < %s
"""


def _collect_subtype(
    conn, logger, subtype: str, filter_params: dict | list[dict], max_pages: int
) -> dict:
    """단일 subtype 전 필터(1개 또는 2개 쿼리 합산) 페이징 수집 + upsert (+ 전량 모드 비활성화)."""
    cur = conn.cursor()
    cur.execute("SELECT NOW()")
    started_at = cur.fetchone()[0]  # DB 서버 시각 기준 — 앱/DB 시계 오차 방지

    facility_type = SUBTYPE_TYPE_MAP[subtype]
    filter_list = filter_params if isinstance(filter_params, list) else [filter_params]

    fetched = upserted = skipped = 0
    for params in filter_list:
        page = 1
        while True:
            if max_pages and page > max_pages:
                logger.info(
                    f"  {subtype}/{params}: --max-pages {max_pages} 도달 — 중단"
                )
                break
            items, total = _fetch_page(params, page, logger)
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
                f"  {subtype}/{params}: {page}p 완료 (누적 {fetched:,}/{total:,})"
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
            logger.info(f"  {subtype}: 폐업/등록취소 비활성화 {deactivated:,}건")
    else:
        logger.info(f"  {subtype}: 표본 모드(--max-pages {max_pages}) — 비활성화 스킵")

    logger.info(
        f"{subtype} 수집 완료: 호출 {fetched:,} / 적재 {upserted:,} / skip {skipped:,}"
    )
    return {
        "fetched": fetched,
        "upserted": upserted,
        "skipped": skipped,
        "deactivated": deactivated,
    }


def collect_hira_hospitals(
    conn, logger, subtypes: list[str] | None = None, max_pages: int = 0
) -> dict:
    """심평원 병원정보 3개 subtype(pediatric_clinic/obgyn_clinic/general_hospital) 수집.

    subtypes 미지정 시 HIRA_SUBTYPE_FILTERS 전체. max_pages=0 이면 전량
    (해당 subtype 완료 후 비활성화까지 수행), 그 외에는 표본 수집(비활성화 스킵).
    """
    target_subtypes = subtypes or list(HIRA_SUBTYPE_FILTERS.keys())
    unknown = [s for s in target_subtypes if s not in HIRA_SUBTYPE_FILTERS]
    if unknown:
        raise ValueError(f"알 수 없는 subtype: {unknown}")

    totals = {"fetched": 0, "upserted": 0, "skipped": 0, "deactivated": 0}
    for subtype in target_subtypes:
        result = _collect_subtype(
            conn, logger, subtype, HIRA_SUBTYPE_FILTERS[subtype], max_pages
        )
        for k in totals:
            totals[k] += result[k]
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subtype",
        choices=list(HIRA_SUBTYPE_FILTERS.keys()),
        help="특정 subtype 만 수집 (미지정 시 3종 전체)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="subtype/필터당 최대 페이지 수 (0=무제한, 표본 수집용)",
    )
    args = parser.parse_args()

    logger = setup_logger("hira_hospitals")
    conn = get_connection()
    try:
        subtypes = [args.subtype] if args.subtype else None
        result = collect_hira_hospitals(
            conn, logger, subtypes=subtypes, max_pages=args.max_pages
        )
        logger.info(
            f"전체 완료: 호출 {result['fetched']:,} / 적재 {result['upserted']:,} "
            f"/ skip {result['skipped']:,} / 비활성화 {result['deactivated']:,}"
        )
    except RateLimitExceeded as e:
        # 부분 성공 — 페이지 단위 커밋이라 여기까지의 적재는 유지된다.
        # 재실행 시 upsert 로 이어받으므로 raw traceback 없이 정상 종료.
        logger.warning(
            f"일일 호출 한도 도달({e}) — 자정 이후 재실행 필요, 부분 커밋 유지됨"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
