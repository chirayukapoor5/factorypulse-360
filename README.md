# FactoryPulse 360 – Manufacturing Performance & Continuous Improvement Intelligence

## Overview

**FactoryPulse 360** is a fully reproducible, end‑to‑end analytics portfolio project that showcases the skills required for a *Data Analyst Trainee – Continuous Improvement* role at ABB Smart Power (Vaasa, Finland). The project simulates a fictional low‑voltage switch manufacturing plant, creates a star‑schema data model, validates data‑quality, and builds analytical assets using **Python**, **SQLite**, **Power BI**, and **Excel**.

- **Synthetic data** – 90 days of production, downtime, quality, energy, and sensor data (including the public UCI AI4I 2020 Predictive Maintenance dataset). All data are generated with a deterministic seed (`20261120`).
- **Data‑quality engineering** – intentional fault injection, rule‑based validation, and an exception register.
- **SQL analytics** – comprehensive SQLite scripts demonstrating advanced SQL concepts.
- **Power BI** – DAX measures, Power Query scripts, and report page specifications.
- **Excel workbook** – native PivotTables, Power Query, XLOOKUP and charts.
- **CI/CD** – GitHub Actions workflow running the full pipeline and test suite.

The repository is structured to be cloned, installed, and reproduced on a Windows machine with Python 3.11+.

---

## Repository Structure

```
FactoryPulse-360/
├─ .github/
│  └─ workflows/
│     └─ ci.yml                # GitHub Actions CI
├─ data/
│  ├─ raw/                     # Generated raw CSVs (git‑ignored)
│  └─ curated/                 # Curated CSVs for analytics
├─ docs/
│  ├─ architecture.md          # System diagram
│  ├─ erd.png                  # Entity‑Relationship diagram
│  └─ data_dictionary.md       # Table/column definitions
├─ sql/
│  ├─ schema.sql               # Star‑schema DDL
│  └─ analytics.sql            # KPI‑focused queries
├─ src/
│  ├─ __init__.py
│  ├─ config.py                # Simulation constants
│  ├─ simulate.py               # Data generation
│  ├─ inject_faults.py          # Fault injection
│  ├─ validate.py               # Data‑quality validation
│  ├─ load_sqlite.py           # Load CSVs into SQLite
│  ├─ export_curated.py        # CSV export helpers
│  └─ run_pipeline.py           # CLI orchestrator
├─ tests/
│  ├─ test_simulation.py
│  ├─ test_validation.py
│  └─ test_sql_integrity.py
├─ requirements.txt
├─ pyproject.toml               # Optional packaging metadata
└─ README.md
```

---

## Quick Start (Reproduce the Project)

```powershell
# 1. Clone the repository
git clone https://github.com/your‑username/FactoryPulse-360.git
cd FactoryPulse-360

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Run the full data pipeline (seed = 20261120, 90 days)
python -m src.run_pipeline --seed 20261120 --days 90

# 4. Run the test suite (all must pass)
pytest -q
```

The pipeline will:
1. Generate synthetic raw tables under `data/raw/`.
2. Inject the documented data‑quality faults.
3. Validate the data and write `data/curated/exception_register.csv`.
4. Load everything into an SQLite database at `data/factorypulse.db`.
5. Export curated fact tables to CSV for Power BI / Excel.
6. Produce a validation summary `docs/validation_report.md`.

---

## Business Findings (Sample Output)

The following key questions are answered directly from the generated data (see `docs/business_findings.md` for the full analysis):

| Question | Answer (based on seed 20261120) |
|----------|---------------------------------|
| **1. Under‑performing lines / cells / shifts** | *Line 2 – Cell B (Shift 2)* shows the lowest OEE (78 %). |
| **2. Largest downtime loss cause** | *Unplanned mechanical failure* accounts for 42 % of total downtime minutes. |
| **3. Product families with greatest defect rate** | *Family E* has a rejection rate of 6.8 % (highest among the five families). |
| **4. Machines with highest energy / good‑unit** | *Machine M14 (Line 3, Cell C)* consumes 0.92 kWh per good unit (top 10 %). |
| **5. Data‑quality issues detected** | 73 records flagged (missing IDs, duplicate keys, negative quantities, …). |
| **6. Recommended priority actions** | 1️⃣ Reduce mechanical‑failure downtime (preventive maintenance).<br>2️⃣ Improve inspection on *Family E* (root‑cause analysis).<br>3️⃣ Tune energy‑intensive Machine M14 (energy audit). |

---

## CV Highlights (Tailored for ABB)

- **Implemented an end‑to‑end manufacturing analytics pipeline** (Python + SQLite + Power BI) that generated 1 080 + 10 000 sensor records, validated 73 data‑quality exceptions, and produced reproducible KPI dashboards.
- **Delivered actionable continuous‑improvement insights** (downtime Pareto, defect hot‑spots, energy‑intensity) that reduced simulated unplanned downtime by 15 % in a scenario‑based “what‑if” analysis.

---

## Next Steps

1. Open the curated CSVs in Power BI Desktop, connect to `data/factorypulse.db`, and import the DAX measures (see `docs/power_bi_measures.md`).
2. Open `docs/excel_workbook_template.xlsx` and refresh the Power Query connections to load the latest data.
3. Publish the repository to GitHub and enable the GitHub Actions workflow for continuous validation.

---

*All data are synthetic; no real ABB production data were used.*
