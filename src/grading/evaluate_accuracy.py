"""
Phase 11: Grading Against Ground Truth
=======================================

Loads ground_truth.json and match_report.csv, compares them, and computes
per-category precision/recall. The matcher NEVER reads ground_truth.json —
this script exists only for offline accuracy evaluation.

Ground truth categories and what our pipeline SHOULD produce:

  SHOULD MATCH (our status = MATCHED or RESOLVED_WITH_REASONING):
    CLEAN_MATCH, FEE_MISMATCH_EXPLAINABLE, TIMING_LAG_EXPLAINABLE,
    PARTIAL_SETTLEMENT_SPLIT, ROUNDING_DRIFT_EXPLAINABLE

  SHOULD EXCEPTION (our status = EXCEPTION):
    DUPLICATE_UTR_ERROR, REFUND_NOT_REFLECTED,
    ORPHAN_NO_GATEWAY_MATCH, ORPHAN_NO_LEDGER_MATCH
"""

import json
import sys
from pathlib import Path

import pandas as pd


GROUND_TRUTH_PATH = Path("data/ground_truth/ground_truth.json")
MATCH_REPORT_PATH = Path("output/match_report.csv")

# Ground truth categories that our pipeline should resolve (not flag as exception)
SHOULD_MATCH_CATEGORIES = {
    "CLEAN_MATCH",
    "FEE_MISMATCH_EXPLAINABLE",
    "TIMING_LAG_EXPLAINABLE",
    "PARTIAL_SETTLEMENT_SPLIT",
    "ROUNDING_DRIFT_EXPLAINABLE",
}

# Ground truth categories that our pipeline should flag as exceptions
SHOULD_EXCEPTION_CATEGORIES = {
    "DUPLICATE_UTR_ERROR",
    "REFUND_NOT_REFLECTED",
    "ORPHAN_NO_GATEWAY_MATCH",
    "ORPHAN_NO_LEDGER_MATCH",
}

# Of the "should match" categories, these are ones where an imperfect
# but explainable result (RESOLVED_WITH_REASONING) is just as correct
# as a perfect match. CLEAN_MATCH must still be exactly MATCHED.
EXPLAINABLE_CATEGORIES = {
    "FEE_MISMATCH_EXPLAINABLE",
    "TIMING_LAG_EXPLAINABLE",
    "PARTIAL_SETTLEMENT_SPLIT",
    "ROUNDING_DRIFT_EXPLAINABLE",
}


def load_ground_truth(path: Path) -> dict:
    """Load ground truth JSON. Returns the records dict."""
    with open(path) as f:
        data = json.load(f)
    return data["records"], data["summary"]


def load_match_report(path: Path) -> pd.DataFrame:
    """Load our match report CSV."""
    return pd.read_csv(path)


def build_gt_lookup(gt_records: dict) -> dict:
    """
    Build a mapping from order_id (as it appears in our match report)
    to ground truth category.

    Handles the special case where the orphan bank record has a synthetic
    key in ground truth (ORPHAN_BANK_UTR556062) but appears as BANKTXN55064
    in our report.
    """
    lookup = {}

    # Build a reverse map: UTR → order_id for orphan detection
    utr_to_gt_key = {}
    for gt_key, gt_info in gt_records.items():
        for utr in gt_info.get("utrs", []):
            utr_to_gt_key[utr] = gt_key

    # Also map synthetic orphan keys to their likely report IDs
    # The orphan bank record in ground truth has key ORPHAN_BANK_UTR556062
    # In our report it appears as BANKTXN55064
    orphan_bank_keys = [k for k in gt_records if k.startswith("ORPHAN_BANK_")]

    for gt_key, gt_info in gt_records.items():
        lookup[gt_key] = gt_info["category"]

    # Map synthetic orphan bank keys to BANKTXN* IDs
    # We'll do this by matching during comparison instead
    return lookup, orphan_bank_keys


def evaluate(gt_records: dict, gt_summary: dict, match_report: pd.DataFrame) -> dict:
    """
    Compare ground truth against our match report.

    Returns a dict with:
      - overall accuracy
      - per-category precision/recall
      - misclassified records
    """
    gt_lookup, orphan_bank_keys = build_gt_lookup(gt_records)

    # Map our match_status to a binary: matched or exception
    def is_matched(status):
        s = str(status)
        return "MATCHED" in s or "RESOLVED" in s

    def is_exception(status):
        return "EXCEPTION" in str(status)

    # Build a mapping from report order_id → ground truth category
    report_to_gt = {}
    unmatched_report_ids = []

    for _, row in match_report.iterrows():
        oid = row["order_id"]
        if oid in gt_lookup:
            report_to_gt[oid] = gt_lookup[oid]
        elif oid.startswith("BANKTXN"):
            # Orphan bank record — match to ORPHAN_BANK_* in ground truth
            for orphan_key in orphan_bank_keys:
                if orphan_key not in report_to_gt.values():
                    report_to_gt[oid] = gt_records[orphan_key]["category"]
                    break
            else:
                unmatched_report_ids.append(oid)
        else:
            unmatched_report_ids.append(oid)

    # Per-category metrics
    category_results = {}

    # Build reverse mapping: gt_category → list of report order_ids
    gt_cat_to_report_ids = {}
    for oid, gt_cat in report_to_gt.items():
        gt_cat_to_report_ids.setdefault(gt_cat, []).append(oid)

    # Collect all ground truth categories
    all_categories = set(gt_summary["category_counts"].keys())

    for cat in all_categories:
        # Records in ground truth with this category
        gt_ids = [k for k, v in gt_records.items() if v["category"] == cat]

        # How many of these did we correctly match/exception?
        correct = 0
        incorrect = 0
        details = []

        for oid in gt_ids:
            # Find this oid in our report (direct match or reverse mapping)
            report_rows = match_report[match_report["order_id"] == oid]

            if len(report_rows) == 0:
                # Check reverse mapping (e.g., ORPHAN_BANK_UTR556062 → BANKTXN55064)
                mapped_ids = gt_cat_to_report_ids.get(cat, [])
                if mapped_ids:
                    # Use the first mapped report ID
                    mapped_id = mapped_ids[0]
                    report_rows = match_report[match_report["order_id"] == mapped_id]

            if len(report_rows) == 0:
                details.append({"id": oid, "verdict": "MISSING_FROM_REPORT"})
                incorrect += 1
                continue

            report_status = report_rows.iloc[0]["match_status"]
            status_str = str(report_status)
            is_matched = "MATCHED" in status_str
            is_resolved = "RESOLVED" in status_str
            is_exception = "EXCEPTION" in status_str

            should_match = cat in SHOULD_MATCH_CATEGORIES
            is_explainable = cat in EXPLAINABLE_CATEGORIES

            # Determine if the pipeline's output is correct for this category
            correct_verdict = False
            if should_match:
                if is_matched:
                    correct_verdict = True
                elif is_explainable and is_resolved:
                    # Explainable categories accept RESOLVED_WITH_REASONING
                    correct_verdict = True
            elif not should_match and is_exception:
                correct_verdict = True

            if correct_verdict:
                correct += 1
                details.append({"id": oid, "verdict": "CORRECT_MATCH" if should_match else "CORRECT_EXCEPTION"})
            else:
                incorrect += 1
                if should_match and is_exception:
                    details.append({"id": oid, "verdict": "FALSE_EXCEPTION"})
                elif not should_match and (is_matched or is_resolved):
                    details.append({"id": oid, "verdict": "FALSE_MATCH"})
                else:
                    details.append({"id": oid, "verdict": "WRONG_STATUS"})

        total = len(gt_ids)
        accuracy = correct / total if total > 0 else 0

        category_results[cat] = {
            "ground_truth_count": total,
            "correct": correct,
            "incorrect": incorrect,
            "accuracy": round(accuracy * 100, 2),
            "details": details,
        }

    # Overall metrics
    total_gt = len(gt_records)
    total_correct = sum(r["correct"] for r in category_results.values())
    total_incorrect = sum(r["incorrect"] for r in category_results.values())
    overall_accuracy = total_correct / total_gt if total_gt > 0 else 0

    # Match rate from our report
    total_report = len(match_report)
    matched_count = int(match_report["match_status"].apply(lambda x: "MATCHED" in str(x)).sum())
    exception_count = int(match_report["match_status"].apply(lambda x: "EXCEPTION" in str(x)).sum())

    return {
        "overall_accuracy_pct": round(overall_accuracy * 100, 2),
        "total_ground_truth_records": total_gt,
        "total_correct": total_correct,
        "total_incorrect": total_incorrect,
        "our_match_rate": {
            "total_report_records": total_report,
            "matched": matched_count,
            "exceptions": exception_count,
        },
        "per_category": category_results,
        "unmatched_report_ids": unmatched_report_ids,
    }


def print_report(results: dict) -> None:
    """Print a human-readable accuracy report."""
    print("=" * 70)
    print("GRADING REPORT: Match Report vs Ground Truth")
    print("=" * 70)

    print(f"\nOverall Accuracy: {results['overall_accuracy_pct']}%")
    print(f"  Ground truth records: {results['total_ground_truth_records']}")
    print(f"  Correctly classified: {results['total_correct']}")
    print(f"  Misclassified:        {results['total_incorrect']}")

    mr = results["our_match_rate"]
    print(f"\nOur Match Report:")
    print(f"  Total records: {mr['total_report_records']}")
    print(f"  MATCHED:       {mr['matched']}")
    print(f"  EXCEPTION:     {mr['exceptions']}")

    print(f"\n{'Category':<35} {'GT Count':>10} {'Correct':>10} {'Wrong':>10} {'Accuracy':>10}")
    print("-" * 77)

    for cat in sorted(results["per_category"].keys()):
        r = results["per_category"][cat]
        print(
            f"{cat:<35} {r['ground_truth_count']:>10} "
            f"{r['correct']:>10} {r['incorrect']:>10} "
            f"{r['accuracy']:>9.1f}%"
        )

    # Show misclassified records
    misclassified = []
    for cat, r in results["per_category"].items():
        for d in r["details"]:
            if d["verdict"] not in ("CORRECT_MATCH", "CORRECT_EXCEPTION"):
                misclassified.append({**d, "category": cat})

    if misclassified:
        print(f"\n{'=' * 70}")
        print(f"MISCLASSIFIED RECORDS ({len(misclassified)})")
        print(f"{'=' * 70}")
        for m in misclassified:
            print(f"  {m['id']:<20} GT: {m['category']:<35} Verdict: {m['verdict']}")
    else:
        print(f"\n{'=' * 70}")
        print("ALL RECORDS CORRECTLY CLASSIFIED")
        print(f"{'=' * 70}")


def save_report(results: dict, path: Path) -> None:
    """Save accuracy report as JSON."""
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved to: {path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    print("Loading ground truth...")
    gt_records, gt_summary = load_ground_truth(GROUND_TRUTH_PATH)
    print(f"  {len(gt_records)} records, {len(gt_summary['category_counts'])} categories")

    print("Loading match report...")
    match_report = load_match_report(MATCH_REPORT_PATH)
    print(f"  {len(match_report)} records")

    print("\nEvaluating...")
    results = evaluate(gt_records, gt_summary, match_report)

    print_report(results)
    save_report(results, Path("output/accuracy_report.json"))
