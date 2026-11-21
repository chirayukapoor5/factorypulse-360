# FactoryPulse 360 — End-to-End Data Lineage & Provenance Architecture

## Executive Summary
This document maps the complete data lifecycle of the FactoryPulse 360 platform, tracking data provenance from original telemetry generation and external benchmark ingestion through fault injection, automated quality validation, relational warehousing, analytical aggregations, and finally downstream Power BI and Excel consumption.

---

## 1. End-to-End Lineage Flow Diagram

```
[ UCI AI4I 2020 Benchmark CSV ]     [ Discrete Factory Simulator ]
   (data/external/ai4i/ai4i2020.csv)   (src/simulate.py: seed, days, start-date)
                 |                                     |
                 |                             +-------v-------+
                 |                             |   data/raw/   |
                 |                             +-------+-------+
                 |                                     |
                 |                       +-------------v-------------+
                 |                       |  Fault Injection Engine   |
                 |                       |   (src/inject_faults.py)  |
                 |                       +-------------+-------------+
                 |                                     |
                 |                             +-------v-------+
                 |                             | data/raw/faulty|
                 |                             +-------+-------+
                 |                                     |
                 |                       +-------------v-------------+
                 |                       |  Data Quality Validator   |
                 |                       |     (src/validate.py)     |
                 |                       +------+-------------+------+
                 |                              |             |
                 |                  Valid Rows  |             | Anomalies
                 |             +----------------v---+     +---v------------------+
                 |             |    data/curated/   |     | FactDQExceptions.csv |
                 |             +--------+-----------+     +---+------------------+
                 |                      |                     |
                 +--------------+       |                     |
                                |       |                     |
                     +----------v-------v---------------------v----------+
                     |            Curated SQLite Warehouse               |
                     |             (data/factorypulse.db)                |
                     |  - Dimensions: DimDate, DimShift, DimMachine, etc.|
                     |  - Facts: FactProduction, FactDowntime, etc.      |
                     |  - Sensor: FactSensor (Internal + External AI4I)  |
                     |  - Exceptions: FactDQExceptions                   |
                     |  - Views: v_ManufacturingMetrics, v_LineShiftOEE  |
                     +--------------------------+------------------------+
                                                |
                     +--------------------------+------------------------+
                     |                                                   |
         +-----------v-------------+                         +-----------v-------------+
         | Analytical SQL Reports  |                         |    BI Handoff Package   |
         | (src/generate_reports)  |                         |      (bi_handoff/)      |
         +-----------+-------------+                         +-----------+-------------+
                     |                                                   |
                     | (reports/analytics/)                              | (CSV, MD, DAX, M)
                     v                                                   v
        +----------------------------+                      +----------------------------+
        | - production_summary.csv   |                      | Downstream Semantic Models |
        | - oee_by_line_shift.csv    |                      | - Power BI Desktop         |
        | - downtime_pareto.csv      |                      | - Power BI Service         |
        | - quality_summary.csv      |                      | - Microsoft Excel Pivot    |
        | - energy_intensity.csv     |                      +----------------------------+
        | - data_quality_summary.csv |
        | - reconciliation_report.csv|
        +----------------------------+
```

---

## 2. Stage-by-Stage Lineage Specifications

### Stage 1: Raw Ingestion & Synthetic Generation
- **Source 1: Discrete Factory Simulator (`src/simulate.py`)**:
  - Simulates 3 production lines, 6 manufacturing cells, and 24 machines producing 5 smart circuit breaker product families across 2 daily shifts.
  - Driven by explicit CLI arguments (`--seed`, `--days`, `--start-date`, `--output-dir`), utilizing NumPy's isolated `default_rng(seed)` generator to guarantee bit-for-bit repeatability across platforms.
  - Outputs raw canonical dimensions and telemetry tables to `data/raw/`.
- **Source 2: Authentic External Benchmark (`data/external/ai4i/ai4i2020.csv`)**:
  - Preserved strictly unmodified as published by the UCI Machine Learning Repository (10,000 observations $\times$ 14 attributes).
  - Explicit provenance attribution: synthetic UCI benchmark telemetry, distinct from real ABB factory operational data.

### Stage 2: Data Quality Fault Injection (`src/inject_faults.py`)
- Injects 12 documented defect scenarios into raw telemetry to test data pipeline resilience:
  1. `DuplicatePrimaryKey`: Cloned primary keys in fact tables.
  2. `NullPrimaryKey`: Nullified surrogate keys.
  3. `OrphanForeignKey`: Foreign keys referencing non-existent dimension keys.
  4. `NegativeValue`: Negative produced/good unit quantities or energy values.
  5. `NegativeDowntime`: Negative stoppage minutes.
  6. `InvalidTimestamp`: Non-existent dates (e.g. month > 12).
  7. `NullEnergyReading`: Null/NaN meter readings.
  8. `InvalidCategory`: Stoppage categories outside standardized domain taxonomy.
  9. `UnitSumMismatch`: Inconsistent production sums (`ProducedUnits != GoodUnits + RejectedUnits`).
  10. `DefectCountMismatch`: Scrap count diverging from defect breakdown.
  11. `DowntimeInconsistency`: Stoppage exceeding total shift scheduled minutes.
  12. `InvalidKPIRange`: Out-of-bounds production ratios.
- Outputs corrupted datasets to `data/raw/faulty/` and logs injected counts into `fault_counts.json`.

### Stage 3: Data Quality Validation & Quarantine (`src/validate.py`)
- Validates all records against schema constraints, referential integrity, domain rules, and physical bounds.
- **Zero Silent Data Deletion Guarantee**:
  - Anomalous records are quarantined into `FactDQExceptions.csv` with source table, record identifier, rule violated, severity, disposition, and full raw payload.
  - Cleaned valid records are output to `data/curated/`.
  - In our curated 30-day baseline, 153 anomalous records are quarantined while 100% of valid manufacturing telemetry is preserved.

### Stage 4: Relational Data Warehousing (`src/load_sqlite.py`, `src/load_external_ai4i.py`)
- Initializes SQLite warehouse `data/factorypulse.db` with `PRAGMA foreign_keys = ON;`.
- Loads dimension tables and curated fact tables.
- Triggers database-level validation to prevent constraint bypassing.
- Unpivots the 5 continuous numeric sensor measurements from the 10,000 UCI AI4I observations into 50,000 `FactSensor` rows with deterministic device IDs (`AI4I-{Type}-{UDI:05d}`) and flags them with `is_external = 1`.
- Compiles analytical views: `v_ManufacturingMetrics` and `v_LineShiftOEE`.

### Stage 5: Analytical SQL & Reconciliation Engine (`src/generate_reports.py`)
- Executes analytical queries with Common Table Expression (CTE) pre-aggregations at the intended grain `(DateKey, ShiftKey, LineKey)` before joining, preventing Cartesian explosion.
- Generates 6 analytical CSV reports plus `reconciliation_report.csv` in `reports/analytics/`.
- Conducts automated reconciliation proving source fact totals match aggregated reports with exactly **0.0 variance**.

### Stage 6: Downstream BI Handoff Package (`bi_handoff/`)
- Curated dimensions and facts copied to `bi_handoff/dimensions/` and `bi_handoff/facts/`.
- Quarantined exceptions stored in `bi_handoff/exceptions/FactDQExceptions.csv`.
- Benchmark reference KPIs provided in `bi_handoff/kpi_reference.csv`.
- Standalone DAX measures and Power Query M transformation scripts provided for zero-friction Power BI / Excel import.
