"""배치 로깅 + 결과 추적."""

import logging
import time
from pathlib import Path

BATCH_LOG_DIR = Path(__file__).resolve().parent / "logs"
BATCH_LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name="batch"):
    """파일 + 콘솔 로거 설정."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # 콘솔
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 파일
    ts = time.strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(BATCH_LOG_DIR / f"batch_{ts}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


class BatchResult:
    """배치 step별 결과 추적."""

    def __init__(self):
        self.steps: list[dict] = []

    def record(self, step: str, status: str, rows: int = 0, duration: float = 0, error: str = ""):
        self.steps.append({
            "step": step,
            "status": status,
            "rows": rows,
            "duration": round(duration, 1),
            "error": error,
        })

    def summary(self, logger: logging.Logger):
        logger.info("=" * 60)
        logger.info("  배치 실행 결과")
        logger.info("=" * 60)
        for s in self.steps:
            icon = "OK" if s["status"] == "success" else "FAIL"
            logger.info(f"  [{icon}] {s['step']:30s}  {s['rows']:>8,}건  {s['duration']:>6.1f}초  {s['error']}")
        logger.info("=" * 60)

    def exit_code(self) -> int:
        if any(s["status"] == "critical" for s in self.steps):
            return 2
        if any(s["status"] == "failed" for s in self.steps):
            return 1
        return 0
