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


def make_valid_budget_choice_publication():
    from scripts.insta_cards import publication as p

    row_labels = (
        "최근 실거래가",
        "전용면적",
        "준공연도",
        "지하철",
        "배정 초등학교",
        "안전점수",
        "월 관리비",
    )

    def item(rank, name, region, pnu_seed, values):
        return p.Item(
            rank=rank,
            name=name,
            region=region,
            pnu=f"{pnu_seed:019d}",
            metrics=tuple(p.Metric(lbl, v, "") for lbl, v in zip(row_labels, values)),
            reasons=("지하철 도보권", "마트 인접"),
        )

    values_a = (
        "6억 9,000만원",
        "59.9㎡",
        "2015년",
        "480m",
        "마포초",
        "78점",
        "25만원 (연 300만원)",
    )
    values_b = (
        "6억 8,000만원",
        "84.9㎡",
        "2010년",
        "890m",
        "분당초",
        "81점",
        "31만원 (연 372만원)",
    )
    return p.Publication(
        schema_version=p.SCHEMA_VERSION,
        slug="budget-choice-11440-vs-41135-20260713",
        status="draft",
        series=p.Series.BUDGET_CHOICE,
        title="같은 7억, 서울 59㎡ vs 분당 84㎡",
        eyebrow="같은 예산, 다른 선택",
        hook="서울 59㎡ vs 분당 84㎡, 당신의 선택은?",
        summary="같은 7억 예산으로 두 지역 대표 단지를 비교했습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="계약일 기준 최근 90일 실거래",
        cover_image="01-cover.png",
        cover_alt="7억 예산 서울 분당 아파트 비교 카드",
        conditions=(
            p.Condition("예산", "7억 이하"),
            p.Condition("면적", "59㎡ / 84㎡"),
            p.Condition("기준일", "2026-07-13"),
        ),
        items=(
            item(1, "마포한강푸르지오", "서울 마포구", 1, values_a),
            item(2, "분당파크뷰", "성남 분당구", 2, values_b),
        ),
        secondary_items=None,
        comparison=p.Comparison(
            row_labels=row_labels,
            columns=(
                p.ComparisonColumn("마포한강푸르지오", values_a),
                p.ComparisonColumn("분당파크뷰", values_b),
            ),
        ),
        narrative=p.Narrative(
            why=("두 지역의 ㎡당 가격 차이가 면적 차이로 이어집니다.",),
            fit_for=p.FitFor(a="입지·교통 우선이라면 서울", b="면적 우선이라면 분당"),
        ),
        methodology=("각 지역 예산 이하 실거래 단지 중 넛지 점수 1위를 대표로 선정",),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다.",
        ),
        map_ctas=(
            p.MapCta(
                "map-a",
                "마포 조건으로 보기",
                ("cost",),
                "11440",
                "서울 마포구",
                {"max_price": 70000},
            ),
            p.MapCta(
                "map-b",
                "분당 조건으로 보기",
                ("cost",),
                "41135",
                "성남 분당구",
                {"max_price": 70000},
            ),
        ),
    )


def make_valid_trade_top_publication():
    from scripts.insta_cards import publication as p

    def price_item(rank):
        return p.Item(
            rank=rank,
            name=f"고가단지{rank}",
            region="서울 서초구",
            pnu=f"{rank:019d}",
            metrics=(
                p.Metric("거래가", f"{30 - rank}억", ""),
                p.Metric("전용면적", "84㎡", ""),
            ),
            reasons=(),
        )

    def hot_item(rank):
        return p.Item(
            rank=rank,
            name=f"급증동네{rank}",
            region=None,
            pnu=None,
            metrics=(
                p.Metric("신고 건수", f"{200 - rank * 10}건", ""),
                p.Metric("직전 대비", f"+{50 - rank * 5}건", ""),
            ),
            reasons=(),
        )

    return p.Publication(
        schema_version=p.SCHEMA_VERSION,
        slug="trade-top-20260713",
        status="draft",
        series=p.Series.TRADE_TOP,
        title="이번 주 신고 최고가 TOP 5",
        eyebrow="신고일 기준 · 최근 7일",
        hook="최근 7일 신고 최고가는 29억",
        summary="신고일 기준 최근 7일 최고가 거래와 신고 급증 동네를 모았습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="신고일 기준 최근 7일",
        cover_image="01-cover.png",
        cover_alt="최근 7일 아파트 신고 최고가 TOP 5 카드",
        conditions=(
            p.Condition("기간", "신고일 기준 최근 7일"),
            p.Condition("기준일", "2026-07-13"),
        ),
        items=tuple(price_item(i + 1) for i in range(5)),
        secondary_items=tuple(hot_item(i + 1) for i in range(5)),
        comparison=None,
        narrative=p.Narrative(why=(), fit_for=None),
        methodology=(
            "단지별 최고가 1건 기준, 신고일 최근 7일 집계",
            "급증은 직전 7일 대비 신고 건수 증가",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고일 기준이라 계약 시점과 다를 수 있습니다.",
        ),
        map_ctas=(),
    )


class TestSlides(unittest.TestCase):
    def _assert_slides(self, pub, expected_names):
        from scripts.insta_cards import slides

        result = slides.build_slides(pub)
        self.assertEqual([name for name, _ in result], expected_names)
        for _, image in result:
            self.assertEqual(image.size, (1080, 1080))

    def test_value_slides(self):
        self._assert_slides(
            make_valid_value_publication(),
            [
                "01-cover.png",
                "02-conditions.png",
                "03-ranking.png",
                "04-why.png",
                "05-caveats.png",
                "06-cta.png",
            ],
        )

    def test_budget_choice_slides(self):
        self._assert_slides(
            make_valid_budget_choice_publication(),
            [
                "01-cover.png",
                "02-conditions.png",
                "03-candidate-a.png",
                "04-candidate-b.png",
                "05-comparison.png",
                "06-why.png",
                "07-fit.png",
                "08-caveats.png",
                "09-cta.png",
            ],
        )

    def test_trade_top_slides(self):
        self._assert_slides(
            make_valid_trade_top_publication(),
            [
                "01-cover.png",
                "02-conditions.png",
                "03-ranking.png",
                "04-ranking-hot.png",
                "05-caveats.png",
                "06-cta.png",
            ],
        )

    def test_cta_question_variants(self):
        from scripts.insta_cards import slides

        self.assertIn("vs", slides.cta_question(make_valid_budget_choice_publication()))
        self.assertEqual(
            slides.cta_question(make_valid_value_publication()),
            "내 조건으로 직접 찾아보기",
        )

    def test_long_names_do_not_crash(self):
        import dataclasses

        from scripts.insta_cards import publication as p, slides

        pub = make_valid_value_publication()
        long_item = p.Item(
            rank=1,
            name="아주아주아주아주아주아주긴한글단지이름" * 3,
            region="서울 노원구",
            pnu="1" * 19,
            metrics=(p.Metric("㎡당 가격", "1,000", "만원/㎡"),),
            reasons=("이유",),
        )
        items = (long_item,) + pub.items[1:]
        pub = dataclasses.replace(pub, items=items)
        for _, image in slides.build_slides(pub):
            self.assertEqual(image.size, (1080, 1080))

    def test_why_at_line_limit_validates_and_renders(self):
        """why 가 한도(2줄)를 정확히 채워도 검증 통과 + 렌더 폭 정합으로 줄 탈락 없음."""
        import dataclasses

        from scripts.insta_cards import publication as p, slides, textrules, theme

        limit = textrules.TEXT_LIMITS["why"]
        font = theme.get_font(limit.font_weight, limit.font_size)
        text = "가격 대비 생활점수가 높은 후보를 골랐습니다"
        word = " 지하철과 학교 접근성"
        while (
            len(textrules.wrap_text(text + word, font, limit.max_width))
            <= limit.max_lines
        ):
            text += word
        self.assertEqual(
            len(textrules.wrap_text(text, font, limit.max_width)), limit.max_lines
        )
        pub = dataclasses.replace(
            make_valid_value_publication(),
            narrative=p.Narrative(why=(text,), fit_for=None),
        )
        p.validate(pub)  # 한도 정확히 채운 문구는 통과해야 함
        for _, image in slides.build_slides(pub):
            self.assertEqual(image.size, (1080, 1080))


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

    def test_map_ctas_exactly_two_for_comparison_series(self):
        import dataclasses

        from scripts.insta_cards import publication as p

        pub = make_valid_budget_choice_publication()
        pub = dataclasses.replace(pub, map_ctas=pub.map_ctas[:1])
        with self.assertRaises(p.PublicationValidationError) as ctx:
            p.validate(pub)
        self.assertTrue(any("map_ctas" in e for e in ctx.exception.errors))

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

    def test_item_name_required(self):
        import dataclasses

        pub = make_valid_value_publication()
        items = list(pub.items)
        items[0] = dataclasses.replace(items[0], name="")
        self.assertTrue(any(".name" in e for e in self._errors(items=tuple(items))))

    def test_to_json_dict_serializes_enum(self):
        from scripts.insta_cards import publication as p

        d = p.to_json_dict(make_valid_value_publication())
        self.assertEqual(d["series"], "value")
        self.assertEqual(d["schema_version"], 1)
        import json

        json.dumps(d, ensure_ascii=False)  # 직렬화 가능해야 함


class TestCopywriting(unittest.TestCase):
    def test_budget_choice_copy_has_no_forbidden_terms(self):
        from scripts.insta_cards import copywriting, textrules

        bundle = copywriting.build_budget_choice_copy(
            "서울 마포구",
            "성남 분당구",
            69000,
            68000,
            59.9,
            84.9,
            ["지하철", "마트"],
            ["공원", "학교"],
        )
        for text in (bundle.hook, *bundle.why, bundle.fit_for.a, bundle.fit_for.b):
            self.assertEqual(textrules.find_forbidden_terms(text), [])
        self.assertIn("59", bundle.hook)
        self.assertIn("84", bundle.hook)

    def test_contributor_labels_maps_subtypes(self):
        from scripts.insta_cards import copywriting

        rows = [{"subtype": "subway"}, {"subtype": "mart"}, {"subtype": "score_safety"}]
        self.assertEqual(
            copywriting.contributor_labels(rows), ["지하철", "마트", "안전 점수"]
        )

    def test_load_copy_overrides_rejects_unknown_key(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("hook: 좋은 문구\nevil: 나쁜키\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_load_copy_overrides_rejects_wrong_type(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("why: 문자열이면안됨\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_load_copy_overrides_rejects_empty_string(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("hook: ''\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_apply_overrides_replaces_only_given_keys(self):
        from scripts.insta_cards import copywriting

        base = copywriting.build_value_copy("서울")
        merged = copywriting.apply_overrides(base, {"hook": "새 훅 문장"})
        self.assertEqual(merged.hook, "새 훅 문장")
        self.assertEqual(merged.why, base.why)


class TestDatasources(unittest.TestCase):
    def _detail_fixture(self):
        return {
            "basic": {"use_apr_day": "20150330", "sigungu_code": "41135"},
            "scores": {"cost": 71.2},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "분당초", "estimated": False},
            "safety": {"safety_score": 78.5},
            "mgmt_cost": {
                "by_area": [
                    {"exclusive_area": 59, "per_unit_cost": 245000, "unit_count": 300},
                    {"exclusive_area": 84, "per_unit_cost": 310000, "unit_count": 200},
                ]
            },
        }

    def test_post_nudge_score_rejects_missing_keys(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = [{"pnu": "1" * 19}]  # bld_nm 등 누락
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.post", return_value=fake):
            with self.assertRaises(datasources.DataSourceError):
                datasources.post_nudge_score({"nudges": ["cost"]})

    def test_get_region_name_raises_when_not_found(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = [{"code": "11440", "name": "서울 마포구"}]
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.get", return_value=fake):
            self.assertEqual(datasources.get_region_name("11440"), "서울 마포구")
            with self.assertRaises(datasources.DataSourceError):
                datasources.get_region_name("99999")

    def test_get_apartment_detail_requires_keys(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = {"basic": {}}  # 나머지 키 누락
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.get", return_value=fake):
            with self.assertRaises(datasources.DataSourceError):
                datasources.get_apartment_detail("1" * 19)

    def test_extract_candidate_metrics_full(self):
        from scripts.insta_cards import datasources

        metrics = datasources.extract_candidate_metrics(self._detail_fixture(), 59.8)
        labels = [m.label for m in metrics]
        self.assertEqual(labels, ["지하철", "배정 초등학교", "안전점수", "월 관리비"])
        self.assertIn("480", metrics[0].value)
        self.assertEqual(metrics[1].value, "분당초")
        # target_area 59.8 → by_area 59 선택 (가장 가까운 평형)
        self.assertIn("25만원", metrics[3].value)
        self.assertIn("연", metrics[3].value)

    def test_extract_candidate_metrics_missing_becomes_info_none(self):
        from scripts.insta_cards import datasources

        detail = self._detail_fixture()
        detail["school"] = None
        detail["mgmt_cost"] = None
        metrics = datasources.extract_candidate_metrics(detail, None)
        self.assertEqual(metrics[1].value, "정보 없음")
        self.assertEqual(metrics[3].value, "정보 없음")

    def test_fetch_recent_trades_builds_conditional_sql(self):
        from unittest.mock import patch

        from scripts.insta_cards import datasources

        captured = {}

        def fake_query_all(conn, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [
                {
                    "pnu": "1" * 19,
                    "deal_amount": 68000,
                    "exclu_use_ar": 59.9,
                    "deal_date": None,
                    "bld_nm": "테스트단지",
                    "use_apr_day": "20100101",
                }
            ]

        with patch("scripts.insta_cards.datasources.query_all", fake_query_all):
            result = datasources.fetch_recent_trades(
                None, "11440", max_amount=70000, min_area=54.9, max_area=64.9
            )
        self.assertIn("deal_amount <= %s", captured["sql"])
        self.assertIn("exclu_use_ar BETWEEN %s AND %s", captured["sql"])
        self.assertEqual(list(result.keys()), ["1" * 19])


class TestOutput(unittest.TestCase):
    def _run(self, tmp, pub=None, force=False, slides=None):
        from pathlib import Path

        from scripts.insta_cards import output, slides as slides_mod

        pub = pub or make_valid_value_publication()
        slides = slides if slides is not None else slides_mod.build_slides(pub)
        return output.write_publication(pub, slides, force=force, root=Path(tmp))

    def test_write_creates_all_files(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            final_dir = self._run(tmp)
            pngs = sorted(p.name for p in final_dir.glob("*.png"))
            self.assertEqual(len(pngs), 6)
            self.assertEqual(pngs[0], "01-cover.png")
            data = json.loads((final_dir / "publication.json").read_text())
            self.assertEqual(data["slug"], "value-seoul-20260713")
            # 임시 디렉토리가 남지 않아야 함
            self.assertEqual(list(Path(tmp).glob("**/*.tmp-*")), [])

    def test_slug_conflict_across_dates(self):
        import tempfile
        from pathlib import Path

        from scripts.insta_cards import output

        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "2026-07-01" / "value-seoul-20260713"
            old.mkdir(parents=True)
            (old / "stale.png").write_bytes(b"x")
            with self.assertRaises(output.SlugConflictError):
                self._run(tmp)

    def test_force_replaces_whole_directory(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "2026-07-01" / "value-seoul-20260713"
            old.mkdir(parents=True)
            (old / "stale.png").write_bytes(b"x")
            final_dir = self._run(tmp, force=True)
            self.assertFalse(old.exists())
            self.assertFalse((final_dir / "stale.png").exists())

    def test_force_same_date_replace_failure_preserves_existing(self):
        """같은 날짜 --force 재발행 중 tmp→final replace 실패 시 기존 발행물 보존."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.insta_cards import output

        with tempfile.TemporaryDirectory() as tmp:
            final_dir = self._run(tmp)  # 최초 발행 (오늘 날짜)
            original = (final_dir / "publication.json").read_text()

            real_replace = output.os.replace
            calls = {"n": 0}

            def flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] == 2:  # 1번째 = final→backup, 2번째 = tmp→final
                    raise OSError("disk boom")
                return real_replace(src, dst)

            with patch(
                "scripts.insta_cards.output.os.replace", side_effect=flaky_replace
            ):
                with self.assertRaises(OSError):
                    self._run(tmp, force=True)
            # 기존 발행물이 원복되어 그대로 남아 있어야 함
            self.assertEqual((final_dir / "publication.json").read_text(), original)
            # 백업/임시 디렉토리가 남지 않아야 함
            self.assertEqual(list(Path(tmp).glob("**/*.bak-*")), [])
            self.assertEqual(list(Path(tmp).glob("**/*.tmp-*")), [])

    def test_render_failure_leaves_no_final_dir(self):
        import tempfile
        from pathlib import Path

        class Boom:
            def save(self, *a, **kw):
                raise RuntimeError("render boom")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self._run(tmp, slides=[("01-cover.png", Boom())])
            self.assertEqual(list(Path(tmp).glob("**/value-seoul-20260713")), [])
            self.assertEqual(list(Path(tmp).glob("**/*.tmp-*")), [])


class TestTradeTopSeries(unittest.TestCase):
    def _price_rows(self, n=5):
        return [
            {
                "pnu": f"{i + 1:019d}",
                "apt_display_name": f"단지{i + 1}",
                "sigungu_name": "서울 서초구",
                "deal_amount": 300000 - i * 10000,
                "exclu_use_ar": 84.9,
            }
            for i in range(n)
        ]

    def _hot_rows(self, n=5):
        return [
            {
                "sigungu_name": f"동네{i + 1}",
                "current_count": 200 - i * 10,
                "prev_count": 150 - i * 10,
                "delta": 50,
            }
            for i in range(n)
        ]

    def test_build_publication_passes_validation(self):
        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import trade_top

        pub = trade_top.build_publication(
            self._price_rows(),
            self._hot_rows(),
            days=7,
            slug="trade-top-20260713",
            status="draft",
            published_at=None,
            copy_overrides=None,
        )
        p.validate(pub)  # 예외 없어야 함
        self.assertEqual(pub.series, p.Series.TRADE_TOP)
        self.assertEqual(pub.items[0].pnu, f"{1:019d}")
        self.assertEqual(len(pub.secondary_items), 5)
        self.assertEqual(pub.map_ctas, ())
        self.assertIn(
            "직전", pub.secondary_items[0].metrics[1].label + pub.methodology[1]
        )

    def test_insufficient_rows_raise(self):
        from scripts.insta_cards.series import trade_top

        with self.assertRaises(ValueError):
            trade_top.build_publication(
                self._price_rows(3),
                self._hot_rows(),
                days=7,
                slug="trade-top-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )

    def test_hot_sql_filters_by_min_report_count(self):
        from unittest.mock import patch

        from scripts.insta_cards.series import trade_top

        captured = {}

        def fake_query_all(conn, sql, params=None):
            captured["sql"], captured["params"] = sql, params
            return []

        with patch("scripts.insta_cards.series.trade_top.query_all", fake_query_all):
            trade_top.fetch_hot_districts(None, 7)
        self.assertIn("prev_window", captured["sql"])
        self.assertIn(trade_top.MIN_REPORT_COUNT, captured["params"])


class TestValueSeries(unittest.TestCase):
    def _candidates(self, n=8):
        return [
            {
                "pnu": f"{i + 1:019d}",
                "bld_nm": f"단지{i + 1}",
                "score": 80.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}, {"subtype": "mart"}],
            }
            for i in range(n)
        ]

    def test_select_candidates_sorts_by_price(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {
            c["pnu"]: 10_000_000.0 - i * 100_000 for i, c in enumerate(candidates)
        }
        top5 = value.select_candidates(candidates, price_map, 100)
        prices = [price_map[c["pnu"]] for c in top5]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(len(top5), 5)

    def test_select_candidates_rejects_undersized(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        candidates[0]["total_hhld_cnt"] = 10
        with self.assertRaises(ValueError):
            value.select_candidates(
                candidates, {c["pnu"]: 1.0 for c in candidates}, 100
            )

    def test_select_candidates_requires_five_with_price(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {candidates[0]["pnu"]: 1.0}  # 1건만 price 보유
        with self.assertRaises(ValueError):
            value.select_candidates(candidates, price_map, 100)

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {c["pnu"]: 9_000_000.0 + i for i, c in enumerate(candidates)}

        args = MagicMock()
        args.region, args.nudge, args.min_hhld = "서울", "cost", 100

        with (
            patch(
                "scripts.insta_cards.series.value.post_nudge_score",
                return_value=candidates,
            ),
            patch(
                "scripts.insta_cards.series.value.fetch_price_per_m2_by_pnu",
                return_value=price_map,
            ),
            patch(
                "scripts.insta_cards.series.value.open_local_db",
                return_value=MagicMock(),
            ),
            patch(
                "scripts.insta_cards.series.value.stale_trade_warning",
                return_value=None,
            ),
        ):
            pub = value.run(
                args,
                slug="value-11000-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.VALUE)
        self.assertEqual(len(pub.items), 5)
        self.assertEqual(pub.map_ctas[0].nudges, ("cost",))
        self.assertEqual(pub.map_ctas[0].filters, {"min_hhld": 100})


class TestCompareSeries(unittest.TestCase):
    def _scored(self, base):
        return [
            {
                "pnu": f"{base + i:019d}",
                "bld_nm": f"단지{base + i}",
                "score": 80.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}],
            }
            for i in range(10)
        ]

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import compare

        detail = {
            "basic": {"use_apr_day": "20150330"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "테스트초", "estimated": False},
            "safety": {"safety_score": 78.0},
            "mgmt_cost": None,
        }
        args = MagicMock()
        args.regions, args.nudge = "11440,41135", "newlywed"

        def fake_scored(payload):
            return self._scored(1 if payload["sigungu_code"] == "11440" else 100)

        aggregate = {"median_amount": 95000.0, "trade_count": 120, "avg_age": 14.2}
        with (
            patch(
                "scripts.insta_cards.series.compare.post_nudge_score",
                side_effect=fake_scored,
            ),
            patch(
                "scripts.insta_cards.series.compare.get_region_name",
                side_effect=lambda c: {"11440": "서울 마포구", "41135": "성남 분당구"}[
                    c
                ],
            ),
            patch(
                "scripts.insta_cards.series.compare.get_apartment_detail",
                return_value=detail,
            ),
            patch(
                "scripts.insta_cards.series.compare.fetch_region_aggregate",
                return_value=aggregate,
            ),
            patch(
                "scripts.insta_cards.series.compare.open_local_db",
                return_value=MagicMock(),
            ),
            patch(
                "scripts.insta_cards.series.compare.stale_trade_warning",
                return_value=None,
            ),
        ):
            pub = compare.run(
                args,
                slug="compare-11440-vs-41135-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.COMPARE)
        self.assertEqual(len(pub.items), 2)
        self.assertEqual(len(pub.map_ctas), 2)
        self.assertEqual(pub.comparison.row_labels, compare.COMPARISON_ROW_LABELS)
        self.assertIn("상위 10개", " ".join(pub.methodology))

    def test_empty_top10_raises(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards.series import compare

        args = MagicMock()
        args.regions, args.nudge = "11440,41135", "newlywed"
        with (
            patch(
                "scripts.insta_cards.series.compare.post_nudge_score", return_value=[]
            ),
            patch(
                "scripts.insta_cards.series.compare.get_region_name",
                return_value="서울 마포구",
            ),
        ):
            with self.assertRaises(ValueError):
                compare.run(
                    args,
                    slug="compare-x-20260713",
                    status="draft",
                    published_at=None,
                    copy_overrides=None,
                )

    def test_regions_must_be_two(self):
        from unittest.mock import MagicMock

        from scripts.insta_cards.series import compare

        args = MagicMock()
        args.regions, args.nudge = "11440", "newlywed"
        with self.assertRaises(ValueError):
            compare.run(
                args,
                slug="compare-x-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )


class TestBudgetChoiceSeries(unittest.TestCase):
    def _eligible(self, seeds):
        return {
            f"{s:019d}": {
                "pnu": f"{s:019d}",
                "deal_amount": 68000,
                "exclu_use_ar": 59.9,
                "deal_date": None,
                "bld_nm": f"단지{s}",
                "use_apr_day": "20150330",
            }
            for s in seeds
        }

    def _scored(self, seeds):
        return [
            {
                "pnu": f"{s:019d}",
                "bld_nm": f"단지{s}",
                "score": 90.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}],
            }
            for i, s in enumerate(seeds)
        ]

    def test_select_representative_intersects_by_score_order(self):
        from scripts.insta_cards.series import budget_choice

        eligible = self._eligible([3, 4])
        scored = self._scored([1, 2, 3, 4])  # 1,2 는 eligible 아님
        trade, row = budget_choice.select_representative(eligible, scored, None)
        self.assertEqual(trade["pnu"], f"{3:019d}")
        self.assertEqual(row["pnu"], f"{3:019d}")

    def test_select_representative_empty_intersection_raises(self):
        from scripts.insta_cards.series import budget_choice

        with self.assertRaises(ValueError):
            budget_choice.select_representative(
                self._eligible([9]), self._scored([1, 2]), None
            )

    def test_override_must_be_eligible(self):
        from scripts.insta_cards.series import budget_choice

        eligible = self._eligible([3])
        with self.assertRaises(ValueError):
            budget_choice.select_representative(
                eligible, self._scored([3]), f"{7:019d}"
            )

    def test_override_eligible_but_not_scored_returns_empty_row(self):
        from scripts.insta_cards.series import budget_choice

        eligible = self._eligible([7])
        trade, row = budget_choice.select_representative(
            eligible, self._scored([1, 2]), f"{7:019d}"
        )
        self.assertEqual(trade["pnu"], f"{7:019d}")
        self.assertEqual(row, {})

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import budget_choice

        detail = {
            "basic": {"use_apr_day": "20150330"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "테스트초", "estimated": False},
            "safety": {"safety_score": 78.0},
            "mgmt_cost": {
                "by_area": [
                    {"exclusive_area": 59, "per_unit_cost": 245000, "unit_count": 100}
                ]
            },
        }
        args = MagicMock()
        args.budget, args.regions = 70000, "11440,41135"
        args.area_a, args.area_b, args.area_tolerance = 59.0, 84.0, 5.0
        args.nudge, args.pnu_a, args.pnu_b = "cost", None, None

        def fake_trades(conn, code, **kw):
            return self._eligible([1, 2] if code == "11440" else [5, 6])

        def fake_scored(payload):
            return self._scored(
                [1, 2] if payload["sigungu_code"] == "11440" else [5, 6]
            )

        with (
            patch(
                "scripts.insta_cards.series.budget_choice.fetch_recent_trades",
                side_effect=fake_trades,
            ),
            patch(
                "scripts.insta_cards.series.budget_choice.post_nudge_score",
                side_effect=fake_scored,
            ),
            patch(
                "scripts.insta_cards.series.budget_choice.get_region_name",
                side_effect=lambda c: {"11440": "서울 마포구", "41135": "성남 분당구"}[
                    c
                ],
            ),
            patch(
                "scripts.insta_cards.series.budget_choice.get_apartment_detail",
                return_value=detail,
            ),
            patch(
                "scripts.insta_cards.series.budget_choice.open_local_db",
                return_value=MagicMock(),
            ),
            patch(
                "scripts.insta_cards.series.budget_choice.stale_trade_warning",
                return_value=None,
            ),
        ):
            pub = budget_choice.run(
                args,
                slug="budget-choice-11440-vs-41135-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.BUDGET_CHOICE)
        self.assertEqual(pub.comparison.row_labels, budget_choice.ROW_LABELS)
        self.assertEqual(len(pub.map_ctas), 2)
        self.assertEqual(pub.map_ctas[0].filters["max_price"], 70000)
        # 카드 표기 가격은 eligible 대표 거래에서 나온다 (예산 이하 보장)
        self.assertIn("6억 8,000만원", pub.items[0].metrics[0].value)


class TestLifestyleSeries(unittest.TestCase):
    def _eligible(self, seeds):
        return {
            f"{s:019d}": {
                "pnu": f"{s:019d}",
                "deal_amount": 65000,
                "exclu_use_ar": 74.9,
                "deal_date": None,
                "bld_nm": f"단지{s}",
                "use_apr_day": "20180501",
            }
            for s in seeds
        }

    def _scored(self, seeds, hhld=500):
        return [
            {
                "pnu": f"{s:019d}",
                "bld_nm": f"단지{s}",
                "score": 90.0 - i,
                "total_hhld_cnt": hhld,
                "top_contributors": [{"subtype": "kindergarten"}, {"subtype": "mart"}],
            }
            for i, s in enumerate(seeds)
        ]

    def test_select_candidates_caps_at_five(self):
        from scripts.insta_cards.series import lifestyle

        result = lifestyle.select_candidates(
            self._eligible(range(1, 10)), self._scored(range(1, 10)), 100
        )
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["trade"]["bld_nm"], "단지1")

    def test_select_candidates_requires_three(self):
        from scripts.insta_cards.series import lifestyle

        with self.assertRaises(ValueError):
            lifestyle.select_candidates(
                self._eligible([1, 2]), self._scored([1, 2]), 100
            )

    def test_select_candidates_rejects_undersized(self):
        from scripts.insta_cards.series import lifestyle

        with self.assertRaises(ValueError):
            lifestyle.select_candidates(
                self._eligible([1, 2, 3]), self._scored([1, 2, 3], hhld=10), 100
            )

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import lifestyle

        detail = {
            "basic": {"use_apr_day": "20180501"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 620.0}},
            "school": {"elementary_school_name": "판교초", "estimated": False},
            "safety": {"safety_score": 82.0},
            "mgmt_cost": None,
        }
        args = MagicMock()
        args.profile, args.region, args.min_hhld = "newlywed", "41135", 100
        args.max_price, args.min_area, args.max_area = 70000, None, None

        with (
            patch(
                "scripts.insta_cards.series.lifestyle.fetch_recent_trades",
                return_value=self._eligible(range(1, 7)),
            ),
            patch(
                "scripts.insta_cards.series.lifestyle.post_nudge_score",
                return_value=self._scored(range(1, 7)),
            ),
            patch(
                "scripts.insta_cards.series.lifestyle.get_region_name",
                return_value="성남 분당구",
            ),
            patch(
                "scripts.insta_cards.series.lifestyle.get_apartment_detail",
                return_value=detail,
            ),
            patch(
                "scripts.insta_cards.series.lifestyle.open_local_db",
                return_value=MagicMock(),
            ),
            patch(
                "scripts.insta_cards.series.lifestyle.stale_trade_warning",
                return_value=None,
            ),
        ):
            pub = lifestyle.run(
                args,
                slug="lifestyle-newlywed-41135-20260713",
                status="draft",
                published_at=None,
                copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.LIFESTYLE)
        self.assertEqual(len(pub.items), 5)
        self.assertEqual(pub.map_ctas[0].nudges, ("newlywed",))
        self.assertEqual(pub.map_ctas[0].filters["max_price"], 70000)
        self.assertIn("min_hhld", pub.map_ctas[0].filters)


class TestCli(unittest.TestCase):
    def test_legacy_options_still_parse(self):
        from scripts.insta_cards import cli

        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "--series",
                "value",
                "--region",
                "서울",
                "--nudge",
                "cost",
                "--min-hhld",
                "100",
            ]
        )
        self.assertEqual(args.series, "value")
        self.assertEqual(args.min_hhld, 100)

    def test_new_series_options_parse(self):
        from scripts.insta_cards import cli

        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "--series",
                "budget-choice",
                "--budget",
                "70000",
                "--regions",
                "11440,41135",
                "--area-a",
                "59",
                "--area-b",
                "84",
            ]
        )
        self.assertEqual(args.budget, 70000)
        self.assertEqual(args.area_tolerance, 5.0)

    def test_auto_slug_for_budget_choice(self):
        from types import SimpleNamespace

        from scripts.insta_cards import cli, publication as p

        args = SimpleNamespace(regions="11440,41135", region=None, profile=None, days=7)
        slug = cli.build_auto_slug(p.Series.BUDGET_CHOICE, args)
        self.assertRegex(slug, r"^budget-choice-11440-vs-41135-\d{8}$")

    def test_auto_slug_rejects_non_ascii(self):
        from types import SimpleNamespace

        from scripts.insta_cards import cli, publication as p

        args = SimpleNamespace(regions=None, region="서울", profile=None, days=7)
        with self.assertRaises(SystemExit):
            cli.build_auto_slug(p.Series.VALUE, args)

    def test_dry_run_writes_nothing(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.insta_cards import cli

        pub = make_valid_value_publication()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("scripts.insta_cards.series.value.run", return_value=pub),
                patch("scripts.insta_cards.output.OUTPUT_ROOT", Path(tmp)),
            ):
                cli.main(
                    [
                        "--series",
                        "value",
                        "--region",
                        "서울",
                        "--slug",
                        "value-seoul-20260713",
                        "--dry-run",
                    ]
                )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_main_writes_publication(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.insta_cards import cli

        pub = make_valid_value_publication()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("scripts.insta_cards.series.value.run", return_value=pub),
                patch("scripts.insta_cards.cli.OUTPUT_ROOT", Path(tmp)),
            ):
                cli.main(
                    [
                        "--series",
                        "value",
                        "--region",
                        "서울",
                        "--slug",
                        "value-seoul-20260713",
                    ]
                )
            found = list(Path(tmp).glob("*/value-seoul-20260713/publication.json"))
            self.assertEqual(len(found), 1)

    def test_shim_module_delegates(self):
        import importlib

        shim = importlib.import_module("scripts.generate_insta_cards")
        from scripts.insta_cards import cli

        self.assertIs(shim.main, cli.main)


class TestFrontendPublish(unittest.TestCase):
    def _record(
        self, slug, published_at="2026-07-17", generated_at="2026-07-17T10:00:00"
    ):
        return {
            "slug": slug,
            "status": "published",
            "published_at": published_at,
            "generated_at": generated_at,
            "cover_image": "01-cover.png",
            "title": f"제목 {slug}",
        }

    def _setup_fs(self, tmp):
        from pathlib import Path

        root = Path(tmp) / "frontend"
        cover_src = Path(tmp) / "01-cover.png"
        cover_src.write_bytes(b"PNG-NEW")
        return root, cover_src

    def test_publish_creates_posts_and_cover(self):
        import json
        import tempfile

        from scripts.insta_cards import frontend_publish as fp

        with tempfile.TemporaryDirectory() as tmp:
            root, cover_src = self._setup_fs(tmp)
            posts_path = fp.publish_to_frontend(self._record("a-slug"), cover_src, root)
            data = json.loads(posts_path.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["slug"], "a-slug")
            self.assertEqual(
                data[0]["cover_image"], "/content/instagram/a-slug/cover.png"
            )
            cover = root / "public/content/instagram/a-slug/cover.png"
            self.assertEqual(cover.read_bytes(), b"PNG-NEW")

    def test_upsert_replaces_same_slug_and_sorts_deterministically(self):
        from scripts.insta_cards import frontend_publish as fp

        posts = [
            self._record("b-slug", "2026-07-15"),
            self._record("a-slug", "2026-07-16", "2026-07-16T09:00:00"),
        ]
        merged = fp.upsert_posts(
            posts, self._record("c-slug", "2026-07-16", "2026-07-16T09:00:00")
        )
        # published_at DESC → generated_at DESC → slug ASC
        self.assertEqual([p["slug"] for p in merged], ["a-slug", "c-slug", "b-slug"])
        replaced = fp.upsert_posts(merged, self._record("b-slug", "2026-07-17"))
        self.assertEqual([p["slug"] for p in replaced], ["b-slug", "a-slug", "c-slug"])
        self.assertEqual(len(replaced), 3)

    def test_broken_posts_json_raises(self):
        import tempfile

        from scripts.insta_cards import frontend_publish as fp

        with tempfile.TemporaryDirectory() as tmp:
            root, cover_src = self._setup_fs(tmp)
            posts_path = root / "src/content/instagram/posts.json"
            posts_path.parent.mkdir(parents=True)
            posts_path.write_text('{"not": "array"}', encoding="utf-8")
            with self.assertRaises(fp.FrontendPublishError):
                fp.publish_to_frontend(self._record("a-slug"), cover_src, root)

    def test_posts_replace_failure_restores_cover(self):
        import tempfile
        from unittest.mock import patch

        from scripts.insta_cards import frontend_publish as fp

        with tempfile.TemporaryDirectory() as tmp:
            root, cover_src = self._setup_fs(tmp)
            # 1차 발행으로 기존 상태 구성
            fp.publish_to_frontend(self._record("a-slug"), cover_src, root)
            cover_dst = root / "public/content/instagram/a-slug/cover.png"
            posts_path = root / "src/content/instagram/posts.json"
            old_posts = posts_path.read_text(encoding="utf-8")
            cover_src.write_bytes(b"PNG-V2")

            real_replace = fp.os.replace
            calls = {"n": 0}

            def flaky_replace(src, dst):
                calls["n"] += 1
                # 재발행 시 replace 순서: ①cover 백업 ②새 cover 배치 ③posts.json 교체
                if calls["n"] == 3:
                    raise OSError("disk full")
                return real_replace(src, dst)

            with patch.object(fp.os, "replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    fp.publish_to_frontend(
                        self._record("a-slug", "2026-07-18"), cover_src, root
                    )

            # 기존 cover·posts.json 모두 원복, 임시/백업 잔존 없음
            self.assertEqual(cover_dst.read_bytes(), b"PNG-NEW")
            self.assertEqual(posts_path.read_text(encoding="utf-8"), old_posts)
            leftovers = [
                p for p in root.rglob("*") if ".tmp-" in p.name or ".bak-" in p.name
            ]
            self.assertEqual(leftovers, [])

    def test_cover_replace_failure_restores_backup(self):
        import tempfile
        from unittest.mock import patch

        from scripts.insta_cards import frontend_publish as fp

        with tempfile.TemporaryDirectory() as tmp:
            root, cover_src = self._setup_fs(tmp)
            # 1차 발행으로 기존 상태 구성
            fp.publish_to_frontend(self._record("a-slug"), cover_src, root)
            cover_dst = root / "public/content/instagram/a-slug/cover.png"
            posts_path = root / "src/content/instagram/posts.json"
            old_posts = posts_path.read_text(encoding="utf-8")
            cover_src.write_bytes(b"PNG-V2")

            real_replace = fp.os.replace
            calls = {"n": 0}

            def flaky_replace(src, dst):
                calls["n"] += 1
                # 재발행 시 replace 순서: ①cover 백업 ②새 cover 배치 ③posts.json 교체
                if calls["n"] == 2:
                    raise OSError("disk full")
                return real_replace(src, dst)

            with patch.object(fp.os, "replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    fp.publish_to_frontend(
                        self._record("a-slug", "2026-07-18"), cover_src, root
                    )

            # ②(새 cover 배치) 실패 시에도 백업 원복 — cover 소실·백업 잔존 없음
            self.assertEqual(cover_dst.read_bytes(), b"PNG-NEW")
            self.assertEqual(posts_path.read_text(encoding="utf-8"), old_posts)
            leftovers = [
                p for p in root.rglob("*") if ".tmp-" in p.name or ".bak-" in p.name
            ]
            self.assertEqual(leftovers, [])


class TestInstagramAssets(unittest.TestCase):
    def _make_source(self, tmp, slide_count=3):
        import json
        from pathlib import Path

        from PIL import Image

        src = Path(tmp) / "src"
        src.mkdir()
        names = [f"{i + 1:02d}-slide.png" for i in range(slide_count)]
        names[0] = "01-cover.png"
        for name in names:
            Image.new("RGB", (1080, 1080), (10, 20, 40)).save(src / name)
        (src / "publication.json").write_text(
            json.dumps({"slug": "test-slug", "status": "published"}),
            encoding="utf-8",
        )
        return src, names

    def test_build_converts_png_to_ordered_jpeg_manifest(self):
        import json
        import tempfile
        from pathlib import Path

        from PIL import Image

        from scripts.insta_cards.instagram import assets

        with tempfile.TemporaryDirectory() as tmp:
            src, names = self._make_source(tmp)
            dest = Path(tmp) / "dest"
            manifest = assets.build_ig_assets(src, dest)
            expected = [n.replace(".png", ".jpg") for n in names]
            self.assertEqual(manifest["instagram_assets"], expected)
            self.assertEqual(len(manifest["asset_generation"]), 12)
            for jpg in expected:
                img = Image.open(dest / jpg)
                self.assertEqual(img.format, "JPEG")
                self.assertEqual(img.size, (1080, 1080))
            saved = json.loads((dest / "publication.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["instagram_assets"], expected)
            self.assertEqual(saved["slug"], "test-slug")

    def test_generation_is_deterministic_and_content_sensitive(self):
        from scripts.insta_cards.instagram import assets

        g1 = assets.compute_generation(b"same-bytes")
        g2 = assets.compute_generation(b"same-bytes")
        g3 = assets.compute_generation(b"other-bytes")
        self.assertEqual(g1, g2)
        self.assertNotEqual(g1, g3)
        self.assertEqual(len(g1), 12)

    def test_slide_count_bounds(self):
        import tempfile
        from pathlib import Path

        from scripts.insta_cards.instagram import assets

        with tempfile.TemporaryDirectory() as tmp:
            src, _ = self._make_source(tmp, slide_count=1)
            with self.assertRaises(assets.InstagramAssetError):
                assets.build_ig_assets(src, Path(tmp) / "d1")
        with tempfile.TemporaryDirectory() as tmp:
            src, _ = self._make_source(tmp, slide_count=11)
            with self.assertRaises(assets.InstagramAssetError):
                assets.build_ig_assets(src, Path(tmp) / "d2")


if __name__ == "__main__":
    unittest.main()
