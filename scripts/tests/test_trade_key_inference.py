"""과거 거래 → 국토부 고유번호 추론 규칙 (설계 4-3) — 순수 함수, CI 대상."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.trade.trade_key_inference import (
    Inference,
    KnownRow,
    TargetRow,
    infer_keys,
)

L = "11590_대림아파트"
DAEBANG, SANGDO = "11590-57", "11590-85"

# 혼입 키: 대방(1993, 59.84·84.92) + 상도(1995, 66.59·84.89)
MIXED_KNOWN = [
    KnownRow(L, DAEBANG, 1993, 84.92),
    KnownRow(L, DAEBANG, 1993, 59.84),
    KnownRow(L, SANGDO, 1995, 84.89),
    KnownRow(L, SANGDO, 1995, 66.59),
]


class TradeInferenceTest(unittest.TestCase):
    def test_single_id_key_with_matching_year(self):
        known = [KnownRow("K", "1-1", 2005, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", 2005, 59.0)], use_build_year=True)
        self.assertEqual(out, {1: Inference("1-1", "infer_single")})

    def test_single_id_key_with_other_year_is_left_alone(self):
        known = [KnownRow("K", "1-1", 2005, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", 1980, 84.0)], use_build_year=True)
        self.assertEqual(out, {})

    def test_mixed_key_resolved_by_year(self):
        targets = [TargetRow(1, L, 1993, 114.0), TargetRow(2, L, 1995, 66.59)]
        out = infer_keys(MIXED_KNOWN, targets, use_build_year=True)
        self.assertEqual(out[1], Inference(DAEBANG, "infer_year"))
        self.assertEqual(out[2], Inference(SANGDO, "infer_year"))

    def test_mixed_key_same_year_resolved_by_area(self):
        known = [KnownRow("M", "A", 2000, 59.0), KnownRow("M", "B", 2000, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.0)], use_build_year=True)
        self.assertEqual(out, {1: Inference("B", "infer_year_area")})

    def test_mixed_key_ambiguous_is_left_alone(self):
        known = [KnownRow("M", "A", 2000, 84.0), KnownRow("M", "B", 2000, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.0)], use_build_year=True)
        self.assertEqual(out, {})

    def test_key_never_seen_with_id_is_left_alone(self):
        out = infer_keys(
            MIXED_KNOWN, [TargetRow(1, "other", 1993, 84.92)], use_build_year=True
        )
        self.assertEqual(out, {})

    def test_area_noise_is_rounded(self):
        # Review Focus 2 — 84.9234 와 84.92 는 같은 서명
        known = [KnownRow("M", "A", 2000, 84.9234), KnownRow("M", "B", 2000, 59.0)]
        out = infer_keys(known, [TargetRow(1, "M", 2000, 84.92)], use_build_year=True)
        self.assertEqual(out, {1: Inference("A", "infer_year_area")})


class RentInferenceTest(unittest.TestCase):
    def test_single_id_key_seen_area(self):
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, 84.0)], use_build_year=False)
        self.assertEqual(out, {1: Inference("1-1", "infer_single")})

    def test_single_id_key_unseen_area_is_left_alone(self):
        # Review Focus 5 — 관측 안 된 면적은 추측하지 않는다
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, 135.0)], use_build_year=False)
        self.assertEqual(out, {})

    def test_mixed_key_resolved_by_area(self):
        out = infer_keys(
            MIXED_KNOWN, [TargetRow(1, L, None, 66.59)], use_build_year=False
        )
        self.assertEqual(out, {1: Inference(SANGDO, "infer_area")})

    def test_mixed_key_shared_area_is_left_alone(self):
        known = [KnownRow("M", "A", None, 84.0), KnownRow("M", "B", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "M", None, 84.0)], use_build_year=False)
        self.assertEqual(out, {})

    def test_none_area_target_is_left_alone(self):
        known = [KnownRow("K", "1-1", None, 84.0)]
        out = infer_keys(known, [TargetRow(1, "K", None, None)], use_build_year=False)
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
