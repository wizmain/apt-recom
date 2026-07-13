"""insta_cards 패키지 테스트 — 클래스 1개 = 모듈 1개."""

import unittest


def make_valid_value_publication(**overrides):
    """value 시리즈 기준 유효 Publication 픽스처. overrides 로 필드 교체."""
    from scripts.insta_cards import publication as p

    items = tuple(
        p.Item(
            rank=i + 1,
            name=f"단지{i + 1}",
            region="서울 노원구",
            pnu=f"{1111111111111111110 + i:d}",
            metrics=(p.Metric("㎡당 가격", "1,000", "만원/㎡"),),
            reasons=("지하철 도보권",),
        )
        for i in range(5)
    )
    base = dict(
        schema_version=p.SCHEMA_VERSION,
        slug="value-seoul-20260713",
        status="draft",
        series=p.Series.VALUE,
        title="숨은 가성비 TOP 5 — 서울",
        eyebrow="가성비 랭킹",
        hook="가격은 낮은데 생활점수는 높은 단지 5곳",
        summary="서울에서 ㎡당 가격이 낮고 가성비 점수가 높은 단지를 골랐습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="가성비 넛지 상위 30 후보 기준",
        cover_image="01-cover.png",
        cover_alt="서울 숨은 가성비 아파트 TOP 5 카드",
        conditions=(p.Condition("지역", "서울"), p.Condition("최소 세대수", "100세대")),
        items=items,
        secondary_items=None,
        comparison=None,
        narrative=p.Narrative(
            why=("상위 후보 대비 ㎡당 가격이 낮습니다.",), fit_for=None
        ),
        methodology=("가성비 넛지 상위 30개 후보 중 ㎡당 가격 오름차순 5곳",),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다.",
        ),
        map_ctas=(
            p.MapCta(
                id="map-main",
                label="같은 조건으로 지도에서 보기",
                nudges=("cost",),
                sigungu_code=None,
                region_label="서울",
                filters={"min_hhld": 100},
            ),
        ),
    )
    base.update(overrides)
    return p.Publication(**base)


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


class TestPublication(unittest.TestCase):
    def _errors(self, **overrides):
        from scripts.insta_cards import publication as p

        try:
            p.validate(make_valid_value_publication(**overrides))
        except p.PublicationValidationError as e:
            return e.errors
        return []

    def test_valid_publication_passes(self):
        self.assertEqual(self._errors(), [])

    def test_slug_format(self):
        self.assertTrue(any("slug" in e for e in self._errors(slug="Bad_Slug")))

    def test_published_requires_published_at(self):
        self.assertTrue(
            any("published_at" in e for e in self._errors(status="published"))
        )

    def test_rank_must_be_sequential(self):
        from scripts.insta_cards import publication as p

        pub = make_valid_value_publication()
        broken = list(pub.items)
        broken[2] = p.Item(
            rank=99,
            name=broken[2].name,
            region=broken[2].region,
            pnu=broken[2].pnu,
            metrics=broken[2].metrics,
            reasons=broken[2].reasons,
        )
        self.assertTrue(any("rank" in e for e in self._errors(items=tuple(broken))))

    def test_min_items(self):
        pub = make_valid_value_publication()
        self.assertTrue(any("items" in e for e in self._errors(items=pub.items[:3])))

    def test_pnu_format(self):
        from scripts.insta_cards import publication as p

        pub = make_valid_value_publication()
        bad = p.Item(
            rank=1,
            name="x",
            region=None,
            pnu="123",
            metrics=pub.items[0].metrics,
            reasons=(),
        )
        items = (bad,) + tuple(
            p.Item(
                rank=i + 2,
                name=f"y{i}",
                region=None,
                pnu=None,
                metrics=pub.items[0].metrics,
                reasons=(),
            )
            for i in range(4)
        )
        self.assertTrue(any("pnu" in e for e in self._errors(items=items)))

    def test_forbidden_term_in_hook(self):
        self.assertTrue(
            any("금지" in e for e in self._errors(hook="무조건 오를 단지 5곳"))
        )

    def test_caveats_required(self):
        self.assertTrue(any("caveats" in e for e in self._errors(caveats=())))

    def test_map_ctas_required_for_non_trade_top(self):
        self.assertTrue(any("map_ctas" in e for e in self._errors(map_ctas=())))

    def test_filter_allowlist(self):
        from scripts.insta_cards import publication as p

        cta = p.MapCta(
            id="map-main",
            label="지도",
            nudges=("cost",),
            sigungu_code=None,
            region_label=None,
            filters={"evil_key": 1},
        )
        self.assertTrue(any("filters" in e for e in self._errors(map_ctas=(cta,))))

    def test_data_as_of_future_rejected(self):
        self.assertTrue(
            any("data_as_of" in e for e in self._errors(data_as_of="2099-01-01"))
        )

    def test_to_json_dict_serializes_enum(self):
        from scripts.insta_cards import publication as p

        d = p.to_json_dict(make_valid_value_publication())
        self.assertEqual(d["series"], "value")
        self.assertEqual(d["schema_version"], 1)
        import json

        json.dumps(d, ensure_ascii=False)  # 직렬화 가능해야 함


if __name__ == "__main__":
    unittest.main()
