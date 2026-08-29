"""
Dashboard Backend (FastAPI)
===========================

Thin REST layer wrapping the reconciliation pipeline. This module contains
NO matching/scoring/explanation logic of its own — every endpoint calls into
src/matcher/, src/explain/, src/exceptions/, src/ingestion/, or reads the
generated output files in output/.

Run from the project root:
    uvicorn backend.main:app --reload
"""

import csv
import io
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse


class _CleanEncoder(json.JSONEncoder):
    """Ensures NaN/Inf never leak into JSON responses."""

    def default(self, o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        return super().default(o)


def _clean(obj):
    """Recursively replace NaN/Inf with None in any nested structure."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


# Ensure relative paths ("data", "output") resolve to the project root no
# matter which directory uvicorn was launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.output_gen import run_output_generation  # noqa: E402
from src.matcher.loader import (  # noqa: E402
    EXPECTED_BANK_COLS,
    EXPECTED_GATEWAY_COLS,
    EXPECTED_LEDGER_COLS,
)
from src.ingestion.pipeline import normalize_uploaded_file  # noqa: E402

OUTPUT_DIR = Path("output")
MATCH_REPORT_PATH = OUTPUT_DIR / "match_report.csv"
SUMMARY_PATH = OUTPUT_DIR / "exception_summary.json"
ACCURACY_PATH = Path("output/accuracy_report.json")
CUSTOM_DATA_DIR = Path("data/custom")

# Required filenames for custom uploads (matches the loader's expectations)
_CUSTOM_FILE_MAP = {
    "ledger_file": ("internal_order_ledger.csv", EXPECTED_LEDGER_COLS, "ledger"),
    "gateway_file": ("gateway_settlement_report.csv", EXPECTED_GATEWAY_COLS, "gateway"),
    "bank_file": ("bank_statement.csv", EXPECTED_BANK_COLS, "bank"),
}

# Canonical accepted values for constrained fields (for schema template)
STATUS_VALUES = ["paid", "refunded", "payment_failed"]
PAYMENT_MODE_VALUES = ["UPI", "Card", "Netbanking"]

# Example rows for the schema template
_SCHEMA_EXAMPLES = {
    "ledger": {
        "order_id": "ORD10001",
        "customer_name": "Aarav Sharma",
        "order_amount": 2500.00,
        "order_date": "2026-03-15",
        "payment_mode": "UPI",
        "status": "paid",
    },
    "gateway": {
        "gateway_txn_id": "rzp_pay_88001",
        "order_ref": "ORD10001",
        "gross_amount": 2500.00,
        "fee_pct": 0.02,
        "fee_amount": 50.00,
        "net_settled": 2450.00,
        "utr": "UTR556001",
        "settlement_date": "2026-03-17",
    },
    "bank": {
        "bank_txn_id": "BANKTXN55001",
        "utr": "UTR556001",
        "credited_amount": 2450.00,
        "value_date": "2026-03-17",
        "narration": "NEFT-RAZORPAY-SETTLEMENT-UTR556001",
    },
}

app = FastAPI(
    title="AI Finance Controller — Reconciliation API",
    description="Multi-source financial reconciliation: ledger x gateway x bank.",
    version="1.0.0",
)

# CORS: allow the Vite dev server origins (Phase 13 frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
# Without this, any unhandled exception (a bug, not a deliberate
# HTTPException) falls through to Starlette's default plain-text
# "Internal Server Error" response. That's not valid JSON, so the
# frontend's JSON.parse() on the response body throws a confusing,
# hard-to-trace error ("Unexpected token 'I', \"Internal S\"... is not
# valid JSON") instead of showing the real Python exception. This
# handler guarantees every response — success or failure — is valid
# JSON, with the actual exception type and message included so bugs
# are visible immediately instead of masked by a parse error.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Unexpected error: {type(exc).__name__}: {exc}",
            "path": str(request.url.path),
        },
    )

# In-memory state from the most recent POST /api/run.
_last_run_summary: dict | None = None
_categories_by_order_id: dict[str, str] = {}
_last_run_dataset_source: str = "sample"

# In-memory staging for pending uploads that need mapping confirmation.
# Key: session_id (auto-generated UUID). Value: the raw bytes per file.
_pending_uploads: dict[str, dict[str, bytes]] = {}


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{path} not found. Trigger POST /api/run first.",
        )
    with open(path) as f:
        return json.load(f)


def _load_match_report() -> dict:
    """Load match_report.csv and return cleaned list-of-dicts (NaN-free)."""
    if not MATCH_REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="match_report.csv not found. Trigger POST /api/run first.",
        )
    df = pd.read_csv(MATCH_REPORT_PATH)
    records = df.to_dict(orient="records")
    return _clean(records)


def _validate_csv_columns(
    df: pd.DataFrame, expected_cols: list[str], filename: str
) -> list[str]:
    """
    Validate a DataFrame against expected columns.

    Returns a list of error strings. Empty list means valid.
    Only checks for missing required columns — extra columns are allowed.
    """
    errors = []
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        errors.append(f"missing required columns: {', '.join(missing)}")
    if len(df) == 0:
        errors.append("file is empty (0 rows)")
    return errors


def _file_summary(df: pd.DataFrame, filename: str) -> dict:
    """Build a short structural summary of a DataFrame."""
    summary: dict = {"filename": filename, "row_count": len(df)}
    if "order_id" in df.columns:
        summary["unique_order_ids"] = int(df["order_id"].nunique())
    if "order_date" in df.columns:
        try:
            dates = pd.to_datetime(df["order_date"], errors="coerce")
            valid = dates.dropna()
            if len(valid) > 0:
                summary["date_range"] = {
                    "from": str(valid.min().date()),
                    "to": str(valid.max().date()),
                }
        except Exception:
            pass
    return summary


def _commit_custom_data(
    normalized_dfs: dict[str, pd.DataFrame],
    all_warnings: dict[str, list[dict]],
) -> dict:
    """
    Write normalized DataFrames to data/custom/ and return a summary dict.

    Called only after all three files pass normalization + schema validation.
    """
    CUSTOM_DATA_DIR.mkdir(exist_ok=True)

    file_pairs = [
        ("ledger_file", "internal_order_ledger.csv"),
        ("gateway_file", "gateway_settlement_report.csv"),
        ("bank_file", "bank_statement.csv"),
    ]

    summaries: list[dict] = []
    total_warnings = 0

    for field_name, target_name in file_pairs:
        df = normalized_dfs[field_name]
        dest = CUSTOM_DATA_DIR / target_name
        df.to_csv(dest, index=False)
        summary = _file_summary(df, target_name)
        summaries.append(summary)
        total_warnings += len(all_warnings.get(field_name, []))

    return {
        "status": "success",
        "ready_for_reconciliation": True,
        "message": "All three files normalized, validated, and committed successfully",
        "dataset_source": "custom",
        "files": summaries,
        "normalization_warnings": all_warnings,
        "total_warnings_applied": total_warnings,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return {
        "service": "reconciliation-api",
        "endpoints": [
            "GET /api/schema-template",
            "GET /api/schema-template/download?file=ledger|gateway|bank",
            "POST /api/upload",
            "POST /api/upload/confirm-mapping",
            "POST /api/run",
            "GET /api/summary",
            "GET /api/transactions?match_status=&category=",
            "GET /api/transactions/{order_id}",
            "GET /api/ask?question=...",
            "GET /api/accuracy",
        ],
    }


# ---------------------------------------------------------------------------
# Schema template (STEP 6)
# ---------------------------------------------------------------------------


@app.get("/api/schema-template")
def get_schema_template():
    """
    Return the exact target schema for each file type, sourced directly
    from loader.py's EXPECTED_*_COLS constants — no duplication.

    Includes required columns, one example row, and accepted values
    for constrained fields.
    """
    return _clean({
        "ledger": {
            "required_columns": EXPECTED_LEDGER_COLS,
            "example_row": _SCHEMA_EXAMPLES["ledger"],
            "constrained_fields": {
                "payment_mode": PAYMENT_MODE_VALUES,
                "status": STATUS_VALUES,
            },
        },
        "gateway": {
            "required_columns": EXPECTED_GATEWAY_COLS,
            "example_row": _SCHEMA_EXAMPLES["gateway"],
            "constrained_fields": {},
        },
        "bank": {
            "required_columns": EXPECTED_BANK_COLS,
            "example_row": _SCHEMA_EXAMPLES["bank"],
            "constrained_fields": {},
        },
    })


@app.get("/api/schema-template/download")
def download_schema_template(file: str = Query(..., description="ledger, gateway, or bank")):
    """
    Download a blank CSV template (headers + one example row) for the
    specified file type.
    """
    if file not in _SCHEMA_EXAMPLES:
        raise HTTPException(status_code=400, detail=f"file must be 'ledger', 'gateway', or 'bank', got '{file}'")

    example = _SCHEMA_EXAMPLES[file]
    headers = list(example.keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerow(example)

    output.seek(0)
    filename_map = {
        "ledger": "internal_order_ledger_template.csv",
        "gateway": "gateway_settlement_report_template.csv",
        "bank": "bank_statement_template.csv",
    }

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename_map[file]}"'},
    )


# ---------------------------------------------------------------------------
# Upload with normalization (STEP 5)
# ---------------------------------------------------------------------------


@app.post("/api/upload")
async def upload_custom_dataset(
    ledger_file: UploadFile = File(...),
    gateway_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
):
    """
    Upload three CSV files and run normalization.

    Flow:
      1. Read each file into a DataFrame.
      2. Run normalize_uploaded_file() — attempts automatic column mapping
         and value normalization.
      3. If any file needs manual mapping: return 422 with per-file details
         (unmapped columns + unused uploaded columns for the user to pick
         from). Raw file bytes are staged in memory under a session ID for
         the confirm-mapping step.
      4. If all files are ready: run loader.py schema validation as a final
         safety check, then commit to data/custom/.

    Returns 422 with status "needs_mapping" if the user must intervene.
    Returns 200 with status "success" and ready_for_reconciliation: true
    if everything passes.
    """
    import uuid

    upload_map = {
        "ledger_file": (ledger_file, EXPECTED_LEDGER_COLS, "internal_order_ledger.csv", "ledger"),
        "gateway_file": (gateway_file, EXPECTED_GATEWAY_COLS, "gateway_settlement_report.csv", "gateway"),
        "bank_file": (bank_file, EXPECTED_BANK_COLS, "bank_statement.csv", "bank"),
    }

    # Phase 1: Read all files into DataFrames, run normalization
    dfs: dict[str, pd.DataFrame] = {}
    raw_bytes: dict[str, bytes] = {}
    norm_results: dict[str, dict] = {}

    for field_name, (upload, expected_cols, target_name, file_type) in upload_map.items():
        # Check file type
        if not upload.filename or not upload.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=422, detail={
                "message": f"File must be a .csv (got: {upload.filename})",
                "errors": {field_name: [f"file must be a .csv (got: {upload.filename})"]},
            })

        content = await upload.read()
        if len(content) == 0:
            raise HTTPException(status_code=422, detail={
                "message": "One or more files are empty",
                "errors": {field_name: ["file is empty (0 bytes)"]},
            })

        raw_bytes[field_name] = content

        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise HTTPException(status_code=422, detail={
                "message": f"Cannot parse CSV: {type(e).__name__}: {e}",
                "errors": {field_name: [f"cannot parse CSV: {type(e).__name__}: {e}"]},
            })

        norm_result = normalize_uploaded_file(df, file_type)
        norm_results[field_name] = norm_result

    # Phase 2: Check if any file needs manual mapping
    needs_mapping = {
        k: v for k, v in norm_results.items()
        if v["status"] == "needs_mapping"
    }

    if needs_mapping:
        # Stage raw bytes for the confirm-mapping step
        session_id = str(uuid.uuid4())
        _pending_uploads[session_id] = raw_bytes

        mapping_details: dict[str, dict] = {}
        for field_name, result in needs_mapping.items():
            _, _, _, file_type = upload_map[field_name]
            mapping_details[field_name] = {
                "auto_mapped": result["auto_mapped"],
                "unmapped_required": result["unmapped_required"],
                "unused_uploaded_columns": result["unused_uploaded_columns"],
                "file_type": file_type,
            }

        raise HTTPException(status_code=422, detail={
            "status": "needs_mapping",
            "message": "Some files require manual column mapping",
            "session_id": session_id,
            "mapping_details": mapping_details,
        })

    # Phase 3: Check for failed normalization
    failed = {
        k: v for k, v in norm_results.items()
        if v["status"] == "failed"
    }
    if failed:
        failure_details: dict[str, dict] = {}
        for field_name, result in failed.items():
            failure_details[field_name] = {
                "failure_reason": result.get("failure_reason", "Unknown"),
                "unresolvable_issues": result.get("unresolvable_issues", []),
            }
        raise HTTPException(status_code=422, detail={
            "status": "failed",
            "message": "One or more files failed normalization",
            "errors": failure_details,
        })

    # Phase 4: All ready — run loader.py schema validation as final safety check
    all_warnings: dict[str, list[dict]] = {}
    validated_dfs: dict[str, pd.DataFrame] = {}

    for field_name, (upload, expected_cols, target_name, file_type) in upload_map.items():
        result = norm_results[field_name]
        norm_df = result["normalized_df"]
        col_errors = _validate_csv_columns(norm_df, expected_cols, target_name)
        if col_errors:
            raise HTTPException(status_code=422, detail={
                "status": "failed",
                "message": f"Schema validation failed after normalization for {target_name}",
                "errors": {field_name: col_errors},
            })
        validated_dfs[field_name] = norm_df
        all_warnings[field_name] = result.get("normalization_warnings", [])

    # Phase 5: Commit to data/custom/
    commit_result = _commit_custom_data(validated_dfs, all_warnings)
    return _clean(commit_result)


@app.post("/api/upload/confirm-mapping")
async def confirm_mapping(
    session_id: str = Query(..., description="Session ID from the initial upload's needs_mapping response"),
    ledger_mapping: str | None = Query(default=None, description='JSON dict of canonical->source column overrides for ledger, e.g. {"order_id":"Order ID"}'),
    gateway_mapping: str | None = Query(default=None, description="Same for gateway"),
    bank_mapping: str | None = Query(default=None, description="Same for bank"),
):
    """
    Finalize a previously ambiguous upload using user-provided manual
    column mappings.

    The session_id references staged raw file bytes from the initial
    upload. The mapping parameters are JSON strings mapping canonical
    column names to the user's chosen uploaded column names.

    Re-runs normalize_uploaded_file() with the overrides applied, then
    proceeds exactly like a successful initial upload if now "ready".
    """
    if session_id not in _pending_uploads:
        raise HTTPException(status_code=404, detail={
            "message": f"Session '{session_id}' not found or expired. Please re-upload.",
        })

    raw_bytes = _pending_uploads.pop(session_id)

    # Parse manual mappings
    manual_maps: dict[str, dict[str, str] | None] = {
        "ledger_file": json.loads(ledger_mapping) if ledger_mapping else None,
        "gateway_file": json.loads(gateway_mapping) if gateway_mapping else None,
        "bank_file": json.loads(bank_mapping) if bank_mapping else None,
    }

    upload_map = {
        "ledger_file": (EXPECTED_LEDGER_COLS, "internal_order_ledger.csv", "ledger"),
        "gateway_file": (EXPECTED_GATEWAY_COLS, "gateway_settlement_report.csv", "gateway"),
        "bank_file": (EXPECTED_BANK_COLS, "bank_statement.csv", "bank"),
    }

    # Re-run normalization with manual overrides
    norm_results: dict[str, dict] = {}
    for field_name, (expected_cols, target_name, file_type) in upload_map.items():
        content = raw_bytes.get(field_name)
        if content is None:
            raise HTTPException(status_code=422, detail={
                "message": f"Missing file data for {field_name}",
                "errors": {field_name: ["file data not found in session"]},
            })

        df = pd.read_csv(io.BytesIO(content))
        manual = manual_maps.get(field_name)
        norm_result = normalize_uploaded_file(df, file_type, manual_mapping=manual)
        norm_results[field_name] = norm_result

    # Check if still needs mapping
    still_needs = {k: v for k, v in norm_results.items() if v["status"] == "needs_mapping"}
    if still_needs:
        mapping_details = {}
        for field_name, result in still_needs.items():
            _, _, file_type = upload_map[field_name]
            mapping_details[field_name] = {
                "auto_mapped": result["auto_mapped"],
                "unmapped_required": result["unmapped_required"],
                "unused_uploaded_columns": result["unused_uploaded_columns"],
                "file_type": file_type,
            }
        # Re-stage for another attempt
        new_session = str(__import__("uuid").uuid4())
        _pending_uploads[new_session] = raw_bytes
        raise HTTPException(status_code=422, detail={
            "status": "needs_mapping",
            "message": "Some columns still unmapped after manual mapping",
            "session_id": new_session,
            "mapping_details": mapping_details,
        })

    # Check for failed normalization
    failed = {k: v for k, v in norm_results.items() if v["status"] == "failed"}
    if failed:
        failure_details = {}
        for field_name, result in failed.items():
            failure_details[field_name] = {
                "failure_reason": result.get("failure_reason", "Unknown"),
                "unresolvable_issues": result.get("unresolvable_issues", []),
            }
        raise HTTPException(status_code=422, detail={
            "status": "failed",
            "message": "One or more files failed normalization",
            "errors": failure_details,
        })

    # All ready — validate and commit
    all_warnings: dict[str, list[dict]] = {}
    validated_dfs: dict[str, pd.DataFrame] = {}

    for field_name, (expected_cols, target_name, file_type) in upload_map.items():
        result = norm_results[field_name]
        norm_df = result["normalized_df"]
        col_errors = _validate_csv_columns(norm_df, expected_cols, target_name)
        if col_errors:
            raise HTTPException(status_code=422, detail={
                "status": "failed",
                "message": f"Schema validation failed after normalization for {target_name}",
                "errors": {field_name: col_errors},
            })
        validated_dfs[field_name] = norm_df
        all_warnings[field_name] = result.get("normalization_warnings", [])

    commit_result = _commit_custom_data(validated_dfs, all_warnings)
    return _clean(commit_result)


@app.post("/api/run")
def run_reconciliation(
    use_llm: bool = Query(default=True, description="Generate explanations via Groq LLM (template fallback on failure)."),
    fallback_ratio: float = Query(default=0.1, ge=0.0, le=1.0, description="Fraction of rows randomly assigned template explanations for a realistic source mix."),
    dataset_source: str = Query(default="sample", description="Dataset to reconcile: 'sample' (data/raw/) or 'custom' (data/custom/)."),
):
    """
    Trigger a full pipeline run:
    load data -> join -> validate -> score -> special-case overrides ->
    explanations -> write output/match_report.csv + exception_summary.json.

    Returns a run summary. Takes ~1-2 minutes when use_llm=true due to
    Groq API rate limits on the free tier.
    """
    global _last_run_summary, _categories_by_order_id, _last_run_dataset_source

    if dataset_source not in ("sample", "custom"):
        raise HTTPException(status_code=400, detail=f"dataset_source must be 'sample' or 'custom', got '{dataset_source}'")

    if dataset_source == "custom":
        # Verify custom data exists
        required = [
            CUSTOM_DATA_DIR / "internal_order_ledger.csv",
            CUSTOM_DATA_DIR / "gateway_settlement_report.csv",
            CUSTOM_DATA_DIR / "bank_statement.csv",
        ]
        missing = [str(p.name) for p in required if not p.exists()]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"No custom dataset available. Upload all three CSVs first via POST /api/upload. Missing: {', '.join(missing)}",
            )

    try:
        summary = run_output_generation(
            use_llm=use_llm,
            fallback_ratio=fallback_ratio,
            dataset_source=dataset_source,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {type(e).__name__}: {e}")

    _last_run_summary = summary
    _categories_by_order_id = summary.get("categories_by_order_id", {})
    _last_run_dataset_source = dataset_source

    return _clean({
        "status": "completed",
        "run_summary": summary,
    })


@app.get("/api/summary")
def get_summary():
    """Return aggregate stats from the latest run (exception_summary.json)."""
    data = _read_json(SUMMARY_PATH)
    data["dataset_source"] = _last_run_dataset_source
    return _clean(data)


@app.get("/api/accuracy")
def get_accuracy():
    """
    Return grading results against ground truth.

    For custom datasets (no ground truth), returns a clear structured
    response indicating grading is unavailable — not an error.
    """
    if _last_run_dataset_source == "custom":
        return _clean({
            "available": False,
            "dataset_source": "custom",
            "message": "Accuracy grading is not available for custom datasets — no ground truth file exists to compare against.",
        })

    if not ACCURACY_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="accuracy_report.json not found. Trigger POST /api/run first.",
        )

    report = _read_json(ACCURACY_PATH)
    report["available"] = True
    report["dataset_source"] = "sample"
    report["grading_matches_latest_run"] = (
        _last_run_summary is not None and ACCURACY_PATH.exists()
    )
    return _clean(report)


@app.get("/api/transactions")
def get_transactions(
    match_status: str | None = Query(default=None, description="Filter: MATCHED, RESOLVED_WITH_REASONING, or EXCEPTION."),
    category: str | None = Query(default=None, description="Filter by exception/resolution category, e.g. DUPLICATE_UTR_ERROR, ORPHAN_NO_GATEWAY_MATCH, PARTIAL_SETTLEMENT_VERIFIED."),
):
    """Return the full match_report.csv as JSON, with optional filters."""
    records = _load_match_report()

    if match_status:
        target = match_status.upper()
        records = [r for r in records if (r.get("match_status") or "").upper() == target]

    if category:
        cat_upper = category.upper()
        records = [
            r for r in records
            if (r.get("override_reason") or "").upper() == cat_upper
            or _categories_by_order_id.get(r.get("order_id", ""), "").upper() == cat_upper
        ]

    return _clean({
        "count": len(records),
        "dataset_source": _last_run_dataset_source,
        "transactions": records,
    })


@app.get("/api/transactions/{order_id}")
def get_transaction(order_id: str):
    """Full detail for one transaction, including explanation and override_reason."""
    records = _load_match_report()

    matches = [r for r in records if r.get("order_id") == order_id]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Transaction '{order_id}' not found.")

    record = matches[0]
    record["category"] = _categories_by_order_id.get(order_id)
    record["dataset_source"] = _last_run_dataset_source
    return _clean(record)


# ---------------------------------------------------------------------------
# Phase 14 — Natural Language Q&A
# ---------------------------------------------------------------------------

import re

# Patterns that look like order IDs in user questions
_ORDER_ID_PATTERNS = [
    re.compile(r"\b(ORD\d{4,6})\b", re.IGNORECASE),          # ORD10027
    re.compile(r"\border\s*(?:id)?\s*[:#=\s]*(\d{4,6})\b", re.IGNORECASE),  # order 10027, order_id: 10027
    re.compile(r"\b(\d{5})\b"),                                 # bare 10027
]

# Keyword hints that map to exception categories / statuses
_KEYWORD_HINTS: list[tuple[list[str], str, str]] = [
    (["duplicate utr", "double credit", "same utr"], "override_reason", "DUPLICATE_UTR_ERROR"),
    (["refund", "refunded", "reversed"], "override_reason", "REFUND_NOT_REFLECTED"),
    (["orphan", "no gateway", "missing gateway"], "override_reason", "ORPHAN_NO_GATEWAY_MATCH"),
    (["no ledger", "missing ledger", "unmatched order"], "override_reason", "ORPHAN_NO_LEDGER_MATCH"),
    (["partial", "split", "multiple payments"], "override_reason", "PARTIAL_SETTLEMENT_VERIFIED"),
    (["amount mismatch", "amount gap", "wrong amount"], "override_reason", "UNEXPLAINED_AMOUNT_GAP"),
    (["timing", "late", "delayed", "settlement lag"], "match_status", "RESOLVED_WITH_REASONING"),
    (["exception", "flagged", "error", "problem", "issue"], "match_status", "EXCEPTION"),
    (["matched", "clean", "ok", "correct", "resolved"], "match_status", "MATCHED"),
]


def _extract_order_id(question: str) -> str | None:
    """Try to pull an order ID out of the user's question."""
    for pattern in _ORDER_ID_PATTERNS:
        m = pattern.search(question)
        if m:
            raw = m.group(1)
            # If it's a bare number, prefix with ORD
            if raw.isdigit():
                return f"ORD{raw}"
            return raw.upper()
    return None


def _find_keyword_hint(question: str) -> tuple[str, str] | None:
    """Check if the question contains keywords pointing to a category/status."""
    q_lower = question.lower()
    for keywords, field, value in _KEYWORD_HINTS:
        if any(kw in q_lower for kw in keywords):
            return field, value
    return None


@app.post("/api/ask")
def ask_question(body: dict = Body(...)):
    """
    Answer a natural-language question about reconciliation results.

    Accepts {"question": "..."} and looks up matching transactions in the
    latest match_report.csv. Supports order_id lookup and category/status
    keyword matching.
    """
    question = body.get("question", "")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=400, detail="Field 'question' is required and must be a non-empty string.")

    try:
        records = _load_match_report()
    except HTTPException:
        return _clean({
            "answer": "No reconciliation results available yet. Run reconciliation first.",
            "matched_transactions": [],
            "match_type": "no_match",
        })
    if not records:
        return _clean({
            "answer": "No reconciliation results available yet. Run reconciliation first.",
            "matched_transactions": [],
            "match_type": "no_match",
        })

    # Strategy 1: Extract order ID
    order_id = _extract_order_id(question)
    if order_id:
        matches = [r for r in records if r.get("order_id") == order_id]
        if matches:
            rec = matches[0]
            answer_parts = [
                f"**{rec['order_id']}** is classified as **{rec['match_status']}** "
                f"(confidence: {(rec.get('confidence_score') or 0) * 100:.1f}%).",
                "",
                rec.get("explanation", "No explanation available."),
            ]
            if rec.get("override_reason"):
                answer_parts.append(f"\nCategory: {rec['override_reason']}")
            return _clean({
                "answer": "\n".join(answer_parts),
                "matched_transactions": [rec],
                "match_type": "order_lookup",
            })
        else:
            return _clean({
                "answer": f"No transaction found with order ID **{order_id}** in the latest reconciliation results.",
                "matched_transactions": [],
                "match_type": "no_match",
            })

    # Strategy 2: Keyword / category matching
    hint = _find_keyword_hint(question)
    if hint:
        field, value = hint
        matches = [r for r in records if r.get(field) == value]
        if matches:
            summary_lines = [f"Found **{len(matches)}** transaction(s) matching your query:\n"]
            for rec in matches[:10]:
                score_str = f"{(rec.get('confidence_score') or 0) * 100:.1f}%"
                summary_lines.append(
                    f"- **{rec['order_id']}** ({rec['match_status']}, {score_str}): "
                    f"{(rec.get('explanation') or '')[:120]}..."
                )
            if len(matches) > 10:
                summary_lines.append(f"\n...and {len(matches) - 10} more.")
            return _clean({
                "answer": "\n".join(summary_lines),
                "matched_transactions": matches[:10],
                "match_type": "category_filter",
            })
        else:
            return _clean({
                "answer": f"No transactions found matching '{value}' in the latest results.",
                "matched_transactions": [],
                "match_type": "category_filter",
            })

    # Strategy 3: Fallback — no recognizable pattern
    return _clean({
        "answer": (
            "I couldn't determine which transaction(s) you're asking about. "
            "Try asking about a specific order ID (e.g. 'Why wasn't ORD10027 settled?') "
            "or use keywords like 'duplicate UTR', 'refund', 'orphan', 'exception', or 'matched'."
        ),
        "matched_transactions": [],
        "match_type": "no_match",
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
