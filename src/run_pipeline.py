import argparse
import pathlib
import sys

from src import simulate, inject_faults, validate, load_sqlite, load_external_ai4i
from src.config import BASE_DIR, DEFAULT_SEED, DEFAULT_DAYS

def main():
    parser = argparse.ArgumentParser(description="Run the full FactoryPulse 360 data pipeline")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for deterministic generation")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of days to simulate")
    args = parser.parse_args()

    # Step 1: generate raw simulation data
    print("[pipeline] Running factory simulation...")
    # The simulate module reads DEFAULT_SEED/DAYS from config, so we temporarily override them
    # (In a real implementation we would refactor but for now we set env variables)
    # However, simulate.main uses the constants directly; we can monkey‑patch via config module
    from src import config as cfg
    cfg.DEFAULT_SEED = args.seed
    cfg.DEFAULT_DAYS = args.days
    simulate.main()

    # Step 2: inject deterministic data‑quality faults
    print("[pipeline] Injecting data‑quality faults...")
    inject_faults.inject_faults()

    # Step 3: validate and produce curated tables + exception register
    print("[pipeline] Validating data...")
    validate.run_validation()

    # Step 4: load curated data into SQLite
    print("[pipeline] Loading curated data into SQLite...")
    load_sqlite.load_sqlite()

    # Step 5: ingest external AI4I dataset (marks rows as external)
    print("[pipeline] Loading external AI4I dataset into FactSensor...")
    db_path = BASE_DIR / "data" / "factorypulse.db"
    load_external_ai4i.load_ai4i(db_path)

    print("[pipeline] Pipeline completed successfully.")

if __name__ == "__main__":
    main()
