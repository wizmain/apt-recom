"""batch.region_codes 검증 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest

from batch.region_codes import (
    is_known_sigungu,
    load_aliases,
    normalize_pnu,
    normalize_sido_name,
    normalize_sigungu,
    normalize_sigungu_code,
)

# 2026-08 실측 사례를 픽스처로 쓴다.
ALIASES = {
    "sigungu": {
        "12300": "29170",  # 광주 북구 개명 (전남광주통합특별시)
        "2815510100": "28110",  # 인천 중구 일부 → 제물포구 (재편, 법정동별)
        "2815510400": "28140",  # 인천 동구 일부 → 제물포구
        "2827510100": "2826010300",  # 인천 서구 분할 (검단 재부여형, 2026-08 실측)
        "2827510200": "2826010400",  # 같은 신코드의 모든 항목이 28260 으로 접힌다
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


class TestNormalizeSigunguCode(unittest.TestCase):
    """법정동 문맥 없는 경계(거래 수집 sggCd) 전용 — 2026-08-29 실측 유형."""

    def test_개명형은_5자리_별칭으로_접는다(self):
        self.assertEqual(normalize_sigungu_code("12300", ALIASES), "29170")

    def test_분할형은_10자리_항목이_유일하게_접힐_때_그_값이다(self):
        """인천 28275 → 모든 10자리 항목이 28260 계열 — 코드만으로 결정된다."""
        self.assertEqual(normalize_sigungu_code("28275", ALIASES), "28260")

    def test_병합형은_갈리므로_바꾸지_않는다(self):
        """제물포구 유형 — 28155 의 10자리 항목이 28110/28140 으로 갈린다."""
        self.assertEqual(normalize_sigungu_code("28155", ALIASES), "28155")

    def test_모르는_코드와_빈_입력은_그대로다(self):
        self.assertEqual(normalize_sigungu_code("99999", ALIASES), "99999")
        self.assertEqual(normalize_sigungu_code("", ALIASES), "")


class TestNormalizePnu(unittest.TestCase):
    def test_신코드_pnu_의_앞자리만_치환한다(self):
        """법정동 이하는 개편 전후 보존된다 (실측 — 오치동 11500)."""
        self.assertEqual(
            normalize_pnu("1230011500009850001", ALIASES), "2917011500009850001"
        )

    def test_재편_pnu_는_법정동을_보고_푼다(self):
        self.assertEqual(
            normalize_pnu("2815510100001230000", ALIASES), "2811010100001230000"
        )

    def test_표준_pnu_는_건드리지_않는다(self):
        self.assertEqual(
            normalize_pnu("2917011500009850001", ALIASES), "2917011500009850001"
        )

    def test_형식이_아니면_그대로_돌려준다(self):
        self.assertEqual(normalize_pnu("TRADE_29170_x", ALIASES), "TRADE_29170_x")
        self.assertIsNone(normalize_pnu(None, ALIASES))


class TestSidoName(unittest.TestCase):
    def test_신_시도명을_표준으로_바꾼다(self):
        self.assertEqual(normalize_sido_name("전남광주통합특별시", ALIASES), "광주")

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
                return [
                    ("sigungu_alias", "12300", "29170"),
                    ("sido_alias", "전남광주통합특별시", "광주"),
                ]

        class _Conn:
            def cursor(self):
                return _Cur()

        a = load_aliases(_Conn())
        self.assertEqual(a["sigungu"]["12300"], "29170")
        self.assertEqual(a["sido"]["전남광주통합특별시"], "광주")


if __name__ == "__main__":
    unittest.main()


class TestAuditUnknownCodes(unittest.TestCase):
    """미등록 코드 감사 — 판정만 하고 데이터를 바꾸지 않는다."""

    class _Cur:
        def __init__(self, outer):
            self.outer = outer

        def execute(self, sql, params=None):
            self.outer.executed.append(sql)
            s = " ".join(sql.split())
            if "group_id = 'sigungu'" in s:
                # audit 의 레지스트리 조회
                self._rows = [("29170",), ("11110",)]
            elif "group_id IN" in s:
                # load_aliases — 그룹명은 파라미터로 넘어와 SQL 텍스트에 없다
                self._rows = [("sigungu_alias", "12300", "29170")]
            else:  # watch SQL
                self._rows = self.outer.watch_rows

        def fetchall(self):
            return self._rows

    class _Conn:
        def __init__(self, watch_rows):
            self.watch_rows = watch_rows
            self.executed: list[str] = []

        def cursor(self):
            return TestAuditUnknownCodes._Cur(self)

    class _Logger:
        def __init__(self):
            self.warnings, self.infos = [], []

        def warning(self, m):
            self.warnings.append(m)

        def info(self, m):
            self.infos.append(m)

    def test_전부_아는_코드면_경보하지_않는다(self):
        """레지스트리 코드와 별칭(신코드)은 정상이다."""
        from batch.region_codes import audit_unknown_codes

        log = self._Logger()
        conn = self._Conn(
            [("29170", "apartments.pnu"), ("12300", "trade_apt_mapping.sgg_cd")]
        )
        self.assertEqual(audit_unknown_codes(conn, log), [])
        self.assertEqual(log.warnings, [])

    def test_미지의_코드는_출처와_함께_경보한다(self):
        """다음 행정구역 개편의 첫 유입을 잡는 것이 목적이다."""
        from batch.region_codes import audit_unknown_codes

        log = self._Logger()
        conn = self._Conn([("13100", "apartments.pnu")])
        unknown = audit_unknown_codes(conn, log)
        self.assertEqual(unknown, [{"code": "13100", "source": "apartments.pnu"}])
        self.assertTrue(log.warnings)

    def test_데이터를_바꾸지_않는다(self):
        from batch.region_codes import audit_unknown_codes

        conn = self._Conn([("13100", "apartments.pnu")])
        audit_unknown_codes(conn, self._Logger())
        joined = " ".join(conn.executed).upper()
        for verb in ("UPDATE ", "DELETE ", "INSERT "):
            self.assertNotIn(verb, joined)


class TestReassignedBjdong(unittest.TestCase):
    """법정동 재부여형 재편 (인천, 2026-08 실측) — 10자리 → 10자리 별칭."""

    ALIASES = {
        "sigungu": {
            "2812513200": "2811012500",  # 제물포구 신법정동 → 중구 답동
            "2812510300": "2814010300",  # 제물포구 송현동 → 동구 (법정동 보존 동)
            "12300": "29170",  # 5자리 개명형 공존
        },
        "sido": {},
    }

    def test_재부여형은_앞_10자리를_통째로_바꾼다(self):
        """인천 중구 답동 로얄 실측 — 5자리 치환이면 엉뚱한 동이 된다."""
        self.assertEqual(
            normalize_pnu("2812513200000080001", self.ALIASES), "2811012500000080001"
        )

    def test_같은_신시군구라도_법정동별로_다른_구코드로_간다(self):
        self.assertEqual(
            normalize_pnu("2812510300001540000", self.ALIASES), "2814010300001540000"
        )

    def test_십자리_매핑이_없는_법정동은_바꾸지_않는다(self):
        """근거 없는 5자리 치환은 오변환 — 원본 유지가 안전하다."""
        self.assertEqual(
            normalize_pnu("2812599900000010000", self.ALIASES), "2812599900000010000"
        )

    def test_개명형과_공존한다(self):
        self.assertEqual(
            normalize_pnu("1230011500009850001", self.ALIASES), "2917011500009850001"
        )

    def test_normalize_sigungu_는_십자리_값에서_시군구를_뽑는다(self):
        self.assertEqual(
            normalize_sigungu("28125", self.ALIASES, bjdong="13200"), "28110"
        )


class TestCanonicalAddr(unittest.TestCase):
    """주소 매칭 키의 시도 토큰 접기 — 표시용이 아니라 매칭 전용."""

    ALIASES = {
        "sigungu": {},
        "sido": {
            "광주": "전남광주",
            "광주광역시": "전남광주",
            "전남": "전남광주",
            "전라남도": "전남광주",
            "전남광주통합특별시": "전남광주",
            "서울": "서울",
            "서울특별시": "서울",
            "강원특별자치도": "강원",
            "강원도": "강원",
            "강원": "강원",
        },
    }

    def test_구표기와_신표기가_같은_키로_접힌다(self):
        """DB "광주 …" vs Kakao "전남광주통합특별시 …" — [L2] 매칭의 전제."""
        from batch.region_codes import canonical_addr

        a = canonical_addr("광주 북구 오치동 985-1", self.ALIASES)
        b = canonical_addr("전남광주통합특별시 북구 오치동 985-1", self.ALIASES)
        self.assertEqual(a, b)
        self.assertEqual(a, "전남광주 북구 오치동 985-1")

    def test_전남_표기도_같은_토큰으로_접힌다(self):
        """통합시라 광주·전남 양쪽 표기가 한 토큰이어야 신표기와 매치된다."""
        from batch.region_codes import canonical_addr

        self.assertEqual(
            canonical_addr("전남 신안군 지도읍 읍내리 1702", self.ALIASES),
            canonical_addr(
                "전남광주통합특별시 신안군 지도읍 읍내리 1702", self.ALIASES
            ),
        )

    def test_정식명과_축약이_같은_키다(self):
        from batch.region_codes import canonical_addr

        self.assertEqual(
            canonical_addr("서울특별시 종로구 청운동 1", self.ALIASES),
            canonical_addr("서울 종로구 청운동 1", self.ALIASES),
        )

    def test_모르는_시도_표기는_원문_유지다(self):
        from batch.region_codes import canonical_addr

        self.assertEqual(
            canonical_addr("미지의시 어딘가 1", self.ALIASES), "미지의시 어딘가 1"
        )

    def test_빈_입력은_그대로다(self):
        from batch.region_codes import canonical_addr

        self.assertEqual(canonical_addr("", self.ALIASES), "")
