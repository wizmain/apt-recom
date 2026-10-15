"""새로 만든 고유번호 키 매핑의 물리 게이트 (ADR-015 F2).

상속(api_inherit_legacy)이 아닌 판정 — 주소 PNU — 은 "그 키의 거래가 그 단지의 것"이라는 근거가
주소 한 줄뿐이다. 2026-10-14 로컬 적용에서 이 판정이 틀린 단지를 골랐다: 같은 지번의 다른 단지
(월계주공1·2, 휘경주공1·2 — 한쪽만 apartments 에 있음). 법정동 이름 매칭(숫자 지운 정규화
신관주공2 → 주공3, 포함 매칭 엘리시아 → 연동엘리시아)은 이 게이트로도 다 걸러지지 않아
2026-10-15 매핑 순위에서 제거했다(trade_key_mapping 모듈 설명).

그래서 매핑을 넣은 **같은 트랜잭션 안에서** audit_mappings 와 같은 판정(mapping_checks.check_mapping
+ mismatch_confirmed — 그 키의 실적 준공연도·면적·층·지번 대 후보 단지)을 돌려, 위반이면 방금 넣은
매핑을 지운다. 지워진 키는 미매핑으로 남는다(fallback 매핑 금지) — rekey 는 계획 행을 이름 키로
되돌려 현상 유지하고, 정기 배치는 다음 회차에 다시 판정한다(같은 근거면 같은 결과로 다시 거부·로그).

게이트 대상은 호출부가 정한다: 방금 INSERT 한 비상속 매핑 중 **기존 apartments 단지**를 가리키는
것만이다. 주소로 새로 등록한 단지는 비교할 진본이 없으니 대상이 아니다.
"""

from __future__ import annotations

from batch.trade.audit_mappings import find_violations

REJECT_LOG_SAMPLE = 50


def gate_keys(inserted: list[tuple[str, str]], exempt_methods: set[str]) -> list[str]:
    """(키, match_method) 쌍 중 게이트를 거칠 키 — 면제 방법(상속 등)을 뺀다. 정렬·중복 제거."""
    return sorted({k for k, method in inserted if method not in exempt_methods})


def reject_unverified_mappings(
    conn, logger, apt_seqs: list[str], source: str
) -> list[dict]:
    """apt_seqs 의 매핑을 물리 감사하고, 위반인 매핑을 지운다. 커밋하지 않는다.

    반환: 거부한 위반 목록(audit_mappings.violation_of 형식). source 는 로그 구분용(호출 위치).
    """
    if not apt_seqs:
        return []
    violations, _ = find_violations(conn, apt_seqs=list(apt_seqs))
    if not violations:
        return []
    keys = sorted({v["apt_seq"] for v in violations})
    conn.cursor().execute(
        "DELETE FROM trade_apt_mapping WHERE apt_seq = ANY(%s)", [keys]
    )
    sample = [
        f"{v['apt_seq']} {v['apt_nm']} → {v['bld_nm']} [{v['match_method']}] "
        f"{', '.join(v['reasons'])}"
        for v in sorted(violations, key=lambda x: x["apt_seq"])[:REJECT_LOG_SAMPLE]
    ]
    logger.warning(
        f"  [{source}] 물리 감사 불통과 → 매핑 거부(미매핑 유지) {len(keys):,}건 "
        f"(최대 {REJECT_LOG_SAMPLE}): {sample}"
    )
    return violations
