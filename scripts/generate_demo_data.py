"""Create realistic demo data for the order-vs-payment reconciliation.

Run from the project folder:
    python scripts/generate_demo_data.py

It writes data/source_orders.csv and data/target_orders.csv.

The target file contains real-world problems on purpose, so every DataGuard
feature has something to find:

* about 5% of orders missing in the payment system (mostly Cash on Delivery)
* a 2.4% gateway fee taken out of some Card payments
* small rounding differences (these are tolerated, not errors)
* settlement delays: order is Completed but the payment is still Pending
* a few genuine status conflicts and wrong customer ids
* duplicate payments (webhook retries), extra payments and blank keys
* the payment system writes order ids as "ORD-10001" instead of "10001"
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

rng = np.random.default_rng(42)
N = 1200

order_ids = np.arange(10001, 10001 + N)
source = pd.DataFrame({
    "order_id": order_ids,
    "customer_id": [f"C{rng.integers(100, 700)}" for _ in range(N)],
    "order_amount": np.round(rng.gamma(2.0, 450, N) + 50, 2),
    "status": rng.choice(["Completed", "Pending", "Cancelled"], N, p=[0.80, 0.12, 0.08]),
    "country": rng.choice(["India", "UAE", "UK", "USA"], N, p=[0.70, 0.10, 0.10, 0.10]),
    "payment_method": rng.choice(["Card", "UPI", "NetBanking", "COD"], N, p=[0.45, 0.30, 0.15, 0.10]),
    "order_date": pd.to_datetime("2026-09-01") + pd.to_timedelta(rng.integers(0, 50, N), unit="D"),
})
source["order_date"] = source["order_date"].dt.strftime("%Y-%m-%d")

# ---------------------------------------------------------------- target
target = source[["order_id", "customer_id", "order_amount", "status"]].copy()
target["order_id"] = target["order_id"].map(lambda x: f"ORD-{x}")

# 1) missing in target: mostly COD
p_missing = np.where(source["payment_method"] == "COD", 0.35, 0.012)
missing = rng.random(N) < p_missing

# 2) 2.4% gateway fee on some completed card payments
fee_rows = (
    (source["payment_method"] == "Card")
    & (source["status"] == "Completed")
    & (rng.random(N) < 0.12)
    & ~missing
)
target.loc[fee_rows, "order_amount"] = np.round(
    source.loc[fee_rows, "order_amount"] * (1 - 0.024), 2
)

# 3) tiny rounding differences (tolerated by the 1.00 tolerance)
rounding_rows = (rng.random(N) < 0.03) & ~missing & ~fee_rows
target.loc[rounding_rows, "order_amount"] = np.round(
    source.loc[rounding_rows, "order_amount"] + rng.uniform(-0.5, 0.5, rounding_rows.sum()), 2
)

# 4) settlement delay: order Completed, payment still Pending
delay_rows = (source["status"] == "Completed") & (rng.random(N) < 0.06) & ~missing & ~fee_rows
target.loc[delay_rows, "status"] = "Pending"

# 5) genuine status conflicts and wrong customers
candidates = np.where(~missing & ~fee_rows & ~delay_rows & (source["status"] == "Completed"))[0]
conflict_idx = rng.choice(candidates, 8, replace=False)
target.loc[conflict_idx, "status"] = "Cancelled"
cust_idx = rng.choice(np.setdiff1d(candidates, conflict_idx), 6, replace=False)
target.loc[cust_idx, "customer_id"] = "C999"

target = target[~missing].copy()

# 6) duplicate payments (webhook retries)
dup_rows = target.sample(12, random_state=7)
target = pd.concat([target, dup_rows], ignore_index=True)

# 7) extra payments with no order
extra = pd.DataFrame({
    "order_id": [f"ORD-{x}" for x in range(20001, 20011)],
    "customer_id": [f"C{x}" for x in range(800, 810)],
    "order_amount": np.round(rng.gamma(2.0, 400, 10) + 50, 2),
    "status": "Completed",
})
target = pd.concat([target, extra], ignore_index=True)

# 8) blank keys in target and a few duplicate orders in source
blank_idx = rng.choice(len(target), 2, replace=False)
target.loc[blank_idx, "order_id"] = ""
source = pd.concat([source, source.sample(3, random_state=3)], ignore_index=True)

# shuffle so the files do not look artificially ordered
source = source.sample(frac=1, random_state=11).reset_index(drop=True)
target = target.sample(frac=1, random_state=12).reset_index(drop=True)

source.to_csv(DATA_DIR / "source_orders.csv", index=False)
target.to_csv(DATA_DIR / "target_orders.csv", index=False)

print(f"source_orders.csv: {len(source):,} rows")
print(f"target_orders.csv: {len(target):,} rows")
