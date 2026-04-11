"""Admin API router.

모든 엔드포인트에 ADMIN_TOKEN Bearer 인증 적용.
배치 관련 엔드포인트는 로컬 환경에서만 동작 (Railway 503).
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from database import DictConnection, get_connection
from services.admin_auth import require_local_env, verify_admin_token
from services.mgmt_cost_parser import (
    insert_mgmt_costs,
    parse_cost_excel,
    register_new_apartments,
)
from services.scoring import get_max_distances, get_nudge_weights, invalidate_cache

# 캐시 무효화 대상 common_code 그룹
_SCORING_GROUPS = {
    "nudge_weight", "facility_distance", "facility_max_distance",
    "region_profile",
    "facility_decay_metro", "facility_decay_major_city", "facility_decay_provincial",
    "density_factor_metro", "density_factor_major_city", "density_factor_provincial",
    "facility_distance_metro", "facility_distance_major_city", "facility_distance_provincial",
}

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(verify_admin_token)],
)
logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ── 테이블 allowlist ──────────────────────────────────────────

ALLOWED_TABLES: dict[str, list[str]] = {
    "apartments": [
        "pnu",
        "bld_nm",
        "total_hhld_cnt",
        "max_floor",
        "use_apr_day",
        "lat",
        "lng",
        "sigungu_code",
    ],
    "trade_history": [
        "apt_nm",
        "sgg_cd",
        "deal_amount",
        "exclu_use_ar",
        "floor",
        "deal_year",
        "deal_month",
    ],
    "rent_history": [
        "apt_nm",
        "sgg_cd",
        "deposit",
        "monthly_rent",
        "exclu_use_ar",
        "deal_year",
        "deal_month",
    ],
    "apt_price_score": ["pnu", "price_per_m2", "price_score", "jeonse_ratio"],
    "apt_safety_score": [
        "pnu",
        "safety_score",
        "cctv_count_500m",
        "crime_safety_score",
    ],
    "facilities": ["facility_type", "facility_subtype", "name", "lat", "lng"],
    "school_zones": [
        "pnu",
        "elementary_school_name",
        "middle_school_zone",
        "high_school_zone",
    ],
    "apt_vectors": ["pnu"],
}

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _validate_column(table: str, column: str) -> None:
    """allowlist에 포함된 컬럼인지 검증."""
    allowed = ALLOWED_TABLES.get(table, [])
    if column not in allowed:
        raise HTTPException(400, f"허용되지 않은 컬럼입니다: {column}")


# ── 배치 로그 보안 ────────────────────────────────────────────

BATCH_LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "batch", "logs")
)


def _safe_log_path(filename: str) -> str:
    """안전한 로그 파일 경로 반환. basename + .log 확장자만 허용."""
    require_local_env()
    basename = os.path.basename(filename)
    if not basename.endswith(".log"):
        raise HTTPException(400, "유효하지 않은 로그 파일명입니다.")
    full = os.path.join(BATCH_LOG_DIR, basename)
    try:
        if os.path.commonpath([BATCH_LOG_DIR, os.path.abspath(full)]) != BATCH_LOG_DIR:
            raise HTTPException(400, "유효하지 않은 경로입니다.")
    except ValueError:
        raise HTTPException(400, "유효하지 않은 경로입니다.")
    return full


# ── Dashboard ─────────────────────────────────────────────────


@router.get("/dashboard/summary")
async def dashboard_summary():
    """KPI 카드 데이터: 아파트 수, 오늘 거래, 만족도, 커버리지."""
    conn = DictConnection()
    try:
        # 총 아파트 수
        row = conn.execute("SELECT COUNT(*) AS cnt FROM apartments").fetchone()
        total_apts = row["cnt"] if row else 0

        # 이번 주 신규 거래 아파트 수 (trade_history.created_at 기반)
        row = conn.execute(
            "SELECT COUNT(DISTINCT apt_nm) AS cnt FROM trade_history WHERE created_at >= NOW() - INTERVAL '7 days'"
        ).fetchone()
        new_apts_week = row["cnt"] if row else 0

        # 오늘 거래 (deal_year, deal_month, deal_day 기준은 데이터 반영일이므로 created_at 사용)
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM trade_history WHERE created_at >= CURRENT_DATE"
        ).fetchone()
        today_trades = row["cnt"] if row else 0

        # 어제 거래 (비교용)
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM trade_history WHERE created_at >= CURRENT_DATE - INTERVAL '1 day' AND created_at < CURRENT_DATE"
        ).fetchone()
        yesterday_trades = row["cnt"] if row else 0

        # 챗봇 만족도 (최근 30일)
        row = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE rating = 1) AS likes, COUNT(*) AS total FROM chat_feedback WHERE created_at >= NOW() - INTERVAL '30 days'"
        ).fetchone()
        likes = row["likes"] if row else 0
        feedback_total = row["total"] if row else 0
        satisfaction_rate = (
            round(likes / feedback_total * 100, 1) if feedback_total > 0 else 0
        )

        # 지난주 만족도 (비교용)
        row = conn.execute(
            """SELECT COUNT(*) FILTER (WHERE rating = 1) AS likes, COUNT(*) AS total
               FROM chat_feedback
               WHERE created_at >= NOW() - INTERVAL '37 days' AND created_at < NOW() - INTERVAL '7 days'"""
        ).fetchone()
        prev_likes = row["likes"] if row else 0
        prev_total = row["total"] if row else 0
        prev_satisfaction = (
            round(prev_likes / prev_total * 100, 1) if prev_total > 0 else 0
        )

        # 주소 커버리지 (lat/lng가 있는 비율)
        row = conn.execute(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE lat IS NOT NULL AND lng IS NOT NULL) AS covered FROM apartments"
        ).fetchone()
        total_for_coverage = row["total"] if row else 0
        covered = row["covered"] if row else 0
        coverage_pct = (
            round(covered / total_for_coverage * 100, 1)
            if total_for_coverage > 0
            else 0
        )
        uncovered = total_for_coverage - covered

        return {
            "total_apartments": total_apts,
            "new_apartments_week": new_apts_week,
            "today_trades": today_trades,
            "yesterday_trades": yesterday_trades,
            "satisfaction_rate": satisfaction_rate,
            "prev_satisfaction_rate": prev_satisfaction,
            "coverage_pct": coverage_pct,
            "uncovered_count": uncovered,
        }
    finally:
        conn.close()


@router.get("/dashboard/quality")
async def dashboard_quality():
    """테이블별 데이터 품질: 레코드 수, NULL 비율, 최근 갱신."""
    conn = DictConnection()
    try:
        quality = []
        # has_created_at: created_at 컬럼이 있는 테이블만 최근 갱신 시각 조회
        tables_to_check = {
            "apartments": {
                "check_null": "lat",
                "label": "아파트 마스터",
                "has_created_at": False,
            },
            "apt_facility_summary": {
                "check_null": "nearest_distance_m",
                "label": "시설 집계",
                "has_created_at": False,
            },
            "apt_price_score": {
                "check_null": "price_score",
                "label": "가격 점수",
                "has_created_at": False,
            },
            "apt_safety_score": {
                "check_null": "safety_score",
                "label": "안전 점수",
                "has_created_at": False,
            },
            "apt_vectors": {
                "check_null": "vec_basic",
                "label": "벡터 생성",
                "has_created_at": False,
            },
            "trade_history": {
                "check_null": None,
                "label": "매매 이력",
                "has_created_at": True,
            },
            "rent_history": {
                "check_null": None,
                "label": "전월세 이력",
                "has_created_at": True,
            },
        }

        for table, info in tables_to_check.items():
            row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
            total = row["cnt"] if row else 0

            null_pct = 0.0
            if info["check_null"] and total > 0:
                col = info["check_null"]
                row = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col} IS NULL"
                ).fetchone()
                null_count = row["cnt"] if row else 0
                null_pct = round(null_count / total * 100, 1)

            # 최근 갱신 시각 (created_at 컬럼이 있는 테이블만)
            latest = None
            if info["has_created_at"]:
                row = conn.execute(
                    f"SELECT MAX(created_at) AS latest FROM {table}"
                ).fetchone()
                latest = row["latest"] if row else None

            quality.append(
                {
                    "table": table,
                    "label": info["label"],
                    "total_records": total,
                    "null_pct": null_pct,
                    "coverage_pct": round(100 - null_pct, 1),
                    "latest_update": latest.isoformat() if latest else None,
                }
            )

        return {"quality": quality}
    finally:
        conn.close()


# ── Data ──────────────────────────────────────────────────────


TABLES_WITH_CREATED_AT = {"trade_history", "rent_history"}


@router.get("/data/stats")
async def data_stats():
    """전체 테이블 통계 요약."""
    conn = DictConnection()
    try:
        stats = []
        for table in ALLOWED_TABLES:
            row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
            total = row["cnt"] if row else 0

            latest = None
            if table in TABLES_WITH_CREATED_AT:
                row = conn.execute(
                    f"SELECT MAX(created_at) AS latest FROM {table}"
                ).fetchone()
                latest = row["latest"] if row else None

            stats.append(
                {
                    "table": table,
                    "total_records": total,
                    "latest_update": latest.isoformat() if latest else None,
                }
            )
        return {"stats": stats}
    finally:
        conn.close()


@router.get("/data/{table}")
async def data_table(
    table: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search_column: str | None = None,
    search_value: str | None = None,
    order_by: str | None = None,
    order_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    """테이블 데이터 조회. allowlist 테이블/컬럼만 허용."""
    if table not in ALLOWED_TABLES:
        raise HTTPException(400, f"허용되지 않은 테이블입니다: {table}")

    columns = ALLOWED_TABLES[table]
    select_cols = ", ".join(columns)
    params: list = []

    # WHERE 절
    where_clause = ""
    if search_column and search_value:
        _validate_column(table, search_column)
        where_clause = f"WHERE {search_column}::text ILIKE %s"
        params.append(f"%{search_value}%")

    # ORDER BY 절
    order_clause = ""
    if order_by:
        _validate_column(table, order_by)
        order_clause = f"ORDER BY {order_by} {order_dir.upper()}"

    # 페이지네이션
    offset = (page - 1) * page_size

    conn = DictConnection()
    try:
        # 총 건수
        count_sql = f"SELECT COUNT(*) AS cnt FROM {table} {where_clause}"
        row = conn.execute(count_sql, params).fetchone()
        total = row["cnt"] if row else 0

        # 데이터 조회
        data_sql = f"SELECT {select_cols} FROM {table} {where_clause} {order_clause} LIMIT %s OFFSET %s"
        rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

        return {
            "table": table,
            "columns": columns,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "data": [dict(r) for r in rows],
        }
    finally:
        conn.close()


# ── Batch ─────────────────────────────────────────────────────

_LOG_FILENAME_PATTERN = re.compile(r"^batch_\d{8}_\d{6}\.log$")


def _parse_batch_log(filepath: str) -> dict:
    """배치 로그 파일에서 요약 정보 파싱."""
    filename = os.path.basename(filepath)
    result = {
        "filename": filename,
        "batch_type": None,
        "status": "unknown",
        "started_at": None,
        "duration": None,
        "total_records": 0,
    }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return result

    for line in lines:
        if "batch_type=" in line.lower() or "--type" in line:
            for btype in ("trade", "quarterly", "annual", "mgmt_cost"):
                if btype in line.lower():
                    result["batch_type"] = btype
                    break

        # 타임스탬프 추출 (첫 번째 줄)
        if result["started_at"] is None:
            ts_match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            if ts_match:
                result["started_at"] = ts_match.group(1)

        if "SUCCESS" in line.upper() or "완료" in line:
            result["status"] = "success"
        elif "WARNING" in line.upper() or "경고" in line:
            if result["status"] != "error":
                result["status"] = "warning"
        elif "ERROR" in line.upper() or "실패" in line:
            result["status"] = "error"

        # 처리 건수
        count_match = re.search(r"(\d+)\s*건", line)
        if count_match:
            result["total_records"] = max(
                result["total_records"], int(count_match.group(1))
            )

    # 소요 시간 (마지막 타임스탬프 - 첫 타임스탬프)
    if lines and result["started_at"]:
        for line in reversed(lines):
            ts_match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            if ts_match:
                try:
                    start = datetime.strptime(result["started_at"], "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                    result["duration"] = str(end - start)
                except ValueError:
                    pass
                break

    return result


@router.get("/batch/history")
async def batch_history():
    """배치 실행 이력 (batch/logs/ 파싱). 로컬 전용."""
    require_local_env()

    if not os.path.isdir(BATCH_LOG_DIR):
        return {"history": [], "message": "로그 디렉토리가 없습니다."}

    log_files = sorted(
        [f for f in os.listdir(BATCH_LOG_DIR) if f.endswith(".log")],
        reverse=True,
    )[:30]  # 최근 30개

    history = []
    for filename in log_files:
        filepath = os.path.join(BATCH_LOG_DIR, filename)
        history.append(_parse_batch_log(filepath))

    return {"history": history}


@router.get("/batch/logs/{filename}")
async def batch_log_detail(filename: str):
    """배치 로그 상세. 로컬 전용, basename + .log만 허용."""
    filepath = _safe_log_path(filename)

    if not os.path.isfile(filepath):
        raise HTTPException(404, "로그 파일을 찾을 수 없습니다.")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(500, f"로그 파일 읽기 실패: {e}")

    return {
        "filename": os.path.basename(filepath),
        "content": content,
        "size_bytes": os.path.getsize(filepath),
    }


# ── Feedback ──────────────────────────────────────────────────


@router.get("/feedback/list")
async def feedback_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    rating: int | None = None,
    tag: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """피드백 목록 (필터 + 페이지네이션)."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor)
        conditions = []
        params: list = []

        if rating is not None:
            conditions.append("rating = %s")
            params.append(rating)
        if tag:
            conditions.append("%s = ANY(tags)")
            params.append(tag)
        if date_from:
            conditions.append("created_at >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= %s")
            params.append(date_to)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        cur.execute(f"SELECT COUNT(*) AS cnt FROM chat_feedback {where}", params)
        total = cur.fetchone()["cnt"]

        cur.execute(
            f"""SELECT id, user_message, assistant_message, rating, tags, comment, session_id, created_at
                FROM chat_feedback {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = cur.fetchall()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "data": [
                {
                    **dict(r),
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/feedback/trend")
async def feedback_trend(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
):
    """만족도 추이 (일/주/월)."""
    conn = DictConnection()
    try:
        if period == "daily":
            trunc = "day"
            interval = "30 days"
        elif period == "weekly":
            trunc = "week"
            interval = "90 days"
        else:
            trunc = "month"
            interval = "365 days"

        rows = conn.execute(
            f"""SELECT DATE_TRUNC(%s, created_at) AS period,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE rating = 1) AS likes
                FROM chat_feedback
                WHERE created_at >= NOW() - INTERVAL '{interval}'
                GROUP BY period
                ORDER BY period""",
            [trunc],
        ).fetchall()

        return {
            "period_type": period,
            "data": [
                {
                    "period": r["period"].isoformat() if r["period"] else None,
                    "total": r["total"],
                    "likes": r["likes"],
                    "satisfaction_rate": round(r["likes"] / r["total"] * 100, 1)
                    if r["total"] > 0
                    else 0,
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


# ── Scoring ───────────────────────────────────────────────────


@router.get("/scoring/weights")
async def scoring_weights():
    """넛지 가중치 조회."""
    weights = get_nudge_weights()
    max_distances = get_max_distances()
    return {
        "nudge_weights": weights,
        "max_distances": max_distances,
    }


@router.get("/scoring/distribution")
async def scoring_distribution(
    nudge_id: str = Query(..., description="넛지 ID (예: cost, pet, commute)"),
):
    """넛지별 점수 분포 히스토그램 데이터."""
    conn = DictConnection()
    try:
        # apt_facility_summary에서 넛지별 점수를 계산하려면 scoring 로직이 필요
        # 여기서는 간단히 시설 거리 분포를 반환
        weights = get_nudge_weights()
        if nudge_id not in weights:
            raise HTTPException(400, f"존재하지 않는 넛지 ID: {nudge_id}")

        subtypes = list(weights[nudge_id].keys())
        if not subtypes:
            return {"nudge_id": nudge_id, "histogram": [], "stats": {}}

        # 첫 번째 주요 시설의 거리 분포로 대표
        primary_subtype = subtypes[0]
        rows = conn.execute(
            """SELECT
                   WIDTH_BUCKET(nearest_distance_m, 0, 5000, 20) AS bucket,
                   COUNT(*) AS cnt,
                   AVG(nearest_distance_m) AS avg_dist
               FROM apt_facility_summary
               WHERE facility_subtype = %s AND nearest_distance_m IS NOT NULL
               GROUP BY bucket
               ORDER BY bucket""",
            [primary_subtype],
        ).fetchall()

        # 전체 통계
        stat_row = conn.execute(
            """SELECT COUNT(*) AS cnt,
                      AVG(nearest_distance_m) AS avg_dist,
                      MIN(nearest_distance_m) AS min_dist,
                      MAX(nearest_distance_m) AS max_dist,
                      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nearest_distance_m) AS median_dist
               FROM apt_facility_summary
               WHERE facility_subtype = %s AND nearest_distance_m IS NOT NULL""",
            [primary_subtype],
        ).fetchone()

        return {
            "nudge_id": nudge_id,
            "primary_subtype": primary_subtype,
            "subtypes": subtypes,
            "histogram": [
                {
                    "bucket": r["bucket"],
                    "count": r["cnt"],
                    "avg_distance_m": round(float(r["avg_dist"]), 1)
                    if r["avg_dist"]
                    else 0,
                }
                for r in rows
            ],
            "stats": {
                "total": stat_row["cnt"] if stat_row else 0,
                "avg_distance_m": round(float(stat_row["avg_dist"]), 1)
                if stat_row and stat_row["avg_dist"]
                else 0,
                "min_distance_m": round(float(stat_row["min_dist"]), 1)
                if stat_row and stat_row["min_dist"]
                else 0,
                "max_distance_m": round(float(stat_row["max_dist"]), 1)
                if stat_row and stat_row["max_dist"]
                else 0,
                "median_distance_m": round(float(stat_row["median_dist"]), 1)
                if stat_row and stat_row["median_dist"]
                else 0,
            },
        }
    finally:
        conn.close()


# ── Codes CRUD (Phase 3) ─────────────────────────────────────


class CodeCreateRequest(BaseModel):
    code: str
    name: str
    extra: str = ""
    sort_order: int = 0


class CodeUpdateRequest(BaseModel):
    name: str | None = None
    extra: str | None = None
    sort_order: int | None = None


@router.post("/codes/{group}")
async def create_code(group: str, req: CodeCreateRequest):
    """공통코드 추가."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM common_code WHERE group_id = %s AND code = %s",
            [group, req.code],
        )
        if cur.fetchone():
            raise HTTPException(409, f"이미 존재하는 코드입니다: {group}/{req.code}")

        cur.execute(
            """INSERT INTO common_code (group_id, code, name, extra, sort_order)
               VALUES (%s, %s, %s, %s, %s)""",
            [group, req.code, req.name, req.extra, req.sort_order],
        )
        conn.commit()
        logger.info(f"Admin: code created {group}/{req.code}")
        return {"message": f"코드 추가됨: {group}/{req.code}"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"코드 추가 실패: {e}")
    finally:
        conn.close()


@router.put("/codes/{group}/{code}")
async def update_code(group: str, code: str, req: CodeUpdateRequest):
    """공통코드 수정."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM common_code WHERE group_id = %s AND code = %s",
            [group, code],
        )
        if not cur.fetchone():
            raise HTTPException(404, f"코드를 찾을 수 없습니다: {group}/{code}")

        updates = []
        params: list = []
        if req.name is not None:
            updates.append("name = %s")
            params.append(req.name)
        if req.extra is not None:
            updates.append("extra = %s")
            params.append(req.extra)
        if req.sort_order is not None:
            updates.append("sort_order = %s")
            params.append(req.sort_order)

        if not updates:
            raise HTTPException(400, "수정할 필드가 없습니다.")

        params.extend([group, code])
        cur.execute(
            f"UPDATE common_code SET {', '.join(updates)} WHERE group_id = %s AND code = %s",
            params,
        )
        conn.commit()
        logger.info(f"Admin: code updated {group}/{code}")

        # 가중치/거리기준 관련 그룹이면 캐시 무효화
        if group in _SCORING_GROUPS:
            invalidate_cache()

        return {"message": f"코드 수정됨: {group}/{code}"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"코드 수정 실패: {e}")
    finally:
        conn.close()


@router.delete("/codes/{group}/{code}")
async def delete_code(group: str, code: str):
    """공통코드 삭제."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM common_code WHERE group_id = %s AND code = %s RETURNING code",
            [group, code],
        )
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(404, f"코드를 찾을 수 없습니다: {group}/{code}")
        conn.commit()
        logger.info(f"Admin: code deleted {group}/{code}")

        if group in _SCORING_GROUPS:
            invalidate_cache()

        return {"message": f"코드 삭제됨: {group}/{code}"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"코드 삭제 실패: {e}")
    finally:
        conn.close()


# ── Scoring weights update (Phase 3) ─────────────────────────


class WeightUpdateRequest(BaseModel):
    nudge_id: str
    weights: dict[str, float]  # {subtype: weight}


@router.put("/scoring/weights")
async def update_scoring_weights(req: WeightUpdateRequest):
    """넛지 가중치 수정."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        updated = 0
        for subtype, weight in req.weights.items():
            code = f"{req.nudge_id}:{subtype}"
            cur.execute(
                "UPDATE common_code SET extra = %s WHERE group_id = %s AND code = %s",
                [str(weight), "nudge_weight", code],
            )
            updated += cur.rowcount

        if updated == 0:
            raise HTTPException(
                404, f"해당 넛지의 가중치를 찾을 수 없습니다: {req.nudge_id}"
            )

        conn.commit()
        invalidate_cache()
        logger.info(
            f"Admin: scoring weights updated for {req.nudge_id} ({updated} rows)"
        )
        return {
            "message": f"가중치 수정됨: {req.nudge_id} ({updated}개)",
            "updated": updated,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"가중치 수정 실패: {e}")
    finally:
        conn.close()


# ── Knowledge (Phase 3) ──────────────────────────────────────

_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploaded_pdfs"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/knowledge/list")
async def admin_knowledge_list():
    """관리자 전용 문서 목록."""
    from services.knowledge_manager import list_documents

    docs = list_documents()
    return {"documents": docs, "total": len(docs)}


@router.post("/knowledge/upload")
async def admin_knowledge_upload(
    file: UploadFile = File(...),
    category: str = Form("general"),
):
    """관리자 전용 PDF 업로드."""
    from services.knowledge_manager import upload_pdf

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드 가능합니다.")

    dest = _UPLOAD_DIR / file.filename
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"파일 저장 실패: {e}")

    try:
        result = await upload_pdf(str(dest), category=category)
        logger.info(f"Admin: knowledge uploaded {file.filename}")
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"PDF 처리 실패: {e}")


@router.delete("/knowledge/{doc_id}")
async def admin_knowledge_delete(doc_id: str):
    """관리자 전용 문서 삭제."""
    from services.knowledge_manager import delete_document

    try:
        result = delete_document(doc_id)
        logger.info(f"Admin: knowledge deleted {doc_id}")
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"문서 삭제 실패: {e}")


# ── Batch Trigger (Phase 4) ──────────────────────────────────

ALLOWED_BATCH_TYPES = {"trade", "quarterly", "annual", "mgmt_cost"}

# type별 timeout (초)
BATCH_TIMEOUTS = {
    "trade": 3600,
    "quarterly": 7200,
    "annual": 1800,
    "mgmt_cost": 7200,
}

# 파일 기반 lock
_batch_locks: dict[str, threading.Lock] = {
    t: threading.Lock() for t in ALLOWED_BATCH_TYPES
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class BatchTriggerRequest(BaseModel):
    batch_type: str
    dry_run: bool = True  # 기본값 True — 명시적 False 전달 시에만 실제 실행


@router.post("/batch/trigger")
async def batch_trigger(req: BatchTriggerRequest):
    """수동 배치 실행. 로컬 전용, dry_run=True 기본값."""
    require_local_env()

    if req.batch_type not in ALLOWED_BATCH_TYPES:
        raise HTTPException(400, f"허용되지 않은 배치 타입: {req.batch_type}")

    lock = _batch_locks[req.batch_type]
    if not lock.acquire(blocking=False):
        raise HTTPException(409, f"{req.batch_type} 배치가 이미 실행 중입니다.")

    try:
        cmd = [
            sys.executable,
            "-m",
            "batch.run",
            "--type",
            req.batch_type,
        ]
        if req.dry_run:
            cmd.append("--dry-run")

        timeout = BATCH_TIMEOUTS.get(req.batch_type, 3600)

        logger.info(
            f"Admin: batch trigger {req.batch_type} "
            f"{'(dry-run)' if req.dry_run else '(LIVE)'} timeout={timeout}s"
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_PROJECT_ROOT),
        )

        return {
            "batch_type": req.batch_type,
            "dry_run": req.dry_run,
            "exit_code": result.returncode,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "status": "success" if result.returncode == 0 else "error",
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"{req.batch_type} 배치 실행 시간 초과 ({timeout}초)")
    except Exception as e:
        raise HTTPException(500, f"배치 실행 실패: {e}")
    finally:
        lock.release()


# ── Mgmt Cost Excel Upload (관리비 엑셀 등록) ────────────────

_XLSX_SUFFIX = ".xlsx"


def _validate_xlsx(file: UploadFile, label: str) -> None:
    """업로드 파일이 .xlsx인지 검증."""
    if not file.filename or not file.filename.lower().endswith(_XLSX_SUFFIX):
        raise HTTPException(400, f"{label} 파일은 .xlsx만 허용됩니다.")


@router.post("/mgmt-cost/preview")
async def mgmt_cost_preview(
    cost_file: UploadFile = File(...),
    area_file: UploadFile | None = File(None),
    basic_file: UploadFile | None = File(None),
):
    """관리비 엑셀 미리보기. 면적/기본정보 파일은 선택."""
    _validate_xlsx(cost_file, "관리비")
    if area_file and area_file.filename:
        _validate_xlsx(area_file, "면적")
    if basic_file and basic_file.filename:
        _validate_xlsx(basic_file, "기본정보")

    cost_tmp = None
    area_tmp = None
    basic_tmp = None
    try:
        cost_tmp = tempfile.NamedTemporaryFile(suffix=_XLSX_SUFFIX, delete=False)
        cost_tmp.write(await cost_file.read())
        cost_tmp.close()

        area_path = None
        if area_file and area_file.filename:
            area_tmp = tempfile.NamedTemporaryFile(suffix=_XLSX_SUFFIX, delete=False)
            area_tmp.write(await area_file.read())
            area_tmp.close()
            area_path = area_tmp.name

        basic_path = None
        if basic_file and basic_file.filename:
            basic_tmp = tempfile.NamedTemporaryFile(suffix=_XLSX_SUFFIX, delete=False)
            basic_tmp.write(await basic_file.read())
            basic_tmp.close()
            basic_path = basic_tmp.name

        rows, errors, new_apts = parse_cost_excel(cost_tmp.name, area_path, basic_path)

        preview_rows = [
            {
                "pnu": r["pnu"],
                "year_month": r["year_month"],
                "kapt_name": r["kapt_name"],
                "cost_per_unit": r["cost_per_unit"],
                "common_cost": r["common_cost"],
                "individual_cost": r["individual_cost"],
                "repair_fund": r["repair_fund"],
                "total_cost": r["total_cost"],
            }
            for r in rows[:100]
        ]

        new_apts_preview = [
            {
                "kapt_code": a["kapt_code"],
                "kapt_name": a["kapt_name"],
                "address": a.get("address", ""),
                "road_address": a.get("road_address", ""),
                "hhld": a.get("hhld", 0),
            }
            for a in new_apts[:100]
        ]

        return {
            "total": len(rows),
            "preview_count": len(preview_rows),
            "rows": preview_rows,
            "errors": errors,
            "new_apts": new_apts_preview,
            "new_apts_count": len(new_apts),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("관리비 미리보기 실패")
        raise HTTPException(500, f"엑셀 파싱 실패: {e}")
    finally:
        if cost_tmp:
            os.unlink(cost_tmp.name)
        if area_tmp:
            os.unlink(area_tmp.name)
        if basic_tmp:
            os.unlink(basic_tmp.name)


# ── 신규 아파트 등록 (비동기) ──

_register_tasks: dict[str, dict] = {}


class RegisterNewRequest(BaseModel):
    new_apts: list[dict]


@router.post("/mgmt-cost/register-new")
async def mgmt_cost_register_new(req: RegisterNewRequest):
    """신규 아파트 지오코딩 + DB 등록 (BackgroundTask)."""
    if not os.getenv("KAKAO_API_KEY"):
        raise HTTPException(400, "KAKAO_API_KEY가 설정되지 않았습니다.")
    if not req.new_apts:
        raise HTTPException(400, "등록할 단지가 없습니다.")

    task_id = str(uuid.uuid4())[:8]
    _register_tasks[task_id] = {
        "status": "running",
        "current": 0,
        "total": len(req.new_apts),
        "registered": 0,
        "errors": [],
        "message": "시작 중...",
        "started_at": datetime.now(),
        "ended_at": None,
    }

    def run():
        state = _register_tasks[task_id]
        try:

            def on_progress(current: int, total: int, msg: str = ""):
                state["current"] = current
                state["message"] = msg

            count, errs = register_new_apartments(req.new_apts, on_progress)
            state["status"] = "completed"
            state["registered"] = count
            state["errors"] = errs
        except Exception as e:
            state["status"] = "failed"
            state["errors"].append(str(e))
            logger.exception("신규 등록 실패")
        finally:
            state["ended_at"] = datetime.now()

    threading.Thread(target=run, daemon=True).start()

    return {
        "task_id": task_id,
        "total": len(req.new_apts),
        "message": f"신규 {len(req.new_apts)}건 등록 시작",
    }


@router.get("/mgmt-cost/register-status/{task_id}")
async def mgmt_cost_register_status(task_id: str):
    """신규 등록 진행 상태 조회."""
    state = _register_tasks.get(task_id)
    if not state:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    elapsed = 0
    if state["started_at"]:
        end = state["ended_at"] or datetime.now()
        elapsed = int((end - state["started_at"]).total_seconds())

    return {
        "status": state["status"],
        "current": state["current"],
        "total": state["total"],
        "registered": state["registered"],
        "errors": state["errors"][:50],  # 최대 50건만
        "message": state["message"],
        "elapsed_seconds": elapsed,
    }


@router.post("/mgmt-cost/import")
async def mgmt_cost_import(
    cost_file: UploadFile = File(...),
    area_file: UploadFile | None = File(None),
):
    """관리비 엑셀 업로드 → DB 적재 (UPSERT). 면적 파일은 선택."""
    _validate_xlsx(cost_file, "관리비")
    if area_file and area_file.filename:
        _validate_xlsx(area_file, "면적")

    cost_tmp = None
    area_tmp = None
    try:
        cost_tmp = tempfile.NamedTemporaryFile(suffix=_XLSX_SUFFIX, delete=False)
        cost_tmp.write(await cost_file.read())
        cost_tmp.close()

        area_path = None
        if area_file and area_file.filename:
            area_tmp = tempfile.NamedTemporaryFile(suffix=_XLSX_SUFFIX, delete=False)
            area_tmp.write(await area_file.read())
            area_tmp.close()
            area_path = area_tmp.name

        rows, errors, _new = parse_cost_excel(cost_tmp.name, area_path)

        if not rows:
            raise HTTPException(400, "적재할 데이터가 없습니다.")

        imported = insert_mgmt_costs(rows)
        logger.info(f"Admin: mgmt_cost imported {imported}건")

        return {
            "imported": imported,
            "errors": errors,
            "message": f"관리비 {imported}건 적재 완료 (오류 {len(errors)}건)",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("관리비 적재 실패")
        raise HTTPException(500, f"관리비 적재 실패: {e}")
    finally:
        if cost_tmp:
            os.unlink(cost_tmp.name)
        if area_tmp:
            os.unlink(area_tmp.name)
