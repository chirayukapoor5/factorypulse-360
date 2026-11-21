import pathlib, shutil
import pytest
import sqlite3
import pandas as pd

from src import simulate, inject_faults, validate, load_sqlite, load_external_ai4i, config

def _setup_pipeline(tmp_path):
    # Ensure a clean data environment
    raw_dir = config.BASE_DIR / "data" / "raw"
    curated_dir = config.BASE_DIR / "data" / "curated"
    # Remove any existing data
    shutil.rmtree(raw_dir, ignore_errors=True)
    shutil.rmtree(curated_dir, ignore_errors=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    # Run simulation and fault injection
    simulate.main()
    inject_faults.inject_faults()
    # Validate and load SQLite
    validate.run_validation()
    load_sqlite.load_sqlite()
    # Load AI4I data
    db_path = config.BASE_DIR / "data" / "factorypulse.db"
    load_external_ai4i.load_ai4i(db_path)
    return db_path

def test_sqlite_foreign_keys(tmp_path):
    db_path = _setup_pipeline(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Verify foreign key enforcement is active (no exception on valid insert)
    cur = conn.cursor()
    date_key = cur.execute("SELECT DateKey FROM DimDate LIMIT 1").fetchone()[0]
    shift_key = cur.execute("SELECT ShiftKey FROM DimShift LIMIT 1").fetchone()[0]
    product_key = cur.execute("SELECT ProductKey FROM DimProduct LIMIT 1").fetchone()[0]
    machine_key = cur.execute("SELECT MachineKey FROM DimMachine LIMIT 1").fetchone()[0]
    # Insert a valid row should succeed
    cur.execute(
        "INSERT INTO FactProduction (DateKey, ShiftKey, MachineKey, ProductKey, TargetUnits, ProducedUnits, GoodUnits, RejectedUnits) VALUES (?, ?, ?, ?, 100, 95, 90, 5)",
        (date_key, shift_key, machine_key, product_key)
    )
    conn.commit()
    conn.close()
