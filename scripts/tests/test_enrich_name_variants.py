"""batch.trade.name_matching 의 이름 변형 생성 테스트.

DB·네트워크 없이 순수 함수만 검증한다 (CI 대상).
enrich_apartments 를 직접 import 하면 batch.db → psycopg2 까지 끌려와
DB 드라이버가 없는 CI 에서 ImportError 가 난다. 규칙만 담은 모듈을 쓴다.
"""

import unittest

from batch.trade.name_matching import (
    _MIN_ALIAS_LEN,
    _name_variants,
    _names_overlap,
    _normalize_name,
)


class TestNameVariants(unittest.TestCase):
    def test_괄호_없으면_원본만_반환한다(self):
        """기존 동작 유지 — Kakao 호출 수가 늘지 않아야 한다."""
        self.assertEqual(_name_variants("산울마을6단지"), ["산울마을6단지"])

    def test_괄호_별칭형은_본명과_별칭을_모두_생성한다(self):
        self.assertEqual(
            _name_variants("세종리첸시아파밀리에H3블록(산울마을6단지)"),
            [
                "세종리첸시아파밀리에H3블록(산울마을6단지)",
                "세종리첸시아파밀리에H3블록",
                "산울마을6단지",
            ],
        )

    def test_원본이_항상_첫_번째다(self):
        """원본 완전일치가 가장 신뢰도 높은 매칭이므로 우선순위 1위여야 한다."""
        for name in ["시영2차(우산빛여울채)", "가락마을9단지(신동아 파밀리에)", "평범한아파트"]:
            self.assertEqual(_name_variants(name)[0], name)

    def test_짧은_괄호조각은_별칭_후보에서_제외된다(self):
        """`(임대)` 같은 조각으로 진본을 찾으면 오매칭 위험이 크다."""
        variants = _name_variants("금호대우(임대)")
        self.assertEqual(variants, ["금호대우(임대)", "금호대우"])
        self.assertNotIn("임대", variants)

    def test_블록코드_괄호도_길이기준을_넘으면_후보가_된다(self):
        """길이만으로는 별칭과 블록코드를 못 가른다 — 타임라인 가드가 방어한다."""
        self.assertIn("CB5-3BL", _name_variants("세종마루(CB5-3BL)"))

    def test_괄호가_여러개면_모두_후보가_된다(self):
        variants = _name_variants("금호벽산(임대)(미공시)")
        self.assertEqual(variants[0], "금호벽산(임대)(미공시)")
        self.assertIn("금호벽산", variants)
        self.assertIn("미공시", variants)

    def test_중복_변형은_한_번만_나온다(self):
        """괄호 제거본이 원본과 같으면 중복 호출이 생기지 않아야 한다."""
        self.assertEqual(len(_name_variants("산울마을6단지")), 1)

    def test_전체가_괄호면_빈_본명을_내지_않는다(self):
        variants = _name_variants("(산울마을6단지)")
        self.assertNotIn("", variants)
        self.assertIn("산울마을6단지", variants)

    def test_빈_입력은_빈_목록이다(self):
        self.assertEqual(_name_variants(""), [])
        self.assertEqual(_name_variants(None), [])

    def test_최소_별칭_길이_상수가_유효하다(self):
        self.assertGreaterEqual(_MIN_ALIAS_LEN, 2)


class TestVariantsMatchCanonicalNames(unittest.TestCase):
    """실제로 유령을 만들었던 거래명이 진본 이름과 이어지는지 확인."""

    # 전부 TRADE_ 유령 레코드를 만들었다가 수동 재매핑한 실제 사례
    CASES = [
        ("세종리첸시아파밀리에H3블록(산울마을6단지)", "산울마을6단지"),
        ("세종리첸시아파밀리에H2블록(산울마을7단지)", "산울마을7단지"),
        ("부영애시앙1차(산정셀트리움)", "산정 셀트리움"),
        ("시영2차(우산빛여울채)", "우산빛여울채"),
    ]

    def test_변형중_하나가_진본이름과_정규화_일치한다(self):
        for trade_nm, canonical_nm in self.CASES:
            normalized = {_normalize_name(v) for v in _name_variants(trade_nm)}
            self.assertIn(
                _normalize_name(canonical_nm), normalized,
                f"{trade_nm} → {canonical_nm} 매칭 실패",
            )

    def test_이름_유사도_가드는_별칭_포함관계를_이미_통과시킨다(self):
        """_names_overlap 은 수정 대상이 아님을 고정한다."""
        self.assertTrue(
            _names_overlap("세종리첸시아파밀리에H3블록(산울마을6단지)", "산울마을6단지")
        )

    def test_다른_단지끼리는_유사도_가드에_걸린다(self):
        self.assertFalse(_names_overlap("부영애시앙1차", "산정 셀트리움"))

    def test_진본에_접미사가_붙으면_인덱스_매칭은_안_된다(self):
        """알려진 한계 — 변형은 거래명만 다루므로 진본 쪽 접미사는 흡수하지 못한다.

        예: 거래명 `산울마을2단지(세종자이더시티)` vs 진본 `산울마을2단지(세종자이 더 시티 아파트)`.
        이 조합은 K-APT 이름 인덱스(정규화 완전일치)로는 이어지지 않고 Kakao 검색
        경로로 매칭된다. 인덱스 매칭까지 넓히려면 접미사 정규화가 별도로 필요하다.
        """
        normalized = {_normalize_name(v) for v in _name_variants("산울마을2단지(세종자이더시티)")}
        self.assertNotIn(_normalize_name("산울마을2단지(세종자이 더 시티 아파트)"), normalized)
        # 다만 이름 유사도 가드는 통과하므로 Kakao 경로에서 거부되지는 않는다
        self.assertTrue(
            _names_overlap("산울마을2단지(세종자이더시티)", "산울마을2단지(세종자이 더 시티 아파트)")
        )


if __name__ == "__main__":
    unittest.main()
