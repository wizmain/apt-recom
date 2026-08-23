"""batch.annual.collect_building_register 순수 함수 — DB·네트워크 없이 확인 (CI 대상)."""

import unittest

from batch.annual.collect_building_register import (
    UPSERT_SQL,
    _aggregate,
    _valid_use_days,
)


class _Logger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass


def dong(**kw):
    base = {
        "bldNm": "101동",
        "mainPurpsCdNm": "공동주택(아파트)",
        "hhldCnt": "100",
        "useAprDay": "20210629",
        "rideUseElvtCnt": "2",
        "emgenUseElvtCnt": "1",
        "indrAutoUtcnt": "50",
        "oudrAutoUtcnt": "10",
        "indrMechUtcnt": "0",
        "oudrMechUtcnt": "0",
    }
    base.update(kw)
    return base


class TestValidUseDays(unittest.TestCase):
    def test_오름차순으로_정렬한다(self):
        self.assertEqual(
            _valid_use_days([dong(useAprDay="20210629"), dong(useAprDay="20200101")]),
            ["20200101", "20210629"],
        )

    def test_형식이_틀린_값은_버린다(self):
        """원천에 ''·'0'·'00000000' 이 섞여 있어 그대로 쓰면 min 이 오염된다."""
        items = [
            dong(useAprDay=""),
            dong(useAprDay="0"),
            dong(useAprDay="00000000"),
            dong(useAprDay="20210629"),
        ]
        self.assertEqual(_valid_use_days(items), ["20210629"])

    def test_전부_비정상이면_빈_목록(self):
        self.assertEqual(_valid_use_days([dong(useAprDay=""), dong(useAprDay=None)]), [])

    def test_중복은_한_번만(self):
        items = [dong(useAprDay="20210629"), dong(useAprDay="20210629")]
        self.assertEqual(_valid_use_days(items), ["20210629"])


class TestAggregate(unittest.TestCase):
    def test_사용승인일_범위를_담는다(self):
        agg = _aggregate(
            [dong(useAprDay="20200101"), dong(useAprDay="20210629")], _Logger(), "p"
        )
        self.assertEqual(agg["register_use_apr_day"], "20200101")
        self.assertEqual(agg["register_use_apr_day_max"], "20210629")

    def test_편차가_없으면_min_max_가_같다(self):
        agg = _aggregate([dong(), dong()], _Logger(), "p")
        self.assertEqual(agg["register_use_apr_day"], agg["register_use_apr_day_max"])

    def test_사용승인일이_없으면_None(self):
        """기존 필드는 그대로 집계되어야 한다 — 날짜 부재가 수집을 막으면 안 된다."""
        agg = _aggregate([dong(useAprDay="")], _Logger(), "p")
        self.assertIsNone(agg["register_use_apr_day"])
        self.assertIsNone(agg["register_use_apr_day_max"])
        self.assertEqual(agg["register_hhld_cnt"], 100)

    def test_비주거_동은_제외된다(self):
        """관리동·상가의 준공일이 단지 값으로 새면 안 된다."""
        items = [
            dong(useAprDay="20210629"),
            dong(mainPurpsCdNm="제1종근린생활시설", useAprDay="19900101", hhldCnt="0"),
        ]
        agg = _aggregate(items, _Logger(), "p")
        self.assertEqual(agg["register_use_apr_day"], "20210629")
        self.assertEqual(agg["register_dong_cnt"], 1)


class TestUpsertSql(unittest.TestCase):
    def test_플레이스홀더_수가_컬럼과_맞는다(self):
        """VALUES 개수가 어긋나면 실행 시점에야 터진다."""
        cols = UPSERT_SQL.split("(", 2)[1].split(")")[0]
        n_cols = len([c for c in cols.split(",") if c.strip()])
        # updated_at 은 NOW() 라 플레이스홀더가 없다
        self.assertEqual(UPSERT_SQL.count("%s"), n_cols - 1)

    def test_사용승인일이_upsert_대상이다(self):
        self.assertIn("register_use_apr_day = EXCLUDED.register_use_apr_day", UPSERT_SQL)


if __name__ == "__main__":
    unittest.main()
