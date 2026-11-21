import pathlib, shutil
import pandas as pd

from src import config, simulate

def _clean_raw():
    raw_dir = config.BASE_DIR / "data" / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

def test_simulation_determinism(tmp_path):
    # Use temporary directory for raw data to avoid polluting repo
    original_raw = config.BASE_DIR / "data" / "raw"
    backup = tmp_path / "backup_raw"
    if original_raw.exists():
        shutil.move(str(original_raw), str(backup))
    # First run
    config.DEFAULT_SEED = 12345
    config.DEFAULT_DAYS = 5
    simulate.main()
    # Capture row counts
    counts1 = {}
    for f in (config.BASE_DIR / "data" / "raw").glob("Fact*.csv"):
        df = pd.read_csv(f)
        counts1[f.name] = df.shape[0]
    # Clean and run again
    shutil.rmtree(config.BASE_DIR / "data" / "raw")
    (config.BASE_DIR / "data" / "raw").mkdir(parents=True, exist_ok=True)
    simulate.main()
    counts2 = {}
    for f in (config.BASE_DIR / "data" / "raw").glob("Fact*.csv"):
        df = pd.read_csv(f)
        counts2[f.name] = df.shape[0]
    # Restore backup if existed
    if backup.exists():
        shutil.rmtree(original_raw, ignore_errors=True)
        shutil.move(str(backup), str(original_raw))
    assert counts1 == counts2, "Simulation output is not deterministic"
