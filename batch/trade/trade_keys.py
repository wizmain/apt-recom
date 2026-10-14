"""거래 키(apt_seq) 규칙 — ADR-015.

이름 조합 키 "{시군구}_{단지명}" 은 같은 구의 동명 단지 거래를 합친다(2026-10-13 동작구
대방대림+상도1동대림). 국토부 단지 고유번호(aptSeq)가 있으면 그것을 키로 쓴다.
키는 불투명 문자열이다 — aptSeq 앞자리가 내부 시군구 코드와 다를 수 있으므로
(실측 331건) 시군구는 항상 sgg_cd 칼럼에서 읽는다.
"""

from __future__ import annotations

from typing import NamedTuple

KEY_METHOD_API = "api"
KEY_METHOD_INFER_SINGLE = "infer_single"
KEY_METHOD_INFER_YEAR = "infer_year"
KEY_METHOD_INFER_YEAR_AREA = "infer_year_area"
KEY_METHOD_INFER_AREA = "infer_area"
KEY_METHOD_API_BACKFILL = "api_backfill"

# 거래 테이블 쓰기 상호 배제 — 거래 배치(batch.run --type trade)와
# 키 변경(batch.rekey_trades)이 같은 행을 동시에 바꾸지 않게 한다. ADR 번호에서 딴 고정값.
TRADE_WRITE_LOCK_ID = 15001

PNU_LENGTH = 19
_MOUNTAIN_LAND_CD = "2"


class TradeKey(NamedTuple):
    apt_seq: str
    legacy_apt_seq: str | None
    apt_seq_method: str | None


def name_key(sgg: str, apt_nm: str) -> str:
    """기존 이름 조합 키."""
    return f"{sgg}_{apt_nm}"


def resolve_trade_key(sgg: str, apt_nm: str, api_apt_seq: str | None) -> TradeKey:
    """적재 행의 키. aptSeq 가 비어 있으면 이름 키를 쓴다."""
    legacy = name_key(sgg, apt_nm)
    api = (api_apt_seq or "").strip()
    if api:
        return TradeKey(api, legacy, KEY_METHOD_API)
    return TradeKey(legacy, None, None)


def address_pnu(sgg, umd_cd, land_cd, bonbun, bubun) -> str | None:
    """거래 주소 필드로 만든 19자리 PNU. 필드가 부족하거나 숫자가 아니면 None."""
    if not (sgg and umd_cd and bonbun):
        return None
    mountain = "1" if str(land_cd) == _MOUNTAIN_LAND_CD else "0"
    pnu = f"{sgg}{umd_cd}{mountain}{str(bonbun).zfill(4)}{str(bubun or '0').zfill(4)}"
    if len(pnu) != PNU_LENGTH or not pnu.isdigit():
        return None
    return pnu


def try_trade_write_lock(conn) -> bool:
    """세션 advisory lock. 다른 세션이 잡고 있으면 즉시 False."""
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", [TRADE_WRITE_LOCK_ID])
    return bool(cur.fetchone()[0])
