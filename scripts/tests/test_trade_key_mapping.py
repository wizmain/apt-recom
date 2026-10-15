"""새 키(국토부 고유번호) → PNU 매핑 순위 (설계 4-2) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from unittest.mock import MagicMock, patch

from batch.trade import trade_key_mapping
from batch.trade.trade_key_mapping import (
    MappingInput,
    decide_mapping,
    inheritable_pnus_by_key,
    mapping_inputs_by_key,
    mixed_legacy_ids,
    most_frequent_value,
    warn_weak_address_choices,
)

DAEBANG = "1159010800005010000"
SANGDO = "1159010200004110000"


def inp(legacy=(), addr=None, apt_nm="대림아파트"):
    return MappingInput(apt_nm, frozenset(legacy), addr)


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

    def test_rank3_nothing_is_unmapped(self):
        self.assertIsNone(decide_mapping(inp()))

    def test_mapping_input_has_no_name_candidates(self):
        # Option A (2026-10-15) — 법정동 이름 매칭 제거: 판정 입력에 이름 후보가 없다
        self.assertEqual(MappingInput._fields, ("apt_nm", "legacy_pnus", "address_pnu"))


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
    """Fix A — 주소 판정은 키의 모든 행으로 한다 (대표 행 하나가 아니다)."""

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

    def summarize(self, rows, existing):
        return mapping_inputs_by_key(rows, existing, {})

    def test_stale_umd_row_does_not_hide_existing_address(self):
        rows = [
            self.row("28260-138", "동아", "10300", n=4),
            self.row("28260-138", "동아", "11300", n=6),
            self.row("28260-138", "동아", None, n=865),  # 전월세 — 주소 없음
        ]
        inp_ = self.summarize(rows, {self.MAJEON_11300})["28260-138"][0]
        self.assertEqual(inp_.address_pnu, self.MAJEON_11300)
        self.assertEqual(decide_mapping(inp_), (self.MAJEON_11300, "api_address_pnu"))

    def test_two_existing_addresses_is_none(self):
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

    def test_rent_only_key_has_no_address(self):
        inp_ = self.summarize([self.row("K", "동아", None, n=5)], set())["K"][0]
        self.assertIsNone(inp_.address_pnu)

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
            [self.row("K", "동아", None)], set(), {"K": {DAEBANG}}
        )
        self.assertEqual(got["K"][0].legacy_pnus, frozenset({DAEBANG}))


class MostFrequentNameTest(unittest.TestCase):
    def test_weighted_count_wins(self):
        self.assertEqual(most_frequent_value({"동아": 3, "마전동아": 2}), "동아")

    def test_tie_is_lexicographically_first(self):
        self.assertEqual(most_frequent_value({"마전동아": 2, "동아": 2}), "동아")

    def test_empty_is_blank(self):
        self.assertEqual(most_frequent_value({}), "")


class WarnWeakAddressChoicesTest(unittest.TestCase):
    def test_logs_only_weak_choices(self):
        logger = MagicMock()
        a, a_old = "2826011300010030001", "2826010300010030001"
        msgs = warn_weak_address_choices(
            logger,
            {"K1": {a: 6, a_old: 4}, "K2": {a: 1, a_old: 3}},
            {"K1": a, "K2": a},
        )
        self.assertEqual(len(msgs), 1)
        self.assertIn("K2", msgs[0])
        logger.warning.assert_called_once()

    def test_silent_when_all_strong(self):
        logger = MagicMock()
        self.assertEqual(
            warn_weak_address_choices(logger, {"K": {DAEBANG: 3}}, {"K": DAEBANG}), []
        )
        logger.warning.assert_not_called()


class InheritablePnusTest(unittest.TestCase):
    """F1 — apartments 에 실존하는 PNU 로 매핑된 이름 키에서만 상속한다."""

    LKS: ClassVar = {"48123-583": {"48123_에일린의뜰"}}
    IDS: ClassVar = {"48123_에일린의뜰": {"48123-583"}}

    def test_dangling_legacy_pnu_is_not_inherited(self):
        legacy = {"48123_에일린의뜰": "4812313700001100000"}  # apartments 에 없음
        got = inheritable_pnus_by_key(self.LKS, self.IDS, legacy, set())
        self.assertEqual(got, {"48123-583": set()})
        # 상속 후보가 없으니 2순위(주소)로 넘어간다(여기선 주소도 없어 미매핑)
        self.assertIsNone(decide_mapping(inp(legacy=got["48123-583"])))

    def test_existing_legacy_pnu_is_inherited(self):
        legacy = {"48123_에일린의뜰": "P_REAL"}
        got = inheritable_pnus_by_key(self.LKS, self.IDS, legacy, {"P_REAL"})
        self.assertEqual(
            decide_mapping(inp(legacy=got["48123-583"])),
            ("P_REAL", "api_inherit_legacy"),
        )

    def test_dangling_variant_is_ignored_like_an_unmapped_name_key(self):
        lks = {"K": {"L1", "L2"}}
        ids = {"L1": {"K"}, "L2": {"K"}}
        got = inheritable_pnus_by_key(lks, ids, {"L1": "P1", "L2": "GONE"}, {"P1"})
        self.assertEqual(got, {"K": {"P1"}})

    def test_mixed_legacy_key_still_not_inherited(self):
        got = inheritable_pnus_by_key(
            {"K": {"L"}}, {"L": {"K", "K2"}}, {"L": "P1"}, {"P1"}
        )
        self.assertEqual(got, {"K": set()})


class MapApiKeysGateTest(unittest.TestCase):
    """F2 — map_api_keys 는 이번에 넣은 비상속 매핑만 게이트에 넘기고, 거부분은 미매핑으로 센다."""

    def test_only_inserted_non_inherit_keys_are_gated(self):
        rows = [
            {
                "apt_seq": "K_ADDR",
                "sgg_cd": "11590",
                "apt_nm": "대림",
                "umd_cd": "10800",
                "land_cd": "1",
                "bonbun": "0501",
                "bubun": "0000",
                "n": 3,
            },
            {
                "apt_seq": "K_INH",
                "sgg_cd": "11590",
                "apt_nm": "현대",
                "umd_cd": None,
                "land_cd": None,
                "bonbun": None,
                "bubun": None,
                "n": 2,
            },
        ]

        def fake_query_all(conn, sql, params=None):
            if "FROM trade_history t" in sql:
                return rows
            if "SELECT DISTINCT apt_seq, legacy_apt_seq" in sql:
                return [{"apt_seq": "K_INH", "legacy_apt_seq": "11590_현대"}]
            if "ARRAY_AGG(DISTINCT api_apt_seq)" in sql:
                return [{"lk": "11590_현대", "ids": ["K_INH"]}]
            if "LEFT JOIN apartments a" in sql:
                return [{"apt_seq": "11590_현대", "pnu": "P_H", "pnu_exists": True}]
            if "SELECT pnu FROM apartments" in sql:
                return [{"pnu": DAEBANG}]
            return []

        gated = {}

        def fake_gate(conn, logger, keys, source):
            gated["keys"] = keys
            return [{"apt_seq": "K_ADDR"}]

        with (
            patch.object(trade_key_mapping, "query_all", side_effect=fake_query_all),
            patch.object(
                trade_key_mapping.psycopg2.extras,
                "execute_values",
                return_value=[
                    ("K_ADDR", "api_address_pnu"),
                    ("K_INH", "api_inherit_legacy"),
                ],
            ),
            patch.object(
                trade_key_mapping, "reject_unverified_mappings", side_effect=fake_gate
            ),
        ):
            mapped = trade_key_mapping.map_api_keys(MagicMock(), MagicMock())
        self.assertEqual(gated["keys"], ["K_ADDR"])
        self.assertEqual(mapped, 1)


class NoNameMappingTest(unittest.TestCase):
    """Option A (2026-10-15) — 같은 법정동에 이름이 같은 단지가 하나뿐이어도, 상속·주소 근거가
    없으면 매핑하지 않는다(로컬 검증에서 이름 매칭 28건 중 절반가량 오매핑)."""

    def test_unique_same_dong_name_without_inherit_or_address_stays_unmapped(self):
        # 신관동 '주공2' — 주소 PNU 는 apartments 에 없고, 같은 법정동엔 '주공2' 단지가 하나 있다
        rows = [
            {
                "apt_seq": "44150-25",
                "sgg_cd": "44150",
                "apt_nm": "주공2",
                "umd_cd": "10300",
                "land_cd": "1",
                "bonbun": "0268",
                "bubun": "0003",
                "n": 30,
            }
        ]
        sqls = []

        def fake_query_all(conn, sql, params=None):
            sqls.append(sql)
            if "FROM trade_history t" in sql:
                return rows
            if "bjd_code" in sql:  # 이름 후보 조회가 되살아나면 유일 동명 후보를 준다
                return [
                    {
                        "pnu": "4415010300102680000",
                        "nm": "주공2",
                        "bjd_code": "4415010300",
                    }
                ]
            return []

        logger = MagicMock()
        with (
            patch.object(trade_key_mapping, "query_all", side_effect=fake_query_all),
            patch.object(trade_key_mapping.psycopg2.extras, "execute_values") as ins,
            patch.object(
                trade_key_mapping, "reject_unverified_mappings", return_value=[]
            ),
        ):
            mapped = trade_key_mapping.map_api_keys(MagicMock(), logger)
        self.assertEqual(mapped, 0)
        ins.assert_not_called()
        self.assertFalse(any("bjd_code" in s for s in sqls))
        self.assertIn("44150-25", logger.warning.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
