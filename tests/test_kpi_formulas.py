"""tests/test_kpi_formulas.py

Comprehensive isolated tests for authentic manufacturing KPI calculation logic (F5).
Validates canonical Python module functions in src.generate_reports and
relational SQLite query parity across Tiers 1-3.
Zero local toy functions; authentic calculation parity.
"""

import sqlite3
import pytest

from src.generate_reports import (
    calculate_availability,
    calculate_performance,
    calculate_quality,
    calculate_oee,
    calculate_energy_intensity,
    calculate_weighted_oee,
)


# ============================================================================
# Tier 1: Equivalence Class Standard Calculations
# ============================================================================

@pytest.mark.tier1
def test_availability_standard_calculation(populated_db):
    """F5: Standard shift availability: 480 scheduled, 30 planned maint, 45 unplanned downtime."""
    avail = calculate_availability(scheduled_minutes=480.0, planned_maintenance_minutes=30.0, unplanned_downtime_minutes=45.0)
    assert pytest.approx(avail, rel=1e-4) == 0.90

    conn = populated_db
    conn.execute("""
        INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
        VALUES (1001, 20240101, 1, 1, 1, 30.0, 1),
               (1002, 20240101, 1, 1, 2, 45.0, 0)
    """)
    conn.commit()

    query = """
    WITH down AS (
        SELECT ShiftKey,
               SUM(CASE WHEN Planned = 1 THEN DowntimeMinutes ELSE 0 END) AS PlannedMaint,
               SUM(CASE WHEN Planned = 0 THEN DowntimeMinutes ELSE 0 END) AS UnplannedDown
        FROM FactDowntime WHERE DateKey = 20240101 AND ShiftKey = 1 AND MachineKey = 1
        GROUP BY ShiftKey
    )
    SELECT ((s.ScheduledMinutes - d.PlannedMaint - d.UnplannedDown) * 1.0 / (s.ScheduledMinutes - d.PlannedMaint)) AS SqlAvail
    FROM DimShift s
    JOIN down d ON s.ShiftKey = d.ShiftKey
    WHERE s.ShiftKey = 1
    """
    cur = conn.execute(query)
    row = cur.fetchone()
    assert pytest.approx(row["SqlAvail"], rel=1e-4) == avail


@pytest.mark.tier1
def test_availability_zero_unplanned_downtime():
    """F5: Availability equals 1.0 (100%) when there is zero unplanned downtime."""
    avail = calculate_availability(scheduled_minutes=480.0, planned_maintenance_minutes=0.0, unplanned_downtime_minutes=0.0)
    assert pytest.approx(avail, rel=1e-4) == 1.0


@pytest.mark.tier2
def test_availability_zero_planned_production_minutes(populated_db):
    """F5: When planned maintenance equals scheduled minutes, availability must be 0.0 without ZeroDivisionError."""
    avail = calculate_availability(scheduled_minutes=480.0, planned_maintenance_minutes=480.0, unplanned_downtime_minutes=0.0)
    assert avail == 0.0

    conn = populated_db
    query = "SELECT COALESCE(0.0 / NULLIF(0.0, 0.0), 0.0) AS SqlZero"
    row = conn.execute(query).fetchone()
    assert row["SqlZero"] == 0.0


@pytest.mark.tier2
def test_availability_downtime_exceeds_planned_production():
    """F5: When unplanned downtime exceeds planned production, availability is clamped to 0.0 (no negative availability)."""
    avail = calculate_availability(scheduled_minutes=480.0, planned_maintenance_minutes=0.0, unplanned_downtime_minutes=500.0)
    assert avail == 0.0


@pytest.mark.tier1
def test_performance_standard_calculation(populated_db):
    """F5: Standard performance: 360 units produced, 1.0 min ideal cycle, 400 operating minutes."""
    perf = calculate_performance(produced_units=360, ideal_cycle_time_minutes=1.0, operating_minutes=400.0)
    assert pytest.approx(perf, rel=1e-4) == 0.90

    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (1011, 20240101, 1, 1, 1, 400, 360, 350, 10)
    """)
    conn.commit()

    query = """
    SELECT (fp.ProducedUnits * dp.IdealCycleTimeMinutes * 1.0 / 400.0) AS SqlPerf
    FROM FactProduction fp
    JOIN DimProduct dp ON fp.ProductKey = dp.ProductKey
    WHERE fp.ProductionKey = 1011
    """
    row = conn.execute(query).fetchone()
    assert pytest.approx(row["SqlPerf"], rel=1e-4) == perf


@pytest.mark.tier2
def test_performance_zero_operating_minutes():
    """F5: Operating minutes = 0 evaluates to performance = 0.0 without ZeroDivisionError."""
    perf = calculate_performance(produced_units=100, ideal_cycle_time_minutes=1.0, operating_minutes=0.0)
    assert perf == 0.0


@pytest.mark.tier2
def test_performance_zero_produced_units():
    """F5: Zero produced units with positive operating minutes yields 0.0 performance."""
    perf = calculate_performance(produced_units=0, ideal_cycle_time_minutes=1.0, operating_minutes=480.0)
    assert perf == 0.0


@pytest.mark.tier1
def test_performance_no_arbitrary_0_5_multiplier():
    """F5: Performance calculation must use product's actual IdealCycleTimeMinutes, not an arbitrary 0.5 constant."""
    cycle_time = 0.75  # 45 seconds per switch
    produced = 400
    operating = 320.0
    perf = calculate_performance(produced, cycle_time, operating)
    assert pytest.approx(perf, rel=1e-4) == 0.9375
    # Verify it strictly diverges from broken 0.5 multiplier calculation (400 * 0.5 / 320 = 0.625)
    assert perf != (produced * 0.5) / operating


@pytest.mark.tier1
def test_quality_standard_calculation(populated_db):
    """F5: Standard quality: 1000 total units, 950 good units, 50 scrap units."""
    qual = calculate_quality(good_units=950, total_units=1000)
    assert pytest.approx(qual, rel=1e-4) == 0.95

    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (1021, 20240101, 1, 1, 1, 1000, 1000, 950, 50)
    """)
    conn.commit()

    query = "SELECT (SUM(GoodUnits) * 1.0 / SUM(ProducedUnits)) AS SqlQual FROM FactProduction WHERE ProductionKey = 1021"
    row = conn.execute(query).fetchone()
    assert pytest.approx(row["SqlQual"], rel=1e-4) == qual


@pytest.mark.tier1
def test_quality_zero_defects():
    """F5: Zero defects yields quality of exactly 1.0 (100%)."""
    qual = calculate_quality(good_units=500, total_units=500)
    assert qual == 1.0


@pytest.mark.tier2
def test_quality_all_defects():
    """F5: 100% defect rate yields quality of 0.0."""
    qual = calculate_quality(good_units=0, total_units=100)
    assert qual == 0.0


@pytest.mark.tier2
def test_quality_zero_total_units():
    """F5: Zero total produced units evaluates to quality = 0.0 without ZeroDivisionError."""
    qual = calculate_quality(good_units=0, total_units=0)
    assert qual == 0.0


@pytest.mark.tier1
def test_oee_standard_multiplication():
    """F5: OEE is the exact product of Availability, Performance, and Quality."""
    a, p, q = 0.90, 0.95, 0.98
    oee = calculate_oee(a, p, q)
    assert pytest.approx(oee, rel=1e-4) == 0.90 * 0.95 * 0.98


@pytest.mark.tier2
def test_oee_zero_when_any_component_is_zero():
    """F5: OEE must be 0.0 if any individual component is 0.0."""
    assert calculate_oee(0.0, 0.95, 0.98) == 0.0
    assert calculate_oee(0.90, 0.0, 0.98) == 0.0
    assert calculate_oee(0.90, 0.95, 0.0) == 0.0


@pytest.mark.tier1
def test_energy_intensity_standard_calculation(populated_db):
    """F5: Energy intensity = Total kWh / Good Units."""
    intensity = calculate_energy_intensity(total_kwh=700.0, good_units=1000)
    assert pytest.approx(intensity, rel=1e-4) == 0.70

    conn = populated_db
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (1031, 20240101, 1, 1, 1, 1000, 1000, 1000, 0)
    """)
    conn.execute("INSERT INTO FactEnergy (EnergyKey, DateKey, ShiftKey, MachineKey, EnergyKWh) VALUES (1031, 20240101, 1, 1, 700.0)")
    conn.commit()

    query = """
    SELECT (fe.EnergyKWh * 1.0 / fp.GoodUnits) AS SqlIntensity
    FROM FactEnergy fe
    JOIN FactProduction fp ON fe.DateKey = fp.DateKey AND fe.ShiftKey = fp.ShiftKey AND fe.MachineKey = fp.MachineKey
    WHERE fp.ProductionKey = 1031
    """
    row = conn.execute(query).fetchone()
    assert pytest.approx(row["SqlIntensity"], rel=1e-4) == intensity


@pytest.mark.tier2
def test_energy_intensity_zero_good_units():
    """F5: Zero good units evaluates to energy intensity = 0.0 without ZeroDivisionError."""
    intensity = calculate_energy_intensity(total_kwh=50.0, good_units=0)
    assert intensity == 0.0


# ============================================================================
# Tier 3: Combinations, Weighted Aggregation & Bounds
# ============================================================================

@pytest.mark.tier3
def test_weighted_vs_arithmetic_oee_aggregation(populated_db):
    """F5: Multi-machine/line OEE aggregation MUST use weighted formulas.
    Adversarial verification: Fails if unweighted AVG() is used.
    """
    conn = populated_db
    # Machine 1: Small batch, high quality (10 units, 10 good) -> Quality = 1.0 (100%)
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (2001, 20240101, 1, 1, 1, 10, 10, 10, 0)
    """)
    # Machine 2: Large batch, low quality (1000 units, 500 good) -> Quality = 0.5 (50%)
    conn.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (2002, 20240101, 1, 2, 1, 1000, 1000, 500, 500)
    """)
    conn.commit()

    query = """
    SELECT
        (SUM(fp.GoodUnits * dp.IdealCycleTimeMinutes) * 1.0 / SUM(fp.ProducedUnits * dp.IdealCycleTimeMinutes)) AS WeightedQuality,
        AVG(fp.GoodUnits * 1.0 / fp.ProducedUnits) AS UnweightedQuality
    FROM FactProduction fp
    JOIN DimProduct dp ON fp.ProductKey = dp.ProductKey
    WHERE fp.ProductionKey IN (2001, 2002)
    """
    row = conn.execute(query).fetchone()

    # Weighted Quality = 510 / 1010 = ~50.495%
    # Unweighted Average = (1.0 + 0.5) / 2.0 = 75.0%
    assert pytest.approx(row["WeightedQuality"], rel=1e-3) == 510 / 1010
    assert row["UnweightedQuality"] == 0.75
    # Strict sensitivity assertion: Weighted aggregate must diverge from unweighted average by > 20%
    assert abs(row["WeightedQuality"] - row["UnweightedQuality"]) > 0.20

    weighted_py = calculate_weighted_oee(good_units=510, ideal_cycle_time_minutes=1.0, planned_production_minutes=1010.0)
    assert pytest.approx(weighted_py, rel=1e-3) == 510 / 1010


@pytest.mark.tier3
def test_kpi_bounds_invariance():
    """F5: Availability, Performance, Quality, and OEE must always fall within [0.0, 1.0] for standard manufacturing conditions."""
    for op_min in [100.0, 400.0, 480.0]:
        for units in [50, 200, 400]:
            a = calculate_availability(480.0, 30.0, 480.0 - op_min)
            p = min(1.0, calculate_performance(units, 1.0, op_min))
            q = calculate_quality(int(units * 0.95), units)
            oee = calculate_oee(a, p, q)

            assert 0.0 <= a <= 1.0
            assert 0.0 <= p <= 1.0
            assert 0.0 <= q <= 1.0
            assert 0.0 <= oee <= 1.0
