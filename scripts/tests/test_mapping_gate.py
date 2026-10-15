"""F2 — 새 비상속 매핑의 물리 게이트 (batch.trade.mapping_gate, audit_mappings.violation_of).

판정은 audit_mappings 와 같은 함수(check_mapping + mismatch_confirmed)다. 사례는 2026-10-14
로컬 표본 검증에서 나온 3순위 이름 매칭 오답(reports/rekey/sample_verification.md)이다.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade import mapping_gate
from batch.trade.audit_mappings import violation_of
from batch.trade.mapping_gate import gate_keys, reject_unverified_mappings


def stats(
    key,
    apt_nm,
    bld_nm,
    *,
    by,
    deal_year,
    areas,
    apt_areas,
    use_apr,
    method,
    floor=5,
    apt_floor=15,
    pnu="P",
):
    """deal_stats 집계 행 하나 (areas 는 (면적, 건수))."""
    return {
        "apt_seq": key,
        "apt_nm": apt_nm,
        "pnu": pnu,
        "bld_nm": bld_nm,
        "match_method": method,
        "trades": sum(n for _, n in areas),
        "rents": 0,
        "max_floor": floor,
        "min_deal_year": deal_year,
        "median_build_year": by,
        "areas": [[a, n] for a, n in areas],
        "jibun_pnus": None,
        "jibun_owner_pnus": None,
        "apt_max_floor": apt_floor,
        "use_apr_day": use_apr,
        "apt_areas": apt_areas,
    }


# 44150-25 (신관동 268-3, 1988, 39.7/51.0/59.1㎡) → 숫자 지운 정규화로 '주공3'(1990, 46.7~47.0㎡)
SINGWAN_TO_JUGONG3 = stats(
    "44150-25",
    "주공2",
    "주공3",
    by=1988,
    deal_year=2006,
    areas=[(39.72, 12), (51.02, 10), (59.12, 8)],
    apt_areas=[46.7, 46.9, 47.0],
    use_apr="19900601",
    method="api_name_exact",
)
# 50110-3508 '엘리시아'(2013, 24~30㎡ 원룸) → 포함 매칭 '연동엘리시아'(2011, 74~85㎡)
ELYSIA = stats(
    "50110-3508",
    "엘리시아",
    "연동엘리시아",
    by=2013,
    deal_year=2014,
    areas=[(24.4, 3), (30.5, 3)],
    apt_areas=[74.9, 84.9],
    use_apr="20110301",
    method="api_name_contains",
)
# 같은 단지(준공·주택형 일치) — 통과해야 한다
MATCHING = stats(
    "44150-13",
    "주공2",
    "옥룡주공2단지",
    by=1994,
    deal_year=2006,
    areas=[(49.94, 60), (59.4, 52)],
    apt_areas=[49.94, 59.4],
    use_apr="19940801",
    method="api_address_pnu",
)
# 준공연도 차이 + 면적 절반 미달(비강) — 신호 2개로 확정
YEAR_AND_AREA = stats(
    "30170-1105",
    "시티팰리스",
    "시티팰리스 8차",
    by=2014,
    deal_year=2014,
    areas=[(59.9, 4), (84.9, 3)],
    apt_areas=[84.9, 101.0],
    use_apr="20190101",
    method="api_name_contains",
)


class ViolationOfTest(unittest.TestCase):
    def test_digit_stripped_exact_name_to_other_complex_is_rejected(self):
        v = violation_of(SINGWAN_TO_JUGONG3)
        self.assertIsNotNone(v)
        self.assertEqual(v["apt_seq"], "44150-25")

    def test_contains_match_with_mismatched_year_and_areas_is_rejected(self):
        self.assertIsNotNone(violation_of(ELYSIA))

    def test_build_year_and_area_together_reject(self):
        v = violation_of(YEAR_AND_AREA)
        self.assertIsNotNone(v)
        self.assertGreaterEqual(len(v["reasons"]), 2)

    def test_matching_complex_passes(self):
        self.assertIsNone(violation_of(MATCHING))


class GateKeysTest(unittest.TestCase):
    def test_inherit_exempt_and_sorted_unique(self):
        inserted = [
            ("K2", "api_name_exact"),
            ("K1", "api_address_pnu"),
            ("K3", "api_inherit_legacy"),
            ("K1", "api_address_pnu"),
        ]
        self.assertEqual(gate_keys(inserted, {"api_inherit_legacy"}), ["K1", "K2"])


class RejectUnverifiedMappingsTest(unittest.TestCase):
    def run_gate(self, rows, keys):
        conn, logger = MagicMock(), MagicMock()
        with patch.object(
            mapping_gate,
            "find_violations",
            return_value=([v for r in rows if (v := violation_of(r))], len(rows)),
        ) as fv:
            out = reject_unverified_mappings(conn, logger, keys, source="test")
        return out, conn, logger, fv

    def test_deletes_only_violating_mappings(self):
        out, conn, logger, fv = self.run_gate(
            [SINGWAN_TO_JUGONG3, ELYSIA, MATCHING],
            ["44150-13", "44150-25", "50110-3508"],
        )
        self.assertEqual(sorted(v["apt_seq"] for v in out), ["44150-25", "50110-3508"])
        sql, params = conn.cursor.return_value.execute.call_args[0]
        self.assertTrue(sql.startswith("DELETE FROM trade_apt_mapping"))
        self.assertEqual(params, [["44150-25", "50110-3508"]])
        logger.warning.assert_called_once()
        self.assertEqual(
            fv.call_args.kwargs["apt_seqs"], ["44150-13", "44150-25", "50110-3508"]
        )

    def test_all_passing_deletes_nothing(self):
        out, conn, logger, _ = self.run_gate([MATCHING], ["44150-13"])
        self.assertEqual(out, [])
        conn.cursor.assert_not_called()
        logger.warning.assert_not_called()

    def test_empty_keys_do_not_query(self):
        with patch.object(mapping_gate, "find_violations") as fv:
            self.assertEqual(
                reject_unverified_mappings(MagicMock(), MagicMock(), [], "t"), []
            )
        fv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
