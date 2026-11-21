"""UCI AI4I 2020 Predictive Maintenance Dataset Ingestion & Provenance.

Dataset Provenance Disclosure:
This module ingests the synthetic UCI AI4I 2020 predictive maintenance benchmark
dataset (Dua & Graff 2019 / Matzka 2020), NOT real ABB telemetry. The source CSV
at data/external/ai4i/ai4i2020.csv is preserved strictly unmodified.
"""

import pathlib
import sqlite3
import pandas as pd

from src.config import BASE_DIR

# Strictly the 5 continuous numeric sensor columns from UCI AI4I 2020
AI4I_NUMERIC_SENSORS = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]

# Synthetic benchmark provenance attribution
DATASET_PROVENANCE_DISCLOSURE = (
    "synthetic UCI AI4I 2020 predictive maintenance benchmark dataset, not real ABB telemetry"
)


def load_ai4i(db_path: pathlib.Path, csv_path: pathlib.Path | None = None) -> int:
    """Load the UCI AI4I 2020 Predictive Maintenance CSV into FactSensor.

    Preserves source data unmodified, extracts strictly the 5 numeric sensor columns,
    maps deterministic device IDs (AI4I-{Type}-{UDI:05d}), preserves original observation
    ID (UDI), and distributes observations deterministically across dates and machines.

    Parameters
    ----------
    db_path : pathlib.Path
        Path to the SQLite database file.
    csv_path : pathlib.Path, optional
        Path to the AI4I source CSV. Defaults to
        ``BASE_DIR / "data" / "external" / "ai4i" / "ai4i2020.csv"``.

    Returns
    -------
    int
        Total count of sensor rows inserted into FactSensor (exactly 50,000).
    """
    if csv_path is None:
        csv_path = BASE_DIR / "data" / "external" / "ai4i" / "ai4i2020.csv"
    csv_path = pathlib.Path(csv_path)

    if not csv_path.is_file():
        raise FileNotFoundError(f"AI4I source CSV not found at {csv_path}")

    # Read authentic source dataset unmodified
    df = pd.read_csv(csv_path)

    # Validate exact headers
    required_headers = {"UDI", "Product ID", "Type"} | set(AI4I_NUMERIC_SENSORS)
    missing = required_headers - set(df.columns)
    if missing:
        raise ValueError(f"AI4I dataset missing required columns: {missing}")

    # Connect to SQLite to retrieve available dimensions
    db_path = pathlib.Path(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT DateKey FROM DimDate ORDER BY DateKey")
    date_keys = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT MachineKey FROM DimMachine ORDER BY MachineKey")
    machine_keys = [r[0] for r in cur.fetchall()]

    if not date_keys:
        raise ValueError("Cannot load AI4I: DimDate is empty in target SQLite database.")
    if not machine_keys:
        raise ValueError("Cannot load AI4I: DimMachine is empty in target SQLite database.")

    num_dates = len(date_keys)
    num_machines = len(machine_keys)

    # Determine starting SensorKey to maintain sequence and integrity
    cur.execute("SELECT COALESCE(MAX(SensorKey), 0) FROM FactSensor")
    next_key = cur.fetchone()[0] + 1

    # Unpivot strictly the 5 numeric sensor columns
    # 10,000 observations * 5 sensors = 50,000 FactSensor rows
    rows = []
    for _, row in df.iterrows():
        udi = int(row["UDI"])
        dev_type = str(row["Type"]).strip()
        # Deterministic identifier: AI4I-{Type}-{UDI:05d}
        device_id = f"AI4I-{dev_type}-{udi:05d}"

        # Deterministic distribution across available dates and machines
        date_key = date_keys[(udi - 1) % num_dates]
        machine_key = machine_keys[(udi - 1) % num_machines]

        for sensor in AI4I_NUMERIC_SENSORS:
            sensor_val = float(row[sensor])
            rows.append({
                "SensorKey": next_key,
                "DateKey": date_key,
                "MachineKey": machine_key,
                "SensorName": sensor,
                "SensorValue": sensor_val,
                "external_machine_id": device_id,
                "is_external": 1,
                "UDI": udi,
            })
            next_key += 1

    sensor_df = pd.DataFrame(rows)
    sensor_df.to_sql("FactSensor", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

    total_inserted = len(sensor_df)
    print(
        f"Loaded {total_inserted} external sensor rows into FactSensor "
        f"({DATASET_PROVENANCE_DISCLOSURE})."
    )
    return total_inserted
