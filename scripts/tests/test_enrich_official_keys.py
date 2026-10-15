"""고유번호 키는 enrich 의 이름 경로를 타지 않고 주소 PNU 로만 매핑·등록된다 (ADR-015, 최종 리뷰 #1)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade import enrich_apartments as mod
from batch.trade.enrich_apartments import (
    OFFICIAL_KEY_ADDRESS_METHOD,
    official_key_names,
    partition_unmapped,
    plan_official_keys,
)

DAEBANG = "1159010800005010000"  # 대방동 501
SANGDO = "1159010200004110000"  # 상도동 411


def row(apt_seq, official, umd_cd="10800", bonbun="0501", bubun="0000", land_cd="1"):
    return {
        "apt_seq": apt_seq,
        "sgg_cd": "11590",
        "apt_nm": "대림아파트",
        "umd_cd": umd_cd,
        "bonbun": bonbun,
        "bubun": bubun,
        "land_cd": land_cd,
        "umd_nm": "대방동",
        "official_key": official,
    }


class PartitionTest(unittest.TestCase):
    def test_official_keys_never_enter_name_flow(self):
        name_row = row("11590_대림아파트", False)
        official = row("11590-57", True)
        name_rows, official_rows = partition_unmapped([name_row, official])
        self.assertEqual(name_rows, [name_row])
        self.assertEqual(official_rows, [official])


class PlanOfficialKeysTest(unittest.TestCase):
    def test_existing_address_pnu_maps(self):
        plan = plan_official_keys([row("11590-57", True)], {DAEBANG})
        self.assertEqual(plan.map_existing, {"11590-57": DAEBANG})
        self.assertEqual(plan.register, {})

    def test_new_address_pnu_registers_once_for_shared_keys(self):
        plan = plan_official_keys([row("11590-57", True), row("11590-58", True)], set())
        self.assertEqual(plan.register, {DAEBANG: ["11590-57", "11590-58"]})

    def test_mountain_lot_uses_land_cd(self):
        plan = plan_official_keys([row("11590-57", True, land_cd="2")], set())
        self.assertEqual(list(plan.register), ["1159010800105010000"])

    def test_no_address_stays_unresolved_without_name_fallback(self):
        # 전월세만 있는 키 등 주소 필드가 없으면 이름으로 찾지 않고 미매핑으로 남긴다
        plan = plan_official_keys(
            [row("11590-99", True, umd_cd=None, bonbun=None, bubun=None)], {SANGDO}
        )
        self.assertEqual(plan.unresolved, ["11590-99"])
        self.assertEqual((plan.map_existing, plan.register), ({}, {}))

    # Fix A — 키의 모든 주소 행으로 판정한다 (대표 행 하나가 아니다)
    def test_stale_umd_row_maps_to_the_one_existing_address(self):
        plan = plan_official_keys(
            [row("11590-57", True, umd_cd="10200"), row("11590-57", True)], {DAEBANG}
        )
        self.assertEqual(plan.map_existing, {"11590-57": DAEBANG})
        self.assertEqual((plan.register, plan.ambiguous), ({}, []))

    def test_several_new_addresses_are_ambiguous_not_registered(self):
        plan = plan_official_keys(
            [row("11590-57", True, umd_cd="10200"), row("11590-57", True)], set()
        )
        self.assertEqual(plan.ambiguous, ["11590-57"])
        self.assertEqual((plan.map_existing, plan.register), ({}, {}))

    def test_several_existing_addresses_are_ambiguous(self):
        plan = plan_official_keys(
            [row("11590-57", True, umd_cd="10200"), row("11590-57", True)],
            {DAEBANG, "1159010200005010000"},
        )
        self.assertEqual(plan.ambiguous, ["11590-57"])
        self.assertEqual(plan.map_existing, {})

    def test_address_row_kept_for_registration(self):
        rent_like = row("11590-57", True, umd_cd=None, bonbun=None, bubun=None)
        addr_row = row("11590-57", True)
        plan = plan_official_keys([rent_like, addr_row], set())
        self.assertEqual(plan.register, {DAEBANG: ["11590-57"]})
        self.assertIs(plan.address_rows[DAEBANG], addr_row)
        self.assertEqual(plan.unresolved, [])


class EnrichOfficialKeysTest(unittest.TestCase):
    def test_uses_address_only_and_never_name_search_or_trade_fallback(self):
        conn = MagicMock()
        cur = conn.cursor.return_value
        resolved = {
            "apt_seq": "11590-58",
            "sgg_cd": "11590",
            "apt_nm": "대림아파트",
            "pnu": SANGDO,
            "lat": None,
            "lng": None,
            "new_plat": None,
            "plat": None,
            "bjd_code": SANGDO[:10],
            "bld_params": None,
            "bld_info": {},
        }
        rows = [
            row("11590-57", True),  # 기존 주소 PNU
            row("11590-58", True, umd_cd="10200", bonbun="0411"),  # 신규 등록
            row("11590-99", True, umd_cd=None, bonbun=None, bubun=None),  # 주소 없음
        ]
        with (
            patch.object(mod, "_resolve_one") as name_search,
            patch.object(
                mod, "_resolve_official_one", return_value=resolved
            ) as by_addr,
            patch.object(mod, "_enrich_kapt_targeted", return_value=0) as kapt_by_name,
        ):
            mapped, registered = mod._enrich_official_keys(
                conn, MagicMock(), rows, {DAEBANG}, {}, {}
            )
        name_search.assert_not_called()
        # 동명 이웃 오매칭 방지: 고유번호 신규 등록 단지에는 이름 기반 K-APT 매칭을 하지 않는다
        kapt_by_name.assert_not_called()
        by_addr.assert_called_once()
        self.assertEqual(by_addr.call_args[0][1], SANGDO)
        self.assertEqual((mapped, registered), (2, {SANGDO: "대림아파트"}))
        sqls = [c[0][0] for c in cur.execute.call_args_list]
        params = [c[0][1] for c in cur.execute.call_args_list]
        self.assertFalse(any("TRADE_" in str(p) for p in params))
        mapping_params = [
            p
            for s, p in zip(sqls, params)
            if s.startswith("INSERT INTO trade_apt_mapping")
        ]
        self.assertEqual(
            sorted((p[0], p[1], p[4]) for p in mapping_params),
            [
                ("11590-57", DAEBANG, OFFICIAL_KEY_ADDRESS_METHOD),
                ("11590-58", SANGDO, OFFICIAL_KEY_ADDRESS_METHOD),
            ],
        )


class OfficialKeyNamesTest(unittest.TestCase):
    """Fix round 1 #4 — 매핑 행 단지명은 최빈값 (trade_key_mapping 과 같은 규칙)."""

    def test_most_frequent_over_counted_rows_ignoring_representative(self):
        rep = dict(row("K", True), apt_nm="동아")  # DISTINCT ON 대표 행 — n 없음
        rows = [
            rep,
            dict(row("K", True), apt_nm="마전동아", n=7),
            dict(row("K", True), apt_nm="동아", n=3),
        ]
        self.assertEqual(official_key_names(rows), {"K": "마전동아"})

    def test_tie_is_lexicographic_and_rep_only_key_uses_rep_name(self):
        rows = [
            dict(row("K", True), apt_nm="마전동아", n=2),
            dict(row("K", True), apt_nm="동아", n=2),
            dict(row("R", True, umd_cd=None), apt_nm="전월세만"),
        ]
        self.assertEqual(official_key_names(rows), {"K": "동아", "R": "전월세만"})

    def test_mapping_row_uses_most_frequent_name(self):
        conn = MagicMock()
        cur = conn.cursor.return_value
        rows = [
            dict(row("11590-57", True), apt_nm="대림"),
            dict(row("11590-57", True), apt_nm="대방대림", n=5),
            dict(row("11590-57", True), apt_nm="대림", n=1),
        ]
        mod._enrich_official_keys(conn, MagicMock(), rows, {DAEBANG}, {}, {})
        ins = [
            c[0][1]
            for c in cur.execute.call_args_list
            if c[0][0].startswith("INSERT INTO trade_apt_mapping")
        ]
        self.assertEqual([(p[0], p[2]) for p in ins], [("11590-57", "대방대림")])


class EnrichOfficialKeysGateTest(unittest.TestCase):
    """F2 — 기존 단지로 붙인 고유번호 키 매핑만 물리 게이트를 거친다(신규 등록 단지는 제외)."""

    def test_existing_pnu_mapping_gated_and_rejection_not_counted(self):
        conn = MagicMock()
        resolved = {
            "apt_seq": "11590-58",
            "sgg_cd": "11590",
            "apt_nm": "대림아파트",
            "pnu": SANGDO,
            "lat": None,
            "lng": None,
            "new_plat": None,
            "plat": None,
            "bjd_code": SANGDO[:10],
            "bld_params": None,
            "bld_info": {},
        }
        rows = [
            row("11590-57", True),
            row("11590-58", True, umd_cd="10200", bonbun="0411"),
        ]
        gated = {}

        def fake_gate(c, lg, keys, source):
            gated["keys"] = keys
            return [{"apt_seq": "11590-57"}]

        with (
            patch.object(mod, "_resolve_official_one", return_value=resolved),
            patch.object(mod, "reject_unverified_mappings", side_effect=fake_gate),
        ):
            mapped, registered = mod._enrich_official_keys(
                conn, MagicMock(), rows, {DAEBANG}, {}, {}
            )
        self.assertEqual(gated["keys"], ["11590-57"])
        self.assertEqual((mapped, registered), (1, {SANGDO: "대림아파트"}))
        conn.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
