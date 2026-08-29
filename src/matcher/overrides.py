"""
Special-Case Overrides
======================

Bridges the gap between special-case detection and final scoring.

Why this exists:
    The per-row validators (amount/timing/reference) only look at ONE
    transaction row at a time. Some genuine errors are invisible to them
    because every individual row looks perfectly fine on its own:

      - A duplicated bank credit (same UTR credited twice): each credit
        individually has exactly correct amounts.
      - A refund not yet reflected (ledger says "refunded", gateway/bank
        still show a normal settlement credit): the settlement math is
        flawless — it's the ledger STATUS that contradicts it.

    detect_duplicate_utrs() and detect_refund_mismatches() find these, but
    their findings must be FORCED onto the final scores — otherwise these
    rows sail through as MATCHED with perfect confidence. This module
    applies those forced overrides AFTER run_scoring() completes.

Downstream contract:
    Every row gets an `override_reason` column: either a machine-readable
    reason string (from scoring_config.SPECIAL_CASE_OVERRIDES) or None/NaN
    for untouched rows. The explainer and categorizer read this column to
    produce specific explanations instead of generic score-based ones.
"""

import pandas as pd

from src.config.scoring_config import SPECIAL_CASE_OVERRIDES
from src.matcher.special_cases import SpecialCaseResult
from src.matcher.scoring import MatchStatus


def apply_special_case_overrides(
    scores_df: pd.DataFrame,
    special_cases_result: SpecialCaseResult,
) -> pd.DataFrame:
    """
    Force EXCEPTION status onto rows flagged by special-case detectors.

    Args:
        scores_df: Scored DataFrame from run_scoring() (after partial
            aggregation). Modified on a copy; sub-scores of unaffected
            rows are left completely untouched.
        special_cases_result: Output of run_special_cases(), containing
            duplicate_utrs and refund_mismatches.

    Returns:
        Copy of scores_df with an added `override_reason` column and with
        match_status / confidence_score overridden for flagged rows.
    """
    result = scores_df.copy()

    # Column must exist even if no overrides fire
    result["override_reason"] = None

    dup_utrs = {d["utr"] for d in special_cases_result.duplicate_utrs}
    refund_orders = set(special_cases_result.refund_mismatches)

    def _row_utrs(row) -> set:
        """
        Collect all UTRs a row references.

        Rows come in two shapes: regular joined rows carry a scalar `utr`
        column, while aggregated partial-settlement and orphan rows carry
        a `utrs` list column (with `utr` absent/NaN). Handle both.
        """
        utrs = set()
        val = row.get("utr")
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            utrs.add(val)
        lst = row.get("utrs")
        if isinstance(lst, list):
            utrs.update(lst)
        return utrs

    def _row_override_reason(row) -> str | None:
        # Duplicate UTR check: does any of this row's UTRs appear 2+ times
        # in the bank statement?
        if dup_utrs and _row_utrs(row) & dup_utrs:
            return SPECIAL_CASE_OVERRIDES["duplicate_utr_reason"]
        if row.get("order_id") in refund_orders:
            return SPECIAL_CASE_OVERRIDES["refund_mismatch_reason"]
        return None

    reasons = result.apply(_row_override_reason, axis=1)
    override_mask = reasons.notna()
    result.loc[override_mask, "override_reason"] = reasons[override_mask]

    # Force status + confidence for overridden rows
    result.loc[override_mask, "match_status"] = MatchStatus.EXCEPTION

    dup_mask = result["override_reason"] == SPECIAL_CASE_OVERRIDES["duplicate_utr_reason"]
    refund_mask = result["override_reason"] == SPECIAL_CASE_OVERRIDES["refund_mismatch_reason"]
    result.loc[dup_mask, "confidence_score"] = SPECIAL_CASE_OVERRIDES["duplicate_utr_score"]
    result.loc[refund_mask, "confidence_score"] = SPECIAL_CASE_OVERRIDES["refund_mismatch_score"]

    n_dup = int(dup_mask.sum())
    n_refund = int(refund_mask.sum())
    if n_dup or n_refund:
        print(
            f"  [overrides] Forced EXCEPTION on {n_dup} duplicate-UTR row(s), "
            f"{n_refund} refund-mismatch row(s)"
        )

    return result
