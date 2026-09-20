"""K-APT 분양·임대 PNU 경합 검수 목록의 짝짓기 규칙 검증 (DB 불요).

대상은 순수 함수뿐이다 — 주소 키, 이름 관계, 신뢰도 분류, 합산 판정. 설계: docs/adr/014-*.md
"""

import tempfile
import unittest
from pathlib import Path

from batch.kapt.pnu_contention import names_related
from batch.trade.mapping_checks import AREA_MATCH_MIN_RATIO
from scripts.kapt_rental_swap_candidates import (
    DECISIONS_FILE,
    classify,
    load_decisions,
    lot_key,
    resolve_combine,
    road_key,
)


class LotKeyTest(unittest.TestCase):
    def test_extracts_region_and_main_lot(self):
        self.assertEqual(
            lot_key("서울특별시 중구 신당동 844 신당남산타운(분양)"),
            ("서울특별시 중구 신당동", "844"),
        )

    def test_sub_lot_is_ignored(self):
        # 혼합 단지의 임대동은 부번만 다른 필지에 있는 경우가 있다 (옥수삼성 250 / 250-5).
        sale = lot_key("서울특별시 성동구 옥수동 250 옥수삼성")
        rental = lot_key("서울특별시 성동구 옥수동 250-5 옥수삼성임대")
        self.assertEqual(sale, rental)

    def test_different_main_lot_does_not_match(self):
        self.assertNotEqual(
            lot_key("서울특별시 영등포구 당산동4가 91 유원제일"),
            lot_key("서울특별시 영등포구 당산동5가 7-2 유원제일2차"),
        )

    def test_address_without_lot_number(self):
        self.assertIsNone(lot_key("서울특별시 중구 신당동"))
        self.assertIsNone(lot_key(None))

    def test_leading_number_is_not_a_lot(self):
        # 첫 토큰이 숫자여도 지역 없이 본번으로 읽지 않는다.
        self.assertIsNone(lot_key("844"))


class RoadKeyTest(unittest.TestCase):
    def test_normalizes_whitespace(self):
        self.assertEqual(
            road_key("서울특별시  중구 다산로 32 "), "서울특별시 중구 다산로 32"
        )

    def test_empty_is_none(self):
        # None 끼리 같다고 짝지어지면 주소 없는 레코드가 전부 서로 묶인다.
        self.assertIsNone(road_key(""))
        self.assertIsNone(road_key(None))


class NamesRelatedTest(unittest.TestCase):
    def test_sale_and_rental_suffixes_are_ignored(self):
        self.assertTrue(names_related("신당남산타운(분양)", "신당남산타운임대"))
        self.assertTrue(names_related("구로두산", "구로두산제2"))

    def test_unrelated_names(self):
        self.assertFalse(names_related("연수승기마을", "연수1차시영임"))

    def test_neighbouring_complex_numbers_are_not_related(self):
        # 단지 번호는 걷어내지 않는다 — 1단지와 2단지는 다른 단지다.
        self.assertFalse(names_related("하남주공2단지", "하남주공1단지"))
        self.assertFalse(names_related("보라2단지", "보라1단지"))

    def test_same_complex_with_different_names_is_not_detected(self):
        # 이름 관계는 충분조건일 뿐이다 — 카카오맵으로 같은 단지임을 확인한 쌍이 거짓으로 나온다.
        # 그래서 거짓일 때 '다른 단지'로 단정하지 않고 combine_households=review 로 남긴다.
        self.assertFalse(names_related("돈암한신한진아파트", "동소문한진임대"))

    def test_empty_core_is_not_related(self):
        # 걷어내고 남는 게 없으면 포함 관계가 항상 참이 되므로 관계없음으로 본다.
        self.assertFalse(names_related("임대아파트", "신당남산타운"))
        self.assertFalse(names_related(None, "신당남산타운"))


class ClassifyTest(unittest.TestCase):
    def test_high_requires_name_area_evidence_and_single_candidate(self):
        self.assertEqual(classify(True, 1.0, 1, True), "HIGH")
        self.assertEqual(classify(True, AREA_MATCH_MIN_RATIO, 1, True), "HIGH")

    def test_medium_when_names_differ(self):
        # 주소·면적이 맞아도 이름이 다르면 이웃한 다른 단지다 (하남주공1단지 ↔ 하남주공2단지).
        # 교체하면 1단지 PNU 가 2단지가 되고 세대수가 두 단지의 합이 된다.
        self.assertEqual(classify(True, 1.0, 1, False), "MEDIUM")

    def test_medium_without_area_evidence(self):
        self.assertEqual(classify(True, None, 1, True), "MEDIUM")

    def test_medium_with_multiple_candidates(self):
        self.assertEqual(classify(True, 1.0, 2, True), "MEDIUM")

    def test_low_when_area_disagrees_even_if_single(self):
        # 주소가 같아도 실거래 면적이 분양 주택형과 어긋나면 다른 단지일 수 있다.
        self.assertEqual(classify(True, 0.0, 1, True), "LOW")
        self.assertEqual(classify(True, AREA_MATCH_MIN_RATIO - 0.01, 1, True), "LOW")

    def test_no_address_match(self):
        self.assertEqual(classify(False, 1.0, 1, True), "NONE")


class ResolveCombineTest(unittest.TestCase):
    def test_related_names_combine_automatically(self):
        self.assertEqual(resolve_combine(True, None), ("yes", "auto:name"))

    def test_unrelated_names_wait_for_a_decision(self):
        self.assertEqual(resolve_combine(False, None), ("review", ""))

    def test_decision_overrides_the_name_rule_both_ways(self):
        # 이름이 달라도 같은 단지(돈암한신한진 ↔ 동소문한진임대), 이름이 이어져도 사람이 막을 수 있다.
        self.assertEqual(resolve_combine(False, "yes"), ("yes", "decision"))
        self.assertEqual(resolve_combine(True, "no"), ("no", "decision"))


class LoadDecisionsTest(unittest.TestCase):
    def _write(self, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        self.addCleanup(Path(tmp.name).unlink)
        with tmp:
            tmp.write(body)
        return Path(tmp.name)

    def test_keyed_by_pnu_and_rental_code(self):
        path = self._write(
            "decisions:\n"
            "- {pnu: P1, rental_kapt_code: R1, combine_households: 'yes'}\n"
            "- {pnu: P2, rental_kapt_code: R2, combine_households: ' NO '}\n"
        )
        self.assertEqual(
            load_decisions(path), {("P1", "R1"): "yes", ("P2", "R2"): "no"}
        )

    def test_unquoted_yes_no_are_booleans_in_yaml(self):
        # 손으로 고치다 따옴표를 빼면 YAML 이 불리언으로 읽는다 — 같은 뜻으로 받는다.
        path = self._write(
            "decisions:\n"
            "- {pnu: P1, rental_kapt_code: R1, combine_households: yes}\n"
            "- {pnu: P2, rental_kapt_code: R2, combine_households: no}\n"
        )
        self.assertEqual(
            load_decisions(path), {("P1", "R1"): "yes", ("P2", "R2"): "no"}
        )

    def test_numeric_looking_pnu_is_kept_as_string(self):
        # PNU 는 19자리 숫자라 따옴표가 없으면 정수로 읽힌다 — 키는 문자열로 맞춘다.
        path = self._write(
            "decisions:\n"
            "- {pnu: 1114016200008440000, rental_kapt_code: A10045301, combine_households: 'yes'}\n"
        )
        self.assertEqual(
            load_decisions(path), {("1114016200008440000", "A10045301"): "yes"}
        )

    def test_missing_file_means_no_decisions(self):
        self.assertEqual(load_decisions(Path("/nonexistent/decisions.yaml")), {})

    def test_typo_aborts_instead_of_falling_back_to_review(self):
        # 오타가 조용히 review 로 떨어지면 판정을 내렸는데도 합산되지 않는다.
        path = self._write(
            "decisions:\n- {pnu: P1, rental_kapt_code: R1, combine_households: yess}\n"
        )
        with self.assertRaises(SystemExit):
            load_decisions(path)

    def test_tracked_decisions_file_is_valid(self):
        # 저장소의 판정 파일 자체가 읽히는지 — 손으로 고치는 파일이라 CI 에서 형식을 잡는다.
        decisions = load_decisions(DECISIONS_FILE)
        self.assertTrue(decisions)
        self.assertTrue(set(decisions.values()) <= {"yes", "no"})


if __name__ == "__main__":
    unittest.main()
