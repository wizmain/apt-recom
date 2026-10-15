"""기존 고유번호 키 매핑 재판정 (설계 4-4) — 순수 분류와 공용 판정 함수의 조회 범위. DB 없음."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch import remap_official_keys as R
from batch.trade import trade_key_mapping
from batch.trade.trade_key_mapping import KeyDecision, decide_api_keys

P1, P2 = "2826011300010030001", "2826010300010030001"


def dec(pnu, method="api_address_pnu"):
    return KeyDecision(pnu, method, "동아", "28260")


def old(pnu, method="api_address_pnu"):
    return R.OldMapping(pnu, method, "28260")


class ClassifyTest(unittest.TestCase):
    def test_same_pnu_is_keep_even_if_method_differs(self):
        self.assertEqual(R.classify(P1, dec(P1, "api_inherit_legacy")), R.ACTION_KEEP)

    def test_different_pnu_is_replace(self):
        self.assertEqual(R.classify(P2, dec(P1)), R.ACTION_REPLACE)

    def test_no_decision_is_delete(self):
        self.assertEqual(R.classify(P1, None), R.ACTION_DELETE)


class PlanRemapTest(unittest.TestCase):
    def test_actions_and_gate_rejection(self):
        olds = {
            "K_KEEP": old(P1),
            "K_REPL": old(P2, "api_name_exact"),
            "K_NONE": old(P1, "api_name_exact"),
            "K_GATE": old(P2),
        }
        decided = {"K_KEEP": dec(P1), "K_REPL": dec(P1), "K_GATE": dec(P1)}
        items = R.plan_remap(olds, decided, gate_rejected={"K_GATE"})
        got = {it.apt_seq: (it.action, it.new) for it in items}
        self.assertEqual(got["K_KEEP"], (R.ACTION_KEEP, dec(P1)))
        self.assertEqual(got["K_REPL"], (R.ACTION_REPLACE, dec(P1)))
        self.assertEqual(got["K_NONE"], (R.ACTION_DELETE, None))
        # 게이트 거부는 근거 없음 — 교체하지 않고 삭제
        self.assertEqual(got["K_GATE"], (R.ACTION_DELETE, None))
        self.assertEqual([it.apt_seq for it in items], sorted(olds))

    def test_summary_by_old_method(self):
        items = R.plan_remap(
            {"A": old(P1), "B": old(P1, "api_name_exact"), "C": old(P2)},
            {"A": dec(P1), "C": dec(P1)},
            set(),
        )
        self.assertEqual(
            R.summarize(items),
            {
                "delete": {"api_name_exact": 1},
                "keep": {"api_address_pnu": 1},
                "replace": {"api_address_pnu": 1},
            },
        )


class NonInheritVerdictsTest(unittest.TestCase):
    def test_verified_and_judged_sets(self):
        items = R.plan_remap(
            {
                "KEEP_ADDR": old(P1),
                "KEEP_NAME": old(
                    P1, "api_name_exact"
                ),  # 행 그대로 — 기존 method 로 비상속
                "REPL_TO_ADDR": old(P2, "api_inherit_legacy"),
                "DEL_NAME": old(P1, "api_name_exact"),
                "KEEP_INH": old(P1, "api_inherit_legacy"),
            },
            {
                "KEEP_ADDR": dec(P1),
                "KEEP_NAME": dec(P1),
                "REPL_TO_ADDR": dec(P1),
                "KEEP_INH": dec(P1, "api_inherit_legacy"),
            },
            set(),
        )
        verified, judged = R.non_inherit_verdicts(items)
        # 리뷰 #4 — 키별 확인한 PNU 를 남긴다(교체는 새 PNU)
        self.assertEqual(
            verified, {"KEEP_ADDR": P1, "KEEP_NAME": P1, "REPL_TO_ADDR": P1}
        )
        self.assertEqual(judged, ["DEL_NAME", "KEEP_ADDR", "KEEP_NAME", "REPL_TO_ADDR"])


class BlockedDeleteTest(unittest.TestCase):
    """리뷰 #2 — 이미 키를 바꾼 구에 행이 있는 키는 삭제하지 않는다(rekey 는 그 행을 다시 보지 않음)."""

    def test_rekeyed_delete_is_blocked_unless_allowed(self):
        olds = {"K_RK": old(P1), "K_NEW": old(P1)}
        blocked = R.plan_remap(olds, {}, set(), rekeyed_keys={"K_RK"})
        self.assertEqual(
            {it.apt_seq: it.action for it in blocked},
            {"K_RK": R.ACTION_BLOCKED_DELETE, "K_NEW": R.ACTION_DELETE},
        )
        allowed = R.plan_remap(
            olds, {}, set(), rekeyed_keys={"K_RK"}, allow_delete_rekeyed=True
        )
        self.assertEqual({it.action for it in allowed}, {R.ACTION_DELETE})

    def test_rekeyed_keep_and_replace_unaffected(self):
        items = R.plan_remap(
            {"A": old(P1), "B": old(P2)},
            {"A": dec(P1), "B": dec(P1)},
            set(),
            rekeyed_keys={"A", "B"},
        )
        self.assertEqual([it.action for it in items], [R.ACTION_KEEP, R.ACTION_REPLACE])

    def test_blocked_is_judged_but_not_verified(self):
        items = R.plan_remap({"K": old(P1)}, {}, set(), rekeyed_keys={"K"})
        self.assertEqual(R.non_inherit_verdicts(items), ({}, ["K"]))


class RowLossTest(unittest.TestCase):
    """리뷰 #3 — 보이던 행 손실(기존 PNU 실존)과 이미 보이지 않던 행을 나눠 센다."""

    def test_visible_and_invisible(self):
        items = R.plan_remap(
            {"VIS": old(P1), "DANG": old("GONE"), "BLK": old(P1)},
            {},
            set(),
            rekeyed_keys={"BLK"},
        )
        counts = {
            "VIS": {"trade_rows": 3, "rent_rows": 1, "inferred_rows": 0},
            "DANG": {"trade_rows": 5, "rent_rows": 0, "inferred_rows": 2},
            "BLK": {"trade_rows": 100, "rent_rows": 100, "inferred_rows": 0},
        }
        loss = R.deleted_row_loss(items, counts, existing_pnus={P1})
        self.assertEqual(
            loss.visible, {"trade_rows": 3, "rent_rows": 1, "inferred_rows": 0}
        )
        self.assertEqual(
            loss.invisible, {"trade_rows": 5, "rent_rows": 0, "inferred_rows": 2}
        )


class EmptyRunCheckpointTest(unittest.TestCase):
    """리뷰 #5·#6 — 대상 0건 --apply 도 체크포인트를 남기고, dry-run 게이트 로그는 쓰기를 암시하지 않는다."""

    def test_zero_mappings_apply_writes_empty_checkpoint(self):
        saved = {}
        with (
            patch.object(R, "_old_mappings", return_value={}),
            patch.object(R, "_rekeyed_sggs", return_value=set()),
            patch.object(R, "_write_report"),
            patch.object(R, "_apply"),
            patch.object(
                R, "_save_checkpoint", side_effect=lambda c, rid, d: saved.update(d)
            ),
        ):
            R.remap(MagicMock(), MagicMock(), True, "r.tsv", "T")
        self.assertEqual(saved["verified_non_inherit_keys"], {})
        self.assertEqual(saved["judged_non_inherit_keys"], [])
        self.assertEqual(saved["total"], 0)

    def test_dry_run_gate_log_says_would_reject(self):
        logger = MagicMock()
        violation = {
            "apt_seq": "K", "apt_nm": "a", "bld_nm": "b",
            "match_method": "api_address_pnu", "reasons": ["층"],
        }  # fmt: skip
        with (
            patch.object(R, "find_violations", return_value=([violation], 1)),
            patch.object(R, "_update_mappings"),
        ):
            got = R._gate_rejections(
                MagicMock(), logger, {"K": old(P2)}, {"K": dec(P1)}, apply=False
            )
        self.assertEqual(got, {"K"})
        msg = logger.warning.call_args[0][0]
        self.assertIn("dry-run", msg)
        self.assertNotIn("삭제 대상", msg)


class GateCandidatesTest(unittest.TestCase):
    def test_inherit_exempt_and_only_changed_pnus_rewritten(self):
        olds = {"INH": old(P2), "SAME": old(P1), "CHG": old(P2)}
        decided = {
            "INH": dec(P1, "api_inherit_legacy"),
            "SAME": dec(P1),
            "CHG": dec(P1),
            "NOT_OLD": dec(P1),  # 기존 api_ 매핑이 아닌 키는 대상 아님
        }
        keys, rewrite = R.gate_candidates(olds, decided)
        self.assertEqual(keys, ["CHG", "SAME"])
        self.assertEqual(rewrite, ["CHG"])


class DecideApiKeysScopeTest(unittest.TestCase):
    """공용 판정 함수 — map_api_keys 경로는 매핑 없는 키만, 재판정은 기존 매핑 무관 + 키 변경 전 행 포함."""

    def _capture(self, **kwargs):
        sqls = []

        def fake_query_all(conn, sql, params=None):
            sqls.append(sql)
            return []

        with patch.object(trade_key_mapping, "query_all", side_effect=fake_query_all):
            out = decide_api_keys(MagicMock(), MagicMock(), **kwargs)
        return out, sqls[0]

    def test_new_mapping_scope_excludes_mapped_and_pending_rows(self):
        out, sql = self._capture(apt_seqs=["K"])
        self.assertIn("NOT EXISTS", sql)
        self.assertNotIn("btrim(api_apt_seq)", sql)
        self.assertEqual(out.decided, {})

    def test_rejudge_scope_includes_mapped_and_pending_rows(self):
        _, sql = self._capture(apt_seqs=["K"], only_unmapped=False)
        self.assertNotIn("NOT EXISTS", sql)
        self.assertIn("apt_seq_method IS NULL AND btrim(api_apt_seq)", sql)

    def test_rejudge_requires_keys(self):
        with self.assertRaises(ValueError):
            decide_api_keys(MagicMock(), MagicMock(), only_unmapped=False)

    def test_pending_row_counts_toward_address_choice(self):
        # 28260-138: 적재 행(개편 전 umd) 1 + 키 변경 전 과거 행(개편 후 umd) — 주소 PNU 둘 다 실존 → 근거 없음
        rows = [
            {"apt_seq": "28260-138", "sgg_cd": "28260", "apt_nm": "동아",
             "umd_cd": "10300", "land_cd": "1", "bonbun": "1003", "bubun": "0001", "n": 1},
            {"apt_seq": "28260-138", "sgg_cd": "28260", "apt_nm": "동아",
             "umd_cd": "11300", "land_cd": "1", "bonbun": "1003", "bubun": "0001", "n": 7},
        ]  # fmt: skip

        def fake_query_all(conn, sql, params=None):
            if "FROM trade_history t" in sql:
                return rows
            if "SELECT pnu FROM apartments" in sql:
                return [{"pnu": P1}, {"pnu": P2}]
            return []

        with patch.object(trade_key_mapping, "query_all", side_effect=fake_query_all):
            out = decide_api_keys(
                MagicMock(), MagicMock(), ["28260-138"], only_unmapped=False
            )
        self.assertEqual(out.decided, {})
        self.assertEqual(out.unmapped, ["28260-138"])


class MapApiKeysUsesSharedDecisionTest(unittest.TestCase):
    """map_api_keys 는 decide_api_keys 판정을 그대로 넣는다 — 행 형식·순서 불변."""

    def test_inserts_decided_rows(self):
        kd = trade_key_mapping.KeyDecisions(
            {"K1": KeyDecision(P1, "api_address_pnu", "동아", "28260")}, ["K2"], {}
        )
        with (
            patch.object(trade_key_mapping, "decide_api_keys", return_value=kd) as d,
            patch.object(
                trade_key_mapping.psycopg2.extras,
                "execute_values",
                return_value=[("K1", "api_address_pnu")],
            ) as ins,
            patch.object(
                trade_key_mapping, "reject_unverified_mappings", return_value=[]
            ),
        ):
            mapped = trade_key_mapping.map_api_keys(MagicMock(), MagicMock(), ["K1"])
        self.assertEqual(d.call_args.kwargs, {})  # 기본 범위(매핑 없는 키만)
        self.assertEqual(
            ins.call_args[0][2], [("K1", P1, "동아", "28260", "api_address_pnu")]
        )
        self.assertEqual(mapped, 1)


if __name__ == "__main__":
    unittest.main()
