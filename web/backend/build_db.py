"""CSV -> SQLite data loading script for apartment recommendation app."""

import re
import time
from pathlib import Path

import pandas as pd

from database import get_connection, create_tables, create_indexes

DATA_DIR = Path(__file__).parent.parent.parent / "apt_eda" / "data"


def load_apartments(conn):
    """Load apartment master data."""
    print("Loading apartments...")
    src = DATA_DIR / "processed" / "fm_apt_master_with_coords.csv"
    df = pd.read_csv(src)
    df = df.rename(columns={
        "PNU": "pnu",
        "bldNm": "bld_nm",
        "total_hhldCnt": "total_hhld_cnt",
        "representative_useAprDay": "use_apr_day",
        "platPlc": "plat_plc",
        "newPlatPlc": "new_plat_plc",
        "bjdCode": "bjd_code",
    })
    df["sigungu_code"] = df["bjd_code"].astype(str).str[:5]
    cols = ["pnu", "bld_nm", "total_hhld_cnt", "dong_count", "max_floor",
            "use_apr_day", "plat_plc", "new_plat_plc", "bjd_code", "sigungu_code",
            "lat", "lng"]
    df = df.drop_duplicates(subset=["pnu"], keep="first")
    df[cols].to_sql("apartments", conn, if_exists="append", index=False)
    print(f"  apartments: {len(df):,} rows")


def load_facilities(conn):
    """Load facilities data."""
    print("Loading facilities...")
    src = DATA_DIR / "processed" / "fm_all_facilities_normalized.csv"
    df = pd.read_csv(src)
    cols = ["facility_id", "facility_type", "facility_subtype", "name", "lat", "lng", "address"]
    df[cols].to_sql("facilities", conn, if_exists="append", index=False)
    print(f"  facilities: {len(df):,} rows")


def load_facility_mapping(conn):
    """Load facility mapping with chunked reading (45M rows)."""
    print("Loading facility mapping (chunked)...")
    src = DATA_DIR / "processed" / "fm_apt_facility_mapping.csv"
    cols_select = ["PNU", "facility_id", "facility_type", "facility_subtype", "distance_m"]
    total_rows = 0
    t0 = time.time()

    def _insert_or_ignore(table, conn, keys, data_iter):
        cols = ", ".join(keys)
        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT OR IGNORE INTO {table.name} ({cols}) VALUES ({placeholders})"
        conn.executemany(sql, data_iter)

    for i, chunk in enumerate(pd.read_csv(src, chunksize=500_000, usecols=cols_select)):
        chunk = chunk.rename(columns={"PNU": "pnu"})
        chunk.to_sql("apt_facility_mapping", conn, if_exists="append", index=False,
                      method=_insert_or_ignore)
        total_rows += len(chunk)
        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  chunk {i+1}: {total_rows:,} rows loaded ({elapsed:.0f}s)")

    elapsed = time.time() - t0
    print(f"  facility mapping: {total_rows:,} rows ({elapsed:.0f}s)")


def load_facility_summary(conn):
    """Generate facility summary from mapping data using SQL aggregation."""
    print("Loading facility summary...")
    conn.execute("""
        INSERT INTO apt_facility_summary
        SELECT pnu, facility_subtype,
            MIN(distance_m),
            SUM(CASE WHEN distance_m <= 1000 THEN 1 ELSE 0 END),
            SUM(CASE WHEN distance_m <= 3000 THEN 1 ELSE 0 END),
            COUNT(*)
        FROM apt_facility_mapping
        GROUP BY pnu, facility_subtype
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM apt_facility_summary").fetchone()[0]
    print(f"  facility summary: {count:,} rows")


def load_trade_history(conn):
    """Load trade history data."""
    print("Loading trade history...")
    src = DATA_DIR / "raw" / "apt_trade_total_2023_2026.csv"
    df = pd.read_csv(src, low_memory=False)
    df = df.rename(columns={
        "aptSeq": "apt_seq",
        "sggCd": "sgg_cd",
        "aptNm": "apt_nm",
        "dealAmount": "deal_amount",
        "excluUseAr": "exclu_use_ar",
        "dealYear": "deal_year",
        "dealMonth": "deal_month",
        "dealDay": "deal_day",
        "buildYear": "build_year",
    })
    df["deal_amount"] = df["deal_amount"].astype(str).str.replace(",", "").astype(int)
    df["sgg_cd"] = df["sgg_cd"].astype(str)
    cols = ["apt_seq", "sgg_cd", "apt_nm", "deal_amount", "exclu_use_ar",
            "floor", "deal_year", "deal_month", "deal_day", "build_year"]
    df[cols].to_sql("trade_history", conn, if_exists="append", index=False)
    print(f"  trade_history: {len(df):,} rows")


def load_rent_history(conn):
    """Load rent history data."""
    print("Loading rent history...")
    src = DATA_DIR / "raw" / "apt_rent_total_2023_2026.csv"
    df = pd.read_csv(src, low_memory=False)
    df = df.rename(columns={
        "aptSeq": "apt_seq",
        "sggCd": "sgg_cd",
        "aptNm": "apt_nm",
        "excluUseAr": "exclu_use_ar",
        "dealYear": "deal_year",
        "dealMonth": "deal_month",
        "dealDay": "deal_day",
        "monthlyRent": "monthly_rent",
    })
    df["deposit"] = df["deposit"].astype(str).str.replace(",", "")
    df["deposit"] = pd.to_numeric(df["deposit"], errors="coerce").fillna(0).astype(int)
    df["sgg_cd"] = df["sgg_cd"].astype(str)
    cols = ["apt_seq", "sgg_cd", "apt_nm", "deposit", "monthly_rent",
            "exclu_use_ar", "floor", "deal_year", "deal_month", "deal_day"]
    df[cols].to_sql("rent_history", conn, if_exists="append", index=False)
    print(f"  rent_history: {len(df):,} rows")


def _normalize_name(name: str) -> str:
    """Normalize apartment name for matching."""
    if not isinstance(name, str):
        return ""
    name = re.sub(r"\(.*?\)", "", name)  # remove parenthetical content
    name = re.sub(r"[^a-zA-Z0-9가-힣]", "", name)  # remove special chars
    return name.upper()


def load_trade_apt_mapping(conn):
    """Match trade apt_seq to apartments.pnu using name matching."""
    print("Loading trade-apt mapping...")

    # Get distinct trade entries
    trade_df = pd.read_sql(
        "SELECT DISTINCT apt_seq, sgg_cd, apt_nm FROM trade_history", conn
    )
    trade_df["norm_name"] = trade_df["apt_nm"].apply(_normalize_name)

    # Get apartment entries
    apt_df = pd.read_sql(
        "SELECT pnu, bld_nm, sigungu_code FROM apartments", conn
    )
    apt_df["norm_name"] = apt_df["bld_nm"].apply(_normalize_name)

    # Join on sgg_cd == sigungu_code AND normalized name
    merged = trade_df.merge(
        apt_df,
        left_on=["sgg_cd", "norm_name"],
        right_on=["sigungu_code", "norm_name"],
        how="inner",
    )
    merged["match_method"] = "exact_name"

    result = merged[["apt_seq", "pnu", "apt_nm", "sgg_cd", "match_method"]].drop_duplicates(
        subset=["apt_seq"], keep="first"
    )
    result.to_sql("trade_apt_mapping", conn, if_exists="append", index=False)

    total_trade = len(trade_df)
    matched = len(result)
    rate = matched / total_trade * 100 if total_trade > 0 else 0
    print(f"  trade_apt_mapping: {matched:,}/{total_trade:,} matched ({rate:.1f}%)")


def load_school_zones(conn):
    """Merge 4 school zone CSVs and load."""
    print("Loading school zones...")

    # Elementary
    elem = pd.read_csv(DATA_DIR / "processed" / "fm_apt_school_zone_enriched.csv")
    elem = elem.rename(columns={
        "PNU": "pnu",
        "school_name": "elementary_school_name",
        "school_id": "elementary_school_id",
        "school_full_name": "elementary_school_full_name",
        "school_zone_id": "elementary_zone_id",
    })
    elem = elem[["pnu", "elementary_school_name", "elementary_school_id",
                  "elementary_school_full_name", "elementary_zone_id"]]

    # Middle
    mid = pd.read_csv(DATA_DIR / "processed" / "fm_apt_middle_school_zone.csv")
    mid = mid.rename(columns={
        "PNU": "pnu",
        "middle_school_zone_name": "middle_school_zone",
    })
    mid = mid[["pnu", "middle_school_zone", "middle_school_zone_id"]]

    # High
    high = pd.read_csv(DATA_DIR / "processed" / "fm_apt_high_school_zone.csv")
    high = high.rename(columns={
        "PNU": "pnu",
        "high_school_zone_name": "high_school_zone",
    })
    high = high[["pnu", "high_school_zone", "high_school_zone_id", "high_school_zone_type"]]

    # Edu district
    edu = pd.read_csv(DATA_DIR / "processed" / "fm_apt_edu_district.csv")
    edu = edu.rename(columns={
        "PNU": "pnu",
        "edu_district_name": "edu_district",
    })
    edu = edu[["pnu", "edu_office_name", "edu_district"]]

    # Merge all on pnu
    result = elem.merge(mid, on="pnu", how="outer")
    result = result.merge(high, on="pnu", how="outer")
    result = result.merge(edu, on="pnu", how="outer")
    result = result.drop_duplicates(subset=["pnu"], keep="first")

    cols = ["pnu", "elementary_school_name", "elementary_school_id",
            "elementary_school_full_name", "elementary_zone_id",
            "middle_school_zone", "middle_school_zone_id",
            "high_school_zone", "high_school_zone_id", "high_school_zone_type",
            "edu_office_name", "edu_district"]
    result[cols].to_sql("school_zones", conn, if_exists="append", index=False)
    print(f"  school_zones: {len(result):,} rows")


def main():
    db_path = Path(__file__).parent / "apt_web.db"
    if db_path.exists():
        db_path.unlink()

    # CLI 스크립트는 FastAPI lifespan 바깥이므로 pool 미초기화.
    # use_pool=False 로 pool 우회해 직접 connect.
    conn = get_connection(db_path, use_pool=False)
    conn.execute("PRAGMA synchronous=OFF")
    create_tables(conn)

    t0 = time.time()
    load_apartments(conn)
    load_facilities(conn)
    load_facility_mapping(conn)
    load_facility_summary(conn)
    load_trade_history(conn)
    load_rent_history(conn)
    load_trade_apt_mapping(conn)
    load_school_zones(conn)

    print("\nCreating indexes...")
    create_indexes(conn)
    conn.close()

    elapsed = time.time() - t0
    size_mb = db_path.stat().st_size / 1024 / 1024
    print(f"\nBuild complete: {db_path} ({size_mb:.1f} MB) in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
