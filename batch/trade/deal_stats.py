"""실적(매매+전월세) 집계 SQL 빌더 — 매핑 감사·재매칭 공용.

임대 단지는 실적이 전월세에만 있어 매매만 집계하면 층·면적 검증이 빈 채로
통과한다. 면적은 건수 가중으로 모은다(mapping_checks.area_match_ratio).

두 가지 성능 함정을 피한다 (2026-08 실측 — 전체 실행 집계가 4시간을 넘겨 중단).
  1) "%(seqs)s IS NULL OR apt_seq = ANY(%(seqs)s)" 패턴은 플래너가 인덱스를
     버리게 만든다 → 필터 유무로 SQL 을 조립한다 (조각은 전부 고정 문자열)
  2) CTE 를 행마다 참조하는 상관 서브쿼리는 매 행 재스캔이다 → GROUP BY
     집계를 만들어 LEFT JOIN 한다
수정 후 전체 집계(거래 317만 + 전월세 659만)가 분 단위로 끝난다.

필터 모드에서는 raw 자체를 target 조인으로 묶는다 — 소수 대상 감사(배치의
신규 매핑 검사)가 전량 집계를 유발하면 안 된다.
"""

from __future__ import annotations

_TEMPLATE = """
WITH {target_cte}raw AS (
    SELECT t.apt_seq, 't' src, t.floor, t.deal_year, t.build_year, t.exclu_use_ar area
      FROM trade_history t {trade_join}
    UNION ALL
    SELECT r.apt_seq, 'r', r.floor, r.deal_year, NULL, r.exclu_use_ar
      FROM rent_history r {rent_join}
),
area_cnt AS (
  SELECT apt_seq, ROUND(area::numeric, 2) area, COUNT(*) cnt
  FROM raw WHERE area > 0 GROUP BY 1, 2
),
area_agg AS (
  SELECT apt_seq, ARRAY_AGG(ARRAY[area::float8, cnt::float8]) AS areas
  FROM area_cnt GROUP BY apt_seq
),
apt_area_agg AS (
  SELECT pnu, ARRAY_AGG(exclusive_area) AS areas FROM apt_area_type GROUP BY pnu
),
deal AS (
  SELECT apt_seq,
         COUNT(*) FILTER (WHERE src = 't') trades,
         COUNT(*) FILTER (WHERE src = 'r') rents,
         MAX(floor) max_floor,
         MIN(deal_year) min_deal_year,
         PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY build_year) median_build_year
  FROM raw GROUP BY apt_seq
)
SELECT m.apt_seq, m.apt_nm, m.sgg_cd, m.pnu, m.match_method,
       d.trades, d.rents, d.max_floor, d.min_deal_year, d.median_build_year,
       aa.areas AS areas,
       a.bld_nm, a.max_floor AS apt_max_floor, a.use_apr_day,
       ap.areas AS apt_areas
FROM trade_apt_mapping m
JOIN deal d ON d.apt_seq = m.apt_seq
JOIN apartments a ON a.pnu = m.pnu
LEFT JOIN area_agg aa ON aa.apt_seq = m.apt_seq
LEFT JOIN apt_area_agg ap ON ap.pnu = m.pnu
ORDER BY (d.trades + d.rents) DESC
"""

_JOIN = "JOIN target g ON g.apt_seq = {alias}.apt_seq"


def build_deal_stats_sql(by_seqs: bool = False, by_pnus: bool = False) -> str:
    """대상 필터에 맞는 집계 SQL 을 만든다.

    by_seqs → %(seqs)s (apt_seq 목록), by_pnus → %(pnus)s (매핑 pnu 목록).
    둘 다 False 면 전체 집계다. 파라미터는 psycopg2 %(name)s 로만 전달되며
    이 함수가 조립하는 조각은 전부 고정 문자열이다.
    """
    conds = []
    if by_seqs:
        conds.append("m2.apt_seq = ANY(%(seqs)s)")
    if by_pnus:
        conds.append("m2.pnu = ANY(%(pnus)s)")
    if not conds:
        return _TEMPLATE.format(target_cte="", trade_join="", rent_join="")
    target = (
        "target AS (\n"
        "  SELECT m2.apt_seq FROM trade_apt_mapping m2 WHERE "
        + " AND ".join(conds) + "\n), "
    )
    return _TEMPLATE.format(
        target_cte=target,
        trade_join=_JOIN.format(alias="t"),
        rent_join=_JOIN.format(alias="r"),
    )
