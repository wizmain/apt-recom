"""K-APT 자료실 엑셀 3종 사전 검증.

정기 반영 대상은 기본정보, 관리비정보, 면적정보 3종이다. 필지고유번호는 제외한다.

사용법:
  .venv/bin/python -m batch.kapt.validate_kapt_files --date 20260626
  .venv/bin/python -m batch.kapt.validate_kapt_files \
    --basic-file apt_eda/data/k-apt/20260626_단지_기본정보.xlsx \
    --cost-file apt_eda/data/k-apt/20260626_단지_관리비정보.xlsx \
    --area-file apt_eda/data/k-apt/20260626_단지_면적정보.xlsx
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from batch.db import get_connection, query_all
from batch.logger import setup_logger

DATA_DIR = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "k-apt"
REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"

REQUIRED_COLUMNS = {
    "basic": [
        "단지코드",
        "단지명",
        "사용승인일",
        "세대수",
        "동수",
        "최고층수",
        "법정동주소",
        "도로명주소",
    ],
    "cost": [
        "단지코드",
        "단지명",
        "발생년월(YYYYMM)",
        "공용관리비계",
        "개별사용료계",
        "장충금 월부과액",
    ],
    "area": [
        "단지코드",
        "단지명",
        "관리비부과면적",
        "주거전용면적(단지합계)",
        "주거전용면적(세부)",
        "세대수",
    ],
}

LABELS = {"basic": "기본정보", "cost": "관리비정보", "area": "면적정보"}


@dataclass(frozen=True)
class FileSummary:
    kind: str
    path: str
    rows: int
    unique_kapt_codes: int
    mapped_codes: int
    loadable_codes: int
    unmapped_codes: int
    unloadable_codes: int
    missing_columns: list[str]
    min_year_month: str | None = None
    max_year_month: str | None = None
    unique_months: int | None = None


def _code_set(df: pd.DataFrame) -> set[str]:
    if "단지코드" not in df.columns:
        return set()
    return {str(v).strip() for v in df["단지코드"].dropna() if str(v).strip()}


def _default_paths(date: str, data_dir: Path) -> tuple[Path, Path, Path]:
    return (
        data_dir / f"{date}_단지_기본정보.xlsx",
        data_dir / f"{date}_단지_관리비정보.xlsx",
        data_dir / f"{date}_단지_면적정보.xlsx",
    )


def _load_db_codes() -> tuple[set[str], set[str]]:
    conn = get_connection()
    try:
        mapped_codes = {
            str(r["kapt_code"]).strip()
            for r in query_all(
                conn,
                "SELECT kapt_code FROM apt_kapt_info WHERE kapt_code IS NOT NULL AND kapt_code <> ''",
            )
        }
        loadable_codes = {
            str(r["kapt_code"]).strip()
            for r in query_all(
                conn,
                """SELECT k.kapt_code
                   FROM apt_kapt_info k
                   JOIN apartments a ON k.pnu = a.pnu
                   WHERE k.kapt_code IS NOT NULL AND k.kapt_code <> ''""",
            )
        }
        return mapped_codes, loadable_codes
    finally:
        conn.close()


def _summarize(
    kind: str, path: Path, db_codes: set[str], loadable_codes: set[str]
) -> tuple[FileSummary, pd.DataFrame, set[str]]:
    if not path.exists():
        raise FileNotFoundError(f"{LABELS[kind]} 파일 없음: {path}")
    df = pd.read_excel(path, header=1)
    missing = [col for col in REQUIRED_COLUMNS[kind] if col not in df.columns]
    codes = _code_set(df)
    mapped = len(codes & db_codes)
    loadable = len(codes & loadable_codes)

    min_ym = max_ym = None
    unique_months = None
    if kind == "cost" and "발생년월(YYYYMM)" in df.columns:
        yms = df["발생년월(YYYYMM)"].dropna().astype(int).astype(str)
        if not yms.empty:
            min_ym = str(yms.min())
            max_ym = str(yms.max())
            unique_months = int(yms.nunique())

    return (
        FileSummary(
            kind=kind,
            path=str(path),
            rows=len(df),
            unique_kapt_codes=len(codes),
            mapped_codes=mapped,
            loadable_codes=loadable,
            unmapped_codes=len(codes) - mapped,
            unloadable_codes=len(codes) - loadable,
            missing_columns=missing,
            min_year_month=min_ym,
            max_year_month=max_ym,
            unique_months=unique_months,
        ),
        df,
        codes,
    )


def validate(
    *, basic_file: Path, cost_file: Path, area_file: Path, report_dir: Path = REPORT_DIR
) -> dict:
    db_codes, loadable_codes = _load_db_codes()
    inputs = {"basic": basic_file, "cost": cost_file, "area": area_file}
    summaries: dict[str, FileSummary] = {}
    code_sets: dict[str, set[str]] = {}
    frames: dict[str, pd.DataFrame] = {}

    for kind, path in inputs.items():
        summary, df, codes = _summarize(kind, path, db_codes, loadable_codes)
        summaries[kind] = summary
        frames[kind] = df
        code_sets[kind] = codes

    report_dir.mkdir(parents=True, exist_ok=True)
    date_hint = Path(basic_file).name.split("_")[0]
    unmapped_rows = []
    for kind, codes in code_sets.items():
        for code in sorted(codes - db_codes):
            unmapped_rows.append(
                {"kind": kind, "label": LABELS[kind], "kapt_code": code}
            )
    unmapped_path = report_dir / f"kapt_unmapped_{date_hint}.csv"
    pd.DataFrame(unmapped_rows).to_csv(unmapped_path, index=False, encoding="utf-8-sig")

    unloadable_rows = []
    for kind, codes in code_sets.items():
        names_by_code = {}
        if "단지코드" in frames[kind].columns and "단지명" in frames[kind].columns:
            code_name_df = frames[kind][["단지코드", "단지명"]].dropna(
                subset=["단지코드"]
            )
            for row in code_name_df.to_dict("records"):
                code = str(row["단지코드"]).strip()
                if code and code not in names_by_code:
                    names_by_code[code] = (
                        "" if pd.isna(row["단지명"]) else str(row["단지명"]).strip()
                    )

        for code in sorted(codes - loadable_codes):
            is_mapped = code in db_codes
            unloadable_rows.append(
                {
                    "kind": kind,
                    "label": LABELS[kind],
                    "kapt_code": code,
                    "apt_name": names_by_code.get(code, ""),
                    "in_apt_kapt_info": is_mapped,
                    "reason": "no_apartments_join"
                    if is_mapped
                    else "no_apt_kapt_info_mapping",
                }
            )
    unloadable_path = report_dir / f"kapt_unloadable_{date_hint}.csv"
    pd.DataFrame(unloadable_rows).to_csv(
        unloadable_path, index=False, encoding="utf-8-sig"
    )

    intersection = set.intersection(*(codes for codes in code_sets.values()))
    union = set.union(*(codes for codes in code_sets.values()))
    result = {
        "summaries": {kind: summary.__dict__ for kind, summary in summaries.items()},
        "db_kapt_codes": len(db_codes),
        "db_loadable_kapt_codes": len(loadable_codes),
        "intersection_codes": len(intersection),
        "union_codes": len(union),
        "unmapped_report": str(unmapped_path),
        "unloadable_report": str(unloadable_path),
        "ok": all(not s.missing_columns for s in summaries.values()),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="K-APT 자료실 엑셀 3종 검증")
    parser.add_argument(
        "--date", help="YYYYMMDD. 파일 경로 미지정 시 기본 파일명에 사용"
    )
    parser.add_argument(
        "--dir", type=Path, default=DATA_DIR, help="K-APT 파일 디렉터리"
    )
    parser.add_argument("--basic-file", type=Path)
    parser.add_argument("--cost-file", type=Path)
    parser.add_argument("--area-file", type=Path)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()

    if args.basic_file and args.cost_file and args.area_file:
        basic_file, cost_file, area_file = (
            args.basic_file,
            args.cost_file,
            args.area_file,
        )
    elif args.date:
        basic_file, cost_file, area_file = _default_paths(args.date, args.dir)
    else:
        parser.error(
            "--date 또는 --basic-file/--cost-file/--area-file 모두 필요합니다."
        )

    logger = setup_logger("kapt_validate")
    result = validate(
        basic_file=basic_file,
        cost_file=cost_file,
        area_file=area_file,
        report_dir=args.report_dir,
    )
    for kind, summary in result["summaries"].items():
        logger.info(
            "%s: rows=%s codes=%s mapped=%s unmapped=%s loadable=%s unloadable=%s missing=%s",
            kind,
            summary["rows"],
            summary["unique_kapt_codes"],
            summary["mapped_codes"],
            summary["unmapped_codes"],
            summary["loadable_codes"],
            summary["unloadable_codes"],
            summary["missing_columns"],
        )
        if kind == "cost":
            logger.info(
                "cost months: %s~%s (%s개월)",
                summary["min_year_month"],
                summary["max_year_month"],
                summary["unique_months"],
            )
    logger.info(
        "DB kapt_code=%s, loadable_kapt_code=%s, intersection=%s, union=%s",
        result["db_kapt_codes"],
        result["db_loadable_kapt_codes"],
        result["intersection_codes"],
        result["union_codes"],
    )
    logger.info("unmapped report: %s", result["unmapped_report"])
    logger.info("unloadable report: %s", result["unloadable_report"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
