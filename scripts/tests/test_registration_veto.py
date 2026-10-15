"""고유번호 키 신규 등록 거부권 — 같은 법정동 같은·포함 이름 단지가 있으면 등록하지 않는다 (리뷰 #2)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.registration_veto import (
    duplicate_candidates,
    names_conflict,
    veto_registrations,
)

ADDR = "1159010800005010000"  # 대방동 501 (등록 예정 주소 PNU)
SAME_DONG = "1159010800006000000"  # 대방동 600 (기존 단지)
OTHER_DONG = "1159010200004110000"  # 상도동 411 (기존 단지)


class NamesConflictTest(unittest.TestCase):
    def test_equal_name_conflicts(self):
        self.assertTrue(names_conflict("대방 대림(아파트)", "대방대림아파트"))

    def test_contains_conflicts(self):
        self.assertTrue(names_conflict("엘리시아", "연동엘리시아"))
        self.assertTrue(names_conflict("연동엘리시아", "엘리시아"))

    def test_short_name_contains_does_not_conflict(self):
        # '현대'(2자)는 아무 단지명에나 포함될 수 있어 포함 규칙에서 뺀다 — 같은 이름만 거부
        self.assertFalse(names_conflict("현대", "현대홈타운"))
        self.assertTrue(names_conflict("현대", "현대"))

    def test_empty_after_normalize_does_not_conflict(self):
        self.assertFalse(names_conflict("101동", "101동"))
        self.assertFalse(names_conflict("", "대림"))


class VetoRegistrationsTest(unittest.TestCase):
    def test_same_dong_equal_name_vetoes(self):
        kept, vetoed = veto_registrations(
            {ADDR: ["K1"]}, {"K1": "대림"}, {ADDR[:10]: [(SAME_DONG, "대림")]}
        )
        self.assertEqual((kept, vetoed), ({}, {"K1": [SAME_DONG]}))

    def test_same_dong_contains_vetoes(self):
        _kept, vetoed = veto_registrations(
            {ADDR: ["K1"]},
            {"K1": "엘리시아"},
            {ADDR[:10]: [(SAME_DONG, "연동엘리시아")]},
        )
        self.assertEqual(vetoed, {"K1": [SAME_DONG]})

    def test_different_dong_does_not_veto(self):
        kept, vetoed = veto_registrations(
            {ADDR: ["K1"]}, {"K1": "대림"}, {OTHER_DONG[:10]: [(OTHER_DONG, "대림")]}
        )
        self.assertEqual((kept, vetoed), ({ADDR: ["K1"]}, {}))

    def test_only_conflicting_key_of_shared_pnu_is_vetoed(self):
        kept, vetoed = veto_registrations(
            {ADDR: ["K1", "K2"]},
            {"K1": "대림", "K2": "신축단지"},
            {ADDR[:10]: [(SAME_DONG, "대림")]},
        )
        self.assertEqual((kept, vetoed), ({ADDR: ["K2"]}, {"K1": [SAME_DONG]}))

    def test_candidates_sorted_unique(self):
        apts = [
            (SAME_DONG, "대림"),
            (SAME_DONG, "대림아파트"),
            ("1159010800000010000", "대림"),
        ]
        self.assertEqual(
            duplicate_candidates("대림", apts), ["1159010800000010000", SAME_DONG]
        )


if __name__ == "__main__":
    unittest.main()
