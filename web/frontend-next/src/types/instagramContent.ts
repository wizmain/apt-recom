// posts.json(= 생성기 Publication 직렬화)의 TS 미러 — 스키마의 단일 진실원은
// scripts/insta_cards/publication.py. 필드 추가 시 양쪽 동시 수정 + SCHEMA_VERSION 확인.
export const SCHEMA_VERSION = 1;

export type Series =
  | "trade_top"
  | "compare"
  | "value"
  | "budget_choice"
  | "lifestyle";

export interface Metric {
  label: string;
  value: string;
  unit: string;
}

export interface Condition {
  label: string;
  value: string;
}

export interface ContentItem {
  rank: number;
  name: string;
  region: string | null;
  pnu: string | null;
  metrics: Metric[];
  reasons: string[];
}

export interface MapCta {
  id: string;
  label: string;
  nudges: string[];
  sigungu_code: string | null;
  region_label: string | null;
  filters: Record<string, number>;
}

export interface ComparisonColumn {
  name: string;
  values: string[];
}

export interface Comparison {
  row_labels: string[];
  columns: ComparisonColumn[];
}

export interface FitFor {
  a: string;
  b: string;
}

export interface Narrative {
  why: string[];
  fit_for: FitFor | null;
}

export interface ContentPost {
  schema_version: number;
  slug: string;
  status: "draft" | "published";
  series: Series;
  title: string;
  eyebrow: string;
  hook: string;
  summary: string;
  generated_at: string;
  published_at: string | null;
  data_as_of: string;
  period_label: string;
  cover_image: string;
  cover_alt: string;
  conditions: Condition[];
  items: ContentItem[];
  secondary_items: ContentItem[] | null;
  comparison: Comparison | null;
  narrative: Narrative;
  methodology: string[];
  caveats: string[];
  map_ctas: MapCta[];
}
