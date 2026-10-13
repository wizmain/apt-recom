"""load_trades 가 ADR-015 키 규칙으로 행을 만드는지 — DB 없이 SQL·행 캡처."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade import load_trades as mod


class _Logger:
    def info(self, *_a, **_k):
        pass


def _trade(apt_seq_api):
    return {
        "sggCd": "11590",
        "aptNm": "대림아파트",
        "excluUseAr": "84.89",
        "floor": "13",
        "dealYear": "2026",
        "dealMonth": "7",
        "dealDay": "2",
        "dealAmount": "105,000",
        "buildYear": "1995",
        "aptSeq": apt_seq_api,
    }


def _rent(apt_seq_api):
    return {
        "sggCd": "11590",
        "aptNm": "대림아파트",
        "excluUseAr": "84.89",
        "floor": "13",
        "dealYear": "2026",
        "dealMonth": "7",
        "dealDay": "2",
        "deposit": "50,000",
        "monthlyRent": "0",
        "buildYear": "1995",
        "aptSeq": apt_seq_api,
    }


class LoadTradesKeyTest(unittest.TestCase):
    def _run(self, trade_rows, rent_rows):
        captured = []

        def fake_exec(conn, sql, rows, chunk_size=10000):
            captured.append((sql, rows))
            return len(rows)

        with (
            patch.object(mod, "query_all", return_value=[]),
            patch.object(mod, "load_aliases", return_value={}),
            patch.object(mod, "execute_values_chunked", fake_exec),
        ):
            mod.load_trades(None, trade_rows, rent_rows, _Logger())
        return captured

    def test_trade_with_api_seq_uses_it(self):
        ((sql, rows),) = self._run([_trade("11590-85")], [])
        self.assertIn("legacy_apt_seq, apt_seq_method", sql)
        row = rows[0]
        self.assertEqual(row[0], "11590-85")
        self.assertEqual(row[-2:], ("11590_대림아파트", "api"))

    def test_trade_without_api_seq_keeps_name_key(self):
        ((_sql, rows),) = self._run([_trade("")], [])
        self.assertEqual(rows[0][0], "11590_대림아파트")
        self.assertEqual(rows[0][-2:], (None, None))

    def test_rent_with_api_seq_and_build_year(self):
        ((sql, rows),) = self._run([], [_rent("11590-85")])
        self.assertIn("build_year", sql)
        row = rows[0]
        self.assertEqual(row[0], "11590-85")
        self.assertEqual(row[-3:], (1995, "11590_대림아파트", "api"))


if __name__ == "__main__":
    unittest.main()
