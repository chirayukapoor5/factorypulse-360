import pathlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import uuid

from src.config import (
    BASE_DIR,
    DEFAULT_SEED,
    DEFAULT_DAYS,
    NUM_LINES,
    CELLS_PER_LINE,
    SHIFTS_PER_DAY,
    PRODUCT_FAMILIES,
    TOTAL_MACHINES,
    SHIFT_IDS,
    LINE_IDS,
    CELL_IDS,
    MACHINE_IDS,
    REASON_DOWNTIME,
    REASON_DEFECT,
)

# Helper to create date dimension
def build_dim_date(start_date: datetime, days: int):
    rows = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        rows.append({
            "DateKey": int(d.strftime("%Y%m%d")),
            "Date": d.date().isoformat(),
            "Year": d.year,
            "Month": d.month,
            "Day": d.day,
            "Week": d.isocalendar()[1],
            "IsWeekend": d.weekday() >= 5,
        })
    return pd.DataFrame(rows)


def build_dim_shift():
    rows = []
    for sid in SHIFT_IDS:
        rows.append({
            "ShiftKey": sid,
            "ShiftId": sid,
            "ShiftName": f"Shift {sid}",
            "StartTime": "06:00:00" if sid == 1 else "14:00:00",
            "EndTime": "14:00:00" if sid == 1 else "22:00:00",
        })
    return pd.DataFrame(rows)


def build_dim_line():
    rows = []
    for lid in LINE_IDS:
        rows.append({"LineKey": lid, "LineId": lid, "LineName": f"Line {lid}"})
    return pd.DataFrame(rows)


def build_dim_machine():
    rows = []
    for idx, (line, cell, m) in enumerate(MACHINE_IDS, start=1):
        rows.append({
            "MachineKey": idx,
            "MachineId": f"M{line}{cell}{m}",
            "LineKey": line,
            "CellId": cell,
            "MachineName": f"Machine {line}{cell}{m}",
        })
    return pd.DataFrame(rows)


def build_dim_product():
    rows = []
    for idx, fam in enumerate(PRODUCT_FAMILIES, start=1):
        rows.append({
            "ProductKey": idx,
            "ProductId": f"P{idx}",
            "ProductFamily": fam,
            "ProductName": f"{fam} Switch",
        })
    return pd.DataFrame(rows)


def build_dim_reason():
    rows = []
    # Downtime reasons
    for idx, r in enumerate(REASON_DOWNTIME, start=1):
        rows.append({"ReasonKey": idx, "ReasonCode": r, "ReasonCategory": "Downtime", "ReasonDescription": f"{r} reason"})
    # Defect reasons – continue indexing
    offset = len(REASON_DOWNTIME)
    for i, r in enumerate(REASON_DEFECT, start=1):
        rows.append({"ReasonKey": offset + i, "ReasonCode": r, "ReasonCategory": "Defect", "ReasonDescription": f"{r} reason"})
    return pd.DataFrame(rows)


def simulate_production(start_date: datetime, days: int, seed: int):
    np.random.seed(seed)
    # Dimensions
    dim_date = build_dim_date(start_date, days)
    dim_shift = build_dim_shift()
    dim_line = build_dim_line()
    dim_machine = build_dim_machine()
    dim_product = build_dim_product()
    dim_reason = build_dim_reason()

    # Prepare empty list for fact rows
    prod_rows = []
    downtime_rows = []
    quality_rows = []
    energy_rows = []
    sensor_rows = []

    # Mapping helpers
    machine_key_lookup = {(row["LineKey"], row["CellId"], int(row["MachineName"].split()[-1][-1])): row["MachineKey"] for _, row in dim_machine.iterrows()}
    product_key_lookup = {row["ProductFamily"]: row["ProductKey"] for _, row in dim_product.iterrows()}
    reason_key_lookup = {row["ReasonCode"]: row["ReasonKey"] for _, row in dim_reason.iterrows()}

    # Synthetic scenario flags
    # A: Elevated downtime in Line 2, Cell 1, Shift 2 (40% extra downtime)
    # B: Higher rejection in Product Family_E (30% higher reject rate)
    # C: Increased energy intensity in Line 3, Cell 2 (25% more kWh per unit)

    for day_offset in range(days):
        cur_date = start_date + timedelta(days=day_offset)
        date_key = int(cur_date.strftime("%Y%m%d"))
        for shift in SHIFT_IDS:
            for line in LINE_IDS:
                for cell in range(1, CELLS_PER_LINE + 1):
                    # Each cell has 4 machines, iterate by machine index
                    for m_idx in range(1, 5):
                        machine_key = machine_key_lookup[(line, cell, m_idx)]
                        # Choose product randomly
                        product_family = np.random.choice(PRODUCT_FAMILIES, p=[0.2]*5)
                        product_key = product_key_lookup[product_family]
                        # Targets and ideal cycle times
                        target_units = np.random.randint(80, 121)  # per shift per machine
                        # Simulate production output with some variance
                        produced_units = max(0, int(target_units * np.random.normal(0.95, 0.05)))
                        # Base reject rate 5% except scenario B
                        base_reject_rate = 0.05
                        if product_family == "Family_E":
                            base_reject_rate *= 1.30  # scenario B
                        rejected_units = int(produced_units * base_reject_rate)
                        good_units = produced_units - rejected_units

                        prod_rows.append({
                            "ProductionKey": None,
                            "DateKey": date_key,
                            "ShiftKey": shift,
                            "MachineKey": machine_key,
                            "ProductKey": product_key,
                            "TargetUnits": target_units,
                            "ProducedUnits": produced_units,
                            "GoodUnits": good_units,
                            "RejectedUnits": rejected_units,
                        })

                        # Downtime – base 5 minutes per shift, add random
                        base_downtime = np.random.exponential(scale=5.0)
                        if line == 2 and cell == 1 and shift == 2:
                            base_downtime *= 1.40  # scenario A
                        downtime_minutes = max(0.0, base_downtime)
                        reason = np.random.choice(REASON_DOWNTIME, p=[0.4,0.3,0.1,0.1,0.1])
                        downtime_rows.append({
                            "DowntimeKey": None,
                            "DateKey": date_key,
                            "ShiftKey": shift,
                            "MachineKey": machine_key,
                            "ReasonKey": reason_key_lookup[reason],
                            "DowntimeMinutes": downtime_minutes,
                            "Planned": 1 if reason == "Planned_Maintenance" else 0,
                        })

                        # Quality defects – map to defect reasons
                        defect_reason = np.random.choice(REASON_DEFECT, p=[0.7,0.2,0.1])
                        quality_rows.append({
                            "QualityKey": None,
                            "DateKey": date_key,
                            "ShiftKey": shift,
                            "MachineKey": machine_key,
                            "ProductKey": product_key,
                            "DefectReasonKey": reason_key_lookup[defect_reason],
                            "DefectCount": rejected_units,
                        })

                        # Energy – base 0.7 kWh per good unit, plus variance
                        energy_per_unit = 0.7
                        if line == 3 and cell == 2:
                            energy_per_unit *= 1.25  # scenario C
                        energy_kwh = good_units * energy_per_unit * np.random.normal(1.0, 0.05)
                        energy_rows.append({
                            "EnergyKey": None,
                            "DateKey": date_key,
                            "ShiftKey": shift,
                            "MachineKey": machine_key,
                            "EnergyKWh": max(0.0, energy_kwh),
                        })

                        # Sensor data – generate 3 generic sensors per machine per shift
                        for sensor_name in ["Temp", "Vibration", "Pressure"]:
                            sensor_value = np.random.normal(50, 10)
                            sensor_rows.append({
                                "SensorKey": None,
                                "DateKey": date_key,
                                "MachineKey": machine_key,
                                "SensorName": sensor_name,
                                "SensorValue": sensor_value,
                                "external_machine_id": None,
                                "is_external": 0,
                            })

    # Convert to DataFrames
    df_prod = pd.DataFrame(prod_rows)
    df_downtime = pd.DataFrame(downtime_rows)
    df_quality = pd.DataFrame(quality_rows)
    df_energy = pd.DataFrame(energy_rows)
    df_sensor = pd.DataFrame(sensor_rows)

    # Assign surrogate primary keys
    for df, key in [(df_prod, "ProductionKey"), (df_downtime, "DowntimeKey"),
                    (df_quality, "QualityKey"), (df_energy, "EnergyKey"),
                    (df_sensor, "SensorKey")]:
        df[key] = range(1, len(df) + 1)

    # Output directories
    raw_dir = BASE_DIR / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dim_date = build_dim_date(start_date, days)
    # Write CSVs (no index)
    dim_date.to_csv(raw_dir / "DimDate.csv", index=False)
    dim_shift.to_csv(raw_dir / "DimShift.csv", index=False)
    dim_line.to_csv(raw_dir / "DimLine.csv", index=False)
    dim_machine.to_csv(raw_dir / "DimMachine.csv", index=False)
    dim_product.to_csv(raw_dir / "DimProduct.csv", index=False)
    dim_reason.to_csv(raw_dir / "DimReason.csv", index=False)
    df_prod.to_csv(raw_dir / "FactProduction.csv", index=False)
    df_downtime.to_csv(raw_dir / "FactDowntime.csv", index=False)
    df_quality.to_csv(raw_dir / "FactQuality.csv", index=False)
    df_energy.to_csv(raw_dir / "FactEnergy.csv", index=False)
    df_sensor.to_csv(raw_dir / "FactSensor.csv", index=False)

    print(f"Generated raw data for {days} days into {raw_dir}")


def main():
    start = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    simulate_production(start_date=start, days=DEFAULT_DAYS, seed=DEFAULT_SEED)

if __name__ == "__main__":
    main()
