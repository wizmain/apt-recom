"""update_weights 의 hedonic 신호 추출(방향 가드) 단위 검증.

핵심 가드: dist 계수가 양수(가까울수록 싸다)인데 유의한 subtype (실측 예:
cctv t=+15.2)이 |t| 정규화만으로 최상위 신호가 되는 것을 막는다 — 신호는
beta<0 AND |t|>=임계 에만 부여하고 나머지는 사유와 함께 제외돼야 한다.
"""

import unittest

from batch.ml.update_weights import T_SIGNIFICANT, hedonic_signal


class HedonicSignalTest(unittest.TestCase):
    def test_direction_guard_excludes_positive_beta(self):
        """유의한 양수 계수(방향역전)는 신호에서 제외되고 사유가 남는다."""
        coefficients = {
            "dist_subway": {"beta": -0.05, "t": -15.0},
            "dist_cctv": {"beta": 0.04, "t": 15.2},  # 실측 재현: 유의하지만 역방향
            "dist_mart": {"beta": -0.03, "t": -9.0},
            "cnt1km_subway": {"beta": 0.01, "t": 8.0},  # dist_ 아님 — 무시
        }
        signal, excluded = hedonic_signal(coefficients)
        self.assertNotIn("cctv", signal)
        self.assertIn("방향역전", excluded["cctv"])
        self.assertEqual(set(signal), {"subway", "mart"})

    def test_insignificant_excluded(self):
        """|t| < 임계 subtype 은 부호와 무관하게 제외된다."""
        coefficients = {
            "dist_subway": {"beta": -0.05, "t": -10.0},
            "dist_library": {"beta": -0.01, "t": -1.3},
            "dist_police": {"beta": 0.01, "t": 1.0},
        }
        signal, excluded = hedonic_signal(coefficients)
        self.assertEqual(set(signal), {"subway"})
        self.assertIn("유의X", excluded["library"])
        self.assertIn("유의X", excluded["police"])

    def test_signal_normalized_by_abs_t(self):
        """유효 subtype 의 신호는 |t| 비례로 합 1.0 정규화된다."""
        coefficients = {
            "dist_a": {"beta": -1.0, "t": -30.0},
            "dist_b": {"beta": -1.0, "t": -10.0},
        }
        signal, _ = hedonic_signal(coefficients)
        self.assertAlmostEqual(sum(signal.values()), 1.0)
        self.assertAlmostEqual(signal["a"], 0.75)
        self.assertAlmostEqual(signal["b"], 0.25)

    def test_threshold_boundary(self):
        """|t| == 임계값은 유효 신호로 포함된다 (>= 비교)."""
        coefficients = {"dist_a": {"beta": -0.1, "t": -T_SIGNIFICANT}}
        signal, excluded = hedonic_signal(coefficients)
        self.assertIn("a", signal)
        self.assertEqual(excluded, {})

    def test_empty_when_no_valid_signal(self):
        """유효 subtype 이 없으면 빈 신호 — 호출측은 전부 '유지' 처리한다."""
        coefficients = {"dist_a": {"beta": 0.1, "t": 5.0}}
        signal, excluded = hedonic_signal(coefficients)
        self.assertEqual(signal, {})
        self.assertIn("a", excluded)


if __name__ == "__main__":
    unittest.main()
