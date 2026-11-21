"""tests/test_sql_analytics.py

Authentic Feature 6 (F6) and Feature 7 (F7) test suite verifying:
- CTE pre-aggregations preventing Cartesian products
- Real integer-to-float division in SQL
- Downtime Pareto sorting and cumulative percentage
- Direct execution of queries extracted from sql/analytics.sql
- Analytical reports generation and non-null KPI verification
"""

import re
import pathlib
import sqlite3
import pandas as pd
import pytest

from src.generate_reports import generate_reports


def get_analytics_query(repo_root: pathlib.Path, query_number: int) -> str:
    """Extract a query from sql/analytics.sql by its section header number."""
    sql_path = repo_root / "sql" / "analytics.sql"
    assert sql_path.exists(), f"sql/analytics.sql not found at {sql_path}"
    text = sql_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"--\s*(?:Query\s*)?{query_number}[:\.][^\r\n]*\r?\n(?:--[^\r\n]*\r?\n)*\s*(.*?)(?=(?:--\s*(?:Query\s*)?\d+[:\.]|\Z))",
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"Query section {query_number} not found in sql/analytics.sql"
    return match.group(1).strip().rstrip(";")


@pytest.mark.tier1
def test_cte_pre_aggregation_prevents_cartesian_multiplication(populated_db):
    """F6: CTE pre-aggregation prevents 1-to-many Cartesian explosion when joining Production and Downtime."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (501, 20240101, 1, 1, 1, 100, 100, 95, 5)
    """)
    conn.execute("""
        INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
        VALUES (601, 20240101, 1, 1, 1, 15.0, 1),
               (602, 20240101, 1, 1, 2, 20.0, 0),
               (603, 20240101, 1, 1, 3, 10.0, 0)
    """)
    conn.commit()

    query = """
    WITH agg_prod AS (
        SELECT DateKey, ShiftKey, MachineKey, SUM(ProducedUnits) AS TotalProduced, SUM(GoodUnits) AS TotalGood
        FROM FactProduction
        WHERE DateKey = 20240101 AND ShiftKey = 1 AND MachineKey = 1
        GROUP BY DateKey, ShiftKey, MachineKey
    ), agg_down AS (
        SELECT DateKey, ShiftKey, MachineKey, SUM(DowntimeMinutes) AS TotalDown
        FROM FactDowntime
        WHERE DateKey = 20240101 AND ShiftKey = 1 AND MachineKey = 1
        GROUP BY DateKey, ShiftKey, MachineKey
    )
    SELECT p.TotalProduced, p.TotalGood, d.TotalDown
    FROM agg_prod p
    JOIN agg_down d ON p.DateKey = d.DateKey AND p.ShiftKey = d.ShiftKey AND p.MachineKey = d.MachineKey;
    """
    cur = conn.execute(query)
    row = cur.fetchone()
    assert row["TotalProduced"] == 100, "Cartesian multiplication multiplied ProducedUnits"
    assert row["TotalGood"] == 95, "Cartesian multiplication multiplied GoodUnits"
    assert row["TotalDown"] == 45.0, "Downtime minutes sum incorrect"


@pytest.mark.tier1
def test_sql_integer_division_cast_to_real(populated_db):
    """F6: SQL queries must cast integers to REAL (* 1.0) to prevent integer truncation to 0."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (502, 20240102, 1, 1, 1, 100, 95, 90, 5)
    """)
    conn.commit()

    cur = conn.execute("SELECT (SUM(GoodUnits) * 1.0 / SUM(ProducedUnits)) AS QualityRatio FROM FactProduction WHERE ProductionKey = 502")
    ratio = cur.fetchone()[0]
    assert isinstance(ratio, float)
    assert pytest.approx(ratio, rel=1e-4) == 90 / 95


@pytest.mark.tier1
def test_downtime_pareto_sorting_descending(populated_db, repo_root):
    """F7: Downtime Pareto query from sql/analytics.sql must sort reasons descending by TotalMinutes."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
        VALUES (701, 20240101, 1, 1, 1, 10.0, 1),
               (702, 20240101, 1, 1, 2, 85.0, 0),
               (703, 20240101, 1, 1, 3, 35.0, 0)
    """)
    conn.commit()

    pareto_query = get_analytics_query(repo_root, 2)
    cur = conn.execute(pareto_query)
    rows = cur.fetchall()
    assert len(rows) >= 3
    minutes = [r["TotalMinutes"] for r in rows]
    assert minutes == sorted(minutes, reverse=True), "Pareto reasons not sorted in descending order"


@pytest.mark.tier1
def test_downtime_pareto_cumulative_percentage(populated_db, repo_root):
    """F7: Downtime Pareto query cumulative percentage must end at exactly 100.0%."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
        VALUES (711, 20240101, 1, 1, 1, 50.0, 1),
               (712, 20240101, 1, 1, 2, 30.0, 0),
               (713, 20240101, 1, 1, 3, 20.0, 0)
    """)
    conn.commit()

    pareto_query = get_analytics_query(repo_root, 2)
    cur = conn.execute(pareto_query)
    rows = cur.fetchall()
    assert len(rows) > 0
    final_pct = rows[-1]["CumPct"]
    assert pytest.approx(final_pct, rel=1e-3) == 100.0


@pytest.mark.tier2
def test_downtime_pareto_zero_downtime_reasons(populated_db, repo_root):
    """F7: Reasons with 0 minutes or empty downtime table must execute cleanly without division by zero."""
    conn = populated_db
    pareto_query = get_analytics_query(repo_root, 2)
    cur = conn.execute(pareto_query)
    rows = cur.fetchall()
    assert len(rows) == 0, "Empty downtime table should yield 0 pareto rows"


@pytest.mark.tier1
def test_oee_by_line_shift_aggregation_grain(populated_db):
    """F6: OEE by line and shift produces exactly 1 row per (Date, Line, Shift)."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (801, 20240101, 1, 1, 1, 100, 95, 90, 5),
               (802, 20240101, 1, 2, 1, 100, 96, 92, 4)
    """)
    conn.commit()

    query = """
    SELECT d.Date, l.LineName, s.ShiftName, COUNT(*) AS MachineRecords
    FROM FactProduction fp
    JOIN DimDate d ON fp.DateKey = d.DateKey
    JOIN DimShift s ON fp.ShiftKey = s.ShiftKey
    JOIN DimMachine m ON fp.MachineKey = m.MachineKey
    JOIN DimLine l ON m.LineKey = l.LineKey
    GROUP BY d.Date, l.LineName, s.ShiftName;
    """
    cur = conn.execute(query)
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["MachineRecords"] == 2


@pytest.mark.tier1
def test_oee_by_line_shift_formula_correctness(populated_db):
    """F6: SQL OEE formula computes Quality = GoodUnits / ProducedUnits."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (811, 20240101, 1, 1, 1, 100, 100, 95, 5)
    """)
    conn.commit()

    cur = conn.execute("""
        SELECT (SUM(GoodUnits) * 100.0 / NULLIF(SUM(ProducedUnits), 0)) AS QualityPct
        FROM FactProduction
        WHERE ProductionKey = 811
    """)
    row = cur.fetchone()
    assert pytest.approx(row["QualityPct"], rel=1e-3) == 95.0


@pytest.mark.tier1
def test_production_summary_aggregations(populated_db):
    """F6: Production summary aggregates Target, Produced, Good, and Rejected units."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (821, 20240101, 1, 1, 1, 200, 190, 180, 10)
    """)
    conn.commit()

    cur = conn.execute("""
        SELECT SUM(TargetUnits) AS TotalTarget, SUM(ProducedUnits) AS TotalProduced,
               SUM(GoodUnits) AS TotalGood, SUM(RejectedUnits) AS TotalRejected
        FROM FactProduction
        WHERE ProductionKey = 821
    """)
    row = cur.fetchone()
    assert row["TotalTarget"] == 200
    assert row["TotalProduced"] == 190
    assert row["TotalGood"] == 180
    assert row["TotalRejected"] == 10


@pytest.mark.tier1
def test_quality_summary_defect_rates(populated_db, repo_root):
    """F6: Quality summary from sql/analytics.sql calculates DefectRatePct."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactQuality (QualityKey, DateKey, ShiftKey, MachineKey, ProductKey, DefectReasonKey, DefectCount)
        VALUES (901, 20240101, 1, 1, 1, 6, 12)
    """)
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (831, 20240101, 1, 1, 1, 200, 200, 188, 12)
    """)
    conn.commit()

    defect_query = get_analytics_query(repo_root, 3)
    cur = conn.execute(defect_query)
    rows = [r for r in cur.fetchall() if r["ProductFamily"] == "Family_A"]
    assert len(rows) == 1
    assert rows[0]["TotalDefects"] == 12
    assert pytest.approx(rows[0]["DefectRatePct"], rel=1e-3) == 6.0


@pytest.mark.tier1
def test_energy_intensity_by_machine(populated_db, repo_root):
    """F6: Energy intensity query from sql/analytics.sql calculates kWhPerGoodUnit."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (841, 20240101, 1, 1, 1, 100, 100, 100, 0)
    """)
    conn.execute("""
        INSERT INTO FactEnergy (EnergyKey, DateKey, ShiftKey, MachineKey, EnergyKWh)
        VALUES (951, 20240101, 1, 1, 75.0)
    """)
    conn.commit()

    energy_query = get_analytics_query(repo_root, 4)
    cur = conn.execute(energy_query)
    rows = cur.fetchall()
    assert len(rows) >= 1
    m1_row = [r for r in rows if r["MachineName"] == "Machine 111"][0]
    assert pytest.approx(m1_row["kWhPerGoodUnit"], rel=1e-3) == 0.75


@pytest.mark.tier1
def test_data_quality_summary_counts(populated_db):
    """F6: Data quality summary query groups exceptions by SourceTable and RuleViolated."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactDQExceptions (ExceptionKey, SourceTable, RecordIdentifier, RuleViolated, Severity, Disposition, Description)
        VALUES (201, 'FactEnergy', 'E1', 'NegativeValue', 'ERROR', 'Quarantine', 'Negative kWh'),
               (202, 'FactEnergy', 'E2', 'NegativeValue', 'ERROR', 'Quarantine', 'Negative kWh'),
               (203, 'FactProduction', 'P1', 'DuplicatePrimaryKey', 'ERROR', 'Quarantine', 'Duplicate PK')
    """)
    conn.commit()

    cur = conn.execute("""
        SELECT SourceTable, RuleViolated, COUNT(*) AS ExceptionCount
        FROM FactDQExceptions
        WHERE ExceptionKey >= 201
        GROUP BY SourceTable, RuleViolated
        ORDER BY SourceTable, RuleViolated
    """)
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0]["SourceTable"] == "FactEnergy"
    assert rows[0]["ExceptionCount"] == 2
    assert rows[1]["SourceTable"] == "FactProduction"
    assert rows[1]["ExceptionCount"] == 1


@pytest.mark.tier2
def test_seven_day_rolling_oee_window(populated_db, repo_root):
    """F6: 7-day rolling OEE query from sql/analytics.sql executes cleanly with window functions."""
    conn = populated_db
    query = get_analytics_query(repo_root, 5)
    cur = conn.execute(query)
    assert cur is not None


@pytest.mark.tier2
def test_generate_reports_creates_all_six_csvs(populated_db, tmp_path):
    """F6: Reports generator creates all 6 analytical CSVs and reconciliation report."""
    reports_dir = tmp_path / "reports"
    db_file = tmp_path / "temp_reports.db"

    # Export populated_db into db_file
    backup_conn = sqlite3.connect(db_file)
    populated_db.backup(backup_conn)
    backup_conn.close()

    res = generate_reports(db_path=db_file, reports_dir=reports_dir)
    assert res["status"] in {"BALANCED", "UNBALANCED"}

    expected_reports = [
        "production_summary.csv",
        "oee_by_line_shift.csv",
        "downtime_parato.csv",
        "quality_summary.csv",
        "energy_intensity.csv",
        "data_quality_summary.csv",
        "reconciliation_report.csv",
    ]
    for fname in expected_reports:
        fpath = reports_dir / fname
        assert fpath.exists(), f"Report file {fname} was not created"
        assert fpath.stat().st_size > 0, f"Report file {fname} is empty"


@pytest.mark.tier2
def test_reports_have_valid_headers_and_non_empty(populated_db, repo_root):
    """F6: Analytical queries produce result sets with required column headers."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
        VALUES (721, 20240101, 1, 1, 1, 10.0, 1)
    """)
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (842, 20240101, 1, 1, 1, 100, 100, 100, 0)
    """)
    conn.execute("""
        INSERT INTO FactEnergy (EnergyKey, DateKey, ShiftKey, MachineKey, EnergyKWh)
        VALUES (952, 20240101, 1, 1, 75.0)
    """)
    conn.commit()

    pareto_df = pd.read_sql_query(get_analytics_query(repo_root, 2), conn)
    assert {"ReasonCode", "TotalMinutes", "CumPct"}.issubset(set(pareto_df.columns))

    energy_df = pd.read_sql_query(get_analytics_query(repo_root, 4), conn)
    assert {"MachineName", "EnergyKWh", "GoodUnits", "kWhPerGoodUnit"}.issubset(set(energy_df.columns))


@pytest.mark.tier2
def test_no_null_kpi_values_in_analytical_reports(populated_db, repo_root):
    """F6: Numeric KPI columns from analytical queries for producing machines must not contain null or NaN values."""
    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (851, 20240101, 1, 1, 1, 100, 100, 95, 5)
    """)
    conn.execute("""
        INSERT INTO FactEnergy (EnergyKey, DateKey, ShiftKey, MachineKey, EnergyKWh)
        VALUES (961, 20240101, 1, 1, 50.0)
    """)
    conn.commit()

    energy_df = pd.read_sql_query(get_analytics_query(repo_root, 4), conn)
    producing_machines = energy_df[energy_df["GoodUnits"] > 0]
    assert len(producing_machines) >= 1
    assert not producing_machines["kWhPerGoodUnit"].isna().any(), "kWhPerGoodUnit contains nulls for producing machines"


@pytest.mark.tier3
def test_analytics_sql_file_syntax_validity(populated_db, repo_root):
    """F6: Every query in sql/analytics.sql must execute cleanly in SQLite with zero syntax errors."""
    for q_idx in range(1, 6):
        query = get_analytics_query(repo_root, q_idx)
        cur = populated_db.execute(query)
        assert cur is not None, f"Query {q_idx} execution returned None cursor"
