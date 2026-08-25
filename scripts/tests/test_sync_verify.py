"""batch.sync_from_railway 검증 로직 — DB·네트워크 없이 순수 함수만 확인 (CI 대상)."""

import unittest

from batch.sync_from_railway import (
    APT_SYNC_TABLES,
    CHECKSUM_COLS,
    build_checksum_sql,
    find_stale_pks,
    verify_status,
)


class TestVerifyStatus(unittest.TestCase):
    """행 수만 보면 재매핑 같은 값 변화를 놓친다 (2026-08-22 실측)."""

    def test_카운트와_체크섬이_같으면_OK(self):
        self.assertEqual(verify_status(100, 100, 7, 7), "OK")

    def test_카운트가_같아도_값이_다르면_드러난다(self):
        """653건 교정 후 로컬·Railway 가 44,718행으로 같은데 pnu 는 23건 달랐다."""
        self.assertEqual(verify_status(44718, 44718, 7, 8), "값 불일치")

    def test_체크섬_대상이_아니면_카운트만_본다(self):
        self.assertEqual(verify_status(100, 100, None, None), "OK")

    def test_카운트_차이는_방향을_표시한다(self):
        self.assertEqual(verify_status(105, 100, 7, 7), "로컬 추가 +5")
        self.assertEqual(verify_status(95, 100, 7, 7), "부족 -5")

    def test_카운트_차이가_체크섬보다_우선한다(self):
        """행 수가 다르면 체크섬은 당연히 달라 — 더 구체적인 정보를 보여준다."""
        self.assertEqual(verify_status(105, 100, 7, 8), "로컬 추가 +5")


class TestChecksumSql(unittest.TestCase):
    def test_대상_테이블은_SQL_을_만든다(self):
        sql = build_checksum_sql("trade_apt_mapping")
        self.assertIn("md5(", sql)
        self.assertIn("FROM trade_apt_mapping", sql)
        for col in ("apt_seq", "pnu", "match_method"):
            self.assertIn(col, sql)

    def test_대상이_아니면_None(self):
        self.assertIsNone(build_checksum_sql("common_code"))

    def test_NULL_은_자리표시자로_대체된다(self):
        """COALESCE 없이 || 하면 컬럼 하나가 NULL 일 때 전체가 NULL 이 된다."""
        self.assertIn("COALESCE", build_checksum_sql("apartments"))


class TestSyncModes(unittest.TestCase):
    def test_재매핑되는_테이블은_upsert(self):
        """trade_apt_mapping.pnu 는 rematch 도구·배치가 바꾸므로 값 갱신이 필요하다."""
        cfg = next(c for c in APT_SYNC_TABLES if c["name"] == "trade_apt_mapping")
        self.assertEqual(cfg["mode"], "upsert")

    def test_체크섬_컬럼은_실제_동기화_컬럼의_부분집합(self):
        """존재하지 않는 컬럼을 넣으면 동기화 검증 단계에서 터진다."""
        by_name = {c["name"]: set(c["cols"]) for c in APT_SYNC_TABLES}
        for table, cols in CHECKSUM_COLS.items():
            if table in by_name:
                self.assertTrue(
                    set(cols) <= by_name[table],
                    f"{table}: {set(cols) - by_name[table]} 가 동기화 대상 컬럼에 없다",
                )


if __name__ == "__main__":
    unittest.main()


class TestFindStalePks(unittest.TestCase):
    """upsert 미러링의 삭제 전파 — 2026-08-25 실측(잔존 23건)에서 도출."""

    COLS = ["pnu", "price_per_m2"]
    PK = ["pnu"]

    def test_Railway_에_없는_로컬_PK_만_잔존이다(self):
        railway = [("A", 1.0), ("B", 2.0)]
        local = [("A",), ("B",), ("C",)]
        self.assertEqual(find_stale_pks(self.COLS, self.PK, railway, local), [("C",)])

    def test_양쪽이_같으면_잔존_없음(self):
        railway = [("A", 1.0)]
        self.assertEqual(find_stale_pks(self.COLS, self.PK, railway, [("A",)]), [])

    def test_복합_PK_도_지원한다(self):
        cols = ["pnu", "facility_subtype", "score"]
        pk = ["pnu", "facility_subtype"]
        railway = [("A", "mart", 1.0)]
        local = [("A", "mart"), ("A", "subway")]
        self.assertEqual(find_stale_pks(cols, pk, railway, local), [("A", "subway")])

    def test_로컬이_비어_있으면_잔존_없음(self):
        self.assertEqual(find_stale_pks(self.COLS, self.PK, [("A", 1.0)], []), [])
