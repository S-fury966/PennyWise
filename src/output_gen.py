"""
Phase 10: Output Generation
============================

Produces the two final output files from a full pipeline + explanation run:
  - output/match_report.csv
  - output/exception_summary.json

Default: use_llm=True with ~10% random template fallback for versatile output.
"""

import json
import sys
from pathlib import Path

import pandas as pd

from src.matcher.pipeline import run_pipeline
from src.explain.explainer import run_explanations
from src.exceptions.categorizer import categorize_exceptions
from src.matcher.loader import load_data


OUTPUT_DIR = Path("output")


def generate_match_report(scores: pd.DataFrame, output_path: Path) -> None:
    """Write match_report.csv with per-transaction results."""
    columns = [
        "order_id", "match_status", "confidence_score",
        "amount_score", "timing_score", "reference_score",
        "override_reason", "explanation", "explanation_source",
    ]
    report = scores[columns].copy()
    report["match_status"] = report["match_status"].apply(
        lambda x: x.value if hasattr(x, "value") else str(x)
    )
    report.to_csv(output_path, index=False)
    print(f"  Written: {output_path} ({len(report)} rows)")


def generate_exception_summary(
    scores: pd.DataFrame,
    categorization,
    output_path: Path,
) -> None:
    """Write exception_summary.json with aggregate stats."""
    total = len(scores)

    status_col = scores["match_status"].apply(
        lambda x: x.value if hasattr(x, "value") else str(x)
    )

    matched = int((status_col == "MATCHED").sum())
    resolved = int((status_col == "RESOLVED_WITH_REASONING").sum())
    exceptions = int((status_col == "EXCEPTION").sum())
    match_rate = round(matched / total * 100, 2) if total > 0 else 0

    summary = {
        "total_records": total,
        "matched_count": matched,
        "resolved_with_reasoning_count": resolved,
        "unresolved_exception_count": exceptions,
        "match_rate_pct": match_rate,
        "average_confidence_score": round(float(scores["confidence_score"].mean()), 4) if total > 0 else 0,
        "exception_breakdown": categorization.summary.get("exception_breakdown", {}),
    }

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Written: {output_path}")


def run_output_generation(
    use_llm: bool = True,
    fallback_ratio: float = 0.1,
    dataset_source: str = "sample",
) -> dict:
    """
    Run the full pipeline and generate output files.

    Args:
        use_llm: Generate explanations via Groq LLM.
        fallback_ratio: Fraction of rows assigned template explanations.
        dataset_source: "sample" reads from data/raw/, "custom" from data/custom/.

    Returns:
        Run summary dict with aggregate stats, per-order exception
        categories (for filtering), explanation source counts, and timing.
    """
    import time

    start_time = time.time()
    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"Running pipeline (dataset_source={dataset_source})...")
    pipeline_result = run_pipeline("data", dataset_source=dataset_source)

    print("Running explanations...")
    scores_with_explanations = run_explanations(
        pipeline_result.scores, use_llm=use_llm, fallback_ratio=fallback_ratio
    )

    print("Categorizing exceptions...")
    data = load_data("data", dataset_source=dataset_source)
    categorization = categorize_exceptions(
        scores=scores_with_explanations,
        special_cases=pipeline_result.special_cases,
        partial_groups=pipeline_result.partial_groups,
        ledger=data.ledger,
        gateway=data.gateway,
    )

    print("Generating outputs...")
    generate_match_report(scores_with_explanations, OUTPUT_DIR / "match_report.csv")
    generate_exception_summary(
        scores_with_explanations, categorization, OUTPUT_DIR / "exception_summary.json"
    )

    # Build run summary for API consumers
    status_counts = scores_with_explanations["match_status"].apply(
        lambda x: x.value if hasattr(x, "value") else str(x)
    ).value_counts()

    categories = {
        oid: info["reason_code"]
        for oid, info in categorization.exception_categories.items()
    }

    run_summary = {
        "total_records": len(scores_with_explanations),
        "matched_count": int(status_counts.get("MATCHED", 0)),
        "resolved_with_reasoning_count": int(status_counts.get("RESOLVED_WITH_REASONING", 0)),
        "unresolved_exception_count": int(status_counts.get("EXCEPTION", 0)),
        "match_rate_pct": round(int(status_counts.get("MATCHED", 0)) / max(len(scores_with_explanations), 1) * 100, 2),
        "average_confidence_score": round(float(scores_with_explanations["confidence_score"].mean()), 4),
        "explanation_sources": scores_with_explanations["explanation_source"].value_counts().to_dict(),
        "exception_breakdown": categorization.summary.get("exception_breakdown", {}),
        "categories_by_order_id": categories,
        "duration_seconds": round(time.time() - start_time, 2),
        "use_llm": use_llm,
        "fallback_ratio": fallback_ratio,
        "dataset_source": dataset_source,
    }

    # Print summary
    print("\n=== Output Summary ===")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    source_counts = scores_with_explanations["explanation_source"].value_counts()
    print(f"\n  Explanation sources:")
    for source, count in source_counts.items():
        print(f"    {source}: {count}")

    return run_summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run_output_generation(use_llm=True, fallback_ratio=0.1, dataset_source="sample")
