"""trade_top — 신고일 기준 최고가 TOP 5 + 직전 기간 대비 신고 급증 동네 TOP 5.

의미론 (변경 금지):
- 최고가: 신고일(created_at) 기준 최근 N일, 단지별 최고가 1건 (DISTINCT ON).
- 급증: 직전 동일 기간 대비 증가 건수 — 카운트만으로 '급증' 표현 금지 (spec §5-5).
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import apply_overrides, build_trade_top_copy
from scripts.insta_cards.datasources import (
    open_local_db,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    Metric,
    Narrative,
    Publication,
    Series,
)

LIST_SIZE = 5
MIN_REPORT_COUNT = 20  # 표본 미달 지역 제외 (제안서 '표본 적은 지역 순위 제외')


def fetch_top_price_trades(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        SELECT pnu, apt_display_name, sgg_cd, deal_amount, exclu_use_ar
        FROM (
            SELECT DISTINCT ON (COALESCE(m.pnu, t.sgg_cd || ':' || t.apt_nm))
                m.pnu,
                COALESCE(a.display_name, a.bld_nm, t.apt_nm) AS apt_display_name,
                t.sgg_cd,
                t.deal_amount,
                t.exclu_use_ar
            FROM trade_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            LEFT JOIN apartments a ON a.pnu = m.pnu
            WHERE t.created_at >= NOW() - (%s || ' days')::interval
            ORDER BY COALESCE(m.pnu, t.sgg_cd || ':' || t.apt_nm),
                     t.deal_amount DESC
        ) per_complex
        ORDER BY deal_amount DESC
        LIMIT %s
        """,
        [days, LIST_SIZE],
    )
    names = _load_sigungu_names(conn)
    return [
        {
            "pnu": r["pnu"],
            "apt_display_name": r["apt_display_name"],
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "deal_amount": r["deal_amount"],
            "exclu_use_ar": r["exclu_use_ar"],
        }
        for r in rows
    ]


def fetch_hot_districts(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        WITH current_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        ), prev_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval * 2
              AND created_at <  NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        )
        SELECT c.sgg_cd,
               c.cnt AS current_count,
               COALESCE(p.cnt, 0) AS prev_count,
               c.cnt - COALESCE(p.cnt, 0) AS delta
        FROM current_window c
        LEFT JOIN prev_window p ON p.sgg_cd = c.sgg_cd
        WHERE c.cnt >= %s AND c.cnt > COALESCE(p.cnt, 0)
        ORDER BY delta DESC, c.cnt DESC
        LIMIT %s
        """,
        [days, days, days, MIN_REPORT_COUNT, LIST_SIZE],
    )
    if not rows:
        return []
    names = _load_sigungu_names(conn)
    return [
        {
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "current_count": r["current_count"],
            "prev_count": r["prev_count"],
            "delta": r["delta"],
        }
        for r in rows
    ]


def _load_sigungu_names(conn) -> dict[str, str]:
    rows = query_all(
        conn,
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["sigungu"],
    )
    return {
        r["code"]: f"{r['name']}({r['extra']})"
        if r["extra"] and r["extra"] != r["name"]
        else r["name"]
        for r in rows
    }


def build_publication(
    price_rows: list[dict],
    hot_rows: list[dict],
    days: int,
    *,
    slug: str,
    status: str,
    published_at: str | None,
    copy_overrides: dict | None,
) -> Publication:
    if len(price_rows) < LIST_SIZE:
        raise ValueError(
            f"최고가 거래가 {len(price_rows)}건 — {LIST_SIZE}건 미만이라 발행 중단"
        )
    if len(hot_rows) < LIST_SIZE:
        raise ValueError(
            f"급증 조건(현재 {MIN_REPORT_COUNT}건 이상 + 직전 대비 증가) 충족 지역이 "
            f"{len(hot_rows)}곳 — {LIST_SIZE}곳 미만이라 발행 중단"
        )

    from scripts.insta_cards.theme import format_eok

    items = tuple(
        Item(
            rank=i + 1,
            name=r["apt_display_name"] or "-",
            region=r["sigungu_name"],
            pnu=r["pnu"],
            metrics=(
                Metric("거래가", format_eok(r["deal_amount"]), ""),
                Metric("전용면적", f"{r['exclu_use_ar']:.0f}㎡", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(price_rows)
    )
    secondary = tuple(
        Item(
            rank=i + 1,
            name=r["sigungu_name"],
            region=None,
            pnu=None,
            metrics=(
                Metric("신고 건수", f"{r['current_count']:,}건", ""),
                Metric("직전 대비", f"+{r['delta']:,}건", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(hot_rows)
    )

    copy = build_trade_top_copy(days, price_rows[0]["deal_amount"])
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    period_label = f"신고일 기준 최근 {days}일"
    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.TRADE_TOP,
        title=f"최근 {days}일 신고 최고가 TOP 5",
        eyebrow=f"신고일 기준 · 최근 {days}일",
        hook=copy.hook,
        summary="신고일 기준 최고가 거래와 신고가 크게 늘어난 동네를 모았습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=period_label,
        cover_image="01-cover.png",
        cover_alt=f"최근 {days}일 아파트 신고 최고가 TOP 5 카드",
        conditions=(
            Condition("기간", period_label),
            Condition("집계 단위", "단지별 최고가 1건"),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=secondary,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            "최고가: 신고일 기준 최근 기간, 단지별 최고가 1건만 집계",
            f"급증: 직전 {days}일 대비 신고 건수 증가분 (현재 {MIN_REPORT_COUNT}건 이상 지역만)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고일 기준이라 실제 계약 시점과 다를 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(),  # 랭킹은 넛지 조건이 아님 — 가짜 의도 부여 금지 (PRD Q3)
    )


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        price_rows = fetch_top_price_trades(conn, args.days)
        hot_rows = fetch_hot_districts(conn, args.days)
    finally:
        conn.close()
    return build_publication(
        price_rows,
        hot_rows,
        args.days,
        slug=slug,
        status=status,
        published_at=published_at,
        copy_overrides=copy_overrides,
    )
