# CLAUDE.md — AI Finance Controller: Reconciliation Agent

## Project Context

This project is being built for a hackathon track called **"AI Finance Controller — Run the books and the cash position"**, sponsored by Razorpay (a payments/fintech company). The track thesis: verification capacity, not generation speed, is the bottleneck in finance operations. Reconciliation, settlement, and forecasting are still largely done by hand.

**What we're building:** An agent that performs **multi-source financial reconciliation** — matching transaction records across three independent data sources (an internal order ledger, a payment gateway settlement report, and a bank statement) to verify that money that was supposed to move actually moved correctly. This mirrors real reconciliation work done by finance/ops teams at any company that processes online payments.

**The judging bar (from the hackathon brief):**
- Throughput: process a 50+ record batch
- Measured accuracy: report an honest match rate, not a cherry-picked example
- Honest exceptions: categorize and explain records that could NOT be resolved, rather than hiding or force-matching them

**Builder profile:** Sayan, a CS/Data Science student (DSCE Bengaluru) with experience in ML, full-stack dev, and DSA/competitive programming. Has prior experience building a weighted-composite trust-scoring system (Conclave project) and an explainable CV defect detector (PCB project) — this project should reuse that "score + explain, don't just classify" pattern.

**Domain knowledge note for the executing LLM:** The user has limited finance domain knowledge. When generating explanations, documentation, or comments related to finance concepts (settlement, UTR, fees, TDS, etc.), write them in clear, plain language — do not assume finance background.

---

## Domain Glossary (for reference during implementation)

- **Payment gateway**: Middleman service (e.g. Razorpay) that processes online payments between customer and merchant.
- **Settlement**: The point where the gateway transfers collected money into the merchant's bank account — this happens with a delay ("settlement lag"), not instantly.
- **UTR (Unique Transaction Reference)**: A unique ID attached to a bank transfer, used to match bank records to gateway records.
- **Gross amount**: What the customer paid.
- **Fee/commission**: What the gateway deducts as its cut before paying out.
- **Net settled amount**: `gross_amount - fee_amount` — what the merchant actually receives.
- **Three-way match**: Comparing internal ledger vs. gateway report vs. bank statement to confirm consistency.
- **Reconciliation**: The overall process of proving these three independent records describe the same real-world events.

---

## Data Schema (already designed — do not redesign)

### Input 1: `internal_order_ledger.csv`
`order_id, customer_name, order_amount, order_date, payment_mode, status`

### Input 2: `gateway_settlement_report.csv`
`gateway_txn_id, order_ref, gross_amount, fee_pct, fee_amount, net_settled, utr, settlement_date`

### Input 3: `bank_statement.csv`
`bank_txn_id, utr, credited_amount, value_date, narration`

### Ground truth (private, matcher must NEVER read this): `ground_truth.json`
Maps each `order_id` (or synthetic key for orphan bank records) to its true injected category:
`CLEAN_MATCH, FEE_MISMATCH_EXPLAINABLE, TIMING_LAG_EXPLAINABLE, PARTIAL_SETTLEMENT_SPLIT, DUPLICATE_UTR_ERROR, ROUNDING_DRIFT_EXPLAINABLE, REFUND_NOT_REFLECTED, ORPHAN_NO_GATEWAY_MATCH, ORPHAN_NO_LEDGER_MATCH`

### Outputs to produce
- `match_report.csv`: per-transaction result — `order_id, match_status, confidence_score, amount_score, timing_score, reference_score, explanation`
- `exception_summary.json`: aggregate stats — total records, matched count, resolved-with-reasoning count, unresolved exception count, match rate %, exception breakdown by category

### Custom Dataset Upload
The system supports user-uploaded CSVs for reconciliation against the same schema above.

- **Upload flow:** `POST /api/upload` — accepts three files, runs normalization (auto-maps column names, normalizes dates/amounts/status), then validates against `EXPECTED_*_COLS` from `loader.py`. If auto-mapping can't resolve some columns, returns `422` with `status: "needs_mapping"` and a `session_id` for the confirm step.
- **Confirm mapping:** `POST /api/upload/confirm-mapping?session_id=...&ledger_mapping=...&gateway_mapping=...&bank_mapping=...` — re-runs normalization with user-provided manual column mappings, then commits to `data/custom/` if all three files become "ready".
- **Schema reference:** `GET /api/schema-template` — returns required columns, example rows, and accepted values for constrained fields per file type. `GET /api/schema-template/download?file=ledger|gateway|bank` — downloadable blank CSV template.
- **Reconciliation:** `POST /api/run?dataset_source=custom` — reads from `data/custom/` instead of `data/raw/`. Frontend gates this behind a successful normalization confirmation (the "Run Reconciliation" button is disabled until custom data is confirmed ready).
- **Accuracy grading:** unavailable for custom datasets (no ground truth), returns structured response with `"available": false`.
- **Schema enforcement:** normalization handles column renaming and value format fixes; loader.py schema validation runs as a final belt-and-suspenders check before writing to `data/custom/`.
- **Location:** `data/custom/` (gitignored, never committed).

### Data Normalization Layer (`src/ingestion/`)
Decoupled from the matching/scoring pipeline. Two levels:

1. **Level 1 — Column Mapping** (`column_mapper.py`): Maps uploaded column names to canonical names using alias tables (common real-world synonyms like "Order ID"→"order_id", "fee"→"fee_amount") and fuzzy matching (difflib, ratio ≥ 0.75). Returns high/medium confidence per mapping.
2. **Level 2 — Value Normalization** (`value_normalizer.py`): Normalizes dates to ISO format (YYYY-MM-DD), strips currency symbols/commas from amounts, maps status values to canonical vocabulary ("paid", "refunded", "payment_failed"). Reports all issues with row indices — never silently coerces.
3. **Orchestrator** (`pipeline.py`): `normalize_uploaded_file()` chains both levels, supports manual_mapping overrides, and returns status: "ready" | "needs_mapping" | "failed".

**What it can handle automatically:** column name synonyms, date format variants (DD/MM/YYYY, YYYY-MM-DD, etc.), currency symbol/comma stripping (₹, $, commas), status vocabulary differences.

**What it cannot handle:** it cannot invent missing structural information — e.g. if a real export represents partial settlements in a completely different structure than one-row-per-leg, the data must already contain the necessary linking information (UTR references, order IDs).

---

## Folder Structure (already decided — do not redesign)

```
finance_reconcilation_agent/
├── data/
│   ├── raw/                    (the 3 input CSVs — already generated)
│   ├── ground_truth/           (ground_truth.json — grading only, never read by matcher — already generated)
│   └── genarate_data.py        (already written and already run)
├── src/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── column_mapper.py      (Level 1 — column name mapping)
│   │   ├── value_normalizer.py   (Level 2 — value/format normalization)
│   │   └── pipeline.py           (orchestrates both levels)
│   ├── matcher/
│   │   ├── loader.py
│   │   ├── exact_join.py
│   │   ├── validators.py
│   │   ├── special_cases.py
│   │   ├── scoring.py
│   │   └── pipeline.py
│   ├── exceptions/
│   │   └── categorizer.py
│   ├── explain/
│   │   └── explainer.py
│   └── grading/
│       └── evaluate_accuracy.py
├── output/
│   ├── match_report.csv
│   └── exception_summary.json
├── backend/
│   └── main.py                  (FastAPI server wrapping the pipeline)
├── frontend/
│   └── ...                      (Vite + React + TypeScript project — dashboard UI)
├── requirements.txt
├── README.md
└── CLAUDE.md                   (this file)
```

**Current status:** Phase 1 (Data Generation) is already complete. The three raw CSVs exist in `data/raw/` and `ground_truth.json` exists in `data/ground_truth/`. Start execution from Phase 2.

---

## Build Phases — Execute in Order

**Do not skip ahead or combine phases.** Each phase should be completed, verified against its "done when" criteria, and confirmed with the user before starting the next. Work incrementally — this project is being built step-by-step, not as one large generation pass.

### Phase 0 — Environment Setup ✅ (partially done)
- Folder structure exists.
- Create `requirements.txt` with: `pandas`, `numpy` (add others only as actually needed).
- Set up a virtual environment and install dependencies.
- **Done when:** dependencies install cleanly.

### Phase 1 — Data Generation ✅ (already done)
- `genarate_data.py` has already been run.
- All 3 CSVs + `ground_truth.json` exist, with ~60 total transactions and 9 category types represented.
- No action needed here unless data needs to be regenerated.

### Phase 2 — Data Loader
- Build `src/matcher/loader.py`: loads the 3 CSVs into pandas DataFrames, parses dates properly, validates expected columns exist, and returns them as a clean bundle (e.g., a dataclass or dict of DataFrames).
- **Done when:** loader can be called standalone and prints shape/dtypes of all 3 DataFrames correctly.

### Phase 3 — Exact Key Join (Stage 1)
- Build `src/matcher/exact_join.py`: joins ledger→gateway on `order_id`/`order_ref`, and gateway→bank on `utr`.
- Handle the one-to-many case (partial settlements) — one `order_id` may map to multiple gateway/bank rows.
- Identify unjoined rows on each side (potential orphans) separately — do not silently drop them.
- **Done when:** every row in every file is accounted for as either "joined" or "orphaned," with counts printed.

### Phase 4 — Validation Logic (Stage 2 & 3)
- Build `src/matcher/validators.py`:
  - **Amount validator**: checks `gross_amount - fee_amount ≈ net_settled ≈ credited_amount` within a small tolerance (handles rounding drift). For partial settlements, sum of net_settled parts should equal gross-minus-fee.
  - **Timing validator**: checks `settlement_date` falls within an acceptable window of `order_date` (e.g., flag but don't auto-fail T+3/T+4 — score it lower rather than binary reject).
- Each validator should return a numeric sub-score (0–1), not just true/false.
- **Done when:** running validators against Phase 3 output produces per-transaction amount_score and timing_score.

### Phase 5 — Special Case Handlers (Stage 4)
- Build `src/matcher/special_cases.py`:
  - Detect duplicate UTRs in the bank statement (same UTR appearing 2+ times) — flag as `DUPLICATE_UTR_ERROR`, do not auto-resolve.
  - Detect refund/status mismatches (ledger status = `refunded` but gateway/bank still show a credit) — flag as `REFUND_NOT_REFLECTED`.
  - Confirm partial settlement handling (multiple UTRs summing to expected net) is correctly recognized as a valid match, not an exception.
- **Done when:** known injected duplicate and refund cases are correctly identified when tested against ground_truth.json categories.

### Phase 6 — Confidence Scoring (Stage 5)
- Build `src/matcher/scoring.py`: combines amount_score, timing_score, and a reference_score (how cleanly the keys joined — e.g., 1.0 for direct key match) into a single weighted composite (suggested starting weights: amount 0.40, timing 0.30, reference 0.30 — tune based on testing).
- Define thresholds: e.g., confidence ≥ 0.85 → `MATCHED`; 0.5–0.85 → `RESOLVED_WITH_REASONING` (needs explanation of why it's still accepted); below 0.5 → `EXCEPTION`.
- **Done when:** every transaction has a final confidence_score and match_status.

### Phase 7 — Pipeline Orchestration
- Build `src/matcher/pipeline.py`: runs loader → exact_join → validators → special_cases → scoring in sequence, producing one unified result set.
- **Done when:** a single function call runs the entire matching process end-to-end and returns a results DataFrame.

### Phase 8 — Exception Categorization
- Build `src/exceptions/categorizer.py`: for every `EXCEPTION`-status record, assign a specific reason code (not generic "unmatched") — e.g. `UNEXPLAINED_AMOUNT_GAP`, `DUPLICATE_UTR`, `ORPHAN_NO_GATEWAY_MATCH`, `ORPHAN_NO_LEDGER_MATCH`.
- **Done when:** every exception has a specific, meaningful reason code, and these can be aggregated into counts by category.

### Phase 9 — Explanation Layer
- Build `src/explain/explainer.py`: generates a human-readable explanation string for every transaction (why it matched, why it was resolved with reasoning, or why it's an exception).
- Start with templated logic (string formatting based on which validators passed/failed). LLM-based natural language generation is an optional polish step — do not add API dependencies unless the templated version is working first.
- **Done when:** every row in the final output has a non-generic, specific explanation string.

### Phase 10 — Output Generation
- Produce `output/match_report.csv` and `output/exception_summary.json` matching the schema defined above.
- **Done when:** both files are generated correctly from a full pipeline run on the 60-record dataset.

### Phase 11 — Grading Against Ground Truth
- Build `src/grading/evaluate_accuracy.py`: loads `ground_truth.json`, compares against `match_report.csv`, and computes precision/recall per category (e.g., "did we correctly resolve all 8 FEE_MISMATCH cases without flagging them as exceptions?" and "did we correctly catch both DUPLICATE_UTR cases as exceptions?").
- **Done when:** a clear accuracy report is generated showing per-category correctness, not just an overall %.

### Phase 12 — Dashboard Backend (FastAPI)
- Build `backend/main.py` (or `backend/app/main.py` if a package structure is preferred) using FastAPI, wrapping the existing pipeline in REST endpoints. Do NOT duplicate or reimplement any matching/scoring/explanation logic here — this layer only calls into `src/matcher/`, `src/explain/`, `src/exceptions/`, and `src/grading/` and serves their results as JSON.
- Required endpoints (exact paths negotiable, but functionality must match):
  - `POST /api/run` — triggers a full pipeline run (load data → join → validate → score → apply special-case overrides → generate explanations → write `output/match_report.csv` and `output/exception_summary.json`) and returns a run summary
  - `GET /api/summary` — returns the contents of `output/exception_summary.json`
  - `GET /api/transactions` — returns the full `match_report.csv` as JSON, with optional query params for filtering by `match_status` or category
  - `GET /api/transactions/{order_id}` — returns full detail for one transaction, including its explanation and `override_reason` if present
  - `GET /api/accuracy` — returns `output/accuracy_report.json` (grading results against `ground_truth.json`), for an optional "accuracy proof" view in the dashboard
- Enable CORS for the frontend's local dev origin (e.g. `http://localhost:5173` for Vite's default port).
- Add `fastapi` and `uvicorn` to `requirements.txt`.
- **Done when:** running the FastAPI server (e.g. `uvicorn backend.main:app --reload`) and hitting each endpoint (via browser, curl, or FastAPI's built-in `/docs` Swagger UI) returns correct, real data from an actual pipeline run — not mock/placeholder data.

### Phase 13 — Dashboard Frontend (React + Vite + Tailwind + shadcn/ui)
- Scaffold a new Vite + React + TypeScript project in a `frontend/` folder at the project root.
- Install and configure: Tailwind CSS, shadcn/ui (component library), Tremor and/or Recharts (dashboard charts), Framer Motion (animation), and a data-fetching approach (native fetch or a small wrapper) pointed at the FastAPI backend's endpoints.
- Build the following views/sections, all on a single dashboard page unless the user requests multiple routes:
  - A KPI summary row (cards): Match Rate, Total Transactions Processed, Exception Count, Average Confidence Score — animated count-up on load using Framer Motion, sourced from `GET /api/summary`
  - An exception breakdown chart (donut or bar) showing category counts (e.g. DUPLICATE_UTR_DETECTED, REFUND_NOT_REFLECTED, ORPHAN_NO_GATEWAY_MATCH, etc.), sourced from `GET /api/summary`
  - A confidence score distribution histogram across all transactions, sourced from `GET /api/transactions`
  - A searchable, filterable, sortable transaction table (`order_id`, `match_status`, `confidence_score`, category/`override_reason`) with a row-click or expand interaction revealing the full explanation text, sourced from `GET /api/transactions` and `GET /api/transactions/{order_id}`
  - A distinctly-styled "Flagged for Review" panel specifically highlighting the EXCEPTION-status transactions with their explanations front and center — this is the most important storytelling section of the dashboard and should be visually prominent, not just another table row
  - A "Run Reconciliation" trigger button that calls `POST /api/run` and shows a live loading/progress state while it executes, then refreshes all the above sections with fresh results — this live re-run capability is a deliberate design choice to make the demo feel real-time rather than pre-baked
- Visual direction: clean, modern, fintech-product feel — avoid default/unstyled component appearances; use shadcn/ui's theming and Tailwind consistently rather than mixing ad hoc CSS.
- **Done when:** running the Vite dev server alongside the FastAPI backend produces a fully working, visually polished dashboard that can trigger a live run and display real results end-to-end, matching the sections described above.

### Phase 14 (Stretch) — Natural Language Q&A Layer ✅
- Only attempt after Phases 1–13 are complete and working.
- Build a simple query interface (can be CLI or added to the dashboard frontend) that answers questions like "why wasn't order X settled?" by looking up that order's row in `match_report.csv` and returning its explanation.
- **Done when:** a natural-language question about a specific order_id returns its stored reasoning correctly.

**Implementation:** `GET /api/ask?question=...` endpoint in `backend/main.py` + `NaturalLanguageQA.tsx` frontend component. The backend extracts order IDs (ORD10027, order 10045, bare 10016) via regex, matches keywords to exception categories/statuses, and falls back to explanation text search. The frontend provides a chat-style interface with example questions, expandable transaction details, and Q&A history.

---

## Working Principles for the Executing LLM

- Work through phases sequentially. Confirm each phase's "done when" criteria before moving to the next.
- Prefer working, testable code over extended write-ups or mathematical exposition at each phase.
- Keep the matcher logic (`src/matcher/`) fully separate from presentation logic (`backend/` + `frontend/`) and reasoning-text generation (`src/explain/`) — this separation matters for judging credibility (a judge should be able to inspect scoring logic independent of demo polish).
- The matcher must NEVER read `ground_truth.json` — that file exists only for `src/grading/evaluate_accuracy.py`. Violating this invalidates the accuracy claim.
- Be explicit and honest in exception categorization — do not force borderline cases into `MATCHED` just to inflate the match rate. The stated goal of this project is an honest exception list, and that is a judged criterion.
- When explaining finance concepts in code comments, docstrings, or README content, write for a reader with no finance background.
- **Do not overfit code to `genarate_data.py`'s specific patterns.** The synthetic dataset is one example, not the spec. Write scoring rules, tolerances, and edge-case handlers that work for *any* reasonable transaction dataset — different settlement windows, different fee structures, different transaction scales, different numbers of sources. If a rule only works because the synthetic data happens to have T+1/T+2 settlements or ₹200–₹6000 amounts, it is wrong. Config-driven behavior (via `src/config/scoring_config.py`) is the correct way to handle dataset-specific tuning; hardcoded assumptions in logic are not.
