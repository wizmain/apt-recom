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

// ── Log Analytics ─────────────────────────────────────────

export type RangePreset = "24h" | "7d" | "30d" | "90d" | "custom";

export interface LogRange {
  preset: RangePreset;
  from?: string;  // ISO 8601 (custom 인 경우)
  to?: string;
}

export interface KeywordCount {
  keyword: string;
  count: number;
}

export interface NudgeComboCount {
  combo: string[];
  count: number;
}

export interface AptDetailCount {
  pnu: string;
  bld_nm: string | null;
  count: number;
}

export interface LogOverview {
  range: { from: string; to: string };
  dau: number;
  wau_devices: number;
  total_events: number;
  chat_sessions: number;
  terminated_rate: number;
  top_keywords: KeywordCount[];
  top_nudge_combos: NudgeComboCount[];
  top_apt_details: AptDetailCount[];
}

export interface LogTimelinePoint {
  ts: string;
  events: number;
  unique_devices: number;
  chats: number;
}

export interface LogTimelineResponse {
  granularity: "day" | "hour";
  points: LogTimelinePoint[];
}

export interface LogPaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface EventLogRow {
  id: number;
  device_id: string;
  event_type: string;
  event_name: string | null;
  payload_preview: string;
  created_at: string | null;
}

export interface ChatLogRow {
  id: number;
  device_id: string;
  user_message_preview: string;
  assistant_message_preview: string;
  tool_call_count: number;
  terminated_early: boolean;
  created_at: string | null;
}

export interface ChatLogDetail {
  id: number;
  device_id: string;
  session_id: string | null;
  user_message: string;
  assistant_message: string;
  tool_calls: Array<{ name?: string; arguments?: unknown }>;
  context: Record<string, unknown>;
  terminated_early: boolean;
  created_at: string | null;
}
