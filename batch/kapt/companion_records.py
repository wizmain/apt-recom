"""같은 단지의 K-APT 레코드(분양·임대)를 PNU 사이에서 옮기는 DB 연산 (ADR-014).

용어
  실제 PNU   apartments 에 있는 필지 키. K-APT 레코드 1건만 붙는다.
  더미 PNU   `KAPT_<단지코드>`. 실제 PNU 를 갖지 못한 레코드의 자리.
  동반 레코드 실제 PNU 를 내주고 더미로 옮겨진 레코드. `parent_pnu` 로 소속 단지를 가리킨다.

옮기는 대상은 **K-APT 레코드에서 유래한 테이블 전부**다. 하나라도 빠지면 세대수는 분양인데
주택형은 임대인 식으로 어긋난다. 위치·거래 기반 테이블(시설·가격·안전 등)은 필지에 속하므로
건드리지 않는다.

호출자가 트랜잭션을 책임진다 — 여기서는 commit/rollback 하지 않는다. 한 PNU 의 이동은 한
트랜잭션 안에서 끝나야 한다.
"""

from __future__ import annotations

from batch.kapt.pnu_contention import dummy_pnu, is_dummy_pnu

# K-APT 레코드 유래 테이블 — 전부 pnu 로 키잉된다 (2026-09-20 스키마 확인, 외래키 없음).
KAPT_KEYED_TABLES: tuple[str, ...] = (
    "apt_kapt_info",
    "apt_area_type",
    "apt_area_info",
    "apt_mgmt_cost",
)

PARENT_PNU_COLUMN = "parent_pnu"


class CompanionRecordError(Exception):
    """전제가 맞지 않아 이동을 거부한다. 호출자는 그 PNU 를 건너뛰고 사유를 남긴다."""


def _scalar(cur, sql: str, params: list):
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return row[0] if not isinstance(row, dict) else next(iter(row.values()))


def ensure_parent_pnu_column(cur) -> None:
    """`parent_pnu` 컬럼이 없으면 중단한다.

    컬럼은 web/backend/database.py create_tables() 가 만든다(백엔드 기동 시 실행). 없는 DB 에서
    이동하면 동반 레코드의 소속이 기록되지 않아 합산 세대수가 다음 적재에서 사라진다.
    """
    exists = _scalar(
        cur,
        """SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'apt_kapt_info' AND column_name = %s""",
        [PARENT_PNU_COLUMN],
    )
    if not exists:
        raise CompanionRecordError(
            f"apt_kapt_info.{PARENT_PNU_COLUMN} 컬럼 없음 — create_tables() 를 먼저 실행할 것 "
            "(Railway 는 백엔드 배포 시 자동 실행)"
        )


def _move_keyed_rows(cur, from_pnu: str, to_pnu: str) -> dict[str, int]:
    moved = {}
    for table in KAPT_KEYED_TABLES:
        cur.execute(f"UPDATE {table} SET pnu = %s WHERE pnu = %s", [to_pnu, from_pnu])
        moved[table] = cur.rowcount
    return moved


def _assert_key_is_free(cur, pnu: str) -> None:
    for table in KAPT_KEYED_TABLES:
        if _scalar(cur, f"SELECT 1 FROM {table} WHERE pnu = %s LIMIT 1", [pnu]):
            raise CompanionRecordError(
                f"{table} 에 {pnu} 행이 이미 있음 — 덮어쓰지 않는다"
            )


def evict_to_dummy(
    cur, real_pnu: str, outgoing_kapt_code: str, *, link_as_companion: bool
) -> dict[str, int]:
    """실제 PNU 를 차지한 레코드를 더미로 옮긴다.

    `link_as_companion` 이 참이면 `parent_pnu` 로 소속 단지를 기록해 세대수 합산에 들어가게 한다.
    **같은 단지의 임대동이라는 근거가 있을 때만** 참으로 준다 — 자리를 내주는 레코드가 이웃한 다른
    단지인 경우가 있다(`군자주공14단지` PNU 에 붙어 있던 `안산군자13단지`). 그때 연결하면 두 단지의
    세대수가 합쳐진다. 거짓이면 옮기기만 하고 합산에서 뺀다.

    실제 PNU 의 `apt_kapt_info` 가 `outgoing_kapt_code` 가 아니면 거부한다 — 검수 목록을 만든 뒤
    DB 가 바뀌었을 수 있다.
    """
    if is_dummy_pnu(real_pnu):
        raise CompanionRecordError(f"{real_pnu} 는 실제 PNU 가 아님")

    current = _scalar(
        cur, "SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [real_pnu]
    )
    if current != outgoing_kapt_code:
        raise CompanionRecordError(
            f"{real_pnu} 의 K-APT 레코드가 {outgoing_kapt_code} 가 아님 (현재 {current})"
        )

    target = dummy_pnu(outgoing_kapt_code)
    _assert_key_is_free(cur, target)

    moved = _move_keyed_rows(cur, real_pnu, target)
    cur.execute(
        f"UPDATE apt_kapt_info SET {PARENT_PNU_COLUMN} = %s WHERE pnu = %s",
        [real_pnu if link_as_companion else None, target],
    )
    return moved


def swap_records(
    cur,
    real_pnu: str,
    incoming_kapt_code: str,
    outgoing_kapt_code: str,
    *,
    link_as_companion: bool,
) -> dict[str, dict[str, int]]:
    """더미에 있던 `incoming` 을 실제 PNU 로, 실제 PNU 의 `outgoing` 을 더미로 옮긴다.

    같은 함수에 코드를 바꿔 넣으면 역교환이 된다. `link_as_companion` 은 `evict_to_dummy` 참고.
    """
    source = dummy_pnu(incoming_kapt_code)
    at_source = _scalar(
        cur, "SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [source]
    )
    if at_source != incoming_kapt_code:
        raise CompanionRecordError(f"{source} 에 {incoming_kapt_code} 레코드가 없음")

    evicted = evict_to_dummy(
        cur, real_pnu, outgoing_kapt_code, link_as_companion=link_as_companion
    )
    moved_in = _move_keyed_rows(cur, source, real_pnu)

    # 실제 PNU 에 붙은 레코드는 동반 레코드가 아니다. sigungu_code 는 적재와 같은 규칙(pnu 앞 5자리).
    cur.execute(
        f"UPDATE apt_kapt_info SET {PARENT_PNU_COLUMN} = NULL, sigungu_code = %s WHERE pnu = %s",
        [real_pnu[:5], real_pnu],
    )
    sync_apartment_fields(cur, real_pnu)
    apply_combined_households(cur, [real_pnu])
    return {"evicted": evicted, "moved_in": moved_in}


def sync_apartment_fields(cur, real_pnu: str) -> None:
    """apartments 의 K-APT 유래 컬럼을 실제 PNU 에 붙은 레코드 값으로 맞춘다.

    `ingest_full_kapt` Phase A 와 같은 규칙 — 값이 있을 때만 덮어쓴다. 세대수는 여기서 **그
    레코드 자신의 값**으로 맞춘다. 동반 레코드가 연결돼 있으면 뒤이은 `apply_combined_households`
    가 합산으로 올리고, 연결이 없으면 이 값이 그대로 남는다(임대 세대수가 남지 않게).
    """
    cur.execute(
        """
        UPDATE apartments a SET
          total_hhld_cnt = CASE WHEN COALESCE(k.ho_cnt, 0) > 0 THEN k.ho_cnt ELSE a.total_hhld_cnt END,
          dong_count  = CASE WHEN COALESCE(k.dong_cnt, 0) > 0 THEN k.dong_cnt ELSE a.dong_count END,
          max_floor   = CASE WHEN COALESCE(k.top_floor_official, k.top_floor, 0) > 0
                             THEN COALESCE(k.top_floor_official, k.top_floor) ELSE a.max_floor END,
          use_apr_day = CASE WHEN COALESCE(k.use_date, '') <> '' THEN k.use_date ELSE a.use_apr_day END
        FROM apt_kapt_info k
        WHERE k.pnu = a.pnu AND a.pnu = %s
        """,
        [real_pnu],
    )


def apply_combined_households(cur, pnus: list[str] | None = None) -> int:
    """동반 레코드가 있는 단지의 세대수를 **분양+임대 합산**으로 맞춘다. 갱신 건수를 반환.

    단지 규모 표기는 합산이다(ADR-014 — 카카오맵 표기와 3/4 일치, 분양만은 1/4). 세대당 관리비의
    분모는 `apt_kapt_info.ho_cnt`(관리비를 보고한 레코드의 세대수)를 그대로 쓰므로 영향받지 않는다.

    현재 `total_hhld_cnt` 에 더하지 않고 `ho_cnt` 에서 다시 계산한다 — 여러 번 실행해도 같은 값.
    `pnus` 를 생략하면 동반 레코드가 있는 전 단지를 처리한다(적재 마지막 단계).
    """
    sql = f"""
        UPDATE apartments a SET total_hhld_cnt = k.ho_cnt + c.companion_hhld
        FROM apt_kapt_info k
        JOIN (
            SELECT {PARENT_PNU_COLUMN} AS parent_pnu, SUM(COALESCE(ho_cnt, 0)) AS companion_hhld
            FROM apt_kapt_info
            WHERE {PARENT_PNU_COLUMN} IS NOT NULL
            GROUP BY {PARENT_PNU_COLUMN}
        ) c ON c.parent_pnu = k.pnu
        WHERE a.pnu = k.pnu AND COALESCE(k.ho_cnt, 0) > 0
    """
    params: list = []
    if pnus is not None:
        sql += " AND a.pnu = ANY(%s)"
        params.append(list(pnus))
    cur.execute(sql, params)
    return cur.rowcount
