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


def _build_csv_name_to_codes(conn):
    """CSV 지역명 → 시군구코드 매핑.

    population_by_district 테이블 + 아파트 DB 기반으로 구축.
    경기도 수원시 같은 시 단위는 하위 구 코드 전부 매핑.
    """
    from collections import defaultdict
    from batch.db import query_all

    SIDO_SHORT = {
        "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
        "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
        "울산광역시": "울산", "세종특별자치시": "세종",
        "경기도": "경기도", "강원특별자치도": "강원도",
        "충청북도": "충북", "충청남도": "충남",
        "전북특별자치도": "전북", "전라남도": "전남",
        "경상북도": "경북", "경상남도": "경남",
        "제주특별자치도": "제주",
    }

    # 1) population_by_district에서 기본 매핑 구축
    pop_rows = query_all(conn,
        "SELECT sigungu_code, sido_name, sigungu_name FROM population_by_district WHERE age_group = '계'")

    name_to_codes = defaultdict(set)
    for r in pop_rows:
        short_sido = SIDO_SHORT.get(r["sido_name"], r["sido_name"][:2])
        sgg_name = r["sigungu_name"]
        code = r["sigungu_code"]
        # 출장소 등 제외 (5자리만)
        if len(code) != 5:
            continue
        # "경기도 수원시장안구" → "경기도 수원시"로 그룹핑
        for city_suffix in ("장안구", "권선구", "팔달구", "영통구",  # 수원
                            "수정구", "중원구", "분당구",  # 성남
                            "만안구", "동안구",  # 안양
                            "원미구", "소사구", "오정구",  # 부천
                            "상록구", "단원구",  # 안산
                            "덕양구", "일산동구", "일산서구",  # 고양
                            "처인구", "기흥구", "수지구",  # 용인
                            "동부출장소", "동탄출장소",  # 화성
                            "풍양출장소", "송탄출장소", "안중출장소",
                            "검단출장소", "영종출장소", "용유출장소"):
            if sgg_name.endswith(city_suffix):
                city_name = sgg_name.replace(city_suffix, "").rstrip()
                if city_name:
                    name_to_codes[f"{short_sido} {city_name}"].add(code)
                break
        else:
            name_to_codes[f"{short_sido} {sgg_name}"].add(code)

    # 2) 비수도권 광역시 표준코드 보충 (population에 없는 지역)
    METRO_CODES = {
        "부산 중구": ["26110"], "부산 서구": ["26140"], "부산 동구": ["26170"],
        "부산 영도구": ["26200"], "부산 부산진구": ["26230"], "부산 동래구": ["26260"],
        "부산 남구": ["26290"], "부산 북구": ["26320"], "부산 강서구": ["26350"],
        "부산 해운대구": ["26380"], "부산 사하구": ["26410"], "부산 금정구": ["26440"],
        "부산 연제구": ["26470"], "부산 수영구": ["26500"], "부산 사상구": ["26530"],
        "부산 기장군": ["26710"],
        "대구 중구": ["27110"], "대구 동구": ["27140"], "대구 서구": ["27170"],
        "대구 남구": ["27200"], "대구 북구": ["27230"], "대구 수성구": ["27260"],
        "대구 달서구": ["27290"], "대구 달성군": ["27710"], "대구 군위군": ["27720"],
        "광주 동구": ["29110"], "광주 서구": ["29140"], "광주 남구": ["29155"],
        "광주 북구": ["29170"], "광주 광산구": ["29200"],
        "대전 동구": ["30110"], "대전 중구": ["30140"], "대전 서구": ["30170"],
        "대전 유성구": ["30200"], "대전 대덕구": ["30230"],
        "울산 중구": ["31110"], "울산 남구": ["31140"], "울산 동구": ["31170"],
        "울산 북구": ["31200"], "울산 울주군": ["31710"],
        "세종시": ["36110"],
    }
    for name, codes in METRO_CODES.items():
        for c in codes:
            name_to_codes[name].add(c)

    # 3) 아파트 DB에 있지만 매핑 안 된 코드 → 3자리 prefix로 시 단위 보충
    apt_rows = query_all(conn,
        "SELECT DISTINCT LEFT(sigungu_code, 5) as sgg FROM apartments WHERE sigungu_code IS NOT NULL")
    apt_codes = {r["sgg"] for r in apt_rows}
    mapped_codes = set()
    for codes in name_to_codes.values():
        mapped_codes.update(codes)
    unmapped = apt_codes - mapped_codes
    if unmapped:
        # 3자리 prefix 기준으로 기존 매핑에 추가
        prefix_to_name = {}
        for name, codes in name_to_codes.items():
            for c in codes:
                prefix_to_name[c[:3]] = name
        for code in unmapped:
            name = prefix_to_name.get(code[:3])
            if name:
                name_to_codes[name].add(code)

    return {name: sorted(codes) for name, codes in name_to_codes.items()}


def load_crime_stats_2024(conn, logger):
    """경찰청 범죄통계 2024 → sigungu_crime_detail 갱신."""
    path = DATA_DIR / "경찰청_범죄 발생 지역별 통계_20241231.csv"
    if not path.exists():
        logger.warning(f"범죄통계 파일 없음: {path}")
        return 0

    df = pd.read_csv(path, encoding="cp949")
    logger.info(f"  범죄통계: {len(df)}행 × {len(df.columns)}열")

    # 범죄중분류 → 5대 범죄 카테고리 매핑 (합산 대상)
    CRIME_CATEGORY = {
        ("강력범죄", "살인기수"): "murder",
        ("강력범죄", "살인미수등"): "murder",
        ("강력범죄", "강도"): "robbery",
        ("강력범죄", "강간"): "sexual_assault",
        ("강력범죄", "유사강간"): "sexual_assault",
        ("강력범죄", "강제추행"): "sexual_assault",
        ("강력범죄", "기타 강간/강제추행등"): "sexual_assault",
        ("절도범죄", "절도범죄"): "theft",
        ("폭력범죄", "상해"): "violence",
        ("폭력범죄", "폭행"): "violence",
        ("폭력범죄", "체포/감금"): "violence",
        ("폭력범죄", "협박"): "violence",
        ("폭력범죄", "약취/유인"): "violence",
        ("폭력범죄", "폭력행위등"): "violence",
        ("폭력범죄", "공갈"): "violence",
        ("폭력범죄", "손괴"): "violence",
    }

    # 시군구 컬럼 추출 (외국 제외)
    sgg_cols = [c for c in df.columns if c not in ("범죄대분류", "범죄중분류") and "외국" not in c]

    # 시군구별 5대 범죄 합산
    from collections import defaultdict
    sgg_crimes: dict[str, dict[str, int]] = defaultdict(lambda: {
        "murder": 0, "robbery": 0, "sexual_assault": 0, "theft": 0, "violence": 0
    })

    for _, row in df.iterrows():
        key = (row["범죄대분류"], row["범죄중분류"])
        crime_type = CRIME_CATEGORY.get(key)
        if not crime_type:
            continue
        for sgg in sgg_cols:
            try:
                val = int(row[sgg])
            except (ValueError, TypeError):
                continue
            sgg_crimes[sgg][crime_type] += val

    logger.info(f"  시군구별 범죄 집계: {len(sgg_crimes)}개 지역")

    # CSV 지역명 → 시군구코드 매핑
    name_to_codes = _build_csv_name_to_codes(conn)

    # 인구 데이터 조회 (유동인구 보정용)
    pop_map = {}
    pop_rows = query_all(conn,
        "SELECT sigungu_code, total_pop FROM population_by_district WHERE age_group = '계'")
    for r in pop_rows:
        pop_map[r["sigungu_code"]] = r["total_pop"]

    # sigungu_crime_detail INSERT
    cur = get_dict_cursor(conn)
    insert_rows = []
    matched_count = 0

    for csv_name, crimes in sgg_crimes.items():
        codes = name_to_codes.get(csv_name, [])
        if not codes:
            continue
        matched_count += 1

        total_crime = sum(crimes.values())
        for code in codes:
            resident_pop = pop_map.get(code, 0)
            # 유동인구 보정: 인구 데이터가 없으면 기본 주민등록인구 사용
            effective_pop = resident_pop or 100000
            float_pop_ratio = 1.0
            crime_rate = total_crime / effective_pop * 100000 if effective_pop else 0

            insert_rows.append((
                code,
                crimes["murder"], crimes["robbery"], crimes["sexual_assault"],
                crimes["theft"], crimes["violence"], total_crime,
                resident_pop, effective_pop, round(crime_rate, 1),
                float_pop_ratio, 2024,
            ))

    logger.info(f"  매핑 성공: {matched_count}/{len(sgg_crimes)} 지역 → {len(insert_rows)}건 INSERT")

    if insert_rows:
        cur.execute("DELETE FROM sigungu_crime_detail")
        from psycopg2.extras import execute_values
        execute_values(cur,
            """INSERT INTO sigungu_crime_detail
               (sigungu_code, murder, robbery, sexual_assault, theft, violence,
                total_crime, resident_pop, effective_pop, crime_rate,
                float_pop_ratio, updated_year)
               VALUES %s""",
            insert_rows, page_size=500)
        conn.commit()
        logger.info(f"  sigungu_crime_detail 갱신 완료: {len(insert_rows)}건 (2024년)")

    # 범죄 안전 점수 계산 (가중 범죄율 기반 percentile rank)
    _update_crime_safety_scores(conn, logger)

    return len(insert_rows)


def _update_crime_safety_scores(conn, logger):
    """sigungu_crime_detail의 crime_safety_score를 percentile rank로 갱신."""
    rows = query_all(conn, "SELECT sigungu_code, total_crime, effective_pop FROM sigungu_crime_detail")
    if not rows:
        return

    WEIGHTS = {"murder": 10, "robbery": 5, "sexual_assault": 3, "violence": 2, "theft": 1}
    detail_rows = query_all(conn,
        "SELECT sigungu_code, murder, robbery, sexual_assault, violence, theft, effective_pop FROM sigungu_crime_detail")

    # 가중 범죄율 계산
    rates = {}
    for r in detail_rows:
        w_crime = (
            (r["murder"] or 0) * WEIGHTS["murder"]
            + (r["robbery"] or 0) * WEIGHTS["robbery"]
            + (r["sexual_assault"] or 0) * WEIGHTS["sexual_assault"]
            + (r["violence"] or 0) * WEIGHTS["violence"]
            + (r["theft"] or 0) * WEIGHTS["theft"]
        )
        pop = r["effective_pop"] or 100000
        rates[r["sigungu_code"]] = w_crime / pop * 100000

    # percentile rank → 0~100 (낮은 범죄율 = 높은 점수)
    import numpy as np
    all_rates = np.array(sorted(rates.values()))

    cur = get_dict_cursor(conn)
    for code, rate in rates.items():
        pct = float(np.searchsorted(all_rates, rate)) / len(all_rates) * 100
        score = round(100 - pct, 1)
        cur.execute(
            "UPDATE sigungu_crime_detail SET crime_safety_score = %s WHERE sigungu_code = %s",
            [score, code])
    conn.commit()
    logger.info(f"  범죄 안전 점수 갱신: {len(rates)}건 (percentile rank)")


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
