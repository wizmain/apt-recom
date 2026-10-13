"""거래 배치는 키 변경 스크립트가 잠금을 쥐고 있으면 실패로 기록하고 멈춘다 (Review Focus 4)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch import run as mod


class RunTradeLockTest(unittest.TestCase):
    def test_busy_lock_records_critical_and_skips_collection(self):
        result = MagicMock()
        conn = MagicMock()
        with (
            patch.object(mod, "get_connection", return_value=conn),
            patch("batch.trade.trade_keys.try_trade_write_lock", return_value=False),
            patch("batch.trade.collect_trades.collect_trades") as collect,
        ):
            mod.run_trade(SimpleNamespace(dry_run=False), MagicMock(), result)
        collect.assert_not_called()
        status = result.record.call_args[0][1]
        self.assertEqual(status, "critical")
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
