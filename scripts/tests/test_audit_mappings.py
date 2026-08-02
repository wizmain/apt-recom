"""batch.trade.audit_mappings 검증 — DB·네트워크 없이 확인 (CI 대상).

audit() 자체는 DB 를 읽지만, 판정 로직과 "고치지 않는다"는 계약은 가짜
커넥션으로 검증할 수 있다. 실제 쿼리는 별도 CLI 실행으로 확인한다.
"""

import unittest

from batch.trade.audit_mappings import _as_apt, _as_deal, audit


class _FakeCursor:
    """query_all 이 쓰는 최소 인터페이스. 실행된 SQL 을 기록한다."""

    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def execute(self, sql, params=None):
        self._log.append(sql)

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.executed: list[str] = []

    def cursor(self, *a, **kw):
        return _FakeCursor(self.rows, self.executed)


class _FakeLogger:
    def __init__(self):
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)


def _row(**kw):
    base = {
        "apt_seq": "11110_A", "apt_nm": "A", "pnu": "1111011700001000000",
        "match_method": "exact_name", "trades": 10, "rents": 5,
        "max_floor": 20, "min_deal_year": 2010, "median_build_year": 2005,
        "areas": [(84.9, 10)],
        "bld_nm": "A", "apt_max_floor": 25, "use_apr_day": "20050101",
        "apt_areas": [84.9],
    }
    base.update(kw)
    return base


class TestRowMapping(unittest.TestCase):
    def test_실적과_아파트_속성을_분리한다(self):
        r = _row()
        self.assertEqual(_as_deal(r)["max_floor"], 20)
        self.assertEqual(_as_apt(r)["max_floor"], 25)
        self.assertEqual(_as_apt(r)["areas"], [84.9])


class TestAudit(unittest.TestCase):
    def test_정합한_매핑은_위반이_아니다(self):
        log = _FakeLogger()
        v = audit(_FakeConn([_row()]), log)
        self.assertEqual(v, [])
        self.assertEqual(log.warnings, [])
        self.assertTrue(log.infos)

    def test_두_지표가_어긋나면_위반이다(self):
        """산내마을1단지행복주택 유형 — 단지번호 + 층."""
        log = _FakeLogger()
        row = _row(apt_nm="산내마을1단지행복주택", bld_nm="산내마을8단지월드메르디앙",
                   max_floor=25, apt_max_floor=15)
        v = audit(_FakeConn([row]), log)
        self.assertEqual(len(v), 1)
        reasons = " ".join(v[0]["reasons"])
        self.assertIn("단지번호", reasons)
        self.assertIn("층", reasons)
        self.assertTrue(log.warnings)

    def test_면적이_거의_안_맞으면_단독으로도_위반이다(self):
        log = _FakeLogger()
        row = _row(areas=[(84.28, 58), (84.84, 11)], apt_areas=[84.8198])
        v = audit(_FakeConn([row]), log)
        self.assertEqual(len(v), 1)
        self.assertTrue(any("면적" in r for r in v[0]["reasons"]))

    def test_지표_하나만_어긋나면_위반이_아니다(self):
        """분양권 거래·건축물대장 층수 편차 오탐을 막는 보정."""
        log = _FakeLogger()
        v = audit(_FakeConn([_row(min_deal_year=2000)]), log)  # 타임라인 단독
        self.assertEqual(v, [])

    def test_데이터를_바꾸지_않는다(self):
        """자동 교정 금지 — UPDATE/DELETE/INSERT 를 실행하면 안 된다."""
        conn = _FakeConn([_row(areas=[(30.0, 10)], apt_areas=[84.9])])
        audit(conn, _FakeLogger())
        joined = " ".join(conn.executed).upper()
        for verb in ("UPDATE ", "DELETE ", "INSERT "):
            self.assertNotIn(verb, joined)

    def test_위반_항목은_교정에_필요한_정보를_담는다(self):
        log = _FakeLogger()
        v = audit(_FakeConn([_row(areas=[(30.0, 10)], apt_areas=[84.9])]), log)[0]
        for key in ("apt_seq", "pnu", "apt_nm", "bld_nm", "match_method",
                    "trades", "rents", "reasons"):
            self.assertIn(key, v)


if __name__ == "__main__":
    unittest.main()
