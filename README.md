# DataGuard — Data Reconciliation & Quality Intelligence Platform

**A data trust layer that identifies mismatches, detects data quality issues, measures financial risk, and helps teams monitor data reliability.**

[![Python](https://img.shields.io/badge/Python-3.x-blue)](https://www.python.org/)
[![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-150458)](https://pandas.pydata.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B)](https://streamlit.io/)
[![MySQL](https://img.shields.io/badge/Database-MySQL-4479A1)](https://www.mysql.com/)

**Live Demo:** https://dataguard-gu6qtnvkwu3ey3nffm5out.streamlit.app/

**GitHub Repository:** https://github.com/kumudpatkar/DataGuard

---

## Overview

DataGuard is a data reconciliation and quality monitoring platform designed to help businesses identify inconsistencies between operational systems and payment records.

For example, an e-commerce business may store orders in its internal database while payment transactions are maintained by an external payment gateway.

DataGuard compares these records, identifies mismatches, detects duplicate entries, calculates financial risk, and provides a dashboard to monitor data reliability.

## Business Problem

Businesses often maintain data across multiple systems. Differences between these systems can lead to:

- Missing or unmatched transactions
- Duplicate records
- Incorrect payment amounts
- Customer and order status mismatches
- Financial reconciliation errors
- Poor data quality and reporting accuracy

DataGuard helps identify and monitor these issues through a centralized dashboard.

## Key Features

### 1. Order Reconciliation
- Compare source and target datasets.
- Identify matched and unmatched records.
- Detect missing records.
- Identify amount, customer, and status mismatches.
- Calculate reconciliation match rates.

### 2. Data Quality Monitoring
- Required field validation.
- Positive and non-negative value checks.
- Duplicate and uniqueness detection.
- Allowed-value validation.
- Range and date-format validation.
- Cross-column and referential validation.
- Automatic rule suggestions.

### 3. Executive Overview Dashboard
- Overall data health score.
- Money at risk.
- Open exception tickets.
- Match rate.
- Row match rate.

### 4. Exception Management
- Track reconciliation exceptions.
- Monitor unresolved issues.
- Maintain issue status and ownership.
- Track resolution activity.

### 5. Financial Risk Analysis
- Identify financial discrepancies.
- Prioritize high-risk exceptions.
- Monitor money at risk.

### 6. Retail Sales Analytics
- Analyze retail transaction data.
- Explore sales and transaction patterns.
- Monitor data quality across retail records.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Pandas | Data manipulation and reconciliation |
| NumPy | Numerical operations |
| Streamlit | Interactive dashboard |
| Plotly | Data visualization |
| MySQL / SQLite | Data storage and workflow persistence |
| Pytest | Automated testing |
| Git & GitHub | Version control |

## Application Modules

- Executive Overview
- Order Reconciliation
- Data Quality
- Retail Sales Analytics
- Retail Data Explorer

## Project Structure

```text
DataGuard/
│
├── app.py
├── core/
│   ├── config.py
│   ├── health.py
│   ├── reconciliation.py
│   ├── quality_rules.py
│   ├── workflow.py
│   └── ...
│
├── views/
│   ├── overview_page.py
│   ├── reconciliation_page.py
│   ├── rules_page.py
│   └── ...
│
├── scripts/
│   └── run_daily.py
│
├── tests/
│   ├── test_quality_rules.py
│   ├── test_reconciliation.py
│   ├── test_workflow.py
│   └── ...
│
├── requirements.txt
└── README.md
```

## Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/kumudpatkar/DataGuard.git
cd DataGuard
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the environment

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the application

```bash
python -m streamlit run app.py
```

Open the local URL displayed in your terminal.

## Run Automated Tests

DataGuard includes automated tests covering reconciliation, quality rules, workflow, risk calculations, and application functionality.

Run the complete test suite:

```bash
python -m pytest -v
```

**Latest test result: 78 tests passed.**

## Skills Demonstrated

This project demonstrates practical skills in:

- Data Cleaning and Transformation
- Exploratory Data Analysis
- SQL and Database Concepts
- Data Reconciliation
- Data Quality Validation
- Duplicate Detection
- Exception Management
- Financial Risk Analysis
- Dashboard Development
- Python Automation
- Testing and Debugging

## Business Impact

DataGuard demonstrates how data analytics and validation techniques can help organizations:

- Improve data consistency across systems.
- Identify missing and duplicate transactions.
- Detect financial discrepancies.
- Prioritize unresolved data issues.
- Monitor data quality through dashboards.
- Improve confidence in business reporting.

## Future Enhancements

- Advanced reconciliation analytics.
- More configurable business validation rules.
- Enhanced exception reporting.
- Scheduled reconciliation monitoring.
- Exportable business reports.

## Author

**Kumud Satyawan Patkar**

Data Analyst | SQL | Python | Excel | Power BI

- **GitHub:** https://github.com/kumudpatkar
- **LinkedIn:** https://linkedin.com/in/kumud-patkar-928180283
- **Portfolio:** https://kumud-portfolio-rho.vercel.app/

---

*DataGuard — Building trust in business data, one reconciliation at a time.*
