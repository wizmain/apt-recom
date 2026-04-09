// ── Dashboard ─────────────────────────────────────────────

export interface DashboardSummary {
  total_apartments: number;
  new_apartments_week: number;
  today_trades: number;
  yesterday_trades: number;
  satisfaction_rate: number;
  prev_satisfaction_rate: number;
  coverage_pct: number;
  uncovered_count: number;
}

export interface QualityItem {
  table: string;
  label: string;
  total_records: number;
  null_pct: number;
  coverage_pct: number;
  latest_update: string | null;
}

export interface DashboardQuality {
  quality: QualityItem[];
}

// ── Data ──────────────────────────────────────────────────

export interface TableStats {
  table: string;
  total_records: number;
  latest_update: string | null;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  data: T[];
}

export interface DataTableResponse extends PaginatedResponse<Record<string, unknown>> {
  table: string;
  columns: string[];
}

// ── Batch ─────────────────────────────────────────────────

export interface BatchHistoryItem {
  filename: string;
  batch_type: string | null;
  status: "success" | "warning" | "error" | "unknown";
  started_at: string | null;
  duration: string | null;
  total_records: number;
}

export interface BatchLogDetail {
  filename: string;
  content: string;
  size_bytes: number;
}

// ── Feedback ──────────────────────────────────────────────

export interface FeedbackItem {
  id: number;
  user_message: string;
  assistant_message: string;
  rating: number;
  tags: string[];
  comment: string;
  session_id: string | null;
  created_at: string | null;
}

export interface FeedbackTrendItem {
  period: string;
  total: number;
  likes: number;
  satisfaction_rate: number;
}

// ── Scoring ───────────────────────────────────────────────

export interface ScoringWeights {
  nudge_weights: Record<string, Record<string, number>>;
  max_distances: Record<string, number>;
}

export interface DistributionBucket {
  bucket: number;
  count: number;
  avg_distance_m: number;
}

export interface ScoringDistribution {
  nudge_id: string;
  primary_subtype: string;
  subtypes: string[];
  histogram: DistributionBucket[];
  stats: {
    total: number;
    avg_distance_m: number;
    min_distance_m: number;
    max_distance_m: number;
    median_distance_m: number;
  };
}

// ── Mgmt Cost ─────────────────────────────────────────────

export interface MgmtCostPreviewRow {
  pnu: string;
  year_month: string;
  kapt_name: string;
  cost_per_unit: number;
  common_cost: number;
  individual_cost: number;
  repair_fund: number;
  total_cost: number;
}

export interface NewAptItem {
  kapt_code: string;
  kapt_name: string;
  address: string;
  road_address: string;
  hhld: number;
}

export interface MgmtCostPreviewResponse {
  total: number;
  preview_count: number;
  rows: MgmtCostPreviewRow[];
  errors: string[];
  new_apts: NewAptItem[];
  new_apts_count: number;
}

export interface RegisterStatusResponse {
  status: "running" | "completed" | "failed";
  current: number;
  total: number;
  registered: number;
  errors: string[];
  message: string;
  elapsed_seconds: number;
}
