import pathlib
import pandas as pd
import numpy as np
from src.config import BASE_DIR, DEFAULT_SEED

# Configuration of fault injection frequencies (deterministic)
FAULT_CONFIG = {
    "missing_id": 0.001,            # fraction of rows missing primary key
    "duplicate_id": 0.001,          # fraction duplicated
    "invalid_category": 0.001,      # invalid categorical values
    "negative_quantity": 0.001,     # negative numbers in quantity columns
    "invalid_timestamp": 0.001,    # dates outside the simulation range
    "inconsistent_units": 0.001,   # Good + Rejected != Produced
    "incorrect_fk": 0.001,         # FK points to non‑existent dimension
    "missing_meter": 0.001,        # null energy readings
    "negative_downtime": 0.001,    # negative downtime minutes
}


def inject_faults():
    """Read raw CSVs, inject deterministic faults, and write a new set of CSVs.
    The original raw files are left untouched; faulty versions are written to
    ``data/raw/faulty/`` preserving the same filenames.
    """
    np.random.seed(DEFAULT_SEED)
    raw_dir = BASE_DIR / "data" / "raw"
    out_dir = raw_dir / "faulty"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Helper to introduce missing primary keys (assumes a column ending with 'Key')
    def maybe_introduce_missing(df, key_col):
        mask = np.random.rand(len(df)) < FAULT_CONFIG["missing_id"]
        df.loc[mask, key_col] = None
        return df

    def maybe_introduce_duplicate(df, key_col):
        dup_mask = np.random.rand(len(df)) < FAULT_CONFIG["duplicate_id"]
        dup_rows = df.loc[dup_mask].copy()
        # keep the same primary key value to create a duplicate entry
        df = pd.concat([df, dup_rows], ignore_index=True)
        return df

    # Process each fact table
    for fname in ["FactProduction.csv", "FactDowntime.csv", "FactQuality.csv", "FactEnergy.csv", "FactSensor.csv"]:
        path = raw_dir / fname
        df = pd.read_csv(path)
        # Identify the primary‑key column (ends with 'Key')
        key_col = [c for c in df.columns if c.endswith('Key')][0]
        df = maybe_introduce_missing(df, key_col)
        df = maybe_introduce_duplicate(df, key_col)

        # Invalid categorical values (foreign‑key columns)
        cat_cols = [c for c in df.columns if c.endswith('Key') and c != key_col]
        for col in cat_cols:
            mask = np.random.rand(len(df)) < FAULT_CONFIG["invalid_category"]
            df.loc[mask, col] = -999  # sentinel invalid id

        # Negative quantities for numeric quantity columns
        qty_cols = [c for c in df.columns if c.lower().endswith('units') or c.lower().endswith('minutes') or c.lower().endswith('kwh')]
        for col in qty_cols:
            mask = np.random.rand(len(df)) < FAULT_CONFIG["negative_quantity"]
            df.loc[mask, col] = -abs(df.loc[mask, col])

        # Inconsistent units for FactProduction
        if fname == "FactProduction.csv":
            mask = np.random.rand(len(df)) < FAULT_CONFIG["inconsistent_units"]
            df.loc[mask, 'ProducedUnits'] = df.loc[mask, 'GoodUnits'] + df.loc[mask, 'RejectedUnits'] + np.random.randint(1, 10)

        # Missing meter readings for FactEnergy
        if fname == "FactEnergy.csv":
            mask = np.random.rand(len(df)) < FAULT_CONFIG["missing_meter"]
            df.loc[mask, 'EnergyKWh'] = None

        # Negative downtime minutes for FactDowntime
        if fname == "FactDowntime.csv":
            mask = np.random.rand(len(df)) < FAULT_CONFIG["negative_downtime"]
            df.loc[mask, 'DowntimeMinutes'] = -abs(df.loc[mask, 'DowntimeMinutes'])

        # Write faulty CSV
        df.to_csv(out_dir / fname, index=False)

    # Copy dimension tables unchanged (they are required for validation)
    for dim in ["DimDate.csv", "DimShift.csv", "DimLine.csv", "DimMachine.csv", "DimProduct.csv", "DimReason.csv"]:
        src = raw_dir / dim
        dst = out_dir / dim
        dst.write_bytes(src.read_bytes())

    print(f"Fault injection completed. Faulty CSVs written to {out_dir}")

if __name__ == "__main__":
    inject_faults()
