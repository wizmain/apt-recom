"""생활안전지도 범죄주의구간 WMS → 아파트별 범죄등급 수집.

WMS GetMap으로 아파트 반경 400m 타일을 받아 픽셀 색상에서 등급(0~10) 추출.
- 0: 데이터 없음 (투명 영역, 주로 안전한 지역)
- 1~3: 낮은 위험 (노란색)
- 4~6: 중간 위험 (주황색)
- 7~10: 높은 위험 (빨간색)

사용법:
  python -m batch.safety.collect_crime_hotspot [--limit N] [--workers N]
"""

import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import numpy as np
import requests
from PIL import Image

from batch.db import get_connection, query_all, get_dict_cursor
from batch.logger import setup_logger

WMS_URL = (
    "https://www.safemap.go.kr/geoserver_pos/safemap/wms"
    "?service=WMS&version=1.1.1&request=GetMap"
    "&layers=A2SM_CRMNLHSPOT_F1_TOT"
    "&srs=EPSG:3857&width=64&height=64"
    "&format=image/png&transparent=true"
)
WMS_HEADERS = {"Referer": "https://www.safemap.go.kr/"}
RADIUS_M = 400
TILE_SIZE = 64


def _to_epsg3857(lat: float, lng: float) -> tuple[float, float]:
    """WGS84(EPSG:4326) → Web Mercator(EPSG:3857)."""
    x = lng * 20037508.34 / 180
    y_rad = math.log(math.tan((90 + lat) * math.pi / 360))
    y = y_rad / (math.pi / 180) * 20037508.34 / 180
    return x, y


def _hue_to_grade(hue: float) -> int:
    """Hue(0~360) → 범죄등급(1~10). 60=노랑(1), 0=빨강(10)."""
    return max(1, min(10, round(10 - hue / 6.67)))


def fetch_crime_grade(lat: float, lng: float) -> float:
    """아파트 좌표의 반경 400m 평균 범죄등급(0~10) 반환."""
    x, y = _to_epsg3857(lat, lng)
    bbox = f"{x - RADIUS_M},{y - RADIUS_M},{x + RADIUS_M},{y + RADIUS_M}"
    url = f"{WMS_URL}&bbox={bbox}"

    try:
        r = requests.get(url, timeout=15, headers=WMS_HEADERS)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            return -1  # 오류
    except (requests.RequestException, Exception):
        return -1

    img = Image.open(BytesIO(r.content)).convert("RGBA")
    arr = np.array(img)

    grades = []
    for py in range(TILE_SIZE):
        for px in range(TILE_SIZE):
            r_, g_, b_, a_ = arr[py, px]
            if a_ < 50:
                continue
            # RGB → HSV
            rf, gf, bf = r_ / 255.0, g_ / 255.0, b_ / 255.0
            mx, mn = max(rf, gf, bf), min(rf, gf, bf)
            diff = mx - mn
            if diff < 0.05 or mx < 0.1:
                continue  # 무채색/어두운색 무시
            # Hue 계산
            if mx == rf:
                hue = 60 * ((gf - bf) / diff % 6)
            elif mx == gf:
                hue = 60 * ((bf - rf) / diff + 2)
            else:
                hue = 60 * ((rf - gf) / diff + 4)
            if hue < 0:
                hue += 360
            # 히트맵 범위: 0(빨강)~60(노랑)
            if hue <= 65:
                grades.append(_hue_to_grade(hue))

    if not grades:
        return 0.0  # 투명 = 데이터 없음 (안전)
    return round(float(np.mean(grades)), 2)


def collect_crime_hotspots(conn, logger, limit=None, workers=10):
    """전체 아파트의 범죄주의구간 등급 수집."""
    sql = """
        SELECT a.pnu, a.lat, a.lng
        FROM apartments a
        LEFT JOIN apt_safety_score s ON a.pnu = s.pnu
        WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL
          AND (s.crime_hotspot_grade IS NULL OR s.crime_hotspot_grade < 0)
        ORDER BY a.pnu
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    apts = query_all(conn, sql)
    total = len(apts)
    if total == 0:
        logger.info("수집 대상 없음 (모든 아파트 수집 완료)")
        return 0

    logger.info(f"범죄주의구간 수집 시작: {total:,}건 (workers={workers})")

    results = {}
    errors = 0
    start = time.time()

    def _task(apt):
        return apt["pnu"], fetch_crime_grade(apt["lat"], apt["lng"])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_task, apt): apt for apt in apts}
        for i, future in enumerate(as_completed(futures), 1):
            pnu, grade = future.result()
            if grade < 0:
                errors += 1
                results[pnu] = -1  # 재시도 대상
            else:
                results[pnu] = grade

            if i % 500 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate / 60 if rate > 0 else 0
                logger.info(f"  진행: {i:,}/{total:,} ({i/total*100:.1f}%) "
                            f"속도={rate:.0f}/s ETA={eta:.1f}분 오류={errors}")

    # DB 업데이트
    cur = get_dict_cursor(conn)
    updated = 0
    for pnu, grade in results.items():
        cur.execute(
            "UPDATE apt_safety_score SET crime_hotspot_grade = %s WHERE pnu = %s",
            [grade, pnu])
        updated += 1

    conn.commit()
    elapsed = time.time() - start
    logger.info(f"범죄주의구간 수집 완료: {updated:,}건 ({elapsed:.0f}초, 오류={errors})")
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    logger = setup_logger("crime_hotspot")
    conn = get_connection()
    try:
        collect_crime_hotspots(conn, logger, limit=args.limit, workers=args.workers)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
