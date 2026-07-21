"""Instagram Graph API 클라이언트 — Instagram Login 방식 (graph.instagram.com).

발행 시퀀스 (spec §5): 원격 manifest 검증 → 자산 검증 → 자식 컨테이너
각각 FINISHED 폴링 → 부모 캐러셀 → FINISHED → published_pending 선기록
→ media_publish → permalink → published 기록. 실패는 전부 예외 중단.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from scripts.insta_cards.instagram.assets import MAX_JPEG_BYTES

GRAPH_HOST = "https://graph.instagram.com"
GRAPH_API_VERSION = "v23.0"  # dry-run 실호출로 유효성 검증 — 온보딩 가이드 참조
HTTP_TIMEOUT = 30
POLL_INTERVAL = 30
CHILD_POLL_TIMEOUT = 120
CAROUSEL_POLL_TIMEOUT = 300
SUPPORTED_SCHEMA_VERSION = 1
ASSET_NAME_PATTERN = re.compile(r"^\d{2}-[a-z0-9-]+\.jpg$")
LOG_PATH = Path("reports/insta/instagram-log.jsonl")


class InstagramApiError(RuntimeError):
    pass


def append_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log_status(slug: str) -> str | None:
    if not LOG_PATH.exists():
        return None
    status = None
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("slug") == slug:
            status = entry.get("status")
    return status


class InstagramClient:
    def __init__(self, user_id: str, access_token: str, site_url: str):
        self.user_id = user_id
        self._token = access_token
        self.site_url = site_url.rstrip("/")

    # --- 내부 헬퍼 ---
    def _mask(self, text: str) -> str:
        return text.replace(self._token, "***TOKEN***")

    def _api(self, path: str) -> str:
        return f"{GRAPH_HOST}/{GRAPH_API_VERSION}{path}"

    def _check(self, resp) -> dict:
        if resp.status_code != 200:
            raise InstagramApiError(
                self._mask(f"Graph API {resp.status_code}: {resp.text[:500]}")
            )
        return resp.json()

    def _get(self, path: str, **params) -> dict:
        params["access_token"] = self._token
        try:
            resp = requests.get(self._api(path), params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            # requests 예외 메시지의 URL 에 토큰(쿼리 파라미터)이 포함될 수 있어 마스킹 후 재던짐
            raise InstagramApiError(self._mask(str(e))) from e
        return self._check(resp)

    def _post(self, path: str, **data) -> dict:
        data["access_token"] = self._token
        try:
            resp = requests.post(self._api(path), data=data, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise InstagramApiError(self._mask(str(e))) from e
        return self._check(resp)

    def _poll_finished(self, container_id: str, timeout: int, label: str) -> None:
        deadline = time.monotonic() + timeout
        while True:
            status = self._get(f"/{container_id}", fields="status_code")
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                detail = self._get(f"/{container_id}", fields="status")
                raise InstagramApiError(f"{label} 컨테이너 ERROR: {detail}")
            if time.monotonic() > deadline:
                raise InstagramApiError(
                    f"{label} 컨테이너 {timeout}초 타임아웃 (상태 {code})"
                )
            time.sleep(POLL_INTERVAL)

    # --- 공개 메서드 ---
    def verify_token(self) -> dict:
        return self._get("/me", fields="user_id,username")

    def publishing_quota(self) -> dict:
        return self._get(f"/{self.user_id}/content_publishing_limit")

    def _fetch_json(self, url: str) -> dict:
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise InstagramApiError(self._mask(str(e))) from e
        if resp.status_code != 200:
            raise InstagramApiError(
                self._mask(
                    f"{url} → {resp.status_code} — 배포 완료 후 재실행하세요: "
                    f"{resp.text[:500]}"
                )
            )
        return resp.json()

    def ig_base_url(self, slug: str) -> str:
        return f"{self.site_url}/content/instagram/{slug}/ig"

    def fetch_manifest(self, slug: str) -> dict:
        latest = self._fetch_json(f"{self.ig_base_url(slug)}/latest.json")
        generation = latest.get("generation", "")
        if not re.fullmatch(r"[0-9a-f]{12}", generation):
            raise InstagramApiError(f"latest.json generation 형식 오류: {generation!r}")
        manifest = self._fetch_json(
            f"{self.ig_base_url(slug)}/{generation}/publication.json"
        )
        if manifest.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            raise InstagramApiError(
                f"지원하지 않는 schema_version: {manifest.get('schema_version')}"
            )
        if manifest.get("slug") != slug:
            raise InstagramApiError(f"manifest slug 불일치: {manifest.get('slug')}")
        if manifest.get("status") != "published":
            raise InstagramApiError(f"published 상태가 아님: {manifest.get('status')}")
        assets = manifest.get("instagram_assets") or []
        if not 2 <= len(assets) <= 10:
            raise InstagramApiError(f"instagram_assets {len(assets)}개 — 2~10장 필요")
        for name in assets:
            if not ASSET_NAME_PATTERN.match(name):
                raise InstagramApiError(f"허용되지 않는 asset 이름: {name!r}")
        manifest["asset_generation"] = generation
        return manifest

    def verify_assets(self, slug: str, manifest: dict) -> list[str]:
        base = f"{self.ig_base_url(slug)}/{manifest['asset_generation']}"
        urls = [f"{base}/{name}" for name in manifest["instagram_assets"]]
        for url in urls:
            try:
                resp = requests.get(url, timeout=HTTP_TIMEOUT)
            except requests.RequestException as e:
                raise InstagramApiError(self._mask(str(e))) from e
            ctype = resp.headers.get("Content-Type", "")
            if resp.status_code != 200 or not ctype.startswith("image/jpeg"):
                raise InstagramApiError(
                    self._mask(
                        f"{url} → {resp.status_code} {ctype} — 배포 완료 후 재실행하세요: "
                        f"{resp.text[:500]}"
                    )
                )
            if len(resp.content) > MAX_JPEG_BYTES:
                raise InstagramApiError(f"{url} → {len(resp.content)} bytes — 8MB 초과")
        return urls

    def publish_carousel(self, slug: str, manifest: dict, caption: str) -> dict:
        urls = self.verify_assets(slug, manifest)
        child_ids = []
        for url in urls:
            child = self._post(
                f"/{self.user_id}/media", image_url=url, is_carousel_item="true"
            )
            child_ids.append(child["id"])
        for cid in child_ids:  # 자식 각각 FINISHED 확인 후 부모 생성 (spec §5-4)
            self._poll_finished(cid, CHILD_POLL_TIMEOUT, "자식")
        carousel = self._post(
            f"/{self.user_id}/media",
            media_type="CAROUSEL",
            children=",".join(child_ids),
            caption=caption,
        )
        self._poll_finished(carousel["id"], CAROUSEL_POLL_TIMEOUT, "캐러셀")
        # publish 직전 선기록 — 성공 후 기록 실패로 인한 중복 게시 방지 (spec §5-6)
        append_log(
            {
                "slug": slug,
                "status": "published_pending",
                "carousel_id": carousel["id"],
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        published = self._post(
            f"/{self.user_id}/media_publish", creation_id=carousel["id"]
        )
        media_id = published["id"]
        permalink = self._get(f"/{media_id}", fields="permalink").get("permalink", "")
        append_log(
            {
                "slug": slug,
                "status": "published",
                "media_id": media_id,
                "permalink": permalink,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        return {"media_id": media_id, "permalink": permalink}

    def recent_permalinks(self, limit: int = 25) -> list[dict]:
        data = self._get("/me/media", fields="permalink,caption", limit=str(limit))
        return data.get("data", [])

    def refresh_token(self) -> dict:
        """장기 토큰 갱신 (60일 주기) — 만료 24시간 이후~60일 이내 호출 가능."""
        return self._get("/refresh_access_token", grant_type="ig_refresh_token")
