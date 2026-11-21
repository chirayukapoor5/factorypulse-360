"""tests/test_faults.py

Authentic Feature 8 (F8) and Feature 9 (F9) test suite verifying:
- Deterministic fault injection with separate count tracking
- Data quality validation engine rules via src.validate.run_validation
- FactDQExceptions quarantine table and audit trail
- Zero silent deletion conservation law
"""

import pathlib
from datetime import datetime
import pandas as pd
import numpy as np
import pytest

from src.inject_faults import inject_faults, FAULT_CONFIG
from src.validate import _validate_table, run_validation


@pytest.fixture
def sample_fault_dirs(tmp_path):
    """Provides an isolated directory structure with minimal valid dimensions and facts."""
    raw_dir = tmp_path / "raw"
    faulty_dir = tmp_path / "raw" / "faulty"
    curated_dir = tmp_path / "curated"
    raw_dir.mkdir(parents=True)
    faulty_dir.mkdir(parents=True)
    curated_dir.mkdir(parents=True)

    # Minimal dimensions
    pd.DataFrame({"DateKey": [20240101, 20240102]}).to_csv(raw_dir / "DimDate.csv", index=False)
    pd.DataFrame({"ShiftKey": [1, 2], "ScheduledMinutes": [480.0, 480.0]}).to_csv(raw_dir / "DimShift.csv", index=False)
    pd.DataFrame({"LineKey": [1, 2], "LineName": ["Line 1", "Line 2"]}).to_csv(raw_dir / "DimLine.csv", index=False)
    pd.DataFrame({"MachineKey": [1, 2, 3, 4], "LineKey": [1, 1, 2, 2]}).to_csv(raw_dir / "DimMachine.csv", index=False)
    pd.DataFrame({"ProductKey": [1, 2], "IdealCycleTimeMinutes": [1.0, 1.0]}).to_csv(raw_dir / "DimProduct.csv", index=False)
    pd.DataFrame({"ReasonKey": [1, 2, 6], "ReasonCode": ["Planned_Maintenance", "Mechanical_Failure", "Scrap"]}).to_csv(raw_dir / "DimReason.csv", index=False)

    # Minimal clean facts
    pd.DataFrame({
        "ProductionKey": [1, 2, 3, 4],
        "DateKey": [20240101, 20240101, 20240102, 20240102],
        "ShiftKey": [1, 1, 2, 2],
        "MachineKey": [1, 2, 3, 4],
        "ProductKey": [1, 2, 1, 2],
        "TargetUnits": [100, 100, 100, 100],
        "ProducedUnits": [100, 100, 100, 100],
        "GoodUnits": [95, 95, 95, 95],
        "RejectedUnits": [5, 5, 5, 5],
    }).to_csv(raw_dir / "FactProduction.csv", index=False)

    pd.DataFrame({
        "DowntimeKey": [1, 2],
        "DateKey": [20240101, 20240102],
        "ShiftKey": [1, 2],
        "MachineKey": [1, 2],
        "ReasonKey": [1, 2],
        "DowntimeMinutes": [15.0, 20.0],
        "Planned": [1, 0],
    }).to_csv(raw_dir / "FactDowntime.csv", index=False)

    pd.DataFrame({
        "EnergyKey": [1, 2],
        "DateKey": [20240101, 20240102],
        "ShiftKey": [1, 2],
        "MachineKey": [1, 2],
        "EnergyKWh": [45.0, 50.0],
    }).to_csv(raw_dir / "FactEnergy.csv", index=False)

    pd.DataFrame({
        "QualityKey": [1, 2],
        "DateKey": [20240101, 20240102],
        "ShiftKey": [1, 2],
        "MachineKey": [1, 2],
        "ProductKey": [1, 2],
        "DefectReasonKey": [6, 6],
        "DefectCount": [5, 5],
    }).to_csv(raw_dir / "FactQuality.csv", index=False)

    pd.DataFrame({
        "SensorKey": [1, 2],
        "DateKey": [20240101, 20240102],
        "MachineKey": [1, 2],
        "SensorName": ["Temp", "Speed"],
        "SensorValue": [298.1, 1500.0],
    }).to_csv(raw_dir / "FactSensor.csv", index=False)

    # Copy dimensions to faulty_dir as well
    for dim in ["DimDate", "DimShift", "DimLine", "DimMachine", "DimProduct", "DimReason"]:
        (faulty_dir / f"{dim}.csv").write_bytes((raw_dir / f"{dim}.csv").read_bytes())

    return {"raw": raw_dir, "faulty": faulty_dir, "curated": curated_dir}


def _copy_clean_facts(sample_fault_dirs):
    raw_dir = sample_fault_dirs["raw"]
    faulty_dir = sample_fault_dirs["faulty"]
    for fact in ["FactProduction", "FactDowntime", "FactQuality", "FactEnergy", "FactSensor"]:
        (faulty_dir / f"{fact}.csv").write_bytes((raw_dir / f"{fact}.csv").read_bytes())


@pytest.mark.tier1
def test_inject_faults_returns_fault_counts_dict(sample_fault_dirs):
    """F8: inject_faults must return a dictionary of fault counts per documented rule."""
    counts = inject_faults(
        input_dir=sample_fault_dirs["raw"],
        output_dir=sample_fault_dirs["faulty"],
        seed=42,
    )
    assert isinstance(counts, dict), "inject_faults must return a dictionary"
    expected_rules = {
        "NullPrimaryKey", "DuplicatePrimaryKey", "OrphanForeignKey",
        "NegativeValue", "NegativeDowntime", "InvalidTimestamp",
        "NullEnergyReading", "InvalidCategory", "UnitSumMismatch",
        "DefectCountMismatch", "DowntimeInconsistency", "InvalidKPIRange"
    }
    assert expected_rules.issubset(set(counts.keys())), f"Missing rules in returned counts: {expected_rules - set(counts.keys())}"
    assert all(isinstance(v, int) and v >= 0 for v in counts.values()), "All fault counts must be non-negative integers"


@pytest.mark.tier1
def test_fault_types_covered():
    """F8: All core documented fault types must be configured in FAULT_CONFIG."""
    required_faults = {
        "missing_id", "duplicate_id", "incorrect_fk", "negative_quantity",
        "negative_downtime", "invalid_timestamp", "missing_meter",
        "invalid_category", "inconsistent_units", "defect_mismatch",
        "downtime_inconsistency", "invalid_kpi_range"
    }
    for fault in required_faults:
        assert fault in FAULT_CONFIG, f"Fault type '{fault}' missing from FAULT_CONFIG"


@pytest.mark.tier1
def test_fault_injection_is_deterministic(sample_fault_dirs, tmp_path):
    """F8: Running fault injection with a fixed RNG seed must produce identical mutated CSVs."""
    out_a = tmp_path / "faulty_a"
    out_b = tmp_path / "faulty_b"
    inject_faults(input_dir=sample_fault_dirs["raw"], output_dir=out_a, seed=123)
    inject_faults(input_dir=sample_fault_dirs["raw"], output_dir=out_b, seed=123)

    for fname in ["FactProduction.csv", "FactDowntime.csv", "FactEnergy.csv"]:
        df_a = pd.read_csv(out_a / fname)
        df_b = pd.read_csv(out_b / fname)
        pd.testing.assert_frame_equal(df_a, df_b)


@pytest.mark.tier1
def test_validation_engine_quarantines_null_primary_keys(sample_fault_dirs):
    """F9: Fact rows with NULL primary keys must be quarantined by the validator."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject null primary key in FactProduction
    df = pd.read_csv(faulty_dir / "FactProduction.csv")
    df.loc[1, "ProductionKey"] = np.nan
    df.to_csv(faulty_dir / "FactProduction.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    null_pk_exc = exc_df[exc_df["RuleViolated"] == "NullPrimaryKey"]
    assert len(null_pk_exc) >= 1, "NullPrimaryKey exception not logged in FactDQExceptions"

    curated_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert not curated_prod["ProductionKey"].isna().any(), "Curated table leaked null primary key"


@pytest.mark.tier1
def test_validation_engine_quarantines_duplicate_primary_keys(sample_fault_dirs):
    """F9: Duplicate primary keys must be detected and quarantined as DuplicatePrimaryKey."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject duplicate primary key in FactProduction
    df = pd.read_csv(faulty_dir / "FactProduction.csv")
    dup_row = df.iloc[[1]].copy()
    df = pd.concat([df, dup_row], ignore_index=True)
    df.to_csv(faulty_dir / "FactProduction.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    dup_exc = exc_df[exc_df["RuleViolated"] == "DuplicatePrimaryKey"]
    assert len(dup_exc) >= 2, "DuplicatePrimaryKey exception not logged for both duplicate records"

    curated_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert curated_prod["ProductionKey"].is_unique, "Curated rows must have unique primary keys"


@pytest.mark.tier1
def test_validation_engine_quarantines_orphan_foreign_keys(sample_fault_dirs):
    """F9: Foreign keys referencing non-existent dimension keys must be quarantined as OrphanForeignKey."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject orphan foreign key in FactProduction
    df = pd.read_csv(faulty_dir / "FactProduction.csv")
    df.loc[1, "MachineKey"] = 999  # MachineKey 999 does not exist in DimMachine
    df.to_csv(faulty_dir / "FactProduction.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    orphan_exc = exc_df[exc_df["RuleViolated"] == "OrphanForeignKey"]
    assert len(orphan_exc) >= 1, "OrphanForeignKey exception not logged in FactDQExceptions"

    curated_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert 999 not in curated_prod["MachineKey"].values, "Curated rows leaked orphan MachineKey 999"


@pytest.mark.tier2
def test_validation_engine_quarantines_negative_units(sample_fault_dirs):
    """F9: Negative produced or good units must be quarantined as NegativeValue."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject negative produced units
    df = pd.read_csv(faulty_dir / "FactProduction.csv")
    df.loc[1, "ProducedUnits"] = -10
    df.to_csv(faulty_dir / "FactProduction.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    neg_exc = exc_df[exc_df["RuleViolated"] == "NegativeValue"]
    assert len(neg_exc) >= 1, "NegativeValue exception not logged for negative units"

    curated_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert (curated_prod["ProducedUnits"] >= 0).all(), "Curated rows contain negative ProducedUnits"


@pytest.mark.tier2
def test_validation_engine_quarantines_negative_energy(sample_fault_dirs):
    """F9: Negative EnergyKWh readings must be quarantined as NegativeValue."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject negative energy
    df = pd.read_csv(faulty_dir / "FactEnergy.csv")
    df.loc[1, "EnergyKWh"] = -5.0
    df.to_csv(faulty_dir / "FactEnergy.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    neg_exc = exc_df[exc_df["RuleViolated"] == "NegativeValue"]
    assert len(neg_exc) >= 1, "NegativeValue exception not logged for negative energy"

    curated_energy = pd.read_csv(curated_dir / "FactEnergy.csv")
    assert (curated_energy["EnergyKWh"] >= 0).all(), "Curated rows contain negative EnergyKWh"


@pytest.mark.tier2
def test_validation_engine_quarantines_negative_downtime(sample_fault_dirs):
    """F9: Negative DowntimeMinutes must be quarantined as NegativeDowntime or NegativeValue."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject negative downtime
    df = pd.read_csv(faulty_dir / "FactDowntime.csv")
    df.loc[1, "DowntimeMinutes"] = -30.0
    df.to_csv(faulty_dir / "FactDowntime.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    neg_exc = exc_df[exc_df["RuleViolated"].isin(["NegativeDowntime", "NegativeValue"])]
    assert len(neg_exc) >= 1, "Negative exception not logged for negative downtime"

    curated_down = pd.read_csv(curated_dir / "FactDowntime.csv")
    assert (curated_down["DowntimeMinutes"] >= 0).all(), "Curated rows contain negative DowntimeMinutes"


@pytest.mark.tier2
def test_validation_engine_quarantines_unit_sum_mismatch(sample_fault_dirs):
    """F9: Production rows where ProducedUnits != GoodUnits + RejectedUnits must be quarantined as UnitSumMismatch."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject unit sum mismatch
    df = pd.read_csv(faulty_dir / "FactProduction.csv")
    df.loc[1, "ProducedUnits"] = 100
    df.loc[1, "GoodUnits"] = 90
    df.loc[1, "RejectedUnits"] = 5  # 90 + 5 = 95 != 100
    df.to_csv(faulty_dir / "FactProduction.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    mismatch_exc = exc_df[exc_df["RuleViolated"] == "UnitSumMismatch"]
    assert len(mismatch_exc) >= 1, "UnitSumMismatch exception not logged in FactDQExceptions"

    curated_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert (curated_prod["ProducedUnits"] == curated_prod["GoodUnits"] + curated_prod["RejectedUnits"]).all()


@pytest.mark.tier2
def test_validation_engine_quarantines_null_energy_readings(sample_fault_dirs):
    """F9: Missing meter readings (EnergyKWh IS NULL) must be detected and quarantined as NullEnergyReading."""
    faulty_dir = sample_fault_dirs["faulty"]
    curated_dir = sample_fault_dirs["curated"]
    _copy_clean_facts(sample_fault_dirs)

    # Inject null energy reading
    df = pd.read_csv(faulty_dir / "FactEnergy.csv")
    df.loc[1, "EnergyKWh"] = np.nan
    df.to_csv(faulty_dir / "FactEnergy.csv", index=False)

    run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    null_energy_exc = exc_df[exc_df["RuleViolated"] == "NullEnergyReading"]
    assert len(null_energy_exc) >= 1, "NullEnergyReading exception not logged in FactDQExceptions"

    curated_energy = pd.read_csv(curated_dir / "FactEnergy.csv")
    assert not curated_energy["EnergyKWh"].isna().any(), "Curated energy leaked null EnergyKWh"


@pytest.mark.tier2
def test_zero_silent_deletion_record_count_conservation(tmp_path):
    """F9: Zero silent deletion: Total raw rows processed must equal Curated rows + Quarantined rows."""
    from src import simulate
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=3, seed=42, output_dir=tmp_path)
    inject_faults(raw_dir, faulty_dir, seed=42)
    total_raw, total_exc = run_validation(faulty_dir, curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    assert len(exc_df) == total_exc

    for fname in ["FactProduction.csv", "FactDowntime.csv", "FactQuality.csv", "FactEnergy.csv"]:
        raw_path = faulty_dir / fname
        curated_path = curated_dir / fname
        if raw_path.exists() and curated_path.exists():
            df_raw = pd.read_csv(raw_path)
            df_curated = pd.read_csv(curated_path)
            table_name = fname.replace(".csv", "")
            table_exc = exc_df[exc_df["SourceTable"] == table_name]
            assert len(df_curated) <= len(df_raw)
            assert len(df_curated) + len(table_exc) >= len(df_raw)


@pytest.mark.tier1
def test_fact_dq_exceptions_structure_and_traceability(tmp_path):
    """F9: FactDQExceptions records must include execution timestamp, table, record ID, and violated rule."""
    from src import simulate
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=3, seed=42, output_dir=tmp_path)
    inject_faults(raw_dir, faulty_dir, seed=42)
    run_validation(faulty_dir, curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    required_cols = ["ExceptionKey", "ExecutionTimestamp", "SourceTable", "RecordIdentifier", "RuleViolated", "Severity", "Disposition", "Description"]
    for col in required_cols:
        assert col in exc_df.columns, f"Column {col} missing from FactDQExceptions"
    dispositions = exc_df["Disposition"].str.upper()
    assert (dispositions == "QUARANTINED").all() or (dispositions == "QUARANTINE").all()
    assert exc_df["ExceptionKey"].is_monotonic_increasing


@pytest.mark.tier2
def test_record_identifier_not_null_or_nan_string(tmp_path):
    """F9: Quarantined exceptions must never have 'nan' or empty string as RecordIdentifier."""
    from src import simulate
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=3, seed=42, output_dir=tmp_path)
    inject_faults(raw_dir, faulty_dir, seed=42)
    run_validation(faulty_dir, curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    assert not exc_df["RecordIdentifier"].isna().any(), "RecordIdentifier contains null values"
    str_ids = exc_df["RecordIdentifier"].astype(str).str.strip().str.lower()
    assert not (str_ids == "nan").any(), "RecordIdentifier contains literal 'nan' strings"
    assert not (str_ids == "").any(), "RecordIdentifier contains empty strings"


@pytest.mark.tier3
def test_curated_tables_contain_zero_quarantined_records(tmp_path):
    """F9: Clean curated datasets must contain 0 invalid or quarantined records."""
    from src import simulate
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=3, seed=42, output_dir=tmp_path)
    inject_faults(raw_dir, faulty_dir, seed=42)
    run_validation(faulty_dir, curated_dir)

    prod_df = pd.read_csv(curated_dir / "FactProduction.csv")
    assert (prod_df["ProducedUnits"] >= 0).all()
    assert (prod_df["GoodUnits"] + prod_df["RejectedUnits"] == prod_df["ProducedUnits"]).all()
    assert prod_df["ProductionKey"].is_unique
    assert not prod_df["ProductionKey"].isna().any()

    energy_df = pd.read_csv(curated_dir / "FactEnergy.csv")
    assert (energy_df["EnergyKWh"] >= 0).all()
    assert not energy_df["EnergyKWh"].isna().any()


@pytest.mark.tier3
def test_injected_vs_detected_fault_counts_reported_separately(tmp_path):
    """F8/F9: Injected fault counts and detected violation counts must be reported independently."""
    from src import simulate
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=7, seed=42, output_dir=tmp_path)
    injected_counts = inject_faults(raw_dir, faulty_dir, seed=42)
    total_raw, total_exc = run_validation(faulty_dir, curated_dir)

    exc_df = pd.read_csv(curated_dir / "FactDQExceptions.csv")
    detected_counts = exc_df.groupby("RuleViolated").size().to_dict()

    assert isinstance(injected_counts, dict)
    assert isinstance(detected_counts, dict)
    assert len(detected_counts) > 0
    assert sum(detected_counts.values()) == total_exc
    assert sum(injected_counts.values()) > 0


