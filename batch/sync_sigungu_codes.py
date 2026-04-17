"""nationwide_codes.ALL_SGG → common_code(sigungu) 동기화 배치.

ALL_SGG 딕셔너리의 시군구 코드·이름을 common_code 테이블에 UPSERT.
DB에만 존재하는 코드(강원특별자치도 51xxx 등)는 삭제하지 않고 알림만 출력.

사용법:
  python -m batch.sync_sigungu_codes            # 실행
  python -m batch.sync_sigungu_codes --dry-run   # 변경 없이 미리보기
"""

import re
import sys

from batch.db import get_connection
from batch.logger import setup_logger
from batch.nationwide_codes import ALL_SGG

# ── 시도 코드 (앞 2자리) → 시도명 ──

SIDO_MAP = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천",
    "29": "광주", "30": "대전", "31": "울산", "36": "세종",
    "41": "경기", "42": "강원", "43": "충북", "44": "충남",
    "45": "전북", "46": "전남", "47": "경북", "48": "경남",
    "50": "제주", "51": "강원", "52": "전북",
}

# ── 구를 가진 시 — code prefix(4자리) → extra에 사용할 시 이름 ──

_CITY_PREFIX: dict[str, str] = {
    "4111": "수원", "4113": "성남", "4117": "안양", "4119": "부천",
    "4127": "안산", "4128": "고양", "4146": "용인", "4159": "화성",
    "4311": "청주", "4413": "천안",
    "4511": "전주", "5211": "전주",
    "4711": "포항", "4812": "창원",
}

_PAREN_SUFFIX = re.compile(r"\((.+)\)$")


def _split_name_extra(code: str, raw_name: str) -> tuple[str, str]:
    """ALL_SGG의 raw name에서 (name, extra) 분리.

    분리 규칙:
      1. "(부산)" 접미사 → extra=부산, name에서 제거
      2. 구를 가진 시 (code prefix 매칭) → extra=시이름, name=구이름+"구"
      3. 나머지 → extra=시도명, name=그대로
    """
    # 1. "(부산)", "(경남)" 등 괄호 접미사
    m = _PAREN_SUFFIX.search(raw_name)
    if m:
        return _PAREN_SUFFIX.sub("", raw_name).strip(), m.group(1)

    # 2. 구를 가진 시
    for prefix, city in _CITY_PREFIX.items():
        if code.startswith(prefix):
            gu_name = raw_name.replace(city, "", 1)
            if not gu_name.endswith(("구", "군")):
                gu_name += "구"
            return gu_name, city

    # 3. 나머지 — 시도명
    return raw_name, SIDO_MAP.get(code[:2], "")


def main():
    dry_run = "--dry-run" in sys.argv
    logger = setup_logger("sync_sigungu")

    # 1. ALL_SGG → (group_id, code, name, extra, sort_order) 행 생성
    rows: list[tuple[str, str, str, str, int]] = []
    for code, raw_name in sorted(ALL_SGG.items()):
        name, extra = _split_name_extra(code, raw_name)
        rows.append(("sigungu", code, name, extra, 0))

    logger.info(f"ALL_SGG 소스: {len(rows)}건")

    if dry_run:
        logger.info("[dry-run] 변경 예정 내역:")
        for _, code, name, extra, _ in rows:
            logger.info(f"  {code} = {extra} {name}")

    # 2. DB 연결 + UPSERT
    conn = get_connection()
    cur = conn.cursor()

    if not dry_run:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            "INSERT INTO common_code (group_id, code, name, extra, sort_order) VALUES %s "
            "ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra",
            rows,
            page_size=500,
        )
        conn.commit()
        logger.info(f"UPSERT 완료: {len(rows)}건")

    # 3. DB에만 있고 ALL_SGG에 없는 코드 확인 (삭제하지 않음)
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu' ORDER BY code")
    db_codes = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    src_codes = set(ALL_SGG.keys())
    db_only = sorted(set(db_codes.keys()) - src_codes)

    if db_only:
        logger.info(f"DB에만 존재하는 코드 ({len(db_only)}건, 삭제하지 않음):")
        for code in db_only:
            name, extra = db_codes[code]
            logger.info(f"  {code} = {extra} {name}")

    # 4. 검증 — UPSERT 결과 확인
    cur.execute("SELECT COUNT(*) FROM common_code WHERE group_id = 'sigungu'")
    total = cur.fetchone()[0]

    # 불일치 확인 (name 또는 extra가 다른 경우)
    mismatches = []
    for _, code, name, extra, _ in rows:
        if code in db_codes:
            db_name, db_extra = db_codes[code]
            if not dry_run and (db_name != name or db_extra != extra):
                mismatches.append((code, f"DB={db_extra} {db_name}", f"SRC={extra} {name}"))

    if mismatches and dry_run:
        # dry-run에서는 현재 DB와 차이를 표시
        for _, code, name, extra, _ in rows:
            if code in db_codes:
                db_name, db_extra = db_codes[code]
                if db_name != name or db_extra != extra:
                    logger.info(f"  갱신 예정: {code}  DB=\"{db_extra} {db_name}\" → \"{extra} {name}\"")

    conn.close()
    logger.info(f"총 sigungu 코드: {total}건 (ALL_SGG {len(rows)}건 + DB 전용 {len(db_only)}건)")

    if dry_run:
        logger.info("[dry-run] 완료 — 실제 변경 없음")


if __name__ == "__main__":
    main()
