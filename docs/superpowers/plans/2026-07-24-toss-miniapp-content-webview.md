# toss-miniapp 콘텐츠(WebView 임베드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** frontend-next의 `/content` 카드뉴스 아티클을 toss-miniapp에서 네이티브 목록 + WebView 상세로 볼 수 있게 한다.

**Architecture:** 콘텐츠 본문은 웹이 렌더한다. 백엔드가 `GET /api/content`로 발행 목록 메타를 서빙(생성 아티팩트 `content_index.json` 기반)하고, 미니앱은 목록만 네이티브로 그린 뒤 상세는 frontend-next의 전용 static 임베드 라우트 `/content/[slug]/embed`를 WebView로 띄운다.

**Tech Stack:** FastAPI(Python 3.12, stdlib json)/ Next.js(App Router, RSC, ISR)/ React Native(granite, react-native-webview)/ unittest(스크립트)·test_core.py(백엔드)·Playwright(frontend-next E2E).

**설계 근거:** `docs/superpowers/specs/2026-07-24-toss-miniapp-content-webview-design.md`

## Global Constraints

- 백엔드(`web/backend/`) 런타임 코드는 `batch/`, `apt_eda/`, `web/frontend-next/**` 등 외부 파일을 import/read 하지 않는다. (Railway는 `web/backend/`만 배포)
- Python: ruff format + check, snake_case. 의존성 추가 시 `uv pip install` + `requirements.txt` 수동 갱신.
- TypeScript: `any` 금지. 변수/함수 camelCase, 컴포넌트 PascalCase. API 응답/DB/프론트 노출 이름은 snake_case, 소문자 시작(underscore prefix 금지).
- API 호출은 `useApi` 훅 경유 (useEffect 내 직접 fetch 금지).
- 커밋: Conventional Commits. 커밋 메시지에 AI 작업자 표기(Co-Authored-By 등) 금지. 문서/코드에 "Generated with Claude Code" 삽입 금지.
- main 브랜치 직접 push 금지. 브랜치: `feature/` 접두어.
- 자동 커밋/push 금지 — 각 Task의 커밋 스텝은 실행자가 수행하되, push는 명시 요청 시에만.
- 미니앱 라우트 파일 규칙: **루트 `pages/*.tsx`(재수출 shim) + `src/pages/*.tsx`(구현) 2개**가 함께 필요하고, `src/router.gen.ts`는 **손으로 편집하지 않고 Granite로 재생성**한다.

---

## File Structure

**Phase 1 — 백엔드 데이터 + API**
- Create `scripts/sync_content_index.py` — posts.json → content_index.json 투영 생성 + `--check`.
- Create `scripts/tests/test_sync_content_index.py` — 동기화 로직 unittest.
- Create `web/backend/content/content_index.json` — 커밋되는 생성 아티팩트.
- Create `web/backend/frontend_config.py` — `FRONTEND_BASE_URL` 공용 상수.
- Modify `web/backend/routers/sitemap.py` — `FRONTEND_BASE_URL`을 공용 모듈에서 import.
- Create `web/backend/routers/content.py` — `GET /api/content`.
- Modify `web/backend/main.py` — content 라우터 등록.
- Modify `web/backend/tests/test_core.py` — content 엔드포인트/계약 테스트.
- Modify `scripts/insta_cards/cli.py` — `--publish` 시 인덱스 자동 생성.
- Create `.github/workflows/ci-content-index.yml` — 드리프트 `--check`.

**Phase 2 — frontend-next 임베드**
- Create `web/frontend-next/src/app/content/[slug]/EmbedContext.tsx` — 임베드 컨텍스트 + Provider(client).
- Modify `web/frontend-next/src/app/content/[slug]/ApartmentLink.tsx` — 임베드 시 plain text.
- Modify `web/frontend-next/src/app/content/[slug]/RelatedContent.tsx` — 임베드 시 `/embed` href.
- Modify `web/frontend-next/src/app/content/[slug]/ContentView.tsx` — `embed` prop, 네비게이션 억제.
- Create `web/frontend-next/src/app/content/[slug]/embed/page.tsx` — static 임베드 라우트.
- Modify `web/frontend-next/e2e/content-landing.spec.ts` — nav 노출/미노출 E2E.

**Phase 3 — toss-miniapp**
- Modify `web/toss-miniapp/src/shared/api/paths.ts` + `packages/shared/api/paths.ts` — `content()` 경로.
- Modify `web/toss-miniapp/src/api/client.ts` — `SITE_BASE` + `buildSiteUrl`.
- Create `web/toss-miniapp/src/types/content.ts` — `ContentListItem`.
- Create `web/toss-miniapp/src/components/ContentCard.tsx` — 카드 UI.
- Create `web/toss-miniapp/src/pages/content.tsx` + `web/toss-miniapp/pages/content.tsx` — 목록 화면 + wrapper.
- Create `web/toss-miniapp/src/pages/content-article.tsx` + `web/toss-miniapp/pages/content-article.tsx` — WebView 상세 + wrapper.
- Modify `web/toss-miniapp/src/pages/index.tsx` — 홈 미리보기 섹션.
- Regenerate `web/toss-miniapp/src/router.gen.ts` — Granite.

---

## Task 1: 콘텐츠 인덱스 동기화 스크립트 (`sync_content_index.py`)

**Files:**
- Create: `scripts/sync_content_index.py`
- Test: `scripts/tests/test_sync_content_index.py`

**Interfaces:**
- Produces:
  - `read_posts(posts_path: Path = POSTS_PATH) -> list[dict]`
  - `build_index(posts: list[dict]) -> list[dict]` — published-only, `published_at` DESC(동률 slug ASC), 인덱스 필드만
  - `write_index(index: list[dict], out_path: Path = INDEX_PATH) -> None` — 원자적 tmp→rename
  - `check(posts_path=POSTS_PATH, index_path=INDEX_PATH) -> bool`
  - `main(argv=None) -> int` — `--check` 지원, `python -m scripts.sync_content_index`
  - 상수 `INDEX_FIELDS`, `POSTS_PATH`, `INDEX_PATH`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_sync_content_index.py`:

```python
"""sync_content_index 투영/검증 테스트 — fixture 기반(실 posts.json 비의존)."""

import json
import tempfile
import unittest
from pathlib import Path


def make_posts():
    """published 2건 + draft 1건. published_at 오름차순으로 배치해 정렬 검증."""
    base = {
        "series": "value",
        "eyebrow": "가성비 랭킹",
        "summary": "요약",
        "cover_image": "/content/instagram/x/cover.png",
        "cover_alt": "커버",
        "data_as_of": "2026-07-10",
    }
    return [
        {**base, "slug": "older", "status": "published", "title": "옛글",
         "published_at": "2026-07-10"},
        {**base, "slug": "draft-one", "status": "draft", "title": "초안",
         "published_at": None},
        {**base, "slug": "newer", "status": "published", "title": "새글",
         "published_at": "2026-07-20"},
    ]


class TestBuildIndex(unittest.TestCase):
    def test_excludes_draft(self):
        from scripts.sync_content_index import build_index

        slugs = [p["slug"] for p in build_index(make_posts())]
        self.assertEqual(slugs, ["newer", "older"])  # draft 제외 + published_at DESC

    def test_only_index_fields(self):
        from scripts.sync_content_index import build_index, INDEX_FIELDS

        item = build_index(make_posts())[0]
        self.assertEqual(set(item.keys()), set(INDEX_FIELDS))
        self.assertNotIn("status", item)

    def test_missing_required_field_raises(self):
        from scripts.sync_content_index import build_index

        posts = make_posts()
        posts[2]["title"] = ""  # published 인데 필수 필드 결손
        with self.assertRaises(ValueError):
            build_index(posts)


class TestWriteAndCheck(unittest.TestCase):
    def test_atomic_write_no_tmp_left(self):
        from scripts.sync_content_index import build_index, write_index

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "content_index.json"
            write_index(build_index(make_posts()), out)
            self.assertTrue(out.exists())
            leftovers = [p.name for p in Path(d).glob("*.tmp-*")]
            self.assertEqual(leftovers, [])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual([x["slug"] for x in data], ["newer", "older"])

    def test_check_pass_and_drift(self):
        from scripts.sync_content_index import build_index, write_index, check

        with tempfile.TemporaryDirectory() as d:
            posts = Path(d) / "posts.json"
            index = Path(d) / "content_index.json"
            posts.write_text(json.dumps(make_posts()), encoding="utf-8")
            write_index(build_index(make_posts()), index)
            self.assertTrue(check(posts, index))  # 일치
            index.write_text("[]", encoding="utf-8")
            self.assertFalse(check(posts, index))  # 드리프트


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest scripts.tests.test_sync_content_index -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sync_content_index'`

- [ ] **Step 3: Write the implementation**

Create `scripts/sync_content_index.py`:

```python
"""posts.json → 백엔드 content_index.json 투영 생성/검증.

백엔드는 Railway 배포 시 web/frontend-next 를 볼 수 없으므로, 발행 시점에
published 메타를 백엔드로 투영해 커밋한다(생성 아티팩트, router.gen.ts 와 동일 철학).
--check 는 커밋된 인덱스가 posts.json 투영과 일치하는지 CI 에서 검증한다(드리프트 차단).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS_PATH = ROOT / "web" / "frontend-next" / "src" / "content" / "instagram" / "posts.json"
INDEX_PATH = ROOT / "web" / "backend" / "content" / "content_index.json"

# content_index 로 투영하는 메타 필드 (본문/구조 필드는 웹이 렌더하므로 제외).
INDEX_FIELDS = (
    "slug",
    "series",
    "title",
    "eyebrow",
    "summary",
    "cover_image",
    "cover_alt",
    "data_as_of",
    "published_at",
)


def read_posts(posts_path: Path = POSTS_PATH) -> list[dict]:
    data = json.loads(posts_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"posts.json 이 배열이 아닙니다: {posts_path}")
    return data


def build_index(posts: list[dict]) -> list[dict]:
    """published 만, 인덱스 필드만, published_at DESC (동률 slug ASC)."""
    published = [p for p in posts if p.get("status") == "published"]
    for p in published:
        missing = [f for f in INDEX_FIELDS if not p.get(f)]
        if missing:
            raise ValueError(
                f"published 레코드 필수 필드 누락 [{p.get('slug')}]: {missing}"
            )
    published.sort(key=lambda p: p["slug"])  # 3차: slug ASC (stable sort)
    published.sort(key=lambda p: p["published_at"], reverse=True)  # 1차: 최신 우선
    return [{f: p[f] for f in INDEX_FIELDS} for p in published]


def _serialize(index: list[dict]) -> str:
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def write_index(index: list[dict], out_path: Path = INDEX_PATH) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f"{out_path.name}.tmp-{os.getpid()}")
    tmp.write_text(_serialize(index), encoding="utf-8")
    tmp.replace(out_path)  # 원자적 rename


def check(posts_path: Path = POSTS_PATH, index_path: Path = INDEX_PATH) -> bool:
    expected = _serialize(build_index(read_posts(posts_path)))
    actual = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    return actual == expected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="content_index.json 생성/검증")
    parser.add_argument(
        "--check", action="store_true", help="드리프트 검사(파일을 쓰지 않음)"
    )
    args = parser.parse_args(argv)
    if args.check:
        if check():
            print("content_index.json: in sync")
            return 0
        print(
            "content_index.json: DRIFT — `python -m scripts.sync_content_index` 실행 후 커밋",
            file=sys.stderr,
        )
        return 1
    write_index(build_index(read_posts()))
    print(f"content_index.json 갱신: {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest scripts.tests.test_sync_content_index -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Format & lint**

Run: `ruff format scripts/sync_content_index.py scripts/tests/test_sync_content_index.py && ruff check scripts/sync_content_index.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add scripts/sync_content_index.py scripts/tests/test_sync_content_index.py
git commit -m "feat(content): posts.json→backend content_index 동기화 스크립트"
```

---

## Task 2: `content_index.json` 생성 아티팩트 커밋

**Files:**
- Create: `web/backend/content/content_index.json` (스크립트 산출물)

**Interfaces:**
- Consumes: Task 1의 `python -m scripts.sync_content_index`

- [ ] **Step 1: 인덱스 생성**

Run: `.venv/bin/python -m scripts.sync_content_index`
Expected: `content_index.json 갱신: .../web/backend/content/content_index.json`

- [ ] **Step 2: 산출물 검증**

Run: `.venv/bin/python -c "import json; d=json.load(open('web/backend/content/content_index.json')); print(len(d), [x['slug'] for x in d]); assert all('cover_image' in x for x in d); assert [x['published_at'] for x in d]==sorted([x['published_at'] for x in d], reverse=True)"`
Expected: `4 [...]` (published 4건, published_at 내림차순), assertion 통과

- [ ] **Step 3: --check 자기검증**

Run: `.venv/bin/python -m scripts.sync_content_index --check`
Expected: `content_index.json: in sync` (exit 0)

- [ ] **Step 4: Commit**

```bash
git add web/backend/content/content_index.json
git commit -m "feat(content): backend content_index.json 초기 생성"
```

---

## Task 3: `FRONTEND_BASE_URL` 공용 모듈 추출

**Files:**
- Create: `web/backend/frontend_config.py`
- Modify: `web/backend/routers/sitemap.py:26`

**Interfaces:**
- Produces: `frontend_config.FRONTEND_BASE_URL: str` (env `FRONTEND_BASE_URL`, 기본 `https://apt-recom.kr`, 끝 슬래시 제거)

- [ ] **Step 1: Write the failing test** (임시 스모크 — Step 4에서 제거)

Run: `cd web/backend && ../../.venv/bin/python -c "from frontend_config import FRONTEND_BASE_URL; print(FRONTEND_BASE_URL)"`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontend_config'`

- [ ] **Step 2: Create the module**

Create `web/backend/frontend_config.py`:

```python
"""프론트엔드(웹) 오리진 — sitemap·content 등이 절대 URL 생성에 공유한다.

값의 단일 출처. 신규 소비 모듈은 로컬 재정의 대신 여기서 import 한다.
"""

import os

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://apt-recom.kr").rstrip("/")
```

- [ ] **Step 3: sitemap.py 를 공용 모듈로 전환**

In `web/backend/routers/sitemap.py`, replace line 26:

```python
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://apt-recom.kr").rstrip("/")
```

with:

```python
from frontend_config import FRONTEND_BASE_URL
```

(파일 상단의 다른 import 와 함께 배치. `os` 가 sitemap.py의 다른 곳에서 쓰이지 않으면 `import os` 도 정리.)

- [ ] **Step 4: Verify import & sitemap 모듈 로드**

Run: `cd web/backend && ../../.venv/bin/python -c "from frontend_config import FRONTEND_BASE_URL; import routers.sitemap; print('ok', FRONTEND_BASE_URL)"`
Expected: `ok https://apt-recom.kr`

- [ ] **Step 5: Format & lint**

Run: `ruff format web/backend/frontend_config.py web/backend/routers/sitemap.py && ruff check web/backend/frontend_config.py web/backend/routers/sitemap.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add web/backend/frontend_config.py web/backend/routers/sitemap.py
git commit -m "refactor(backend): FRONTEND_BASE_URL 공용 모듈 추출"
```

---

## Task 4: `GET /api/content` 라우터 + 등록 + 테스트

**Files:**
- Create: `web/backend/routers/content.py`
- Modify: `web/backend/main.py:45` (import), `web/backend/main.py:118` (include_router)
- Test: `web/backend/tests/test_core.py`

**Interfaces:**
- Consumes: `frontend_config.FRONTEND_BASE_URL`, `web/backend/content/content_index.json`
- Produces:
  - `content.router` (APIRouter, `GET /content`)
  - `content.load_index(index_path: Path = INDEX_PATH) -> list[dict]` — 누락/손상 시 `HTTPException(500)`
  - `content.list_content() -> list[dict]` — 항목 키: `slug, series, title, eyebrow, summary, cover_image_url, cover_alt, data_as_of, published_at`

- [ ] **Step 1: Write the failing tests**

In `web/backend/tests/test_core.py`, add near the 대시보드 테스트 블록 (같은 클래스/스코프 관례를 따를 것):

```python
    @test("콘텐츠 /content: 목록 구조 + 절대 커버 URL + published_at DESC")
    def test_content_list_structure():
        from routers.content import list_content

        items = list_content()
        assert isinstance(items, list), "배열 아님"
        if items:
            it = items[0]
            for k in [
                "slug",
                "series",
                "title",
                "eyebrow",
                "summary",
                "cover_image_url",
                "cover_alt",
                "data_as_of",
                "published_at",
            ]:
                assert k in it, f"응답에 {k} 없음"
            assert it["cover_image_url"].startswith("http"), "cover_image_url 절대 URL 아님"
            dates = [x["published_at"] for x in items]
            assert dates == sorted(dates, reverse=True), "published_at 내림차순 아님"

    @test("콘텐츠 load_index 계약: 빈 배열 파일 → [], 누락 파일 → 500")
    def test_content_index_contract():
        import tempfile
        from pathlib import Path
        from fastapi import HTTPException
        from routers.content import load_index

        with tempfile.TemporaryDirectory() as d:
            empty = Path(d) / "content_index.json"
            empty.write_text("[]", encoding="utf-8")
            assert load_index(empty) == [], "빈 배열 파일은 [] 여야"

            missing = Path(d) / "nope.json"
            raised = False
            try:
                load_index(missing)
            except HTTPException as e:
                raised = True
                assert e.status_code == 500, f"누락 파일 status={e.status_code}"
            assert raised, "누락 파일인데 예외 없음"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | grep -i "content\|FAIL\|Error" | head`
Expected: FAIL — `ModuleNotFoundError: No module named 'routers.content'`

- [ ] **Step 3: Create the router**

Create `web/backend/routers/content.py`:

```python
"""GET /api/content — 발행된 콘텐츠 목록(메타).

content_index.json(scripts.sync_content_index 생성물)을 읽어 published 목록을
반환한다. 상세 본문은 프론트(/content/[slug]/embed)가 렌더하므로 여기서는
목록 메타 + 커버 절대 URL 만 제공한다.

파일 누락/손상은 "발행분 없음"(정상 [])과 구분되는 배포 결함이므로 5xx 로 드러낸다.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from frontend_config import FRONTEND_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()

INDEX_PATH = Path(__file__).resolve().parent.parent / "content" / "content_index.json"


def load_index(index_path: Path = INDEX_PATH) -> list[dict]:
    """인덱스 파일을 읽어 목록 반환. 파일 누락/손상/형식오류는 배포 결함 → 500."""
    try:
        raw = index_path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        logger.error("content_index.json 없음: %s", index_path)
        raise HTTPException(
            status_code=500, detail="content_index.json 없음 — 발행/배포 확인"
        ) from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("content_index.json 파싱 실패: %s", e)
        raise HTTPException(
            status_code=500, detail="content_index.json 파싱 실패"
        ) from e
    if not isinstance(data, list):
        logger.error("content_index.json 배열 아님")
        raise HTTPException(status_code=500, detail="content_index.json 형식 오류")
    return data


@router.get("/content")
def list_content() -> list[dict]:
    """published_at DESC 로 이미 정렬된 인덱스를 그대로 노출 + 커버 절대 URL."""
    return [
        {
            "slug": it["slug"],
            "series": it["series"],
            "title": it["title"],
            "eyebrow": it["eyebrow"],
            "summary": it["summary"],
            "cover_image_url": f"{FRONTEND_BASE_URL}{it['cover_image']}",
            "cover_alt": it["cover_alt"],
            "data_as_of": it["data_as_of"],
            "published_at": it["published_at"],
        }
        for it in load_index()
    ]
```

- [ ] **Step 4: Register the router in main.py**

In `web/backend/main.py`, add `content` to the `from routers import (...)` block (line ~45), and add after line 117 (`codes` 등록 부근, `/api` prefix 그룹):

```python
app.include_router(content.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | tail -5`
Expected: 전체 PASS (content 2건 포함). 개별 확인: 출력에 "콘텐츠 /content" / "콘텐츠 load_index 계약" PASS.

- [ ] **Step 6: Smoke the endpoint**

Run: `cd web/backend && ../../.venv/bin/python -c "from routers.content import list_content; r=list_content(); print(len(r), r[0]['cover_image_url'])"`
Expected: `4 https://apt-recom.kr/content/instagram/.../cover.png`

- [ ] **Step 7: Format & lint**

Run: `ruff format web/backend/routers/content.py && ruff check web/backend/routers/content.py`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add web/backend/routers/content.py web/backend/main.py web/backend/tests/test_core.py
git commit -m "feat(content): GET /api/content 발행 목록 엔드포인트"
```

---

## Task 5: 발행 자동화(`--publish`) + CI 드리프트 가드

**Files:**
- Modify: `scripts/insta_cards/cli.py:192-194`
- Create: `.github/workflows/ci-content-index.yml`

**Interfaces:**
- Consumes: Task 1의 `build_index`, `read_posts`, `write_index`

- [ ] **Step 1: `--publish` 경로에 인덱스 생성 연결**

In `scripts/insta_cards/cli.py`, replace lines 192-194:

```python
    if args.publish:
        posts_path = publish_to_frontend(to_json_dict(pub), final_dir / "01-cover.png")
        print(f"frontend: {posts_path} 갱신 + cover 복사 — posts.json·cover 커밋 필요")
```

with:

```python
    if args.publish:
        posts_path = publish_to_frontend(to_json_dict(pub), final_dir / "01-cover.png")
        print(f"frontend: {posts_path} 갱신 + cover 복사 — posts.json·cover 커밋 필요")
        # 백엔드는 frontend 파일을 못 읽으므로 published 메타를 투영해 커밋(생성물).
        from scripts.sync_content_index import build_index, read_posts, write_index

        write_index(build_index(read_posts()))
        print("backend: content_index.json 갱신 — 커밋 필요")
```

- [ ] **Step 2: Verify import path resolves**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/insta_cards/cli.py').read()); from scripts.sync_content_index import build_index, read_posts, write_index; print('imports ok')"`
Expected: `imports ok`

- [ ] **Step 3: Create the CI drift workflow**

Create `.github/workflows/ci-content-index.yml`:

```yaml
name: Content Index Drift Check

on:
  pull_request:
    paths:
      - 'web/frontend-next/src/content/instagram/posts.json'
      - 'web/backend/content/content_index.json'
      - 'scripts/sync_content_index.py'

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      # stdlib 만 사용 — 별도 의존성 설치 불필요.
      - name: Check content_index drift
        run: python -m scripts.sync_content_index --check
```

- [ ] **Step 4: Verify workflow YAML is valid**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci-content-index.yml')); print('yaml ok')"`
Expected: `yaml ok` (yaml 미설치 시: `ruff check` 로 대체 불가 — 대신 육안 확인 후 진행)

- [ ] **Step 5: Format & lint the modified script**

Run: `ruff format scripts/insta_cards/cli.py && ruff check scripts/insta_cards/cli.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add scripts/insta_cards/cli.py .github/workflows/ci-content-index.yml
git commit -m "feat(content): --publish 인덱스 자동생성 + CI 드리프트 가드"
```

---

## Task 6: 임베드 컨텍스트 + `ApartmentLink` 임베드 대응

**Files:**
- Create: `web/frontend-next/src/app/content/[slug]/EmbedContext.tsx`
- Modify: `web/frontend-next/src/app/content/[slug]/ApartmentLink.tsx`

**Interfaces:**
- Produces:
  - `EmbedContext: React.Context<boolean>` (기본 false)
  - `EmbedProvider({ embed, children }): JSX.Element`
- Consumes: `ApartmentLink`가 `useContext(EmbedContext)`로 임베드 여부 판단

- [ ] **Step 1: Create the context + provider (client)**

Create `web/frontend-next/src/app/content/[slug]/EmbedContext.tsx`:

```tsx
"use client";

import { createContext } from "react";

/**
 * 임베드(미니앱 WebView) 렌더 여부. true면 웹 전용 네비게이션(단지 링크 등)을 감춘다.
 * RSC 에서 Provider 는 client 경계여야 하므로 별도 client 모듈로 분리한다.
 */
export const EmbedContext = createContext(false);

export function EmbedProvider({
  embed,
  children,
}: {
  embed: boolean;
  children: React.ReactNode;
}) {
  return <EmbedContext.Provider value={embed}>{children}</EmbedContext.Provider>;
}
```

- [ ] **Step 2: `ApartmentLink`가 임베드 시 plain text 렌더**

Replace `web/frontend-next/src/app/content/[slug]/ApartmentLink.tsx` entirely:

```tsx
"use client";

import { useContext } from "react";
import Link from "next/link";
import { logEvent } from "@/lib/logEvent";
import { EmbedContext } from "./EmbedContext";

/** 단지 상세 링크 + content_apartment_click 이벤트. pnu 없거나 임베드면 텍스트만. */
export function ApartmentLink({
  slug,
  pnu,
  rank,
  name,
}: {
  slug: string;
  pnu: string | null;
  rank: number;
  name: string;
}) {
  const embed = useContext(EmbedContext);
  if (embed || !pnu)
    return <span className="font-semibold text-gray-900">{name}</span>;
  return (
    <Link
      href={`/apartment/${pnu}`}
      className="font-semibold text-blue-700 hover:underline"
      onClick={() => logEvent("content_apartment_click", { slug, pnu, rank })}
    >
      {name}
    </Link>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd web/frontend-next && npx tsc --noEmit`
Expected: exit 0 (no errors)

- [ ] **Step 4: Commit**

```bash
git add "web/frontend-next/src/app/content/[slug]/EmbedContext.tsx" "web/frontend-next/src/app/content/[slug]/ApartmentLink.tsx"
git commit -m "feat(content): 임베드 컨텍스트 + 단지 링크 임베드 대응"
```

---

## Task 7: `ContentView` 임베드 prop + 임베드 라우트

**Files:**
- Modify: `web/frontend-next/src/app/content/[slug]/ContentView.tsx:68-88`
- Modify: `web/frontend-next/src/app/content/[slug]/RelatedContent.tsx:10-22`
- Create: `web/frontend-next/src/app/content/[slug]/embed/page.tsx`

**Interfaces:**
- Consumes: `EmbedProvider` (Task 6), `getPublishedPost`/`getPublishedPosts`, `ContentView`
- Produces:
  - `ContentView({ post, embed? }): JSX.Element`
  - `RelatedContent({ currentSlug, embed? }): JSX.Element`
  - route `/content/[slug]/embed` (static, noindex)

- [ ] **Step 1: `RelatedContent`에 embed prop 추가**

In `web/frontend-next/src/app/content/[slug]/RelatedContent.tsx`, change the signature (line 10) and the `href` (line 22):

```tsx
export function RelatedContent({
  currentSlug,
  embed = false,
}: {
  currentSlug: string;
  embed?: boolean;
}) {
```

and the Link href:

```tsx
              href={embed ? `/content/${post.slug}/embed` : `/content/${post.slug}`}
```

- [ ] **Step 2: `ContentView`에 embed prop + 네비게이션 억제**

Replace the `ContentView` function (lines 68-88) in `web/frontend-next/src/app/content/[slug]/ContentView.tsx`:

```tsx
export function ContentView({
  post,
  embed = false,
}: {
  post: ContentPost;
  embed?: boolean;
}) {
  const ctas = post.map_ctas.map((cta) => ({
    id: cta.id,
    label: cta.label,
    href: buildMapCtaHref(post, cta),
  }));
  return (
    <EmbedProvider embed={embed}>
      <article className="mx-auto max-w-xl px-4 pb-28 pt-6">
        {!embed && (
          <div className="mb-5">
            <SiteNav from="content" />
          </div>
        )}
        <ContentHero post={post} />
        <ConditionChips post={post} />
        <SeriesBody post={post} />
        <MethodologyNote post={post} />
        {post.series === "trade_top" && !embed && <DashboardCta slug={post.slug} />}
        {!embed && <ContentActions slug={post.slug} ctas={ctas} />}
        <RelatedContent currentSlug={post.slug} embed={embed} />
      </article>
    </EmbedProvider>
  );
}
```

Add the import at the top of `ContentView.tsx` (with the other local imports):

```tsx
import { EmbedProvider } from "./EmbedContext";
```

- [ ] **Step 3: Create the embed route**

Create `web/frontend-next/src/app/content/[slug]/embed/page.tsx`:

```tsx
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getPublishedPost, getPublishedPosts } from "@/lib/instagramContent";
import { ContentView } from "../ContentView";

// 일반 상세(page.tsx)와 동일한 검증된 ISR 패턴 — 정적 프리렌더 + 미발행 slug 404.
export const revalidate = 3600;
export const dynamicParams = true;

export function generateStaticParams() {
  return getPublishedPosts().map((p) => ({ slug: p.slug }));
}

type PageParams = { slug: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<PageParams>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  // 임베드는 미니앱 WebView 전용 — 중복 콘텐츠 방지로 noindex.
  if (!post) return { title: "콘텐츠를 찾을 수 없습니다", robots: { index: false } };
  return { title: post.title, description: post.summary, robots: { index: false } };
}

export default async function ContentEmbedPage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { slug } = await params;
  const post = getPublishedPost(slug);
  if (!post) notFound();
  return <ContentView post={post} embed />;
}
```

- [ ] **Step 4: Typecheck**

Run: `cd web/frontend-next && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 5: Build — 임베드 라우트 정적 생성 확인 (ISR 보존)**

Run: `cd web/frontend-next && npm run build 2>&1 | grep -i "content/\[slug\]"`
Expected: 빌드 성공 + `/content/[slug]` 와 `/content/[slug]/embed` 두 라우트가 프리렌더 목록에 표기 (에러 없이 완료)

- [ ] **Step 6: Commit**

```bash
git add "web/frontend-next/src/app/content/[slug]/ContentView.tsx" "web/frontend-next/src/app/content/[slug]/RelatedContent.tsx" "web/frontend-next/src/app/content/[slug]/embed/page.tsx"
git commit -m "feat(content): 임베드 전용 static 라우트 + 웹 네비게이션 억제"
```

---

## Task 8: 임베드 네비게이션 E2E

**Files:**
- Modify: `web/frontend-next/e2e/content-landing.spec.ts`

**Interfaces:**
- Consumes: `firstPost.slug` (기존 spec 상단에서 posts.json 로 산출), 라우트 `/content/[slug]` · `/content/[slug]/embed`

- [ ] **Step 1: Write the E2E tests**

Append inside the `test.describe("/content 콘텐츠 랜딩", () => { ... })` block in `web/frontend-next/e2e/content-landing.spec.ts`:

```typescript
  test("일반 상세 — SiteNav 노출", async ({ page }) => {
    await page.goto(`/content/${firstPost.slug}`);
    await expect(
      page.getByRole("navigation", { name: "주요 화면 이동" }),
    ).toBeVisible();
  });

  test("임베드 상세 — SiteNav·대시보드 CTA 미노출", async ({ page }) => {
    await page.goto(`/content/${firstPost.slug}/embed`);
    await expect(
      page.getByRole("navigation", { name: "주요 화면 이동" }),
    ).toHaveCount(0);
    // 지도 CTA(홈으로) 링크가 임베드엔 없어야
    await expect(page.locator('a[href^="/?"]')).toHaveCount(0);
  });

  test("임베드 관련 아티클 — 링크가 embed 유지", async ({ page }) => {
    await page.goto(`/content/${firstPost.slug}/embed`);
    const related = page.locator('a[href^="/content/"][href$="/embed"]');
    // published ≥ 2 이므로 관련글 최소 1건 (RelatedContent RELATED_LIMIT=2)
    await expect(related.first()).toBeVisible();
  });
```

- [ ] **Step 2: Run the E2E suite**

Run: `cd web/frontend-next && npm run e2e -- content-landing`
Expected: 신규 3 test 포함 전체 PASS (Playwright dev 서버 자동 기동 설정에 의존 — 기존 spec 과 동일 실행 방식)

- [ ] **Step 3: Commit**

```bash
git add web/frontend-next/e2e/content-landing.spec.ts
git commit -m "test(content): 임베드 네비게이션 노출/미노출 E2E"
```

---

## Task 9: 미니앱 API 경로 + `SITE_BASE`/`buildSiteUrl` + 타입

**Files:**
- Modify: `web/toss-miniapp/src/shared/api/paths.ts`
- Modify: `packages/shared/api/paths.ts`
- Modify: `web/toss-miniapp/src/api/client.ts`
- Create: `web/toss-miniapp/src/types/content.ts`

**Interfaces:**
- Produces:
  - `apiPaths.content(): string` → `'/api/content'`
  - `SITE_BASE: string`(client 내부), `buildSiteUrl(path: string, query?): string` (export)
  - `ContentListItem` 타입

- [ ] **Step 1: `apiPaths.content()` 추가 (양쪽 동기화)**

In BOTH `web/toss-miniapp/src/shared/api/paths.ts` AND `packages/shared/api/paths.ts`, add inside the `apiPaths` object (대시보드 그룹 아래):

```typescript
  // 콘텐츠
  content: () => '/api/content',
```

- [ ] **Step 2: `SITE_BASE` + `buildSiteUrl` 추가**

In `web/toss-miniapp/src/api/client.ts`, add after the `API_BASE` definition:

```typescript
// 프론트(웹) 오리진 — WebView 임베드 URL 등에 사용. 백엔드 API_BASE 와 별개 호스트.
// Phase 4 에서 plugin-env 도입 시 env 로 교체할 것.
const SITE_BASE = 'https://apt-recom.kr';
```

and add a new exported function (after `buildApiUrl`):

```typescript
/**
 * 프론트(웹) 절대 URL 조립 — WebView source URI 용. buildApiUrl 과 동일 인코딩,
 * host 만 SITE_BASE.
 */
export function buildSiteUrl(
  path: string,
  query?: RequestOptions['query']
): string {
  const url = `${SITE_BASE}${path}`;
  if (!query) return url;
  const search = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`
    )
    .join('&');
  return search ? `${url}?${search}` : url;
}
```

- [ ] **Step 3: `ContentListItem` 타입**

Create `web/toss-miniapp/src/types/content.ts`:

```typescript
/** GET /api/content 응답 항목 (web/backend/routers/content.py:list_content). */
export interface ContentListItem {
  slug: string;
  series: string;
  title: string;
  eyebrow: string;
  summary: string;
  cover_image_url: string;
  cover_alt: string;
  data_as_of: string;
  published_at: string;
}
```

- [ ] **Step 4: Typecheck**

Run: `cd web/toss-miniapp && npx tsc --noEmit`
Expected: exit 0 (intro.tsx 기존 이슈는 이미 해소됨 — router.gen 에 /intro 등록 완료)

- [ ] **Step 5: Commit**

```bash
git add web/toss-miniapp/src/shared/api/paths.ts packages/shared/api/paths.ts web/toss-miniapp/src/api/client.ts web/toss-miniapp/src/types/content.ts
git commit -m "feat(miniapp): content API 경로 + buildSiteUrl + ContentListItem"
```

---

## Task 10: `ContentCard` 컴포넌트

**Files:**
- Create: `web/toss-miniapp/src/components/ContentCard.tsx`

**Interfaces:**
- Consumes: `ContentListItem` (Task 9)
- Produces: `default ContentCard({ item: ContentListItem; onPress: () => void })`

- [ ] **Step 1: Create the component**

Create `web/toss-miniapp/src/components/ContentCard.tsx`:

```tsx
import React from 'react';
import {
  Image,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type { ContentListItem } from '../types/content';

interface Props {
  item: ContentListItem;
  onPress: () => void;
}

/** 콘텐츠 카드 — 홈 미리보기와 목록 화면 공용. */
export default function ContentCard({ item, onPress }: Props) {
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      <Image
        source={{ uri: item.cover_image_url }}
        style={styles.cover}
        accessibilityLabel={item.cover_alt}
      />
      <View style={styles.body}>
        <Text style={styles.eyebrow}>{item.eyebrow}</Text>
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.summary} numberOfLines={2}>
          {item.summary}
        </Text>
        <Text style={styles.meta}>기준일 {item.data_as_of}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: '#EEF1F4',
  },
  cover: {
    width: 84,
    height: 84,
    borderRadius: 12,
    backgroundColor: '#EEF1F4',
  },
  body: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#12B886', fontSize: 12, fontWeight: '700' },
  title: { color: '#191F28', fontSize: 15, fontWeight: '800', marginTop: 2 },
  summary: { color: '#6B7684', fontSize: 13, marginTop: 4 },
  meta: { color: '#A2A8B4', fontSize: 11, marginTop: 6 },
});
```

- [ ] **Step 2: Typecheck**

Run: `cd web/toss-miniapp && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add web/toss-miniapp/src/components/ContentCard.tsx
git commit -m "feat(miniapp): ContentCard 카드 컴포넌트"
```

---

## Task 11: 콘텐츠 목록 화면 `/content` + 루트 wrapper

**Files:**
- Create: `web/toss-miniapp/src/pages/content.tsx`
- Create: `web/toss-miniapp/pages/content.tsx`

**Interfaces:**
- Consumes: `apiPaths.content()`, `ContentListItem`, `useApi`, `ContentCard`
- Produces: route `/content`, `navigation.navigate('/content-article', { slug })` 호출

- [ ] **Step 1: Create the list screen**

Create `web/toss-miniapp/src/pages/content.tsx`:

```tsx
import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { createRoute } from '@granite-js/react-native';
import { apiPaths } from '../shared/api/paths';
import type { ContentListItem } from '../types/content';
import { useApi } from '../hooks/useApi';
import ContentCard from '../components/ContentCard';

export const Route = createRoute('/content', {
  validateParams: (_params: Readonly<object | undefined>) =>
    ({}) as Record<string, never>,
  component: ContentListPage,
});

function ContentListPage() {
  const navigation = Route.useNavigation();
  const list = useApi<ContentListItem[]>(apiPaths.content());

  const goArticle = (slug: string) =>
    navigation.navigate('/content-article', { slug });

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <Text style={styles.title}>숫자로 보는 집 이야기</Text>
      <Text style={styles.subtitle}>
        카드뉴스의 순위·가격이 어떻게 나왔는지 데이터 근거를 공개해요.
      </Text>
      {list.loading ? (
        <View style={styles.status}>
          <ActivityIndicator color="#3182F6" />
        </View>
      ) : list.error ? (
        <Text style={styles.empty}>콘텐츠를 불러오지 못했어요.</Text>
      ) : !list.data || list.data.length === 0 ? (
        <Text style={styles.empty}>아직 발행된 콘텐츠가 없어요.</Text>
      ) : (
        <View style={styles.listGap}>
          {list.data.map((item) => (
            <ContentCard
              key={item.slug}
              item={item}
              onPress={() => goArticle(item.slug)}
            />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F6F8FB' },
  content: { padding: 18, paddingBottom: 44 },
  title: { color: '#191F28', fontSize: 22, fontWeight: '900' },
  subtitle: { color: '#6B7684', fontSize: 14, marginTop: 4, marginBottom: 16 },
  status: { paddingVertical: 40, alignItems: 'center' },
  empty: {
    color: '#A2A8B4',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 40,
  },
  listGap: { gap: 12 },
});
```

- [ ] **Step 2: Create the root wrapper**

Create `web/toss-miniapp/pages/content.tsx`:

```tsx
export { Route } from 'pages/content';
```

- [ ] **Step 3: Typecheck** (route 미등록 경고는 Task 13에서 해소되므로, 이 시점엔 `navigate('/content-article', …)` 타입 오류가 예상됨)

Run: `cd web/toss-miniapp && npx tsc --noEmit 2>&1 | grep -v "content-article" | grep -c "error TS" || true`
Expected: `/content-article` 미등록으로 인한 오류 외 신규 오류 0. (전체 통과는 Task 13에서.)

- [ ] **Step 4: Commit**

```bash
git add web/toss-miniapp/src/pages/content.tsx web/toss-miniapp/pages/content.tsx
git commit -m "feat(miniapp): 콘텐츠 목록 화면 /content"
```

---

## Task 12: WebView 상세 화면 `/content-article` + 루트 wrapper

**Files:**
- Create: `web/toss-miniapp/src/pages/content-article.tsx`
- Create: `web/toss-miniapp/pages/content-article.tsx`

**Interfaces:**
- Consumes: `buildSiteUrl` (Task 9), `WebView` from `@granite-js/native/react-native-webview`
- Produces: route `/content-article`, param `{ slug: string }` (SLUG_PATTERN 검증)

- [ ] **Step 1: Create the WebView detail screen**

Create `web/toss-miniapp/src/pages/content-article.tsx`:

```tsx
import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from '@granite-js/native/react-native-webview';
import { createRoute } from '@granite-js/react-native';
import { buildSiteUrl } from '../api/client';

// 원본(lib/instagramContent SLUG_PATTERN)과 동일 규칙으로 검증.
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
// 임베드 상세만 허용 — 그 외 origin/경로로의 이동은 차단(웹 이탈 방지).
const ALLOWED_PREFIX = 'https://apt-recom.kr/content/';

export const Route = createRoute('/content-article', {
  // slug 를 raw 문자열로 유지 (Granite 기본 JSON.parse 회피 — apt.tsx 패턴).
  parserParams: (params) => params,
  validateParams: (params: Readonly<object | undefined>) => {
    const p = params as { slug?: unknown } | undefined;
    const slug =
      typeof p?.slug === 'string' && SLUG_PATTERN.test(p.slug) ? p.slug : '';
    return { slug };
  },
  component: ContentArticlePage,
});

function ContentArticlePage() {
  const { slug } = Route.useParams();
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [reloadKey, setReloadKey] = useState(0);

  if (!slug) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>콘텐츠를 찾을 수 없어요.</Text>
      </View>
    );
  }

  const uri = buildSiteUrl(`/content/${slug}/embed`);
  const retry = () => {
    setStatus('loading');
    setReloadKey((k) => k + 1);
  };

  return (
    <View style={styles.root}>
      <WebView
        key={reloadKey}
        source={{ uri }}
        style={styles.webview}
        originWhitelist={['https://*']}
        onLoadStart={() => setStatus('loading')}
        onLoadEnd={() => setStatus((s) => (s === 'error' ? s : 'ok'))}
        onError={() => setStatus('error')}
        onHttpError={() => setStatus('error')}
        onShouldStartLoadWithRequest={(req) =>
          req.url.startsWith(ALLOWED_PREFIX)
        }
      />
      {status === 'loading' && (
        <View style={styles.overlay} pointerEvents="none">
          <ActivityIndicator color="#3182F6" />
        </View>
      )}
      {status === 'error' && (
        <View style={styles.overlay}>
          <Text style={styles.empty}>불러오지 못했어요.</Text>
          <TouchableOpacity style={styles.retry} onPress={retry}>
            <Text style={styles.retryText}>다시 시도</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  webview: { flex: 1, backgroundColor: 'transparent' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
    gap: 12,
  },
  empty: { color: '#A2A8B4', fontSize: 14 },
  retry: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: '#3182F6',
  },
  retryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
});
```

- [ ] **Step 2: Create the root wrapper**

Create `web/toss-miniapp/pages/content-article.tsx`:

```tsx
export { Route } from 'pages/content-article';
```

- [ ] **Step 3: Typecheck** (여전히 router.gen 미등록 — Task 13 전까지 `/content-article`·`/content` 미등록 오류만 남음)

Run: `cd web/toss-miniapp && npx tsc --noEmit 2>&1 | grep "error TS" | grep -v "content-article\|'/content'" | head`
Expected: 라우트 미등록 외 신규 오류 없음(빈 출력)

- [ ] **Step 4: Commit**

```bash
git add web/toss-miniapp/src/pages/content-article.tsx web/toss-miniapp/pages/content-article.tsx
git commit -m "feat(miniapp): 콘텐츠 상세 WebView 화면 /content-article"
```

---

## Task 13: 홈 미리보기 섹션 + `router.gen.ts` 재생성

**Files:**
- Modify: `web/toss-miniapp/src/pages/index.tsx`
- Regenerate: `web/toss-miniapp/src/router.gen.ts` (Granite)

**Interfaces:**
- Consumes: `apiPaths.content()`, `ContentListItem`, `ContentCard`, route `/content`·`/content-article`

- [ ] **Step 1: 홈 import 추가**

In `web/toss-miniapp/src/pages/index.tsx`, add to imports:

```tsx
import type { ContentListItem } from '../types/content';
import ContentCard from '../components/ContentCard';
```

- [ ] **Step 2: 홈에 콘텐츠 데이터 + 네비게이션 추가**

In `HomePage()` (after the `recent` useApi around line 50-52), add:

```tsx
  const content = useApi<ContentListItem[]>(apiPaths.content());
  const goContent = () => navigation.navigate('/content', {});
  const goArticle = (slug: string) =>
    navigation.navigate('/content-article', { slug });
```

- [ ] **Step 3: 홈에 미리보기 섹션 렌더**

In `web/toss-miniapp/src/pages/index.tsx`, add just before the closing `</ScrollView>` (after `<RankingCard state={ranking} />`):

```tsx
      {content.data && content.data.length > 0 && (
        <View style={styles.contentSection}>
          <View style={styles.contentHead}>
            <Text style={styles.contentTitle}>숫자로 보는 집 이야기</Text>
            <TouchableOpacity onPress={goContent} activeOpacity={0.8}>
              <Text style={styles.contentMore}>전체 보기</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.contentGap}>
            {content.data.slice(0, 2).map((item) => (
              <ContentCard
                key={item.slug}
                item={item}
                onPress={() => goArticle(item.slug)}
              />
            ))}
          </View>
        </View>
      )}
```

- [ ] **Step 4: 홈 스타일 추가**

In the `StyleSheet.create({ ... })` of `index.tsx`, add:

```tsx
  contentSection: { marginTop: 20 },
  contentHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  contentTitle: { color: '#191F28', fontSize: 18, fontWeight: '900' },
  contentMore: { color: '#3182F6', fontSize: 13, fontWeight: '700' },
  contentGap: { gap: 12 },
```

- [ ] **Step 5: Regenerate router.gen.ts (Granite — 수동 편집 금지)**

Run: `cd web/toss-miniapp && npx granite build`
Expected: 빌드 과정에서 `src/router.gen.ts` 가 재생성되어 `/content`·`/content-article` 항목이 추가됨.

Verify: `git diff --stat web/toss-miniapp/src/router.gen.ts` 에 변경 표기, 그리고
`grep -c "content" web/toss-miniapp/src/router.gen.ts` ≥ 2.

> **환경상 `granite build`(네이티브)가 불가하면:** `npx granite dev` 를 실행해 라우터가 생성되는 즉시(콘솔에 dev 서버 준비 로그) 중단(Ctrl-C)한다. `granite dev`/`build` 모두 기동 시 `router.gen.ts` 를 재생성한다. **어느 경우에도 `router.gen.ts` 를 손으로 편집하지 않는다.**

- [ ] **Step 6: Typecheck (전체 통과)**

Run: `cd web/toss-miniapp && npx tsc --noEmit`
Expected: exit 0 — `/content`·`/content-article` 등록 완료로 Task 11·12의 미등록 오류가 모두 해소됨

- [ ] **Step 7: Commit**

```bash
git add web/toss-miniapp/src/pages/index.tsx web/toss-miniapp/src/router.gen.ts
git commit -m "feat(miniapp): 홈 콘텐츠 미리보기 섹션 + 라우트 등록"
```

---

## Final Verification (전체 통합)

- [ ] **백엔드 테스트 전체**

Run: `.venv/bin/python web/backend/tests/test_core.py 2>&1 | tail -3`
Expected: 전체 PASS

- [ ] **동기화 스크립트 테스트 + 드리프트 체크**

Run: `.venv/bin/python -m unittest scripts.tests.test_sync_content_index -v && .venv/bin/python -m scripts.sync_content_index --check`
Expected: unittest PASS + `content_index.json: in sync`

- [ ] **frontend-next 타입/빌드/E2E**

Run: `cd web/frontend-next && npx tsc --noEmit && npm run build && npm run e2e -- content-landing`
Expected: 모두 성공

- [ ] **미니앱 타입체크**

Run: `cd web/toss-miniapp && npx tsc --noEmit`
Expected: exit 0

- [ ] **수동 확인 (실행자 환경에서)**

미니앱 홈 → "숫자로 보는 집 이야기" 미리보기 노출 → "전체 보기" → 목록 → 카드 탭 → WebView 에서 임베드 아티클(웹 메뉴/CTA 없이) 렌더 → 관련 아티클 탭 시 임베드 유지 → 로드 실패 시 "다시 시도" 동작.

---

## Self-Review 결과

- **Spec coverage:** §4A(Task 1·2·4·5) / §4B embed 라우트·네비게이션 억제(Task 6·7·8) / §4C 미니앱 파일·wrapper·slug 검증·WebView 에러(Task 9~13) / §6 에러 계약(Task 4·11·12) / §7 테스트(Task 1·4·8 + Final) — 전 항목 대응 태스크 존재.
- **Placeholder scan:** 코드 스텝은 실제 구현/테스트 코드 포함, "적절히 처리" 류 없음.
- **Type consistency:** `build_index/write_index/read_posts/check`(Task 1) 시그니처가 Task 2·5 사용처와 일치. `load_index/list_content`(Task 4) 키가 test·미니앱 `ContentListItem`(Task 9)·`ContentCard`(Task 10) 필드와 일치(`cover_image_url` 등). `ContentView({post, embed})`·`RelatedContent({currentSlug, embed})`(Task 7)가 embed route(Task 7 Step 3) 호출과 일치. 라우트 `/content`·`/content-article` 명칭이 Task 11·12·13 전반 일관.
