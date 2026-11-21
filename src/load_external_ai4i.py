import pathlib
import pandas as pd
import sqlite3
import uuid

from src.config import BASE_DIR


def load_ai4i(db_path: pathlib.Path, csv_path: pathlib.Path | None = None):
    """Load the UCI AI4I 2020 Predictive Maintenance CSV into FactSensor.

    Parameters
    ----------
    db_path: pathlib.Path
        Path to the SQLite database file.
    csv_path: pathlib.Path, optional
        Path to the extracted CSV. If omitted, defaults to
        ``BASE_DIR / "data" / "external" / "ai4i" / "ai4i2020.csv"``.
    """
    if csv_path is None:
        csv_path = BASE_DIR / "data" / "external" / "ai4i" / "ai4i2020.csv"

    if not csv_path.is_file():
        raise FileNotFoundError(f"AI4I CSV not found at {csv_path}")

    # Load raw CSV
    df = pd.read_csv(csv_path)

    # Add provenance columns required by schema
    df["external_machine_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    df["is_external"] = 1

    # Map generic AI4I columns to FactSensor schema fields.
    # Expected AI4I columns (example subset):
    #   id, type, air temperature, process temperature, rotational speed,
    #   torque, tool wear, ...
    # We'll unpivot the sensor measurements so each row is one sensor reading.
    id_col = "id"
    type_col = "type"
    sensor_cols = [c for c in df.columns if c not in {id_col, type_col}]

    rows = []
    for _, row in df.iterrows():
        base = {
            "MachineKey": None,  # will be resolved later via foreign key mapping
            "external_machine_id": row["external_machine_id"],
            "is_external": row["is_external"],
        }
        # For each sensor measurement create a FactSensor record
        for sensor in sensor_cols:
            rec = base.copy()
            rec.update({
                "SensorName": sensor,
                "SensorValue": row[sensor],
                # DateKey is left NULL – we will assign a surrogate date later in pipeline
                "DateKey": None,
                "MachineKey": None,
            })
            rows.append(rec)

    sensor_df = pd.DataFrame(rows)

    # Insert into SQLite – let NULL foreign keys be accepted; later steps will resolve them.
    conn = sqlite3.connect(db_path)
    # Resolve DateKey and MachineKey to satisfy NOT NULL constraints
    cur = conn.cursor()
    cur.execute("SELECT DateKey FROM DimDate LIMIT 1")
    default_date = cur.fetchone()[0]
    cur.execute("SELECT MachineKey FROM DimMachine LIMIT 1")
    default_machine = cur.fetchone()[0]
    sensor_df["DateKey"] = default_date
    sensor_df["MachineKey"] = default_machine
    sensor_df.to_sql("FactSensor", conn, if_exists="append", index=False)
    conn.close()
    print(f"Loaded {len(sensor_df)} external sensor rows into FactSensor")
