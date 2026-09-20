"""K-APT 2026-09 관리비 합계 열 이름 변경 회귀 검증.

별칭 해소(`resolve_cost_column_aliases`) 단위 테스트와, 로더·검증기가 옛/새 열 이름을
모두 받아들이는지 보는 통합 테스트로 나뉜다. 엑셀 읽기·DB 는 전부 patch 된다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from batch.kapt import collect_mgmt_cost as loader
from batch.kapt.cost_columns import (
    COMMON_COST_TOTAL_COLUMN,
    COST_COLUMN_ALIASES,
    resolve_cost_column_aliases,
)
from batch.kapt.validate_kapt_files import _summarize

NEW_TOTAL_COLUMN = "공용관리비(합계)"
TOTAL_COLUMN_VARIANTS = [COMMON_COST_TOTAL_COLUMN, NEW_TOTAL_COLUMN]


class ResolveCostColumnAliasesTest(unittest.TestCase):
    def test_new_name_is_registered_as_alias(self):
        self.assertIn(NEW_TOTAL_COLUMN, COST_COLUMN_ALIASES[COMMON_COST_TOTAL_COLUMN])

    def test_alias_maps_to_canonical_when_canonical_missing(self):
        renames = resolve_cost_column_aliases(["단지코드", NEW_TOTAL_COLUMN])
        self.assertEqual(renames, {NEW_TOTAL_COLUMN: COMMON_COST_TOTAL_COLUMN})

    def test_no_rename_when_canonical_present(self):
        self.assertEqual(
            resolve_cost_column_aliases(["단지코드", COMMON_COST_TOTAL_COLUMN]), {}
        )

    def test_canonical_wins_when_both_present(self):
        # 둘 다 있으면 rename 이 정식 열을 덮어쓰면 안 된다.
        columns = [COMMON_COST_TOTAL_COLUMN, NEW_TOTAL_COLUMN]
        self.assertEqual(resolve_cost_column_aliases(columns), {})

    def test_no_rename_when_neither_present(self):
        # 둘 다 없으면 조용히 넘어가고, 누락은 검증기의 필수 컬럼 검사가 잡는다.
        self.assertEqual(resolve_cost_column_aliases(["단지코드"]), {})


class CostColumnsIntegrationTest(unittest.TestCase):
    def frame(self, total_column):
        row = dict.fromkeys(
            loader.COMMON_COLS
            + loader.INDIV_COLS
            + loader.ETC_COLS
            + loader.REPAIR_COLS,
            0,
        )
        row.update(
            {
                "단지코드": "A1",
                "단지명": "테스트",
                "발생년월(YYYYMM)": 202607,
                total_column: 100000,
                "개별사용료계": 20000,
                "인건비": 10000,
            }
        )
        return pd.DataFrame([row])

    def test_validator_accepts_old_and_new_total_column(self):
        for column in TOTAL_COLUMN_VARIANTS:
            with self.subTest(column=column), tempfile.NamedTemporaryFile() as file:
                with patch("pandas.read_excel", return_value=self.frame(column)):
                    summary, _, _ = _summarize("cost", Path(file.name), {"A1"}, {"A1"})
                self.assertEqual(summary.missing_columns, [])

    def test_loader_preserves_reported_total_above_partial_details(self):
        for column in TOTAL_COLUMN_VARIANTS:
            with self.subTest(column=column), tempfile.NamedTemporaryFile() as file:
                area = pd.DataFrame(
                    [
                        {
                            "단지코드": "A1",
                            "관리비부과면적": 1000,
                            "주거전용면적(단지합계)": 800,
                            "세대수": 10,
                        }
                    ]
                )
                cursor = MagicMock()
                with (
                    patch("pandas.read_excel", side_effect=[self.frame(column), area]),
                    patch.object(loader, "_db_url", return_value="unused"),
                    patch.object(loader.psycopg2, "connect"),
                    patch.object(loader, "get_dict_cursor", return_value=cursor),
                    patch.object(
                        loader,
                        "query_all",
                        side_effect=[
                            [{"kapt_code": "A1"}],
                            [
                                {
                                    "kapt_code": "A1",
                                    "pnu": "P1",
                                    "kapt_hhld": 10,
                                    "apts_hhld": 10,
                                }
                            ],
                            [{"cnt": 1}],
                        ],
                    ),
                ):
                    result = loader.collect_from_xlsx(
                        cost_files=[file.name], area_xlsx=file.name
                    )
                values = cursor.execute.call_args.args[1]
                self.assertEqual(values[2], 100000)
                self.assertEqual(values[5:7], [120000, 12000])
                self.assertEqual(result["loaded"], 1)


if __name__ == "__main__":
    unittest.main()
