"""--publish 시 프론트 레지스트리 반영 — posts.json upsert + cover 복사 + ig 세대 자산.

cover 경로가 slug 고정(/content/instagram/{slug}/cover.png)이라 재발행 시
한쪽만 교체되면 구 레코드가 새 cover 를 가리켜 "같은 실행의 동일 데이터"
원칙이 깨진다 → cover + ig 세대 디렉토리 + posts.json 3자를 하나의 스왑으로 정합화한다
(spec §3-4):
  새 파일들을 임시 경로에 준비 → cover 백업 → 새 cover 배치 →
  ig 세대 디렉토리·latest.json 교체 → posts.json 교체.
  cover 배치·ig 세대 교체·posts.json 교체 중 어느 단계가 실패해도
  cover 는 백업으로 원복하고, 새로 배치한 ig 세대 디렉토리는 제거하며,
  latest.json 은 직전 세대(정리 로직상 항상 최대 1개 존재)로 되돌린 뒤 re-raise 한다.
어떤 실패 경로에서도 "새 cover/ig 자산 + 구 레코드"(또는 역) 조합이나
cover 소실·백업 잔존이 남지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from scripts.insta_cards.instagram.assets import build_ig_assets, compute_generation
from scripts.insta_cards.publication import SLUG_PATTERN

FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "web" / "frontend-next"
POSTS_JSON_RELPATH = Path("src/content/instagram/posts.json")
COVER_PUBLIC_RELDIR = Path("public/content/instagram")
COVER_FILENAME = "cover.png"
IG_RELDIR = "ig"
IG_LATEST_FILENAME = "latest.json"


class FrontendPublishError(RuntimeError):
    pass


def public_cover_path(slug: str) -> str:
    return f"/content/instagram/{slug}/{COVER_FILENAME}"


def upsert_posts(posts: list[dict], record: dict) -> list[dict]:
    """같은 slug 교체 후 결정적 정렬: published_at DESC → generated_at DESC → slug ASC."""
    merged = [p for p in posts if p.get("slug") != record["slug"]] + [record]
    merged.sort(key=lambda p: p.get("slug") or "")  # 3차: slug ASC (stable sort 활용)
    merged.sort(
        key=lambda p: (p.get("published_at") or "", p.get("generated_at") or ""),
        reverse=True,
    )
    return merged


def _load_posts(posts_path: Path) -> list[dict]:
    if not posts_path.exists():
        return []
    try:
        data = json.loads(posts_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FrontendPublishError(f"posts.json 파싱 실패: {posts_path} — {e}") from e
    if not isinstance(data, list):
        raise FrontendPublishError(f"posts.json 이 배열이 아닙니다: {posts_path}")
    return data


def publish_to_frontend(
    record: dict, cover_src: Path, frontend_root: Path = FRONTEND_ROOT
) -> Path:
    if not cover_src.is_file():
        raise FrontendPublishError(f"cover 원본이 없습니다: {cover_src}")

    # 직접 호출자 방어용 형식 검증 — 경로 구성 전 slug 형식을 보장
    try:
        slug = record["slug"]
    except KeyError:
        raise FrontendPublishError("record에 'slug' 필드가 없습니다") from None
    if not SLUG_PATTERN.match(slug):
        raise FrontendPublishError(
            f"slug 형식 오류: {slug} — 소문자 ASCII+하이픈만 허용"
        )
    posts_path = frontend_root / POSTS_JSON_RELPATH
    cover_dst = frontend_root / COVER_PUBLIC_RELDIR / slug / COVER_FILENAME

    rec = dict(record)
    rec["cover_image"] = public_cover_path(slug)
    new_posts = upsert_posts(_load_posts(posts_path), rec)

    # pre-swap 검증 — 아직 어떤 임시 파일도 만들지 않은 시점 (실패해도 잔존물 없음)
    source_dir = cover_src.parent
    pub_json = source_dir / "publication.json"
    if not pub_json.is_file():
        raise FrontendPublishError(
            f"발행 디렉토리에 publication.json 없음: {source_dir}"
        )
    generation = compute_generation(pub_json.read_bytes())

    pid = os.getpid()
    posts_tmp = posts_path.with_name(f"posts.json.tmp-{pid}")
    cover_tmp = cover_dst.with_name(f"{COVER_FILENAME}.tmp-{pid}")
    cover_bak = cover_dst.with_name(f"{COVER_FILENAME}.bak-{pid}")
    ig_root = frontend_root / COVER_PUBLIC_RELDIR / slug / IG_RELDIR
    gen_dir = ig_root / generation
    gen_tmp = ig_root / f"{generation}.tmp-{pid}"
    latest_path = ig_root / IG_LATEST_FILENAME
    latest_tmp = ig_root / f"{IG_LATEST_FILENAME}.tmp-{pid}"

    # 준비(임시 파일 생성)부터 finally 의 정리 범위 안에서 수행 —
    # build_ig_assets 등 준비 단계 실패 시에도 부분 gen_tmp/posts_tmp/cover_tmp 가 남지 않는다.
    try:
        # 발행 디렉토리에서 ig 세대 자산을 임시 세대 디렉토리에 JPEG+manifest 로 준비
        build_ig_assets(source_dir, gen_tmp)
        ig_root.mkdir(parents=True, exist_ok=True)
        latest_tmp.write_text(
            json.dumps({"generation": generation}) + "\n", encoding="utf-8"
        )
        # 정리 대상 이전 세대 — 정리 로직이 매 발행마다 신규 세대 외 전부 제거하므로 항상 0~1개
        old_generations = [
            d.name
            for d in ig_root.iterdir()
            if d.is_dir() and d.name != generation and ".tmp-" not in d.name
        ]
        posts_path.parent.mkdir(parents=True, exist_ok=True)
        cover_dst.parent.mkdir(parents=True, exist_ok=True)
        posts_tmp.write_text(
            json.dumps(new_posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        shutil.copyfile(cover_src, cover_tmp)

        had_cover = cover_dst.exists()
        if had_cover:
            os.replace(cover_dst, cover_bak)  # ① 기존 cover 백업 (rename — 원복 가능)
        try:
            os.replace(cover_tmp, cover_dst)  # ② 새 cover 배치
            try:
                # ②b 새 세대 배치 (신규 경로 — rename 만, 동일 gen 재발행이면 교체) + ③ posts.json 교체
                # 두 단계를 하나의 try 로 묶는다 — gen_dir/latest 교체가 posts.json 이전에
                # 위치하므로, 이 구간 어디서 실패하든(②b 자체 포함) ② 로 배치한 새 cover 를
                # 그대로 두면 "새 cover + 구 posts.json 레코드" 조합이 남는다.
                if gen_dir.exists():
                    shutil.rmtree(gen_dir)
                os.replace(gen_tmp, gen_dir)
                os.replace(latest_tmp, latest_path)
                os.replace(posts_tmp, posts_path)  # ③ posts.json 교체
            except BaseException:
                # ②b·③ 실패 공통 → 새 cover·새 세대를 치운다: "새 자산 + 구 레코드" 방지
                os.replace(cover_dst, cover_tmp)
                shutil.rmtree(gen_dir, ignore_errors=True)  # 새 세대 제거
                # latest 원복: 이전 세대가 있으면 그 값으로 재작성, 없으면 삭제
                if old_generations:
                    latest_path.write_text(
                        json.dumps({"generation": old_generations[0]}) + "\n",
                        encoding="utf-8",
                    )
                else:
                    latest_path.unlink(missing_ok=True)
                raise
        except BaseException:
            # ②·③ 실패 공통: 백업 원복 (원본 예외는 그대로 체이닝되어 전파)
            if had_cover and not cover_dst.exists():
                os.replace(cover_bak, cover_dst)
            raise
        if had_cover:
            cover_bak.unlink(missing_ok=True)  # ④ 성공 — 백업 정리
        # 성공 시 이전 세대 정리 (정리 후 항상 신규 세대 1개만 남는 불변식 유지)
        for g in old_generations:
            shutil.rmtree(ig_root / g, ignore_errors=True)
    finally:
        posts_tmp.unlink(missing_ok=True)
        cover_tmp.unlink(missing_ok=True)
        shutil.rmtree(gen_tmp, ignore_errors=True)
        latest_tmp.unlink(missing_ok=True)
    return posts_path
