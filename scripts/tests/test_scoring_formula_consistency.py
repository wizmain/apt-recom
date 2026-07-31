"""web/backend 스코어링과 batch/ml/apply_curves 의 복제 수식 일치 검증.

로그 감쇠 커널과 프로필 배율은 Railway 배포 경계(web/backend 는 batch 를
import 할 수 없고, 배치도 web/backend 에 의존하지 않는다) 때문에 양쪽에
복제되어 있다. 한쪽만 수정되면 ML 곡선 적합(apply_curves)이 런타임과 다른
수식을 전제로 decay 를 역산하게 되므로, 여기서 두 구현을 직접 비교해
드리프트를 차단한다.

주의: web/backend 를 sys.path 에 추가하는 것은 이 테스트의 비교 목적에
한정된다 — 런타임 코드의 모듈 경계 규칙(웹↔배치 상호 import 금지)을
완화하는 것이 아니다. DB 연결은 필요 없다 (순수 함수·상수만 비교).
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from batch.ml import apply_curves  # noqa: E402
from services import scoring  # noqa: E402


class ScoringFormulaConsistencyTest(unittest.TestCase):
    def test_log_decay_kernel_identical(self):
        """거리×decay×max_d 그리드 전 구간에서 두 커널 출력이 일치해야 한다."""
        max_d_grid = [1000.0, 3000.0, 6000.0]
        decay_grid = [50.0, 250.0, 400.0, 800.0, 1500.0]
        for max_d in max_d_grid:
            for decay in decay_grid:
                for step in range(0, 71):
                    d = step * 100.0
                    self.assertAlmostEqual(
                        scoring.log_decay_score(d, decay, max_d),
                        apply_curves._log_decay_score(d, decay, max_d),
                        places=9,
                        msg=f"d={d}, decay={decay}, max_d={max_d}",
                    )

    def test_profile_decay_multiplier_identical(self):
        """apply_curves 가 프로필별 decay 산출에 쓰는 배율은 런타임 배율과 같아야 한다."""
        self.assertEqual(apply_curves.PROFILE_MULTIPLIER, scoring._DECAY_MULTIPLIER)


if __name__ == "__main__":
    unittest.main()
