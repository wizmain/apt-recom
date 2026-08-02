"""batch.trade.registry 검증 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest

from batch.trade.registry import (
    API_ERROR,
    EMPTY,
    OK,
    PARSE_ERROR,
    QUOTA,
    RETRYABLE,
    parse_registry_response,
)


def _envelope(body: str, code: str = "00", msg: str = "NORMAL SERVICE.") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>{code}</resultCode><resultMsg>{msg}</resultMsg></header>
<body>{body}</body></response>"""


_ITEM = """<items><item>
  <hhldCnt>98</hhldCnt><dongNm>101동</dongNm>
  <grndFlrCnt>10</grndFlrCnt><useAprDay>20111230</useAprDay>
</item></items>"""


class TestStatusClassification(unittest.TestCase):
    def test_정상_응답은_ok_다(self):
        r = parse_registry_response(_envelope(_ITEM))
        self.assertEqual(r.status, OK)
        self.assertEqual(r.info["total_hhld_cnt"], 98)
        self.assertEqual(r.info["max_floor"], 10)
        self.assertEqual(r.info["use_apr_day"], "20111230")

    def test_item_없으면_empty_다(self):
        """이것만이 확정적 '해당 지번에 건물 없음'이다."""
        r = parse_registry_response(_envelope("<items></items>"))
        self.assertEqual(r.status, EMPTY)
        self.assertEqual(r.info, {})

    def test_쿼터_초과는_코드로_구분한다(self):
        r = parse_registry_response(_envelope(
            "", code="22", msg="LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"))
        self.assertEqual(r.status, QUOTA)

    def test_쿼터_초과는_메시지로도_구분한다(self):
        """코드 체계가 달라도 메시지로 잡는다."""
        r = parse_registry_response(_envelope(
            "", code="99", msg="LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"))
        self.assertEqual(r.status, QUOTA)

    def test_그_밖의_에러코드는_api_error_다(self):
        r = parse_registry_response(_envelope(
            "", code="30", msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
        self.assertEqual(r.status, API_ERROR)
        self.assertIn("30", r.detail)

    def test_깨진_xml_은_parse_error_다(self):
        self.assertEqual(parse_registry_response("<broken").status, PARSE_ERROR)
        self.assertEqual(parse_registry_response("").status, PARSE_ERROR)

    def test_empty_만_재시도_대상이_아니다(self):
        """리하우스(LEEHAUS) 누락의 핵심 — 쿼터 소진을 '건물 없음'으로 기록하면
        재시도 대상에서 영구히 빠진다."""
        self.assertNotIn(EMPTY, RETRYABLE)
        for s in (QUOTA, API_ERROR, PARSE_ERROR):
            self.assertIn(s, RETRYABLE)


class TestSummarize(unittest.TestCase):
    def test_여러_동의_세대수를_합산한다(self):
        body = """<items>
          <item><hhldCnt>50</hhldCnt><dongNm>101동</dongNm><grndFlrCnt>15</grndFlrCnt>
                <useAprDay>20100101</useAprDay></item>
          <item><hhldCnt>70</hhldCnt><dongNm>102동</dongNm><grndFlrCnt>20</grndFlrCnt>
                <useAprDay>20120101</useAprDay></item>
        </items>"""
        info = parse_registry_response(_envelope(body)).info
        self.assertEqual(info["total_hhld_cnt"], 120)
        self.assertEqual(info["dong_count"], 2)
        self.assertEqual(info["max_floor"], 20)

    def test_준공일은_가장_이른_값이다(self):
        """증축 동이 섞여도 단지 준공 시점을 잡는다."""
        body = """<items>
          <item><useAprDay>20120101</useAprDay></item>
          <item><useAprDay>20100101</useAprDay></item>
        </items>"""
        self.assertEqual(
            parse_registry_response(_envelope(body)).info["use_apr_day"], "20100101")

    def test_값이_없으면_None_이다(self):
        info = parse_registry_response(_envelope("<items><item/></items>")).info
        self.assertIsNone(info["total_hhld_cnt"])
        self.assertIsNone(info["max_floor"])
        self.assertIsNone(info["use_apr_day"])

    def test_숫자가_아닌_값은_무시한다(self):
        body = "<items><item><hhldCnt>미상</hhldCnt><grndFlrCnt>-</grndFlrCnt></item></items>"
        info = parse_registry_response(_envelope(body)).info
        self.assertIsNone(info["total_hhld_cnt"])
        self.assertIsNone(info["max_floor"])


if __name__ == "__main__":
    unittest.main()


class TestBuildingName(unittest.TestCase):
    """건물명 — 거래 기반 회수 경로에서 POI 이름을 신뢰할 수 없어 여기서 얻는다."""

    def test_세대수가_많은_동의_이름을_고른다(self):
        """표제부에는 관리동·상가동이 섞여 있다."""
        body = """<items>
          <item><bldNm>관리동</bldNm><hhldCnt>0</hhldCnt></item>
          <item><bldNm>대연 SK VIEW Hills</bldNm><hhldCnt>180</hhldCnt></item>
        </items>"""
        self.assertEqual(
            parse_registry_response(_envelope(body)).info["bld_nm"],
            "대연 SK VIEW Hills")

    def test_공백만_든_이름은_무시한다(self):
        body = """<items>
          <item><bldNm> </bldNm><hhldCnt>10</hhldCnt></item>
          <item><bldNm>수성아파트</bldNm><hhldCnt>60</hhldCnt></item>
        </items>"""
        self.assertEqual(
            parse_registry_response(_envelope(body)).info["bld_nm"], "수성아파트")

    def test_같은_이름의_여러_동은_합산된다(self):
        body = """<items>
          <item><bldNm>월드파크</bldNm><hhldCnt>30</hhldCnt></item>
          <item><bldNm>월드파크</bldNm><hhldCnt>66</hhldCnt></item>
          <item><bldNm>상가</bldNm><hhldCnt>80</hhldCnt></item>
        </items>"""
        self.assertEqual(
            parse_registry_response(_envelope(body)).info["bld_nm"], "월드파크")

    def test_이름이_없으면_None_이다(self):
        self.assertIsNone(
            parse_registry_response(_envelope("<items><item/></items>")).info["bld_nm"])


class TestPnuToBldParams(unittest.TestCase):
    def test_표준_pnu_를_조회_파라미터로_분해한다(self):
        from batch.trade.registry import pnu_to_bld_params
        p = pnu_to_bld_params("2917011500009850001")
        self.assertEqual(p, {"sigungu_cd": "29170", "bjdong_cd": "11500",
                             "plat_gb_cd": "0", "bun": "0985", "ji": "0001"})
