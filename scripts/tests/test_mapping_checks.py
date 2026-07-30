"""batch.trade.mapping_checks 검증 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest

from batch.trade.mapping_checks import (
    AREA_TOLERANCE,
    FLOOR_TOLERANCE,
    PRESALE_TOLERANCE_YEARS,
    area_match_ratio,
    check_mapping,
    complex_number_conflict,
    complex_numbers,
    floor_exceeds,
    mismatch_confirmed,
    name_consistent,
    timeline_violation,
)


def codes(signals):
    return {s.code for s in signals}


class TestComplexNumber(unittest.TestCase):
    def test_단지와_차수를_모두_뽑는다(self):
        self.assertEqual(complex_numbers("가락(1차)쌍용아파트"), {"1"})
        self.assertEqual(complex_numbers("산내마을8단지월드메르디앙"), {"8"})
        self.assertEqual(complex_numbers("부평1,2차금호타운"), {"2"})

    def test_번호가_다르면_충돌이다(self):
        self.assertTrue(
            complex_number_conflict("성원대치2단지아파트", "SH공사대치1단지")
        )
        self.assertTrue(
            complex_number_conflict(
                "산내마을1단지행복주택", "산내마을8단지월드메르디앙"
            )
        )

    def test_번호가_같으면_충돌이_아니다(self):
        self.assertFalse(complex_number_conflict("가락(1차)쌍용아파트", "가락쌍용1차"))

    def test_한쪽에만_번호가_있으면_판단하지_않는다(self):
        """`충무주공(872)` 의 872 는 지번이라 단지 번호로 볼 수 없다."""
        self.assertFalse(complex_number_conflict("충무주공(872)", "산본충무2차"))
        self.assertFalse(complex_number_conflict("미성", "월계시영고층"))


class TestFloor(unittest.TestCase):
    def test_크게_초과하면_다른_단지다(self):
        self.assertTrue(floor_exceeds(25, 15))

    def test_같거나_낮으면_정상이다(self):
        self.assertFalse(floor_exceeds(20, 20))
        self.assertFalse(floor_exceeds(14, 20))

    def test_건축물대장_표기_편차는_허용한다(self):
        """약수(7층 vs 5층)·성요셉(6 vs 5)·송림아마레스(7 vs 6) 오탐 사례.

        소규모·노후 단지는 대표동 기준이나 옥탑 계산 차이로 1~2층 어긋난다.
        """
        self.assertFalse(floor_exceeds(7, 5))
        self.assertFalse(floor_exceeds(6, 5))
        self.assertGreaterEqual(FLOOR_TOLERANCE, 2)

    def test_값이_없으면_판단하지_않는다(self):
        self.assertFalse(floor_exceeds(None, 20))
        self.assertFalse(floor_exceeds(25, None))


class TestArea(unittest.TestCase):
    def test_허용오차는_다른_주택형을_구분할_만큼_좁다(self):
        """84.28 과 84.82 는 다른 주택형이다 (차이 0.54)."""
        self.assertLess(AREA_TOLERANCE, 0.54)
        self.assertEqual(area_match_ratio([84.28], [84.82]), 0.0)

    def test_반올림_차이는_흡수한다(self):
        self.assertEqual(area_match_ratio([84.82], [84.8198]), 1.0)

    def test_일부만_맞으면_비율로_나온다(self):
        self.assertAlmostEqual(area_match_ratio([59.9, 84.82], [84.8198]), 0.5)

    def test_건수로_가중한다(self):
        """면적 종류만 세면 소수의 예외 거래가 과대평가된다.

        부영애시앙1차: 84.28㎡ 58건 + 84.84㎡ 11건, 진본 주택형은 84.8198 단일.
        종류만 세면 1/2=50% 로 통과하지만, 건수로 세면 11/69=16% 로 걸린다.
        """
        self.assertAlmostEqual(area_match_ratio([84.28, 84.84], [84.8198]), 0.5)
        self.assertAlmostEqual(
            area_match_ratio([(84.28, 58), (84.84, 11)], [84.8198]), 11 / 69
        )

    def test_한쪽이_비면_판단_불가다(self):
        self.assertIsNone(area_match_ratio([], [84.82]))
        self.assertIsNone(area_match_ratio([84.82], None))


class TestCheckMapping(unittest.TestCase):
    def test_정합하면_사유가_없다(self):
        deal = {
            "apt_nm": "산울마을6단지",
            "max_floor": 32,
            "min_deal_year": 2024,
            "median_build_year": 2024,
            "areas": [59.6, 84.9],
        }
        apt = {
            "bld_nm": "산울마을6단지",
            "max_floor": 35,
            "use_apr_day": "20240307",
            "areas": [59.6, 84.9],
        }
        self.assertEqual(check_mapping(deal, apt), [])

    def test_부영애시앙1차_사례를_걸러낸다(self):
        """실제로 병합 대상에서 제외했던 건 — 주택형과 층이 진본에 없다."""
        deal = {
            "apt_nm": "부영애시앙1차",
            "max_floor": 21,
            "min_deal_year": 2023,
            "median_build_year": 2008,
            "areas": [(84.28, 58), (84.84, 11)],
        }
        apt = {
            "bld_nm": "산정 셀트리움",
            "max_floor": 20,
            "use_apr_day": "20081120",
            "areas": [84.8198],
        }
        signals = check_mapping(deal, apt)
        self.assertIn("area", codes(signals))
        self.assertTrue(mismatch_confirmed(signals))

    def test_거래가_준공보다_한참_이르면_타임라인_위반이다(self):
        deal = {
            "apt_nm": "A",
            "max_floor": None,
            "min_deal_year": 2010,
            "median_build_year": None,
            "areas": None,
        }
        apt = {
            "bld_nm": "A",
            "max_floor": None,
            "use_apr_day": "20200101",
            "areas": None,
        }
        self.assertIn("timeline", codes(check_mapping(deal, apt)))

    def test_판단_재료가_없으면_통과시킨다(self):
        """지표가 비었다고 오매핑으로 몰지 않는다."""
        deal = {
            "apt_nm": "A",
            "max_floor": None,
            "min_deal_year": None,
            "median_build_year": None,
            "areas": None,
        }
        apt = {"bld_nm": "B", "max_floor": None, "use_apr_day": None, "areas": None}
        self.assertEqual(check_mapping(deal, apt), [])


class TestNameConsistent(unittest.TestCase):
    def test_같은_단지인데도_표기_차이로_불일치가_난다(self):
        """이름 유사도를 단독 근거로 쓰면 안 되는 이유.

        아래 세 쌍은 같은 단지로 보이지만 임계값(0.4) 아래로 떨어진다.
        그래서 check_mapping 의 물리 지표로 다시 걸러야 한다.
        """
        for a, b in [
            ("목동신시가지14", "목동14단지"),
            ("가락(1차)쌍용아파트", "가락쌍용1차"),
            ("인천 SK Sky VIEW", "인천에스케이스카이뷰"),
        ]:
            self.assertFalse(name_consistent(a, b), f"{a} vs {b}")

    def test_전혀_다른_이름은_불일치다(self):
        self.assertFalse(name_consistent("부영애시앙1차", "산정 셀트리움"))

    def test_공통부분이_충분하면_일치로_본다(self):
        self.assertTrue(name_consistent("산울마을6단지", "산울마을6단지"))
        self.assertTrue(
            name_consistent(
                "세종리첸시아파밀리에H3블록(산울마을6단지)", "산울마을6단지"
            )
        )

    def test_진본_이름이_없으면_판단하지_않는다(self):
        self.assertTrue(name_consistent("아무개", ""))


if __name__ == "__main__":
    unittest.main()


class TestMismatchConfirmed(unittest.TestCase):
    """판정 보정 — 지표 하나로 확정하지 않되, 면적은 예외로 둔다."""

    def _deal(self, **kw):
        base = {"apt_nm": "A", "max_floor": None, "min_deal_year": None,
                "median_build_year": None, "areas": None}
        base.update(kw)
        return base

    def _apt(self, **kw):
        base = {"bld_nm": "A", "max_floor": None, "use_apr_day": None, "areas": None}
        base.update(kw)
        return base

    def test_분양권_거래는_오매핑이_아니다(self):
        """신당파인힐하나유보라 오탐 사례 — 준공 2019, 최초거래 2018."""
        self.assertFalse(timeline_violation("20190607", 2018, None))
        self.assertGreaterEqual(PRESALE_TOLERANCE_YEARS, 1)

    def test_준공보다_한참_이르면_여전히_위반이다(self):
        self.assertTrue(timeline_violation("20200101", 2010, None))

    def test_타임라인_단독으로는_확정하지_않는다(self):
        signals = check_mapping(self._deal(min_deal_year=2010),
                                self._apt(use_apr_day="20200101"))
        self.assertEqual(codes(signals), {"timeline"})
        self.assertFalse(mismatch_confirmed(signals))

    def test_층_단독으로는_확정하지_않는다(self):
        signals = check_mapping(self._deal(max_floor=30), self._apt(max_floor=20))
        self.assertEqual(codes(signals), {"floor"})
        self.assertFalse(mismatch_confirmed(signals))

    def test_두_지표가_함께_어긋나면_확정한다(self):
        signals = check_mapping(
            self._deal(max_floor=30, min_deal_year=2010),
            self._apt(max_floor=20, use_apr_day="20200101"))
        self.assertEqual(codes(signals), {"floor", "timeline"})
        self.assertTrue(mismatch_confirmed(signals))

    def test_주택형이_거의_안_맞으면_단독으로도_확정한다(self):
        """부영애시앙1차 기준 — 면적 일치 16%."""
        signals = check_mapping(
            self._deal(areas=[(84.28, 58), (84.84, 11)]), self._apt(areas=[84.8198]))
        self.assertEqual(codes(signals), {"area"})
        self.assertTrue(mismatch_confirmed(signals))

    def test_면적이_애매하게_맞으면_단독으로는_확정하지_않는다(self):
        """40% — 임계(50%) 아래라 신호는 나오지만 strong(25% 이하)은 아니다."""
        signals = check_mapping(
            self._deal(areas=[(59.9, 6), (84.82, 4)]), self._apt(areas=[84.8198]))
        self.assertEqual(codes(signals), {"area"})
        self.assertFalse(mismatch_confirmed(signals))
