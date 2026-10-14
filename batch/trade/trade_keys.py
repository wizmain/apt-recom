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


def _blank_to_none(v):
    s = str(v).strip() if v is not None else ""
    return s or None


def address_rows_by_key(rows) -> dict[str, dict[str, dict]]:
    """키 → {주소 PNU: 그 PNU 를 만든 첫 행}. 주소 필드가 있는 **모든** 행을 본다.

    대표 행 하나만 보면 행정구역 개편 전후 umd_cd 가 섞인 키(예: 28260-138 마전동아
    11300/10300)가 존재하지 않는 PNU 를 골라 미매핑된다. 주소 필드가 없는 행(전월세)은 무시한다.
    rows: apt_seq·sgg_cd·umd_cd·land_cd·bonbun·bubun 을 가진 dict.
    """
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        pnu = address_pnu(
            str(r["sgg_cd"])[:5],
            r.get("umd_cd"),
            r.get("land_cd"),
            _blank_to_none(r.get("bonbun")),
            _blank_to_none(r.get("bubun")),
        )
        if pnu:
            out.setdefault(r["apt_seq"], {}).setdefault(pnu, r)
    return out


def unique_existing_pnu(candidates, existing) -> str | None:
    """후보 주소 PNU 중 apartments 에 있는 것이 정확히 하나일 때만 그것. 0개·2개 이상이면 None."""
    hits = set(candidates) & set(existing)
    return next(iter(hits)) if len(hits) == 1 else None


def most_frequent_value(counts: dict[str, int]) -> str:
    """가장 많이 나온 값. 동률이면 사전순 첫 값(결정적). 비어 있으면 빈 문자열."""
    if not counts:
        return ""
    return min(counts, key=lambda v: (-counts[v], v))


def _row_count(r) -> int:
    return int(r.get("n") or 1)


def address_pnu_counts(rows) -> dict[str, dict[str, int]]:
    """키 → {주소 PNU: 행 수}. 집계 행이면 n(행 수)으로 가중, n 이 없으면 1."""
    out: dict[str, dict[str, int]] = {}
    for key, by_pnu in address_rows_by_key(rows).items():
        out[key] = dict.fromkeys(by_pnu, 0)
    for r in rows:
        pnu = address_pnu(
            str(r["sgg_cd"])[:5],
            r.get("umd_cd"),
            r.get("land_cd"),
            _blank_to_none(r.get("bonbun")),
            _blank_to_none(r.get("bubun")),
        )
        if pnu:
            out[r["apt_seq"]][pnu] += _row_count(r)
    return out


_JIBUN_SLICE = slice(10, PNU_LENGTH)  # 산 여부 + 본번 4 + 부번 4


def address_choice_warning(key: str, counts: dict[str, int], chosen: str) -> str | None:
    """고른 주소 PNU 가 키 주소 행의 소수파이거나 다수파와 지번이 다르면 경고 문구 (동작 변경 없음).

    개편 전후 법정동 코드만 다른 경우(지번 같음)는 소수파일 때만 경고한다.
    """
    total = sum(counts.values())
    if not total or chosen not in counts:
        return None
    majority = most_frequent_value(counts)
    minority = counts[chosen] * 2 < total
    other_jibun = chosen[_JIBUN_SLICE] != majority[_JIBUN_SLICE]
    if not (minority or other_jibun):
        return None
    shares = {p: f"{c}/{total}" for p, c in sorted(counts.items())}
    return f"{key} → {chosen} (소수파={minority}, 다수파와 지번 다름={other_jibun}) 행 비율 {shares}"


def try_trade_write_lock(conn) -> bool:
    """세션 advisory lock. 다른 세션이 잡고 있으면 즉시 False."""
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", [TRADE_WRITE_LOCK_ID])
    return bool(cur.fetchone()[0])
