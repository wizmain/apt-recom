"""읍면동 법정동코드를 common_code 테이블에 적재.

사용법:
  python -m batch.load_emd_codes
"""

import csv
import re
from pathlib import Path
from batch.db import get_connection
from batch.logger import setup_logger

def _normalize_sgg(name: str) -> str:
    """시군구명에서 시+구/군 사이 공백 삽입. 예: '용인시처인구' → '용인시 처인구'"""
    return re.sub(r"(시)([가-힣]+[구군])$", r"\1 \2", name)


def main():
    logger = setup_logger("load_emd")
    csv_path = Path(__file__).resolve().parents[1] / "apt_eda" / "data" / "processed" / "04_bjd_mapping.csv"

    if not csv_path.exists():
        logger.error(f"CSV 파일 없음: {csv_path}")
        return

    conn = get_connection()
    cur = conn.cursor()

    # 기존 emd 데이터 삭제
    cur.execute("DELETE FROM common_code WHERE group_id = 'emd'")

    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            bjd_code = r["bjdCode"].strip()
            emd_name = r["읍면동명"].strip()
            region = f"{r['시도명'].strip()} {_normalize_sgg(r['시군구명'].strip())}"
            rows.append(("emd", bjd_code, emd_name, region, 0))

    from psycopg2.extras import execute_values
    execute_values(cur,
        "INSERT INTO common_code (group_id, code, name, extra, sort_order) VALUES %s "
        "ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra",
        rows, page_size=1000)

    conn.commit()

    # 검증
    cur.execute("SELECT COUNT(*) FROM common_code WHERE group_id = 'emd'")
    count = cur.fetchone()[0]
    conn.close()

    logger.info(f"읍면동 코드 적재 완료: {count}건")


if __name__ == "__main__":
    main()
