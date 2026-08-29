from dataclasses import dataclass, field

import pandas as pd

from src.matcher.special_cases import SpecialCaseResult
from src.matcher.scoring import MatchStatus


# Reason codes for exceptions — each maps to a specific, actionable cause
REASON_CODES = {
    "ORPHAN_NO_GATEWAY_MATCH": "Bank credit has no matching gateway transaction — funds arrived but origin is unknown",
    "ORPHAN_NO_LEDGER_MATCH": "Ledger order has no matching gateway transaction — payment likely failed or was never initiated",
    "DUPLICATE_UTR_ERROR": "Same UTR credited multiple times in bank statement — possible double-credit error",
    "REFUND_NOT_REFLECTED": "Ledger shows refund but gateway/bank still show original credit — reversal not yet processed",
    "UNVERIFIED_PARTIAL": "Order has multiple gateway rows but split amounts do not reconcile to expected total",
    "UNEXPLAINED_AMOUNT_GAP": "Amounts do not reconcile across sources beyond tolerance — cause unknown",
    "LOW_CONFIDENCE": "Combined score too low to classify — multiple weak signals",
}


# Maps machine-readable override reasons (from scoring_config) to the
# canonical reason codes used in the exception summary output.
OVERRIDE_REASON_MAP = {
    "DUPLICATE_UTR_DETECTED": "DUPLICATE_UTR_ERROR",
    "REFUND_NOT_REFLECTED": "REFUND_NOT_REFLECTED",
}


@dataclass
class CategorizationResult:
    """Output of the exception categorizer."""
    exception_categories: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


def _find_bank_orphan(order_id: str, bank_orphans: list[dict]) -> bool:
    """Check if an order_id is a bank orphan (by bank_txn_id)."""
    return any(b["bank_txn_id"] == order_id for b in bank_orphans)


def _find_duplicate_utr_order(order_id: str, duplicate_utrs: list[dict], gateway: pd.DataFrame) -> bool:
    """Check if an order_id's gateway row uses a duplicate UTR."""
    dup_utrs = {d["utr"] for d in duplicate_utrs}
    row = gateway[gateway["order_ref"] == order_id]
    if len(row) == 0:
        return False
    return row["utr"].isin(dup_utrs).any()


def categorize_exceptions(
    scores: pd.DataFrame,
    special_cases: SpecialCaseResult,
    partial_groups: dict,
    ledger: pd.DataFrame,
    gateway: pd.DataFrame,
) -> CategorizationResult:
    """
    For every EXCEPTION-status record, assign a specific reason code.

    Also categorizes RESOLVED_WITH_REASONING records with explanatory tags
    (these aren't exceptions, but benefit from knowing WHY they were resolved).

    Returns:
        CategorizationResult mapping order_id -> reason code + explanation.
    """
    exceptions = scores[scores["match_status"].apply(lambda x: x == MatchStatus.EXCEPTION)]
    resolved = scores[scores["match_status"].apply(lambda x: x == MatchStatus.RESOLVED_WITH_REASONING)]

    categories = {}

    # --- Categorize exceptions ---
    for _, row in exceptions.iterrows():
        oid = row["order_id"]
        reason = None

        # Check: pipeline-set override reason (duplicate UTR / refund
        # mismatch) — authoritative, set by apply_special_case_overrides()
        override = row.get("override_reason")
        if override is not None and not (isinstance(override, float) and pd.isna(override)):
            reason = OVERRIDE_REASON_MAP.get(str(override), str(override))

        # Check: bank orphan (no gateway match)
        if reason is None and _find_bank_orphan(oid, special_cases.orphan_bank):
            reason = "ORPHAN_NO_GATEWAY_MATCH"

        # Check: ledger orphan (no gateway match)
        elif reason is None and oid in special_cases.orphan_ledger:
            reason = "ORPHAN_NO_LEDGER_MATCH"

        # Check: duplicate UTR
        elif _find_duplicate_utr_order(oid, special_cases.duplicate_utrs, gateway):
            reason = "DUPLICATE_UTR_ERROR"

        # Check: refund not reflected
        elif oid in special_cases.refund_mismatches:
            reason = "REFUND_NOT_REFLECTED"

        # Check: unverified partial (duplicated but amounts don't reconcile)
        elif oid in partial_groups and not partial_groups[oid].get("verified", False):
            reason = "UNVERIFIED_PARTIAL"

        # Check: amount gap (amount_score is very low)
        elif row.get("amount_score", 1.0) < 0.3:
            reason = "UNEXPLAINED_AMOUNT_GAP"

        # Fallback
        else:
            reason = "LOW_CONFIDENCE"

        categories[oid] = {
            "reason_code": reason,
            "explanation": REASON_CODES[reason],
            "confidence_score": row["confidence_score"],
        }

    # --- Tag resolved records (not exceptions, but useful for reporting) ---
    for _, row in resolved.iterrows():
        oid = row["order_id"]
        tags = []

        if oid in partial_groups and partial_groups[oid].get("verified", False):
            tags.append("PARTIAL_SETTLEMENT_VERIFIED")
        if oid in special_cases.refund_mismatches:
            tags.append("REFUND_NOT_REFLECTED")
        if row.get("timing_score", 1.0) < 0.85:
            tags.append("TIMING_LAG")
        if row.get("amount_score", 1.0) < 0.95:
            tags.append("AMOUNT_DRIFT")

        categories[oid] = {
            "reason_code": "RESOLVED" if not tags else "+".join(tags),
            "explanation": f"Resolved with reasoning: {', '.join(tags)}" if tags else "Resolved with reasoning",
            "confidence_score": row["confidence_score"],
        }

    # Build summary
    exception_cats = {}
    for oid, info in categories.items():
        status = scores.loc[scores["order_id"] == oid, "match_status"].iloc[0]
        if status == MatchStatus.EXCEPTION:
            code = info["reason_code"]
            exception_cats[code] = exception_cats.get(code, 0) + 1

    summary = {
        "total_records": len(scores),
        "exception_count": len(exceptions),
        "resolved_count": len(resolved),
        "exception_breakdown": exception_cats,
    }

    return CategorizationResult(
        exception_categories=categories,
        summary=summary,
    )


def print_categorization(result: CategorizationResult) -> None:
    """Pretty-print the categorization results."""
    print("=== Exception Categorization ===\n")

    for oid, info in sorted(result.exception_categories.items()):
        print(f"  {oid}: {info['reason_code']}")
        print(f"    {info['explanation']}")
        print(f"    confidence: {info['confidence_score']:.4f}")
        print()

    print("=== Summary ===")
    for k, v in result.summary.items():
        print(f"  {k}: {v}")
