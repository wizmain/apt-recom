"""batch.trade.recollect_history 순수 함수 검증 — DB·네트워크 없이 (CI 대상)."""

import unittest

from batch.trade.recollect_history import month_range, pair_key, parse_codes


class TestMonthRange(unittest.TestCase):
    def test_최근_월부터_연도를_넘어간다(self):
        self.assertEqual(
            month_range(202511, 202602), ["202602", "202601", "202512", "202511"]
        )

    def test_한_달(self):
        self.assertEqual(month_range(202512, 202512), ["202512"])

    def test_뒤집힌_기간은_거부(self):
        with self.assertRaises(ValueError):
            month_range(202602, 202511)

    def test_5년치_개수(self):
        self.assertEqual(len(month_range(202110, 202609)), 60)


class TestParseCodes(unittest.TestCase):
    def test_쉼표_구분(self):
        self.assertEqual(parse_codes("41595, 41597"), ["41595", "41597"])

    def test_빈_값과_잘못된_코드는_거부(self):
        for value in ("", "4159", "화성", "41595,abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_codes(value)


class TestPairKey(unittest.TestCase):
    def test_체크포인트_키(self):
        self.assertEqual(pair_key("28125", "202607"), "28125:202607")


if __name__ == "__main__":
    unittest.main()
