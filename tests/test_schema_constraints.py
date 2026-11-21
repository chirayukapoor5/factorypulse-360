import sqlite3
import pytest


@pytest.mark.tier1
def test_pragma_foreign_keys_enabled(isolated_db):
    """F4: SQLite foreign key enforcement must be active (PRAGMA foreign_keys = 1)."""
    cur = isolated_db.execute("PRAGMA foreign_keys;")
    result = cur.fetchone()[0]
    assert result == 1, "Foreign key pragma is not enabled"


@pytest.mark.tier1
def test_dim_date_pk_uniqueness(isolated_db):
    """F4: DimDate primary key (DateKey) must enforce uniqueness."""
    isolated_db.execute("""
        INSERT INTO DimDate (DateKey, Date, Year, Month, Day, Week, IsWeekend)
        VALUES (20240101, '2024-01-01', 2024, 1, 1, 1, 0)
    """)
    isolated_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        isolated_db.execute("""
            INSERT INTO DimDate (DateKey, Date, Year, Month, Day, Week, IsWeekend)
            VALUES (20240101, '2024-01-01', 2024, 1, 1, 1, 0)
        """)


@pytest.mark.tier1
def test_dim_machine_pk_uniqueness(populated_db):
    """F4: DimMachine primary key (MachineKey) must enforce uniqueness."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO DimMachine (MachineKey, MachineId, LineKey, CellId, MachineName)
            VALUES (1, 'M111', 1, 1, 'Duplicate Machine')
        """)


@pytest.mark.tier1
def test_dim_product_pk_uniqueness(populated_db):
    """F4: DimProduct primary key (ProductKey) must enforce uniqueness."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO DimProduct (ProductKey, ProductId, ProductFamily, ProductName)
            VALUES (1, 'P1_DUP', 'Family_A', 'Duplicate Product')
        """)


@pytest.mark.tier1
def test_dim_shift_pk_uniqueness(populated_db):
    """F4: DimShift primary key (ShiftKey) must enforce uniqueness."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO DimShift (ShiftKey, ShiftId, ShiftName, StartTime, EndTime)
            VALUES (1, 1, 'Duplicate Shift', '06:00:00', '14:00:00')
        """)


@pytest.mark.tier1
def test_dim_line_pk_uniqueness(populated_db):
    """F4: DimLine primary key (LineKey) must enforce uniqueness."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO DimLine (LineKey, LineId, LineName)
            VALUES (1, 1, 'Duplicate Line')
        """)


@pytest.mark.tier1
def test_dim_reason_pk_uniqueness(populated_db):
    """F4: DimReason primary key (ReasonKey) must enforce uniqueness."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO DimReason (ReasonKey, ReasonCode, ReasonCategory, ReasonDescription)
            VALUES (1, 'DUP_REASON', 'Downtime', 'Duplicate reason')
        """)


@pytest.mark.tier1
def test_fact_production_valid_fk_insert(populated_db):
    """F4: FactProduction successfully inserts record referencing valid dimensions."""
    populated_db.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (101, 20240101, 1, 1, 1, 100, 95, 90, 5)
    """)
    populated_db.commit()

    cur = populated_db.execute("SELECT COUNT(*) FROM FactProduction WHERE ProductionKey = 101")
    assert cur.fetchone()[0] == 1


@pytest.mark.tier2
def test_fact_production_invalid_machine_fk_rejected(populated_db):
    """F4: FactProduction must reject non-existent MachineKey = 9999."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
            VALUES (102, 20240101, 1, 9999, 1, 100, 95, 90, 5)
        """)


@pytest.mark.tier2
def test_fact_production_invalid_date_fk_rejected(populated_db):
    """F4: FactProduction must reject non-existent DateKey = 19000101."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
            VALUES (103, 19000101, 1, 1, 1, 100, 95, 90, 5)
        """)


@pytest.mark.tier2
def test_fact_downtime_invalid_reason_fk_rejected(populated_db):
    """F4: FactDowntime must reject non-existent ReasonKey = 9999."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactDowntime (DowntimeKey, DateKey, ShiftKey, MachineKey, ReasonKey, DowntimeMinutes, Planned)
            VALUES (101, 20240101, 1, 1, 9999, 30.0, 0)
        """)


@pytest.mark.tier2
def test_fact_energy_invalid_machine_fk_rejected(populated_db):
    """F4: FactEnergy must reject non-existent MachineKey = 9999."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactEnergy (EnergyKey, DateKey, ShiftKey, MachineKey, EnergyKWh)
            VALUES (101, 20240101, 1, 9999, 45.5)
        """)


@pytest.mark.tier2
def test_fact_production_not_null_constraints(populated_db):
    """F4: FactProduction must enforce NOT NULL on critical metric and foreign key columns."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
            VALUES (104, NULL, 1, 1, 1, 100, 95, 90, 5)
        """)


@pytest.mark.tier2
def test_fact_sensor_numeric_value_not_null(populated_db):
    """F4: FactSensor must enforce NOT NULL on SensorValue."""
    with pytest.raises(sqlite3.IntegrityError):
        populated_db.execute("""
            INSERT INTO FactSensor (SensorKey, DateKey, MachineKey, SensorName, SensorValue, is_external)
            VALUES (101, 20240101, 1, 'Temperature', NULL, 0)
        """)


@pytest.mark.tier3
def test_fact_production_unit_conservation(populated_db):
    """F4: Unit conservation check: GoodUnits + RejectedUnits == ProducedUnits."""
    # Insert compliant row
    populated_db.execute("""
        INSERT INTO FactProduction (ProductionKey, DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits)
        VALUES (105, 20240101, 1, 1, 1, 100, 100, 95, 5)
    """)
    cur = populated_db.execute("SELECT ProducedUnits, GoodUnits, RejectedUnits FROM FactProduction WHERE ProductionKey = 105")
    row = cur.fetchone()
    assert row["GoodUnits"] + row["RejectedUnits"] == row["ProducedUnits"]


@pytest.mark.tier1
def test_fact_dq_exceptions_schema_and_insert(populated_db):
    """F4: FactDQExceptions must accept properly formatted quarantine records."""
    populated_db.execute("""
        INSERT INTO FactDQExceptions (ExceptionKey, SourceTable, RecordIdentifier, RuleViolated, Severity, Disposition, Description)
        VALUES (1, 'FactProduction', '1001', 'DuplicatePrimaryKey', 'ERROR', 'Quarantine', 'Duplicate primary key detected')
    """)
    populated_db.commit()

    cur = populated_db.execute("SELECT COUNT(*) FROM FactDQExceptions WHERE ExceptionKey = 1")
    assert cur.fetchone()[0] == 1
