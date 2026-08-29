"""
Ingestion Pipeline — Normalize Uploaded Files
==============================================

Orchestrates Level 1 (column mapping) and Level 2 (value normalization)
to transform an arbitrary CSV into the exact schema the reconciliation
pipeline expects.

This module is the ONLY entry point for the ingestion layer — the rest
of the system (matcher, explain, grading) never calls column_mapper or
value_normalizer directly.
"""

from __future__ import annotations

import pandas as pd

from src.ingestion.column_mapper import suggest_column_mapping
from src.ingestion.value_normalizer import normalize_file_columns
from src.matcher.loader import EXPECTED_BANK_COLS, EXPECTED_GATEWAY_COLS, EXPECTED_LEDGER_COLS


_EXPECTED_COLS: dict[str, list[str]] = {
    "ledger": EXPECTED_LEDGER_COLS,
    "gateway": EXPECTED_GATEWAY_COLS,
    "bank": EXPECTED_BANK_COLS,
}

# If more than this fraction of rows have unresolvable issues, the file
# is considered too broken to proceed automatically.
_UNRESOLVABLE_THRESHOLD = 0.10


def normalize_uploaded_file(
    df: pd.DataFrame,
    file_type: str,
    manual_mapping: dict[str, str] | None = None,
) -> dict:
    """
    Normalize an uploaded DataFrame into the canonical schema.

    Args:
        df: Raw DataFrame from the uploaded CSV.
        file_type: One of "ledger", "gateway", "bank".
        manual_mapping: Optional user-provided overrides mapping
            canonical column name -> uploaded column name. These take
            priority over auto-mapping.

    Returns:
        {
            "status": "ready" | "needs_mapping" | "failed",
            "auto_mapped": {canonical: {"source_col": ..., "confidence": ...}},
            "unmapped_required": [...],           # only if needs_mapping
            "unused_uploaded_columns": [...],
            "normalization_warnings": [...],      # non-fatal issues
            "unresolvable_issues": [...],         # fatal value problems
            "normalized_df": <DataFrame>,          # only if status == "ready"
        }

    NOTE: the key is "auto_mapped" (matching column_mapper.py's
    suggest_column_mapping() output and backend/main.py's expectations)
    — this was previously inconsistently named "mapping_applied" here,
    which caused an unhandled KeyError in backend/main.py's needs_mapping
    handling whenever a file required manual column mapping. Keep this
    key name in sync with backend/main.py if either side changes.
    """
    if file_type not in _EXPECTED_COLS:
        raise ValueError(f"Unknown file_type: {file_type}. Must be one of: {list(_EXPECTED_COLS.keys())}")

    expected = _EXPECTED_COLS[file_type]

    # ------------------------------------------------------------------
    # Step 1: Column mapping
    # ------------------------------------------------------------------
    uploaded_cols = list(df.columns)
    mapping_result = suggest_column_mapping(uploaded_cols, file_type)

    # Merge manual overrides (user-provided mappings from confirm-mapping)
    auto_mapped = mapping_result["auto_mapped"]
    unmapped_required = list(mapping_result["unmapped_required"])
    unused_uploaded = list(mapping_result["unused_uploaded_columns"])

    if manual_mapping:
        for canonical, source_col in manual_mapping.items():
            if source_col and source_col in uploaded_cols:
                auto_mapped[canonical] = {
                    "source_col": source_col,
                    "confidence": "manual",
                }
                if canonical in unmapped_required:
                    unmapped_required.remove(canonical)
                # Remove from unused if it was there
                if source_col in unused_uploaded:
                    unused_uploaded.remove(source_col)

    # ------------------------------------------------------------------
    # Step 2: Check if all required columns are mapped
    # ------------------------------------------------------------------
    if unmapped_required:
        return {
            "status": "needs_mapping",
            "auto_mapped": auto_mapped,
            "unmapped_required": unmapped_required,
            "unused_uploaded_columns": unused_uploaded,
            "normalization_warnings": [],
            "unresolvable_issues": [],
            "normalized_df": None,
        }

    # ------------------------------------------------------------------
    # Step 3: Rename columns to canonical names
    # ------------------------------------------------------------------
    rename_map = {info["source_col"]: canonical for canonical, info in auto_mapped.items()}
    df_normalized = df.rename(columns=rename_map)

    # ------------------------------------------------------------------
    # Step 4: Value normalization (Level 2)
    # ------------------------------------------------------------------
    df_normalized, warnings, unresolvable = normalize_file_columns(
        df_normalized, file_type,
    )

    # ------------------------------------------------------------------
    # Step 5: Check if too many values are broken
    # ------------------------------------------------------------------
    total_rows = len(df_normalized)
    if total_rows > 0 and len(unresolvable) > 0:
        # Count affected rows (a single row can have multiple issues)
        affected_rows = len({issue["row_index"] for issue in unresolvable})
        broken_fraction = affected_rows / total_rows
        if broken_fraction > _UNRESOLVABLE_THRESHOLD:
            return {
                "status": "failed",
                "auto_mapped": auto_mapped,
                "unmapped_required": [],
                "unused_uploaded_columns": unused_uploaded,
                "normalization_warnings": warnings,
                "unresolvable_issues": unresolvable,
                "normalized_df": None,
                "failure_reason": (
                    f"{affected_rows}/{total_rows} rows "
                    f"({broken_fraction:.0%}) have unresolvable values — "
                    f"exceeds {_UNRESOLVABLE_THRESHOLD:.0%} threshold"
                ),
            }

    # ------------------------------------------------------------------
    # Step 6: Verify all expected columns are present in the result
    # ------------------------------------------------------------------
    missing_in_result = [c for c in expected if c not in df_normalized.columns]
    if missing_in_result:
        return {
            "status": "failed",
            "auto_mapped": auto_mapped,
            "unmapped_required": [],
            "unused_uploaded_columns": unused_uploaded,
            "normalization_warnings": warnings,
            "unresolvable_issues": unresolvable,
            "normalized_df": None,
            "failure_reason": f"Internal error: expected columns missing after mapping: {missing_in_result}",
        }

    return {
        "status": "ready",
        "auto_mapped": auto_mapped,
        "unmapped_required": [],
        "unused_uploaded_columns": unused_uploaded,
        "normalization_warnings": warnings,
        "unresolvable_issues": unresolvable,
        "normalized_df": df_normalized,
    }
