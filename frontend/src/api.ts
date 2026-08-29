const BASE = "/api";

export interface Summary {
  total_records: number;
  matched_count: number;
  resolved_with_reasoning_count: number;
  unresolved_exception_count: number;
  match_rate_pct: number;
  average_confidence_score: number;
  exception_breakdown: Record<string, number>;
}

export interface Transaction {
  order_id: string;
  match_status: string;
  confidence_score: number | null;
  amount_score: number | null;
  timing_score: number | null;
  reference_score: number | null;
  override_reason: string | null;
  explanation: string;
  explanation_source: string;
  category?: string | null;
}

export interface TransactionsResponse {
  count: number;
  transactions: Transaction[];
}

export interface RunResponse {
  status: string;
  run_summary: {
    total_records: number;
    matched_count: number;
    unresolved_exception_count: number;
    match_rate_pct: number;
    average_confidence_score: number;
    duration_seconds: number;
    explanation_sources: Record<string, number>;
  };
}

export interface AccuracyReport {
  overall_accuracy_pct: number;
  total_ground_truth_records: number;
  total_correct: number;
  total_incorrect: number;
  per_category: Record<string, {
    ground_truth_count: number;
    correct: number;
    incorrect: number;
    accuracy: number;
  }>;
}

export async function fetchSummary(): Promise<Summary> {
  const res = await fetch(`${BASE}/summary`);
  if (!res.ok) throw new Error(`GET /api/summary failed: ${res.status}`);
  return res.json();
}

export async function fetchTransactions(params?: {
  match_status?: string;
  category?: string;
}): Promise<TransactionsResponse> {
  const qs = new URLSearchParams();
  if (params?.match_status) qs.set("match_status", params.match_status);
  if (params?.category) qs.set("category", params.category);
  const url = `${BASE}/transactions${qs.toString() ? "?" + qs : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /api/transactions failed: ${res.status}`);
  return res.json();
}

export async function fetchTransaction(orderId: string): Promise<Transaction> {
  const res = await fetch(`${BASE}/transactions/${encodeURIComponent(orderId)}`);
  if (!res.ok) throw new Error(`GET /api/transactions/${orderId} failed: ${res.status}`);
  return res.json();
}

export async function fetchAccuracy(): Promise<AccuracyReport> {
  const res = await fetch(`${BASE}/accuracy`);
  if (!res.ok) throw new Error(`GET /api/accuracy failed: ${res.status}`);
  return res.json();
}

export async function runReconciliation(
  useLlm = true,
  fallbackRatio = 0.1,
  datasetSource: "sample" | "custom" = "sample",
): Promise<RunResponse> {
  const qs = new URLSearchParams({
    use_llm: String(useLlm),
    fallback_ratio: String(fallbackRatio),
    dataset_source: datasetSource,
  });
  const res = await fetch(`${BASE}/run?${qs}`, { method: "POST" });
  if (!res.ok) throw new Error(`POST /api/run failed: ${res.status}`);
  return res.json();
}

export interface AskResponse {
  answer: string;
  matched_transactions: Transaction[];
  match_type: "order_lookup" | "category_filter" | "no_match";
}

export async function askQuestion(question: string): Promise<AskResponse> {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`POST /api/ask failed: ${res.status}`);
  return res.json();
}
