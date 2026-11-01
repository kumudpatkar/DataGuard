"""Central settings for DataGuard.

Everything that can change between machines (paths, secrets, currency)
lives here, so the rest of the code never hard-codes it.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional; the app still runs without it
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
REPORTS_DIR = BASE_DIR / "reports"
STORAGE_DIR = BASE_DIR / "storage"

STORAGE_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("DATAGUARD_DB", str(STORAGE_DIR / "dataguard.db")))

# Retail data: the full file is used if you put it at data/data.csv,
# otherwise the small sample that ships with the project is used.
RETAIL_FULL_FILE = DATA_DIR / "data.csv"
RETAIL_SAMPLE_FILE = DATA_DIR / "sample_retail.csv"

PIPELINE_CONFIG = CONFIG_DIR / "pipeline.yaml"
RULES_CONFIG = CONFIG_DIR / "rules.yaml"

# Display currency. The retail data is in GBP; INR is a presentation conversion.
DISPLAY_CURRENCY = os.getenv("DISPLAY_CURRENCY", "GBP").upper()
GBP_TO_INR = float(os.getenv("GBP_TO_INR", "127.14"))

# Alerts (all optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

# A health score below this level triggers an alert
DEFAULT_HEALTH_ALERT_THRESHOLD = 80
