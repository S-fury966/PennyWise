from dataclasses import dataclass, field

import pandas as pd

from src.matcher.loader import ReconciliationData


@dataclass
class JoinResult:
    """Holds the joined output plus orphan tracking."""
    ledger_gateway_joined: pd.DataFrame
    gateway_bank_joined: pd.DataFrame
    full_joined: pd.DataFrame
    ledger_orphans: pd.DataFrame
    gateway_orphans_from_ledger: pd.DataFrame
    bank_orphans: pd.DataFrame
    gateway_orphans_from_bank: pd.DataFrame
    summary: dict = field(default_factory=dict)


def join_ledger_to_gateway(
    ledger: pd.DataFrame, gateway: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Left-join ledger to gateway on order_id = order_ref.
    One ledger row may match multiple gateway rows (partial settlements).

    Returns:
        (joined_df, ledger_orphans, gateway_unmatched)
            - joined_df: merged ledger+gateway rows
            - ledger_orphans: ledger rows with no gateway match
            - gateway_unmatched: gateway rows not matched to any ledger row
    """
    merged = ledger.merge(
        gateway,
        left_on="order_id",
        right_on="order_ref",
        how="outer",
        indicator=True,
        suffixes=("_ledger", "_gateway"),
    )

    ledger_orphans = merged[merged["_merge"] == "left_only"].copy()
    gateway_unmatched = merged[merged["_merge"] == "right_only"].copy()
    matched = merged[merged["_merge"] == "both"].copy()

    matched.drop(columns=["_merge"], inplace=True)
    ledger_orphans.drop(columns=["_merge"], inplace=True)
    gateway_unmatched.drop(columns=["_merge"], inplace=True)

    return matched, ledger_orphans, gateway_unmatched


def join_gateway_to_bank(
    gateway: pd.DataFrame, bank: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Left-join gateway to bank on utr.
    One gateway UTR may match multiple bank rows (duplicate UTR error case).

    Returns:
        (joined_df, gateway_orphans, bank_orphans)
            - joined_df: merged gateway+bank rows
            - gateway_orphans: gateway rows with no bank match
            - bank_orphans: bank rows with no gateway match
    """
    merged = gateway.merge(
        bank,
        on="utr",
        how="outer",
        indicator=True,
        suffixes=("_gateway", "_bank"),
    )

    gateway_orphans = merged[merged["_merge"] == "left_only"].copy()
    bank_orphans = merged[merged["_merge"] == "right_only"].copy()
    matched = merged[merged["_merge"] == "both"].copy()

    matched.drop(columns=["_merge"], inplace=True)
    gateway_orphans.drop(columns=["_merge"], inplace=True)
    bank_orphans.drop(columns=["_merge"], inplace=True)

    return matched, gateway_orphans, bank_orphans


def build_full_join(
    ledger_gateway_joined: pd.DataFrame, bank: pd.DataFrame
) -> pd.DataFrame:
    """
    Three-way merge: left-join ledger_gateway_joined with bank on utr.

    This brings credited_amount, bank_txn_id, value_date, and narration
    into the ledger+gateway result, enabling the full three-way amount
    check (gross-fee vs net_settled vs credited_amount).

    Duplicate UTRs in bank (the DUPLICATE_UTR_ERROR case) are handled by
    deduplicating bank on utr before the merge — each gateway row gets at
    most one bank row, avoiding artificial row explosion.
    """
    bank_deduped = bank.drop_duplicates(subset="utr", keep="first")
    return ledger_gateway_joined.merge(
        bank_deduped,
        on="utr",
        how="left",
        suffixes=("", "_bank"),
    )


def run_exact_join(data: ReconciliationData) -> JoinResult:
    """Run the full two-stage exact key join."""

    lg_matched, lg_ledger_orphans, lg_gateway_unmatched = join_ledger_to_gateway(
        data.ledger, data.gateway
    )

    # For the gateway→bank join, use the original gateway rows (not the
    # outer-merged subset) so we get full gateway columns back.
    gb_matched, gb_gateway_orphans, gb_bank_orphans = join_gateway_to_bank(
        data.gateway, data.bank
    )

    # Three-way merge: bring bank data into ledger+gateway rows
    full = build_full_join(lg_matched, data.bank)

    summary = {
        "ledger_total": len(data.ledger),
        "gateway_total": len(data.gateway),
        "bank_total": len(data.bank),
        "ledger_gateway_matched_rows": len(lg_matched),
        "full_joined_rows": len(full),
        "full_joined_has_bank": int(full["credited_amount"].notna().sum()),
        "ledger_orphans": len(lg_ledger_orphans),
        "gateway_unmatched_to_ledger": len(lg_gateway_unmatched),
        "gateway_bank_matched_rows": len(gb_matched),
        "gateway_orphans_to_bank": len(gb_gateway_orphans),
        "bank_orphans": len(gb_bank_orphans),
    }

    return JoinResult(
        ledger_gateway_joined=lg_matched,
        gateway_bank_joined=gb_matched,
        full_joined=full,
        ledger_orphans=lg_ledger_orphans,
        gateway_orphans_from_ledger=lg_gateway_unmatched,
        bank_orphans=gb_bank_orphans,
        gateway_orphans_from_bank=gb_gateway_orphans,
        summary=summary,
    )


if __name__ == "__main__":
    from src.matcher.loader import load_data

    data = load_data("data")
    result = run_exact_join(data)

    print("=== Exact Join Summary ===")
    for k, v in result.summary.items():
        print(f"  {k}: {v}")

    print(f"\n=== Ledger Orphans ({len(result.ledger_orphans)}) ===")
    if len(result.ledger_orphans) > 0:
        print(result.ledger_orphans[["order_id", "customer_name", "order_amount", "status"]].to_string(index=False))

    print(f"\n=== Bank Orphans ({len(result.bank_orphans)}) ===")
    if len(result.bank_orphans) > 0:
        print(result.bank_orphans[["bank_txn_id", "utr", "credited_amount", "narration"]].to_string(index=False))

    print(f"\n=== Ledger-Gateway Joined Sample (first 5) ===")
    if len(result.ledger_gateway_joined) > 0:
        print(result.ledger_gateway_joined[["order_id", "order_ref", "order_amount", "gross_amount", "net_settled"]].head().to_string(index=False))
