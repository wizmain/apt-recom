"""전국 학군 정보 갱신 — SHP 폴리곤 + 아파트 좌표 Spatial Join.

초등학교 통학구역, 중학교 학교군, 고등학교 학교군을 아파트에 매핑하여
school_zones 테이블 갱신.

데이터 소스:
  - apt_eda/data/hakguzi/elementry/초등학교통학구역.shp
  - apt_eda/data/hakguzi/middle/중학교학교군.shp
  - apt_eda/data/hakguzi/high/고등학교학교군.shp
  - apt_eda/data/hakguzi/재단법인한국지방교육행정연구재단_학교학구도연계정보_20250922.csv
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from batch.db import query_all, execute_values_chunked

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HAKGUZI_DIR = PROJECT_ROOT / "apt_eda" / "data" / "hakguzi"


def _load_apartments(conn):
    """DB에서 좌표 있는 아파트 로드 → GeoDataFrame."""
    rows = query_all(conn, """
        SELECT pnu, bld_nm, lat, lng, sigungu_code
        FROM apartments
        WHERE lat IS NOT NULL AND lng IS NOT NULL
          AND total_hhld_cnt > 0 AND pnu NOT LIKE 'TRADE_%%'
    """)
    if not rows:
        return None

    df = pd.DataFrame(rows)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lng"], df["lat"]),
        crs="EPSG:4326",
    )
    return gdf


def _load_zone_shp(shp_path):
    """SHP 파일 로드 + WGS84 변환."""
    gdf = gpd.read_file(shp_path)
    gdf = gdf.to_crs(epsg=4326)
    return gdf


def _load_school_linkage():
    """학구ID → 학교ID/학교명 연계 CSV 로드."""
    linkage_path = HAKGUZI_DIR / "재단법인한국지방교육행정연구재단_학교학구도연계정보_20250922.csv"
    if not linkage_path.exists():
        return {}
    df = pd.read_csv(linkage_path, encoding="cp949")
    # 학교급별 딕셔너리
    result = {}
    for _, row in df.iterrows():
        zone_id = row.get("학구ID", "")
        if zone_id:
            result[zone_id] = {
                "school_id": row.get("학교ID", ""),
                "school_name": row.get("학교명", ""),
                "school_type": row.get("학교급구분", ""),
            }
    return result


def _spatial_join(apt_gdf, zone_gdf):
    """아파트 GeoDataFrame + 학구 폴리곤 → Spatial Join."""
    joined = gpd.sjoin(apt_gdf, zone_gdf, how="left", predicate="within")
    # 중복 제거 (겹치는 학구 → 첫 번째만)
    joined = joined.drop_duplicates(subset=["pnu"], keep="first")
    return joined


def update_school_zones(conn, logger):
    """전국 학군 정보 갱신."""
    # 1. 아파트 로드
    apt_gdf = _load_apartments(conn)
    if apt_gdf is None:
        logger.info("아파트 데이터 없음")
        return 0

    logger.info(f"아파트 로드: {len(apt_gdf):,}건")

    # 2. 학구-학교 연계 로드
    linkage = _load_school_linkage()
    logger.info(f"학구-학교 연계: {len(linkage):,}건")

    # 3. 초등학교 통학구역
    elem_path = HAKGUZI_DIR / "elementry" / "초등학교통학구역.shp"
    if elem_path.exists():
        logger.info("초등학교 통학구역 Spatial Join...")
        elem_zone = _load_zone_shp(elem_path)
        elem_joined = _spatial_join(apt_gdf, elem_zone)
        elem_map = {}
        for _, row in elem_joined.iterrows():
            pnu = row["pnu"]
            zone_id = row.get("HAKGUDO_ID")
            if pd.notna(zone_id):
                link = linkage.get(zone_id, {})
                elem_map[pnu] = {
                    "elementary_school_name": str(row.get("HAKGUDO_NM", "")).replace("통학구역", ""),
                    "elementary_school_id": link.get("school_id", ""),
                    "elementary_school_full_name": link.get("school_name", ""),
                    "elementary_zone_id": zone_id,
                    "edu_office_name": str(row.get("EDU_NM", "")).replace("교육지원청", ""),
                    "edu_district": str(row.get("EDU_NM", "")),
                }
        logger.info(f"  초등학교 매칭: {len(elem_map):,}건")
    else:
        elem_map = {}
        logger.warning("  초등학교 SHP 없음")

    # 4. 중학교 학교군
    mid_path = HAKGUZI_DIR / "middle" / "중학교학교군.shp"
    if mid_path.exists():
        logger.info("중학교 학교군 Spatial Join...")
        mid_zone = _load_zone_shp(mid_path)
        mid_joined = _spatial_join(apt_gdf, mid_zone)
        mid_map = {}
        for _, row in mid_joined.iterrows():
            pnu = row["pnu"]
            zone_id = row.get("HAKGUDO_ID")
            if pd.notna(zone_id):
                mid_map[pnu] = {
                    "middle_school_zone": str(row.get("HAKGUDO_NM", "")),
                    "middle_school_zone_id": zone_id,
                }
        logger.info(f"  중학교 매칭: {len(mid_map):,}건")
    else:
        mid_map = {}
        logger.warning("  중학교 SHP 없음")

    # 5. 고등학교 학교군
    high_path = HAKGUZI_DIR / "high" / "고등학교학교군.shp"
    if high_path.exists():
        logger.info("고등학교 학교군 Spatial Join...")
        high_zone = _load_zone_shp(high_path)
        high_joined = _spatial_join(apt_gdf, high_zone)
        high_map = {}
        for _, row in high_joined.iterrows():
            pnu = row["pnu"]
            zone_id = row.get("HAKGUDO_ID")
            if pd.notna(zone_id):
                zone_nm = str(row.get("HAKGUDO_NM", ""))
                high_map[pnu] = {
                    "high_school_zone": zone_nm,
                    "high_school_zone_id": zone_id,
                    "high_school_zone_type": "평준화" if "평준화" in zone_nm else "비평준화",
                }
        logger.info(f"  고등학교 매칭: {len(high_map):,}건")
    else:
        high_map = {}
        logger.warning("  고등학교 SHP 없음")

    # 6. 통합 + DB 적재
    all_pnus = set(elem_map.keys()) | set(mid_map.keys()) | set(high_map.keys())
    logger.info(f"학군 매핑 아파트: {len(all_pnus):,}건")

    upsert_rows = []
    for pnu in all_pnus:
        e = elem_map.get(pnu, {})
        m = mid_map.get(pnu, {})
        h = high_map.get(pnu, {})
        upsert_rows.append((
            pnu,
            e.get("elementary_school_name"),
            e.get("elementary_school_id"),
            e.get("elementary_school_full_name"),
            e.get("elementary_zone_id"),
            m.get("middle_school_zone"),
            m.get("middle_school_zone_id"),
            h.get("high_school_zone"),
            h.get("high_school_zone_id"),
            h.get("high_school_zone_type"),
            e.get("edu_office_name"),
            e.get("edu_district"),
        ))

    if upsert_rows:
        cur = conn.cursor()
        cur.execute("TRUNCATE school_zones")
        execute_values_chunked(conn,
            """INSERT INTO school_zones (pnu, elementary_school_name, elementary_school_id,
               elementary_school_full_name, elementary_zone_id, middle_school_zone,
               middle_school_zone_id, high_school_zone, high_school_zone_id,
               high_school_zone_type, edu_office_name, edu_district) VALUES %s""",
            upsert_rows)
        logger.info(f"school_zones 갱신 완료: {len(upsert_rows):,}건")

    return len(upsert_rows)
