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
