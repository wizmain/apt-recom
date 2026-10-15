"""키 변경 스크립트의 순수 로직 — 구 단위 계획과 커밋 전 불변식 (설계 4-3·4-5)."""

import sys
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch import rekey_trades
from batch.rekey_trades import SKIP_STATUSES, Snapshot, check_invariants, plan_sgg
from batch.trade.remap_verification import (
    RemapVerification,
    verification_from_checkpoint,
    verified_existing_keys,
)
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
            {"apt_seq": "11590-57", "pnu": "P_OLD", "match_method": "api_address_pnu"}
        ]
        after_rows = before_rows + [
            {"apt_seq": "11590-85", "pnu": "P_NEW", "match_method": "api_address_pnu"}
        ]
        old_rows = [{"apt_seq": L, "pnu": "P_L", "match_method": "exact_name"}]
        snaps = iter([old_rows, before_rows, after_rows])

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
        # 이름 키 매핑(F3 출발 PNU) → 새 키 매핑 스냅샷 → map_api_keys → 변경 후
        self.assertEqual(calls, ["mappings", "mappings", "map_api_keys", "mappings"])
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

        def fake_key_pairs(c, table, ids):
            moved_queries.append((table, ids))
            # 되돌림 대상 행(2·5) → L2, 남은 행(1) → L
            return [("11590-85", self.L2)] if 1 not in ids else [("11590-57", L)]

        old_mappings = [{"apt_seq": L, "pnu": "P_L", "match_method": "exact_name"}]
        with (
            mock.patch.object(rekey_trades, "_allowed_pnus", return_value=set()),
            mock.patch.object(rekey_trades, "_snapshot", return_value=snap),
            mock.patch.object(rekey_trades, "_current_keys", return_value=[self.L2, L]),
            mock.patch.object(rekey_trades, "audit", side_effect=fake_audit),
            mock.patch.object(rekey_trades, "_apply"),
            mock.patch.object(
                rekey_trades, "_mappings", side_effect=[old_mappings, [], mapped]
            ),
            mock.patch.object(rekey_trades, "map_api_keys"),
            mock.patch.object(rekey_trades, "_key_pairs", side_effect=fake_key_pairs),
            mock.patch.object(rekey_trades, "_revert") as revert,
        ):
            errors, reverted, _review = rekey_trades.apply_and_verify(
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
        # 남은(되돌리지 않은) 계획 행으로만 옮겨진 이름 키를 찾는다 (되돌림 조회 다음)
        self.assertEqual(moved_queries[-1], ("trade_history", [1]))

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


class AttributionPreservingTest(unittest.TestCase):
    """F3a — 귀속 보존 키는 감사 비교 양쪽에서 빼고 재매칭 검토 목록으로 남긴다."""

    # K_INH: 이름 키 L_A(P_A) 행을 같은 P_A 로 상속 / K_ADDR: L_B(P_B) 행을 주소 P_X 로
    PAIRS: ClassVar = {"K_INH": {"L_A"}, "K_ADDR": {"L_B"}, "K_SPLIT": {"L_A", "L_C"}}
    OLD: ClassVar = {"L_A": "P_A", "L_B": "P_B", "L_C": "P_C"}
    NEW: ClassVar = {"K_INH": "P_A", "K_ADDR": "P_X", "K_SPLIT": "P_A"}

    def test_preserving_keys(self):
        self.assertEqual(
            rekey_trades.preserving_keys(self.PAIRS, self.OLD, self.NEW), {"K_INH"}
        )

    def test_unmapped_legacy_is_not_preserving(self):
        self.assertEqual(
            rekey_trades.preserving_keys({"K": {"L_X"}}, {}, {"K": "P"}), set()
        )

    def test_fully_preserved_old_keys(self):
        # L_A 행 일부는 K_SPLIT(비보존)로도 갔다 → 기준선에 남는다
        self.assertEqual(
            rekey_trades.fully_preserved_old_keys(self.PAIRS, {"K_INH"}), set()
        )
        self.assertEqual(
            rekey_trades.fully_preserved_old_keys({"K_INH": {"L_A"}}, {"K_INH"}),
            {"L_A"},
        )

    def test_inherit_only_violation_excluded_from_both_sides_and_listed(self):
        before = [{"apt_seq": "L_A"}, {"apt_seq": "L_B"}]
        after = [
            {
                "apt_seq": "K_INH",
                "pnu": "P_A",
                "apt_nm": "금호",
                "bld_nm": "영주동아",
                "match_method": "api_inherit_legacy",
                "reasons": ["면적 일치 0%"],
            },
        ]
        pairs = {"K_INH": {"L_A"}, "K_ADDR": {"L_B"}}
        cmp = rekey_trades.compare_audits(
            before, after, {"L_A", "L_B"}, {"K_INH"}, {"L_A"}, pairs
        )
        self.assertEqual((cmp.before, cmp.after), (1, 0))
        self.assertEqual(
            cmp.rematch_review,
            [
                {
                    "apt_seq": "K_INH",
                    "legacy_keys": ["L_A"],
                    "pnu": "P_A",
                    "apt_nm": "금호",
                    "bld_nm": "영주동아",
                    "match_method": "api_inherit_legacy",
                    "reasons": ["면적 일치 0%"],
                }
            ],
        )

    def test_non_preserving_violation_still_counts(self):
        cmp = rekey_trades.compare_audits(
            [], [{"apt_seq": "K_ADDR"}], {"L_B"}, {"K_INH"}, set(), {"K_ADDR": {"L_B"}}
        )
        self.assertEqual((cmp.before, cmp.after, cmp.rematch_review), (0, 1, []))

    def test_partial_preservation_does_not_hide_new_violation(self):
        # L_A 행이 보존 키 K_INH 와 비보존 키 K_SPLIT 로 나뉘었다 → L_A 는 기준선에 남으므로
        # K_INH 위반도 변경 후에서 빼면 안 된다 (빼면 L_A 위반이 K_SPLIT 신규 위반을 가린다)
        preserving = rekey_trades.preserving_keys(self.PAIRS, self.OLD, self.NEW)
        preserved_old = rekey_trades.fully_preserved_old_keys(self.PAIRS, preserving)
        cmp = rekey_trades.compare_audits(
            [{"apt_seq": "L_A"}],
            [{"apt_seq": "K_INH"}, {"apt_seq": "K_SPLIT"}],
            {"L_A", "L_B", "L_C"},
            preserving,
            preserved_old,
            self.PAIRS,
        )
        self.assertEqual((cmp.before, cmp.after, cmp.rematch_review), (1, 2, []))


class SourcePnusTest(unittest.TestCase):
    """F3b — 검증된 비상속 새 키로 행을 보낸 이름 키의 출발 PNU 만 허용 목록에 더한다."""

    def test_only_verified_non_inherit_moves(self):
        pairs = {"K_ADDR": {"L_B", "L_UNMAPPED"}, "K_INH": {"L_A"}}
        old = {"L_A": "P_A", "L_B": "P_B"}
        self.assertEqual(rekey_trades.source_pnus(pairs, old, {"K_ADDR"}), {"P_B"})
        self.assertEqual(rekey_trades.source_pnus(pairs, old, set()), set())

    def test_created_non_inherit_keys_excludes_pre_existing_and_inherit(self):
        after = [
            {"apt_seq": "K_OLD", "pnu": "P1", "match_method": "api_address_pnu"},
            {"apt_seq": "K_NEW", "pnu": "P2", "match_method": "api_address_pnu"},
            {"apt_seq": "K_INH", "pnu": "P3", "match_method": "api_inherit_legacy"},
        ]
        self.assertEqual(
            rekey_trades.created_non_inherit_keys({"K_OLD"}, after), {"K_NEW"}
        )

    def test_apply_and_verify_allows_source_pnu_of_verified_move(self):
        # 41135 무지개마을형: L_B(P_B) 행이 검증된 주소 매핑 K_ADDR(P_X)로 옮겨 P_B 귀속이 줄어든다
        plan = {"trade_history": [(1, "K_ADDR", "api")], "rent_history": []}
        captured = {}

        def fake_check(before, after, allowed, ab, aa):
            captured["allowed"] = allowed
            return []

        with (
            mock.patch.object(rekey_trades, "_allowed_pnus", return_value=set()),
            mock.patch.object(rekey_trades, "_snapshot"),
            mock.patch.object(rekey_trades, "_current_keys", return_value=["L_B"]),
            mock.patch.object(rekey_trades, "audit", return_value=[]),
            mock.patch.object(rekey_trades, "_apply"),
            mock.patch.object(
                rekey_trades,
                "_mappings",
                side_effect=[
                    [{"apt_seq": "L_B", "pnu": "P_B", "match_method": "exact_name"}],
                    [],
                    [
                        {
                            "apt_seq": "K_ADDR",
                            "pnu": "P_X",
                            "match_method": "api_address_pnu",
                        }
                    ],
                ],
            ),
            mock.patch.object(rekey_trades, "map_api_keys"),
            mock.patch.object(
                rekey_trades, "_key_pairs", return_value=[("K_ADDR", "L_B")]
            ),
            mock.patch.object(rekey_trades, "check_invariants", side_effect=fake_check),
        ):
            _, _, review = rekey_trades.apply_and_verify(
                mock.MagicMock(), "41135", mock.MagicMock(), plan, [], []
            )
        self.assertEqual(captured["allowed"], {"P_X", "P_B"})
        self.assertEqual(review, [])


class RemapVerifiedF3bTest(unittest.TestCase):
    """재판정이 검증한 기존 비상속 매핑은 이번 실행 생성분처럼 출발·도착 PNU 를 허용한다."""

    def run_with(self, remap, after_violations=()):
        # L_B(P_B) 행이 이전부터 있던 주소 매핑 K_ADDR(P_X) 로 옮겨진다
        plan = {"trade_history": [(1, "K_ADDR", "api")], "rent_history": []}
        k_addr = {"apt_seq": "K_ADDR", "pnu": "P_X", "match_method": "api_address_pnu"}
        captured = {}

        def fake_check(before, after, allowed, ab, aa):
            captured["allowed"] = allowed
            return []

        with (
            mock.patch.object(rekey_trades, "_allowed_pnus", return_value=set()),
            mock.patch.object(rekey_trades, "_snapshot"),
            mock.patch.object(rekey_trades, "_current_keys", return_value=["L_B"]),
            mock.patch.object(
                rekey_trades, "audit", side_effect=[[], list(after_violations)]
            ),
            mock.patch.object(rekey_trades, "_apply"),
            mock.patch.object(
                rekey_trades,
                "_mappings",
                side_effect=[
                    [{"apt_seq": "L_B", "pnu": "P_B", "match_method": "exact_name"}],
                    [k_addr],
                    [k_addr],
                ],
            ),
            mock.patch.object(rekey_trades, "map_api_keys"),
            mock.patch.object(
                rekey_trades, "_key_pairs", return_value=[("K_ADDR", "L_B")]
            ),
            mock.patch.object(rekey_trades, "check_invariants", side_effect=fake_check),
        ):
            rekey_trades.apply_and_verify(
                mock.MagicMock(), "11410", mock.MagicMock(), plan, [], [], remap=remap
            )
        return captured["allowed"]

    def test_remap_verified_existing_mapping_allows_source_and_destination(self):
        remap = RemapVerification("T", {"K_ADDR": "P_X"}, frozenset({"K_ADDR"}))
        self.assertEqual(self.run_with(remap), {"P_X", "P_B"})

    def test_remap_verified_but_full_history_violation_is_unverified(self):
        # 리뷰 #1 — 재판정 게이트는 적재 행 몇 개만 봤다. 옮긴 전체 행 감사에 위반이면 신뢰하지 않는다
        remap = RemapVerification("T", {"K_ADDR": "P_X"}, frozenset({"K_ADDR"}))
        violation = {"apt_seq": "K_ADDR", "pnu": "P_X", "reasons": ["층"]}
        self.assertEqual(self.run_with(remap, [violation]), set())

    def test_remap_verified_with_different_pnu_is_unverified(self):
        # 리뷰 #4 — 체크포인트의 PNU 와 지금 매핑 PNU 가 다르면 재판정 이후 바뀐 매핑
        remap = RemapVerification("T", {"K_ADDR": "P_OTHER"}, frozenset({"K_ADDR"}))
        self.assertEqual(self.run_with(remap), set())

    def test_created_after_remap_is_verified(self):
        # 재판정 당시 비상속 매핑이 아니었던 키 — 이후 현재 규칙의 map_api_keys 가 만든 것
        remap = RemapVerification("T", {}, frozenset({"OTHER"}))
        self.assertEqual(self.run_with(remap), {"P_X", "P_B"})

    def test_created_after_remap_with_violation_is_unverified(self):
        remap = RemapVerification("T", {}, frozenset({"OTHER"}))
        self.assertEqual(self.run_with(remap, [{"apt_seq": "K_ADDR"}]), set())

    def test_judged_but_not_verified_stays_unverified(self):
        # 재판정이 지운 뒤 다시 생긴 키·blocked_delete 키 — 미검증
        remap = RemapVerification("T", {}, frozenset({"K_ADDR"}))
        self.assertEqual(self.run_with(remap), set())

    def test_without_remap_pre_existing_stays_unverified(self):
        self.assertEqual(self.run_with(None), set())

    def test_inherit_mapping_never_verified_by_remap(self):
        remap = RemapVerification("T", {"K": "P"}, frozenset({"K"}))
        rows = [{"apt_seq": "K", "pnu": "P", "match_method": "api_inherit_legacy"}]
        self.assertEqual(
            verified_existing_keys({"K"}, rows, remap, "api_inherit_legacy"), set()
        )


class RemapCheckpointGuardTest(unittest.TestCase):
    def test_apply_refused_without_checkpoint(self):
        with self.assertRaises(SystemExit):
            rekey_trades.require_remap_checkpoint(None, True, mock.MagicMock())

    def test_dry_run_only_warns(self):
        logger = mock.MagicMock()
        rekey_trades.require_remap_checkpoint(None, False, logger)
        logger.warning.assert_called_once()

    def test_apply_allowed_with_checkpoint(self):
        remap = RemapVerification("T", {}, frozenset())
        rekey_trades.require_remap_checkpoint(remap, True, mock.MagicMock())

    def test_old_format_checkpoint_counts_as_missing(self):
        self.assertIsNone(verification_from_checkpoint("T", '{"total": 1}'))
        # PNU 없는 목록 형식(첫 구현)도 옛 형식 — 리뷰 #4
        self.assertIsNone(
            verification_from_checkpoint(
                "T",
                '{"verified_non_inherit_keys": ["A"], "judged_non_inherit_keys": ["A"]}',
            )
        )
        got = verification_from_checkpoint(
            "T",
            '{"verified_non_inherit_keys": {"A": "P"}, "judged_non_inherit_keys": ["A", "B"]}',
        )
        self.assertEqual(got, RemapVerification("T", {"A": "P"}, frozenset("AB")))

    def test_empty_checkpoint_passes_guard(self):
        # 리뷰 #5 — api_ 매핑 0건이어도 재판정 --apply 는 빈 체크포인트를 남기고, 그걸로 통과
        got = verification_from_checkpoint(
            "T", '{"verified_non_inherit_keys": {}, "judged_non_inherit_keys": []}'
        )
        self.assertEqual(got, RemapVerification("T", {}, frozenset()))
        rekey_trades.require_remap_checkpoint(got, True, mock.MagicMock())

    def test_main_apply_with_sgg_obeys_guard(self):
        argv = ["rekey_trades", "--target", "local", "--apply", "--sgg", "11410"]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(rekey_trades, "db_url", return_value="x"),
            mock.patch.object(rekey_trades.psycopg2, "connect"),
            mock.patch.object(rekey_trades, "try_trade_write_lock", return_value=True),
            mock.patch.object(rekey_trades, "load_latest", return_value=None),
            mock.patch.object(rekey_trades, "rekey_sgg") as run,
            self.assertRaises(SystemExit),
        ):
            rekey_trades.main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
