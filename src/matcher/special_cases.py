from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SpecialCaseResult:
    """Tracks which rows have special case flags."""
    duplicate_utrs: list[dict] = field(default_factory=list)
    refund_mismatches: list[str] = field(default_factory=list)
    partial_settlements: list[str] = field(default_factory=list)
    orphan_ledger: list[str] = field(default_factory=list)
    orphan_bank: list[dict] = field(default_factory=list)


def detect_duplicate_utrs(bank: pd.DataFrame) -> list[dict]:
    """
    Detect UTRs that appear more than once in the bank statement.
    Each duplicate UTR is a potential double-credit error.

    Returns:
        List of dicts with keys: utr, count, bank_txn_ids.
    """
    dup_mask = bank["utr"].duplicated(keep=False)
    dups = bank[dup_mask].sort_values("utr")
    results = []
    for utr, group in dups.groupby("utr"):
        results.append({
            "utr": utr,
            "count": len(group),
            "bank_txn_ids": group["bank_txn_id"].tolist(),
        })
    return results


def detect_refund_mismatches(
    ledger: pd.DataFrame, gateway: pd.DataFrame
) -> list[str]:
    """
    Detect orders where ledger status is 'refunded' but gateway still
    shows a settled transaction (i.e., the reversal hasn't been reflected).

    Returns:
        List of order_ids that have refund mismatches.
    """
    refunded = ledger[ledger["status"] == "refunded"]["order_id"].tolist()
    gateway_refs = set(gateway["order_ref"].tolist())
    return [oid for oid in refunded if oid in gateway_refs]


def detect_partial_settlements(gateway: pd.DataFrame) -> list[str]:
    """
    Detect order_refs that have multiple gateway rows — UNVERIFIED candidates.

    This is a raw "candidate splits" detector: it identifies order_refs
    that APPEAR to be partial settlements based on row count alone. It does
    NOT verify whether the split amounts actually sum to the expected total.

    Verification now lives in build_partial_groups() (validators.py), which
    computes a `verified` field per group. Use that for scoring decisions.
    This function's output is useful for reporting and special-case tagging,
    but should not be treated as confirmed-correct.

    Returns:
        List of order_refs with multiple gateway rows (unverified).
    """
    counts = gateway["order_ref"].value_counts()
    return counts[counts > 1].index.tolist()


def detect_orphans(
    ledger_orphans: pd.DataFrame,
    bank_orphans: pd.DataFrame,
) -> SpecialCaseResult:
    """
    Build orphan lists from the join results.

    Args:
        ledger_orphans: Ledger rows with no gateway match.
        bank_orphans: Bank rows with no gateway match.

    Returns:
        SpecialCaseResult with orphan lists populated.
    """
    result = SpecialCaseResult()
    result.orphan_ledger = ledger_orphans["order_id"].tolist() if len(ledger_orphans) > 0 else []
    result.orphan_bank = (
        bank_orphans[["bank_txn_id", "utr"]].to_dict("records")
        if len(bank_orphans) > 0
        else []
    )
    return result


def run_special_cases(
    ledger: pd.DataFrame,
    gateway: pd.DataFrame,
    bank: pd.DataFrame,
    ledger_orphans: pd.DataFrame,
    bank_orphans: pd.DataFrame,
) -> SpecialCaseResult:
    """
    Run all special case detectors and return a unified result.
    """
    result = SpecialCaseResult()

    result.duplicate_utrs = detect_duplicate_utrs(bank)
    result.refund_mismatches = detect_refund_mismatches(ledger, gateway)
    result.partial_settlements = detect_partial_settlements(gateway)

    orphans = detect_orphans(ledger_orphans, bank_orphans)
    result.orphan_ledger = orphans.orphan_ledger
    result.orphan_bank = orphans.orphan_bank

    return result


def print_special_cases(result: SpecialCaseResult) -> None:
    """Pretty-print the special case detection results."""
    print("=== Special Case Detection Results ===\n")

    print(f"Duplicate UTRs: {len(result.duplicate_utrs)}")
    for d in result.duplicate_utrs:
        print(f"  {d['utr']}: {d['count']} bank entries — {d['bank_txn_ids']}")

    print(f"\nRefund Mismatches: {len(result.refund_mismatches)}")
    for oid in result.refund_mismatches:
        print(f"  {oid}")

    print(f"\nPartial Settlements (valid): {len(result.partial_settlements)}")
    for ref in result.partial_settlements:
        print(f"  {ref}")

    print(f"\nOrphan Ledger (no gateway match): {len(result.orphan_ledger)}")
    for oid in result.orphan_ledger:
        print(f"  {oid}")

    print(f"\nOrphan Bank (no gateway match): {len(result.orphan_bank)}")
    for b in result.orphan_bank:
        print(f"  {b['bank_txn_id']} (UTR: {b['utr']})")
