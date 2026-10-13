"""키 변경 스크립트의 순수 로직 — 구 단위 계획과 커밋 전 불변식 (설계 4-3·4-5)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch import rekey_trades
from batch.rekey_trades import SKIP_STATUSES, Snapshot, check_invariants, plan_sgg
from batch.trade.trade_key_inference import KnownRow, TargetRow

L = "11590_대림아파트"


class PlanSggTest(unittest.TestCase):
    def test_api_rows_and_inferred_rows(self):
        trade_known = [
            KnownRow(L, "11590-57", 1993, 84.92),
            KnownRow(L, "11590-85", 1995, 84.89),
        ]
        trade_targets = [TargetRow(1, L, 1993, 114.0), TargetRow(2, L, 2001, 84.0)]
        plan = plan_sgg(
            trade_known=trade_known,
            trade_api_rows=[(9, "11590-85")],
            trade_targets=trade_targets,
            rent_known=trade_known,
            rent_api_rows=[],
            rent_targets=[TargetRow(5, L, None, 84.89)],
        )
        self.assertEqual(
            sorted(plan["trade_history"]),
            [(1, "11590-57", "infer_year"), (9, "11590-85", "api")],
        )
        self.assertEqual(plan["rent_history"], [(5, "11590-85", "infer_area")])


class CheckInvariantsTest(unittest.TestCase):
    def snap(self, rows=10, unmapped=0, pnus=None):
        return Snapshot(
            {"trade_history": rows, "rent_history": rows},
            unmapped,
            pnus or {"A": 5, "B": 5},
        )

    def test_clean_change_passes(self):
        after = self.snap(pnus={"A": 4, "B": 6})
        self.assertEqual(check_invariants(self.snap(), after, {"A", "B"}, 0, 0), [])

    def test_row_count_change_fails(self):
        self.assertTrue(check_invariants(self.snap(), self.snap(rows=9), set(), 0, 0))

    def test_more_unmapped_fails(self):
        self.assertTrue(
            check_invariants(self.snap(), self.snap(unmapped=1), set(), 0, 0)
        )

    def test_change_outside_allowed_fails(self):
        after = self.snap(pnus={"A": 4, "B": 6})
        self.assertTrue(check_invariants(self.snap(), after, {"A"}, 0, 0))

    def test_audit_increase_fails(self):
        self.assertTrue(check_invariants(self.snap(), self.snap(), set(), 1, 2))


class CheckpointAndGuardTest(unittest.TestCase):
    def test_rolled_back_is_skipped_on_full_run(self):
        self.assertEqual(set(SKIP_STATUSES), {"done", "failed", "rolled_back"})

    def test_done_queries_skip_statuses(self):
        with mock.patch.object(
            rekey_trades, "query_all", return_value=[{"code": "11590"}]
        ) as q:
            self.assertEqual(rekey_trades._done(None), {"11590"})
        self.assertEqual(q.call_args[0][2][1], list(SKIP_STATUSES))

    def test_blank_api_seq_is_not_an_api_row(self):
        rows = [
            {
                "id": 1,
                "apt_seq": L,
                "api_apt_seq": " 11590-57 ",
                "by": 1993,
                "area": 84.9,
            },
            {"id": 2, "apt_seq": L, "api_apt_seq": "   ", "by": 1993, "area": 84.9},
            {"id": 3, "apt_seq": L, "api_apt_seq": "", "by": 1993, "area": 84.9},
            {"id": 4, "apt_seq": L, "api_apt_seq": None, "by": 1993, "area": 84.9},
        ]
        with mock.patch.object(rekey_trades, "query_all", return_value=rows):
            api_rows, targets = rekey_trades._targets(
                None, "11590", "trade_history", True
            )
        self.assertEqual(api_rows, [(1, "11590-57")])
        self.assertEqual([tg.row_id for tg in targets], [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
