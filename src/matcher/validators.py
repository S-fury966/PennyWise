import numpy as np
import pandas as pd

from src.config.scoring_config import (
    SETTLEMENT_WINDOW,
    AMOUNT_TOLERANCE,
    FEE_TOLERANCE,
    REFERENCE_SCORE,
)


def _evaluate_curve(value: float, curve: list[tuple], default: float) -> float:
    """Walk a (threshold, score) curve and return the score for the given value.

    The curve is evaluated in order. The first entry whose threshold exceeds
    the value wins. If no entry matches, `default` is returned.

    For timing_score, curve entries are (lag_days, score) and we want the
    first entry where lag_days >= actual_lag. For amount_score, entries are
    (tolerance_pct, score) and we want the first entry where the tolerance
    exceeds the actual gap ratio.
    """
    for threshold, score in curve:
        if value <= threshold:
            return score
    return default


def amount_score(row: pd.Series, partial_groups: dict | None = None) -> float:
    """
    Score how well the amounts reconcile for a single transaction row.

    Uses PROPORTIONAL tolerance: the allowed gap is a percentage of the
    transaction amount, with a minimum flat-rupee floor for tiny transactions.

    Checks:
      1. gross_amount - fee_amount  vs  net_settled
      2. net_settled  vs  credited_amount (if bank data present)

    For partial settlements (where net_settled < gross - fee), the row is
    scored based on whether its order_ref belongs to a known partial group
    whose total net_settled matches gross-fee.

    Args:
        row: A Series containing at minimum:
             gross_amount, fee_amount, net_settled, and optionally
             credited_amount, order_ref.
        partial_groups: Optional dict mapping order_ref -> dict with keys:
             'expected_net' (gross-fee) and 'actual_sum' (sum of net_settled).

    Returns:
        Float between 0.0 and 1.0.
    """
    gross = float(row.get("gross_amount", 0) or 0)
    fee = float(row.get("fee_amount", 0) or 0)
    net_settled = float(row.get("net_settled", 0) or 0)
    credited = row.get("credited_amount", None)
    if credited is not None and not pd.isna(credited):
        credited = float(credited)
    else:
        credited = None

    expected_net = gross - fee
    flat_floor = AMOUNT_TOLERANCE["flat_floor_rupees"]
    amount_curve = AMOUNT_TOLERANCE["amount_curve"]
    default_amt = AMOUNT_TOLERANCE["default_amount_score"]

    def _score_gap(diff: float, reference_amount: float) -> float:
        """Score a gap using proportional tolerance."""
        if diff < flat_floor:
            return 1.0
        if reference_amount <= 0:
            return default_amt
        gap_ratio = diff / reference_amount
        return _evaluate_curve(gap_ratio, amount_curve, default_amt)

    # Sub-score 1: gross - fee vs net_settled
    net_diff = abs(expected_net - net_settled)
    net_score = _score_gap(net_diff, gross)

    # If net_score is low, check partial settlement groups
    if net_score < 0.5:
        order_ref = row.get("order_ref", None)
        if partial_groups and order_ref in partial_groups:
            group = partial_groups[order_ref]
            group_diff = abs(group["expected_net"] - group["actual_sum"])
            if group_diff < flat_floor:
                net_score = 0.9  # valid partial — group reconciles
            elif group_diff / max(group["expected_net"], 1) < 0.001:
                net_score = 0.7  # partial with small group drift
            else:
                net_score = 0.3  # partial but group doesn't reconcile

    # Sub-score 2: net_settled vs credited_amount
    if credited is None:
        credit_score = None  # no bank data available
    else:
        credit_diff = abs(net_settled - credited)
        credit_score = _score_gap(credit_diff, net_settled)

    # Weight: 0.6 amount, 0.4 credit (or just amount if no bank data)
    if credit_score is None:
        return round(net_score, 4)
    return round(0.6 * net_score + 0.4 * credit_score, 4)


def timing_score(row: pd.Series) -> float:
    """
    Score how well the settlement timing aligns with the order date.

    Reads the scoring curve from SETTLEMENT_WINDOW config instead of
    using hardcoded elif branches. Each entry in the config's timing_curve
    is a (lag_days, score) tuple.

    Args:
        row: A Series containing order_date and settlement_date.

    Returns:
        Float between 0.0 and 1.0.
    """
    order_date = row.get("order_date")
    settlement_date = row.get("settlement_date")

    if pd.isna(order_date) or pd.isna(settlement_date):
        return 0.5  # missing data, neutral

    lag_days = (settlement_date - order_date).days
    curve = SETTLEMENT_WINDOW["timing_curve"]
    default_score = SETTLEMENT_WINDOW["default_timing_score"]

    # Find the matching entry: first curve entry where curve_days >= lag_days
    for curve_days, score in curve:
        if lag_days <= curve_days:
            return score
    return default_score


def reference_score(
    row: pd.Series, is_partial: bool = False, partial_groups: dict | None = None
) -> float:
    """
    Score the quality of the key-based join for a single row.

    Scoring:
      0.9  — partial settlement row with VERIFIED group reconciliation
      0.2  — duplicated order_ref but group NOT verified (suspicious)
      1.0  — clean direct key match (order_id = order_ref, utr matches)
      0.95 — ledger+gateway joined, no bank data yet
      0.5  — orphan / no match on one side

    Partial settlement checks come FIRST because partial rows have
    order_ref populated (gateway side exists), but their reference score
    depends on whether the group amounts reconcile — not just on whether
    the gateway side is present.

    Args:
        row: Series from a joined DataFrame. Expected to have 'order_ref'
             (from gateway side) which may be NaN for orphans.
        is_partial: True if this row belongs to a partial settlement group.
        partial_groups: Optional dict from build_partial_groups(). Used to
             check whether a partial group's amounts actually reconcile.

    Returns:
        Float between 0.0 and 1.0.
    """
    has_bank = not pd.isna(row.get("credited_amount"))

    # Partial settlement — check verification BEFORE the general gateway check
    if is_partial:
        order_ref = row.get("order_ref", None)
        group = partial_groups.get(order_ref) if partial_groups else None
        if group and group.get("verified"):
            return REFERENCE_SCORE["verified_partial_split"]
        else:
            return REFERENCE_SCORE["unverified_duplicate"]

    has_gateway = not pd.isna(row.get("order_ref"))

    if has_gateway and has_bank:
        return REFERENCE_SCORE["full_three_way_match"]
    elif has_gateway:
        return REFERENCE_SCORE["ledger_gateway_only_match"]
    else:
        return REFERENCE_SCORE["orphan"]


def fee_plausibility_score(row: pd.Series) -> float:
    """
    Optional sanity check: is the gateway fee percentage within the
    expected range?

    This is a SEPARATE score — it is NOT folded into amount_score or
    the composite confidence calculation. It exists for future use or
    manual review.

    Args:
        row: A Series containing gross_amount and fee_amount.

    Returns:
        Float between 0.0 and 1.0:
          1.0 if fee_pct is within the configured range,
          0.5 if slightly outside,
          0.0 if wildly outside.
    """
    gross = float(row.get("gross_amount", 0) or 0)
    fee = float(row.get("fee_amount", 0) or 0)

    if gross <= 0:
        return 0.5  # can't evaluate

    fee_pct = round(fee / gross, 6)
    min_fee = FEE_TOLERANCE["min_fee_pct"]
    max_fee = FEE_TOLERANCE["max_fee_pct"]

    if min_fee <= fee_pct <= max_fee:
        return 1.0
    # Allow 0.5% slack on either side before penalizing hard
    elif (min_fee - 0.005) <= fee_pct <= (max_fee + 0.005):
        return 0.7
    else:
        return 0.3


def build_partial_groups(gateway: pd.DataFrame) -> dict:
    """
    For orders with multiple gateway rows (partial settlements),
    compute the expected net, actual sum, and verification result
    per order_ref.

    Returns:
        dict mapping order_ref -> {
            'expected_net': float,  # gross - fee
            'actual_sum': float,    # sum of net_settled across rows
            'group_diff': float,    # abs(expected_net - actual_sum)
            'verified': bool,       # True if group_diff < 0.01
        }
    """
    dup_refs = gateway["order_ref"].value_counts()
    dup_refs = dup_refs[dup_refs > 1].index.tolist()

    groups = {}
    for ref in dup_refs:
        subset = gateway[gateway["order_ref"] == ref]
        gross = subset["gross_amount"].iloc[0]
        fee = subset["fee_amount"].iloc[0]
        expected_net = gross - fee
        actual_sum = subset["net_settled"].sum()
        group_diff = abs(expected_net - actual_sum)
        groups[ref] = {
            "expected_net": expected_net,
            "actual_sum": actual_sum,
            "group_diff": group_diff,
            "verified": group_diff < 0.01,
        }
    return groups
