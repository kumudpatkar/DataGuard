# DataGuard — Automated Data Quality & Reconciliation Platform

**Transforming raw business data into trusted, actionable intelligence.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Framework-Streamlit-FF4B4B)](https://streamlit.io/)
[![Pandas](https://img.shields.io/badge/Data-Pandas-150458)](https://pandas.pydata.org/)
[![Plotly](https://img.shields.io/badge/Visualization-Plotly-3F4F75)](https://plotly.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**Live Application:** https://dataguard-gu6qtnvkwu3ey3nffm5out.streamlit.app/

**GitHub Repository:** https://github.com/kumudpatkar/DataGuard

---

## 1. Overview

DataGuard is an automated data quality, reconciliation and exception management platform built using Python, Pandas and Streamlit.

Businesses frequently maintain financial and operational information across multiple systems. Differences between these systems can result in incorrect reports, financial discrepancies, duplicate transactions and unreliable business decisions.

Traditional reconciliation processes often depend on manual Excel comparisons, making them time-consuming, difficult to scale and challenging to audit.

DataGuard addresses these challenges by providing a centralized platform that:

- Compares records across multiple data sources.
- Identifies missing, duplicate and mismatched records.
- Quantifies financial exposure through Money-at-Risk analysis.
- Detects recurring discrepancy patterns.
- Tracks exceptions through a ticket-based workflow.
- Monitors data quality using configurable validation rules.
- Generates data health scores and operational alerts.
- Provides interactive analytics and reporting dashboards.

The platform is designed to support both demonstration datasets and user-provided business data.

## 2. Business Problem

Consider an e-commerce company that stores order information in its internal system while payment information is maintained by an external payment gateway.

Every day, finance and operations teams need to verify:

- Whether every order has a corresponding payment.
- Whether transaction amounts match.
- Whether duplicate payments exist.
- Whether settlement delays explain apparent differences.
- Which discrepancies create the highest financial risk.
- Whether previously identified issues have been resolved.

Manual reconciliation makes these activities difficult to manage consistently.

**DataGuard automates the comparison process and helps teams move from identifying discrepancies to investigating and resolving them.**

## 3. Key Features

### 3.1 Automated Data Reconciliation

Compare two datasets using configurable matching keys and comparison rules.

Capabilities:

- CSV and Excel file support.
- Column mapping and matching-key selection.
- Data normalization and key cleaning.
- Configurable numerical tolerance.
- Duplicate record identification.
- Missing record detection.
- Field-level mismatch identification.
- Settlement timing difference handling.
- Preservation of blank and duplicate keys for exception analysis.

### 3.2 Money-at-Risk Analysis

Identify discrepancies based on their financial impact and severity.

The risk engine calculates:

**Money-at-Risk = Financial Exposure × Severity Weight**

Examples include:

- Missing transactions.
- Incorrect payment amounts.
- Duplicate payments.
- Settlement timing differences.

This helps prioritize exceptions based on potential business impact rather than treating every discrepancy equally.

### 3.3 Root Cause Detection

Identify recurring patterns behind data discrepancies.

Examples:

- Gateway fee inconsistencies.
- Duplicate transactions caused by retry operations.
- Missing payment records.
- Invalid customer identifiers.
- Recurring order and payment mismatches.

The objective is to help analysts investigate the underlying reasons behind repeated data quality problems.

### 3.4 Exception Management & Audit Tracking

Manage identified discrepancies through a structured ticket workflow.

Capabilities:

- Exception assignment.
- Status updates.
- Comments and investigation notes.
- Automatic ticket closure when an issue is resolved.
- Reopening when a previously resolved issue returns.
- Audit history for tracking changes.

### 3.5 Configurable Data Quality Rules

Validate datasets using configurable business rules.

Capabilities:

- Ten supported rule types.
- YAML-based rule configuration.
- Multiple validation rules.
- Automated rule suggestions.
- Interactive rule builder.
- Data quality issue identification.

Rules are maintained in `config/rules.yaml`.

### 3.6 Data Health Monitoring

Monitor overall dataset reliability using a score between 0 and 100.

The health score uses four components:

| Component | Weight |
|---|---:|
| Record Matching | 60% |
| Completeness | 15% |
| Rule Validation | 15% |
| Uniqueness | 10% |

Health categories:

- 90–100: Healthy
- 75–89: Needs Attention
- Below 75: At Risk

The platform also provides health trends and configurable Telegram or webhook alerts.

### 3.7 Retail Sales Analytics

Explore retail datasets through interactive analytical dashboards.

Capabilities:

- Revenue analysis.
- Product and country-level performance.
- Revenue bridge analysis.
- Sales quality monitoring.
- KPI trust scoring.
- Interactive data exploration.

The included retail sample dataset contains approximately 10,000 records.

### 3.8 Daily Pipeline Automation

Execute reconciliation and quality checks without opening the Streamlit interface.

Example:

```bash
python scripts/run_daily.py --pipeline orders_vs_payments --threshold 80
```

The automation process can:

- Execute configured pipelines.
- Generate reconciliation reports.
- Update exception records.
- Calculate health scores.
- Trigger alerts when scores fall below configured thresholds.

## 4. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application development and processing |
| Pandas | Data cleaning and reconciliation |
| Streamlit | Interactive web application |
| Plotly | Interactive data visualization |
| MySQL | Optional relational data storage |
| SQLite | Workflow and audit storage |
| YAML | Pipeline and quality rule configuration |
| Pytest | Automated testing |
| Git & GitHub | Version control and source management |
| Streamlit Community Cloud | Application deployment |

## 5. Application Modules

| Module | Description |
|---|---|
| Executive Overview | Overall reconciliation and business health |
| Order Reconciliation | Source-to-target record comparison |
| Data Quality | Validation rules and quality monitoring |
| Exceptions | Discrepancy investigation and tracking |
| Health Monitoring | Data health scores and trends |
| Retail Sales Analytics | Retail performance analysis |
| Retail Data Explorer | Dataset exploration |

## 6. Application Architecture

DataGuard follows a modular architecture that separates business logic from the user interface.

```text
              DATA SOURCES
                   |
          CSV / Excel / MySQL
                   |
                   v
          DATA PROCESSING
              Pandas
                   |
                   v
        RECONCILIATION ENGINE
          Matching & Comparison
                   |
          +--------+--------+
          |        |        |
          v        v        v
        Quality  Risk    Root Cause
         Rules   Engine   Detection
          |        |        |
          +--------+--------+
                   |
                   v
          EXCEPTION MANAGEMENT
             SQLite Storage
                   |
                   v
          STREAMLIT DASHBOARD
                   |
          +--------+--------+
          |        |        |
          v        v        v
        Overview Reports Analytics
```

## 7. Project Structure

```text
DataGuard/
│
├── app.py
├── requirements.txt
├── README.md
├── Dockerfile
│
├── core/
│   ├── reconciliation.py
│   ├── quality_rules.py
│   ├── risk.py
│   ├── root_cause.py
│   ├── workflow.py
│   ├── health.py
│   ├── alerts.py
│   ├── retail.py
│   ├── pipeline.py
│   ├── config.py
│   └── utils.py
│
├── views/
│   ├── overview_page.py
│   ├── reconciliation_page.py
│   ├── rules_page.py
│   ├── exceptions_page.py
│   ├── health_page.py
│   └── retail_page.py
│
├── config/
│   ├── pipeline.yaml
│   └── rules.yaml
│
├── scripts/
│   ├── run_daily.py
│   ├── generate_demo_data.py
│   ├── load_to_mysql.py
│   └── refresh_ticket_risk.py
│
├── tests/
│
├── data/
│   ├── examples/
│   ├── sample_retail.csv
│   ├── source_orders.csv
│   └── target_orders.csv
│
└── storage/
```

## 8. Installation & Local Setup

### Prerequisites

- Python 3.10 or newer.
- Git.
- VS Code (recommended).

### Step 1: Clone the repository

```bash
git clone https://github.com/kumudpatkar/DataGuard.git
cd DataGuard
```

### Step 2: Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure environment variables

Copy `.env.example` to `.env` and configure the required values.

Never upload `.env` or database credentials to GitHub.

### Step 5: Run the application

```bash
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## 9. Using Your Own Data

DataGuard supports user-provided datasets.

### Reconciliation

1. Open the Order Reconciliation module.
2. Select the option to upload your own files.
3. Upload the source and target CSV or Excel files.
4. Select the matching-key column.
5. Map the comparison columns.
6. Configure the numerical tolerance.
7. Execute reconciliation.
8. Review matched records and exceptions.

### Custom Quality Rules

Modify:

```text
config/rules.yaml
```

Add or update business validation rules according to the requirements of the dataset.

### Custom Pipelines

Modify:

```text
config/pipeline.yaml
```

Use the existing pipeline configuration as a reference.

## 10. Automated Testing

DataGuard includes automated tests covering:

- Reconciliation logic.
- Duplicate and missing records.
- Data quality rules.
- Financial risk calculations.
- Root cause detection.
- Exception workflow.
- Retail analytics.
- Application page smoke tests.

Run the test suite:

```bash
python -m pytest
```

## 11. Deployment

DataGuard is deployed using Streamlit Community Cloud.

**Live Application:**

https://dataguard-gu6qtnvkwu3ey3nffm5out.streamlit.app/

**Deployment platform:** Streamlit Community Cloud

**Source code:** GitHub

The application is connected to the GitHub repository and can receive updates through the deployment workflow.

## 12. Optional MySQL Integration

MySQL integration is available for loading order datasets into relational tables.

Example:

```bash
python scripts/load_to_mysql.py \
  --file data/source_orders.csv \
  --table source_orders
```

Database credentials should be configured through environment variables.

The main dashboard does not require MySQL for its standard demonstration workflow.

## 13. Docker Support

Build the Docker image:

```bash
docker build -t dataguard .
```

Run the container:

```bash
docker run -p 8501:8501 dataguard
```

Access the application at:

```text
http://localhost:8501
```

## 14. Current Limitations

- Authentication and role-based access control are not currently implemented.
- SQLite is intended for individual or small-team workflows.
- Larger multi-user deployments may require PostgreSQL or MySQL-backed workflow storage.
- Retail sample currency is GBP; INR conversion uses a configurable rate rather than historical exchange rates.
- Datasets are processed in memory, so very large-scale workloads may require database-backed processing.
- External alert delivery requires provider configuration.

## 15. Future Enhancements

Planned improvements include:

- AI-assisted explanations of reconciliation exceptions.
- Intelligent anomaly detection.
- Fuzzy matching for inconsistent transaction identifiers.
- Many-to-one payment reconciliation.
- Role-based access control.
- Multi-user support.
- PostgreSQL-backed workflow storage.
- Advanced financial risk analytics.
- Enhanced automated reporting.

## 16. Author

**Kumud Satyawan Patkar**

Data Analyst | Python | SQL | Excel | Power BI

GitHub: https://github.com/kumudpatkar

LinkedIn: https://linkedin.com/in/kumud-patkar-928180283

Portfolio: https://kumud-portfolio-rho.vercel.app/

---

## Project Links

| Resource | Link |
|---|---|
| Live Demo | https://dataguard-gu6qtnvkwu3ey3nffm5out.streamlit.app/ |
| GitHub Repository | https://github.com/kumudpatkar/DataGuard |

**DataGuard — Making business data more reliable, transparent and actionable.**
