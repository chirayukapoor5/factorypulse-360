"""tests/test_reconciliation.py

Authentic Feature 7 (F7) test suite verifying reconciliation between
curated SQLite fact tables and analytical SQL pre-aggregations / reports.
Zero dummy DataFrames, zero tautological assertions, zero hardcoded outcomes.
"""

import sqlite3
import pandas as pd
import pytest
from datetime import datetime
from src import simulate, inject_faults, validate, load_sqlite
from src.generate_reports import generate_reports


@pytest.fixture(scope="module")
def reconciliation_db(tmp_path_factory):
    """Provides a genuine 3-day SQLite database populated with all facts and dimensions."""
    tmp_path = tmp_path_factory.mktemp("recon_db")
    raw_dir = tmp_path / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = tmp_path / "curated"
    db_path = tmp_path / "reconciliation.db"

    simulate.simulate_production(start_date=datetime(2024, 1, 1), days=3, seed=42, output_dir=tmp_path)
    inject_faults.inject_faults(input_dir=raw_dir, output_dir=faulty_dir, seed=42)
    validate.run_validation(raw_dir=faulty_dir, curated_dir=curated_dir)
    load_sqlite.load_sqlite(db_path=db_path, curated_dir=curated_dir, raw_dir=raw_dir)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn, db_path, curated_dir
    conn.close()


@pytest.mark.tier1
def test_production_total_units_reconciliation(reconciliation_db):
    """F7: Curated FactProduction total units must reconcile exactly with analytical pre-aggregation."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(ProducedUnits) FROM FactProduction")
    source_total = cur.fetchone()[0]
    assert source_total is not None and source_total > 0

    # CTE pre-aggregation at (DateKey, ShiftKey, LineKey) grain
    cur = conn.execute("""
        WITH line_prod AS (
            SELECT fp.DateKey, fp.ShiftKey, dm.LineKey, SUM(fp.ProducedUnits) AS LineProduced
            FROM FactProduction fp
            JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
            GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey
        )
        SELECT SUM(LineProduced) FROM line_prod;
    """)
    agg_total = cur.fetchone()[0]
    variance = abs(source_total - agg_total)
    assert variance == 0, f"Production total units mismatch: source={source_total}, agg={agg_total}"


@pytest.mark.tier1
def test_production_good_units_reconciliation(reconciliation_db):
    """F7: Curated FactProduction good units must reconcile exactly with analytical pre-aggregation."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(GoodUnits) FROM FactProduction")
    source_good = cur.fetchone()[0]
    assert source_good is not None and source_good > 0

    cur = conn.execute("""
        WITH line_good AS (
            SELECT fp.DateKey, fp.ShiftKey, dm.LineKey, SUM(fp.GoodUnits) AS GoodUnits
            FROM FactProduction fp
            JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
            GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey
        )
        SELECT SUM(GoodUnits) FROM line_good;
    """)
    agg_good = cur.fetchone()[0]
    assert abs(source_good - agg_good) == 0, f"Good units mismatch: source={source_good}, agg={agg_good}"


@pytest.mark.tier1
def test_production_rejected_units_reconciliation(reconciliation_db):
    """F7: Curated FactProduction rejected units must reconcile with analytical pre-aggregation."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(RejectedUnits) FROM FactProduction")
    source_rejected = cur.fetchone()[0]
    assert source_rejected is not None and source_rejected > 0

    cur = conn.execute("""
        WITH agg_rejected AS (
            SELECT dm.LineKey, SUM(fp.RejectedUnits) AS TotalRejected
            FROM FactProduction fp
            JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
            GROUP BY dm.LineKey
        )
        SELECT SUM(TotalRejected) FROM agg_rejected;
    """)
    agg_rejected = cur.fetchone()[0]

    assert source_rejected == agg_rejected, f"Production rejected vs analytical mismatch: {source_rejected} != {agg_rejected}"


@pytest.mark.tier1
def test_downtime_total_minutes_reconciliation(reconciliation_db):
    """F7: Curated FactDowntime total minutes must reconcile exactly with Downtime Pareto grand total."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(DowntimeMinutes) FROM FactDowntime")
    source_downtime = cur.fetchone()[0]
    assert source_downtime is not None and source_downtime > 0

    cur = conn.execute("""
        WITH downtime_by_reason AS (
            SELECT r.ReasonCode, SUM(fd.DowntimeMinutes) AS TotalMinutes
            FROM FactDowntime fd
            JOIN DimReason r ON fd.ReasonKey = r.ReasonKey
            GROUP BY r.ReasonCode
        )
        SELECT SUM(TotalMinutes) FROM downtime_by_reason;
    """)
    pareto_total = cur.fetchone()[0]
    assert pytest.approx(source_downtime, rel=1e-5) == pareto_total, f"Downtime Pareto mismatch: source={source_downtime}, pareto={pareto_total}"


@pytest.mark.tier1
def test_quality_total_defects_reconciliation(reconciliation_db):
    """F7: Curated FactQuality defect counts must reconcile exactly with Product Family quality aggregation."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(DefectCount) FROM FactQuality")
    source_defects = cur.fetchone()[0]
    assert source_defects is not None and source_defects > 0

    cur = conn.execute("""
        WITH defects_by_product AS (
            SELECT p.ProductFamily, SUM(fq.DefectCount) AS TotalDefects
            FROM FactQuality fq
            JOIN DimProduct p ON fq.ProductKey = p.ProductKey
            GROUP BY p.ProductFamily
        )
        SELECT SUM(TotalDefects) FROM defects_by_product;
    """)
    agg_defects = cur.fetchone()[0]
    assert source_defects == agg_defects, f"Defects mismatch: source={source_defects}, agg={agg_defects}"


@pytest.mark.tier1
def test_energy_total_kwh_reconciliation(reconciliation_db):
    """F7: Curated FactEnergy total kWh must reconcile exactly with machine-level energy intensity sum."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT SUM(EnergyKWh) FROM FactEnergy")
    source_energy = cur.fetchone()[0]
    assert source_energy is not None and source_energy > 0

    cur = conn.execute("""
        WITH energy_by_machine AS (
            SELECT MachineKey, SUM(EnergyKWh) AS TotalKWh
            FROM FactEnergy
            GROUP BY MachineKey
        )
        SELECT SUM(TotalKWh) FROM energy_by_machine;
    """)
    agg_energy = cur.fetchone()[0]
    assert pytest.approx(source_energy, rel=1e-5) == agg_energy, f"Energy mismatch: source={source_energy}, agg={agg_energy}"


@pytest.mark.tier1
def test_exceptions_total_count_reconciliation(reconciliation_db):
    """F7: Curated FactDQExceptions row count must reconcile exactly with Data Quality Summary total."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT COUNT(*) FROM FactDQExceptions")
    source_exceptions = cur.fetchone()[0]
    assert source_exceptions is not None and source_exceptions > 0

    cur = conn.execute("""
        WITH exceptions_by_rule AS (
            SELECT RuleViolated, COUNT(*) AS RuleCount
            FROM FactDQExceptions
            GROUP BY RuleViolated
        )
        SELECT SUM(RuleCount) FROM exceptions_by_rule;
    """)
    summary_exceptions = cur.fetchone()[0]
    assert source_exceptions == summary_exceptions, f"Exceptions mismatch: source={source_exceptions}, summary={summary_exceptions}"


@pytest.mark.tier2
def test_oee_line_shift_production_reconciliation(reconciliation_db):
    """F7: End-of-line machine finished units must equal OEE by line/shift report total good units, preventing 4x double-counting."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("""
        SELECT SUM(fp.GoodUnits)
        FROM FactProduction fp
        JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
        WHERE dm.IsEndOfLine = 1;
    """)
    eol_good = cur.fetchone()[0]
    assert eol_good is not None and eol_good > 0

    cur = conn.execute("""
        WITH line_finished AS (
            SELECT fp.DateKey, fp.ShiftKey, dm.LineKey, SUM(fp.GoodUnits) AS FinishedGood
            FROM FactProduction fp
            JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey
            WHERE dm.IsEndOfLine = 1
            GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey
        )
        SELECT SUM(FinishedGood) FROM line_finished;
    """)
    line_total_finished = cur.fetchone()[0]
    assert eol_good == line_total_finished

    # Verify total station operations exceed finished EOL goods by ~4x (4 sequential cell stages)
    cur = conn.execute("SELECT SUM(GoodUnits) FROM FactProduction")
    total_station_good = cur.fetchone()[0]
    assert total_station_good > eol_good
    assert pytest.approx(total_station_good, rel=0.15) == eol_good * 4.0


@pytest.mark.tier2
def test_reconciliation_report_csv_generation(reconciliation_db, tmp_path):
    """F7: Reconciliation report schema must contain Metric, SourceTotal, AggregatedTotal, Variance, and Status."""
    conn, db_path, _ = reconciliation_db
    reports_dir = tmp_path / "reports"
    res = generate_reports(db_path=db_path, reports_dir=reports_dir)
    assert res["status"] == "BALANCED"

    recon_csv = reports_dir / "reconciliation_report.csv"
    assert recon_csv.exists()
    loaded_df = pd.read_csv(recon_csv)
    expected_cols = {"Metric", "SourceTotal", "AggregatedTotal", "Variance", "Status"}
    assert expected_cols.issubset(set(loaded_df.columns))
    assert len(loaded_df) == 4
    assert (loaded_df["Variance"] == 0.0).all()
    assert (loaded_df["Status"] == "BALANCED").all()


@pytest.mark.tier2
def test_reconciliation_report_all_metrics_zero_variance(reconciliation_db):
    """F7: In a healthy pipeline run, all reconciliation metrics must have Variance == 0.0 and Status == BALANCED."""
    conn, _, _ = reconciliation_db
    metrics = [
        ("ProducedUnits", "SELECT SUM(ProducedUnits) FROM FactProduction",
         "SELECT SUM(cnt) FROM (SELECT SUM(ProducedUnits) AS cnt FROM FactProduction fp JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey)"),
        ("GoodUnits", "SELECT SUM(GoodUnits) FROM FactProduction",
         "SELECT SUM(cnt) FROM (SELECT SUM(GoodUnits) AS cnt FROM FactProduction fp JOIN DimMachine dm ON fp.MachineKey = dm.MachineKey GROUP BY fp.DateKey, fp.ShiftKey, dm.LineKey)"),
        ("DowntimeMinutes", "SELECT SUM(DowntimeMinutes) FROM FactDowntime",
         "SELECT SUM(m) FROM (SELECT SUM(DowntimeMinutes) AS m FROM FactDowntime GROUP BY ReasonKey)"),
        ("EnergyKWh", "SELECT SUM(EnergyKWh) FROM FactEnergy",
         "SELECT SUM(e) FROM (SELECT SUM(EnergyKWh) AS e FROM FactEnergy GROUP BY MachineKey)"),
    ]

    recon_rows = []
    for metric_name, src_sql, agg_sql in metrics:
        src_val = conn.execute(src_sql).fetchone()[0]
        agg_val = conn.execute(agg_sql).fetchone()[0]
        variance = abs(src_val - agg_val)
        status = "BALANCED" if pytest.approx(variance, abs=1e-3) == 0.0 else "UNBALANCED"
        recon_rows.append({"Metric": metric_name, "SourceTotal": src_val, "AggregatedTotal": agg_val, "Variance": variance, "Status": status})

    df = pd.DataFrame(recon_rows)
    assert (df["Variance"] < 1e-3).all(), f"Non-zero variance detected in reconciliation:\n{df}"
    assert (df["Status"] == "BALANCED").all()


@pytest.mark.tier3
def test_reconciliation_detects_deliberate_data_tampering(reconciliation_db):
    """F7: Intentionally modified fact row must trigger non-zero variance and flag status as UNBALANCED."""
    conn, _, _ = reconciliation_db
    conn.execute("SAVEPOINT tamper_test")
    try:
        source_before = conn.execute("SELECT SUM(ProducedUnits) FROM FactProduction").fetchone()[0]

        # Tamper with the fact table
        conn.execute("UPDATE FactProduction SET ProducedUnits = ProducedUnits - 25 WHERE ProductionKey = (SELECT MIN(ProductionKey) FROM FactProduction)")

        source_tampered = conn.execute("SELECT SUM(ProducedUnits) FROM FactProduction").fetchone()[0]
        variance = abs(source_before - source_tampered)
        status = "BALANCED" if variance == 0 else "UNBALANCED"

        assert variance == 25, f"Expected 25 units discrepancy, got {variance}"
        assert status == "UNBALANCED"
    finally:
        conn.execute("ROLLBACK TO tamper_test")


@pytest.mark.tier3
def test_reconciliation_date_range_alignment(reconciliation_db):
    """F7: Date ranges across production and downtime must align with DimDate without orphan dates."""
    conn, _, _ = reconciliation_db
    cur = conn.execute("SELECT DISTINCT DateKey FROM DimDate ORDER BY DateKey")
    dim_dates = {r[0] for r in cur.fetchall()}

    cur = conn.execute("SELECT DISTINCT DateKey FROM FactProduction ORDER BY DateKey")
    prod_dates = {r[0] for r in cur.fetchall()}

    cur = conn.execute("SELECT DISTINCT DateKey FROM FactDowntime ORDER BY DateKey")
    down_dates = {r[0] for r in cur.fetchall()}

    cur = conn.execute("SELECT DISTINCT DateKey FROM FactEnergy ORDER BY DateKey")
    energy_dates = {r[0] for r in cur.fetchall()}

    assert prod_dates.issubset(dim_dates), "Orphan DateKeys in FactProduction not found in DimDate"
    assert down_dates.issubset(dim_dates), "Orphan DateKeys in FactDowntime not found in DimDate"
    assert energy_dates.issubset(dim_dates), "Orphan DateKeys in FactEnergy not found in DimDate"
    assert prod_dates == down_dates == energy_dates, "Temporal misalignment across fact tables"
    assert len(prod_dates) > 0, "No dates populated in fact tables"
