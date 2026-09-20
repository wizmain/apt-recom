"""거래 수집 배치의 시간 상한·실패 가시성 테스트 (DB·네트워크 불요).

배경 (2026-08-17 실측): 같은 작업량(254 시군구 × 1개월)이 8/16 에는 수집 9분 12초로
끝났는데 8/17 에는 59분을 넘겨 60분 벽에서 강제 종료됐다. 작업량 증가가 아니라
**실패 경로가 비싸서** 생기는 폭발이었다 — 정상 콜 1.09초 vs 실패 콜 92초
(30초 timeout × 3회 + 백오프). 508콜 중 33콜(6%)만 재시도를 소진하면 60분을 넘긴다.

게다가 그 실패는 로그 없이 None → [] 로 흡수돼 관측조차 되지 않았다.
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from batch.config import (  # noqa: E402
    COLLECT_BUDGET_MINUTES,
    DATA_GO_KR_RETRIES,
    DATA_GO_KR_TIMEOUT,
)
from batch.trade import collect_trades as mod  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.records = []

    def info(self, msg):
        self.records.append(("info", str(msg)))

    def warning(self, msg):
        self.records.append(("warning", str(msg)))

    def error(self, msg):
        self.records.append(("error", str(msg)))

    def text(self, level=None):
        return "\n".join(m for lv, m in self.records if level is None or lv == level)


class StepClock:
    """호출할 때마다 step 초씩 흐르는 결정론적 시계."""

    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class TestCallApiFailureVisibility(unittest.TestCase):
    """실패가 조용히 빈 결과로 흡수되면 안 된다 — 그게 이번 사고를 깜깜하게 만들었다."""

    def test_failure_is_logged_with_reason(self):
        logger = FakeLogger()
        with (
            patch.object(mod.requests, "get", side_effect=RuntimeError("boom")),
            patch.object(mod.time, "sleep"),
        ):
            result = mod._call_api("http://x", "11680", "202608", logger)
        self.assertIsNone(result)
        text = logger.text("warning")
        self.assertIn("11680", text)
        self.assertIn("202608", text)
        self.assertIn("boom", text, "실패 사유가 로그에 남지 않는다")

    def test_worst_case_cost_uses_bounded_constants(self):
        """최악 콜 비용 = timeout × retries + 백오프. 상수로 묶여 있어야 한다."""
        logger = FakeLogger()
        timeouts = []

        def fake_get(url, params=None, timeout=None):
            timeouts.append(timeout)
            raise RuntimeError("boom")

        with (
            patch.object(mod.requests, "get", fake_get),
            patch.object(mod.time, "sleep"),
        ):
            mod._call_api("http://x", "11680", "202608", logger)

        self.assertEqual(len(timeouts), DATA_GO_KR_RETRIES)
        self.assertTrue(all(t == DATA_GO_KR_TIMEOUT for t in timeouts))
        worst_case = DATA_GO_KR_TIMEOUT * DATA_GO_KR_RETRIES
        self.assertLess(
            worst_case, 60, "실패 콜 하나가 1분을 넘으면 소수 실패로도 예산이 터진다"
        )

    def test_success_returns_body_without_retry(self):
        logger = FakeLogger()

        class Resp:
            text = "<xml/>"

            def raise_for_status(self):
                pass

        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append(url)
            return Resp()

        with patch.object(mod.requests, "get", fake_get):
            result = mod._call_api("http://x", "11680", "202608", logger)
        self.assertEqual(result, "<xml/>")
        self.assertEqual(len(calls), 1)


class TestRotation(unittest.TestCase):
    """예산에 걸릴 때 잘리는 쪽이 늘 같으면 그 지역만 결손이 고착된다.

    시군구 코드는 오름차순이라 뒤쪽은 항상 비수도권이다.
    """

    def test_rotation_preserves_every_code(self):
        codes = [f"{i:05d}" for i in range(254)]
        for offset in (0, 1, 97, 253):
            rotated = mod._rotate(codes, offset)
            self.assertEqual(sorted(rotated), sorted(codes))
            self.assertEqual(len(rotated), len(codes))

    def test_rotation_starts_at_offset(self):
        codes = ["a", "b", "c", "d"]
        self.assertEqual(mod._rotate(codes, 2), ["c", "d", "a", "b"])

    def test_offset_differs_between_runs_of_same_day(self):
        """하루 2회(03/15 UTC)가 같은 지점에서 시작하면 회전이 무의미하다."""
        morning = mod._rotation_offset(254, datetime(2026, 8, 17, 3, 0))
        evening = mod._rotation_offset(254, datetime(2026, 8, 17, 15, 0))
        self.assertNotEqual(morning, evening)

    def test_offset_differs_across_days(self):
        today = mod._rotation_offset(254, datetime(2026, 8, 17, 3, 0))
        tomorrow = mod._rotation_offset(254, datetime(2026, 8, 18, 3, 0))
        self.assertNotEqual(today, tomorrow)

    def test_offset_covers_whole_range_over_time(self):
        """며칠 안에 앞쪽·뒤쪽이 골고루 시작 지점이 돼야 결손이 고착되지 않는다."""
        seen = {
            mod._rotation_offset(254, datetime(2026, 8, d, h, 0))
            for d in range(1, 29)
            for h in (3, 15)
        }
        self.assertGreater(len(seen), 40, f"회전 폭이 좁다: {len(seen)}개 지점")

    def test_offset_is_safe_for_empty_code_list(self):
        self.assertEqual(mod._rotation_offset(0, datetime(2026, 8, 17, 3, 0)), 0)


class TestCollectBudget(unittest.TestCase):
    def _run(self, *, codes, budget_seconds, step, fail_codes=()):
        logger = FakeLogger()

        def fake_call(url, code, month, log, **kwargs):
            return None if code in fail_codes else "<xml/>"

        with (
            patch.object(mod, "get_district_codes", return_value=list(codes)),
            patch.object(mod, "_get_collection_months", return_value=["202608"]),
            patch.object(mod, "_call_api", fake_call),
            patch.object(
                mod, "_parse_xml", lambda xml, cmap: [] if xml is None else [{"a": 1}]
            ),
            patch.object(mod.time, "sleep"),
        ):
            trade_rows, rent_rows, stats = mod.collect_trades(
                conn=None,
                logger=logger,
                budget_seconds=budget_seconds,
                clock=StepClock(step),
                now=datetime(2026, 8, 17, 3, 0),
            )
        return trade_rows, rent_rows, stats, logger

    def test_within_budget_collects_every_district(self):
        codes = [f"{i:05d}" for i in range(10)]
        trade_rows, rent_rows, stats, logger = self._run(
            codes=codes, budget_seconds=10_000, step=1
        )
        self.assertFalse(stats.budget_exceeded)
        self.assertEqual(stats.districts_done, 10)
        self.assertEqual(len(trade_rows), 10)
        self.assertEqual(len(rent_rows), 10)

    def test_budget_exceeded_returns_partial_instead_of_hanging(self):
        """예산을 넘기면 예외가 아니라 **정상 반환**이어야 한다.

        그래야 적재·점수 재계산 등 후속 단계가 실행되고 부분 수집분이 보존된다.
        (지금까지는 60분 벽에서 프로세스가 죽어 수집분이 전량 날아갔다.)
        """
        codes = [f"{i:05d}" for i in range(10)]
        trade_rows, _, stats, logger = self._run(
            codes=codes, budget_seconds=25, step=10
        )
        self.assertTrue(stats.budget_exceeded)
        self.assertEqual(stats.districts_done, 2)
        self.assertEqual(len(trade_rows), 2, "수집한 만큼은 반환돼야 한다")
        warning = logger.text("warning")
        self.assertIn("2/10", warning, "어디서 멈췄는지 로그에 없다")

    def test_failed_calls_are_counted_and_surfaced(self):
        codes = [f"{i:05d}" for i in range(10)]
        _, _, stats, logger = self._run(
            codes=codes, budget_seconds=10_000, step=1, fail_codes={"00003", "00007"}
        )
        # 시군구당 매매·전월세 2콜 → 실패 시군구 2곳이면 4콜 실패
        self.assertEqual(stats.failed, 4)
        self.assertEqual(stats.attempted, 20)
        self.assertIn("실패", logger.text(), "실패 건수가 요약에 없다")

    def test_default_budget_leaves_room_under_job_wall(self):
        """수집 예산 + 후속 단계가 워크플로 timeout-minutes(60) 안에 들어와야 한다.

        실측: 후속 단계(적재·가격 재계산·저평가·신규 등록)가 약 7분.
        """
        self.assertLessEqual(COLLECT_BUDGET_MINUTES + 7, 60)


if __name__ == "__main__":
    unittest.main()
