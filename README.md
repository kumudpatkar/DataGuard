# DataGuard

**A data trust layer.** DataGuard finds differences between two systems, explains *why* they
happen, shows *how much money* they put at risk, and tracks every one until it is fixed.

## The problem it solves

An online business keeps orders in its own system and payments in a gateway such as Razorpay,
PayU or the bank. Every day someone in finance compares the two in Excel. It is slow, and the
real pain is not finding mismatches but what comes after:

* There are thousands of them. Which ones matter first?
* Many have the same cause. Why do they keep happening?
* Nobody owns them, so they are found again next week.
* Small rounding differences and normal settlement delays create noise that hides real errors.

DataGuard does this work automatically.

## What is inside

| Feature | What it does |
|---|---|
| **Fast reconciliation** | One pandas merge, so 200,000 rows take about 2 seconds. Cleans keys (`ORD-1005` = `1005`), ignores rounding within a tolerance, treats settlement delays as timing differences, and never silently drops duplicates or blank keys. |
| **Money-at-Risk** | Every exception gets a money value (exposure x severity), so the worst ones come first. |
| **Root-cause detector** | Finds patterns: a fixed 2.4% gateway fee, "35% of COD orders never reach payments", a placeholder customer id, duplicate payments from retries. |
| **Exception tickets** | Assign, comment, change status. Tickets close automatically when the data is fixed and re-open if the problem returns. Every change is in the audit log. |
| **Quality rules** | 10 rule types, rules stored in `config/rules.yaml`, run many at once, automatic rule suggestions, and a point-and-click rule builder. |
| **Health score and alerts** | One 0 to 100 score per run, a trend chart, and Telegram or webhook alerts when it drops. |
| **Any two files** | Upload CSV or Excel, map the columns, and compare. No code needed. |
| **Retail analytics** | A revenue bridge that adds up exactly, products and countries without fees or postage mixed in, and a KPI trust score. |
| **Daily automation** | `scripts/run_daily.py` runs everything without the app and exits with a code your scheduler can use. |

## Quick start

You need Python 3.10 or newer.

**Windows:** double-click `setup.bat` once, then `run.bat`.

**macOS / Linux:** `./setup.sh` once, then `./run.sh`.

**Or by hand:**

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On the **Overview** page, press **Run the demo now** to see it working on realistic data.

### Open in VS Code

Open the `DataGuard` folder (or double-click `DataGuard.code-workspace`). Press **F5** and choose
*DataGuard: run the app*. Run tests with the Testing panel or `Ctrl+Shift+P` > *Tasks: Run Test Task*.

## Using your own data

* **Two files to compare:** open **Reconciliation**, choose *Upload my own files*, pick the key
  column, the columns to compare, and the tolerance.
* **A permanent pipeline:** add an entry to `config/pipeline.yaml`. Use the existing one as a template.
* **Your full retail file:** put it at `data/data.csv` and restart. Without it the 10,000-row
  sample `data/sample_retail.csv` is used.
* **Your own rules:** add a rule set to `config/rules.yaml`, or build rules in the app and
  download them as YAML.

## Project structure

```
DataGuard/
├── app.py                  Streamlit entry point (sidebar and page choice only)
├── core/                   All the logic. No Streamlit code here, so it is easy to test.
│   ├── reconciliation.py   The comparison engine
│   ├── risk.py             Money-at-Risk scoring
│   ├── root_cause.py       Pattern detector
│   ├── quality_rules.py    Rules engine, rule suggestions, YAML loading
│   ├── workflow.py         Tickets, comments, run history, audit log (SQLite)
│   ├── health.py           Health score
│   ├── alerts.py           Telegram and webhook alerts
│   ├── retail.py           Retail cleaning, revenue bridge, trust score
│   ├── pipeline.py         Runs everything in one call (used by app and script)
│   └── config.py           Paths and settings from .env
├── views/                  One file per page of the app
├── config/                 pipeline.yaml and rules.yaml
├── scripts/                run_daily.py, generate_demo_data.py, load_to_mysql.py
├── tests/                  Automated tests
├── data/                   Demo and sample data
└── storage/                SQLite database is created here (not committed)
```

## How the main ideas work

**Status of a record**

| Status | Meaning |
|---|---|
| Matched | Same on both sides, including differences inside the tolerance |
| Timing Difference | Matches a timing rule, for example *Completed* in orders but *Pending* in payments |
| Mismatch | A real difference in an amount, status or other field |
| Missing in Target / Source | The record exists on one side only |
| Duplicate in Source / Target | The same key appears more than once |
| Missing Key | A record has no key, so it cannot be matched |

**Money-at-Risk** = exposure x severity.
Exposure is the money affected: the full amount for a missing record, the gap for an amount
mismatch, the extra copies for a duplicate. Severity runs from 1.0 (missing payment) down to
0.2 (timing delay). Weights are in `core/risk.py`.

**Health score** = Matching 60% + Completeness 15% + Rules 15% + Uniqueness 10%.
Matching is strict on purpose: a timing delay counts as half a match, and every 1% of records
with an exception costs 3 points of the Matching part (99% match = 97, 95% = 85, 90% = 70,
80% = 40). 90 or more is Healthy, 75 to 90 Needs attention, below 75 At risk.

**KPI trust score** (retail) = the share of sales value that has an identified customer and
passes basic checks. It tells you how far customer-level numbers can be trusted.

## Daily automation

```bash
python scripts/run_daily.py --pipeline orders_vs_payments --threshold 80
```

Reconciles, saves the run and tickets, writes `reports/<pipeline>_<date>.csv`, and sends an alert
if the score is below the threshold. The exit code is 1 when the score is below the threshold.

* **Windows Task Scheduler:** run `.venv\Scripts\python.exe scripts\run_daily.py`, start in the project folder.
* **cron:** `0 8 * * *  cd /path/to/DataGuard && .venv/bin/python scripts/run_daily.py`

## Alerts and secrets

Copy `.env.example` to `.env` and fill in only what you need. **Never commit `.env`**; it is
already in `.gitignore`. No password is stored in the code.

## Tests

```bash
python -m pytest
```

The suite covers the reconciliation edge cases, risk maths, root-cause detection, the rules
engine, the ticket workflow, the retail logic, and opens every page of the app.

## Optional: MySQL

```bash
python scripts/load_to_mysql.py --file data/source_orders.csv --table source_orders
```

The login comes from `.env`. The app itself does not need MySQL.

## Docker

```bash
docker build -t dataguard .
docker run -p 8501:8501 dataguard
```

## Known limits

* **No login.** The "Working as" name only labels audit entries. For shared company use, put the
  app behind your single sign-on or a reverse proxy with authentication.
* **SQLite** suits one person or a small team. For many simultaneous users, move the workflow
  tables to PostgreSQL or MySQL.
* The retail sample is in GBP. INR is a display conversion at a rate you set, not a historical rate.
* The whole of each file is held in memory. Millions of rows need a database-backed approach.

## Ideas for the next version

AI-written explanations for each exception, many-to-one matching (one payment settling several
orders), fuzzy key matching, role-based permissions, and a PostgreSQL backend.
