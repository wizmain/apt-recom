"""Nudge scoring engine for apartment recommendations.

가중치/최대거리를 common_code 테이블에서 로드하고 캐시.
거리→점수 변환: 로그 감쇠 비선형 함수 (ML Feature Importance 기반 decay 파라미터)
밀도 반영: count_1km 기반 밀도 점수를 거리 점수와 블렌딩
프로필별 파라미터: metro / major_city / provincial 3단계 지역 프로필
"""

import math

from database import DictConnection

# ---------------------------------------------------------------------------
# 지역 프로필 매핑 (시도코드 → profile)
# ---------------------------------------------------------------------------
_region_profiles: dict[str, str] | None = None

_DEFAULT_REGION_PROFILES: dict[str, str] = {
    "11": "metro",
    "28": "metro",
    "41": "metro",
    "26": "major_city",
    "27": "major_city",
    "29": "major_city",
    "30": "major_city",
    "31": "major_city",
    "36": "major_city",
    "42": "provincial",
    "43": "provincial",
    "44": "provincial",
    "45": "provincial",
    "46": "provincial",
    "47": "provincial",
    "48": "provincial",
    "50": "provincial",
}


def _load_region_profiles() -> dict[str, str]:
    global _region_profiles
    if _region_profiles is not None:
        return _region_profiles
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name FROM common_code WHERE group_id = %s",
        ["region_profile"],
    ).fetchall()
    conn.close()
    if rows:
        _region_profiles = {r["code"]: r["name"] for r in rows}
    else:
        _region_profiles = _DEFAULT_REGION_PROFILES.copy()
    return _region_profiles


def get_region_profile(sigungu_code: str | None) -> str:
    """시군구코드 → 프로필(metro/major_city/provincial) 반환."""
    profiles = _load_region_profiles()
    sido = (sigungu_code or "")[:2]
    return profiles.get(sido, "provincial")


# ---------------------------------------------------------------------------
# 모듈 레벨 캐시 (서버 프로세스 내 1회 로드)
# ---------------------------------------------------------------------------
_max_distances: dict[str, float] | None = None
_max_distances_by_profile: dict[str, dict[str, float]] | None = None
_nudge_weights: dict[str, dict[str, float]] | None = None
_facility_decay_by_profile: dict[str, dict[str, float]] | None = None
_density_factor_by_profile: dict[str, dict[str, float]] | None = None


# ---------------------------------------------------------------------------
# 기본값 (metro 프로필 기준, DB에 데이터 없을 때 fallback)
# ---------------------------------------------------------------------------

# 시설별 로그 감쇠 파라미터 (ML Feature Importance 기반)
_DEFAULT_FACILITY_DECAY: dict[str, float] = {
    "mart": 800,
    "hospital": 700,
    "subway": 500,
    "pharmacy": 400,
    "animal_hospital": 350,
    "convenience_store": 350,
    "bus": 300,
    "kindergarten": 400,
    "library": 350,
    "pet_facility": 300,
    "cctv": 300,
    "school": 400,
    "fire_station": 250,
    "park": 300,
    "police": 250,
    "assigned_elementary": 400,  # 배정초교 — school 과 동일 감쇠 (도보 통학 거리 민감)
    # 상가정보 유래 4종 (Phase 2-2) — decay 는 subtype 희소성에 비례
    "cafe": 300,  # 초밀집 업종(전국 10만+) — 가까운 것만 유의미, 낮은 decay
    "kids_cafe": 500,  # 희소 업종 — 다소 멀어도 접근성 가치 유지되도록 높은 decay
    "pet_shop": 400,  # 중간 밀집도 — mart/hospital 과 유사한 감쇠
    "fitness": 400,  # 중간 밀집도 — 동일 근거
    # 심평원 병원 세분화 3종 (Phase 2-3) — decay 는 통원 성격에 비례
    "pediatric_clinic": 500,  # 일상 통원(예방접종 등) — 도보~단거리 통원권 중심
    "obgyn_clinic": 700,  # 정기 산전관리 — 소아과보다 넓은 통원권 허용
    "general_hospital": 1500,  # 응급/중증 대응 — 광역 시설, provincial 배율로 추가 확장
    # NEIS 학원(입시.검정 및 보습) (Phase 2-5) — decay 는 school(400)/library(350)
    # 보다 넓게 잡는다: 학원은 "가장 가까운 곳"이 아니라 강사진/입시 실적 등으로
    # 동네 경계를 넘어 선택하는 통학권이 흔함(obgyn_clinic=700 과 동일한 넓은
    # 통원권 성격) — 도보 통학권보다 관대한 감쇠로 원거리 유명 학원가도
    # 일정 점수를 유지하도록 한다.
    "academy": 700,
}

# 시설별 밀도 환산 계수 (count_1km × factor → 0~100 점수)
_DEFAULT_DENSITY_FACTOR: dict[str, float] = {
    "convenience_store": 5,
    "bus": 5,
    "cctv": 3,
    "pharmacy": 8,
    "hospital": 8,
    "mart": 15,
    "school": 15,
    "kindergarten": 10,
    "park": 10,
    "library": 25,
    "subway": 25,
    "pet_facility": 15,
    "animal_hospital": 15,
    "police": 50,
    "fire_station": 50,
    # 배정초교는 단일 시설이라 밀도 개념이 없음 — count_1km∈{0,1} 을
    # "1km 도보권 보너스"(0 또는 100)로 사용 (배치가 0/1 로 적재)
    "assigned_elementary": 100,
    # 상가정보 유래 4종 (Phase 2-2) — factor 는 subtype 희소성에 반비례
    # (Task 2 실측: count_1km 중앙값 66, 서울 96%가 캡(34개) 포화 →
    #  카페는 캡 구조상 초밀집이라 낮은 factor 가 정합. 건물단위 dedup 도
    #  근접편의 지표로 타당 판정 — 코드리뷰 기록)
    "cafe": 3,
    "kids_cafe": 20,  # 희소 업종 — 소수 존재만으로도 밀도 점수가 크게 오르도록 높은 factor
    "pet_shop": 12,
    "fitness": 10,
    # 심평원 병원 세분화 3종 (Phase 2-3) — factor 결정 근거 (실측, 프로필별
    # DENSITY_MULTIPLIER 적용 후 min(100, count_1km*factor) 포화율 기준):
    #   pediatric_clinic: 계획 초안 factor=10 은 전국 71.0%/서울 91.1% 가 캡(100점)
    #   포화 — cafe(factor=3, 전국 83.5%/서울 96.1%) 와 큰 차이가 없어 "카페만큼
    #   초밀집"으로 취급하는 셈이 되고, 소아과는 신혼 넛지의 핵심 세분화 축이라
    #   변별력이 필요하다. 또한 count_1km 7~12 구간이 전체의 24.2% 를 차지하는데
    #   좌표충돌 skip(12.9%)으로 이 구간에서 count 가 ±1 흔들리면 포화 여부가
    #   뒤집히는 임계 구간과 정확히 겹친다. factor=8 로 완화하면 포화율이 전국
    #   60.1%/서울 84.7% 로 낮아져 cafe 대비 변별력을 회복하고, metro 프로필의
    #   포화 임계(count_1km 10→13)가 밀집 구간에서 한 칸 멀어져 skip 민감도가
    #   줄어든다. factor=7 은 포화율을 더 낮추지만(53.5%/78.7%) 신혼 넛지에서
    #   비중 있는 신호로 두기엔 과소평가 — factor=8 채택.
    "pediatric_clinic": 8,
    #   obgyn_clinic: factor=15 유지 — 전국 33.5%/서울 58.6% 포화로 아직 변별력
    #   구간(캡 미달)이 다수라 완화 불필요.
    "obgyn_clinic": 15,
    #   general_hospital: factor=60 유지 — 전국 385개 희소 시설, 포화 전국
    #   9.2%/서울 6.7% 로 매우 낮아 "가까이 있으면 확실히 우대"하는 응급/중증
    #   대응 성격에 부합.
    "general_hospital": 60,
    # NEIS 학원(입시.검정 및 보습) (Phase 2-5) — factor 결정 근거 (전국 실측,
    # apt_facility_summary 35,696행, count_1km 분포: p10=7/p25=17/p50=32/p75=52/
    # p90=77/p95=97/p99=146/max=461. 압축 semantics 주의: facilities 는 좌표
    # UNIQUE 로 같은 건물 학원을 대표 1건으로 압축하므로 count_1km 은 "학원 실개수"가
    # 아니라 "학원 보유 지점 수"다.
    #   DENSITY_MULTIPLIER 적용 후 min(100, count_1km*factor*mult) 포화율(캡 도달
    #   비율, factor 후보별):
    #     factor=2 → 전국 39.1%/서울 54.7%, factor=1.5 → 24.8%/36.4%,
    #     factor=1 → 전국 9.5%/서울 12.5% (metro 5.9%/major_city 16.6%/
    #     provincial 10.7%), factor=0.75 → 3.8%/5.4%.
    #   cafe(factor=3, 전국 83.5%/서울 96.1%)나 최초 채택 전 pediatric_clinic
    #   후보(factor=10, 71.0%/91.1%)수준의 포화는 "카페급 변별력 상실"에
    #   해당한다 — 학원은 count_1km 원본 스케일 자체가 병원/상가류보다 한 자릿수
    #   위(중앙값 32 vs 병원류 단자릿수)라 같은 factor 크기를 적용하면 즉시
    #   과포화된다. factor=1 은 nationwide 포화가 p95(97)~p99(146) 구간, 즉
    #   "실제 학원가(대치동 등 상위 5% 지점)"에서만 만점에 도달하고 중앙값(32)
    #   근방 다수 아파트는 32~52점대로 완만하게 분포해 변별력을 유지한다.
    "academy": 1,
}

# 시설별 max_distance(컷오프, m) — 기존 15종은 common_code(facility_distance,
# metro 기준) 실측값을 그대로 반영(DB 가 있으면 항상 DB 값 우선이라 fallback 로만 쓰임).
# Phase 2 이후 추가된 9종은 DB(facility_distance/_major_city/_provincial)에 행이
# 없어 종전에는 distance_to_score() 의 `.get(subtype, 3000)` 균일 폴백을 탔다 —
# 아래 값으로 대체한다.
#
# 결정 근거 — max_distance/decay 비율 패턴 실측(기존 15종, metro 기준):
#   근린 밀집형(convenience_store 1000/350≈2.86, cctv 1000/300≈3.33): ratio ~2.9-3.3
#   도보 통학/일상권(school·kindergarten 2000/400=5.0): ratio 5.0
#   광역/희소형(subway 3000/500=6.0, hospital 3000/700≈4.29): ratio ~4.3-6.0
#   응급/행정형(police 3000/250=12.0, fire_station 5000/250=20.0): ratio 12-20
# 신규 9종은 decay 값이 근접한 기존 subtype 의 ratio 대역을 그대로 적용해
# max_distance 를 역산했다(단, "단거리 통원권" 등 문서화된 성격 차이가 있으면
# 같은 decay 라도 ratio 를 구분 — 아래 각 항목 주석 참조):
_DEFAULT_MAX_DISTANCE: dict[str, float] = {
    "mart": 2000,
    "hospital": 3000,
    "subway": 3000,
    "pharmacy": 1500,
    "animal_hospital": 3000,
    "convenience_store": 1000,
    "bus": 1500,
    "kindergarten": 2000,
    "library": 3000,
    "pet_facility": 3000,
    "cctv": 1000,
    "school": 2000,
    "fire_station": 5000,
    "park": 2000,
    "police": 3000,
    # 배정초교 — decay 가 school 과 동일(400)이므로 max_distance 도 school 과
    # 동일값 사용 (동일 ratio=5.0, 도보 통학권 성격 그대로 유지).
    "assigned_elementary": 2000,
    # 상가정보 유래 4종 (Phase 2-2)
    # cafe: decay(300)가 convenience_store(350)와 가장 가깝고 "초밀집·근거리만
    # 유의미"라는 성격도 동일 — convenience_store 의 ratio(~2.86)를 그대로 적용.
    "cafe": 1000,
    # kids_cafe: decay(500)가 subway 와 동일값 — 희소 업종이라 subway 와 같은
    # ratio(6.0) 적용, 다소 멀어도 완만하게 점수가 남도록 함.
    "kids_cafe": 3000,
    # pet_shop / fitness: decay(400)가 school/kindergarten 과 동일 — 동일
    # ratio(5.0) 적용.
    "pet_shop": 2000,
    "fitness": 2000,
    # 심평원 병원 세분화 3종 (Phase 2-3)
    # pediatric_clinic: decay(500)만 보면 kids_cafe/subway 와 같지만, 문서화된
    # 성격이 "도보~단거리 통원권 중심"으로 명시돼 있어 광역형 ratio(6.0) 대신
    # school 대역 ratio(5.0)를 적용해 kids_cafe 보다 좁은 컷오프를 유지한다.
    "pediatric_clinic": 2000,
    # obgyn_clinic: decay(700)가 hospital 과 동일값이고 "소아과보다 넓은 통원권"
    # 이라는 성격도 hospital 과 부합 — hospital 과 동일값(ratio 4.29) 사용.
    "obgyn_clinic": 3000,
    # general_hospital: decay(1500)가 hospital(700)의 2.14배 — "광역 시설"
    # 성격을 반영해 hospital 과 동일 ratio(≈4.29)로 스케일: 3000 × (1500/700) ≈
    # 6428 → 6000(관리 편의를 위한 반올림). 기존 균일폴백(3000)보다 넓어져
    # 3000~6000m 구간의 원거리 종합병원도 0점 대신 점진적 점수를 받는다.
    "general_hospital": 6000,
    # academy: decay(700)가 hospital/obgyn_clinic 과 동일값이며, 주석상
    # "obgyn_clinic 과 동일한 넓은 통원권 성격"으로 명시돼 있어 동일값 사용.
    "academy": 3000,
}

# 프로필별 배율 (metro=1.0 기준)
_DECAY_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.8}
_DENSITY_MULTIPLIER = {"metro": 1.0, "major_city": 1.5, "provincial": 2.0}
_MAX_DIST_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.6}


# ---------------------------------------------------------------------------
# 로더 함수들
# ---------------------------------------------------------------------------


def _load_max_distances() -> dict[str, float]:
    """글로벌 max_distance (facility_distance group) — 코드 기본값 + DB 오버라이드 merge.

    merge semantics: _DEFAULT_MAX_DISTANCE 위에 DB(facility_distance group) 값을
    subtype 단위로 얹는다 — decay/density 로더와 동일 패턴(a96b199). DB 에 행이
    있는 기존 15 subtype 은 DB 값이 우선(운영에서 common_code 로 튜닝 가능하게
    유지)하고, Phase 2 이후 추가된 9 subtype(DB 미등록)은 코드 기본값을 쓴다.

    fallback 발동 조건: DB(facility_distance group)에도 _DEFAULT_MAX_DISTANCE 에도
    없는 subtype 만 호출측 `.get(subtype, 3000)` 상수 폴백을 탄다.
    """
    global _max_distances
    if _max_distances is not None:
        return _max_distances
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name FROM common_code WHERE group_id = %s", ["facility_distance"]
    ).fetchall()
    conn.close()
    overrides = {r["code"]: float(r["name"]) for r in rows}
    _max_distances = {**_DEFAULT_MAX_DISTANCE, **overrides}
    return _max_distances


# 프로필별 파라미터 로더 공통 규칙 (merge semantics):
# "배율 적용된 코드 기본값" 위에 common_code 의 프로필별 오버라이드 행을
# subtype 단위로 얹는다 (DB 행이 있는 subtype 은 DB 값 우선, 없는 subtype 은
# 스케일된 기본값 사용).
#
# 왜 merge 인가 — 과거에는 프로필 group 에 행이 1개라도 있으면 dict 를 통째로
# 교체했는데, ML 튜닝(apply_curves)이 심은 major_city/provincial 15개 subtype
# 행이 존재하는 상태에서 이후 Phase 2 에 추가된 subtype(cafe/kids_cafe/
# pet_shop/fitness/pediatric_clinic/obgyn_clinic/general_hospital/academy 및
# assigned_elementary)이 비수도권 프로필에서 통째로 누락되어
# `.get(subtype, 기본상수)` 폴백으로 오동작했다 (예: academy density factor
# 의도 1×배율 → 폴백 10 이 적용돼 major_city 포화율 91.5%). merge 는 각
# subtype 의 결정 근거(위 기본값 딕셔너리 주석)가 전제한 값을 복원한다.
#
# fallback 발동 조건: 프로필 group 에도 기본값 딕셔너리에도 없는 subtype 만
# 호출측 `.get(subtype, 상수)` 기본값을 탄다 — 신규 subtype 은 반드시
# _DEFAULT_* 딕셔너리에 등록할 것.


def _load_max_distances_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 max_distance 로드 — 배율 적용 글로벌 기본값 + DB 오버라이드 merge."""
    global _max_distances_by_profile
    if _max_distances_by_profile is not None:
        return _max_distances_by_profile

    base = _load_max_distances()
    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"facility_distance_{profile}"],
        ).fetchall()
        mult = _MAX_DIST_MULTIPLIER.get(profile, 1.0)
        scaled_defaults = {k: round(v * mult, 1) for k, v in base.items()}
        overrides = {r["code"]: float(r["name"]) for r in rows}
        result[profile] = {**scaled_defaults, **overrides}

    conn.close()
    _max_distances_by_profile = result
    return result


def _load_facility_decay_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 decay 로드 — 배율 적용 기본값 + DB 오버라이드 merge."""
    global _facility_decay_by_profile
    if _facility_decay_by_profile is not None:
        return _facility_decay_by_profile

    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"facility_decay_{profile}"],
        ).fetchall()
        mult = _DECAY_MULTIPLIER.get(profile, 1.0)
        scaled_defaults = {
            k: float(round(v * mult)) for k, v in _DEFAULT_FACILITY_DECAY.items()
        }
        overrides = {r["code"]: float(r["name"]) for r in rows}
        result[profile] = {**scaled_defaults, **overrides}

    conn.close()
    _facility_decay_by_profile = result
    return result


def _load_density_factor_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 density factor 로드 — 배율 적용 기본값 + DB 오버라이드 merge."""
    global _density_factor_by_profile
    if _density_factor_by_profile is not None:
        return _density_factor_by_profile

    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"density_factor_{profile}"],
        ).fetchall()
        mult = _DENSITY_MULTIPLIER.get(profile, 1.0)
        scaled_defaults = {
            k: round(v * mult, 1) for k, v in _DEFAULT_DENSITY_FACTOR.items()
        }
        overrides = {r["code"]: float(r["name"]) for r in rows}
        result[profile] = {**scaled_defaults, **overrides}

    conn.close()
    _density_factor_by_profile = result
    return result


def _load_nudge_weights() -> dict[str, dict[str, float]]:
    global _nudge_weights
    if _nudge_weights is not None:
        return _nudge_weights
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["nudge_weight"],
    ).fetchall()
    conn.close()
    _nudge_weights = {}
    for r in rows:
        parts = r["code"].split(":", 1)
        if len(parts) == 2:
            nudge_id, _ = parts
            if nudge_id not in _nudge_weights:
                _nudge_weights[nudge_id] = {}
            _nudge_weights[nudge_id][r["name"]] = float(r["extra"])
    return _nudge_weights


# ---------------------------------------------------------------------------
# 공개 API: 캐시 접근 + 무효화
# ---------------------------------------------------------------------------


def get_max_distances() -> dict[str, float]:
    return _load_max_distances()


def get_nudge_weights() -> dict[str, dict[str, float]]:
    return _load_nudge_weights()


def invalidate_cache() -> None:
    """모듈 레벨 캐시 리셋. 가중치/거리기준 수정 후 호출."""
    global _nudge_weights, _max_distances, _max_distances_by_profile
    global _region_profiles, _facility_decay_by_profile, _density_factor_by_profile
    _nudge_weights = None
    _max_distances = None
    _max_distances_by_profile = None
    _region_profiles = None
    _facility_decay_by_profile = None
    _density_factor_by_profile = None


# ---------------------------------------------------------------------------
# 지표 정규화 상수/함수
# ---------------------------------------------------------------------------

# 인프라/데이터가 아예 없는 축의 중립 점수.
# - subway: 비수도권 인프라 부재 시 개별 아파트에 적용 (facility_score 내부)
# - 지역 결측: 요청 후보군 전체에서 관측되지 않는 subtype 에 적용 (routers/nudge.py)
# 결측 축을 0점으로 깔면 해당 지역 전체가 구조적으로 저평가되므로,
# "변별력이 없는 축은 중립"이라는 원칙으로 통일한다.
INFRA_MISSING_NEUTRAL_SCORE = 50.0

# 파생(derived) 지표 — 원본 시설 관측치가 아니라 다른 배치 산출물에서 계산되는
# facility_subtype. quarterly 배치가 학군을 재계산하기 전까지, trade 배치로
# 신규 등록된 아파트는 apt_facility_summary 에 이 subtype 행이 아예 없다.
# "행 없음" 이 "그 아파트 주변에 시설이 없음" 이 아니라 "아직 계산 안 됨" 을
# 뜻하므로, 지역 전체 결측(routers/nudge.py 4a)뿐 아니라 개별 아파트 결측도
# 중립 처리해야 education(가중 0.30) 같은 축에서 신규 아파트가 0점으로
# 깔리는 것을 막는다. 대상: assigned_elementary (quarterly 학군 배정 배치).
DERIVED_FACILITY_SUBTYPES: set[str] = {"assigned_elementary"}

# 전세가율(%) → 0~100 점수 선형 변환 구간.
# 실측 분포(apt_price_score 26,395건, 2026-07: 중앙값 71.7%, 최대 215.7% 이상치)
# 기준 40% 이하 = 0점, 90% 이상 = 100점 클리핑.
# 방향: 전세가율 높음 = 매매가 대비 사용가치 높음(가성비)·갭 부담 낮음(투자) → 고점.
JEONSE_RATIO_SCORE_FLOOR = 40.0
JEONSE_RATIO_SCORE_CEIL = 90.0


def jeonse_ratio_to_score(jeonse_ratio: float | None) -> float:
    """전세가율(%) → 0~100 점수. 결측/비정상(≤0)은 중립 50점.

    apt_price_score.jeonse_ratio 원값은 0~215% 범위라 0~100 점수 축에
    직접 주입하면 스케일이 왜곡된다 — 반드시 이 함수를 거쳐 주입할 것.
    """
    if jeonse_ratio is None or jeonse_ratio <= 0:
        return INFRA_MISSING_NEUTRAL_SCORE
    span = JEONSE_RATIO_SCORE_CEIL - JEONSE_RATIO_SCORE_FLOOR
    scaled = (jeonse_ratio - JEONSE_RATIO_SCORE_FLOOR) / span * 100.0
    return round(min(100.0, max(0.0, scaled)), 2)


# 세대당 주차대수 → 0~100 선형 구간 (건축물대장 표제부 집계, Phase 2-1).
# 법정 기준이 세대당 ~1대 내외임을 근거로 0.4대 이하 = 0점, 1.3대 이상 = 100점.
# 초기값 — 전수 수집 후 실측 분포(percentile)로 재확인한다.
PARKING_RATIO_SCORE_FLOOR = 0.4
PARKING_RATIO_SCORE_CEIL = 1.3

# 승강기 1대당 담당 세대수가 이 값 이하면 만점 (승강기 대기시간 체감 근거).
ELEVATOR_HOUSEHOLDS_PER_UNIT_GOOD = 25.0


def parking_ratio_to_score(parking_per_hhld: float | None) -> float:
    """세대당 주차대수 → 0~100. 값 NULL(대장에 주차 미기재)은 중립."""
    if parking_per_hhld is None:
        return INFRA_MISSING_NEUTRAL_SCORE
    span = PARKING_RATIO_SCORE_CEIL - PARKING_RATIO_SCORE_FLOOR
    scaled = (parking_per_hhld - PARKING_RATIO_SCORE_FLOOR) / span * 100.0
    return round(min(100.0, max(0.0, scaled)), 2)


def elevator_to_score(elevator_count: int | None, hhld_cnt: int | None) -> float:
    """승강기 수 → 0~100 (세대당 밀도 기준).

    - elevator_count None (대장 미기재) → 중립
    - 0대 → 0점 (계단식 구식 단지 — 결측이 아닌 실제 열위)
    - hhld 불명이면 승강기 존재만으로 중립 이상 판단 불가 → 중립
    """
    if elevator_count is None:
        return INFRA_MISSING_NEUTRAL_SCORE
    if elevator_count <= 0:
        return 0.0
    if not hhld_cnt or hhld_cnt <= 0:
        return INFRA_MISSING_NEUTRAL_SCORE
    scaled = 100.0 * (elevator_count * ELEVATOR_HOUSEHOLDS_PER_UNIT_GOOD) / hhld_cnt
    return round(min(100.0, scaled), 2)


# ---------------------------------------------------------------------------
# 점수 계산 함수
# ---------------------------------------------------------------------------


def distance_to_score(
    distance_m: float | None,
    facility_subtype: str,
    profile: str = "metro",
) -> float:
    """거리 → 0~100 점수 (로그 감쇠 비선형, 프로필별 파라미터)."""
    if distance_m is None:
        return 0.0
    max_d_map = _load_max_distances_by_profile()
    max_d = max_d_map.get(profile, {}).get(facility_subtype, 3000)
    if distance_m >= max_d:
        return 0.0
    decay_map = _load_facility_decay_by_profile()
    decay = decay_map.get(profile, _DEFAULT_FACILITY_DECAY).get(facility_subtype, 400)
    score = 100.0 * max(
        0.0, 1.0 - math.log(1 + distance_m / decay) / math.log(1 + max_d / decay)
    )
    return round(score, 2)


def density_to_score(
    count_1km: int | None,
    facility_subtype: str,
    profile: str = "metro",
) -> float:
    """1km 내 시설 수 → 0~100 점수 (프로필별 factor)."""
    if not count_1km:
        return 0.0
    factor_map = _load_density_factor_by_profile()
    factor = factor_map.get(profile, _DEFAULT_DENSITY_FACTOR).get(facility_subtype, 10)
    return round(min(100.0, count_1km * factor), 2)


def facility_score(
    distance_m: float | None,
    count_1km: int | None,
    facility_subtype: str,
    distance_ratio: float = 0.7,
    profile: str = "metro",
) -> float:
    """거리(70%) + 밀도(30%) 블렌딩 점수 (프로필별 파라미터).

    지하철 인프라가 없는 비수도권 아파트는 중립 점수 50점 반환.
    """
    # 지하철 인프라가 없는 비수도권: 중립 점수
    # distance=None 또는 max_distance 초과 + 1km 내 0개 → 인프라 부재로 판단
    if facility_subtype == "subway" and profile != "metro" and not count_1km:
        if distance_m is None:
            return INFRA_MISSING_NEUTRAL_SCORE
        max_d_map = _load_max_distances_by_profile()
        max_d = max_d_map.get(profile, {}).get("subway", 3000)
        if distance_m >= max_d:
            return INFRA_MISSING_NEUTRAL_SCORE

    d_score = distance_to_score(distance_m, facility_subtype, profile)
    n_score = density_to_score(count_1km, facility_subtype, profile)
    return round(d_score * distance_ratio + n_score * (1.0 - distance_ratio), 2)


def calculate_nudge_score(
    facility_scores: dict[str, float],
    nudge_id: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """단일 넛지의 가중 평균 점수."""
    weights = (
        custom_weights if custom_weights else _load_nudge_weights().get(nudge_id, {})
    )
    if not weights:
        return 0.0

    total_weight = 0.0
    total_score = 0.0
    for subtype, w in weights.items():
        total_score += facility_scores.get(subtype, 0.0) * w
        total_weight += w

    if total_weight == 0:
        return 0.0
    return round(total_score / total_weight, 2)


def calculate_multi_nudge_score(
    facility_scores: dict[str, float],
    nudge_ids: list[str],
    custom_weights_map: dict[str, dict[str, float]] | None = None,
) -> float:
    """복수 넛지의 평균 점수."""
    if not nudge_ids:
        return 0.0
    scores = [
        calculate_nudge_score(
            facility_scores,
            nid,
            (custom_weights_map or {}).get(nid),
        )
        for nid in nudge_ids
    ]
    return round(sum(scores) / len(scores), 2)


def get_top_contributors(
    facility_scores: dict[str, float],
    nudge_ids: list[str],
    custom_weights_map: dict[str, dict[str, float]] | None = None,
    top_n: int = 3,
) -> list[dict]:
    """선택된 넛지들의 상위 기여 시설 subtype을 contribution 내림차순으로 반환.

    contribution = facility_score × weight (넛지별 정규화 가중치 × 점수).
    여러 넛지를 동시에 선택하면 subtype별로 weight/contribution을 누적 후 랭킹.

    반환 포맷:
        [{"subtype": "subway", "score": 86.0, "weight_sum": 0.3, "contribution": 25.8}, ...]
    """
    if not nudge_ids:
        return []

    default_weights = _load_nudge_weights()
    agg: dict[str, dict[str, float]] = {}

    for nid in nudge_ids:
        custom = (custom_weights_map or {}).get(nid)
        weights = custom if custom else default_weights.get(nid, {})
        if not weights:
            continue
        total_w = sum(weights.values()) or 1.0
        for subtype, w in weights.items():
            norm_w = (
                w / total_w
            )  # 넛지 내부 정규화 (calculate_nudge_score 와 동일 규칙)
            score = float(facility_scores.get(subtype, 0.0))
            bucket = agg.setdefault(
                subtype, {"score": score, "weight_sum": 0.0, "contribution": 0.0}
            )
            bucket["weight_sum"] += norm_w
            bucket["contribution"] += score * norm_w

    items = [
        {
            "subtype": subtype,
            "score": round(v["score"], 2),
            "weight_sum": round(v["weight_sum"], 4),
            "contribution": round(v["contribution"], 2),
        }
        for subtype, v in agg.items()
        if v["score"] > 0  # 점수 0이면 기여 요소로 부적합
    ]
    items.sort(key=lambda x: x["contribution"], reverse=True)
    return items[:top_n]
