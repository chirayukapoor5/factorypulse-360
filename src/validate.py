import pathlib
import pandas as pd

# Columns for the exception register (order matters for CSV export)
EXCEPTION_COLUMNS = [
    "ExceptionKey",
    "SourceTable",
    "RecordIdentifier",
    "RuleViolated",
    "Severity",
    "Disposition",
    "Description",
]

def _load_dimensions(raw_dir: pathlib.Path):
    dim_tables = {}
    for dim in ["DimDate", "DimShift", "DimLine", "DimMachine", "DimProduct", "DimReason"]:
        dim_tables[dim] = pd.read_csv(raw_dir / f"{dim}.csv")
    return dim_tables

def _validate_table(df: pd.DataFrame, table_name: str, pk_col: str, fk_map: dict, dim_tables: dict):
    """Validate a fact table and return good rows + a list of exception dicts.
    
    Parameters
    ----------
    df: DataFrame – fact table (may contain faulty rows).
    table_name: str – name of the source table.
    pk_col: str – primary‑key column name.
    fk_map: dict – foreign‑key column -> (dim_name, dim_key_col).
    dim_tables: dict – pre‑loaded dimension DataFrames.
    """
    exceptions = []
    good_mask = pd.Series(True, index=df.index)

    # 1. Duplicate primary keys
    dup_mask = df[pk_col].duplicated(keep=False)
    for idx in df[dup_mask].index:
        exceptions.append({
            "SourceTable": table_name,
            "RecordIdentifier": str(df.at[idx, pk_col]),
            "RuleViolated": "DuplicatePrimaryKey",
            "Severity": "High",
            "Disposition": "Quarantine",
            "Description": f"Primary key {df.at[idx, pk_col]} appears multiple times.",
        })
    good_mask &= ~dup_mask

    # 2. Orphaned foreign keys
    for fk_col, (dim_name, dim_key) in fk_map.items():
        valid_keys = set(dim_tables[dim_name][dim_key])
        orphan_mask = ~df[fk_col].isin(valid_keys)
        for idx in df[orphan_mask].index:
            exceptions.append({
                "SourceTable": table_name,
                "RecordIdentifier": str(df.at[idx, pk_col]),
                "RuleViolated": "OrphanForeignKey",
                "Severity": "High",
                "Disposition": "Quarantine",
                "Description": f"{fk_col} value {df.at[idx, fk_col]} not found in {dim_name}.",
            })
        good_mask &= ~orphan_mask

    # 3. Non‑negative numeric columns (units, minutes, kWh)
    numeric_cols = [c for c in df.columns if c.lower().endswith('units') or c.lower().endswith('minutes') or c.lower().endswith('kwh')]
    for col in numeric_cols:
        neg_mask = df[col] < 0
        for idx in df[neg_mask].index:
            exceptions.append({
                "SourceTable": table_name,
                "RecordIdentifier": str(df.at[idx, pk_col]),
                "RuleViolated": "NegativeValue",
                "Severity": "Medium",
                "Disposition": "Quarantine",
                "Description": f"Column {col} has negative value {df.at[idx, col]}.",
            })
        good_mask &= ~neg_mask

    # 4. Production unit consistency (specific to FactProduction)
    if table_name == "FactProduction":
        inc_mask = df['GoodUnits'] + df['RejectedUnits'] != df['ProducedUnits']
        for idx in df[inc_mask].index:
            exceptions.append({
                "SourceTable": table_name,
                "RecordIdentifier": str(df.at[idx, pk_col]),
                "RuleViolated": "UnitSumMismatch",
                "Severity": "Medium",
                "Disposition": "Quarantine",
                "Description": "GoodUnits + RejectedUnits does not equal ProducedUnits.",
            })
        good_mask &= ~inc_mask

    good_df = df[good_mask].copy()
    return good_df, exceptions

def run_validation():
    """Run validation on the faulty raw data.
    Writes curated fact CSVs to ``data/curated/`` and an exception register.
    Also creates a concise markdown report under ``docs/validation_report.md``.
    """
    base = pathlib.Path(__file__).resolve().parents[1]  # repository root
    raw_dir = base / "data" / "raw" / "faulty"
    curated_dir = base / "data" / "curated"
    curated_dir.mkdir(parents=True, exist_ok=True)

    # Load dimensions (assumed clean)
    dim_tables = _load_dimensions(raw_dir)

    # Fact table metadata: primary key and foreign‑key mappings
    fact_meta = {
        "FactProduction": {
            "pk": "ProductionKey",
            "fks": {
                "DateKey": ("DimDate", "DateKey"),
                "ShiftKey": ("DimShift", "ShiftKey"),
                "MachineKey": ("DimMachine", "MachineKey"),
                "ProductKey": ("DimProduct", "ProductKey"),
            },
        },
        "FactDowntime": {
            "pk": "DowntimeKey",
            "fks": {
                "DateKey": ("DimDate", "DateKey"),
                "ShiftKey": ("DimShift", "ShiftKey"),
                "MachineKey": ("DimMachine", "MachineKey"),
                "ReasonKey": ("DimReason", "ReasonKey"),
            },
        },
        "FactQuality": {
            "pk": "QualityKey",
            "fks": {
                "DateKey": ("DimDate", "DateKey"),
                "ShiftKey": ("DimShift", "ShiftKey"),
                "MachineKey": ("DimMachine", "MachineKey"),
                "ProductKey": ("DimProduct", "ProductKey"),
                "DefectReasonKey": ("DimReason", "ReasonKey"),
            },
        },
        "FactEnergy": {
            "pk": "EnergyKey",
            "fks": {
                "DateKey": ("DimDate", "DateKey"),
                "ShiftKey": ("DimShift", "ShiftKey"),
                "MachineKey": ("DimMachine", "MachineKey"),
            },
        },
        "FactSensor": {
            "pk": "SensorKey",
            "fks": {
                "DateKey": ("DimDate", "DateKey"),
                "MachineKey": ("DimMachine", "MachineKey"),
            },
        },
    }

    all_exceptions = []
    for fact_name, meta in fact_meta.items():
        df_raw = pd.read_csv(raw_dir / f"{fact_name}.csv")
        good_df, exc = _validate_table(df_raw, fact_name, meta["pk"], meta["fks"], dim_tables)
        # Export curated good rows
        good_df.to_csv(curated_dir / f"{fact_name}.csv", index=False)
        # Append exceptions (will be enriched later with ExceptionKey)
        for e in exc:
            e["ExceptionKey"] = None
        all_exceptions.extend(exc)

        # Build exception register DataFrame
    exc_df = pd.DataFrame(all_exceptions, columns=EXCEPTION_COLUMNS)
    # Ensure ExceptionKey is a sequential identifier
    if 'ExceptionKey' not in exc_df.columns:
        exc_df.insert(0, 'ExceptionKey', range(1, len(exc_df) + 1))
    else:
        exc_df['ExceptionKey'] = range(1, len(exc_df) + 1)
    exc_df.to_csv(curated_dir / 'FactDQExceptions.csv', index=False)


    # ---- Validation report ----
    report_path = base / "docs" / "validation_report.md"
    total_raw = sum(pd.read_csv(raw_dir / f"{t}.csv").shape[0] for t in fact_meta)
    total_curated = sum(pd.read_csv(curated_dir / f"{t}.csv").shape[0] for t in fact_meta)
    total_exc = len(exc_df)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Validation Report\n\n")
        f.write(f"- Raw fact records: {total_raw}\n")
        f.write(f"- Curated (accepted) records: {total_curated}\n")
        f.write(f"- Detected exceptions: {total_exc}\n\n")
        f.write("## Exceptions by rule\n\n")
        for rule, cnt in exc_df.groupby("RuleViolated").size().items():
            f.write(f"- {rule}: {cnt}\n")
    print(f"Validation complete – report written to {report_path}")

if __name__ == "__main__":
    run_validation()
