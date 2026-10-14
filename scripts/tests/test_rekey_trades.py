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


class RowsToRevertTest(unittest.TestCase):
    """Fix B — 새 키가 매핑되지 못하면 계획 행만 이름 키로 되돌린다(현상 유지)."""

    def test_only_planned_rows_of_unmapped_keys(self):
        plan = {
            "trade_history": [
                (1, "11590-57", "api"),
                (2, "11590-99", "infer_single"),
                (3, "11590-99", "api"),
            ],
            "rent_history": [(7, "11590-99", "infer_area"), (8, "11590-57", "api")],
        }
        self.assertEqual(
            rekey_trades.rows_to_revert(plan, {"11590-99"}),
            {"trade_history": [2, 3], "rent_history": [7]},
        )

    def test_unmapped_key_not_in_plan_touches_nothing(self):
        # 적재기가 쓴 'api' 행만 가진 키 — 계획에 없으므로 되돌릴 행이 없다
        plan = {"trade_history": [(1, "11590-57", "api")], "rent_history": []}
        self.assertEqual(
            rekey_trades.rows_to_revert(plan, {"11590-77"}),
            {"trade_history": [], "rent_history": []},
        )

    def test_nothing_unmapped(self):
        plan = {"trade_history": [(1, "11590-57", "api")]}
        self.assertEqual(
            rekey_trades.rows_to_revert(plan, set()), {"trade_history": []}
        )

    L2 = "11590_대림"  # 계획 행이 전부 되돌려지는 이름 키

    def run_apply_and_verify(self, before_violations, after_violations):
        known = [KnownRow(L, "11590-57", 1993, 84.92)]
        snap = Snapshot({"trade_history": 1}, 0, {})
        mapped = [
            {"apt_seq": "11590-57", "pnu": "P", "match_method": "api_address_pnu"}
        ]
        plan = {
            "trade_history": [(1, "11590-57", "api"), (2, "11590-85", "api")],
            "rent_history": [(5, "11590-85", "infer_area")],
        }
        audited = []
        audit_results = iter([before_violations, after_violations])

        def fake_audit(c, lg, apt_seqs):
            audited.append(apt_seqs)
            return next(audit_results)

        moved_queries = []

        def fake_query_all(c, sql, params):
            moved_queries.append((sql.split("FROM ")[1].split()[0], params[0]))
            return [{"legacy_apt_seq": L}]

        with (
            mock.patch.object(rekey_trades, "_allowed_pnus", return_value=set()),
            mock.patch.object(rekey_trades, "_snapshot", return_value=snap),
            mock.patch.object(rekey_trades, "_current_keys", return_value=[self.L2, L]),
            mock.patch.object(rekey_trades, "audit", side_effect=fake_audit),
            mock.patch.object(rekey_trades, "_apply"),
            mock.patch.object(rekey_trades, "_mappings", side_effect=[[], mapped]),
            mock.patch.object(rekey_trades, "map_api_keys"),
            mock.patch.object(
                rekey_trades,
                "_key_pairs",
                side_effect=lambda c, t, ids: [("11590-85", self.L2)],
            ),
            mock.patch.object(rekey_trades, "query_all", side_effect=fake_query_all),
            mock.patch.object(rekey_trades, "_revert") as revert,
        ):
            errors, reverted = rekey_trades.apply_and_verify(
                mock.MagicMock(), "11590", mock.MagicMock(), plan, known, []
            )
        return errors, reverted, audited, revert, moved_queries

    def test_apply_and_verify_reverts_unmapped_planned_rows_and_drops_key_from_audit(
        self,
    ):
        errors, reverted, audited, revert, moved_queries = self.run_apply_and_verify(
            [], []
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            sorted((c[0][1], c[0][2]) for c in revert.call_args_list),
            [("rent_history", [5]), ("trade_history", [2])],
        )
        # 체크포인트용 전체 {새 키: [이름 키]} 를 담는다
        self.assertEqual(
            reverted,
            {
                "keys": 1,
                "rows": {"trade_history": 1, "rent_history": 1},
                "map": {"11590-85": [self.L2]},
            },
        )
        # 변경 전 감사는 계획 전체 이름 키, 변경 후 감사는 매핑된 새 키만
        self.assertEqual(audited, [[self.L2, L], ["11590-57"]])
        # 남은(되돌리지 않은) 계획 행으로만 옮겨진 이름 키를 찾는다
        self.assertEqual(moved_queries, [("trade_history", [1])])

    def test_fully_reverted_old_key_violation_does_not_mask_new_violation(self):
        # L2 의 기존 위반은 L2 행이 전부 되돌려져 기준선에서 빠진다 → 새 키 위반 1건이 드러난다
        errors, *_ = self.run_apply_and_verify(
            [{"apt_seq": self.L2}], [{"apt_seq": "11590-57"}]
        )
        self.assertEqual(errors, ["감사 위반 증가 0 → 1"])

    def test_violation_of_still_moved_old_key_stays_in_baseline(self):
        errors, *_ = self.run_apply_and_verify(
            [{"apt_seq": L}, {"apt_seq": self.L2}], [{"apt_seq": "11590-57"}]
        )
        self.assertEqual(errors, [])


class BaselineViolationCountTest(unittest.TestCase):
    def test_counts_only_violations_of_old_keys_with_moved_rows(self):
        violations = [{"apt_seq": "A"}, {"apt_seq": "B"}, {"apt_seq": "C"}]
        self.assertEqual(
            rekey_trades.baseline_violation_count(violations, {"A", "C", "Z"}), 2
        )

    def test_nothing_moved_is_zero(self):
        self.assertEqual(
            rekey_trades.baseline_violation_count([{"apt_seq": "A"}], set()), 0
        )


class RevertedKeyMapTest(unittest.TestCase):
    def test_lists_all_legacy_keys_per_new_key(self):
        pairs = [("K1", "L_b"), ("K1", "L_a"), ("K2", "L_a"), ("K1", "L_a")]
        self.assertEqual(
            rekey_trades.reverted_key_map(pairs),
            {"K1": ["L_a", "L_b"], "K2": ["L_a"]},
        )


class KnownTrimsApiIdTest(unittest.TestCase):
    """최종 리뷰 #6 — _known 의 고유번호는 공백 제거 값(적재·대상 행과 같은 기준)."""

    def test_select_uses_btrim(self):
        with mock.patch.object(rekey_trades, "query_all", return_value=[]) as q:
            rekey_trades._known(None, "11590", "trade_history", True)
        self.assertIn("btrim(api_apt_seq) AS api_apt_seq", q.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
