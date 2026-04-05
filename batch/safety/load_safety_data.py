"""안전 데이터 CSV 적재 — 보안등, 소방서, 교통사고, 범죄통계.

사용법:
  python -m batch.safety.load_safety_data
"""

import hashlib
import re
from pathlib import Path

import pandas as pd

from batch.db import get_connection, get_dict_cursor, query_all
from batch.logger import setup_logger

DATA_DIR = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "안전자료"


def _make_fid(prefix: str, lat: float, lng: float, name: str) -> str:
    """좌표+이름 기반 안정적 facility_id."""
    name_hash = hashlib.md5((name or "").encode()).hexdigest()[:8]
    return f"{prefix}_{lat:.4f}_{lng:.4f}_{name_hash}"


def load_security_lights(conn, logger):
    """전국보안등표준데이터 → facilities 테이블."""
    path = DATA_DIR / "전국보안등정보표준데이터.csv"
    if not path.exists():
        logger.warning(f"보안등 파일 없음: {path}")
        return 0

    df = pd.read_csv(path, encoding="cp949")
    df = df.dropna(subset=["위도", "경도"])
    df = df[(df["위도"] > 33) & (df["위도"] < 39) & (df["경도"] > 124) & (df["경도"] < 132)]
    logger.info(f"  보안등: {len(df):,}건 (좌표 유효)")

    cur = get_dict_cursor(conn)
    cur.execute("DELETE FROM facilities WHERE facility_subtype = 'security_light'")

    rows = []
    seen = set()
    for _, r in df.iterrows():
        lat, lng = float(r["위도"]), float(r["경도"])
        name = str(r.get("보안등위치명", ""))[:200]
        fid = _make_fid("SCL", lat, lng, name)
        coord_key = (round(lat, 6), round(lng, 6))
        if fid in seen or coord_key in seen:
            continue
        seen.add(fid)
        seen.add(coord_key)
        addr = str(r.get("소재지도로명주소") or r.get("소재지지번주소") or "")[:300]
        rows.append((fid, "safety", "security_light", name, lat, lng, addr))

    from psycopg2.extras import execute_values
    execute_values(cur,
        "INSERT INTO facilities (facility_id, facility_type, facility_subtype, name, lat, lng, address) VALUES %s "
        "ON CONFLICT (facility_id) DO NOTHING",
        rows, page_size=5000)
    conn.commit()
    logger.info(f"  보안등 적재: {len(rows):,}건")
    return len(rows)


def load_fire_stations(conn, logger):
    """소방서+119안전센터 좌표 → facilities 테이블."""
    # 소방서 좌표
    path1 = DATA_DIR / "소방청_전국소방서 좌표현황(XY좌표)_20240901.csv"
    rows = []
    seen = set()

    if path1.exists():
        df1 = pd.read_csv(path1, encoding="cp949")
        for _, r in df1.iterrows():
            try:
                lat, lng = float(r["X좌표"]), float(r["Y좌표"])
            except (ValueError, TypeError):
                continue
            if not (33 < lat < 39 and 124 < lng < 132):
                # X/Y 뒤바뀜 확인
                if 33 < lng < 39 and 124 < lat < 132:
                    lat, lng = lng, lat
                else:
                    continue
            name = str(r.get("소방서 및 안전센터명", ""))[:200]
            ftype = str(r.get("유형", ""))
            subtype = "fire_station" if "소방서" in ftype or "소방서" in name else "fire_center"
            fid = _make_fid("FIR", lat, lng, name)
            if fid not in seen:
                seen.add(fid)
                addr = str(r.get("주소", ""))[:300]
                rows.append((fid, "safety", subtype, name, lat, lng, addr))
        logger.info(f"  소방서 좌표: {len(rows):,}건")

    # 119안전센터 (좌표 없음 → Kakao 검색 필요, 일단 주소만 적재 가능한 건 건너뜀)
    # 소방서 좌표 파일에 119안전센터도 포함되어 있음

    # 좌표+subtype 중복 제거
    coord_seen = set()
    deduped = []
    for r in rows:
        key = (r[2], round(r[4], 6), round(r[5], 6))  # subtype, lat, lng
        if key not in coord_seen:
            coord_seen.add(key)
            deduped.append(r)

    if deduped:
        cur = get_dict_cursor(conn)
        cur.execute("DELETE FROM facilities WHERE facility_subtype IN ('fire_station', 'fire_center')")
        from psycopg2.extras import execute_values
        execute_values(cur,
            "INSERT INTO facilities (facility_id, facility_type, facility_subtype, name, lat, lng, address) VALUES %s "
            "ON CONFLICT (facility_id) DO NOTHING",
            deduped, page_size=1000)
        conn.commit()
        logger.info(f"  소방/119센터 적재: {len(deduped):,}건 (중복 {len(rows)-len(deduped)}건 제거)")
    return len(rows)


def load_traffic_accidents(conn, logger):
    """교통사고 다발지역 → traffic_accident_hotspot 테이블."""
    path = DATA_DIR / "17_24_lg.csv"
    if not path.exists():
        logger.warning(f"교통사고 파일 없음: {path}")
        return 0

    df = pd.read_csv(path, encoding="euc-kr")
    logger.info(f"  교통사고 다발지역: {len(df):,}건")

    cur = get_dict_cursor(conn)
    cur.execute("TRUNCATE traffic_accident_hotspot")

    rows = []
    for _, r in df.iterrows():
        try:
            lat = float(r.get("위도", 0))
            lng = float(r.get("경도", 0))
        except (ValueError, TypeError):
            continue
        rows.append((
            str(r.get("시도시군구명", ""))[:50],
            str(r.get("지점명", ""))[:200],
            int(r.get("사고건수", 0)),
            int(r.get("사상자수", 0)),
            int(r.get("사망자수", 0)),
            int(r.get("중상자수", 0)),
            lat, lng,
            str(r.get("법정동코드", ""))[:10],
        ))

    from psycopg2.extras import execute_values
    execute_values(cur,
        "INSERT INTO traffic_accident_hotspot (sigungu_name, spot_name, accident_cnt, casualty_cnt, death_cnt, serious_cnt, lat, lng, bjd_code) VALUES %s",
        rows, page_size=1000)
    conn.commit()
    logger.info(f"  교통사고 적재: {len(rows):,}건")
    return len(rows)


def load_crime_stats_2024(conn, logger):
    """경찰청 범죄통계 2024 → sigungu_crime_detail 갱신."""
    path = DATA_DIR / "경찰청_범죄 발생 지역별 통계_20241231.csv"
    if not path.exists():
        logger.warning(f"범죄통계 파일 없음: {path}")
        return 0

    df = pd.read_csv(path, encoding="cp949")
    logger.info(f"  범죄통계: {len(df)}행 × {len(df.columns)}열")

    # 시군구별 5대 범죄 집계 (행: 범죄유형, 열: 시군구)
    # 범죄대분류-범죄중분류 매핑
    crime_map = {
        ("강력범죄", "살인기수"): "murder",
        ("강력범죄", "강도"): "robbery",
        ("강력범죄", "성폭력"): "sexual_assault",
        ("폭력범죄", "폭력"): "violence",
        ("재산범죄", "절도"): "theft",
    }

    # 시군구 컬럼 추출 (외국 제외)
    sgg_cols = [c for c in df.columns if c not in ("범죄대분류", "범죄중분류") and "외국" not in c]

    sgg_crimes = {}
    for _, row in df.iterrows():
        key = (row["범죄대분류"], row["범죄중분류"])
        crime_type = crime_map.get(key)
        if not crime_type:
            continue
        for sgg in sgg_cols:
            if sgg not in sgg_crimes:
                sgg_crimes[sgg] = {}
            try:
                sgg_crimes[sgg][crime_type] = int(row[sgg])
            except (ValueError, TypeError):
                pass

    logger.info(f"  시군구별 범죄: {len(sgg_crimes)}개 지역")

    # sigungu_crime_detail 갱신은 시군구 코드 매칭이 필요하여 별도 처리
    # 여기서는 데이터 확인만
    if sgg_crimes:
        sample = list(sgg_crimes.items())[:3]
        for name, crimes in sample:
            logger.info(f"    {name}: {crimes}")

    return len(sgg_crimes)


def main():
    logger = setup_logger("load_safety")
    conn = get_connection()

    try:
        logger.info("안전 데이터 적재 시작")
        load_security_lights(conn, logger)
        load_fire_stations(conn, logger)
        load_traffic_accidents(conn, logger)
        load_crime_stats_2024(conn, logger)
        logger.info("안전 데이터 적재 완료")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
