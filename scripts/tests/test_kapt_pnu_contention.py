"""K-APT 분양·임대 PNU 경합 규칙과 레코드 이동 연산 검증 (ADR-014, DB 불요).

DB 연산은 가짜 커서로 본다 — 확인하는 것은 SQL 의 결과가 아니라 **거부 조건과 이동 순서**다.
순서가 틀리면 PK 충돌이 나거나(분양을 먼저 옮김) 임대 행이 덮인다.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from batch.kapt.companion_records import (
    KAPT_KEYED_TABLES,
    CompanionRecordError,
    evict_to_dummy,
    swap_records,
)
from batch.kapt.pnu_contention import (
    KEEP_EXISTING,
    REPLACE,
    dummy_pnu,
    is_dummy_pnu,
    resolve_contention,
)
from scripts.swap_kapt_sale_rental import load_targets

REAL_PNU = "1114016200008440000"
SALE_CODE = "A10045302"
RENTAL_CODE = "A10045301"


class ResolveContentionTest(unittest.TestCase):
    def test_sale_or_mixed_replaces_rental(self):
        self.assertEqual(resolve_contention("임대", "분양"), REPLACE)
        self.assertEqual(resolve_contention("임대", "혼합"), REPLACE)

    def test_rental_never_replaces(self):
        self.assertEqual(resolve_contention("분양", "임대"), KEEP_EXISTING)
        self.assertEqual(resolve_contention("혼합", "임대"), KEEP_EXISTING)
        self.assertEqual(resolve_contention("임대", "임대"), KEEP_EXISTING)

    def test_same_rank_keeps_existing(self):
        # 분양끼리·분양과 혼합은 근거 없이 뒤집지 않는다 — 매 적재마다 자리가 바뀌면 안 된다.
        self.assertEqual(resolve_contention("분양", "분양"), KEEP_EXISTING)
        self.assertEqual(resolve_contention("분양", "혼합"), KEEP_EXISTING)

    def test_unknown_sale_type_neither_replaces_nor_is_replaced(self):
        for unknown in (None, "", "사택 및 관사 등"):
            with self.subTest(unknown=unknown):
                self.assertEqual(resolve_contention(unknown, "분양"), KEEP_EXISTING)
                self.assertEqual(resolve_contention("임대", unknown), KEEP_EXISTING)

    def test_whitespace_is_ignored(self):
        self.assertEqual(resolve_contention(" 임대 ", "분양 "), REPLACE)


class DummyPnuTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(dummy_pnu(SALE_CODE), "KAPT_A10045302")
        self.assertTrue(is_dummy_pnu(dummy_pnu(SALE_CODE)))

    def test_real_and_empty_are_not_dummy(self):
        self.assertFalse(is_dummy_pnu(REAL_PNU))
        self.assertFalse(is_dummy_pnu(None))
        self.assertFalse(is_dummy_pnu(""))


class FakeCursor:
    """SELECT 에는 준비된 값을 돌려주고, 실행된 문장을 순서대로 기록한다."""

    def __init__(self, kapt_code_at: dict[str, str], occupied: set[str] = frozenset()):
        self.kapt_code_at = kapt_code_at
        self.occupied = set(occupied)
        self.statements: list[tuple[str, list]] = []
        self.rowcount = 1
        self._result = None

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        params = list(params or [])
        self.statements.append((sql, params))
        if sql.startswith("SELECT kapt_code FROM apt_kapt_info"):
            code = self.kapt_code_at.get(params[0])
            self._result = (code,) if code else None
        elif sql.startswith("SELECT 1 FROM"):
            self._result = (1,) if params[0] in self.occupied else None
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def moves(self) -> list[tuple[str, str, str]]:
        """(테이블, from, to) — `UPDATE t SET pnu = %s WHERE pnu = %s` 만 추린다."""
        out = []
        for sql, params in self.statements:
            if sql.startswith("UPDATE") and "SET pnu = %s WHERE pnu = %s" in sql:
                out.append((sql.split()[1], params[1], params[0]))
        return out


class EvictToDummyTest(unittest.TestCase):
    def test_moves_every_kapt_keyed_table_and_marks_parent(self):
        cur = FakeCursor({REAL_PNU: RENTAL_CODE})
        evict_to_dummy(cur, REAL_PNU, RENTAL_CODE, link_as_companion=True)

        self.assertEqual(
            cur.moves(),
            [(t, REAL_PNU, dummy_pnu(RENTAL_CODE)) for t in KAPT_KEYED_TABLES],
        )
        parent_sql, parent_params = cur.statements[-1]
        self.assertIn("SET parent_pnu = %s", parent_sql)
        self.assertEqual(parent_params, [REAL_PNU, dummy_pnu(RENTAL_CODE)])

    def test_without_link_the_record_moves_but_is_not_a_companion(self):
        # 자리를 내주는 레코드가 이웃한 다른 단지일 수 있다 (군자주공14단지 ↔ 안산군자13단지).
        # 연결하면 두 단지의 세대수가 합쳐지므로 parent_pnu 를 비워 합산에서 뺀다.
        cur = FakeCursor({REAL_PNU: RENTAL_CODE})
        evict_to_dummy(cur, REAL_PNU, RENTAL_CODE, link_as_companion=False)

        self.assertEqual(len(cur.moves()), len(KAPT_KEYED_TABLES))
        _, parent_params = cur.statements[-1]
        self.assertEqual(parent_params, [None, dummy_pnu(RENTAL_CODE)])

    def test_rejects_when_pnu_holds_a_different_record(self):
        # 검수 목록을 만든 뒤 DB 가 바뀐 경우 — 엉뚱한 레코드를 밀어내면 안 된다.
        cur = FakeCursor({REAL_PNU: "A99999999"})
        with self.assertRaises(CompanionRecordError):
            evict_to_dummy(cur, REAL_PNU, RENTAL_CODE, link_as_companion=True)
        self.assertEqual(cur.moves(), [])

    def test_rejects_when_dummy_key_is_occupied(self):
        cur = FakeCursor({REAL_PNU: RENTAL_CODE}, occupied={dummy_pnu(RENTAL_CODE)})
        with self.assertRaises(CompanionRecordError):
            evict_to_dummy(cur, REAL_PNU, RENTAL_CODE, link_as_companion=True)
        self.assertEqual(cur.moves(), [])

    def test_rejects_dummy_as_real_pnu(self):
        cur = FakeCursor({})
        with self.assertRaises(CompanionRecordError):
            evict_to_dummy(
                cur, dummy_pnu(RENTAL_CODE), RENTAL_CODE, link_as_companion=True
            )


class SwapRecordsTest(unittest.TestCase):
    def test_evicts_before_moving_in(self):
        # 분양을 먼저 옮기면 실제 PNU 의 PK 와 충돌한다 — 반드시 임대를 먼저 뺀다.
        cur = FakeCursor({REAL_PNU: RENTAL_CODE, dummy_pnu(SALE_CODE): SALE_CODE})
        swap_records(
            cur,
            REAL_PNU,
            incoming_kapt_code=SALE_CODE,
            outgoing_kapt_code=RENTAL_CODE,
            link_as_companion=True,
        )

        n = len(KAPT_KEYED_TABLES)
        moves = cur.moves()
        self.assertEqual(
            moves[:n],
            [(t, REAL_PNU, dummy_pnu(RENTAL_CODE)) for t in KAPT_KEYED_TABLES],
        )
        self.assertEqual(
            moves[n:], [(t, dummy_pnu(SALE_CODE), REAL_PNU) for t in KAPT_KEYED_TABLES]
        )

    def test_rejects_when_incoming_is_not_at_its_dummy(self):
        cur = FakeCursor({REAL_PNU: RENTAL_CODE})
        with self.assertRaises(CompanionRecordError):
            swap_records(
                cur,
                REAL_PNU,
                incoming_kapt_code=SALE_CODE,
                outgoing_kapt_code=RENTAL_CODE,
                link_as_companion=True,
            )
        self.assertEqual(cur.moves(), [])


class LoadTargetsTest(unittest.TestCase):
    def _write(self, rows, fieldnames=None):
        fieldnames = fieldnames or [
            "confidence",
            "pnu",
            "sale_kapt_code",
            "rental_kapt_code",
            "combine_households",
        ]
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8-sig", newline=""
        )
        self.addCleanup(Path(tmp.name).unlink)
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return Path(tmp.name)

    def test_only_high_confidence(self):
        path = self._write(
            [
                {
                    "confidence": "HIGH",
                    "pnu": "P1",
                    "sale_kapt_code": "S1",
                    "rental_kapt_code": "R1",
                    "combine_households": "yes",
                },
                {
                    "confidence": "MEDIUM",
                    "pnu": "P2",
                    "sale_kapt_code": "S2",
                    "rental_kapt_code": "R2",
                    "combine_households": "yes",
                },
                {
                    "confidence": "LOW",
                    "pnu": "P3",
                    "sale_kapt_code": "S3",
                    "rental_kapt_code": "R3",
                    "combine_households": "yes",
                },
            ]
        )
        self.assertEqual([t["pnu"] for t in load_targets(path)], ["P1"])

    def test_ambiguous_pnu_is_dropped(self):
        # 손으로 승격하다 한 PNU 에 HIGH 가 둘이 되면 어느 쪽을 붙일지 알 수 없다.
        path = self._write(
            [
                {
                    "confidence": "HIGH",
                    "pnu": "P1",
                    "sale_kapt_code": "S1",
                    "rental_kapt_code": "R1",
                    "combine_households": "yes",
                },
                {
                    "confidence": "HIGH",
                    "pnu": "P1",
                    "sale_kapt_code": "S9",
                    "rental_kapt_code": "R1",
                    "combine_households": "yes",
                },
                {
                    "confidence": "HIGH",
                    "pnu": "P2",
                    "sale_kapt_code": "S2",
                    "rental_kapt_code": "R2",
                    "combine_households": "yes",
                },
            ]
        )
        self.assertEqual([t["pnu"] for t in load_targets(path)], ["P2"])

    def test_missing_columns_abort(self):
        path = self._write(
            [{"confidence": "HIGH", "pnu": "P1"}], fieldnames=["confidence", "pnu"]
        )
        with self.assertRaises(SystemExit):
            load_targets(path)


if __name__ == "__main__":
    unittest.main()
