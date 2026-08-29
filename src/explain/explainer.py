"""
Explanation Layer
=================

Generates human-readable explanation strings for every transaction.

Two generators:
  1. Template-based: pure string formatting, no network dependency, always works.
  2. Groq LLM-based: generates natural-language explanations via Groq API.

The orchestration function tries Groq first, falls back to template on any
failure. Every row gets an explanation — the pipeline never crashes due to
a missing API key or network error.
"""

import os
import random
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Template-based explanation generator (fallback — always available)
# ---------------------------------------------------------------------------

def _fmt_amount(val) -> str:
    """Format a rupee amount for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    return f"Rs.{val:,.2f}"


def _fmt_pct(val) -> str:
    """Format a percentage for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    return f"{val * 100:.2f}%"


def _settlement_lag_days(row) -> int | None:
    """Compute settlement lag in days, or None if dates are missing."""
    od = row.get("order_date")
    sd = row.get("settlement_date")
    if od is None or sd is None:
        return None
    if isinstance(od, float) and pd.isna(od):
        return None
    if isinstance(sd, float) and pd.isna(sd):
        return None
    try:
        return (sd - od).days
    except Exception:
        return None


def generate_template_explanation(row: dict) -> str:
    """
    Generate a specific, non-generic explanation string for a single
    transaction using only the data present in the row dict.

    This function NEVER calls an LLM and NEVER makes network requests.
    It is the trustworthy fallback that must work offline.
    """
    status = str(row.get("match_status", ""))
    is_exception = "EXCEPTION" in status
    is_resolved = "RESOLVED" in status
    is_matched = "MATCHED" in status and not is_resolved and not is_exception

    order_id = row.get("order_id", "unknown")

    # --- Special-case overrides take priority over all score-based wording ---
    # These rows may have perfect sub-scores; the override reason explains
    # the structural error that per-row math cannot see.
    override_reason = row.get("override_reason")
    if override_reason is not None and not (isinstance(override_reason, float) and pd.isna(override_reason)):
        if override_reason == "DUPLICATE_UTR_DETECTED":
            utrs = []
            single = row.get("utr")
            if single is not None and not (isinstance(single, float) and pd.isna(single)):
                utrs.append(single)
            lst = row.get("utrs")
            if isinstance(lst, list):
                utrs.extend(u for u in lst if u not in utrs)
            utrs_str = ", ".join(str(u) for u in utrs) if utrs else "N/A"
            return (
                f"Order {_order_label(order_id)} was flagged because its UTR "
                f"({utrs_str}) appears MORE THAN ONCE in the bank statement. "
                f"The individual amounts looked correct, but crediting the same "
                f"bank transfer reference twice suggests a possible double credit "
                f"— held for manual review rather than auto-accepted."
            )
        if override_reason == "REFUND_NOT_REFLECTED":
            return (
                f"Order {_order_label(order_id)} shows as REFUNDED in the internal "
                f"ledger, but the gateway and bank statement still show the original "
                f"settlement credit as if it stands normally. The settlement math "
                f"is correct — it's the refund that hasn't been reflected across all "
                f"systems yet. Flagged so the reversal can be traced manually."
            )

    amount_score = row.get("amount_score", 0)
    timing_score = row.get("timing_score", 0)
    reference_score = row.get("reference_score", 0)
    confidence = row.get("confidence_score", 0)

    order_amount = row.get("order_amount")
    gross = row.get("gross_amount")
    fee = row.get("fee_amount")
    fee_pct = row.get("fee_pct")
    net = row.get("net_settled")
    credited = row.get("credited_amount")
    lag_days = _settlement_lag_days(row)

    is_partial = isinstance(row.get("gateway_txn_ids"), list) and len(row.get("gateway_txn_ids", [])) > 1
    is_orphan_ledger = row.get("status") != "unknown" and pd.isna(row.get("order_ref")) and not is_partial
    is_orphan_bank = row.get("status") == "unknown"
    is_refund = row.get("status") == "refunded"

    # --- EXCEPTION paths ---
    if is_exception:
        if is_orphan_bank:
            return (
                f"Bank credit of {_fmt_amount(credited)} found with no matching "
                f"gateway transaction (UTR: {row.get('utr', 'N/A')}). The funds "
                f"arrived but the source is unknown — flagged for manual review."
            )
        if is_orphan_ledger:
            return (
                f"Order {_order_label(order_id)} for {_fmt_amount(order_amount)} "
                f"has no matching gateway transaction. The payment may have failed "
                f"silently or was never recorded by the gateway."
            )
        if is_partial and reference_score < 0.5:
            return (
                f"Order {_order_label(order_id)} appears multiple times in the "
                f"gateway file, but the settled amounts do not sum to the expected "
                f"total of {_fmt_amount(gross)} minus fees — treated as a possible "
                f"billing error, not a valid split."
            )
        # Generic fallback for other exceptions
        return (
            f"Order {_order_label(order_id)} could not be reconciled "
            f"(confidence: {confidence:.0%}). Amount score: {amount_score:.2f}, "
            f"timing score: {timing_score:.2f}, reference score: {reference_score:.2f}. "
            f"Flagged for manual review."
        )

    # --- RESOLVED_WITH_REASONING paths ---
    if is_resolved:
        reasons = []
        if timing_score < 0.85 and lag_days is not None:
            reasons.append(
                f"settled at T+{lag_days} (beyond the usual T+1/T+2 window but "
                f"still within acceptable range)"
            )
        if amount_score < 0.95:
            if is_partial:
                reasons.append(
                    f"split across {len(row.get('gateway_txn_ids', []))} gateway "
                    f"transactions that sum to the expected net"
                )
            elif not pd.isna(gross) and not pd.isna(fee) and not pd.isna(net):
                expected_net = gross - fee
                diff = abs(expected_net - net)
                reasons.append(
                    f"amounts reconcile within Rs.{diff:.2f} tolerance "
                    f"(gross {_fmt_amount(gross)} - fee {_fmt_amount(fee)} = "
                    f"{_fmt_amount(expected_net)}, net settled {_fmt_amount(net)})"
                )
        if not reasons:
            reasons.append(f"all checks passed with minor variations")

        return (
            f"Order {_order_label(order_id)} resolved with reasoning: "
            f"{'; '.join(reasons)}. Confidence: {confidence:.0%}."
        )

    # --- MATCHED paths ---
    if is_matched:
        # Partial settlement
        if is_partial:
            n_parts = len(row.get("gateway_txn_ids", []))
            utrs = row.get("utrs", [])
            parts_str = ", ".join(utrs) if utrs else f"{n_parts} parts"
            return (
                f"Order {_order_label(order_id)} for {_fmt_amount(order_amount)} "
                f"was settled across {n_parts} partial payments (UTRs: {parts_str}). "
                f"Split amounts verified to reconcile to the expected total."
            )

        # Standard clean match
        parts = []
        if not pd.isna(gross) and not pd.isna(fee) and not pd.isna(net):
            parts.append(
                f"amounts reconcile exactly (gross {_fmt_amount(gross)} - "
                f"fee {_fmt_amount(fee)} = {_fmt_amount(net)}, confirmed by "
                f"bank credit of {_fmt_amount(credited)})"
            )
        if lag_days is not None:
            if lag_days <= 2:
                parts.append(f"settled at T+{lag_days} (normal window)")
            else:
                parts.append(f"settled at T+{lag_days}")

        if parts:
            return (
                f"Order {_order_label(order_id)} matched cleanly: "
                f"{'; '.join(parts)}."
            )
        return (
            f"Order {_order_label(order_id)} matched with high confidence "
            f"({confidence:.0%})."
        )

    return f"Order {_order_label(order_id)}: status {status}."


def _order_label(order_id: str) -> str:
    """Return a clean label for an order ID."""
    if order_id and order_id.startswith("BANKTXN"):
        return f"bank transaction {order_id}"
    return order_id


# ---------------------------------------------------------------------------
# Groq-based explanation generator (primary when API key is available)
# ---------------------------------------------------------------------------

def generate_llm_explanation(row: dict) -> str | None:
    """
    Generate an explanation using the Groq LLM API.

    Returns None if:
      - GROQ_API_KEY is not set
      - Any API error occurs (timeout, auth, rate limit, etc.)
      - Response is empty
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Build a data-only prompt — no speculation allowed
    data_fields = {}
    for key in [
        "order_id", "order_amount", "status", "gross_amount", "fee_pct",
        "fee_amount", "net_settled", "credited_amount", "order_date",
        "settlement_date", "amount_score", "timing_score", "reference_score",
        "confidence_score", "match_status",
    ]:
        val = row.get(key)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            data_fields[key] = str(val) if not isinstance(val, (int, float)) else val

    # Override reason is the most important field when present — it explains
    # a structural error that the numeric scores alone cannot convey.
    override_reason = row.get("override_reason")
    if override_reason is not None and not (isinstance(override_reason, float) and pd.isna(override_reason)):
        data_fields["override_reason"] = str(override_reason)

    # Add partial settlement info if present
    gw_ids = row.get("gateway_txn_ids")
    if isinstance(gw_ids, list) and len(gw_ids) > 0:
        data_fields["gateway_txn_ids"] = gw_ids
    utrs = row.get("utrs")
    if isinstance(utrs, list) and len(utrs) > 0:
        data_fields["utr_list"] = utrs

    status_str = str(data_fields.get("match_status", "unknown"))
    data_str = "\n".join(f"  {k}: {v}" for k, v in data_fields.items())

    prompt = f"""You are a financial reconciliation assistant. Write ONE clear,
concise sentence explaining the reconciliation outcome for this transaction.
Use plain language — no finance jargon. State ONLY facts present in the data
below. Do not invent numbers or speculate beyond what the data shows.

If match_status is RESOLVED_WITH_REASONING and override_reason is NOT present:
this means the transaction was accepted despite a minor imperfection.
Look at amount_score and timing_score to determine why: if timing_score is
below 0.85, mention the settlement was slightly delayed beyond the normal
window; if amount_score is below 0.95, mention a small reconciliation gap
between the expected and credited amount, referencing the actual numbers
in the data. Do NOT mention override_reason at all if it is absent from
the data — do not comment on its absence.

If override_reason is DUPLICATE_UTR_DETECTED: state that although the amounts
looked correct, the SAME bank transfer reference (UTR) was credited more than
once in the bank statement, so this may be a double credit needing manual
review. Do NOT say the amounts reconcile.
If override_reason is REFUND_NOT_REFLECTED: state that the internal ledger
shows the order as refunded, but the gateway/bank still show the original
settlement credit as if it happened normally, so the refund has not yet been
reflected across all systems. Do NOT say the amounts reconcile.

Transaction data:
{data_str}

Match status: {status_str}

Explanation:"""

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
            timeout=5,
        )
        text = response.choices[0].message.content.strip()
        return text if text else None
    except Exception as e:
        print(f"  [LLM WARNING] Groq failed for {row.get('order_id', '?')}: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Orchestration — tries LLM, falls back to template
# ---------------------------------------------------------------------------

def generate_explanation(row: dict, use_llm: bool = True) -> dict:
    """
    Generate an explanation for a single transaction row.

    Args:
        row: dict of transaction data from the scored DataFrame.
        use_llm: If True, try Groq first. If False, skip to template.

    Returns:
        dict with keys:
          - "explanation": str — the explanation text
          - "explanation_source": "groq" | "template"
    """
    if use_llm:
        llm_text = generate_llm_explanation(row)
        if llm_text:
            return {"explanation": llm_text, "explanation_source": "groq"}

    template_text = generate_template_explanation(row)
    return {"explanation": template_text, "explanation_source": "template"}


# ---------------------------------------------------------------------------
# Batch runner — applies explanations to entire scored DataFrame
# ---------------------------------------------------------------------------

def run_explanations(scored_df: pd.DataFrame, use_llm: bool = True, fallback_ratio: float = 0.1) -> pd.DataFrame:
    """
    Add explanation columns to the scored DataFrame.

    Does NOT modify the pipeline's matching/scoring logic — this is a
    separate post-processing step, keeping matcher and explain decoupled.

    Args:
        scored_df: DataFrame from src/matcher/pipeline.py's output.
        use_llm: If True, try Groq for each row. If False, use templates only.
        fallback_ratio: Fraction of rows to randomly assign to template even
            when use_llm=True. Gives the output a realistic mix of sources.
            Set to 0.0 for all-LLM, 1.0 for all-template.

    Returns:
        DataFrame with two new columns: "explanation" and "explanation_source".
    """
    n = len(scored_df)
    # Pre-compute which rows get forced template fallback
    if use_llm and fallback_ratio > 0:
        n_fallback = max(1, int(n * fallback_ratio))
        fallback_indices = set(random.sample(range(n), n_fallback))
    else:
        fallback_indices = set()

    llm_count = 0
    template_count = 0

    results = []
    for i, row in scored_df.iterrows():
        if use_llm and i not in fallback_indices:
            result = generate_explanation(row.to_dict(), use_llm=True)
            if result["explanation_source"] == "groq":
                llm_count += 1
            else:
                template_count += 1
        else:
            result = generate_explanation(row.to_dict(), use_llm=False)
            template_count += 1
        results.append(result)

    result_df = pd.DataFrame(results, index=scored_df.index)

    print(f"\n  Explanation summary: {llm_count} LLM, {template_count} template, {n} total")
    return pd.concat([scored_df, result_df], axis=1)
