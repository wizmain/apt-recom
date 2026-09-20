"""실적(매매+전월세) 집계 SQL 빌더 — 매핑 감사·재매칭 공용.

임대 단지는 실적이 전월세에만 있어 매매만 집계하면 층·면적 검증이 빈 채로
통과한다. 면적은 건수 가중으로 모은다(mapping_checks.area_match_ratio).

두 가지 성능 함정을 피한다 (2026-08 실측 — 전체 실행 집계가 4시간을 넘겨 중단).
  1) "%(seqs)s IS NULL OR apt_seq = ANY(%(seqs)s)" 패턴은 플래너가 인덱스를
     버리게 만든다 → 필터 유무로 SQL 을 조립한다 (조각은 전부 고정 문자열)
  2) CTE 를 행마다 참조하는 상관 서브쿼리는 매 행 재스캔이다 → GROUP BY
     집계를 만들어 LEFT JOIN 한다
수정 후 전체 집계(거래 317만 + 전월세 659만)가 분 단위로 끝난다.

지번 키(jibun_key CTE)는 매매만 쓴다 — rent_history 에 umd_cd/bonbun/bubun 이 없다.
매매 내 채움률은 16퍼센트 수준이라 커버리지가 낮은 대신 확실한 신호다. PNU 11번째
자리는 '0' 으로 고정한다: trade_history.land_cd 는 산여부가 아니라 1~5 값이라
그대로 쓰면 조인이 전멸한다(실측 '0' 90.5퍼센트 vs land_cd 0퍼센트).
SQL 주석에 퍼센트 기호를 쓰지 않는 이유 — 이 SQL 은 파라미터와 함께 실행되므로
psycopg2 가 주석 안의 % 도 플레이스홀더로 해석한다.

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
  SELECT pnu, ARRAY_AGG(exclusive_area) AS areas FROM ({apt_area_source}) u GROUP BY pnu
),
-- 거래 지번 → PNU 키. PNU 는 법정동코드(10)+산여부(1)+본번(4)+부번(4) 이므로 신고
-- 지번으로 같은 키를 만들어 매핑처와 대조한다 (mapping_checks.jibun_points_elsewhere).
-- rent_history 에는 umd_cd/bonbun/bubun 이 없어 매매만 근거로 쓴다(모듈 주석 참조).
-- 11번째 자리는 '0' 으로 고정한다 — land_cd 는 산여부가 아니다(모듈 주석 참조).
-- bonbun/bubun 은 원천이 이미 4자리로 채워 오지만, 원천이 바뀌어도 키가 깨지지 않게
-- LPAD 로 한 번 더 보장한다.
jibun_key AS (
  SELECT DISTINCT t.apt_seq,
         t.sgg_cd || t.umd_cd || '0'
           || LPAD(t.bonbun, 4, '0') || LPAD(t.bubun, 4, '0') AS pnu_key
  FROM trade_history t {trade_join}
  WHERE t.bonbun IS NOT NULL AND t.bonbun <> ''
    AND t.umd_cd IS NOT NULL AND t.umd_cd <> ''
),
jibun_agg AS (
  SELECT j.apt_seq,
         ARRAY_AGG(j.pnu_key) AS jibun_pnus,
         ARRAY_REMOVE(ARRAY_AGG(a2.pnu), NULL) AS jibun_owner_pnus
  FROM jibun_key j
  LEFT JOIN apartments a2 ON a2.pnu = j.pnu_key
  GROUP BY j.apt_seq
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
       jb.jibun_pnus, jb.jibun_owner_pnus,
       a.bld_nm, a.max_floor AS apt_max_floor, a.use_apr_day,
       ap.areas AS apt_areas
FROM trade_apt_mapping m
JOIN deal d ON d.apt_seq = m.apt_seq
JOIN apartments a ON a.pnu = m.pnu
LEFT JOIN area_agg aa ON aa.apt_seq = m.apt_seq
LEFT JOIN apt_area_agg ap ON ap.pnu = m.pnu
LEFT JOIN jibun_agg jb ON jb.apt_seq = m.apt_seq
ORDER BY (d.trades + d.rents) DESC
"""

_JOIN = "JOIN target g ON g.apt_seq = {alias}.apt_seq"

_OWN_AREA_TYPES = "SELECT pnu, exclusive_area FROM apt_area_type"

# 분양·임대 혼합 단지는 임대동 레코드가 동반 레코드(KAPT_ 더미 + parent_pnu)로 따로 있다 (ADR-014).
# 임대동의 전월세는 같은 단지의 정당한 실적이므로, 그 주택형도 단지의 주택형으로 본다. 빼면
# `남산타운(임대)` 전월세가 분양 주택형과 안 맞는다는 이유로 오매핑 위반이 된다(2026-09-20 실측:
# 교체 직후 40 PNU 에서 31건).
_COMPANION_AREA_TYPES = """
    UNION ALL
    SELECT k.parent_pnu AS pnu, t.exclusive_area
      FROM apt_kapt_info k JOIN apt_area_type t ON t.pnu = k.pnu
     WHERE k.parent_pnu IS NOT NULL"""

COMPANION_COLUMN_SQL = """
SELECT 1 FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'apt_kapt_info' AND column_name = 'parent_pnu'
"""


def build_deal_stats_sql(
    by_seqs: bool = False, by_pnus: bool = False, with_companions: bool = False
) -> str:
    """대상 필터에 맞는 집계 SQL 을 만든다.

    by_seqs → %(seqs)s (apt_seq 목록), by_pnus → %(pnus)s (매핑 pnu 목록).
    둘 다 False 면 전체 집계다. 파라미터는 psycopg2 %(name)s 로만 전달되며
    이 함수가 조립하는 조각은 전부 고정 문자열이다.

    with_companions → 동반 레코드(임대동)의 주택형을 단지 주택형에 포함한다. `parent_pnu` 컬럼을
    참조하므로 **컬럼이 있는 DB 에서만** 켠다 — 호출부가 COMPANION_COLUMN_SQL 로 확인해 넘긴다.
    컬럼은 백엔드 create_tables() 가 만들기 때문에, 배포 전의 DB 에서 이 SQL 이 실패하면 같은
    연결의 트랜잭션이 깨져 배치의 뒤 단계까지 막는다. 컬럼이 전 환경에 생긴 뒤에는 이 인자를
    없애고 항상 포함하도록 정리한다(제거 조건: Railway 백엔드 배포 완료).
    """
    area_source = _OWN_AREA_TYPES + (_COMPANION_AREA_TYPES if with_companions else "")
    conds = []
    if by_seqs:
        conds.append("m2.apt_seq = ANY(%(seqs)s)")
    if by_pnus:
        conds.append("m2.pnu = ANY(%(pnus)s)")
    if not conds:
        return _TEMPLATE.format(
            target_cte="", trade_join="", rent_join="", apt_area_source=area_source
        )
    target = (
        "target AS (\n"
        "  SELECT m2.apt_seq FROM trade_apt_mapping m2 WHERE "
        + " AND ".join(conds) + "\n), "
    )
    return _TEMPLATE.format(
        target_cte=target,
        trade_join=_JOIN.format(alias="t"),
        rent_join=_JOIN.format(alias="r"),
        apt_area_source=area_source,
    )
