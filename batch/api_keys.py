"""data.go.kr API 키 로테이션 공용 모듈.

여러 수집기(collect_area_info, collect_building_register 등)가 동일한
일일 한도 풀(.env 의 PRIMARY/SECONDARY/THIRD 키)을 공유하므로,
로테이터를 프로세스 단일 인스턴스로 공유한다 — 한 수집기가 소진시킨 키를
다른 수집기가 다시 시도하는 낭비 방지.

원본 구현: batch/trade/collect_area_info.py (2026-05) 에서 추출 —
building_register 수집(2026-07)이 두 번째 소비자가 되며 공통화.
"""

from batch.config import (
    DATA_GO_KR_API_KEY,
    DATA_GO_KR_API_SECONDARY_KEY,
    DATA_GO_KR_API_THIRD_KEY,
)


class KeysExhausted(Exception):
    """등록된 data.go.kr API 키 전부 일일 한도 초과."""


class KeyRotator:
    """data.go.kr API 키 로테이터 — 429 발생 시 다음 키로 순차 전환.

    - key1 → key2 → key3 → … → exhausted(소진)
    - 순차적으로 상태 전이만 허용 (되돌아가지 않음 — 한도는 자정까지 유지)
    - 프로세스 수명 동안 상태 유지
    """

    def __init__(self, *keys: str):
        self._keys = [k for k in keys if k]
        self._index = 0
        self._exhausted = False

    def current(self) -> str:
        if self._exhausted or self._index >= len(self._keys):
            raise KeysExhausted("DATA_GO_KR API 키 전부 소진")
        return self._keys[self._index]

    def rotate(self) -> bool:
        """다음 키로 전환. 더 이상 없으면 exhausted=True 로 표시."""
        self._index += 1
        if self._index >= len(self._keys):
            self._exhausted = True
            return False
        return True

    def exhausted(self) -> bool:
        return self._exhausted


# 프로세스 공유 싱글턴 — data.go.kr 계열 수집기는 이 인스턴스를 사용할 것
data_go_rotator = KeyRotator(
    DATA_GO_KR_API_KEY,
    DATA_GO_KR_API_SECONDARY_KEY,
    DATA_GO_KR_API_THIRD_KEY,
)
