from dataclasses import dataclass
from pathlib import Path

import pandas as pd


EXPECTED_LEDGER_COLS = [
    "order_id", "customer_name", "order_amount",
    "order_date", "payment_mode", "status",
]

EXPECTED_GATEWAY_COLS = [
    "gateway_txn_id", "order_ref", "gross_amount",
    "fee_pct", "fee_amount", "net_settled", "utr",
    "settlement_date",
]

EXPECTED_BANK_COLS = [
    "bank_txn_id", "utr", "credited_amount",
    "value_date", "narration",
]


@dataclass
class ReconciliationData:
    ledger: pd.DataFrame
    gateway: pd.DataFrame
    bank: pd.DataFrame


def _validate_columns(df: pd.DataFrame, expected: list[str], source_name: str) -> None:
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(
            f"{source_name} is missing columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )


def _parse_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_data(
    data_dir: str | Path = "data",
    dataset_source: str = "sample",
) -> ReconciliationData:
    """
    Load and validate the three reconciliation CSVs.

    Args:
        data_dir: Root data directory (default "data").
        dataset_source: "sample" reads from data/raw/, "custom" reads
            from data/custom/.

    Raises:
        FileNotFoundError: If any required CSV is missing.
        ValueError: If required columns are missing from a CSV.
    """
    data_dir = Path(data_dir)
    if dataset_source == "custom":
        subdir = data_dir / "custom"
    else:
        subdir = data_dir / "raw"

    ledger_path = subdir / "internal_order_ledger.csv"
    gateway_path = subdir / "gateway_settlement_report.csv"
    bank_path = subdir / "bank_statement.csv"

    for path in [ledger_path, gateway_path, bank_path]:
        if not path.exists():
            raise FileNotFoundError(f"Expected data file not found: {path}")

    ledger = pd.read_csv(ledger_path)
    gateway = pd.read_csv(gateway_path)
    bank = pd.read_csv(bank_path)

    _validate_columns(ledger, EXPECTED_LEDGER_COLS, "internal_order_ledger")
    _validate_columns(gateway, EXPECTED_GATEWAY_COLS, "gateway_settlement_report")
    _validate_columns(bank, EXPECTED_BANK_COLS, "bank_statement")

    ledger = _parse_dates(ledger, ["order_date"])
    gateway = _parse_dates(gateway, ["settlement_date"])
    bank = _parse_dates(bank, ["value_date"])

    return ReconciliationData(ledger=ledger, gateway=gateway, bank=bank)


if __name__ == "__main__":
    data = load_data("data")

    print("=== Internal Order Ledger ===")
    print(f"Shape: {data.ledger.shape}")
    print(f"Dtypes:\n{data.ledger.dtypes}\n")

    print("=== Gateway Settlement Report ===")
    print(f"Shape: {data.gateway.shape}")
    print(f"Dtypes:\n{data.gateway.dtypes}\n")

    print("=== Bank Statement ===")
    print(f"Shape: {data.bank.shape}")
    print(f"Dtypes:\n{data.bank.dtypes}\n")

    print("All 3 data sources loaded and validated successfully.")
