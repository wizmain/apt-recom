"""새 키(국토부 고유번호) → PNU 매핑 순위 (설계 4-2) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from unittest.mock import MagicMock, patch

from batch.trade import trade_key_mapping
from batch.trade.trade_key_mapping import (
    MappingInput,
    decide_mapping,
    mapping_inputs_by_key,
    mixed_legacy_ids,
    most_frequent_value,
)

DAEBANG = "1159010800005010000"
SANGDO = "1159010200004110000"


def inp(legacy=(), addr=None, cands=(), apt_nm="대림아파트"):
    return MappingInput(apt_nm, frozenset(legacy), addr, tuple(cands))


class DecideMappingTest(unittest.TestCase):
    def test_rank1_inherits_single_legacy_pnu(self):
        self.assertEqual(
            decide_mapping(inp(legacy=[DAEBANG], addr=SANGDO)),
            (DAEBANG, "api_inherit_legacy"),
        )

    def test_conflicting_legacy_pnus_skip_inheritance(self):
        # Review Focus 3 — 이름 변형 키 둘이 다른 PNU 면 상속하지 않는다
        self.assertEqual(
            decide_mapping(inp(legacy=[DAEBANG, SANGDO], addr=SANGDO)),
            (SANGDO, "api_address_pnu"),
        )

    def test_rank2_address_pnu(self):
        self.assertEqual(decide_mapping(inp(addr=SANGDO)), (SANGDO, "api_address_pnu"))

    # 기대값은 recalc_price._normalize_name/_core_name 실측(2026-10-13)에 맞춘 것:
    # "상도 대림"→norm "상도대림" / "대방대림아파트"→norm 그대로·core "대방대림" / "대림아파트 "→core "대림"
    def test_rank3_exact_name_in_dong(self):
        cands = [(SANGDO, "상도 대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="상도대림")),
            (SANGDO, "api_name_exact"),
        )

    def test_rank3_contains_unique(self):
        cands = [(DAEBANG, "대방대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="대방대림아파트")),
            (DAEBANG, "api_name_contains"),
        )

    def test_rank3_core_unique(self):
        cands = [(SANGDO, "대림"), ("9" * 19, "현대")]
        self.assertEqual(
            decide_mapping(inp(cands=cands, apt_nm="대림아파트 ")),
            (SANGDO, "api_name_core"),
        )

    def test_rank3_same_name_twice_in_dong_is_unmapped(self):
        # 기존 이름 매칭은 정확 일치에서 첫 후보를 골랐다 — 동명 단지 혼입의 원인과 같다.
        cands = [(DAEBANG, "대림"), (SANGDO, "대림")]
        self.assertIsNone(decide_mapping(inp(cands=cands, apt_nm="대림")))

    def test_rank4_nothing_is_unmapped(self):
        self.assertIsNone(decide_mapping(inp()))


class FrozenInheritWarningTest(unittest.TestCase):
    """최종 리뷰 #3 — 이름 키가 혼입으로 바뀐 상속 매핑은 재매핑 없이 경고만."""

    def test_mixed_legacy_ids_only_from_multi_id_keys(self):
        ids = {"11590_대림": {"11590-57", "11590-85"}, "11590_현대": {"11590-10"}}
        self.assertEqual(mixed_legacy_ids(ids), ["11590-57", "11590-85"])

    def test_warns_inherited_keys_under_mixed_legacy_without_writing(self):
        conn, logger = MagicMock(), MagicMock()
        with patch.object(
            trade_key_mapping, "query_all", return_value=[{"apt_seq": "11590-57"}]
        ) as q:
            trade_key_mapping._warn_frozen_inherits(
                conn, logger, {"11590_대림": {"11590-57", "11590-85"}}
            )
        sql, params = q.call_args[0][1], q.call_args[0][2]
        self.assertIn("SELECT", sql)
        self.assertEqual(params, [["11590-57", "11590-85"], "api_inherit_legacy"])
        logger.warning.assert_called_once()
        self.assertIn("11590-57", logger.warning.call_args[0][0])
        conn.cursor.assert_not_called()

    def test_no_query_when_nothing_mixed(self):
        with patch.object(trade_key_mapping, "query_all") as q:
            trade_key_mapping._warn_frozen_inherits(
                MagicMock(), MagicMock(), {"11590_현대": {"11590-10"}}
            )
        q.assert_not_called()


class MappingInputsByKeyTest(unittest.TestCase):
    """Fix A — 주소·법정동 판정은 키의 모든 행으로 한다 (대표 행 하나가 아니다)."""

    MAJEON_11300 = "2826011300010030001"  # 마전동아 (apartments 에 있음)
    MAJEON_10300 = "2826010300010030001"  # 개편 전 법정동 — apartments 에 없음

    @staticmethod
    def row(key, apt_nm, umd_cd, n=1, bonbun="1003", bubun="0001"):
        return {
            "apt_seq": key,
            "sgg_cd": "28260",
            "apt_nm": apt_nm,
            "umd_cd": umd_cd,
            "land_cd": "1",
            "bonbun": bonbun if umd_cd else None,
            "bubun": bubun if umd_cd else None,
            "n": n,
        }

    def summarize(self, rows, existing, cands_by_bjd=None):
        return mapping_inputs_by_key(rows, existing, cands_by_bjd or {}, {})

    def test_stale_umd_row_does_not_hide_existing_address(self):
        rows = [
            self.row("28260-138", "동아", "10300", n=4),
            self.row("28260-138", "동아", "11300", n=6),
            self.row("28260-138", "동아", None, n=865),  # 전월세 — 주소 없음
        ]
        inp_ = self.summarize(rows, {self.MAJEON_11300})["28260-138"][0]
        self.assertEqual(inp_.address_pnu, self.MAJEON_11300)
        self.assertEqual(decide_mapping(inp_), (self.MAJEON_11300, "api_address_pnu"))

    def test_two_existing_addresses_fall_through_to_name(self):
        rows = [
            self.row("28260-138", "동아", "10300"),
            self.row("28260-138", "동아", "11300"),
        ]
        inp_ = self.summarize(rows, {self.MAJEON_11300, self.MAJEON_10300})[
            "28260-138"
        ][0]
        self.assertIsNone(inp_.address_pnu)

    def test_no_existing_address_is_none(self):
        inp_ = self.summarize([self.row("K", "동아", "10300")], set())["K"][0]
        self.assertIsNone(inp_.address_pnu)

    def test_name_candidates_union_over_all_bjd_codes(self):
        rows = [self.row("K", "동아", "10300"), self.row("K", "동아", "11300")]
        cands = {
            "2826010300": [("P1", "동아")],
            "2826011300": [("P2", "현대")],
            "2826099999": [("P3", "무관")],
        }
        inp_ = self.summarize(rows, set(), cands)["K"][0]
        self.assertEqual(sorted(inp_.name_candidates), [("P1", "동아"), ("P2", "현대")])

    def test_rent_only_key_has_no_candidates(self):
        inp_ = self.summarize([self.row("K", "동아", None, n=5)], set())["K"][0]
        self.assertEqual((inp_.address_pnu, inp_.name_candidates), (None, ()))

    def test_apt_nm_is_most_frequent_and_sgg_is_returned(self):
        rows = [
            self.row("K", "마전동아", "11300", n=2),
            self.row("K", "동아", "11300", n=5),
            self.row("K", "동아", None, n=1),
        ]
        inp_, sgg_cd = self.summarize(rows, set())["K"]
        self.assertEqual((inp_.apt_nm, sgg_cd), ("동아", "28260"))

    def test_legacy_pnus_pass_through(self):
        got = mapping_inputs_by_key(
            [self.row("K", "동아", None)], set(), {}, {"K": {DAEBANG}}
        )
        self.assertEqual(got["K"][0].legacy_pnus, frozenset({DAEBANG}))


class MostFrequentNameTest(unittest.TestCase):
    def test_weighted_count_wins(self):
        self.assertEqual(most_frequent_value({"동아": 3, "마전동아": 2}), "동아")

    def test_tie_is_lexicographically_first(self):
        self.assertEqual(most_frequent_value({"마전동아": 2, "동아": 2}), "동아")

    def test_empty_is_blank(self):
        self.assertEqual(most_frequent_value({}), "")


if __name__ == "__main__":
    unittest.main()
