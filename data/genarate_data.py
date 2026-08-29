"""
Synthetic Reconciliation Dataset Generator + Ground Truth
------------------------------------------------------------
Generates three linked datasets (ledger, gateway, bank) AND a private
ground_truth.json answer key in the same run, so they can never drift
out of sync. The matcher should NEVER read ground_truth.json — it's
only for grading your own accuracy afterward.
"""

import pandas as pd
import json
import random
from datetime import date, timedelta

random.seed(42)

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
TOTAL_CLEAN_BASE = 35
FEE_MISMATCH_COUNT = 8
TIMING_LAG_COUNT = 5
PARTIAL_SETTLEMENT_COUNT = 3
DUPLICATE_UTR_COUNT = 2
ROUNDING_DRIFT_COUNT = 3
REFUND_REVERSAL_COUNT = 2
ORPHAN_BANK_COUNT = 1
ORPHAN_LEDGER_COUNT = 1

START_DATE = date(2026, 3, 1)
CUSTOMER_NAMES = [
    "Aarav Sharma", "Priya Nair", "Rohan Gupta", "Sneha Iyer", "Kabir Khan",
    "Ananya Rao", "Vikram Singh", "Meera Joshi", "Arjun Reddy", "Ishita Bose",
    "Dev Patel", "Kavya Menon", "Aditya Verma", "Riya Kapoor", "Nikhil Das",
    "Tanya Malhotra", "Yash Chopra", "Divya Pillai", "Karan Mehta", "Sanya Kaur"
]
PAYMENT_MODES = ["UPI", "Card", "Netbanking"]

ledger_rows = []
gateway_rows = []
bank_rows = []
ground_truth = {}   # order_id / utr -> category record

order_counter = 10001
gateway_counter = 88000
bank_counter = 55000
utr_counter = 556000


def next_order_id():
    global order_counter
    order_counter += 1
    return f"ORD{order_counter}"


def next_gateway_id():
    global gateway_counter
    gateway_counter += 1
    return f"rzp_pay_{gateway_counter}"


def next_bank_id():
    global bank_counter
    bank_counter += 1
    return f"BANKTXN{bank_counter}"


def next_utr():
    global utr_counter
    utr_counter += 1
    return f"UTR{utr_counter}"


def random_order_date():
    offset = random.randint(0, 20)
    return START_DATE + timedelta(days=offset)


def record_truth(order_id, category, utrs=None, notes=""):
    """Store the ground-truth label for one order_id."""
    ground_truth[order_id] = {
        "category": category,
        "utrs": utrs or [],
        "notes": notes
    }


def make_clean_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    settlement_date = order_date + timedelta(days=random.choice([1, 2]))
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": net_settled,
        "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
    })
    record_truth(order_id, "CLEAN_MATCH", [utr], "Standard 2% fee, normal T+1/T+2 lag")


def make_fee_mismatch_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = random.choice([0.015, 0.0236, 0.025, 0.03])
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    settlement_date = order_date + timedelta(days=random.choice([1, 2]))
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": net_settled,
        "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
    })
    record_truth(order_id, "FEE_MISMATCH_EXPLAINABLE", [utr],
                 f"Non-standard fee slab {fee_pct*100}% — should resolve via fee math, not flag as exception")


def make_timing_lag_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    settlement_date = order_date + timedelta(days=random.choice([3, 4]))
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": net_settled,
        "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
    })
    record_truth(order_id, "TIMING_LAG_EXPLAINABLE", [utr],
                 f"Settlement at T+{(settlement_date - order_date).days} — wider than usual window but legitimate")


def make_partial_settlement_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(2000, 6000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)

    split_ratio = random.uniform(0.3, 0.6)
    part1 = round(net_settled * split_ratio, 2)
    part2 = round(net_settled - part1, 2)

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })

    utrs_for_order = []
    for part_amount in [part1, part2]:
        settlement_date = order_date + timedelta(days=random.choice([1, 2]))
        utr = next_utr()
        gw_id = next_gateway_id()
        utrs_for_order.append(utr)
        gateway_rows.append({
            "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
            "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": part_amount,
            "utr": utr, "settlement_date": settlement_date
        })
        bank_rows.append({
            "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": part_amount,
            "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
        })
    record_truth(order_id, "PARTIAL_SETTLEMENT_SPLIT", utrs_for_order,
                 "One order settled across two UTRs — requires one-to-many matching")


def make_duplicate_utr_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    settlement_date = order_date + timedelta(days=1)
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    for _ in range(2):
        bank_rows.append({
            "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": net_settled,
            "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
        })
    record_truth(order_id, "DUPLICATE_UTR_ERROR", [utr],
                 "Same UTR credited twice in bank statement — genuine double-credit error, should NOT auto-resolve")


def make_rounding_drift_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    drift = random.choice([0.01, 0.05, 0.10, 0.25, 0.50]) * random.choice([1, -1])
    credited_amount = round(net_settled + drift, 2)
    settlement_date = order_date + timedelta(days=1)
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": credited_amount,
        "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
    })
    record_truth(order_id, "ROUNDING_DRIFT_EXPLAINABLE", [utr],
                 f"Drift of {drift:+.2f} between net_settled and credited_amount — within tolerance")


def make_refund_reversal_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 5000), 2)
    fee_pct = 0.02
    fee_amount = round(amount * fee_pct, 2)
    net_settled = round(amount - fee_amount, 2)
    settlement_date = order_date + timedelta(days=1)
    utr = next_utr()
    gw_id = next_gateway_id()

    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "refunded"
    })
    gateway_rows.append({
        "gateway_txn_id": gw_id, "order_ref": order_id, "gross_amount": amount,
        "fee_pct": fee_pct, "fee_amount": fee_amount, "net_settled": net_settled,
        "utr": utr, "settlement_date": settlement_date
    })
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": net_settled,
        "value_date": settlement_date, "narration": f"NEFT-RAZORPAY-SETTLEMENT-{utr}"
    })
    record_truth(order_id, "REFUND_NOT_REFLECTED", [utr],
                 "Ledger shows refunded but gateway/bank still show original credit — reversal lag, real exception")


def make_orphan_bank_transaction():
    utr = next_utr()
    settlement_date = random_order_date() + timedelta(days=1)
    amount = round(random.uniform(200, 3000), 2)
    bank_rows.append({
        "bank_txn_id": next_bank_id(), "utr": utr, "credited_amount": amount,
        "value_date": settlement_date, "narration": f"NEFT-UNKNOWN-SOURCE-{utr}"
    })
    record_truth(f"ORPHAN_BANK_{utr}", "ORPHAN_NO_GATEWAY_MATCH", [utr],
                 "Bank credit with no matching gateway UTR at all — genuine unresolved exception")


def make_orphan_ledger_transaction():
    order_id = next_order_id()
    order_date = random_order_date()
    amount = round(random.uniform(200, 3000), 2)
    ledger_rows.append({
        "order_id": order_id, "customer_name": random.choice(CUSTOMER_NAMES),
        "order_amount": amount, "order_date": order_date,
        "payment_mode": random.choice(PAYMENT_MODES), "status": "paid"
    })
    record_truth(order_id, "ORPHAN_NO_LEDGER_MATCH", [],
                 "Order in ledger with no matching gateway transaction — payment likely failed silently")


# ------------------------------------------------------------------
# GENERATE ALL CATEGORIES
# ------------------------------------------------------------------
for _ in range(TOTAL_CLEAN_BASE):
    make_clean_transaction()
for _ in range(FEE_MISMATCH_COUNT):
    make_fee_mismatch_transaction()
for _ in range(TIMING_LAG_COUNT):
    make_timing_lag_transaction()
for _ in range(PARTIAL_SETTLEMENT_COUNT):
    make_partial_settlement_transaction()
for _ in range(DUPLICATE_UTR_COUNT):
    make_duplicate_utr_transaction()
for _ in range(ROUNDING_DRIFT_COUNT):
    make_rounding_drift_transaction()
for _ in range(REFUND_REVERSAL_COUNT):
    make_refund_reversal_transaction()
for _ in range(ORPHAN_BANK_COUNT):
    make_orphan_bank_transaction()
for _ in range(ORPHAN_LEDGER_COUNT):
    make_orphan_ledger_transaction()

# ------------------------------------------------------------------
# SHUFFLE + SAVE (NOTE: shuffling rows does NOT affect ground_truth,
# since it's keyed by order_id/utr, not row position)
# ------------------------------------------------------------------
random.shuffle(ledger_rows)
random.shuffle(gateway_rows)
random.shuffle(bank_rows)

pd.DataFrame(ledger_rows).to_csv("internal_order_ledger.csv", index=False)
pd.DataFrame(gateway_rows).to_csv("gateway_settlement_report.csv", index=False)
pd.DataFrame(bank_rows).to_csv("bank_statement.csv", index=False)

with open("ground_truth.json", "w") as f:
    json.dump({
        "summary": {
            "total_transactions": len(ground_truth),
            "category_counts": pd.Series(
                [v["category"] for v in ground_truth.values()]
            ).value_counts().to_dict()
        },
        "records": ground_truth
    }, f, indent=2, default=str)

print(f"internal_order_ledger.csv      -> {len(ledger_rows)} rows")
print(f"gateway_settlement_report.csv  -> {len(gateway_rows)} rows")
print(f"bank_statement.csv             -> {len(bank_rows)} rows")
print(f"ground_truth.json              -> {len(ground_truth)} labeled records")