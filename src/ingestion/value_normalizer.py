"""
Level 2 — Value / Format Normalization
=======================================

Normalizes cell values within already-mapped columns: dates to ISO format,
amounts to floats, status values to canonical vocabulary. Each function
returns both the normalized data AND a list of specific issues (row index
+ reason) — never silently coercing bad values without reporting them.
"""

from __future__ import annotations

import re

import pandas as pd


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------

# Common date formats found in real-world payment/finance exports.
_DATE_FORMATS = [
    "%Y-%m-%d",       # 2026-03-15
    "%d-%m-%Y",       # 15-03-2026
    "%d/%m/%Y",       # 15/03/2026
    "%m/%d/%Y",       # 03/15/2026
    "%Y/%m/%d",       # 2026/03/15
    "%d %b %Y",       # 15 Mar 2026
    "%d %B %Y",       # 15 March 2026
    "%b %d, %Y",      # Mar 15, 2026
    "%B %d, %Y",      # March 15, 2026
    "%d-%b-%Y",       # 15-Mar-2026
    "%d-%b-%y",       # 15-Mar-26
    "%Y%m%d",         # 20260315
]


def normalize_dates(series: pd.Series) -> tuple[pd.Series, list[dict]]:
    """
    Parse a date column into ISO format (YYYY-MM-DD strings).

    Returns:
        (normalized_series, issues) where issues is a list of
        {"row_index": int, "original_value": str, "reason": str}.
    """
    issues: list[dict] = []
    result = series.copy()

    for idx, raw_val in series.items():
        if pd.isna(raw_val) or str(raw_val).strip() == "":
            issues.append({
                "row_index": int(idx),
                "original_value": str(raw_val),
                "reason": "empty or null value",
            })
            result.at[idx] = None
            continue

        raw_str = str(raw_val).strip()

        # Try pandas flexible parser first (handles ISO and many common formats)
        # Try ISO format explicitly first to avoid dayfirst ambiguity warning
        parsed = pd.to_datetime(raw_str, format="%Y-%m-%d", errors="coerce")
        if pd.isna(parsed):
            parsed = pd.to_datetime(raw_str, dayfirst=True, errors="coerce", format="mixed")
        if pd.notna(parsed):
            result.at[idx] = parsed.strftime("%Y-%m-%d")
            continue

        # Try explicit formats
        parsed_ok = False
        for fmt in _DATE_FORMATS:
            try:
                from datetime import datetime
                parsed = datetime.strptime(raw_str, fmt)
                result.at[idx] = parsed.strftime("%Y-%m-%d")
                parsed_ok = True
                break
            except ValueError:
                continue

        if not parsed_ok:
            issues.append({
                "row_index": int(idx),
                "original_value": raw_str,
                "reason": f"unrecognized date format: '{raw_str}'",
            })
            result.at[idx] = None

    return result, issues


# ---------------------------------------------------------------------------
# Amount normalization
# ---------------------------------------------------------------------------

# Patterns to strip from currency strings
_CURRENCY_STRIP = re.compile(r"[₹$€£¥\s,]")


def normalize_amounts(series: pd.Series) -> tuple[pd.Series, list[dict]]:
    """
    Strip currency symbols, commas, whitespace and convert to float.

    Returns:
        (normalized_series, issues) where issues is a list of
        {"row_index": int, "original_value": str, "reason": str}.
    """
    issues: list[dict] = []
    result = series.copy()

    for idx, raw_val in series.items():
        if pd.isna(raw_val) or str(raw_val).strip() == "":
            issues.append({
                "row_index": int(idx),
                "original_value": str(raw_val),
                "reason": "empty or null amount",
            })
            result.at[idx] = None
            continue

        raw_str = str(raw_val).strip()

        # Strip currency symbols and commas
        cleaned = _CURRENCY_STRIP.sub("", raw_str)

        # Handle parenthetical negatives: (1234.56) -> -1234.56
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]

        # Handle explicit negative signs with currency
        if raw_str.startswith("-") and not cleaned.startswith("-"):
            cleaned = "-" + cleaned

        try:
            result.at[idx] = float(cleaned)
        except (ValueError, TypeError):
            issues.append({
                "row_index": int(idx),
                "original_value": raw_str,
                "reason": f"cannot convert to number: '{raw_str}'",
            })
            result.at[idx] = None

    return result, issues


# ---------------------------------------------------------------------------
# Status normalization
# ---------------------------------------------------------------------------

# Canonical status values and their alias maps.
# Keys are the canonical values used in the pipeline; values are lists of
# common alternative spellings/wordings that should map to them.
STATUS_ALIASES: dict[str, list[str]] = {
    "paid": [
        "paid", "completed", "success", "successful", "settled",
        "processed", "captured", "done", "approved",
    ],
    "refunded": [
        "refunded", "refund", "reversed", "reversal", "returned",
        "cancel_refund", "chargeback",
    ],
    "payment_failed": [
        "payment_failed", "failed", "failure", "error",
        "declined", "rejected", "void", "cancelled", "canceled",
    ],
}


def normalize_status(
    series: pd.Series,
    canonical_values: list[str] | None = None,
    alias_map: dict[str, list[str]] | None = None,
) -> tuple[pd.Series, list[dict]]:
    """
    Normalize status values to canonical vocabulary via case-insensitive
    alias matching.

    Args:
        series: Raw status column.
        canonical_values: Allowed output values. Defaults to
            ["paid", "refunded", "payment_failed"].
        alias_map: Custom alias map. Defaults to STATUS_ALIASES.

    Returns:
        (normalized_series, issues) where issues is a list of
        {"row_index": int, "original_value": str, "reason": str}.
    """
    if canonical_values is None:
        canonical_values = list(STATUS_ALIASES.keys())
    if alias_map is None:
        alias_map = STATUS_ALIASES

    # Build reverse lookup: normalized alias -> canonical
    reverse: dict[str, str] = {}
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            reverse[alias.strip().lower()] = canonical

    issues: list[dict] = []
    result = series.copy()

    for idx, raw_val in series.items():
        if pd.isna(raw_val) or str(raw_val).strip() == "":
            issues.append({
                "row_index": int(idx),
                "original_value": str(raw_val),
                "reason": "empty or null status",
            })
            result.at[idx] = None
            continue

        raw_str = str(raw_val).strip()
        norm = raw_str.lower()

        if norm in reverse:
            result.at[idx] = reverse[norm]
        else:
            issues.append({
                "row_index": int(idx),
                "original_value": raw_str,
                "reason": f"unrecognized status value: '{raw_str}'",
            })
            result.at[idx] = None

    return result, issues


# ---------------------------------------------------------------------------
# Per-file-type normalization dispatch
# ---------------------------------------------------------------------------

# Which columns get which normalization, per file type
_NORMALIZATION_PLAN: dict[str, dict[str, list[str]]] = {
    "ledger": {
        "dates": ["order_date"],
        "amounts": ["order_amount"],
        "status": ["status"],
    },
    "gateway": {
        "dates": ["settlement_date"],
        "amounts": ["gross_amount", "fee_amount", "net_settled"],
        "status": [],
    },
    "bank": {
        "dates": ["value_date"],
        "amounts": ["credited_amount"],
        "status": [],
    },
}


def normalize_file_columns(
    df: pd.DataFrame,
    file_type: str,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """
    Apply all relevant normalizations to a mapped DataFrame.

    Returns:
        (normalized_df, warnings, unresolvable_issues)
        - warnings: non-fatal issues (e.g. date format assumed)
        - unresolvable_issues: values that could not be normalized at all
    """
    if file_type not in _NORMALIZATION_PLAN:
        raise ValueError(f"Unknown file_type: {file_type}")

    plan = _NORMALIZATION_PLAN[file_type]
    df = df.copy()
    warnings: list[dict] = []
    unresolvable: list[dict] = []

    # Normalize dates
    for col in plan["dates"]:
        if col in df.columns:
            normalized, issues = normalize_dates(df[col])
            df[col] = normalized
            for issue in issues:
                issue["column"] = col
                if "unrecognized" in issue["reason"]:
                    unresolvable.append(issue)
                else:
                    warnings.append(issue)

    # Normalize amounts
    for col in plan["amounts"]:
        if col in df.columns:
            normalized, issues = normalize_amounts(df[col])
            df[col] = normalized
            for issue in issues:
                issue["column"] = col
                if "cannot convert" in issue["reason"] or "empty" in issue["reason"]:
                    unresolvable.append(issue)
                else:
                    warnings.append(issue)

    # Normalize status
    for col in plan["status"]:
        if col in df.columns:
            normalized, issues = normalize_status(df[col])
            df[col] = normalized
            for issue in issues:
                issue["column"] = col
                if "unrecognized" in issue["reason"] or "empty" in issue["reason"]:
                    unresolvable.append(issue)
                else:
                    warnings.append(issue)

    return df, warnings, unresolvable
