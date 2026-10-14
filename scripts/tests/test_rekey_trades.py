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


class CreatedMappingPnusTest(unittest.TestCase):
    """최종 리뷰 #1c — 허용 목록 확장은 이번 실행에서 새로 생긴 비상속 매핑만."""

    def test_pre_existing_and_inherited_mappings_are_excluded(self):
        after = [
            {"apt_seq": "11590-57", "pnu": "P_OLD", "match_method": "api_address_pnu"},
            {"apt_seq": "11590-85", "pnu": "P_NEW", "match_method": "api_address_pnu"},
            {
                "apt_seq": "11590-90",
                "pnu": "P_INH",
                "match_method": "api_inherit_legacy",
            },
        ]
        self.assertEqual(
            rekey_trades.created_mapping_pnus({"11590-57"}, after), {"P_NEW"}
        )

    def test_rekey_sgg_snapshots_mappings_before_map_api_keys(self):
        calls = []
        before_rows = [
            {"apt_seq": "11590-57", "pnu": "P_OLD", "match_method": "api_name_exact"}
        ]
        after_rows = before_rows + [
            {"apt_seq": "11590-85", "pnu": "P_NEW", "match_method": "api_address_pnu"}
        ]
        snaps = iter([before_rows, after_rows])

        def fake_mappings(conn, keys):
            calls.append("mappings")
            return next(snaps)

        def fake_map(conn, logger, apt_seqs):
            calls.append("map_api_keys")

        captured = {}

        def fake_check(before, after, allowed, ab, aa):
            captured["allowed"] = allowed
            return []

        known = [KnownRow(L, "11590-57", 1993, 84.92)]
        snap = Snapshot({"trade_history": 1}, 0, {})
        with (
            mock.patch.object(rekey_trades, "_known", return_value=known),
            mock.patch.object(
                rekey_trades,
                "_targets",
                return_value=([(1, "11590-57"), (2, "11590-85")], []),
            ),
            mock.patch.object(rekey_trades, "_allowed_pnus", return_value=set()),
            mock.patch.object(rekey_trades, "_snapshot", return_value=snap),
            mock.patch.object(rekey_trades, "_current_keys", return_value=[L]),
            mock.patch.object(rekey_trades, "audit", return_value=[]),
            mock.patch.object(rekey_trades, "_apply"),
            mock.patch.object(rekey_trades, "_mappings", side_effect=fake_mappings),
            mock.patch.object(rekey_trades, "map_api_keys", side_effect=fake_map),
            mock.patch.object(rekey_trades, "check_invariants", side_effect=fake_check),
            mock.patch.object(rekey_trades, "_save_checkpoint"),
        ):
            status = rekey_trades.rekey_sgg(
                mock.MagicMock(), "11590", mock.MagicMock(), apply=True
            )
        self.assertEqual(status, "done")
        self.assertEqual(calls, ["mappings", "map_api_keys", "mappings"])
        self.assertEqual(captured["allowed"], {"P_NEW"})


class KnownTrimsApiIdTest(unittest.TestCase):
    """최종 리뷰 #6 — _known 의 고유번호는 공백 제거 값(적재·대상 행과 같은 기준)."""

    def test_select_uses_btrim(self):
        with mock.patch.object(rekey_trades, "query_all", return_value=[]) as q:
            rekey_trades._known(None, "11590", "trade_history", True)
        self.assertIn("btrim(api_apt_seq) AS api_apt_seq", q.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
