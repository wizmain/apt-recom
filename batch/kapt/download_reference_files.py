"""K-APT 자료실 엑셀 파일 확인/다운로드.

K-APT 자료실의 3개 탭(기본정보, 관리비정보, 면적정보)을 확인해 최신 날짜형
게시글의 첨부 엑셀을 내려받는다. 필지고유번호는 집토리 정기 반영 범위에서
제외한다.

사용법:
  .venv/bin/python -m batch.kapt.download_reference_files --dry-run
  .venv/bin/python -m batch.kapt.download_reference_files --download
  .venv/bin/python -m batch.kapt.download_reference_files --download --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Final
from urllib.parse import unquote

import requests

from batch.logger import setup_logger

BASE_URL: Final = "https://www.k-apt.go.kr"
LIST_URL: Final = f"{BASE_URL}/web/board/webReference/boardList.do"
AJAX_URL: Final = f"{BASE_URL}/web/board/webReference/boardListAjax.do"
DOWNLOAD_URL: Final = f"{BASE_URL}/board/getFileDownload.do"
BOARD_TYPE: Final = "03"
DATA_DIR: Final = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "k-apt"
MANIFEST_FILE: Final = DATA_DIR / ".download_manifest.json"

# 필지고유번호(scode=02)는 정기 반영에서 제외한다.
TARGETS: Final = {
    "basic": {"scode": "01", "label": "기본정보"},
    "cost": {"scode": "03", "label": "관리비정보"},
    "area": {"scode": "04", "label": "면적정보"},
}

CSRF_RE: Final = re.compile(r'name="_csrf"[^>]*value="([^"]+)"')
ITEM_RE: Final = re.compile(
    r"<a[^>]+(?:onclick|href)=\"javascript:goCheck\((\d+),\s*\d+\);\"[^>]*>\s*(.*?)\s*</a>",
    re.DOTALL,
)
FILE_RE_TEMPLATE: Final = r"fileDown\('{seq}','{board_type}','([^']+)'\)"
DATE_RE: Final = re.compile(r"\((\d{4})\.(\d{2})\.(\d{2})\.\)")
TAG_RE: Final = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ReferenceItem:
    kind: str
    label: str
    scode: str
    title: str
    seq: str
    file_num: str
    date: str

    @property
    def yyyymmdd(self) -> str:
        return self.date.replace("-", "")

    @property
    def normalized_filename(self) -> str:
        return f"{self.yyyymmdd}_단지_{self.label}.xlsx"


def _strip_tags(value: str) -> str:
    return TAG_RE.sub("", value).strip()


def _extract_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise RuntimeError("K-APT 자료실 페이지에서 CSRF 토큰을 찾지 못했습니다.")
    return match.group(1)


def _parse_date(title: str) -> str | None:
    match = DATE_RE.search(title)
    if not match:
        return None
    y, m, d = match.groups()
    return f"{y}-{m}-{d}"


def _content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    msg = Message()
    msg["content-disposition"] = value
    filename = msg.get_param("filename", header="content-disposition")
    if isinstance(filename, str) and filename:
        return unquote(filename).strip('"')
    match = re.search(r'filename="?([^";]+)"?', value)
    return unquote(match.group(1)) if match else None


def _load_manifest(path: Path = MANIFEST_FILE) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_manifest(manifest: dict, path: Path = MANIFEST_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; apt-recom-kapt-downloader/1.0)",
            "Referer": LIST_URL,
        }
    )
    return session


def _get_csrf(session: requests.Session) -> str:
    response = session.get(LIST_URL, timeout=30)
    response.raise_for_status()
    return _extract_csrf(response.text)


def _list_items(
    session: requests.Session, csrf: str, *, kind: str, page_no: int = 1
) -> list[ReferenceItem]:
    target = TARGETS[kind]
    response = session.post(
        AJAX_URL,
        data={
            "scode": target["scode"],
            "boardType": BOARD_TYPE,
            "pageNo": str(page_no),
            "stype": "",
            "keyword": "",
            "_csrf": csrf,
        },
        timeout=30,
    )
    response.raise_for_status()

    html = response.text
    items: list[ReferenceItem] = []
    for match in ITEM_RE.finditer(html):
        seq = match.group(1)
        title = _strip_tags(match.group(2))
        date = _parse_date(title)
        if not date:
            # 관리비 탭에는 "2026년" 같은 연간 파일이 섞여 있어 정기 주간 파일만 선택한다.
            continue
        file_re = re.compile(
            FILE_RE_TEMPLATE.format(seq=re.escape(seq), board_type=BOARD_TYPE)
        )
        file_match = file_re.search(html, pos=match.end())
        if not file_match:
            continue
        items.append(
            ReferenceItem(
                kind=kind,
                label=target["label"],
                scode=target["scode"],
                title=title,
                seq=seq,
                file_num=file_match.group(1),
                date=date,
            )
        )
    return items


def _latest_items(session: requests.Session, csrf: str) -> dict[str, ReferenceItem]:
    latest: dict[str, ReferenceItem] = {}
    for kind in TARGETS:
        items = _list_items(session, csrf, kind=kind)
        if not items:
            raise RuntimeError(
                f"K-APT 자료실 {TARGETS[kind]['label']} 최신 날짜형 게시글을 찾지 못했습니다."
            )
        latest[kind] = max(items, key=lambda item: item.date)
    return latest


def _download_one(
    session: requests.Session,
    csrf: str,
    item: ReferenceItem,
    output_dir: Path,
    *,
    force: bool,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / item.normalized_filename
    if output_path.exists() and not force:
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        return {
            **asdict(item),
            "status": "exists",
            "path": str(output_path),
            "sha256": digest,
            "bytes": output_path.stat().st_size,
        }

    response = session.post(
        f"{DOWNLOAD_URL}?seq={item.seq}&boardType={BOARD_TYPE}",
        data={"_csrf": csrf, "fileNum": item.file_num},
        stream=True,
        timeout=120,
    )
    response.raise_for_status()

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    digest = hashlib.sha256()
    total = 0
    with tmp_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            digest.update(chunk)
            total += len(chunk)
            f.write(chunk)

    if total < 1024 or tmp_path.read_bytes()[:2] != b"PK":
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"다운로드 결과가 XLSX로 보이지 않습니다: {item.title} ({total} bytes)"
        )

    tmp_path.replace(output_path)
    source_filename = _content_disposition_filename(
        response.headers.get("content-disposition")
    )
    return {
        **asdict(item),
        "status": "downloaded",
        "path": str(output_path),
        "source_filename": source_filename,
        "sha256": digest.hexdigest(),
        "bytes": total,
    }


def run(
    *, output_dir: Path = DATA_DIR, download: bool = False, force: bool = False
) -> dict:
    session = _session()
    csrf = _get_csrf(session)
    latest = _latest_items(session, csrf)
    manifest = _load_manifest()

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "download": download,
        "force": force,
        "items": {},
    }

    for kind, item in latest.items():
        prev = manifest.get("items", {}).get(kind, {})
        is_new = prev.get("seq") != item.seq or prev.get("date") != item.date
        if download:
            item_result = _download_one(
                session, csrf, item, output_dir, force=force or is_new
            )
        else:
            item_result = {
                **asdict(item),
                "status": "new" if is_new else "unchanged",
                "path": str(output_dir / item.normalized_filename),
            }
        item_result["is_new"] = is_new
        result["items"][kind] = item_result

    if download:
        manifest.update(result)
        _save_manifest(manifest)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="K-APT 자료실 최신 엑셀 3종 확인/다운로드"
    )
    parser.add_argument(
        "--download", action="store_true", help="실제 파일 다운로드 수행"
    )
    parser.add_argument("--dry-run", action="store_true", help="목록만 확인 (기본값)")
    parser.add_argument(
        "--force", action="store_true", help="기존 파일이 있어도 재다운로드"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DATA_DIR, help="다운로드 저장 디렉터리"
    )
    args = parser.parse_args()

    logger = setup_logger("kapt_download")
    result = run(
        output_dir=args.output_dir,
        download=args.download and not args.dry_run,
        force=args.force,
    )
    for kind, item in result["items"].items():
        logger.info(
            "%s: %s seq=%s file=%s status=%s is_new=%s",
            kind,
            item["title"],
            item["seq"],
            item["path"],
            item["status"],
            item["is_new"],
        )
    if args.download and not args.dry_run:
        logger.info("manifest: %s", MANIFEST_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
