from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.matcher.loader import load_data
from src.matcher.exact_join import run_exact_join
from src.matcher.validators import build_partial_groups
from src.matcher.special_cases import run_special_cases, SpecialCaseResult
from src.matcher.scoring import run_scoring
from src.matcher.overrides import apply_special_case_overrides


@dataclass
class PipelineResult:
    """Full output of the reconciliation pipeline."""
    scores: pd.DataFrame
    special_cases: SpecialCaseResult
    partial_groups: dict
    join_summary: dict


def run_pipeline(
    data_dir: str | Path = "data",
    dataset_source: str = "sample",
) -> PipelineResult:
    """
    Run the full reconciliation pipeline end-to-end.

    Steps:
        1. Load data (3 CSVs -> DataFrames)
        2. Exact key join (ledger<->gateway<->bank)
        3. Build partial settlement groups
        4. Detect special cases (duplicates, refunds, orphans)
        5. Score all transactions
        6. Apply special-case overrides (duplicate UTR, refund mismatch) --
           forced EXCEPTION for errors that per-row math cannot see

    Args:
        data_dir: Root data directory (default "data").
        dataset_source: "sample" reads from data/raw/, "custom" reads
            from data/custom/.

    Returns:
        PipelineResult with scored DataFrame and metadata.
    """
    # Step 1: Load
    data = load_data(data_dir, dataset_source=dataset_source)

    # Step 2: Join
    join_result = run_exact_join(data)

    # Step 3: Partial groups
    partial_groups = build_partial_groups(data.gateway)

    # Step 4: Special cases
    special_cases = run_special_cases(
        ledger=data.ledger,
        gateway=data.gateway,
        bank=data.bank,
        ledger_orphans=join_result.ledger_orphans,
        bank_orphans=join_result.bank_orphans,
    )

    # Step 5: Score — use full_joined so amount_score() sees credited_amount
    scores = run_scoring(
        lg_joined=join_result.full_joined,
        ledger_orphans=join_result.ledger_orphans,
        bank_orphans=join_result.bank_orphans,
        partial_groups=partial_groups,
    )

    # Step 6: Special-case overrides — duplicate UTRs and refund mismatches
    # look perfect to per-row math; force their status here, BEFORE the
    # explanation layer and output generation see the data.
    scores = apply_special_case_overrides(scores, special_cases)

    return PipelineResult(
        scores=scores,
        special_cases=special_cases,
        partial_groups=partial_groups,
        join_summary=join_result.summary,
    )


if __name__ == "__main__":
    result = run_pipeline("data")

    print("=== Pipeline Complete ===\n")
    print(f"Total transactions scored: {len(result.scores)}")
    print(f"Match status distribution:")
    print(result.scores["match_status"].value_counts().to_string())

    print(f"\nJoin summary:")
    for k, v in result.join_summary.items():
        print(f"  {k}: {v}")

    print(f"\nSpecial cases detected:")
    sc = result.special_cases
    print(f"  Duplicate UTRs: {len(sc.duplicate_utrs)}")
    print(f"  Refund mismatches: {len(sc.refund_mismatches)}")
    print(f"  Partial settlements: {len(sc.partial_settlements)}")
    print(f"  Ledger orphans: {len(sc.orphan_ledger)}")
    print(f"  Bank orphans: {len(sc.orphan_bank)}")
