"""batch.region_codes 검증 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest

from batch.region_codes import (
    is_known_sigungu,
    load_aliases,
    normalize_pnu,
    normalize_sido_name,
    normalize_sigungu,
)

# 2026-08 실측 사례를 픽스처로 쓴다.
ALIASES = {
    "sigungu": {
        "12300": "29170",        # 광주 북구 개명 (전남광주통합특별시)
        "2815510100": "28110",   # 인천 중구 일부 → 제물포구 (재편, 법정동별)
        "2815510400": "28140",   # 인천 동구 일부 → 제물포구
    },
    "sido": {"전남광주통합특별시": "광주"},
}


class TestNormalizeSigungu(unittest.TestCase):
    def test_개명된_신코드를_구코드로_바꾼다(self):
        self.assertEqual(normalize_sigungu("12300", ALIASES), "29170")

    def test_모르는_코드는_그대로_둔다(self):
        """이미 표준이거나 미지의 코드 — 조용히 바꾸면 안 된다."""
        self.assertEqual(normalize_sigungu("29170", ALIASES), "29170")
        self.assertEqual(normalize_sigungu("99999", ALIASES), "99999")

    def test_재편은_법정동으로_구코드가_갈린다(self):
        """제물포구 유형 — 같은 신코드라도 법정동에 따라 원 소속이 다르다."""
        self.assertEqual(normalize_sigungu("28155", ALIASES, bjdong="10100"), "28110")
        self.assertEqual(normalize_sigungu("28155", ALIASES, bjdong="10400"), "28140")

    def test_재편인데_법정동이_없으면_바꾸지_않는다(self):
        """근거 없이 절반 확률로 찍는 것보다 원본 유지가 안전하다."""
        self.assertEqual(normalize_sigungu("28155", ALIASES), "28155")

    def test_빈_입력은_그대로다(self):
        self.assertEqual(normalize_sigungu("", ALIASES), "")


class TestNormalizePnu(unittest.TestCase):
    def test_신코드_pnu_의_앞자리만_치환한다(self):
        """법정동 이하는 개편 전후 보존된다 (실측 — 오치동 11500)."""
        self.assertEqual(
            normalize_pnu("1230011500009850001", ALIASES),
            "2917011500009850001")

    def test_재편_pnu_는_법정동을_보고_푼다(self):
        self.assertEqual(
            normalize_pnu("2815510100001230000", ALIASES),
            "2811010100001230000")

    def test_표준_pnu_는_건드리지_않는다(self):
        self.assertEqual(
            normalize_pnu("2917011500009850001", ALIASES),
            "2917011500009850001")

    def test_형식이_아니면_그대로_돌려준다(self):
        self.assertEqual(normalize_pnu("TRADE_29170_x", ALIASES), "TRADE_29170_x")
        self.assertIsNone(normalize_pnu(None, ALIASES))


class TestSidoName(unittest.TestCase):
    def test_신_시도명을_표준으로_바꾼다(self):
        self.assertEqual(
            normalize_sido_name("전남광주통합특별시", ALIASES), "광주")

    def test_모르는_명칭은_그대로다(self):
        self.assertEqual(normalize_sido_name("서울", ALIASES), "서울")


class TestKnownSigungu(unittest.TestCase):
    def test_레지스트리나_별칭에_있으면_안다(self):
        registry = {"29170"}
        self.assertTrue(is_known_sigungu("29170", registry, ALIASES))
        self.assertTrue(is_known_sigungu("12300", registry, ALIASES))

    def test_둘_다_없으면_모른다(self):
        """다음 행정구역 개편의 감지 신호 — 배치 감사가 이 결과로 경보한다."""
        self.assertFalse(is_known_sigungu("13100", {"29170"}, ALIASES))


class TestLoadAliases(unittest.TestCase):
    def test_그룹별로_나눠_적재한다(self):
        class _Cur:
            def execute(self, sql, params=None): ...
            def fetchall(self):
                return [("sigungu_alias", "12300", "29170"),
                        ("sido_alias", "전남광주통합특별시", "광주")]
        class _Conn:
            def cursor(self):
                return _Cur()
        a = load_aliases(_Conn())
        self.assertEqual(a["sigungu"]["12300"], "29170")
        self.assertEqual(a["sido"]["전남광주통합특별시"], "광주")


if __name__ == "__main__":
    unittest.main()
