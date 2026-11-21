import pathlib
import sqlite3
import pandas as pd
from src.config import BASE_DIR

DB_PATH = BASE_DIR / "data" / "factorypulse.db"

def _load_csv_to_table(conn: sqlite3.Connection, table: str, csv_path: pathlib.Path, if_exists: str = "append"):
    df = pd.read_csv(csv_path)
    # Clean data for tables with NOT NULL constraints
    if table == "FactEnergy":
        df = df.dropna(subset=["EnergyKWh"])
    if table == "FactDQExceptions":
        # RecordIdentifier must not be null/NaN
        df = df.dropna(subset=["RecordIdentifier"])
        # Also ensure no empty strings
        df = df[df["RecordIdentifier"].astype(str).str.strip() != ""]
    df.to_sql(table, conn, if_exists=if_exists, index=False)
    print(f"Loaded {len(df)} rows into {table}")

def _create_schema(conn: sqlite3.Connection):
    schema_path = BASE_DIR / "sql" / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    print("Database schema created")

def load_sqlite():
    """Create the SQLite database, enforce foreign keys, and populate all tables.
    Assumes curated fact tables are present in ``data/curated`` and dimension CSVs
    are in ``data/raw/faulty`` (unchanged from the original raw export).
    """
    # Remove existing DB to allow schema recreation
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    _create_schema(conn)
    # Add trigger to enforce foreign key integrity for FactProduction MachineKey
    conn.executescript('''
        CREATE TRIGGER IF NOT EXISTS fk_factproduction_machinekey BEFORE INSERT ON FactProduction
        FOR EACH ROW BEGIN
            SELECT RAISE(FAIL, 'Invalid MachineKey')
            WHERE (SELECT COUNT(*) FROM DimMachine WHERE MachineKey = NEW.MachineKey) = 0;
        END;
    ''')
    dim_dir = BASE_DIR / "data" / "raw" / "faulty"
    for dim in ["DimDate", "DimShift", "DimLine", "DimMachine", "DimProduct", "DimReason"]:
        _load_csv_to_table(conn, dim, dim_dir / f"{dim}.csv", if_exists="append")
    cur_dir = BASE_DIR / "data" / "curated"
    for fact in ["FactProduction", "FactDowntime", "FactQuality", "FactEnergy", "FactSensor", "FactDQExceptions"]:
        _load_csv_to_table(conn, fact, cur_dir / f"{fact}.csv", if_exists="append")
    conn.commit()
    print(f"SQLite database created at {DB_PATH}")
    conn.close()

if __name__ == "__main__":
    load_sqlite()
