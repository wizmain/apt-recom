"""데일리 로테이션 리졸버 테스트 — 결정론·순환·명령 형태 + 실 yaml 스모크."""

import unittest
from datetime import date


def make_cfg():
    """작은 fixture cfg (yaml 편집과 무관하게 로직 검증)."""
    return {
        "timezone": "Asia/Seoul",
        "anchor_date": "2026-07-27",  # 월요일
        "weekday_format": {
            "mon": "trade_top",
            "tue": "value",
            "wed": "compare",
            "thu": "lifestyle",
            "fri": "budget_choice",
            "sat": "value",
            "sun": "lifestyle",
        },
        "series": {
            "trade_top": {"days": 7, "min_hhld": 100},
            "value": {
                "nudge": "cost",
                "min_smallest_area": 59,
                "regions": [
                    {"keyword": "강남구", "slug": "gangnam"},
                    {"keyword": "서초구", "slug": "seocho"},
                ],
            },
            "compare": {
                "nudge": "newlywed",
                "min_hhld": 100,
                "pairs": ["11710,11740", "11680,11650"],
            },
            "lifestyle": {
                "profiles": ["pet", "newlywed"],
                "regions": ["11680", "11650"],
            },
            "budget_choice": {
                "items": [
                    {
                        "regions": "11350,41463",
                        "budget": 60000,
                        "area_a": 59,
                        "area_b": 59,
                    },
                ]
            },
        },
    }


class TestResolve(unittest.TestCase):
    def test_weekday_maps_to_series(self):
        from scripts.insta_cards.rotation import resolve

        cfg = make_cfg()
        self.assertEqual(resolve(cfg, date(2026, 7, 27))["series"], "trade_top")  # 월
        self.assertEqual(resolve(cfg, date(2026, 7, 28))["series"], "value")  # 화
        self.assertEqual(resolve(cfg, date(2026, 8, 1))["series"], "value")  # 토

    def test_deterministic(self):
        from scripts.insta_cards.rotation import resolve

        cfg = make_cfg()
        a = resolve(cfg, date(2026, 7, 28))
        b = resolve(cfg, date(2026, 7, 28))
        self.assertEqual(a, b)

    def test_occurrence_cycles_per_series(self):
        from scripts.insta_cards.rotation import resolve

        cfg = make_cfg()
        # value 는 화·토 등장. 첫 value(화 7/28)=occ0, 두번째 value(토 8/1)=occ1.
        tue = resolve(cfg, date(2026, 7, 28))
        sat = resolve(cfg, date(2026, 8, 1))
        self.assertEqual(tue["occurrence"], 0)
        self.assertEqual(sat["occurrence"], 1)
        self.assertEqual(tue["params"]["keyword"], "강남구")
        self.assertEqual(sat["params"]["keyword"], "서초구")  # 큐 1칸 전진
        # 다음 주 화(8/4) = occ2 → len(regions)=2 로 wrap → 다시 강남구
        self.assertEqual(resolve(cfg, date(2026, 8, 4))["params"]["keyword"], "강남구")

    def test_slug_formats(self):
        from scripts.insta_cards.rotation import resolve

        cfg = make_cfg()
        self.assertEqual(resolve(cfg, date(2026, 7, 27))["slug"], "trade-top-20260727")
        self.assertEqual(
            resolve(cfg, date(2026, 7, 28))["slug"], "value-gangnam-20260728"
        )
        self.assertEqual(
            resolve(cfg, date(2026, 7, 29))["slug"], "compare-11710-vs-11740-20260729"
        )

    def test_command_shape(self):
        from scripts.insta_cards.rotation import resolve

        cfg = make_cfg()
        cmd = resolve(cfg, date(2026, 7, 31))["command"]  # 금 budget_choice
        self.assertIn("--series budget-choice", cmd)
        self.assertIn("--regions 11350,41463", cmd)
        self.assertIn("--budget 60000", cmd)
        self.assertIn("--area-a 59", cmd)

    def test_trade_top_carries_min_hhld(self):
        """세대수 하한이 명령에 실려야 한다 (부티크 빌라 혼입 방지)."""
        from scripts.insta_cards.rotation import resolve

        a = resolve(make_cfg(), date(2026, 7, 27))  # 월 trade_top
        self.assertEqual(a["params"]["min_hhld"], 100)
        self.assertIn("--min-hhld 100", a["command"])

    def test_compare_carries_min_hhld(self):
        """세대수 하한이 params·명령 양쪽에 실려야 한다 (빌라급 단지 대표 방지)."""
        from scripts.insta_cards.rotation import resolve

        a = resolve(make_cfg(), date(2026, 7, 29))  # 수 compare
        self.assertEqual(a["params"]["min_hhld"], 100)
        self.assertIn("--min-hhld 100", a["command"])

    def test_value_carries_min_smallest_area(self):
        """면적 하한이 params·명령 양쪽에 실려야 한다 (소형단지 혼입 방지)."""
        from scripts.insta_cards.rotation import resolve

        a = resolve(make_cfg(), date(2026, 7, 28))  # 화 value
        self.assertEqual(a["params"]["min_smallest_area"], 59)
        self.assertIn("--min-smallest-area 59", a["command"])

    def test_before_anchor_raises(self):
        from scripts.insta_cards.rotation import resolve

        with self.assertRaises(ValueError):
            resolve(make_cfg(), date(2026, 7, 1))


class TestRealYaml(unittest.TestCase):
    def test_loads_and_resolves_14_days_valid_slugs(self):
        from datetime import timedelta

        from scripts.insta_cards.publication import SLUG_PATTERN
        from scripts.insta_cards.rotation import load_rotation, resolve

        cfg = load_rotation()
        start = date.fromisoformat(cfg["anchor_date"])
        for i in range(14):
            a = resolve(cfg, start + timedelta(days=i))
            self.assertTrue(SLUG_PATTERN.match(a["slug"]), f"invalid slug: {a['slug']}")
            self.assertTrue(a["command"].startswith("python -m scripts.insta_cards"))


if __name__ == "__main__":
    unittest.main()
