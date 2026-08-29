from enum import Enum

import numpy as np
import pandas as pd

from src.config.scoring_config import COMPOSITE_WEIGHTS, STATUS_THRESHOLDS
from src.matcher.validators import amount_score, timing_score, reference_score


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    RESOLVED_WITH_REASONING = "RESOLVED_WITH_REASONING"
    EXCEPTION = "EXCEPTION"


def compute_confidence(
    amount: float, timing: float, reference: float
) -> float:
    """Compute weighted composite confidence score."""
    return round(
        COMPOSITE_WEIGHTS["amount"] * amount
        + COMPOSITE_WEIGHTS["timing"] * timing
        + COMPOSITE_WEIGHTS["reference"] * reference,
        4,
    )


def classify_status(confidence: float) -> MatchStatus:
    """Map confidence score to a match status."""
    if confidence >= STATUS_THRESHOLDS["matched"]:
        return MatchStatus.MATCHED
    elif confidence >= STATUS_THRESHOLDS["resolved"]:
        return MatchStatus.RESOLVED_WITH_REASONING
    else:
        return MatchStatus.EXCEPTION


def score_ledger_gateway_rows(
    lg_joined: pd.DataFrame,
    partial_groups: dict,
) -> pd.DataFrame:
    """
    Score all rows in the ledger-gateway joined DataFrame.

    For partial settlement orders, the individual rows' scores are
    averaged to produce a single score per order_id.

    Returns:
        DataFrame with one row per (order_id, gateway_txn_id) pair,
        plus columns: amount_score, timing_score, reference_score,
        confidence_score, match_status.
    """
    result = lg_joined.copy()
    partial_refs = set(partial_groups.keys())

    result["amount_score"] = result.apply(
        lambda r: amount_score(r, partial_groups), axis=1
    )
    result["timing_score"] = result.apply(timing_score, axis=1)
    result["reference_score"] = result.apply(
        lambda r: reference_score(
            r,
            is_partial=r.get("order_ref") in partial_refs,
            partial_groups=partial_groups,
        ),
        axis=1,
    )
    result["confidence_score"] = result.apply(
        lambda r: compute_confidence(
            r["amount_score"], r["timing_score"], r["reference_score"]
        ),
        axis=1,
    )
    result["match_status"] = result["confidence_score"].apply(classify_status)
    return result


def aggregate_partial_orders(scored: pd.DataFrame) -> pd.DataFrame:
    """
    For partial settlement orders (multiple rows per order_id),
    aggregate to one row per order_id by averaging the sub-scores.

    Non-partial orders pass through unchanged.
    """
    partial_mask = scored["order_id"].duplicated(keep=False)
    partial_rows = scored[partial_mask]
    non_partial = scored[~partial_mask]

    if len(partial_rows) == 0:
        return scored

    agg = partial_rows.groupby("order_id").agg(
        customer_name=("customer_name", "first"),
        order_amount=("order_amount", "first"),
        order_date=("order_date", "first"),
        payment_mode=("payment_mode", "first"),
        status=("status", "first"),
        gateway_txn_ids=("gateway_txn_id", list),
        utrs=("utr", list),
        amount_score=("amount_score", "mean"),
        timing_score=("timing_score", "mean"),
        reference_score=("reference_score", "mean"),
    ).reset_index()

    agg["confidence_score"] = agg.apply(
        lambda r: compute_confidence(
            r["amount_score"], r["timing_score"], r["reference_score"]
        ),
        axis=1,
    )
    agg["match_status"] = agg["confidence_score"].apply(classify_status)

    return pd.concat([non_partial, agg], ignore_index=True)


def score_orphan_ledger(ledger_orphans: pd.DataFrame) -> pd.DataFrame:
    """Score ledger orphans (no gateway match) as EXCEPTION."""
    if len(ledger_orphans) == 0:
        return pd.DataFrame()

    result = ledger_orphans[["order_id", "customer_name", "order_amount", "order_date", "payment_mode", "status"]].copy()
    result["gateway_txn_ids"] = [[] for _ in range(len(result))]
    result["utrs"] = [[] for _ in range(len(result))]
    result["amount_score"] = 0.0
    result["timing_score"] = 0.0
    result["reference_score"] = 0.0
    result["confidence_score"] = 0.0
    result["match_status"] = MatchStatus.EXCEPTION
    return result


def score_orphan_bank(bank_orphans: pd.DataFrame) -> pd.DataFrame:
    """Score bank orphans (no gateway match) as EXCEPTION."""
    if len(bank_orphans) == 0:
        return pd.DataFrame()

    result = pd.DataFrame()
    result["order_id"] = bank_orphans["bank_txn_id"]
    result["customer_name"] = "UNKNOWN"
    result["order_amount"] = bank_orphans["credited_amount"]
    result["order_date"] = bank_orphans["value_date"]
    result["payment_mode"] = "UNKNOWN"
    result["status"] = "unknown"
    result["gateway_txn_ids"] = [[] for _ in range(len(result))]
    result["utrs"] = bank_orphans["utr"].apply(lambda u: [u])
    result["amount_score"] = 0.0
    result["timing_score"] = 0.0
    result["reference_score"] = 0.0
    result["confidence_score"] = 0.0
    result["match_status"] = MatchStatus.EXCEPTION
    return result


def run_scoring(
    lg_joined: pd.DataFrame,
    ledger_orphans: pd.DataFrame,
    bank_orphans: pd.DataFrame,
    partial_groups: dict,
) -> pd.DataFrame:
    """
    Run full scoring pipeline. Returns a unified DataFrame with one row
    per order_id (or bank orphan ID) and columns:
        order_id, customer_name, order_amount, order_date, payment_mode,
        status, gateway_txn_ids, utrs, amount_score, timing_score,
        reference_score, confidence_score, match_status.
    """
    scored = score_ledger_gateway_rows(lg_joined, partial_groups)
    aggregated = aggregate_partial_orders(scored)

    orphan_lg = score_orphan_ledger(ledger_orphans)
    orphan_bn = score_orphan_bank(bank_orphans)

    all_rows = pd.concat([aggregated, orphan_lg, orphan_bn], ignore_index=True)
    return all_rows.sort_values("order_id").reset_index(drop=True)
