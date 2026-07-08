"""NEIS 학원/교습소 정보 → facilities `academy` subtype 적재 (라이프점수 Phase 2-5).

입시·검정·보습 학원만 필터링해 교육청별로 페이징 수집한다. NEIS 응답에는
좌표가 없고 도로명주소(FA_RDNMA)만 제공되므로, 지금까지의 Phase 2 수집기
(HIRA/상가/대기질)와 달리 **지오코딩이 유일한 신규 요소**다 — 재수집 시
Kakao 쿼터를 아끼기 위해 기존 NEIS_ 행의 주소가 이전과 동일하면 좌표를
재사용하는 증분 지오코딩을 적용한다.

PoC 확정(2026-07-08, 실측):
- `https://open.neis.go.kr/hub/acaInsTiInfo` + KEY=NEIS_API_KEY, Type=json,
  pIndex/pSize(≤1000), ATPT_OFCDC_SC_CODE(17개 교육청 코드).
- 응답 구조: `d["acaInsTiInfo"][0]["head"][0]["list_total_count"]`(총건수) +
  `d["acaInsTiInfo"][1]["row"]`(목록). 데이터 없음/오류 시 최상위에 "RESULT"
  키만 반환됨(`{"RESULT": {"CODE": "INFO-200", "MESSAGE": "..."}}`) —
  INFO-200(해당 데이터 없음)은 정상 종료, 그 외 코드는 예외로 전파한다.
- 서울(B10) 실측 총 25,522곳 중 REALM_SC_NM 분포: 입시.검정 및 보습 62% /
  예능 27% / 국제화 5%(진단 문서 기준) — **수집 대상은 '입시.검정 및 보습'만**.
- 좌표 미제공 → FA_RDNMA(도로명주소)를 Kakao 주소검색으로 지오코딩. 도로명 표기가
  이미 시/도까지 포함하고 있어(예: "서울특별시 강남구 선릉로68길 10") 그대로
  질의하면 매칭됨을 PoC 실측으로 확인.

facility_id: 'NEIS_' + 교육청코드 + '_' + ACA_ASNUM. ACA_ASNUM(학원지정번호)은
교육청 내부에서만 유일 보장되는 키라 교육청 간 중복 가능성이 있어 접두어로 구분한다.

Kakao 지오코딩 유틸 재사용 검토: web/backend/services/geocoder.py 가 존재하지만
(1) web/backend/CLAUDE.md 의 배포 경계 규칙상 batch/ ↔ web/backend/ 는 서로
import 하지 않는 관례이고(batch 는 Railway 에 배포되지 않는 별도 파이프라인),
(2) 기존 batch/ 수집기들(fix_coord_drift.py, register_new_apartments.py,
enrich_apartments.py, fill_addresses.py, collect_fire_centers.py)도 이미 각자
Kakao 주소검색 최소 구현을 반복하는 것이 이 코드베이스의 기존 관례다(batch
내부에도 공용 지오코딩 유틸이 없음). 따라서 이 모듈도 그 관례를 따라 최소
구현을 둔다 — 신규 중복이 아니라 기존 패턴 준수.

사용법:
  .venv/bin/python -m batch.quarterly.collect_academies                     # 전국 17개 교육청
  .venv/bin/python -m batch.quarterly.collect_academies --offices B10       # 서울만
  .venv/bin/python -m batch.quarterly.collect_academies --offices B10 --max-pages 2  # 표본
"""

import argparse
import time

import psycopg2.errors
import requests

from batch.config import KAKAO_API_KEY, KAKAO_RATE, NEIS_API_KEY, NEIS_RATE
from batch.db import get_connection
from batch.logger import setup_logger

NEIS_API_URL = "https://open.neis.go.kr/hub/acaInsTiInfo"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

MAX_ROWS_PER_PAGE = 1000  # PoC 확정(2026-07-08)
NEIS_SUCCESS_CODE = "INFO-000"
NEIS_NO_DATA_CODE = "INFO-200"  # 해당 데이터 없음 — 정상 종료(빈 페이지 취급)
MAX_RETRIES = 2  # transient 오류 백오프 재시도 (collect_hira_hospitals 관례)
KAKAO_GEOCODE_TIMEOUT = 5
KAKAO_MAX_RETRIES = 2
GEOCODE_PROGRESS_INTERVAL = 5000  # 지오코딩 진행 로그 단위(5,000건마다)

ACADEMY_REALM = "입시.검정 및 보습"  # REALM_SC_NM 필터값
REG_STTUS_OPEN = "개원"  # REG_STTUS_NM 필터값(폐원/등록취소 등 제외)
FACILITY_TYPE = "education"
FACILITY_SUBTYPE = "academy"

# 17개 시도교육청 코드 (context 확정, 2026-07-08 PoC)
NEIS_OFFICES: dict[str, str] = {
    "B10": "서울",
    "C10": "부산",
    "D10": "대구",
    "E10": "인천",
    "F10": "광주",
    "G10": "대전",
    "H10": "울산",
    "I10": "세종",
    "J10": "경기",
    "K10": "강원",
    "M10": "충북",
    "N10": "충남",
    "P10": "전북",
    "Q10": "전남",
    "R10": "경북",
    "S10": "경남",
    "T10": "제주",
}


class RateLimitExceeded(RuntimeError):
    """NEIS API 일일 호출 한도 소진(HTTP 429) — 조기 중단, 페이지 단위 부분 커밋 유지."""


class KakaoQuotaExceeded(RuntimeError):
    """Kakao 지오코딩 일일 쿼터 소진(HTTP 429) — 조기 중단.

    페이지 처리 도중 발생하면 해당 페이지의 미커밋 upsert 는 롤백되지만
    (다음 실행 시 idempotent upsert 로 재처리되므로 데이터 손실 없음),
    이전에 완료된 페이지는 이미 커밋되어 있어 그대로 유지된다.
    """


def _fetch_page(office_code: str, page: int, logger) -> tuple[list[dict], int]:
    """단일 교육청 1페이지 조회. (rows, list_total_count) 반환.

    키(KEY)는 요청 params 에만 담기고 로그에는 절대 출력하지 않는다.
    """
    params = {
        "KEY": NEIS_API_KEY,
        "Type": "json",
        "pIndex": str(page),
        "pSize": str(MAX_ROWS_PER_PAGE),
        "ATPT_OFCDC_SC_CODE": office_code,
    }
    attempt = 0
    while True:
        try:
            resp = requests.get(NEIS_API_URL, params=params, timeout=30)
            if resp.status_code == 429:
                raise RateLimitExceeded(
                    f"{office_code} {page}p: HTTP 429 (일일 한도 소진)"
                )
            resp.raise_for_status()
            data = resp.json()
            aca = data.get("acaInsTiInfo")
            if aca is None:
                result = data.get("RESULT") or {}
                code = result.get("CODE")
                if code == NEIS_NO_DATA_CODE:
                    return [], 0
                raise RuntimeError(
                    f"{office_code} {page}p: RESULT {code} ({result.get('MESSAGE')})"
                )
            head = aca[0].get("head") or []
            total = int(head[0].get("list_total_count") or 0) if head else 0
            rows = aca[1].get("row", []) if len(aca) > 1 else []
            return rows, total
        except RateLimitExceeded:
            raise  # 한도 소진 — 재시도 대상 아님, 상위에서 조기 중단
        except Exception:  # noqa: BLE001 — transient 대비 재시도 후 상위 전파
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            time.sleep(attempt)  # 1s, 2s 백오프


def _filter_row(row: dict) -> bool:
    """분야(입시.검정 및 보습) + 등록상태(개원)만 통과."""
    return (
        row.get("REALM_SC_NM") == ACADEMY_REALM
        and row.get("REG_STTUS_NM") == REG_STTUS_OPEN
    )


def _facility_id(office_code: str, row: dict) -> str | None:
    asnum = row.get("ACA_ASNUM")
    if not asnum:
        return None
    return f"NEIS_{office_code}_{asnum}"


def _compose_address(row: dict) -> str:
    """도로명주소(FA_RDNMA) + 상세(FA_RDNDA) 결합.

    지오코딩 질의는 FA_RDNMA(도로명 본번지)만 사용한다 — FA_RDNDA는 층/호수 등
    상세 정보로 좌표에 영향을 주지 않는다. 증분 비교는 결합 문자열 전체로
    수행하는데, FA_RDNDA가 FA_RDNMA 뒤에 이어붙는 구조라 결합값이 동일하면
    FA_RDNMA도 반드시 동일함이 보장되어 안전하다.
    """
    road = (row.get("FA_RDNMA") or "").strip()
    detail = (row.get("FA_RDNDA") or "").strip()
    return f"{road}{detail}".strip()


def _load_office_cache(conn, office_code: str) -> dict[str, tuple[str, float, float]]:
    """해당 교육청 접두 기존 NEIS_ 행의 (facility_id → address, lat, lng) 캐시.

    재수집 시 주소가 바뀌지 않은 행은 Kakao 재호출 없이 좌표를 재사용한다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT facility_id, address, lat, lng FROM facilities WHERE facility_id LIKE %s",
        [f"NEIS\\_{office_code}\\_%"],
    )
    return {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}


def _kakao_geocode(road_address: str, logger) -> tuple[float, float] | None:
    """도로명주소 → (lat, lng). 매칭 없음/오류 시 None(호출부에서 skip 처리)."""
    if not KAKAO_API_KEY or not road_address:
        return None
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    attempt = 0
    while True:
        try:
            resp = requests.get(
                KAKAO_ADDRESS_URL,
                headers=headers,
                params={"query": road_address, "size": 1},
                timeout=KAKAO_GEOCODE_TIMEOUT,
            )
            if resp.status_code == 429:
                raise KakaoQuotaExceeded("Kakao 지오코딩 일일 쿼터 소진(HTTP 429)")
            resp.raise_for_status()
            time.sleep(KAKAO_RATE)
            docs = resp.json().get("documents", [])
            if not docs:
                return None
            doc = docs[0]
            if not doc.get("y") or not doc.get("x"):
                return None
            return float(doc["y"]), float(doc["x"])
        except KakaoQuotaExceeded:
            raise  # 조기 중단 대상 — 상위로 전파
        except Exception as e:  # noqa: BLE001 — transient 대비 재시도 후 skip(행 단위 실패)
            attempt += 1
            if attempt > KAKAO_MAX_RETRIES:
                logger.debug(
                    f"Kakao 지오코딩 실패(재시도 소진, addr='{road_address}'): {e}"
                )
                return None
            time.sleep(attempt)


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
    해당 행만 롤백해 skip 처리(collect_hira_hospitals/collect_store_facilities 관례).
    """
    cur.execute("SAVEPOINT academy_row")
    try:
        cur.execute(UPSERT_SQL, row)
    except psycopg2.errors.UniqueViolation:
        cur.execute("ROLLBACK TO SAVEPOINT academy_row")
        return False
    cur.execute("RELEASE SAVEPOINT academy_row")
    return True


def _collect_office(
    conn, logger, office_code: str, office_name: str, max_pages: int
) -> dict:
    """단일 교육청 전 페이징 수집 + 증분 지오코딩 + upsert (+ 전량 모드 비활성화)."""
    cur = conn.cursor()
    cur.execute("SELECT NOW()")
    started_at = cur.fetchone()[0]  # DB 서버 시각 기준 — 앱/DB 시계 오차 방지

    cache = _load_office_cache(conn, office_code)

    fetched = filtered = geocoded = geocode_reused = geocode_failed = 0
    upserted = skipped = 0
    page = 1
    while True:
        if max_pages and page > max_pages:
            logger.info(
                f"  {office_name}({office_code}): --max-pages {max_pages} 도달 — 중단"
            )
            break
        rows, total = _fetch_page(office_code, page, logger)
        time.sleep(NEIS_RATE)
        if not rows:
            break
        for row in rows:
            fetched += 1
            if not _filter_row(row):
                continue
            filtered += 1

            facility_id = _facility_id(office_code, row)
            if not facility_id:
                skipped += 1
                continue

            address = _compose_address(row)
            cached = cache.get(facility_id)
            if (
                cached
                and cached[0] == address
                and cached[1] is not None
                and cached[2] is not None
            ):
                lat, lng = cached[1], cached[2]
                geocode_reused += 1
            else:
                road = (row.get("FA_RDNMA") or "").strip()
                coord = _kakao_geocode(road, logger)
                if coord is None:
                    geocode_failed += 1
                    skipped += 1
                    continue
                lat, lng = coord
                geocoded += 1

            name = (row.get("ACA_NM") or "")[:200]
            db_row = (
                facility_id,
                FACILITY_TYPE,
                FACILITY_SUBTYPE,
                name,
                lat,
                lng,
                address[:300],
            )
            if _upsert_row(cur, db_row):
                upserted += 1
            else:
                skipped += 1

            processed = geocoded + geocode_reused
            if processed and processed % GEOCODE_PROGRESS_INTERVAL == 0:
                logger.info(
                    f"  {office_name}: 지오코딩 진행 {processed:,}건 "
                    f"(신규 {geocoded:,} / 재사용 {geocode_reused:,} / 실패 {geocode_failed:,})"
                )
        conn.commit()
        logger.info(
            f"  {office_name}({office_code}): {page}p 완료 (누적 {fetched:,}/{total:,})"
        )
        if page * MAX_ROWS_PER_PAGE >= total:
            break
        page += 1

    deactivated = 0
    if max_pages == 0:
        cur.execute(
            "UPDATE facilities SET is_active = FALSE "
            "WHERE facility_subtype = %s AND facility_id LIKE %s AND updated_at < %s",
            [FACILITY_SUBTYPE, f"NEIS\\_{office_code}\\_%", started_at],
        )
        deactivated = cur.rowcount
        conn.commit()
        if deactivated:
            logger.info(f"  {office_name}: 폐원/등록취소 비활성화 {deactivated:,}건")
    else:
        logger.info(
            f"  {office_name}: 표본 모드(--max-pages {max_pages}) — 비활성화 스킵"
        )

    logger.info(
        f"{office_name}({office_code}) 완료: 조회 {fetched:,} / 필터통과 {filtered:,} / "
        f"지오코딩 신규 {geocoded:,} / 재사용 {geocode_reused:,} / 실패 {geocode_failed:,} / "
        f"적재 {upserted:,} / skip {skipped:,} / 비활성화 {deactivated:,}"
    )
    return {
        "fetched": fetched,
        "filtered": filtered,
        "geocoded": geocoded,
        "geocode_reused": geocode_reused,
        "geocode_failed": geocode_failed,
        "upserted": upserted,
        "deactivated": deactivated,
    }


def collect_academies(
    conn, logger, offices: list[str] | None = None, max_pages: int = 0
) -> dict:
    """NEIS 학원(입시.검정 및 보습) 수집. offices 미지정 시 17개 교육청 전체.

    max_pages=0 이면 교육청별 전량 수집(완료 후 비활성화까지 수행), 그 외에는
    표본 수집(비활성화 스킵). 반환 dict 는 대상 교육청 전체 합산.
    """
    target_offices = offices or list(NEIS_OFFICES)
    unknown = [o for o in target_offices if o not in NEIS_OFFICES]
    if unknown:
        raise ValueError(f"알 수 없는 교육청 코드: {unknown}")

    totals = {
        "fetched": 0,
        "filtered": 0,
        "geocoded": 0,
        "geocode_reused": 0,
        "geocode_failed": 0,
        "upserted": 0,
        "deactivated": 0,
    }
    for office_code in target_offices:
        office_name = NEIS_OFFICES[office_code]
        logger.info(f"{office_name}({office_code}) 수집 시작")
        result = _collect_office(conn, logger, office_code, office_name, max_pages)
        for k in totals:
            totals[k] += result[k]
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offices",
        nargs="+",
        choices=list(NEIS_OFFICES.keys()),
        help="특정 교육청 코드만 수집 (미지정 시 17개 전체)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="교육청당 최대 페이지 수 (0=무제한, 표본 수집용)",
    )
    args = parser.parse_args()

    logger = setup_logger("academies")
    conn = get_connection()
    try:
        result = collect_academies(
            conn, logger, offices=args.offices, max_pages=args.max_pages
        )
        logger.info(
            f"전체 완료: 조회 {result['fetched']:,} / 필터통과 {result['filtered']:,} / "
            f"지오코딩 신규 {result['geocoded']:,} / 재사용 {result['geocode_reused']:,} / "
            f"실패 {result['geocode_failed']:,} / 적재 {result['upserted']:,} / "
            f"비활성화 {result['deactivated']:,}"
        )
    except (RateLimitExceeded, KakaoQuotaExceeded) as e:
        # 부분 성공 — 페이지 단위 커밋이라 여기까지의 적재는 유지된다.
        # 재실행 시 upsert/증분 캐시로 이어받으므로 raw traceback 없이 정상 종료.
        logger.warning(f"한도 도달({e}) — 재실행 필요, 부분 커밋 유지됨")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
