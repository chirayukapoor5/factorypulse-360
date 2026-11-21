import sqlite3
import pathlib
import pytest
from src import load_sqlite

def _setup_temp_db(tmp_path):
    # Create temporary SQLite DB
    db_path = tmp_path / "temp_factorypulse.db"
    conn = sqlite3.connect(db_path)
    # Load schema
    load_sqlite._create_schema(conn)
    # Insert minimal dimension rows required for foreign keys
    conn.execute("INSERT INTO DimMachine (MachineKey, MachineId, LineKey, CellId, MachineName) VALUES (1, 'M1', 1, 1, 'Machine 1')")
    conn.execute("INSERT INTO DimDate (DateKey, Date, Year, Month, Day, Week, IsWeekend) VALUES (20210101, '2021-01-01', 2021, 1, 1, 1, 0)")
    conn.execute("INSERT INTO DimShift (ShiftKey, ShiftId, ShiftName, StartTime, EndTime) VALUES (1, 1, 'Shift 1', '08:00', '16:00')")
    conn.execute("INSERT INTO DimProduct (ProductKey, ProductId, ProductFamily, ProductName) VALUES (1, 'P1', 'Family A', 'Product A')")
    conn.commit()
    conn.close()
    return db_path

def test_sqlite_trigger_enforces_machinekey(tmp_path):
    db_path = _setup_temp_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Valid insert should succeed
    conn.execute(
        "INSERT INTO FactProduction (DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits) VALUES (20210101, 1, 1, 1, 100, 95, 90, 5)"
    )
    conn.commit()
    # Invalid insert should raise via trigger
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO FactProduction (DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits) VALUES (20210101, 1, 999, 1, 100, 95, 90, 5)"
        )
    conn.close()
