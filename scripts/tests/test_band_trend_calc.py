"""batch.trade.band_trend_calc 검증 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest
from datetime import date

from batch.trade.band_trend_calc import (
    BandDef,
    band_of,
    base_month,
    complex_grade,
    drop_outliers,
    monthly_series,
    parse_band_extra,
    placement_rank,
    region_grade,
    shift_month,
    type_change,
    window,
)


class TestBaseMonth(unittest.TestCase):
    def test_신고기한이_지난_달만_기준월(self):
        self.assertEqual(base_month(date(2026, 11, 25)), 202609)
        self.assertEqual(
            base_month(date(2026, 11, 30)), 202609
        )  # 10/31+30 = 11/30, 미경과
        self.assertEqual(base_month(date(2026, 12, 1)), 202610)
        self.assertEqual(
            base_month(date(2027, 1, 30)), 202611
        )  # 12/31+30 = 1/30, 미경과
        self.assertEqual(base_month(date(2027, 1, 31)), 202612)


class TestWindow(unittest.TestCase):
    def test_연도를_넘는_창(self):
        self.assertEqual(window(202601), [202511, 202512, 202601])
        self.assertEqual(shift_month(202609, -12), 202509)


class TestBand(unittest.TestCase):
    BANDS = [BandDef("59", 50, 70), BandDef("84", 70, 100), BandDef("175", 175, None)]

    def test_경계는_하한_포함_상한_제외(self):
        self.assertEqual(band_of(70.0, self.BANDS), "84")
        self.assertEqual(band_of(69.99, self.BANDS), "59")
        self.assertEqual(band_of(240.0, self.BANDS), "175")
        self.assertIsNone(band_of(45.0, self.BANDS))
        self.assertIsNone(band_of(120.0, self.BANDS))

    def test_코드값_extra_파싱(self):
        self.assertEqual(parse_band_extra("59", "50,70"), BandDef("59", 50.0, 70.0))
        self.assertEqual(parse_band_extra("175", "175,"), BandDef("175", 175.0, None))


class TestOutliers(unittest.TestCase):
    def test_중앙값_25퍼센트_밖은_제외(self):
        self.assertEqual(sorted(drop_outliers([84000, 82500, 55000])), [82500, 84000])

    def test_두건이_크게_벌어지면_둘다_제외(self):
        self.assertEqual(drop_outliers([50000, 100000]), [])

    def test_빈_입력은_빈_목록(self):
        self.assertEqual(drop_outliers([]), [])


class TestTypeChange(unittest.TestCase):
    def test_주택형별_비율을_최근건수로_가중(self):
        pct, matched = type_change(
            {84.52: [90000, 85000], 84.54: [85000, 89000, 85000], 84.99: [91000]},
            {84.52: [65000], 84.54: [66000, 67000]},
        )
        self.assertAlmostEqual(pct, 30.54, places=2)  # 84.99 는 과거 창에 없어 제외
        self.assertEqual(matched, 2)

    def test_공통_주택형_없으면_None(self):
        self.assertEqual(type_change({84.5: [1, 2]}, {59.9: [1, 2]}), (None, 0))

    def test_창_거래가_최소건수_미만이면_None(self):
        self.assertEqual(
            type_change({84.5: [90000]}, {84.5: [80000, 81000]}), (None, 0)
        )


class TestGrades(unittest.TestCase):
    REGION = [
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

    def test_지역등급_15단계_균등분할(self):
        self.assertEqual(region_grade(1, 71, self.REGION), "S+")
        self.assertEqual(region_grade(71, 71, self.REGION), "D-")
        self.assertEqual(region_grade(30, 71, self.REGION), "B+")  # (30-1)*15//71 = 6

    def test_단지등급_십분위_두개씩(self):
        self.assertEqual(complex_grade(1, 96, list("SABCD")), ("S", 1))
        self.assertEqual(complex_grade(59, 96, list("SABCD")), ("C", 7))
        self.assertEqual(complex_grade(96, 96, list("SABCD")), ("D", 10))

    def test_12개월_대입_순위(self):
        self.assertEqual(placement_rank(70000, [90000, 80000, 70000, 60000]), 3)


class TestMonthlySeries(unittest.TestCase):
    def test_빈달은_None_0건_이상거래는_롤링창_기준_제외(self):
        series = monthly_series(
            {202607: [80000, 82000], 202609: [83000, 50000]},
            [202607, 202608, 202609],
        )
        self.assertEqual(series[0], (202607, 81000, 2))
        self.assertEqual(series[1], (202608, None, 0))
        self.assertEqual(
            series[2], (202609, 83000, 1)
        )  # 7~9월 창 중앙값 81000 기준 50000 제외


if __name__ == "__main__":
    unittest.main()
