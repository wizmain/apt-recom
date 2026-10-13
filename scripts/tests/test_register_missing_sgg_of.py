"""register_missing_apartments._sgg_of — 키 문자열을 해석하지 않고 칼럼에서 조회 (ADR-015)."""
import unittest

from scripts.register_missing_apartments import _sgg_of


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


class SggOfTest(unittest.TestCase):
    def test_reads_sgg_from_column_for_opaque_key(self):
        cur = _FakeCursor({"sgg_cd": "11590"})
        self.assertEqual(_sgg_of(cur, "11590-57"), "11590")
        self.assertEqual(cur.calls[0][1], ["11590-57", "11590-57"])

    def test_returns_none_when_key_unknown(self):
        self.assertIsNone(_sgg_of(_FakeCursor(None), "99999-1"))


if __name__ == "__main__":
    unittest.main()
