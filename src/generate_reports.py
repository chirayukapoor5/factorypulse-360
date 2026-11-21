"""src/generate_reports.py

FactoryPulse 360 - Analytical Report Generator & Reconciliation Audit
Executes analytical SQL queries against the curated SQLite warehouse and exports
the analytical CSV reports plus reconciliation_report.csv.
"""

import argparse
import pathlib
import sys
import sqlite3
import pandas as pd
from typing import Dict, Any

# Ensure repository root is on sys.path to support both 'python src/generate_reports.py' and 'python -m src.generate_reports'
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config import BASE_DIR

DEFAULT_DB_PATH = BASE_DIR / "data" / "factorypulse.db"
DEFAULT_REPORTS_DIR = BASE_DIR / "reports" / "analytics"


def generate_reports(
    db_path: pathlib.Path | str | None = None,
    reports_dir: pathlib.Path | str | None = None,
) -> Dict[str, Any]:
    """Generates 6 analytical CSV reports + reconciliation report in reports_dir.

    Parameters
    ----------
    db_path : Path or str, optional
        Path to SQLite database (defaults to data/factorypulse.db).
    reports_dir : Path or str, optional
        Target directory for analytical reports (defaults to reports/analytics).

    Returns
    -------
    dict[str, Any]
        Reconciliation verification dictionary with status and variance metrics.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path = pathlib.Path(db_path)

    if reports_dir is None:
        reports_dir = DEFAULT_REPORTS_DIR
    reports_dir = pathlib.Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Detect optional schema columns in DimProduct and DimShift
    dim_product_cols = {r[1] for r in conn.execute("PRAGMA table_info(DimProduct)").fetchall()}
    dim_shift_cols = {r[1] for r in conn.execute("PRAGMA table_info(DimShift)").fetchall()}

    has_cycle_time = "IdealCycleTimeMinutes" in dim_product_cols
    has_scheduled_minutes = "ScheduledMinutes" in dim_shift_cols

    # Query 1: Production Summary
    q_prod = """
    SELECT
        d.Date,
        l.LineName,
        SUM(fp.TargetUnits) AS TotalTarget,
        SUM(fp.ProducedUnits) AS TotalProduced,
        SUM(fp.GoodUnits) AS TotalGood,
        SUM(fp.RejectedUnits) AS TotalRejected
    FROM FactProduction fp
    JOIN DimDate d ON fp.DateKey = d.DateKey
    JOIN DimMachine m ON fp.MachineKey = m.MachineKey
    JOIN DimLine l ON m.LineKey = l.LineKey
    GROUP BY d.Date, l.LineName
    ORDER BY d.Date, l.LineName;
    """
    df_prod = pd.read_sql_query(q_prod, conn)
    df_prod.to_csv(reports_dir / "production_summary.csv", index=False)

    # Query 2: OEE by Line and Shift
    cycle_time_expr = "SUM(fp.ProducedUnits * dp.IdealCycleTimeMinutes)" if has_cycle_time else "SUM(fp.ProducedUnits * 4.5)"
    join_product_clause = "JOIN DimProduct dp ON fp.ProductKey = dp.ProductKey" if has_cycle_time else ""
    scheduled_minutes_expr = "COALESCE(s.ScheduledMinutes, 480.0)" if has_scheduled_minutes else "480.0"

    q_oee = f"""
    WITH prod_agg AS (
        SELECT
            fp.DateKey,
            fp.ShiftKey,
            m.LineKey,
            COUNT(DISTINCT fp.MachineKey) AS ActiveMachines,
            SUM(fp.TargetUnits) AS TargetUnits,
            SUM(fp.ProducedUnits) AS ProducedUnits,
            SUM(fp.GoodUnits) AS GoodUnits,
            SUM(fp.RejectedUnits) AS RejectedUnits,
            {cycle_time_expr} AS IdealProductionMinutes
        FROM FactProduction fp
        JOIN DimMachine m ON fp.MachineKey = m.MachineKey
        {join_product_clause}
        GROUP BY fp.DateKey, fp.ShiftKey, m.LineKey
    ),
    down_agg AS (
        SELECT
            fd.DateKey,
            fd.ShiftKey,
            m.LineKey,
            SUM(fd.DowntimeMinutes) AS TotalDowntime,
            SUM(CASE WHEN fd.Planned = 1 THEN fd.DowntimeMinutes ELSE 0.0 END) AS PlannedMaintenanceMinutes,
            SUM(CASE WHEN fd.Planned = 0 THEN fd.DowntimeMinutes ELSE 0.0 END) AS UnplannedDowntimeMinutes
        FROM FactDowntime fd
        JOIN DimMachine m ON fd.MachineKey = m.MachineKey
        GROUP BY fd.DateKey, fd.ShiftKey, m.LineKey
    ),
    energy_agg AS (
        SELECT
            fe.DateKey,
            fe.ShiftKey,
            m.LineKey,
            SUM(fe.EnergyKWh) AS TotalEnergy
        FROM FactEnergy fe
        JOIN DimMachine m ON fe.MachineKey = m.MachineKey
        GROUP BY fe.DateKey, fe.ShiftKey, m.LineKey
    ),
    line_machines AS (
        SELECT LineKey, COUNT(*) AS MachineCount
        FROM DimMachine
        GROUP BY LineKey
    )
    SELECT
        d.Date,
        l.LineName,
        s.ShiftName,
        COALESCE(p.TargetUnits, 0) AS TargetUnits,
        COALESCE(p.ProducedUnits, 0) AS ProducedUnits,
        COALESCE(p.GoodUnits, 0) AS GoodUnits,
        COALESCE(p.RejectedUnits, 0) AS RejectedUnits,
        ROUND(COALESCE(dn.TotalDowntime, 0.0), 2) AS TotalDowntime,
        ROUND(COALESCE(e.TotalEnergy, 0.0), 2) AS TotalEnergy,
        ROUND(
            CASE
                WHEN (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0)) <= 0.0 THEN 0.0
                ELSE (
                    (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) * 100.0 /
                    NULLIF(lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0), 0.0)
                )
            END, 2
        ) AS AvailabilityPct,
        ROUND(
            CASE
                WHEN (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) <= 0.0 THEN 0.0
                ELSE (
                    COALESCE(p.IdealProductionMinutes, 0.0) * 100.0 /
                    NULLIF(lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0), 0.0)
                )
            END, 2
        ) AS PerformancePct,
        ROUND(
            CASE
                WHEN COALESCE(p.ProducedUnits, 0) <= 0 THEN 0.0
                ELSE (COALESCE(p.GoodUnits, 0) * 100.0 / p.ProducedUnits)
            END, 2
        ) AS QualityPct,
        ROUND(
            (
                (
                    CASE
                        WHEN (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0)) <= 0.0 THEN 0.0
                        ELSE (
                            (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) /
                            NULLIF(lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0), 0.0)
                        )
                    END
                ) * (
                    CASE
                        WHEN (lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0)) <= 0.0 THEN 0.0
                        ELSE (
                            COALESCE(p.IdealProductionMinutes, 0.0) /
                            NULLIF(lm.MachineCount * {scheduled_minutes_expr} - COALESCE(dn.PlannedMaintenanceMinutes, 0.0) - COALESCE(dn.UnplannedDowntimeMinutes, 0.0), 0.0)
                        )
                    END
                ) * (
                    CASE
                        WHEN COALESCE(p.ProducedUnits, 0) <= 0 THEN 0.0
                        ELSE (COALESCE(p.GoodUnits, 0) * 1.0 / p.ProducedUnits)
                    END
                )
            ) * 100.0, 2
        ) AS OEE_Pct
    FROM DimDate d
    CROSS JOIN DimLine l
    CROSS JOIN DimShift s
    JOIN line_machines lm ON l.LineKey = lm.LineKey
    LEFT JOIN prod_agg p ON d.DateKey = p.DateKey AND s.ShiftKey = p.ShiftKey AND l.LineKey = p.LineKey
    LEFT JOIN down_agg dn ON d.DateKey = dn.DateKey AND s.ShiftKey = dn.ShiftKey AND l.LineKey = dn.LineKey
    LEFT JOIN energy_agg e ON d.DateKey = e.DateKey AND s.ShiftKey = e.ShiftKey AND l.LineKey = e.LineKey
    ORDER BY d.Date, l.LineName, s.ShiftName;
    """
    df_oee = pd.read_sql_query(q_oee, conn)
    df_oee.to_csv(reports_dir / "oee_by_line_shift.csv", index=False)

    # Query 3: Downtime Pareto Analysis
    q_down = """
    WITH downtime_by_reason AS (
        SELECT r.ReasonCode, SUM(fd.DowntimeMinutes) AS TotalMinutes
        FROM FactDowntime fd
        JOIN DimReason r ON fd.ReasonKey = r.ReasonKey
        GROUP BY r.ReasonCode
    ), ranked AS (
        SELECT ReasonCode, TotalMinutes,
               SUM(TotalMinutes) OVER (ORDER BY TotalMinutes DESC, ReasonCode ASC) AS CumulativeMinutes,
               SUM(TotalMinutes) OVER () AS GrandTotal
        FROM downtime_by_reason
    )
    SELECT ReasonCode,
           ROUND(TotalMinutes, 4) AS TotalMinutes,
           ROUND(TotalMinutes * 100.0 / NULLIF(GrandTotal, 0.0), 4) AS PctOfTotal,
           ROUND(CumulativeMinutes, 4) AS CumulativeMinutes,
           ROUND(CumulativeMinutes * 100.0 / NULLIF(GrandTotal, 0.0), 4) AS CumPct
    FROM ranked
    ORDER BY TotalMinutes DESC, ReasonCode ASC;
    """
    df_down = pd.read_sql_query(q_down, conn)
    df_down.to_csv(reports_dir / "downtime_parato.csv", index=False)
    df_down.to_csv(reports_dir / "downtime_pareto.csv", index=False)

    # Query 4: Quality & Scrap Summary by Product Family
    q_quality = """
    WITH prod_by_family AS (
        SELECT p.ProductFamily,
               SUM(fp.ProducedUnits) AS TotalProduced,
               SUM(fp.GoodUnits) AS TotalGood,
               SUM(fp.RejectedUnits) AS TotalRejected
        FROM FactProduction fp
        JOIN DimProduct p ON fp.ProductKey = p.ProductKey
        GROUP BY p.ProductFamily
    ), qual_by_family AS (
        SELECT p.ProductFamily,
               SUM(fq.DefectCount) AS TotalDefects
        FROM FactQuality fq
        JOIN DimProduct p ON fq.ProductKey = p.ProductKey
        GROUP BY p.ProductFamily
    )
    SELECT
        p.ProductFamily,
        COALESCE(p.TotalProduced, 0) AS TotalProduced,
        COALESCE(p.TotalGood, 0) AS TotalGood,
        COALESCE(p.TotalRejected, 0) AS TotalRejected,
        COALESCE(q.TotalDefects, 0) AS TotalDefects,
        ROUND(COALESCE(q.TotalDefects, 0) * 100.0 / NULLIF(p.TotalProduced, 0), 4) AS DefectRatePct,
        ROUND(COALESCE(p.TotalRejected, 0) * 100.0 / NULLIF(p.TotalProduced, 0), 4) AS RejectionRatePct,
        ROUND(COALESCE(p.TotalGood, 0) * 100.0 / NULLIF(p.TotalProduced, 0), 4) AS YieldPct
    FROM prod_by_family p
    LEFT JOIN qual_by_family q ON p.ProductFamily = q.ProductFamily
    ORDER BY p.ProductFamily;
    """
    df_quality = pd.read_sql_query(q_quality, conn)
    df_quality.to_csv(reports_dir / "quality_summary.csv", index=False)

    # Query 5: Energy Intensity Ranking
    q_energy = """
    WITH energy_by_machine AS (
        SELECT MachineKey, SUM(EnergyKWh) AS EnergyKWh
        FROM FactEnergy
        GROUP BY MachineKey
    ), prod_by_machine AS (
        SELECT MachineKey, SUM(GoodUnits) AS GoodUnits
        FROM FactProduction
        GROUP BY MachineKey
    )
    SELECT
        m.MachineName,
        ROUND(COALESCE(e.EnergyKWh, 0.0), 4) AS EnergyKWh,
        COALESCE(p.GoodUnits, 0) AS GoodUnits,
        ROUND(COALESCE(e.EnergyKWh, 0.0) * 1.0 / NULLIF(p.GoodUnits, 0), 4) AS kWhPerGoodUnit
    FROM DimMachine m
    LEFT JOIN energy_by_machine e ON m.MachineKey = e.MachineKey
    LEFT JOIN prod_by_machine p ON m.MachineKey = p.MachineKey
    ORDER BY kWhPerGoodUnit DESC, m.MachineName ASC;
    """
    df_energy = pd.read_sql_query(q_energy, conn)
    df_energy.to_csv(reports_dir / "energy_intensity.csv", index=False)

    # Query 6: Data Quality Summary
    q_dq = """
    SELECT
        SourceTable,
        RuleViolated,
        Severity,
        Disposition,
        COUNT(*) AS ExceptionCount
    FROM FactDQExceptions
    GROUP BY SourceTable, RuleViolated, Severity, Disposition
    ORDER BY SourceTable, RuleViolated;
    """
    df_dq = pd.read_sql_query(q_dq, conn)
    df_dq.to_csv(reports_dir / "data_quality_summary.csv", index=False)

    # Query 7: Reconciliation Audit (4 core metrics matching test_reconciliation.py)
    cur = conn.cursor()
    src_produced = cur.execute("SELECT SUM(ProducedUnits) FROM FactProduction").fetchone()[0] or 0
    src_good = cur.execute("SELECT SUM(GoodUnits) FROM FactProduction").fetchone()[0] or 0
    src_downtime = cur.execute("SELECT SUM(DowntimeMinutes) FROM FactDowntime").fetchone()[0] or 0.0
    src_energy = cur.execute("SELECT SUM(EnergyKWh) FROM FactEnergy").fetchone()[0] or 0.0

    agg_produced = int(df_prod["TotalProduced"].sum())
    agg_good = int(df_prod["TotalGood"].sum())
    agg_downtime = float(df_down["TotalMinutes"].sum())
    agg_energy = float(df_energy["EnergyKWh"].sum())

    recon_rows = [
        {"Metric": "ProducedUnits", "SourceTotal": src_produced, "AggregatedTotal": agg_produced},
        {"Metric": "GoodUnits", "SourceTotal": src_good, "AggregatedTotal": agg_good},
        {"Metric": "DowntimeMinutes", "SourceTotal": round(src_downtime, 2), "AggregatedTotal": round(agg_downtime, 2)},
        {"Metric": "EnergyKWh", "SourceTotal": round(src_energy, 2), "AggregatedTotal": round(agg_energy, 2)},
    ]

    for r in recon_rows:
        diff = abs(r["SourceTotal"] - r["AggregatedTotal"])
        r["Variance"] = round(diff, 2)
        r["Status"] = "BALANCED" if r["Variance"] == 0.0 else "UNBALANCED"

    df_recon = pd.DataFrame(recon_rows)
    df_recon.to_csv(reports_dir / "reconciliation_report.csv", index=False)

    conn.close()

    total_variance = float(df_recon["Variance"].sum())
    is_balanced = (df_recon["Status"] == "BALANCED").all()

    return {
        "status": "BALANCED" if is_balanced else "UNBALANCED",
        "total_variance": total_variance,
        "metrics": {r["Metric"]: r for r in recon_rows},
        "reports_dir": str(reports_dir),
        "reports_generated": [
            "production_summary.csv",
            "oee_by_line_shift.csv",
            "downtime_parato.csv",
            "downtime_pareto.csv",
            "quality_summary.csv",
            "energy_intensity.csv",
            "data_quality_summary.csv",
            "reconciliation_report.csv",
        ],
    }


def calculate_availability(
    scheduled_minutes: float,
    planned_maintenance_minutes: float,
    unplanned_downtime_minutes: float,
) -> float:
    """Computes Availability ratio = Operating Minutes / Planned Production Minutes.
    Clamps between 0.0 and 1.0; returns 0.0 if planned production <= 0."""
    planned_production = scheduled_minutes - planned_maintenance_minutes
    if planned_production <= 0.0:
        return 0.0
    operating_minutes = planned_production - unplanned_downtime_minutes
    if operating_minutes <= 0.0:
        return 0.0
    return min(1.0, max(0.0, operating_minutes / planned_production))


def calculate_performance(
    produced_units: int,
    ideal_cycle_time_minutes: float,
    operating_minutes: float,
) -> float:
    """Computes Performance ratio = Ideal Production Minutes / Operating Minutes.
    Clamps to 0.0 if operating minutes <= 0 or produced units <= 0."""
    if operating_minutes <= 0.0 or produced_units <= 0 or ideal_cycle_time_minutes <= 0.0:
        return 0.0
    ideal_minutes = produced_units * ideal_cycle_time_minutes
    return ideal_minutes / operating_minutes


def calculate_quality(good_units: int, total_units: int) -> float:
    """Computes Quality ratio = Good Units / Total Units.
    Clamps between 0.0 and 1.0; returns 0.0 if total units <= 0."""
    if total_units <= 0 or good_units <= 0:
        return 0.0
    return min(1.0, max(0.0, good_units / total_units))


def calculate_oee(availability: float, performance: float, quality: float) -> float:
    """Computes OEE = Availability * Performance * Quality."""
    return max(0.0, availability * performance * quality)


def calculate_energy_intensity(total_kwh: float, good_units: int) -> float:
    """Computes Energy Intensity = Total kWh / Good Units.
    Returns 0.0 if good units <= 0."""
    if good_units <= 0 or total_kwh <= 0.0:
        return 0.0
    return total_kwh / good_units


def calculate_weighted_oee(
    good_units: int,
    ideal_cycle_time_minutes: float,
    planned_production_minutes: float,
) -> float:
    """Computes weighted aggregate OEE directly from total ideal production time and planned production time:
    OEE = Total Ideal Production Minutes / Total Planned Production Minutes."""
    if planned_production_minutes <= 0.0 or good_units <= 0 or ideal_cycle_time_minutes <= 0.0:
        return 0.0
    ideal_good_minutes = good_units * ideal_cycle_time_minutes
    return min(1.0, max(0.0, ideal_good_minutes / planned_production_minutes))


def main():
    parser = argparse.ArgumentParser(description="Generate FactoryPulse 360 analytical reports")
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")
    parser.add_argument("--reports-dir", type=str, default=str(DEFAULT_REPORTS_DIR), help="Output reports directory")
    args = parser.parse_args()

    result = generate_reports(db_path=args.db_path, reports_dir=args.reports_dir)
    print(f"Reports generated into {result['reports_dir']}. Status: {result['status']}")


if __name__ == "__main__":
    main()
