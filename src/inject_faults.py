import json
import pathlib
import pandas as pd
import numpy as np
from src.config import BASE_DIR, DEFAULT_SEED

# Configuration of fault injection frequencies (deterministic)
FAULT_CONFIG = {
    "missing_id": 0.002,             # fraction of rows missing primary key (NullPrimaryKey)
    "duplicate_id": 0.002,           # fraction duplicated (DuplicatePrimaryKey)
    "incorrect_fk": 0.002,           # FK points to non-existent dimension (OrphanForeignKey)
    "negative_quantity": 0.002,      # negative numbers in quantity columns (NegativeValue)
    "negative_downtime": 0.002,      # negative downtime minutes (NegativeDowntime)
    "invalid_timestamp": 0.002,      # dates outside the simulation range (InvalidTimestamp)
    "missing_meter": 0.002,          # null energy readings (NullEnergyReading)
    "invalid_category": 0.002,       # invalid categorical values (InvalidCategory)
    "inconsistent_units": 0.002,     # Good + Rejected != Produced (UnitSumMismatch)
    "defect_mismatch": 0.002,        # FactQuality.DefectCount != FactProduction.RejectedUnits (DefectCountMismatch)
    "downtime_inconsistency": 0.002, # DowntimeMinutes > 480 (DowntimeInconsistency)
    "invalid_kpi_range": 0.002,      # GoodUnits > ProducedUnits (InvalidKPIRange)
}


def inject_faults(
    input_dir: pathlib.Path | None = None,
    output_dir: pathlib.Path | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, int]:
    """Read raw CSVs, inject deterministic faults, and write a new set of CSVs.

    The original raw files are left untouched; faulty versions are written to
    ``output_dir`` (defaulting to ``input_dir / 'faulty'``) preserving the same filenames.

    Parameters
    ----------
    input_dir : Path, optional
        Source directory containing raw CSVs. Defaults to BASE_DIR / 'data' / 'raw'.
    output_dir : Path, optional
        Target directory for faulty CSVs. Defaults to input_dir / 'faulty'.
    seed : int, optional
        RNG seed for deterministic fault injection. Defaults to DEFAULT_SEED.

    Returns
    -------
    dict[str, int]
        Dictionary of injected fault counts by rule.
    """
    if input_dir is None:
        input_dir = BASE_DIR / "data" / "raw"
    input_dir = pathlib.Path(input_dir)

    if output_dir is None:
        output_dir = input_dir / "faulty"
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    fault_counts: dict[str, int] = {
        "NullPrimaryKey": 0,
        "DuplicatePrimaryKey": 0,
        "OrphanForeignKey": 0,
        "NegativeValue": 0,
        "NegativeDowntime": 0,
        "InvalidTimestamp": 0,
        "NullEnergyReading": 0,
        "InvalidCategory": 0,
        "UnitSumMismatch": 0,
        "DefectCountMismatch": 0,
        "DowntimeInconsistency": 0,
        "InvalidKPIRange": 0,
    }

    # Load fact tables that exist
    fact_file_names = [
        "FactProduction.csv",
        "FactDowntime.csv",
        "FactQuality.csv",
        "FactEnergy.csv",
        "FactSensor.csv",
    ]

    loaded_facts: dict[str, pd.DataFrame] = {}
    for fname in fact_file_names:
        p = input_dir / fname
        if p.exists():
            loaded_facts[fname] = pd.read_csv(p)

    for fname, df in loaded_facts.items():
        # Identify primary-key column (ends with 'Key')
        key_cols = [c for c in df.columns if c.endswith("Key")]
        if not key_cols:
            continue
        key_col = key_cols[0]

        # 1. Missing primary keys (NullPrimaryKey)
        mask_missing = rng.random(len(df)) < FAULT_CONFIG["missing_id"]
        count_missing = int(mask_missing.sum())
        if count_missing > 0:
            df.loc[mask_missing, key_col] = None
            fault_counts["NullPrimaryKey"] += count_missing

        # 2. Duplicate primary keys (DuplicatePrimaryKey)
        non_null_mask = df[key_col].notna()
        non_null_idx = df[non_null_mask].index
        if len(non_null_idx) > 0:
            mask_dup = rng.random(len(non_null_idx)) < FAULT_CONFIG["duplicate_id"]
            dup_indices = non_null_idx[mask_dup]
            dup_rows = df.loc[dup_indices].copy()
            count_dup = len(dup_rows)
            if count_dup > 0:
                df = pd.concat([df, dup_rows], ignore_index=True)
                fault_counts["DuplicatePrimaryKey"] += count_dup

        # 3. Invalid timestamps (InvalidTimestamp)
        if "DateKey" in df.columns:
            valid_cand = df[df[key_col].notna() & df["DateKey"].notna()].index
            if len(valid_cand) > 0:
                mask_ts = rng.random(len(valid_cand)) < FAULT_CONFIG["invalid_timestamp"]
                ts_idx = valid_cand[mask_ts]
                count_ts = len(ts_idx)
                if count_ts > 0:
                    df.loc[ts_idx, "DateKey"] = 99999999
                    fault_counts["InvalidTimestamp"] += count_ts

        # 4. Orphan foreign keys (OrphanForeignKey)
        # Exclude DateKey (tested by InvalidTimestamp) and primary key
        fk_cols = [c for c in df.columns if c.endswith("Key") and c != key_col and c != "DateKey"]
        for col in fk_cols:
            cand = df[df[key_col].notna() & df[col].notna() & (df[col] != -999)].index
            if len(cand) > 0:
                prob = FAULT_CONFIG["incorrect_fk"] / max(1, len(fk_cols))
                mask_fk = rng.random(len(cand)) < prob
                fk_idx = cand[mask_fk]
                count_fk = len(fk_idx)
                if count_fk > 0:
                    df.loc[fk_idx, col] = -999
                    fault_counts["OrphanForeignKey"] += count_fk

        # 5. Table-specific faults
        if fname == "FactProduction.csv":
            # Negative quantities
            qty_cols = [c for c in ["ProducedUnits", "GoodUnits", "RejectedUnits", "TargetUnits"] if c in df.columns]
            for col in qty_cols:
                cand = df[df[key_col].notna() & df[col].notna() & (df[col] > 0)].index
                if len(cand) > 0:
                    prob = FAULT_CONFIG["negative_quantity"] / max(1, len(qty_cols))
                    mask_neg = rng.random(len(cand)) < prob
                    neg_idx = cand[mask_neg]
                    count_neg = len(neg_idx)
                    if count_neg > 0:
                        df.loc[neg_idx, col] = -abs(df.loc[neg_idx, col])
                        fault_counts["NegativeValue"] += count_neg

            # Invalid KPI component ranges: GoodUnits > ProducedUnits
            cand_kpi = df[
                df[key_col].notna()
                & (df["ProducedUnits"] > 0)
                & (df["GoodUnits"] >= 0)
            ].index
            if len(cand_kpi) > 0:
                mask_kpi = rng.random(len(cand_kpi)) < FAULT_CONFIG["invalid_kpi_range"]
                kpi_idx = cand_kpi[mask_kpi]
                count_kpi = len(kpi_idx)
                if count_kpi > 0:
                    addends = rng.integers(5, 25, size=count_kpi)
                    df.loc[kpi_idx, "GoodUnits"] = df.loc[kpi_idx, "ProducedUnits"] + addends
                    fault_counts["InvalidKPIRange"] += count_kpi

            # UnitSumMismatch: GoodUnits + RejectedUnits != ProducedUnits
            cand_units = df[
                df[key_col].notna()
                & (df["ProducedUnits"] >= 0)
                & (df["GoodUnits"] >= 0)
                & (df["GoodUnits"] <= df["ProducedUnits"])
            ].index
            if len(cand_units) > 0:
                mask_unit = rng.random(len(cand_units)) < FAULT_CONFIG["inconsistent_units"]
                unit_idx = cand_units[mask_unit]
                count_unit = len(unit_idx)
                if count_unit > 0:
                    addends = rng.integers(1, 10, size=count_unit)
                    df.loc[unit_idx, "ProducedUnits"] = (
                        df.loc[unit_idx, "GoodUnits"] + df.loc[unit_idx, "RejectedUnits"] + addends
                    )
                    fault_counts["UnitSumMismatch"] += count_unit

        elif fname == "FactDowntime.csv":
            # Negative downtime
            cand_neg_dt = df[df[key_col].notna() & df["DowntimeMinutes"].notna() & (df["DowntimeMinutes"] > 0)].index
            if len(cand_neg_dt) > 0:
                mask_ndt = rng.random(len(cand_neg_dt)) < FAULT_CONFIG["negative_downtime"]
                ndt_idx = cand_neg_dt[mask_ndt]
                count_ndt = len(ndt_idx)
                if count_ndt > 0:
                    df.loc[ndt_idx, "DowntimeMinutes"] = -abs(df.loc[ndt_idx, "DowntimeMinutes"])
                    fault_counts["NegativeDowntime"] += count_ndt

            # Downtime inconsistency: DowntimeMinutes > 480
            cand_dti = df[df[key_col].notna() & df["DowntimeMinutes"].notna() & (df["DowntimeMinutes"] >= 0)].index
            if len(cand_dti) > 0:
                mask_dti = rng.random(len(cand_dti)) < FAULT_CONFIG["downtime_inconsistency"]
                dti_idx = cand_dti[mask_dti]
                count_dti = len(dti_idx)
                if count_dti > 0:
                    df.loc[dti_idx, "DowntimeMinutes"] = 480.0 + rng.integers(10, 120, size=count_dti)
                    fault_counts["DowntimeInconsistency"] += count_dti

            # Invalid category: Planned column set to invalid value
            if "Planned" in df.columns:
                cand_cat = df[df[key_col].notna()].index
                if len(cand_cat) > 0:
                    prob = FAULT_CONFIG["invalid_category"] / 2
                    mask_cat = rng.random(len(cand_cat)) < prob
                    cat_idx = cand_cat[mask_cat]
                    count_cat = len(cat_idx)
                    if count_cat > 0:
                        df.loc[cat_idx, "Planned"] = -1
                        fault_counts["InvalidCategory"] += count_cat

        elif fname == "FactQuality.csv":
            # Negative defect count
            cand_neg_q = df[df[key_col].notna() & df["DefectCount"].notna() & (df["DefectCount"] > 0)].index
            if len(cand_neg_q) > 0:
                prob = FAULT_CONFIG["negative_quantity"] / 2
                mask_neg_q = rng.random(len(cand_neg_q)) < prob
                neg_q_idx = cand_neg_q[mask_neg_q]
                count_neg_q = len(neg_q_idx)
                if count_neg_q > 0:
                    df.loc[neg_q_idx, "DefectCount"] = -abs(df.loc[neg_q_idx, "DefectCount"])
                    fault_counts["NegativeValue"] += count_neg_q

            # Defect mismatch: FactQuality.DefectCount != FactProduction.RejectedUnits
            cand_def = df[df[key_col].notna() & df["DefectCount"].notna() & (df["DefectCount"] >= 0)].index
            if len(cand_def) > 0:
                mask_def = rng.random(len(cand_def)) < FAULT_CONFIG["defect_mismatch"]
                def_idx = cand_def[mask_def]
                count_def = len(def_idx)
                if count_def > 0:
                    df.loc[def_idx, "DefectCount"] = df.loc[def_idx, "DefectCount"] + rng.integers(5, 20, size=count_def)
                    fault_counts["DefectCountMismatch"] += count_def

        elif fname == "FactEnergy.csv":
            # Missing meter reading: EnergyKWh = None
            cand_em = df[df[key_col].notna() & df["EnergyKWh"].notna()].index
            if len(cand_em) > 0:
                mask_em = rng.random(len(cand_em)) < FAULT_CONFIG["missing_meter"]
                em_idx = cand_em[mask_em]
                count_em = len(em_idx)
                if count_em > 0:
                    df.loc[em_idx, "EnergyKWh"] = None
                    fault_counts["NullEnergyReading"] += count_em

            # Negative energy
            cand_ne = df[df[key_col].notna() & df["EnergyKWh"].notna() & (df["EnergyKWh"] > 0)].index
            if len(cand_ne) > 0:
                prob = FAULT_CONFIG["negative_quantity"] / 2
                mask_ne = rng.random(len(cand_ne)) < prob
                ne_idx = cand_ne[mask_ne]
                count_ne = len(ne_idx)
                if count_ne > 0:
                    df.loc[ne_idx, "EnergyKWh"] = -abs(df.loc[ne_idx, "EnergyKWh"])
                    fault_counts["NegativeValue"] += count_ne

        elif fname == "FactSensor.csv":
            # Invalid sensor category
            if "SensorName" in df.columns:
                cand_sn = df[df[key_col].notna() & df["SensorName"].notna()].index
                if len(cand_sn) > 0:
                    prob = FAULT_CONFIG["invalid_category"] / 2
                    mask_sn = rng.random(len(cand_sn)) < prob
                    sn_idx = cand_sn[mask_sn]
                    count_sn = len(sn_idx)
                    if count_sn > 0:
                        df.loc[sn_idx, "SensorName"] = "INVALID_SENSOR_TYPE"
                        fault_counts["InvalidCategory"] += count_sn

        # Write faulty CSV
        df.to_csv(output_dir / fname, index=False)

    # Copy dimension tables unchanged (assumed clean references for validation)
    for dim in ["DimDate.csv", "DimShift.csv", "DimLine.csv", "DimMachine.csv", "DimProduct.csv", "DimReason.csv"]:
        src = input_dir / dim
        if src.exists():
            dst = output_dir / dim
            dst.write_bytes(src.read_bytes())

    # Save fault counts manifest for audit tracking
    manifest_path = output_dir / "fault_counts.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(fault_counts, f, indent=2)

    print(f"Fault injection completed. Faulty CSVs written to {output_dir}")
    return fault_counts


if __name__ == "__main__":
    inject_faults()
