"""batch.trade.band_trend_aggregate 검증 — 혼입 제외·창 필터·등급·행 생성 (DB 없음, CI 대상)."""

import unittest

from batch.trade.band_trend_aggregate import (
    GRADE_FALLBACK_WINDOW_MONTHS,
    GRADE_WINDOW_MONTHS,
    REASON_BUILD_YEAR_MISMATCH,
    REASON_MAPPING_VIOLATION,
    BandTrade,
    GradeCandidate,
    SourceTrade,
    apply_exclusions,
    build_tables,
    build_year_mismatch,
    complex_grades,
    excluded_ratio_by_band,
    region_grades,
    trades_in_window,
)
from batch.trade.band_trend_calc import BandDef

BANDS = [BandDef("59", 50.0, 70.0), BandDef("84", 70.0, 100.0)]
COMPLEX_LABELS = ["S", "A", "B", "C", "D"]
REGION_LABELS = [
    "S+",
    "S",
    "S-",
    "A+",
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "D-",
]


def source(
    apt_seq,
    area=84.0,
    ym=202609,
    price=10000,
    build_year=2010,
    completion_year=2010,
    pnu="P1",
):
    return SourceTrade(
        apt_seq,
        "단지",
        f"M_{apt_seq}",
        pnu,
        "11110",
        area,
        ym,
        price,
        build_year,
        completion_year,
    )


def band_trade(ym, price, pnu="P1", sgg="11110", area=84.0):
    return BandTrade(pnu, sgg, "84", area, ym, price)


class TestBuildYearMismatch(unittest.TestCase):
    def test_허용오차_3년_초과만_불일치(self):
        self.assertFalse(build_year_mismatch(2013, 2010))
        self.assertTrue(build_year_mismatch(2014, 2010))
        self.assertTrue(build_year_mismatch(2006, 2010))

    def test_한쪽이_없으면_판단하지_않음(self):
        self.assertFalse(build_year_mismatch(None, 2010))
        self.assertFalse(build_year_mismatch(2000, None))


class TestApplyExclusions(unittest.TestCase):
    def test_매핑위반_키는_거래_전부_제외(self):
        result = apply_exclusions(
            [source("BAD"), source("BAD", price=20000), source("OK")],
            BANDS,
            {"BAD": "PNU_BAD"},
        )
        self.assertEqual([t.price for t in result.kept], [10000])
        self.assertEqual(
            result.excluded_keys["BAD"], ("PNU_BAD", REASON_MAPPING_VIOLATION)
        )
        self.assertEqual(result.excluded_trades_by_key["BAD"], 2)

    def test_건축년도_불일치는_그_거래만_빼고_키는_감사_기록(self):
        result = apply_exclusions(
            [source("K", build_year=2010), source("K", build_year=1995)],
            BANDS,
            {},
        )
        self.assertEqual(len(result.kept), 1)
        self.assertEqual(result.excluded_keys["K"], ("M_K", REASON_BUILD_YEAR_MISMATCH))
        self.assertEqual(result.excluded_trades_by_key["K"], 1)

    def test_두_사유에_다_걸리면_매핑위반_우선(self):
        result = apply_exclusions([source("K", build_year=1995)], BANDS, {"K": "PNU_K"})
        self.assertEqual(result.excluded_keys["K"], ("PNU_K", REASON_MAPPING_VIOLATION))

    def test_면적대별_제외_비율(self):
        result = apply_exclusions(
            [
                source("BAD"),
                source("OK"),
                source("OK"),
                source("OK"),
                source("OK", area=59.0),
            ],
            BANDS,
            {"BAD": "PNU_BAD"},
        )
        self.assertEqual(excluded_ratio_by_band(result), {"84": 0.25, "59": 0.0})

    def test_면적대_밖_거래는_통계에서_빠짐(self):
        result = apply_exclusions(
            [source("K", area=40.0), source("K", area=59.9)], BANDS, {}
        )
        self.assertEqual(result.trades_by_band, {"59": 1})
        self.assertEqual(result.kept[0].band, "59")
        self.assertEqual(result.kept[0].type_key, 59.9)


class TestTradesInWindow(unittest.TestCase):
    def test_창_밖은_무시하고_창_중앙값_25퍼센트_밖은_제외(self):
        trades = [
            band_trade(202609, 10000),
            band_trade(202608, 10500),
            band_trade(202607, 20000),  # 중앙값 10500 대비 +90%
            band_trade(202603, 1000),  # 창 밖
        ]
        kept = trades_in_window(trades, frozenset({202607, 202608, 202609}))
        self.assertEqual(sorted(t.price for t in kept), [10000, 10500])


class TestComplexGrades(unittest.TestCase):
    def test_6개월_모집단_순위와_12개월_대입(self):
        population = [GradeCandidate(f"P{i}", 3, 100.0 - i, None) for i in range(10)]
        thin_mid = GradeCandidate("THIN", 1, 50.0, 95.5)  # 6개월 표본 미달
        thin_cheap = GradeCandidate("CHEAP", 0, None, 1.0)  # 모집단 전부보다 쌈
        no_price = GradeCandidate("NONE", 0, None, None)
        grades = complex_grades(
            [*population, thin_mid, thin_cheap, no_price], COMPLEX_LABELS
        )

        self.assertEqual(grades["P0"].grade, "S")
        self.assertEqual((grades["P0"].rank, grades["P0"].total), (1, 10))
        self.assertEqual(grades["P0"].window_months, GRADE_WINDOW_MONTHS)
        self.assertEqual(grades["P9"].grade, "D")
        # 95.5 보다 비싼 단지 5개 → 6위 대입 → 십분위 6 → B(5~6분위), 순위는 비움
        self.assertEqual(grades["THIN"].grade, "B")
        self.assertIsNone(grades["THIN"].rank)
        self.assertIsNone(grades["THIN"].total)
        self.assertEqual(grades["THIN"].window_months, GRADE_FALLBACK_WINDOW_MONTHS)
        # 모집단 최하위보다 싸면 total+1 이 아니라 최하위로 맞춘다
        self.assertEqual(grades["CHEAP"].grade, "D")
        self.assertNotIn("NONE", grades)

    def test_모집단_4곳이면_대입_단지까지_전부_등급_없음(self):
        population = [GradeCandidate(f"P{i}", 3, 100.0 - i, None) for i in range(4)]
        thin = GradeCandidate("THIN", 1, 50.0, 99.0)
        self.assertEqual(complex_grades([*population, thin], COMPLEX_LABELS), {})

    def test_모집단_5곳이면_등급_부여(self):
        population = [GradeCandidate(f"P{i}", 3, 100.0 - i, None) for i in range(5)]
        thin = GradeCandidate("THIN", 1, 50.0, 99.0)
        grades = complex_grades([*population, thin], COMPLEX_LABELS)
        self.assertEqual(
            [grades[f"P{i}"].grade for i in range(5)], ["S", "A", "B", "C", "D"]
        )
        self.assertEqual((grades["P4"].rank, grades["P4"].total), (5, 5))
        self.assertEqual(grades["THIN"].window_months, GRADE_FALLBACK_WINDOW_MONTHS)

    def test_모집단이_없으면_등급_없음(self):
        self.assertEqual(
            complex_grades([GradeCandidate("P", 1, 10.0, 10.0)], COMPLEX_LABELS), {}
        )


class TestRegionGrades(unittest.TestCase):
    def test_표본_미달_지역은_등급_없음(self):
        grades = region_grades(
            {"A": (300, 10), "B": (100, 10), "C": (500, 4)}, REGION_LABELS
        )
        self.assertNotIn("C", grades)
        self.assertEqual(
            (grades["A"].grade, grades["A"].rank, grades["A"].total), ("S+", 1, 2)
        )
        self.assertEqual((grades["B"].grade, grades["B"].rank), ("B", 2))


class TestBuildTables(unittest.TestCase):
    def test_단지_변화율_지역대비_노출조건(self):
        base = 202609
        kept = [
            # P1: 현재 창 11000×2, 6개월 전 창 10000×2, 12개월 전 창 없음
            band_trade(202609, 11000),
            band_trade(202608, 11000),
            band_trade(202603, 10000),
            band_trade(202602, 10000),
            # P2: 현재 창 1건 → 목록 제외, 월별 시계열도 넣지 않음
            band_trade(202609, 30000, pnu="P2"),
            band_trade(202603, 30000, pnu="P2"),
            band_trade(202602, 30000, pnu="P2"),
        ]
        tables = build_tables(kept, base, REGION_LABELS, COMPLEX_LABELS)

        self.assertEqual([r.pnu for r in tables.trend_rows], ["P1"])
        row = tables.trend_rows[0]
        self.assertEqual(
            (row.median_price_3m, row.trade_count_3m, row.trade_count_6m), (11000, 2, 2)
        )
        self.assertAlmostEqual(row.change_6m_pct, 10.0)
        self.assertEqual(row.matched_type_count_6m, 1)
        self.assertIsNone(row.change_12m_pct)
        self.assertEqual(row.matched_type_count_12m, 0)
        # 지역 6개월 변화: (단지,주택형) 짝 P1 +10% (가중 2), P2 0% (가중 1) → 6.67%
        region = tables.region_rows[0]
        self.assertAlmostEqual(region.change_6m_pct, 20 / 3)
        self.assertAlmostEqual(row.relative_change_6m_pct, 10.0 - 20 / 3)
        self.assertEqual(region.trade_count_3m, 3)
        self.assertIsNone(region.region_grade)  # 3건 < MIN_REGION_TRADES

        # 월별 시계열은 목록에 오른 쌍(P1)만
        self.assertEqual({r.pnu for r in tables.monthly_rows}, {"P1"})
        p1_months = sorted(r.deal_ym for r in tables.monthly_rows)
        self.assertEqual(p1_months, [202602, 202603, 202608, 202609])


if __name__ == "__main__":
    unittest.main()
