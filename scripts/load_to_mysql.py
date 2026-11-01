"""Load a CSV file into MySQL (optional tool, not needed to run the app).

The database login comes from your .env file (DB_HOST, DB_USER, DB_PASSWORD,
DB_NAME), so no password is stored in the code.

Examples (run from the project folder):

    python scripts/load_to_mysql.py --file data/source_orders.csv --table source_orders
    python scripts/load_to_mysql.py --file data/target_orders.csv --table target_orders
    python scripts/load_to_mysql.py --file data/data.csv --table retail_transactions --latin1

Requires:  pip install mysql-connector-python
The table is created automatically if it does not exist (all columns as TEXT
except numbers, which are stored as DOUBLE).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core import config  # noqa: E402  (loads .env)

import os  # noqa: E402

BATCH_SIZE = 5000


def safe_name(name: str) -> str:
    """Only allow letters, numbers and underscores in table and column names."""
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", str(name))
    if not cleaned or cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description="Load a CSV file into a MySQL table.")
    parser.add_argument("--file", required=True, help="CSV file to load")
    parser.add_argument("--table", required=True, help="MySQL table name")
    parser.add_argument("--latin1", action="store_true", help="Read the CSV as Latin-1 text")
    parser.add_argument("--replace", action="store_true", help="Delete existing rows first")
    args = parser.parse_args()

    try:
        import mysql.connector
    except ImportError:
        print("Please install the MySQL driver first:  pip install mysql-connector-python")
        return 2

    password = os.getenv("DB_PASSWORD")
    user = os.getenv("DB_USER")
    if not user or not password:
        print("DB_USER and DB_PASSWORD are not set. Copy .env.example to .env and fill them in.")
        return 2

    path = Path(args.file)
    if not path.is_absolute():
        path = config.BASE_DIR / path
    df = pd.read_csv(path, encoding="latin1" if args.latin1 else "utf-8", low_memory=False)
    df.columns = [safe_name(c) for c in df.columns]
    table = safe_name(args.table)

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"), user=user, password=password,
    )
    cursor = connection.cursor()
    database = safe_name(os.getenv("DB_NAME", "dataguard"))
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
    cursor.execute(f"USE `{database}`")

    column_sql = ", ".join(
        f"`{col}` {'DOUBLE' if pd.api.types.is_numeric_dtype(df[col]) else 'TEXT'}"
        for col in df.columns
    )
    cursor.execute(f"CREATE TABLE IF NOT EXISTS `{table}` ({column_sql})")
    if args.replace:
        cursor.execute(f"DELETE FROM `{table}`")

    placeholders = ", ".join(["%s"] * len(df.columns))
    insert_sql = (f"INSERT INTO `{table}` ({', '.join(f'`{c}`' for c in df.columns)}) "
                  f"VALUES ({placeholders})")

    rows = df.astype(object).where(df.notna(), None).values.tolist()
    for start in range(0, len(rows), BATCH_SIZE):
        cursor.executemany(insert_sql, rows[start:start + BATCH_SIZE])
        connection.commit()
        print(f"Loaded {min(start + BATCH_SIZE, len(rows)):,} / {len(rows):,} rows")

    cursor.close()
    connection.close()
    print(f"Done. {len(rows):,} rows are now in {database}.{table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
