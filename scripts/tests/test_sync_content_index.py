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
        {
            **base,
            "slug": "older",
            "status": "published",
            "title": "옛글",
            "published_at": "2026-07-10",
        },
        {
            **base,
            "slug": "draft-one",
            "status": "draft",
            "title": "초안",
            "published_at": None,
        },
        {
            **base,
            "slug": "newer",
            "status": "published",
            "title": "새글",
            "published_at": "2026-07-20",
        },
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
