"""
Scoring Configuration
=====================

This file contains ALL tuning knobs for the reconciliation scoring pipeline.
Each section controls how a specific aspect of transaction matching is scored.

WHEN TO EDIT THIS FILE:
  Whenever you load a new or custom dataset with different characteristics
  (different settlement delays, different transaction sizes, different fee
  structures), review and adjust these values BEFORE running the pipeline.
  You should NOT need to touch any Python source code to tune scoring behavior.

VALUES DEFINED HERE:
  - What counts as a "normal" settlement window (how many days after an order
    the bank payment typically arrives)
  - How much amount discrepancy is tolerated before flagging a mismatch
  - What fee percentage range is considered plausible
  - How the individual sub-scores (amount, timing, reference) are weighted
    into a single confidence score
  - What confidence thresholds determine the final match status label
"""

# =============================================================================
# SETTLEMENT WINDOW
# =============================================================================
# Controls how the "timing" sub-score is calculated.
#
# The scoring works by checking how many days elapsed between the order date
# and the settlement date. Each entry in TIMING_CURVE is a (lag_days, score)
# tuple: if the lag equals lag_days, the score is the corresponding value.
# The curve is evaluated top-to-bottom; the first matching entry wins.
#
# lag_days = settlement_date - order_date (in whole days)
#
# To adjust for a dataset where settlements typically take T+3/T+5:
#   - Set expected_min_days=3, expected_max_days=5
#   - Adjust TIMING_CURVE entries so 3-5 days gets score 1.0

SETTLEMENT_WINDOW = {
    "expected_min_days": 1,
    "expected_max_days": 2,
    "acceptable_max_days": 6,
    # List of (lag_days, score) tuples. Evaluated in order; first match wins.
    # Anything beyond the last entry gets the last entry's score.
    "timing_curve": [
        (-1, 0.3),   # settlement before order — suspicious
        (0, 0.5),    # same-day — unusual but possible
        (1, 1.0),    # ideal
        (2, 1.0),    # normal
        (3, 0.85),   # acceptable, slightly late
        (4, 0.7),    # at the edge
        (5, 0.5),    # flagged but not auto-fail
        (6, 0.5),    # last acceptable day
    ],
    # Score for any lag_days > acceptable_max_days or < -1
    "default_timing_score": 0.2,
}

# =============================================================================
# AMOUNT TOLERANCE
# =============================================================================
# Controls how the "amount" sub-score is calculated for the two checks:
#   1. gross_amount - fee_amount  vs  net_settled
#   2. net_settled  vs  credited_amount
#
# Uses PROPORTIONAL tolerance: the allowed gap is a percentage of the
# transaction amount (gross_amount). A minimum flat-rupee floor is also
# applied so tiny transactions aren't unfairly strict.
#
# effective_tolerance = max(flat_floor_rupees, pct * transaction_amount)
#
# AMOUNT_CURVE is a list of (tolerance_pct, score) tuples evaluated in order.
# The first entry whose tolerance_pct exceeds the actual gap ratio wins.
# tolerance_pct is expressed as a decimal (0.01 = 1%, 0.001 = 0.1%).
#
# Example: for a ₹5000 transaction:
#   - tolerance at 0.0001 = ₹0.50   (score 1.0 = exact match)
#   - tolerance at 0.001  = ₹5.00   (score 0.85 = rounding drift)
#   - tolerance at 0.01   = ₹50.00  (score 0.6  = small gap)
#   - anything larger                  (score 0.0  = mismatch)

AMOUNT_TOLERANCE = {
    "flat_floor_rupees": 0.01,
    # List of (tolerance_pct, score) tuples. tolerance_pct is a decimal.
    # Evaluated in order; first entry whose tolerance exceeds the actual
    # gap ratio wins.
    "amount_curve": [
        (0.0001, 1.0),   # 0.01% — essentially exact match
        (0.001, 0.65),   # 0.1%  — rounding drift (not a clean match, but explainable)
        (0.01, 0.6),     # 1%    — small gap
    ],
    # Score for gaps larger than the last curve entry
    "default_amount_score": 0.0,
}

# =============================================================================
# FEE PLAUSIBILITY
# =============================================================================
# Controls an OPTIONAL sanity check on whether the gateway fee percentage
# falls within a reasonable range. This is a separate score — it is NOT
# folded into amount_score or the composite confidence calculation yet.
# It exists for future use or manual review.
#
# fee_pct is the fee as a decimal (e.g., 0.02 = 2%).
# A typical payment gateway charges between 1.5% and 3.0%.

FEE_TOLERANCE = {
    "min_fee_pct": 0.015,   # 1.5%
    "max_fee_pct": 0.03,    # 3.0%
}

# =============================================================================
# COMPOSITE WEIGHTS
# =============================================================================
# How the individual sub-scores are combined into a single confidence score:
#   confidence = amount_weight * amount_score
#             + timing_weight * timing_score
#             + reference_weight * reference_score
#
# All three weights must sum to 1.0.

COMPOSITE_WEIGHTS = {
    "amount": 0.40,
    "timing": 0.30,
    "reference": 0.30,
}

# =============================================================================
# STATUS THRESHOLDS
# =============================================================================
# The confidence score is mapped to a match status label using these thresholds:
#
#   confidence >= MATCHED_THRESHOLD  -->  "MATCHED"
#   confidence >= RESOLVED_THRESHOLD -->  "RESOLVED_WITH_REASONING"
#   confidence <  RESOLVED_THRESHOLD -->  "EXCEPTION"
#
# RESOLVED_WITH_REASONING means "not a clean match, but explainable —
# accepted with reasoning." EXCEPTION means "could not be resolved."

STATUS_THRESHOLDS = {
    "matched": 0.96,
    "resolved": 0.50,
}

# =============================================================================
# REFERENCE SCORE
# =============================================================================
# Trust levels for HOW a match was found — not whether the amounts are correct
# (that's amount_score's job), but whether the key-based join itself is
# trustworthy. Higher scores mean the join path is more reliable.
#
# "unverified_duplicate" deliberately scores well BELOW "orphan" because a
# suspicious repeat (same order_ref appearing twice with non-reconciling
# amounts) is a stronger red flag than simply missing data on one side.

REFERENCE_SCORE = {
    "full_three_way_match": 1.0,       # matched cleanly across ledger+gateway+bank
    "ledger_gateway_only_match": 0.95, # matched but bank leg not yet available
    "verified_partial_split": 0.9,     # duplicate order_ref, amounts verified to reconcile
    "unverified_duplicate": 0.2,       # duplicate order_ref, amounts do NOT verify — suspicious
    "orphan": 0.5,                     # no match found on one side
}

# =============================================================================
# SPECIAL CASE OVERRIDES
# =============================================================================
# Some errors cannot be detected by per-row amount/timing math alone because
# each individual row looks correct on its own. These are structural errors
# found by the special-case detectors (src/matcher/special_cases.py):
#
#   - DUPLICATE_UTR: the same bank transfer reference was credited more than
#     once. Each credit individually reconciles perfectly, so amount scoring
#     sees no problem — only cross-row detection catches it.
#   - REFUND_MISMATCH: the ledger already recorded the order as refunded, but
#     the gateway/bank still show the original settlement credit as if it
#     stands. Again, the settlement math itself is perfect.
#
# When one of these fires, the transaction's status is FORCED to EXCEPTION
# and its confidence is forced down to the value here, regardless of how
# good its computed sub-scores were. The override reason is recorded on the
# row so downstream code can explain WHY.

SPECIAL_CASE_OVERRIDES = {
    # Forced confidence score for rows flagged by a special-case detector.
    # Deliberately far below STATUS_THRESHOLDS["resolved"] (0.50) so the
    # row can never be classified as MATCHED or RESOLVED_WITH_REASONING.
    "duplicate_utr_score": 0.1,
    "refund_mismatch_score": 0.1,
    # Machine-readable reasons written into the override_reason column.
    "duplicate_utr_reason": "DUPLICATE_UTR_DETECTED",
    "refund_mismatch_reason": "REFUND_NOT_REFLECTED",
}
