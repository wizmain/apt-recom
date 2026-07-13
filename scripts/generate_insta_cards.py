"""(deprecated) 인스타 카드 생성 구 진입점 — scripts/insta_cards 패키지로 이관됨.

기존 옵션(--series trade-top/compare/value, --days, --regions, --nudge,
--region, --min-hhld)은 새 CLI 가 그대로 받는다. 출력은 단일 카드가 아니라
캐러셀 디렉토리(reports/insta/{날짜}/{slug}/)로 바뀌었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.insta_cards.cli import main  # noqa: E402

if __name__ == "__main__":
    print(
        "[deprecated] scripts/generate_insta_cards.py 대신 "
        "`python -m scripts.insta_cards` 를 사용하세요.",
        file=sys.stderr,
    )
    main()
