"""batch.trade.backfill_dealing_gbn 순수 함수 검증 — DB·네트워크 없이 (CI 대상)."""

import unittest
from datetime import date

from batch.trade.backfill_dealing_gbn import (
    DEALING_GBN_FIRST_YM,
    default_to_ym,
    pair_key,
    parse_sido,
    update_row,
)

NO_ALIASES = {"sigungu": {}}


def api_row(**overrides):
    row = {
        "dealingGbn": "직거래",
        "sggCd": "11590",
        "aptNm": "대림아파트",
        "excluUseAr": "84.96",
        "floor": "13",
        "dealYear": "2025",
        "dealMonth": "8",
        "dealDay": "3",
        "dealAmount": "80,000",
    }
    row.update(overrides)
    return row


class TestUpdateRow(unittest.TestCase):
    def test_고유키는_적재_규칙과_같게_만든다(self):
        self.assertEqual(
            update_row(api_row(), NO_ALIASES),
            ("직거래", "11590", "대림아파트", 84.96, 13, 2025, 8, 3, 80000),
        )

    def test_금액_공백과_쉼표를_지운다(self):
        self.assertEqual(
            update_row(api_row(dealAmount=" 1,250,000 "), NO_ALIASES)[-1], 1250000
        )

    def test_거래유형이_비어_있으면_채울_값이_없다(self):
        self.assertIsNone(update_row(api_row(dealingGbn=""), NO_ALIASES))
        self.assertIsNone(update_row(api_row(dealingGbn="  "), NO_ALIASES))

    def test_고유키_칼럼이_빠지면_건너뛴다(self):
        for field in (
            "excluUseAr",
            "floor",
            "dealYear",
            "dealMonth",
            "dealDay",
            "dealAmount",
        ):
            with self.subTest(field=field):
                self.assertIsNone(update_row(api_row(**{field: ""}), NO_ALIASES))
        self.assertIsNone(update_row(api_row(aptNm=""), NO_ALIASES))
        self.assertIsNone(update_row(api_row(sggCd=""), NO_ALIASES))

    def test_지하층_음수도_유지한다(self):
        self.assertEqual(update_row(api_row(floor="-1"), NO_ALIASES)[4], -1)

    def test_시군구_신코드는_내부_구코드로_접는다(self):
        # 분할형: 인천 28275 → 28260 (region_codes.normalize_sigungu_code 규칙)
        aliases = {"sigungu": {"2827510100": "2826010100"}}
        self.assertEqual(update_row(api_row(sggCd="28275"), aliases)[1], "28260")


class TestDefaults(unittest.TestCase):
    def test_기본_종료월은_지난달(self):
        self.assertEqual(default_to_ym(date(2026, 11, 25)), 202610)
        self.assertEqual(default_to_ym(date(2027, 1, 3)), 202612)

    def test_제공_시작월(self):
        self.assertEqual(DEALING_GBN_FIRST_YM, 202111)


class TestParseSido(unittest.TestCase):
    def test_쉼표_구분(self):
        self.assertEqual(parse_sido("11, 28,41"), ["11", "28", "41"])

    def test_빈_값은_전국(self):
        self.assertEqual(parse_sido(""), [])

    def test_잘못된_코드는_거부(self):
        with self.assertRaises(ValueError):
            parse_sido("서울")
        with self.assertRaises(ValueError):
            parse_sido("111")


class TestPairKey(unittest.TestCase):
    def test_체크포인트_키(self):
        self.assertEqual(pair_key("11590", 202508), "11590:202508")


if __name__ == "__main__":
    unittest.main()
