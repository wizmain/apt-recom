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


class ExecuteValuesChunkedCountTest(unittest.TestCase):
    """반환값은 시도한 행 수가 아니라 실제 반영 행 수(rowcount 합)여야 한다."""

    def test_sums_rowcount_not_chunk_length(self):
        from batch import db

        class _Cur:
            rowcount = -1

        class _Conn:
            def __init__(self):
                self.cur = _Cur()
                self.commits = 0

            def cursor(self):
                return self.cur

            def commit(self):
                self.commits += 1

        # chunk 별 반영 수: 3행 중 2행, 2행 중 0행(전부 ON CONFLICT 로 버려짐)
        applied = iter([2, 0])

        def fake_execute_values(cur, _sql, _chunk, page_size):
            cur.rowcount = next(applied)

        conn = _Conn()
        with patch.object(db.psycopg2.extras, "execute_values", fake_execute_values):
            total = db.execute_values_chunked(
                conn, "SQL", [1, 2, 3, 4, 5], chunk_size=3
            )
        self.assertEqual(total, 2)
        self.assertEqual(conn.commits, 1)


if __name__ == "__main__":
    unittest.main()
