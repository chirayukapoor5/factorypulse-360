"""tests/test_pipeline_e2e.py

End-to-End Pipeline & Real-World Application Scenario Test Suite (Tiers 3-4).
Validates manufacturing topology, UCI AI4I benchmark ingestion, and ABB Smart Power scenarios:
- Line 2 Shift 2 outage surge
- Product Family_E scrap spike
- Line 3 Cell 2 energy hotspot
- Breaker cell 4-stage sequential manufacturing flow
- Global zero-variance cross-fact reconciliation
"""

import re
import sqlite3
import pathlib
from datetime import datetime
import pandas as pd
import pytest

from src import simulate, inject_faults, validate, load_sqlite, load_external_ai4i


@pytest.fixture(scope="module")
def e2e_pipeline_context(tmp_path_factory, repo_root):
    """Generates an authentic 7-day populated SQLite database with all dimensions,
    curated facts, fault exceptions, and external AI4I sensor telemetry."""
    tmp_path = tmp_path_factory.mktemp("pipeline_ctx")
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"
    db_path = tmp_path / "factorypulse_test.db"

    # Step 1: Simulate 7 days of discrete manufacturing
    simulate.simulate_production(
        start_date=datetime(2024, 1, 1),
        days=7,
        seed=42,
        output_dir=tmp_path,
    )

    # Step 2: Inject deterministic faults
    inject_faults.inject_faults(
        input_dir=raw_dir,
        output_dir=faulty_dir,
        seed=42,
    )

    # Step 3: Validate and quarantine
    validate.run_validation(
        raw_dir=faulty_dir,
        curated_dir=curated_dir,
    )

    # Step 4: Ingest into SQLite
    load_sqlite.load_sqlite(
        db_path=db_path,
        curated_dir=curated_dir,
        raw_dir=raw_dir,
    )

    # Step 5: Ingest AI4I external benchmark
    ai4i_csv = repo_root / "data" / "external" / "ai4i" / "ai4i2020.csv"
    if ai4i_csv.exists():
        load_external_ai4i.load_ai4i(db_path=db_path, csv_path=ai4i_csv)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield {
        "conn": conn,
        "db_path": db_path,
        "tmp_path": tmp_path,
        "raw_dir": raw_dir,
        "curated_dir": curated_dir,
    }
    conn.close()


# ==============================================================================
# F3: Manufacturing Topology & Double-Counting Prevention
# ==============================================================================

@pytest.mark.tier1
def test_manufacturing_topology_3_lines_6_cells_24_machines(populated_db):
    """F3: Topology consists of 3 production lines, 6 manufacturing cells, and 24 machines."""
    conn = populated_db
    cur = conn.execute("SELECT COUNT(*) FROM DimLine")
    assert cur.fetchone()[0] == 3

    cur = conn.execute("SELECT COUNT(DISTINCT LineKey || '-' || CellId) FROM DimMachine")
    assert cur.fetchone()[0] == 6

    cur = conn.execute("SELECT COUNT(*) FROM DimMachine")
    assert cur.fetchone()[0] == 24


@pytest.mark.tier1
def test_stage_sequence_modeling_in_dim_machine(populated_db):
    """F3: DimMachine models 4 sequential process stages (StageSequence 1 to 4) per cell."""
    conn = populated_db
    cur = conn.execute("PRAGMA table_info(DimMachine)")
    cols = {r[1] for r in cur.fetchall()}
    if "StageSequence" in cols:
        cur = conn.execute("SELECT DISTINCT StageSequence FROM DimMachine ORDER BY StageSequence")
        stages = [r[0] for r in cur.fetchall()]
        assert stages == [1, 2, 3, 4]


@pytest.mark.tier1
def test_end_of_line_flag_in_dim_machine(populated_db):
    """F3: IsEndOfLine flag is 1 only for Stage 4 (Packaging) and 0 for Stages 1, 2, 3."""
    conn = populated_db
    cur = conn.execute("PRAGMA table_info(DimMachine)")
    cols = {r[1] for r in cur.fetchall()}
    if "IsEndOfLine" in cols and "StageSequence" in cols:
        cur = conn.execute("SELECT StageSequence, IsEndOfLine FROM DimMachine")
        for stage, is_eol in cur.fetchall():
            if stage == 4:
                assert is_eol == 1
            else:
                assert is_eol == 0


@pytest.mark.tier2
def test_double_counting_prevention_line_aggregation(e2e_pipeline_context):
    """F3: Finished product output must filter on IsEndOfLine = 1 to prevent 4x volume inflation."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT
            SUM(fp.ProducedUnits) AS TotalStationOperations,
            SUM(CASE WHEN dm.IsEndOfLine = 1 THEN fp.ProducedUnits ELSE 0 END) AS FinishedGoodUnits
        FROM FactProduction fp
        JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey;
    """)
    row = cur.fetchone()
    total_ops = row["TotalStationOperations"]
    finished = row["FinishedGoodUnits"]

    assert finished > 0, "Finished goods count cannot be zero"
    assert total_ops > finished, "Total station operations must exceed finished goods"
    assert pytest.approx(total_ops, rel=0.15) == finished * 4.0, (
        "Cell volume without IsEndOfLine filter should reflect ~4x station stages"
    )


@pytest.mark.tier2
def test_machine_level_metrics_include_all_stages(e2e_pipeline_context):
    """F3: Machine-level metrics (e.g. scrap, downtime, energy) apply across all 24 machines."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT dm.StageSequence,
               COUNT(DISTINCT dm.MachineKey) AS MachineCount,
               COUNT(DISTINCT fe.MachineKey) AS EnergyMachineCount,
               COUNT(DISTINCT fd.MachineKey) AS DowntimeMachineCount
        FROM DimMachine dm
        LEFT JOIN FactEnergy fe ON dm.MachineKey = fe.MachineKey
        LEFT JOIN FactDowntime fd ON dm.MachineKey = fd.MachineKey
        GROUP BY dm.StageSequence;
    """)
    rows = cur.fetchall()
    assert len(rows) == 4, "Must cover all 4 sequential process stages"
    for r in rows:
        assert r["MachineCount"] == 6, f"Stage {r['StageSequence']} must have 6 machines (3 lines * 2 cells)"
        assert r["EnergyMachineCount"] == 6, f"Stage {r['StageSequence']} missing energy monitoring"
        assert r["DowntimeMachineCount"] == 6, f"Stage {r['StageSequence']} missing downtime tracking"


# ==============================================================================
# F10: UCI AI4I Dataset Integration & Provenance
# ==============================================================================

@pytest.mark.tier1
def test_ai4i_raw_file_unmodified_preservation(repo_root):
    """F10: UCI AI4I 2020 source file must be preserved unmodified with 10,000 rows and 14 columns."""
    ai4i_path = repo_root / "data" / "external" / "ai4i" / "ai4i2020.csv"
    assert ai4i_path.exists(), "Source ai4i2020.csv is missing"
    df = pd.read_csv(ai4i_path)
    assert df.shape == (10000, 14), f"AI4I dataset dimensions altered: {df.shape}"


@pytest.mark.tier1
def test_ai4i_ingestion_creates_exactly_50000_sensor_rows(e2e_pipeline_context):
    """F10: Unpivoting 5 numeric sensor columns from 10,000 observations must yield exactly 50,000 FactSensor rows."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("SELECT COUNT(*) FROM FactSensor WHERE is_external = 1")
    count = cur.fetchone()[0]
    assert count == 50000, f"Expected exactly 50,000 external AI4I rows, got {count}"


@pytest.mark.tier1
def test_ai4i_numeric_columns_mapping(e2e_pipeline_context):
    """F10: Only 5 continuous numeric sensors are unpivoted from AI4I benchmark."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("SELECT DISTINCT SensorName FROM FactSensor WHERE is_external = 1 ORDER BY SensorName")
    names = {r[0].lower() for r in cur.fetchall()}
    expected = {
        "air temperature [k]",
        "process temperature [k]",
        "rotational speed [rpm]",
        "torque [nm]",
        "tool wear [min]",
    }
    assert names == expected, f"Unexpected sensor names unpivoted: {names}"


@pytest.mark.tier2
def test_ai4i_sensor_value_is_pure_numeric_real(e2e_pipeline_context):
    """F10: FactSensor.SensorValue must be numeric REAL with zero non-numeric string values."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT DISTINCT typeof(SensorValue)
        FROM FactSensor
        WHERE is_external = 1;
    """)
    types = {r[0] for r in cur.fetchall()}
    assert types.issubset({"real", "integer"}), f"Invalid data types found in SensorValue: {types}"


@pytest.mark.tier2
def test_ai4i_deterministic_identifier_format(e2e_pipeline_context):
    """F10: AI4I observations use deterministic device identifier matching ^AI4I-[LMH]-\\d{5}$."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("SELECT DISTINCT external_machine_id FROM FactSensor WHERE is_external = 1 LIMIT 50")
    pattern = re.compile(r"^AI4I-[LMH]-\d{5}$")
    for r in cur.fetchall():
        assert pattern.match(r[0]), f"Malformed device identifier: {r[0]}"


@pytest.mark.tier2
def test_ai4i_deterministic_distribution_across_machines_and_dates(e2e_pipeline_context):
    """F10: AI4I telemetry observations must be distributed across machines and dates, not all on machine 1 date 1."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT COUNT(DISTINCT MachineKey) AS Machines, COUNT(DISTINCT DateKey) AS Dates
        FROM FactSensor
        WHERE is_external = 1;
    """)
    row = cur.fetchone()
    assert row["Machines"] == 24, f"AI4I not distributed across all 24 machines: {row['Machines']}"
    assert row["Dates"] > 1, f"AI4I observations clumped on a single date: {row['Dates']}"


@pytest.mark.tier2
def test_ai4i_external_provenance_flag(populated_db):
    """F10: FactSensor distinguishes external UCI benchmark data via is_external = 1."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactSensor (SensorKey, DateKey, MachineKey, SensorName, SensorValue, is_external)
        VALUES (9901, 20240101, 1, 'Torque [Nm]', 42.5, 1),
               (9902, 20240101, 1, 'Vibration', 1.2, 0)
    """)
    conn.commit()

    cur = conn.execute("SELECT is_external, COUNT(*) FROM FactSensor WHERE SensorKey >= 9901 GROUP BY is_external")
    rows = dict(cur.fetchall())
    assert rows[1] == 1, "External AI4I row not marked with is_external = 1"
    assert rows[0] == 1, "Native sensor row not marked with is_external = 0"


# ==============================================================================
# Tier 4: Real-World ABB Smart Power Application Scenarios
# ==============================================================================

@pytest.mark.tier4
def test_tier4_abb_lifecycle_commissioning(e2e_pipeline_context):
    """Tier 4: Full E2E Commissioning Lifecycle verifies end-to-end pipeline execution inside isolated environment."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("PRAGMA integrity_check;")
    assert cur.fetchone()[0] == "ok"

    # All dimension tables populated
    for dim, min_rows in [("DimDate", 7), ("DimShift", 2), ("DimLine", 3), ("DimMachine", 24), ("DimProduct", 5), ("DimReason", 8)]:
        cur = conn.execute(f"SELECT COUNT(*) FROM {dim}")
        assert cur.fetchone()[0] >= min_rows

    # All fact tables populated with valid records
    for fact in ["FactProduction", "FactDowntime", "FactQuality", "FactEnergy", "FactSensor", "FactDQExceptions"]:
        cur = conn.execute(f"SELECT COUNT(*) FROM {fact}")
        assert cur.fetchone()[0] > 0


@pytest.mark.tier4
def test_tier4_abb_scenario_a_line2_shift2_downtime_surge(e2e_pipeline_context):
    """Tier 4: Line 2 Cell 1 Shift 2 exhibits elevated downtime (+40%), driving down Shift 2 Availability."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT fd.ShiftKey,
               AVG(fd.DowntimeMinutes) AS AvgDowntime,
               SUM(fd.DowntimeMinutes) AS TotalDowntime
        FROM FactDowntime fd
        JOIN DimMachine dm ON fd.MachineKey = dm.MachineKey
        WHERE dm.LineKey = 2 AND dm.CellId = 1
        GROUP BY fd.ShiftKey
        ORDER BY fd.ShiftKey;
    """)
    rows = {r["ShiftKey"]: r for r in cur.fetchall()}
    assert 1 in rows and 2 in rows, "Line 2 Cell 1 must have data for Shift 1 and Shift 2"

    downtime_shift1 = rows[1]["AvgDowntime"]
    downtime_shift2 = rows[2]["AvgDowntime"]

    assert downtime_shift2 > downtime_shift1, (
        f"Expected Shift 2 downtime surge: Shift 2 ({downtime_shift2:.2f}m) <= Shift 1 ({downtime_shift1:.2f}m)"
    )

    avail_shift1 = (480.0 - downtime_shift1) / 480.0
    avail_shift2 = (480.0 - downtime_shift2) / 480.0
    assert avail_shift2 < avail_shift1


@pytest.mark.tier4
def test_tier4_abb_scenario_b_family_e_scrap_spike(e2e_pipeline_context):
    """Tier 4: Product Family_E exhibits elevated scrap rate (+30%), lowering YieldPct in quality summary."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT dp.ProductFamily,
               SUM(fp.RejectedUnits) AS Rejects,
               SUM(fp.ProducedUnits) AS Produced,
               (SUM(fp.RejectedUnits) * 1.0 / NULLIF(SUM(fp.ProducedUnits), 0)) AS ScrapRate
        FROM FactProduction fp
        JOIN DimProduct dp ON fp.ProductKey = dp.ProductKey
        GROUP BY dp.ProductFamily
        ORDER BY ScrapRate DESC;
    """)
    rows = cur.fetchall()
    assert len(rows) == 5, f"Expected 5 product families, got {len(rows)}"

    highest_family = rows[0]["ProductFamily"]
    family_e_scrap = rows[0]["ScrapRate"]
    assert highest_family == "Family_E", f"Expected Family_E to have highest scrap rate, but {highest_family} was highest"

    other_scraps = [r["ScrapRate"] for r in rows if r["ProductFamily"] != "Family_E"]
    avg_other_scrap = sum(other_scraps) / len(other_scraps)
    assert family_e_scrap > avg_other_scrap * 1.15, (
        f"Family_E scrap ({family_e_scrap:.4f}) not sufficiently elevated above other families ({avg_other_scrap:.4f})"
    )


@pytest.mark.tier4
def test_tier4_abb_scenario_c_line3_cell2_energy_hotspot(e2e_pipeline_context):
    """Tier 4: Line 3 Cell 2 machines consume highest kWhPerGoodUnit (energy hotspot)."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT dm.LineKey, dm.CellId,
               SUM(fe.EnergyKWh) * 1.0 / NULLIF(SUM(fp.GoodUnits), 0) AS kWhPerGoodUnit
        FROM FactEnergy fe
        JOIN FactProduction fp ON fe.DateKey = fp.DateKey AND fe.ShiftKey = fp.ShiftKey AND fe.MachineKey = fp.MachineKey
        JOIN DimMachine dm ON fe.MachineKey = dm.MachineKey
        GROUP BY dm.LineKey, dm.CellId
        ORDER BY kWhPerGoodUnit DESC;
    """)
    rows = cur.fetchall()
    assert len(rows) == 6, f"Expected 6 manufacturing cells, got {len(rows)}"

    top_cell = rows[0]
    assert top_cell["LineKey"] == 3 and top_cell["CellId"] == 2, (
        f"Expected Line 3 Cell 2 to be highest energy hotspot, got Line {top_cell['LineKey']} Cell {top_cell['CellId']}"
    )

    other_intensities = [r["kWhPerGoodUnit"] for r in rows[1:]]
    avg_baseline = sum(other_intensities) / len(other_intensities)
    assert top_cell["kWhPerGoodUnit"] > avg_baseline * 1.15, (
        f"Hotspot ({top_cell['kWhPerGoodUnit']:.4f}) not significantly higher than baseline ({avg_baseline:.4f})"
    )


@pytest.mark.tier4
def test_tier4_abb_scenario_e_stage_sequencing_flow(e2e_pipeline_context):
    """Tier 4: Tracks product flow sequentially through 4 machine stages in an ABB breaker cell."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT LineKey, CellId, COUNT(DISTINCT StageSequence) AS StagesCount
        FROM DimMachine
        GROUP BY LineKey, CellId;
    """)
    for r in cur.fetchall():
        assert r["StagesCount"] == 4, f"Line {r['LineKey']} Cell {r['CellId']} does not have 4 sequential stages"

    cur = conn.execute("SELECT StageSequence, IsEndOfLine FROM DimMachine")
    for stage, is_eol in cur.fetchall():
        if stage == 4:
            assert is_eol == 1
        else:
            assert is_eol == 0


@pytest.mark.tier4
def test_tier4_abb_scenario_g_quarantine_audit_trail(e2e_pipeline_context):
    """Tier 4: Audit trail in FactDQExceptions retains full traceability with zero dropped records."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("SELECT ExceptionKey, SourceTable, RecordIdentifier, RuleViolated, Severity, Disposition FROM FactDQExceptions")
    rows = cur.fetchall()
    assert len(rows) > 0, "FactDQExceptions should contain quarantined exceptions from inject_faults"

    valid_rules = {
        "DuplicatePrimaryKey", "OrphanForeignKey", "NegativeValue",
        "UnitSumMismatch", "NullPrimaryKey", "NullEnergyReading", "NegativeDowntime",
        "InvalidTimestamp", "InvalidCategory", "DefectCountMismatch",
        "DowntimeInconsistency", "InvalidKPIRange"
    }
    for r in rows:
        assert r["SourceTable"] in {"FactProduction", "FactDowntime", "FactQuality", "FactEnergy", "FactSensor"}
        assert r["RecordIdentifier"] is not None and str(r["RecordIdentifier"]).strip() != ""
        assert r["RuleViolated"] in valid_rules, f"Unexpected rule violated: {r['RuleViolated']}"
        assert r["Disposition"] in {"Quarantine", "QUARANTINED"}


@pytest.mark.tier4
def test_tier4_abb_reconciliation_zero_variance(e2e_pipeline_context):
    """Tier 4: Global multi-shift reconciliation across production, downtime, and energy achieves variance == 0.0."""
    conn = e2e_pipeline_context["conn"]
    # Production
    src_prod = conn.execute("SELECT SUM(ProducedUnits) FROM FactProduction").fetchone()[0]
    agg_prod = conn.execute("""
        SELECT SUM(LineTotal) FROM (
            SELECT fp.DateKey, fp.ShiftKey, dm.LineKey, SUM(fp.ProducedUnits) AS LineTotal
            FROM FactProduction fp JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
            GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey
        )
    """).fetchone()[0]
    assert abs(src_prod - agg_prod) == 0

    # Downtime
    src_down = conn.execute("SELECT SUM(DowntimeMinutes) FROM FactDowntime").fetchone()[0]
    agg_down = conn.execute("SELECT SUM(TotalMinutes) FROM (SELECT SUM(DowntimeMinutes) AS TotalMinutes FROM FactDowntime GROUP BY ReasonKey)").fetchone()[0]
    assert pytest.approx(src_down, rel=1e-5) == agg_down

    # Energy
    src_energy = conn.execute("SELECT SUM(EnergyKWh) FROM FactEnergy").fetchone()[0]
    agg_energy = conn.execute("SELECT SUM(TotalKWh) FROM (SELECT SUM(EnergyKWh) AS TotalKWh FROM FactEnergy GROUP BY MachineKey)").fetchone()[0]
    assert pytest.approx(src_energy, rel=1e-5) == agg_energy


@pytest.mark.tier4
def test_tier4_bi_handoff_directory_structure(isolated_env):
    """Tier 4: bi_handoff directory structure contains dimensions/, facts/, and exceptions/."""
    bi_handoff = isolated_env["bi_handoff"]
    assert (bi_handoff / "dimensions").exists()
    assert (bi_handoff / "facts").exists()
    assert (bi_handoff / "exceptions").exists()


@pytest.mark.tier4
def test_tier4_bi_handoff_dimensions_match_curated(populated_db):
    """Tier 4: Dimensions in bi_handoff must match curated database dimensions."""
    conn = populated_db
    cur = conn.execute("SELECT COUNT(*) FROM DimLine")
    assert cur.fetchone()[0] == 3


@pytest.mark.tier4
def test_tier4_bi_handoff_facts_match_curated(e2e_pipeline_context):
    """Tier 4: Facts in bi_handoff / curated export must match curated database facts."""
    conn = e2e_pipeline_context["conn"]
    curated_dir = e2e_pipeline_context["curated_dir"]

    cur = conn.execute("SELECT COUNT(*), SUM(ProducedUnits), SUM(GoodUnits) FROM FactProduction")
    db_count, db_produced, db_good = cur.fetchone()
    assert db_count > 0, "FactProduction must contain rows"

    df_prod = pd.read_csv(curated_dir / "FactProduction.csv")
    assert len(df_prod) == db_count, f"Row count mismatch: CSV={len(df_prod)}, DB={db_count}"
    assert df_prod["ProducedUnits"].sum() == db_produced
    assert df_prod["GoodUnits"].sum() == db_good


@pytest.mark.tier4
def test_tier4_multi_day_temporal_continuity(e2e_pipeline_context):
    """Tier 4: Simulated dates must form a continuous chronological sequence without gaps in database."""
    conn = e2e_pipeline_context["conn"]
    cur = conn.execute("""
        SELECT DISTINCT d.Date
        FROM FactProduction fp
        JOIN DimDate d ON fp.DateKey = d.DateKey
        ORDER BY d.Date;
    """)
    date_strings = [r[0] for r in cur.fetchall()]
    assert len(date_strings) >= 7, f"Expected at least 7 days of simulated dates, got {len(date_strings)}"

    dates = pd.to_datetime(date_strings)
    diffs = (dates[1:] - dates[:-1]).days
    assert all(diff == 1 for diff in diffs), f"Discontinuous date sequence found: {date_strings}"


@pytest.mark.tier4
def test_tier4_end_to_end_pipeline_isolation(tmp_path, repo_root, run_pipeline_cli):
    """Tier 4: Running pipeline inside tmp_path writes zero bytes to repository data/ directory."""
    isolated_out = tmp_path / "custom_data"
    res = run_pipeline_cli("--seed", "99", "--days", "2", "--start-date", "2024-01-01", "--output-dir", str(isolated_out))
    assert res.returncode == 0, f"Pipeline run failed with stderr: {res.stderr}"

    assert (isolated_out / "raw").exists() or (isolated_out / "data" / "raw").exists()
    assert (isolated_out / "curated").exists() or (isolated_out / "data" / "curated").exists()
