import pathlib
import sqlite3
import pandas as pd
from src.config import BASE_DIR

DB_PATH = BASE_DIR / "data" / "factorypulse.db"

def _load_csv_to_table(conn: sqlite3.Connection, table: str, csv_path: pathlib.Path, if_exists: str = "append"):
    df = pd.read_csv(csv_path)
    # Defensive default column population for schema extensions
    if table == "DimShift" and "ScheduledMinutes" not in df.columns:
        df["ScheduledMinutes"] = 480.0
    if table == "DimProduct":
        if "IdealCycleTimeSeconds" not in df.columns:
            df["IdealCycleTimeSeconds"] = 270.0
        if "IdealCycleTimeMinutes" not in df.columns:
            df["IdealCycleTimeMinutes"] = 4.5
    # Align dataframe columns with existing SQLite table schema to prevent column mismatch
    cur = conn.execute(f"PRAGMA table_info({table})")
    table_cols = {row[1] for row in cur.fetchall()}
    if table_cols:
        cols_to_load = [c for c in df.columns if c in table_cols]
        df = df[cols_to_load]
    df.to_sql(table, conn, if_exists=if_exists, index=False)
    print(f"Loaded {len(df)} rows into {table}")

def _create_schema(conn: sqlite3.Connection):
    schema_path = BASE_DIR / "sql" / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    print("Database schema created")

def load_sqlite(
    db_path: pathlib.Path | None = None,
    curated_dir: pathlib.Path | None = None,
    raw_dir: pathlib.Path | None = None,
) -> None:
    """Create the SQLite database, enforce foreign keys, and populate all tables.
    Assumes curated fact tables are present in ``curated_dir`` and dimension CSVs
    are in ``raw_dir`` (or ``raw_dir / 'faulty'``).
    """
    if db_path is None:
        db_path = DB_PATH
    db_path = pathlib.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if curated_dir is None:
        curated_dir = BASE_DIR / "data" / "curated"
    curated_dir = pathlib.Path(curated_dir)

    if raw_dir is None:
        raw_dir = BASE_DIR / "data" / "raw" / "faulty"
    raw_dir = pathlib.Path(raw_dir)
    if raw_dir.name != "faulty" and (raw_dir / "faulty").exists():
        dim_dir = raw_dir / "faulty"
    else:
        dim_dir = raw_dir

    # Remove existing DB to allow schema recreation
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
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
    for dim in ["DimDate", "DimShift", "DimLine", "DimMachine", "DimProduct", "DimReason"]:
        dim_path = dim_dir / f"{dim}.csv"
        if not dim_path.exists() and (dim_dir.parent / f"{dim}.csv").exists():
            dim_path = dim_dir.parent / f"{dim}.csv"
        _load_csv_to_table(conn, dim, dim_path, if_exists="append")
    for fact in ["FactProduction", "FactDowntime", "FactQuality", "FactEnergy", "FactSensor", "FactDQExceptions"]:
        _load_csv_to_table(conn, fact, curated_dir / f"{fact}.csv", if_exists="append")
    conn.commit()
    print(f"SQLite database created at {db_path}")
    conn.close()

if __name__ == "__main__":
    load_sqlite()
