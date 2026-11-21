# FactoryPulse 360 — Manufacturing Analytics Engineering & Quality System

[![CI Automation & Manufacturing Analytics Verification](https://github.com/chirayukapoor5/factorypulse-360/actions/workflows/ci.yml/badge.svg)](https://github.com/chirayukapoor5/factorypulse-360/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Tests Passing](https://img.shields.io/badge/tests-124%20passed%2C%200%20failed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FactoryPulse 360** is an enterprise-grade discrete manufacturing analytics engineering and data quality platform modeling 3 production lines, 6 manufacturing cells, and 24 machines producing low-voltage electrical switches and smart circuit breakers. 

Built to simulate and analyze shop-floor operations at **ABB Smart Power** standards, the platform demonstrates complete end-to-end analytics engineering: deterministic data simulation, automated fault injection, rigorous data quality validation, relational star-schema warehousing in SQLite, Cartesian-free analytical SQL reporting, automated reconciliation audits, 100% isolated pytest coverage, GitHub Actions CI automation, and a prepared semantic handoff package for Power BI and Excel downstream authors.

---

## Architecture Overview

```
                                [ FactoryPulse 360 Architecture ]

  +------------------------------+                  +--------------------------------+
  | Discrete Factory Simulator   |                  | UCI AI4I 2020 Benchmark CSV    |
  | (NumPy default_rng seed 42)  |                  | (10,000 observations x 14 cols)|
  +--------------+---------------+                  +---------------+----------------+
                 |                                                  |
                 v                                                  |
  +------------------------------+                                  |
  | Raw Telemetry & Dimensions   |                                  |
  | (data/raw/)                  |                                  |
  +--------------+---------------+                                  |
                 |                                                  |
                 v                                                  |
  +------------------------------+                                  |
  | Fault Injection Engine       |                                  |
  | (12 Documented Defect Types) |                                  |
  +--------------+---------------+                                  |
                 |                                                  |
                 v                                                  |
  +------------------------------+                                  |
  | Data Quality Validator       |                                  |
  | (0 Silent Record Deletion)   |                                  |
  +-------+--------------+-------+                                  |
          |              |                                          |
Valid     v              v Quarantined                              |
  +---------------+  +--------------------+                         |
  | data/curated/ |  | FactDQExceptions   |                         |
  +-------+-------+  +---------+----------+                         |
          |                    |                                    |
          v                    v                                    v
  +-----------------------------------------------------------------+----+
  |                     SQLite Curated Warehouse                         |
  |                      (data/factorypulse.db)                          |
  |  - Dimensions: DimDate, DimShift, DimLine, DimMachine, DimProduct... |
  |  - Facts: FactProduction, FactDowntime, FactQuality, FactEnergy...   |
  |  - Sensor: FactSensor (4,275 internal + 50,000 authentic AI4I benchmark)|
  |  - Analytical Views: v_ManufacturingMetrics, v_LineShiftOEE          |
  +--------------------------------+-------------------------------------+
                                   |
           +-----------------------+-----------------------+
           |                                               |
           v                                               v
+-------------------------------+              +-------------------------------+
| Analytical SQL & Reconciliation|              | Downstream BI Handoff Package |
| (reports/analytics/)          |              | (bi_handoff/)                 |
| - production_summary.csv      |              | - dimensions/ (6 CSVs)        |
| - oee_by_line_shift.csv       |              | - facts/ (5 CSVs)             |
| - downtime_pareto.csv         |              | - exceptions/ (DQ CSV)        |
| - quality_summary.csv         |              | - kpi_reference.csv           |
| - energy_intensity.csv        |              | - 5 Markdown Specifications   |
| - data_quality_summary.csv    |              | - dax/measures.dax            |
| - reconciliation_report.csv   |              | - power_query/transformations.m|
+-------------------------------+              +-------------------------------+
```

---

## Quickstart & Reproduction Guide

### Prerequisites
- Python 3.11 or 3.12
- Git

### 1. Clone & Set Up Environment
```bash
# Clone repository
git clone https://github.com/chirayukapoor5/factorypulse-360.git
cd factorypulse-360

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Execute Full Deterministic Data Pipeline
```bash
python -m src.run_pipeline --seed 42 --days 30 --start-date 2024-01-01 --output-dir data
```
This executes the 6-stage pipeline:
1. Simulates 30 days of shop-floor telemetry across 3 lines, 6 cells, and 24 machines.
2. Injects deterministic data quality faults into `data/raw/faulty/`.
3. Validates telemetry, quarantining anomalies into `FactDQExceptions.csv` with zero silent record deletion.
4. Initializes and populates the SQLite curated star-schema warehouse (`data/factorypulse.db`).
5. Ingests the 10,000 UCI AI4I 2020 benchmark observations into `FactSensor` (yielding 50,000 benchmark sensor rows).
6. Computes analytical queries and exports 6 analytical CSV reports plus reconciliation audit.

### 3. Run the Isolated Pytest Suite
```bash
pytest -v
```
All **124 tests pass with 0 failures**. The test suite uses temporary directories (`tmp_path`) and isolated in-memory/file databases, guaranteeing **zero repository data mutations**.

### 4. Analytical Reports & Reconciliation Audit
```bash
python src/generate_reports.py
```
Exports reports to `reports/analytics/` and verifies reconciliation between source fact tables and analytical aggregates with **0.0 variance**.

---

## Verified Database Warehouse State (30-Day Curated Baseline)

The curated relational warehouse at `data/factorypulse.db` enforces foreign keys (`PRAGMA foreign_keys = ON;`) and contains the following verified row counts:

| Table Name | Entity Type | Table Grain | Exact Row Count | Description |
|:---|:---|:---|---:|:---|
| `DimDate` | Dimension | 1 row per calendar day | **30** | Calendar dates: 2024-01-01 to 2024-01-30 |
| `DimShift` | Dimension | 1 row per shift | **2** | Shift 1 (06:00–14:00), Shift 2 (14:00–22:00) |
| `DimLine` | Dimension | 1 row per production line | **3** | Line 1, Line 2, Line 3 |
| `DimMachine` | Dimension | 1 row per machine | **24** | 24 machines across 6 manufacturing cells |
| `DimProduct` | Dimension | 1 row per product SKU | **5** | Families A–E (Smart circuit breakers) |
| `DimReason` | Dimension | 1 row per downtime reason | **8** | Stoppage taxonomy (Planned, Breakdown, Setup) |
| `FactProduction` | Fact | Machine $\times$ Shift $\times$ Date | **1,416** | Unit production (Target, Produced, Good, Rejected) |
| `FactDowntime` | Fact | Machine $\times$ Reason $\times$ Shift $\times$ Date | **1,416** | Stoppages (Planned vs Unplanned minutes) |
| `FactQuality` | Fact | Machine $\times$ Reason $\times$ Shift $\times$ Date | **1,428** | Defect counts categorized by defect reason |
| `FactEnergy` | Fact | Machine $\times$ Shift $\times$ Date | **1,423** | Machine-level electrical energy (kWh) |
| `FactSensor` | Fact | Machine $\times$ Date $\times$ Observation | **54,275** | 4,275 internal telemetry + 50,000 UCI AI4I benchmark |
| `FactDQExceptions`| Audit Fact | 1 row per quarantined anomaly | **153** | Complete quarantined exception register |

---

## Verified Manufacturing KPI Benchmarks & Reconciliation

All KPI calculations use proper weighted aggregates without arbitrary multipliers or hardcoded 24-hour periods.

### Enterprise 30-Day Curated KPI Summary

| Metric | Enterprise Formula | Mathematical Calculation | Benchmark Figure |
|:---|:---|:---|:---:|
| **Availability (A)** | $\frac{\text{Operating Minutes}}{\text{Planned Production Minutes}}$ | $\frac{684,143.17\text{ min}}{688,120.98\text{ min}} \times 100\%$ | **99.42%** |
| **Performance (P)** | $\frac{\text{Ideal Production Minutes}}{\text{Operating Minutes}}$ | $\frac{133,478.00\text{ min}}{684,143.17\text{ min}} \times 100\%$ | **19.51%** |
| **Quality (Q)** | $\frac{\text{Good Units}}{\text{Total Produced Units}}$ | $\frac{127,133\text{ units}}{133,478\text{ units}} \times 100\%$ | **95.25%** |
| **OEE** | $\text{Availability} \times \text{Performance} \times \text{Quality}$ | $0.994219 \times 0.195102 \times 0.952464$ | **18.48%** |
| **Energy Intensity** | $\frac{\text{Total Energy Consumption (kWh)}}{\text{Total Good Units}}$ | $\frac{92,885.22\text{ kWh}}{127,133\text{ units}}$ | **0.7306 kWh/unit** |

### Breakdown by Production Line & Operating Shift

| Entity | Availability | Performance | Quality | OEE | Energy Intensity | Notes |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **Line 1** | 99.47% | 19.61% | 95.23% | **18.58%** | 0.6980 kWh/unit | Nominal baseline efficiency |
| **Line 2** | 99.36% | 19.45% | 95.30% | **18.42%** | 0.7088 kWh/unit | Elevated Shift 2 downtime (+40% stoppage surge) |
| **Line 3** | 99.44% | 19.47% | 95.20% | **18.43%** | **0.7853 kWh/unit** | **Energy Hotspot** on Cell 2 (+12.5% vs Line 1) |
| **Shift 1** | 99.43% | 19.47% | 95.25% | **18.44%** | 0.7351 kWh/unit | Morning Shift (06:00–14:00) |
| **Shift 2** | 99.41% | 19.55% | 95.24% | **18.51%** | 0.7261 kWh/unit | Afternoon Shift (14:00–22:00) |

### Automated Reconciliation Audit (`reports/analytics/reconciliation_report.csv`)

| Reconciled Metric | Source Fact Table Sum | Aggregated Report Sum | Absolute Variance | Audit Status |
|:---|:---:|:---:|:---:|:---:|
| **Produced Units** | 133,478 | 133,478 | **0.0** | **BALANCED** |
| **Good Units** | 127,133 | 127,133 | **0.0** | **BALANCED** |
| **Downtime Minutes** | 7,056.83 | 7,056.83 | **0.0** | **BALANCED** |
| **Electrical Energy (kWh)** | 92,885.22 | 92,885.22 | **0.0** | **BALANCED** |

---

## Data Quality Validation & Zero Silent Deletion Audit

The validation engine (`src/validate.py`) enforces 12 discrete manufacturing integrity rules across all fact tables. In our curated 30-day baseline, **153 anomalies are quarantined** into `FactDQExceptions` with complete traceability:

| Source Fact Table | Quarantined Exceptions | Rules Detected & Quarantined |
|:---|---:|:---|
| `FactProduction` | **26** | `UnitSumMismatch` (6), `InvalidTimestamp` (5), `NegativeValue` (4), `NullPrimaryKey` (4), `InvalidKPIRange` (3), `DuplicatePrimaryKey` (2), `OrphanForeignKey` (2) |
| `FactDowntime` | **28** | `DuplicatePrimaryKey` (8), `OrphanForeignKey` (8), `NegativeDowntime` (3), `NullPrimaryKey` (3), `DowntimeInconsistency` (2), `InvalidCategory` (2), `InvalidTimestamp` (2) |
| `FactQuality` | **26** | `DefectCountMismatch` (12), `DuplicatePrimaryKey` (8), `NegativeValue` (2), `InvalidTimestamp` (2), `NullPrimaryKey` (1), `OrphanForeignKey` (1) |
| `FactEnergy` | **18** | `OrphanForeignKey` (5), `NullPrimaryKey` (4), `NullEnergyReading` (3), `InvalidTimestamp` (3), `DuplicatePrimaryKey` (2), `NegativeValue` (1) |
| `FactSensor` | **55** | `DuplicatePrimaryKey` (20), `NullPrimaryKey` (13), `InvalidTimestamp` (10), `InvalidCategory` (6), `OrphanForeignKey` (6) |
| **Total** | **153** | **100% Traceable in FactDQExceptions, Zero Silent Data Deletion** |

---

## Key Continuous Improvement & Analytical Findings

1. **Downtime Pareto Concentration**:
   - `Planned_Maintenance` accounts for **43.63%** of all downtime (3,079.02 min).
   - `Mechanical_Failure` represents **25.94%** of downtime (1,830.34 min).
   - Combined, top two stoppage causes represent **69.57% cumulative downtime**.
2. **Quality & Scrap Spike (`Family_E`)**:
   - `Family_E` smart circuit breakers exhibit a defect/scrap spike with a **5.97% rejection rate** (vs 4.48%–4.51% across Families A–D).
3. **Energy Hotspot (Line 3 Cell 2)**:
   - Machines 321–324 consume **0.8459 to 0.8871 kWh per good unit**, creating an energy consumption hotspot (+12.5% higher specific energy than Line 1).
4. **Shift Operational Discrepancy**:
   - Line 2 Cell 1 experiences a +40% surge in downtime during Shift 2, driving lower Availability for that specific operating cell.

---

## External Data Ingestion & Provenance Disclosure

- **Dataset**: UCI AI4I 2020 Predictive Maintenance Dataset (Dua & Graff 2019 / Matzka 2020).
- **Source File**: `data/external/ai4i/ai4i2020.csv` (10,000 observations $\times$ 14 columns, 522 KB).
- **Provenance Disclosure**: The dataset represents synthetic benchmark milling equipment telemetry from the UCI Machine Learning Repository, **NOT real ABB factory production telemetry**.
- **Transformation**: Unpivots 5 continuous numeric sensors (`Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]`) into exactly **50,000 FactSensor rows** flagged with `is_external = 1` and deterministic device IDs (`AI4I-{Type}-{UDI:05d}`).

---

## Power BI & Excel Semantic Handoff Package (`bi_handoff/`)

To support downstream BI authors without coupling repository state to proprietary binary formats, all semantic assets are provided in `bi_handoff/`:

```
bi_handoff/
├── dimensions/
│   ├── DimDate.csv
│   ├── DimShift.csv
│   ├── DimLine.csv
│   ├── DimMachine.csv
│   ├── DimProduct.csv
│   └── DimReason.csv
├── facts/
│   ├── FactProduction.csv
│   ├── FactDowntime.csv
│   ├── FactQuality.csv
│   ├── FactEnergy.csv
│   └── FactSensor.csv
├── exceptions/
│   └── FactDQExceptions.csv
├── kpi_reference.csv                  # Benchmark reference figures for validation
├── model_relationships.md             # Star-schema 1-to-many cardinality specification
├── kpi_definitions.md                 # Mathematical formulas, numerators & denominators
├── data_dictionary.md                 # Complete table and column specifications
├── refresh_instructions.md            # Step-by-step Power BI & Excel import instructions
├── data_lineage.md                    # End-to-end data lifecycle documentation
├── dax/
│   └── measures.dax                   # Production DAX measures library
└── power_query/
    └── transformations.m              # Parameterized Power Query M import scripts
```

### Unfinished Downstream BI Tasks (Handoff Scope)
As per architecture scope (do NOT commit native binary PBIX or Excel workbooks):
1. **Interactive PBIX Report Authoring**: Constructing executive report canvasses in Power BI Desktop (Executive OEE, Loss Pareto, Scrap Drillthrough, Energy Hotspots).
2. **Power BI Service Deployment**: Configuring workspace tenant, scheduled refresh via on-premise gateway, and mobile layouts.
3. **Excel Operational Workbook**: Designing native `.xlsx` financial workbooks with PivotTables, Slicers, and financial scrap impact calculations.
4. **Row-Level Security (RLS)**: Enforcing role-based filters by Line Manager and Shift Supervisor.

---

## Continuous Integration & Automated Verification

GitHub Actions runs on every push and pull request to `main` on Ubuntu Linux with Python 3.12:
- Checks out code and installs dependencies.
- Verifies source dataset presence (`data/external/ai4i/ai4i2020.csv`).
- Runs full deterministic pipeline (`python -m src.run_pipeline`).
- Executes 124 isolated pytest unit and integration tests.
- Generates analytical CSV reports and validates zero reconciliation variance (`python src/generate_reports.py`).
- Publishes reports, exception registers, and BI handoff packages as workflow artifacts.

---

## License
This project is open-source and available under the [MIT License](LICENSE).
The UCI AI4I 2020 Predictive Maintenance dataset is distributed under Creative Commons Attribution 4.0 International (CC BY 4.0).
