"""insta_cards 패키지 테스트 — 클래스 1개 = 모듈 1개."""

import unittest


class TestTheme(unittest.TestCase):
    def test_format_eok(self):
        from scripts.insta_cards import theme

        self.assertEqual(theme.format_eok(43500), "4억 3,500만원")
        self.assertEqual(theme.format_eok(70000), "7억")
        self.assertEqual(theme.format_eok(9500), "9,500만원")

    def test_format_price_per_m2(self):
        from scripts.insta_cards import theme

        self.assertEqual(theme.format_price_per_m2(12345678.0), "1,235만원/㎡")

    def test_truncate_text_returns_ellipsis_when_too_wide(self):
        from scripts.insta_cards import theme

        draw = theme.measuring_draw()
        font = theme.get_font("semibold", 34)
        long_name = "아주아주아주아주긴한글단지이름테스트" * 3
        result = theme.truncate_text(draw, long_name, font, 300)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(draw.textlength(result, font=font), 300)

    def test_build_base_canvas_dimensions(self):
        from scripts.insta_cards import theme

        canvas = theme.build_base_canvas("시리즈 라벨", ["타이틀 1행", "타이틀 2행"])
        self.assertEqual(canvas.image.size, (1080, 1080))
        self.assertGreater(canvas.content_bottom, canvas.content_top)


class TestTextRules(unittest.TestCase):
    def test_wrap_text_splits_long_korean(self):
        from scripts.insta_cards import textrules, theme

        font = theme.get_font("regular", 28)
        lines = textrules.wrap_text("가나다라마바사 아자차카타파하 " * 10, font, 400)
        draw = theme.measuring_draw()
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(draw.textlength(line, font=font), 400)

    def test_check_field_passes_short_hook(self):
        from scripts.insta_cards import textrules

        self.assertEqual(textrules.check_field("hook", "7억으로 어디까지?"), [])

    def test_check_field_rejects_overflow_hook(self):
        from scripts.insta_cards import textrules

        errors = textrules.check_field("hook", "아주 긴 훅 문장 " * 30)
        self.assertEqual(len(errors), 1)
        self.assertIn("hook", errors[0])

    def test_check_field_rejects_empty(self):
        from scripts.insta_cards import textrules

        self.assertEqual(len(textrules.check_field("summary", "  ")), 1)

    def test_check_field_unknown_field_raises(self):
        from scripts.insta_cards import textrules

        with self.assertRaises(KeyError):
            textrules.check_field("no_such_field", "text")

    def test_find_forbidden_terms(self):
        from scripts.insta_cards import textrules

        self.assertEqual(
            textrules.find_forbidden_terms("무조건 오를 아파트"), ["오를", "무조건"]
        )
        self.assertEqual(textrules.find_forbidden_terms("가격 대비 생활점수"), [])


if __name__ == "__main__":
    unittest.main()
