"""새 키(국토부 고유번호) → PNU 매핑 순위 (설계 4-2) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_key_mapping import MappingInput, decide_mapping

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


if __name__ == "__main__":
    unittest.main()
