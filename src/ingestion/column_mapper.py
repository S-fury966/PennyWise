"""
Level 1 — Column Name Mapping
==============================

Maps uploaded CSV column names to the canonical names expected by the
reconciliation pipeline. Uses alias lists (common real-world synonyms)
and fuzzy matching (difflib) as a fallback, with explicit confidence
levels for each mapping.

Canonical column definitions are imported from src/matcher/loader.py
— never duplicated here.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.matcher.loader import EXPECTED_BANK_COLS, EXPECTED_GATEWAY_COLS, EXPECTED_LEDGER_COLS


# ---------------------------------------------------------------------------
# Alias tables: canonical_name -> list of common real-world synonyms
# ---------------------------------------------------------------------------

LEDGER_ALIASES: dict[str, list[str]] = {
    "order_id": [
        "order_id", "orderid", "order_ref", "order_no", "order_number",
        "id", "txnid", "txn_id", "transaction_id", "reference",
    ],
    "customer_name": [
        "customer_name", "customer", "buyer_name", "buyer",
        "name", "client_name", "client", "payer_name", "payer",
    ],
    "order_amount": [
        "order_amount", "amount", "total", "total_amount", "invoice_amount",
        "gross_amount", "value", "price", "order_value", "txn_amount",
        "amt",
    ],
    "order_date": [
        "order_date", "date", "txn_date", "transaction_date",
        "created_at", "order_time", "placed_at", "placed_on",
    ],
    "payment_mode": [
        "payment_mode", "payment_method", "method", "mode",
        "pay_mode", "payment_type", "pmode", "txn_mode",
    ],
    "status": [
        "status", "order_status", "txn_status", "payment_status",
        "state", "result",
    ],
}

GATEWAY_ALIASES: dict[str, list[str]] = {
    "gateway_txn_id": [
        "gateway_txn_id", "txn_id", "transaction_id", "payment_id",
        "gateway_id", "razorpay_payment_id", "rp_txn_id", "gateway_ref",
        "pay_id", "payment_ref", "id",
    ],
    "order_ref": [
        "order_ref", "order_id", "orderid", "order_number",
        "merchant_order_id", "client_order_id", "order_reference",
        "order", "ref_order",
    ],
    "gross_amount": [
        "gross_amount", "amount", "total", "total_amount",
        "payment_amount", "txn_amount", "order_amount", "value",
        "gross", "gross_val",
    ],
    "fee_pct": [
        "fee_pct", "fee_percent", "commission_pct", "rate",
        "gateway_fee_pct", "fee_rate", "pct",
    ],
    "fee_amount": [
        "fee_amount", "fee", "commission", "commission_amount",
        "gateway_fee", "charges", "deduction", "processing_fee",
        "fee_val",
    ],
    "net_settled": [
        "net_settled", "net_amount", "settled_amount", "payout_amount",
        "net_payout", "settlement_amount", "net_settled_amount",
        "amount_settled", "net", "net_val",
    ],
    "utr": [
        "utr", "utr_number", "transaction_ref", "bank_ref",
        "reference_number", "utr_ref", "bank_reference",
        "neft_utr", "imps_utr", "rtgs_utr", "ref", "reference",
    ],
    "settlement_date": [
        "settlement_date", "settle_date", "payout_date",
        "settlement_time", "settled_on", "paid_on", "credit_date",
        "date", "settlement",
    ],
}

BANK_ALIASES: dict[str, list[str]] = {
    "bank_txn_id": [
        "bank_txn_id", "txn_id", "transaction_id", "ref_no",
        "bank_transaction_id", "statement_ref", "entry_id",
        "sno", "serial_no", "id",
    ],
    "utr": [
        "utr", "utr_number", "transaction_ref", "bank_ref",
        "reference_number", "utr_ref", "reference",
        "neft_utr", "imps_utr", "rtgs_utr", "ref",
    ],
    "credited_amount": [
        "credited_amount", "credit_amount", "amount_credited",
        "deposit", "deposit_amount", "credit", "inflow",
        "received_amount", "amount", "balance", "credit_amt",
    ],
    "value_date": [
        "value_date", "date", "txn_date", "transaction_date",
        "posting_date", "entry_date", "credited_on",
    ],
    "narration": [
        "narration", "description", "remarks", "note",
        "txn_description", "particulars", "details", "memo",
        "desc",
    ],
}

# Map file_type -> alias dict
_FILE_TYPE_ALIASES: dict[str, dict[str, list[str]]] = {
    "ledger": LEDGER_ALIASES,
    "gateway": GATEWAY_ALIASES,
    "bank": BANK_ALIASES,
}

# Map file_type -> expected columns
_FILE_TYPE_EXPECTED: dict[str, list[str]] = {
    "ledger": EXPECTED_LEDGER_COLS,
    "gateway": EXPECTED_GATEWAY_COLS,
    "bank": EXPECTED_BANK_COLS,
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Collapse a column name to a canonical comparison form.

    Lowercases, strips whitespace, collapses runs of underscores/spaces/hyphens.
    """
    s = name.strip().lower()
    s = re.sub(r"[\s_\-]+", "", s)
    return s


def _build_reverse_index(aliases: dict[str, list[str]]) -> dict[str, str]:
    """Map every normalized alias form -> its canonical column name."""
    idx: dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            idx[_normalize_name(alias)] = canonical
    return idx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MEDIUM_CONFIDENCE_THRESHOLD = 0.75


def suggest_column_mapping(
    uploaded_columns: list[str],
    file_type: str,
    confidence_threshold: float = MEDIUM_CONFIDENCE_THRESHOLD,
) -> dict:
    """
    Suggest a mapping from uploaded column names to canonical names.

    Args:
        uploaded_columns: Column names from the user's CSV.
        file_type: One of "ledger", "gateway", "bank".
        confidence_threshold: Minimum fuzzy-match ratio (0-1) for
            medium-confidence auto-matches.

    Returns:
        {
            "auto_mapped": {canonical_col: {"source_col": ..., "confidence": "high"|"medium"}},
            "unmapped_required": [canonical columns with no confident match],
            "unused_uploaded_columns": [uploaded columns not mapped to anything],
        }
    """
    if file_type not in _FILE_TYPE_EXPECTED:
        raise ValueError(f"Unknown file_type: {file_type}. Must be one of: {list(_FILE_TYPE_EXPECTED.keys())}")

    expected = _FILE_TYPE_EXPECTED[file_type]
    aliases = _FILE_TYPE_ALIASES[file_type]
    reverse_idx = _build_reverse_index(aliases)

    # Phase 1: Exact / alias matching (high confidence)
    auto_mapped: dict[str, dict] = {}
    used_uploaded: set[str] = set()

    for canonical in expected:
        norm_canonical = _normalize_name(canonical)
        # Try exact canonical match first
        for col in uploaded_columns:
            if _normalize_name(col) == norm_canonical:
                auto_mapped[canonical] = {"source_col": col, "confidence": "high"}
                used_uploaded.add(col)
                break
        else:
            # Try alias match
            for col in uploaded_columns:
                norm_col = _normalize_name(col)
                if norm_col in reverse_idx and reverse_idx[norm_col] == canonical:
                    auto_mapped[canonical] = {"source_col": col, "confidence": "high"}
                    used_uploaded.add(col)
                    break

    # Phase 2: Fuzzy matching for remaining unmapped canonicals
    unmapped_required: list[str] = []
    remaining_uploaded = [c for c in uploaded_columns if c not in used_uploaded]

    for canonical in expected:
        if canonical in auto_mapped:
            continue

        best_col = None
        best_ratio = 0.0

        for col in remaining_uploaded:
            ratio = SequenceMatcher(None, _normalize_name(canonical), _normalize_name(col)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_col = col

        if best_col and best_ratio >= confidence_threshold:
            auto_mapped[canonical] = {"source_col": best_col, "confidence": "medium"}
            used_uploaded.add(best_col)
            remaining_uploaded = [c for c in remaining_uploaded if c not in used_uploaded]
        else:
            unmapped_required.append(canonical)

    unused_uploaded = [c for c in uploaded_columns if c not in used_uploaded]

    return {
        "auto_mapped": auto_mapped,
        "unmapped_required": unmapped_required,
        "unused_uploaded_columns": unused_uploaded,
    }
