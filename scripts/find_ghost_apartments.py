"""의심 아파트 레코드 탐지 및 CSV 저장.

카테고리:
  [1] 브랜드명 + 1995년 이전 준공 + K-APT 미연동 + 거래 0건 (유령 — 신뢰도 매우 높음)
  [2] 브랜드명 + 세대수 < 50 + K-APT 미연동 + 거래 0건
  [3] 전반적 유령 (K-APT · area_info · 거래 모두 없음)
  [4] 시군구 + 단지명 중복
  [5] 사용승인일 포맷 이상

사용: .venv/bin/python -m scripts.find_ghost_apartments
출력: reports/ghost_apartments_{category}.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

from web.backend.database import DictConnection

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# 2000년대 이후 런칭 주요 브랜드 — 1990년 이전 준공이면 이름 오염 가능성
BRANDS = [
    "자이", "래미안", "푸르지오", "블루밍", "힐스테이트", "e편한세상", "이편한세상",
    "아이파크", "롯데캐슬", "SK뷰", "센트럴", "더샵", "꿈에그린", "데시앙",
    "스위첸", "해모로", "리슈빌", "한라비발디", "서희스타힐스", "호반베르디움",
    "금호어울림", "대림e편한", "현대홈타운", "하이페리온",
]
BRAND_RE = "|".join(BRANDS)

COMMON_COLS = (
    "a.pnu, a.bld_nm, a.use_apr_day, a.total_hhld_cnt, a.dong_count, "
    "a.max_floor, a.sigungu_code, a.plat_plc, a.new_plat_plc"
)


def _save(rows, filename):
    path = REPORTS_DIR / filename
    if not rows:
        print(f"  {filename}: 0 rows (skipped)")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename}: {len(rows):,} rows → {path}")


def main():
    conn = DictConnection()
    try:
        print("[1] 브랜드명 + 1995 이전 + K-APT없음 + 거래0")
        q1 = f"""
            SELECT {COMMON_COLS}
            FROM apartments a
            LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
            WHERE a.bld_nm ~ %s
              AND a.use_apr_day ~ '^[12][0-9]{{7}}$'
              AND a.use_apr_day < '19950101'
              AND k.pnu IS NULL
              AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping WHERE pnu = a.pnu)
            ORDER BY a.sigungu_code, a.use_apr_day
        """
        _save([dict(r) for r in conn.execute(q1, [BRAND_RE]).fetchall()],
              "ghost_apartments_1_brand_old.csv")

        print("[2] 브랜드명 + 세대수<50 + K-APT없음 + 거래0")
        q2 = f"""
            SELECT {COMMON_COLS}
            FROM apartments a
            LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
            WHERE a.bld_nm ~ %s
              AND a.total_hhld_cnt < 50
              AND k.pnu IS NULL
              AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping WHERE pnu = a.pnu)
            ORDER BY a.sigungu_code, a.bld_nm
        """
        _save([dict(r) for r in conn.execute(q2, [BRAND_RE]).fetchall()],
              "ghost_apartments_2_brand_small.csv")

        print("[3] 유령 (K-APT·area_info·거래 모두 없음)")
        q3 = f"""
            SELECT {COMMON_COLS}
            FROM apartments a
            LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
            LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
            WHERE k.pnu IS NULL AND ai.pnu IS NULL
              AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping WHERE pnu = a.pnu)
            ORDER BY a.sigungu_code, a.bld_nm
        """
        _save([dict(r) for r in conn.execute(q3).fetchall()],
              "ghost_apartments_3_orphan.csv")

        print("[4] 시군구+단지명 중복 그룹")
        q4 = """
            SELECT sigungu_code, bld_nm, COUNT(*) AS dup_count,
                   STRING_AGG(pnu, ', ') AS pnus,
                   STRING_AGG(COALESCE(plat_plc, ''), ' | ') AS addrs
            FROM apartments
            WHERE bld_nm IS NOT NULL AND bld_nm != ''
            GROUP BY sigungu_code, bld_nm
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC, sigungu_code, bld_nm
        """
        _save([dict(r) for r in conn.execute(q4).fetchall()],
              "ghost_apartments_4_duplicate_names.csv")

        print("[5] 사용승인일 포맷 이상")
        q5 = f"""
            SELECT {COMMON_COLS}
            FROM apartments a
            WHERE a.use_apr_day IS NOT NULL
              AND a.use_apr_day !~ '^[12][0-9]{{7}}$'
            ORDER BY a.sigungu_code
        """
        _save([dict(r) for r in conn.execute(q5).fetchall()],
              "ghost_apartments_5_bad_date.csv")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
