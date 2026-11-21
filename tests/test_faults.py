import pathlib, shutil
import pandas as pd

from src import inject_faults, config

def test_fault_injection_counts(tmp_path):
    # Backup original raw data
    raw_dir = config.BASE_DIR / "data" / "raw"
    backup = tmp_path / "raw_backup"
    shutil.copytree(raw_dir, backup)
    # Run fault injection
    inject_faults.inject_faults()
    faulty_dir = raw_dir / "faulty"
    # Ensure each fact file exists in faulty directory
    for fact in ["FactProduction.csv", "FactDowntime.csv", "FactQuality.csv", "FactEnergy.csv", "FactSensor.csv"]:
        assert (faulty_dir / fact).exists(), f"{fact} not created"
    # Verify that row counts are >= original (due to possible duplicates)
    for fact in ["FactProduction.csv", "FactDowntime.csv", "FactQuality.csv", "FactEnergy.csv", "FactSensor.csv"]:
        orig = pd.read_csv(backup / fact)
        faulty = pd.read_csv(faulty_dir / fact)
        assert faulty.shape[0] >= orig.shape[0], f"Row count for {fact} decreased"
