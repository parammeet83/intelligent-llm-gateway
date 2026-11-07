// Mirrors backend response shapes (backend/app/api/v1). Money values are decimal strings.

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string | null; details: Record<string, unknown> };
}

export interface HealthResponse {
  status: "ok";
  version: string;
  environment: "development" | "test" | "production";
  providers: string[];
  /** True when every enabled provider is the mock: all responses are simulated. */
  simulated_only: boolean;
}

export interface ReadyResponse {
  status: "ready" | "not_ready";
  checks: Record<string, "ok" | "pending" | "unavailable" | "unknown">;
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export type CostStatus = "reported" | "estimated" | "free_tier" | "unavailable";

export interface RequestSummary {
  id: string;
  tenant: string | null;
  client_request_id: string | null;
  status: string;
  error_code: string | null;
  task_type: string | null;
  prompt_version: string | null;
  routing_tier: string | null;
  policy_version: string | null;
  provider: string | null;
  model: string | null;
  attempt_count: number;
  fallback_used: boolean;
  simulated: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  actual_charge_usd: string | null;
  cost_status: CostStatus;
  estimated_list_cost_usd: string | null;
  list_cost_status: "estimated" | "unavailable";
  reason_codes: string[];
  score: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface Attempt {
  attempt: number;
  provider: string;
  model: string;
  reason_code: string;
  status: string;
  error_code: string | null;
  http_status: number | null;
  retry_after_s: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  actual_charge_usd: string | null;
  cost_status: CostStatus;
  estimated_list_cost_usd: string | null;
  list_cost_status: string;
  simulated: boolean;
  started_at: string;
}

export interface Candidate {
  provider: string;
  model_id: string;
  tier: string;
  eligible: boolean;
  exclusions: string[];
  worst_case_list_cost_usd: string | null;
  observed_p95_ms: number | null;
  simulated: boolean;
}

export interface Decision {
  policy_version?: string;
  task_type?: string;
  score?: number;
  computed_tier?: string;
  required_tier?: string;
  reason_codes?: string[];
  explanation?: string;
  contributions?: { feature: string; points: number; detail: string }[];
  selected?: Candidate | null;
  fallback_chain?: Candidate[];
  candidates?: Candidate[];
  execution?: { outcome: string; skipped: { model: string; reason: string }[] };
  rejected_before_routing?: boolean;
}

export interface RequestDetail extends RequestSummary {
  prompt_sha256: string | null;
  input_chars: number | null;
  decision: Decision | null;
  attempts: Attempt[];
}

export interface GroupStats {
  requests: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  actual_charge_usd: string;
  actual_charge_known_requests: number;
  actual_charge_unknown_requests: number;
  free_tier_requests: number;
  estimated_list_cost_usd: string;
  estimated_list_cost_known_requests: number;
  estimated_list_cost_unknown_requests: number;
  cost_per_successful_request_usd: string | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

export interface UsageSummary {
  window: { since: string; until: string; bucket: "hour" | "day" };
  truncated: boolean;
  totals: GroupStats & {
    rejected_rate_limit: number;
    rejected_budget: number;
    rejected_policy: number;
    pending: number;
    fallback_rate: number | null;
    rate_limit_rejection_rate: number | null;
    simulated_requests: number;
  };
  by_status: Record<string, number>;
  by_provider: (GroupStats & { provider: string })[];
  by_model: (GroupStats & { model: string })[];
  by_tier: (GroupStats & { tier: string; share: number | null })[];
  by_tenant: (GroupStats & { tenant: string })[] | null;
  timeseries: (GroupStats & { bucket: string })[];
  latency_histogram: { bucket_ms: string; count: number }[];
}

export interface BudgetPeriod {
  period: "daily" | "monthly";
  period_start: string;
  limit_usd: string;
  spent_usd: string;
  reserved_usd: string;
  remaining_usd: string;
}

export interface TenantView {
  id: string;
  slug: string;
  name: string;
  status: "active" | "suspended";
  rate_limit_rpm: number;
  daily_budget_usd: string | null;
  monthly_budget_usd: string | null;
  budget_basis: string;
  budgets: BudgetPeriod[];
  created_at: string | null;
  unrevoked_keys?: number;
}

export interface KeyView {
  id: string;
  name: string;
  prefix: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  expires_at: string | null;
  active: boolean;
}

export interface KeyCreated extends KeyView {
  api_key: string;
  warning: string;
}

export interface KeyRotated {
  old_key: KeyView;
  new_key: KeyView & { api_key: string };
  warning: string;
}

export interface ModelInfo {
  provider: string;
  model_id: string;
  display_name: string;
  tier: string;
  billing: string;
  capabilities: string[];
  context_window: number;
  max_output_tokens: number;
  enabled_in_registry: boolean;
  provider_enabled: boolean;
  preview: boolean;
  simulated: boolean;
  verified_on: string | null;
  source_url: string | null;
  list_price: {
    input_usd_per_mtok: string;
    output_usd_per_mtok: string;
    effective_date: string;
    source_url: string;
    simulated: boolean;
  } | null;
  runtime: {
    listed_by_provider: boolean | null;
    circuit: string;
    exclusion: string | null;
    latency_samples: number;
    observed_p95_ms: number | null;
  };
}

export interface ModelsResponse {
  policy_version: string;
  models: ModelInfo[];
}

export interface ProviderInfo {
  name: string;
  simulated: boolean;
  charge_basis: string;
  max_retries: number;
  quota_available: boolean;
  catalog_verified: boolean;
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
}

export interface AdminConfig {
  environment: string;
  policy: Record<string, unknown> & { version: string };
  providers: string[];
  simulated_only: boolean;
  settings: Record<string, string | number | boolean>;
}

export interface StrategyMetrics {
  cases: number;
  executed: number;
  failures: number;
  failure_rate: number | null;
  scorable: number;
  passed: number;
  pass_rate: number | null;
  pass_rate_wilson_95: [number, number] | null;
  by_difficulty: Record<string, { scorable: number; passed: number; pass_rate: number | null }>;
  estimated_list_cost_total_usd: string;
  estimated_list_cost_per_request_usd: string | null;
  estimated_list_cost_per_accepted_answer_usd: string | null;
  input_tokens: number;
  output_tokens: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  fallback_rate: number | null;
  provider_distribution: Record<string, number>;
  model_distribution: Record<string, number>;
  tier_distribution: Record<string, number>;
  not_auto_scorable: number;
  needs_human_review: number;
}

export interface Comparison {
  paired_cases: number;
  pass_rate_difference: number | null;
  pass_rate_difference_bootstrap_95: [number, number] | null;
  non_inferiority_margin: number;
  quality_rule_point_estimate_holds: boolean;
  non_inferiority_supported_by_ci: boolean;
  cost_per_accepted_answer_ratio: number | null;
  cost_rule_holds: boolean;
}

export interface EvalRun {
  id: string;
  label: string;
  strategy: string;
  dataset_version: string;
  policy_version: string | null;
  simulated: boolean;
  status: string;
  preregistration_sha256: string;
  summary: {
    metrics: StrategyMetrics | null;
    comparison_vs_baseline: Comparison | null;
    publishable: boolean;
    publishable_reasons: string[];
    label: string;
  } | null;
  // Only the registration fields the Evaluation page reads; the snapshot has many more.
  config_snapshot?: {
    execution_revision?: string | null;
    execution_schedule?: { day: number; days: number } | null;
    execution_recovery?: { day: number; executes: unknown[]; carried_over: number } | null;
  } | null;
  started_at: string;
  finished_at: string | null;
}

export interface EvalRunDetail extends EvalRun {
  results: {
    case_id: string;
    passed: boolean | null;
    score: number | null;
    provider: string | null;
    model: string | null;
    tier: string | null;
    fallback_used: boolean;
    error_code: string | null;
    latency_ms: number | null;
    estimated_list_cost_usd: string | null;
  }[];
}
