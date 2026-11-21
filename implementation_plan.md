## Goal Description
The goal is to incorporate the **UCI AI4I 2020 Predictive Maintenance** dataset into the **FactoryPulse 360** portfolio project while preserving its provenance and clearly marking all synthetic assignments. The dataset will be stored alongside the factory‑simulation data, linked to the `FactSensor` table, and used for advanced analytics (e.g., sensor‑driven downtime prediction) without claiming any real ABB production telemetry.

## User Review Required
> [!IMPORTANT] **Dataset Handling**
> The user uploaded `ai4i+2020+predictive+maintenance+dataset.zip`. The plan assumes the zip contains the original `sensor_data.csv` (or similarly named) file. Confirm that the archive structure is acceptable or provide an alternative location for the raw CSV.

> [!WARNING] **File Size & CI Limits**
> The AI4I CSV (~10 MB) will be stored in the repository under `data/external/`. Ensure the repository size remains <100 MB to stay within typical GitHub limits.

## Open Questions
> [!CAUTION] **Column Mapping** – Which columns from the AI4I dataset should be mapped to our `DimMachine` and `FactSensor` dimensions?
> - The dataset includes `id`, `type`, `air temperature`, `process temperature`, … which are generic sensor readings.
> - Do you want a **one‑to‑one** mapping (each AI4I record → a synthetic machine) or a **many‑to‑one** mapping (multiple records per simulated machine)?
>
> > Please confirm the preferred mapping strategy.

> [!CAUTION] **Data Split** – Should the AI4I observations be split across the 90‑day simulation timeline, or kept as a separate historical snapshot?
>
> > Confirm whether timestamps need to be generated (e.g., random dates within the simulation period) or left as‑is.

## Proposed Changes
---
### Data Extraction & Placement
#### [NEW] data/external/ai4i/
* Directory to host the extracted AI4I CSV(s).

#### [NEW] src/load_external_ai4i.py
```python
"""Utility to load the AI4I Predictive Maintenance CSV into the SQLite database.

- Reads the CSV from `data/external/ai4i/sensor_data.csv`.
- Adds a surrogate `external_machine_id` column (UUID) to preserve provenance.
- Stores the raw rows in `FactSensor` with a flag `is_external = 1`.
- No alteration of the original values.
"""
import pandas as pd, sqlite3, pathlib, uuid
from src.config import BASE_DIR

def load_ai4i(db_path: pathlib.Path):
    src = BASE_DIR / "data" / "external" / "ai4i" / "sensor_data.csv"
    df = pd.read_csv(src)
    # Add provenance columns
    df["external_machine_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    df["is_external"] = 1
    # Align column names to FactSensor schema (mapper defined in docs/schema_mapping.md)
    # ... mapping logic ...
    conn = sqlite3.connect(db_path)
    df.to_sql("FactSensor", conn, if_exists="append", index=False)
    conn.close()
```
```

---
### Schema Adjustments
#### [MODIFY] sql/schema.sql
Add two columns to `FactSensor`:
```sql
ALTER TABLE FactSensor ADD COLUMN external_machine_id TEXT;
ALTER TABLE FactSensor ADD COLUMN is_external INTEGER NOT NULL DEFAULT 0;
```
These columns allow us to differentiate AI4I‑origin rows from simulated sensor data.

---
### Pipeline Integration
#### [MODIFY] src/run_pipeline.py
* Add a step after `load_sqlite.py` that invokes `load_external_ai4i.py` when the AI4I zip is present.
* Record the provenance in `docs/data_provenance.md`.

---
### Documentation Updates
#### [MODIFY] docs/data_dictionary.md
* Document the new columns (`external_machine_id`, `is_external`).
* Add a section describing the AI4I dataset source, licensing, and how it is used.

#### [NEW] docs/data_provenance.md
* Explain the extraction process, the random‑seed‑independent nature of the AI4I data, and how it is linked to synthetic machines.

---
### Test Additions
#### [NEW] tests/test_ai4i_integration.py
```python
def test_ai4i_loaded(tmp_path):
    # Run the pipeline with a small subset of the AI4I CSV (e.g., first 100 rows)
    # Verify that FactSensor contains rows where is_external = 1
    # Verify that external_machine_id is unique and non‑null
```

---
### CI Adjustments
#### [MODIFY] .github/workflows/ci.yml
* Ensure the CI job unpacks the uploaded AI4I zip (using `Expand-Archive`).
* Add a step to run `pytest -q tests/test_ai4i_integration.py`.

## Verification Plan
### Automated Tests
* Run the full test suite: `pytest -q` – all existing tests plus the new AI4I integration test must pass.
* Confirm that the SQLite schema includes the two new columns.
* Validate that `FactSensor` contains a mixture of simulated (`is_external = 0`) and external (`is_external = 1`) rows.

### Manual Verification
1. After running `python -m src.run_pipeline …`, open `data/factorypulse.db` in DB Browser for SQLite.
2. Execute `SELECT COUNT(*) FROM FactSensor WHERE is_external = 1;` – should match the number of rows in the AI4I CSV.
3. Open the generated Power BI data model (or Power Query) and verify that a new column `IsExternal` appears in the sensor table.
4. Review `docs/data_provenance.md` for clear attribution.

---
### Open Issues After Implementation
* None – all decisions are captured in the Open Questions above.

**Please review the plan, answer the open questions, and approve or suggest modifications.**