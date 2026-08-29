import sys
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from src.output_gen import run_output_generation

result = run_output_generation(use_llm=False, fallback_ratio=0)

df = pd.read_csv("output/match_report.csv")
print("Status distribution:")
print(df["match_status"].value_counts().to_string())
print()

for oid in ["ORD10056", "ORD10057", "ORD10045", "ORD10049", "ORD10050", "ORD10002"]:
    row = df[df["order_id"] == oid]
    if len(row):
        r = row.iloc[0]
        print(
            f"{oid}: status={r['match_status']}, "
            f"conf={r['confidence_score']}, "
            f"amt={r['amount_score']}, "
            f"time={r['timing_score']}, "
            f"ref={r['reference_score']}"
        )
