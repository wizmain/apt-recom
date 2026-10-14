"""거래 키 규칙(ADR-015) — DB·네트워크 없이 확인 (CI 대상)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_keys import (
    KEY_METHOD_API,
    TradeKey,
    address_pnu,
    address_rows_by_key,
    name_key,
    resolve_trade_key,
    try_trade_write_lock,
    unique_existing_pnu,
)


class ResolveTradeKeyTest(unittest.TestCase):
    def test_api_seq_becomes_key_and_name_key_is_kept(self):
        self.assertEqual(
            resolve_trade_key("11590", "대림아파트", "11590-85"),
            TradeKey("11590-85", "11590_대림아파트", KEY_METHOD_API),
        )

    def test_missing_api_seq_keeps_name_key(self):
        self.assertEqual(
            resolve_trade_key("11590", "대림아파트", None),
            TradeKey("11590_대림아파트", None, None),
        )

    def test_blank_api_seq_is_treated_as_missing(self):
        # Review Focus 1 — 빈 키가 생기면 안 된다.
        for blank in ("", "   ", "\t"):
            self.assertEqual(
                resolve_trade_key("11590", "대림아파트", blank).apt_seq,
                "11590_대림아파트",
            )

    def test_api_seq_is_stripped(self):
        self.assertEqual(
            resolve_trade_key("11590", "대림", " 11590-57 ").apt_seq, "11590-57"
        )

    def test_name_key_format(self):
        self.assertEqual(name_key("11590", "대림아파트"), "11590_대림아파트")


class AddressPnuTest(unittest.TestCase):
    def test_daebang_daelim(self):
        # 대방동 501 → 1159010800005010000 (2026-10-13 실측 PNU)
        self.assertEqual(
            address_pnu("11590", "10800", "1", "0501", "0000"), "1159010800005010000"
        )

    def test_mountain_lot_uses_1(self):
        self.assertEqual(address_pnu("11590", "10800", "2", "12", "3")[10], "1")

    def test_pads_short_numbers(self):
        self.assertEqual(
            address_pnu("11590", "10800", "1", "501", None), "1159010800005010000"
        )

    def test_missing_parts_return_none(self):
        self.assertIsNone(address_pnu("11590", None, "1", "0501", "0000"))
        self.assertIsNone(address_pnu("11590", "10800", "1", None, "0000"))

    def test_non_numeric_returns_none(self):
        self.assertIsNone(address_pnu("11590", "10800", "1", "산12", "0"))


class TradeWriteLockTest(unittest.TestCase):
    def test_returns_lock_result(self):
        class Cur:
            def __init__(self, got):
                self.got = got
                self.sql = None

            def execute(self, sql, params):
                self.sql, self.params = sql, params

            def fetchone(self):
                return (self.got,)

        class Conn:
            def __init__(self, got):
                self.cur = Cur(got)

            def cursor(self):
                return self.cur

        self.assertTrue(try_trade_write_lock(Conn(True)))
        busy = Conn(False)
        self.assertFalse(try_trade_write_lock(busy))
        self.assertIn("pg_try_advisory_lock", busy.cur.sql)


class AddressRowsByKeyTest(unittest.TestCase):
    """Fix A — 키의 주소 PNU 는 대표 행 하나가 아니라 주소 필드가 있는 모든 행에서 모은다."""

    @staticmethod
    def row(key, umd_cd, bonbun="1003", bubun="0001", land_cd="1"):
        return {
            "apt_seq": key,
            "sgg_cd": "28260",
            "umd_cd": umd_cd,
            "land_cd": land_cd,
            "bonbun": bonbun,
            "bubun": bubun,
        }

    def test_collects_distinct_pnus_over_all_rows_and_ignores_rows_without_address(
        self,
    ):
        # 28260-138 마전동아: 행정구역 개편 전후 umd_cd 11300/10300 이 섞여 있다
        rows = [
            self.row("28260-138", "11300"),
            self.row("28260-138", "10300"),
            self.row("28260-138", "11300"),
            self.row(
                "28260-138", None, bonbun=None, bubun=None
            ),  # 전월세 행 — 주소 없음
            self.row("28260-999", None, bonbun=None, bubun=None),
        ]
        got = address_rows_by_key(rows)
        self.assertEqual(
            set(got["28260-138"]),
            {"2826011300010030001", "2826010300010030001"},
        )
        self.assertNotIn("28260-999", got)
        # 대표 행은 그 PNU 를 만든 첫 행
        self.assertIs(got["28260-138"]["2826011300010030001"], rows[0])

    def test_blank_bonbun_is_no_address(self):
        self.assertEqual(address_rows_by_key([self.row("K", "11300", bonbun="  ")]), {})


class UniqueExistingPnuTest(unittest.TestCase):
    A, B = "2826011300010030001", "2826010300010030001"

    def test_only_one_exists(self):
        self.assertEqual(unique_existing_pnu({self.A, self.B}, {self.A}), self.A)

    def test_both_exist_is_ambiguous(self):
        self.assertIsNone(unique_existing_pnu({self.A, self.B}, {self.A, self.B}))

    def test_none_exists(self):
        self.assertIsNone(unique_existing_pnu({self.A, self.B}, set()))
        self.assertIsNone(unique_existing_pnu(set(), {self.A}))


if __name__ == "__main__":
    unittest.main()
