import argparse
from datetime import datetime
import pathlib
import sys

# Ensure repository root is on sys.path to support both 'python src/run_pipeline.py' and 'python -m src.run_pipeline'
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import simulate, inject_faults, validate, load_sqlite, load_external_ai4i, generate_reports
from src.config import BASE_DIR, DEFAULT_SEED, DEFAULT_DAYS, DEFAULT_START_DATE


def main():
    parser = argparse.ArgumentParser(description="Run the full FactoryPulse 360 data pipeline")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for deterministic generation")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of days to simulate")
    parser.add_argument("--start-date", type=str, default=DEFAULT_START_DATE, help="Simulation start date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=str, default="data", help="Output directory for generated data")
    parser.add_argument("--reports-dir", type=str, default=None, help="Output directory for analytical reports")
    args = parser.parse_args()

    # Validate days: must be positive integer
    if args.days <= 0:
        parser.error(f"--days must be a positive integer, got {args.days}")

    # Validate start_date format and valid calendar date (e.g. rejects 2024/01/01 and 2024-02-30)
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    except ValueError as e:
        parser.error(f"Invalid --start-date '{args.start_date}', expected format YYYY-MM-DD: {e}")

    # Resolve output directory
    target_path = pathlib.Path(args.output_dir)
    if not target_path.is_absolute():
        target_path = BASE_DIR / target_path

    if target_path.name == "data":
        base_data_dir = target_path
    else:
        base_data_dir = target_path / "data"

    raw_dir = base_data_dir / "raw"
    faulty_dir = raw_dir / "faulty"
    curated_dir = base_data_dir / "curated"
    db_path = base_data_dir / "factorypulse.db"

    # Resolve reports directory
    if args.reports_dir:
        reports_dir = pathlib.Path(args.reports_dir)
        if not reports_dir.is_absolute():
            reports_dir = BASE_DIR / reports_dir
    elif target_path.name == "data":
        reports_dir = target_path.parent / "reports" / "analytics"
    else:
        reports_dir = target_path / "reports" / "analytics"

    # Step 1: generate raw simulation data
    print(f"[pipeline] Running factory simulation: start_date={args.start_date}, days={args.days}, seed={args.seed}...")
    simulate.simulate_production(
        start_date=start_date,
        days=args.days,
        seed=args.seed,
        output_dir=base_data_dir,
    )

    # Step 2: inject deterministic data-quality faults
    print(f"[pipeline] Injecting data-quality faults into {faulty_dir}...")
    inject_faults.inject_faults(
        input_dir=raw_dir,
        output_dir=faulty_dir,
        seed=args.seed,
    )

    # Step 3: validate and produce curated tables + exception register
    print(f"[pipeline] Validating data into {curated_dir}...")
    validate.run_validation(
        raw_dir=faulty_dir,
        curated_dir=curated_dir,
    )

    # Step 4: load curated data into SQLite
    print(f"[pipeline] Loading curated data into SQLite at {db_path}...")
    load_sqlite.load_sqlite(
        db_path=db_path,
        curated_dir=curated_dir,
        raw_dir=faulty_dir,
    )

    # Step 5: ingest external AI4I dataset (marks rows as external)
    print(f"[pipeline] Loading external AI4I dataset into FactSensor at {db_path}...")
    inserted_ai4i = load_external_ai4i.load_ai4i(db_path=db_path)
    print(f"[pipeline] Loaded {inserted_ai4i} external AI4I rows.")

    # Step 6: generate analytical reports and reconciliation report
    print(f"[pipeline] Generating analytical reports into {reports_dir}...")
    recon_result = generate_reports.generate_reports(
        db_path=db_path,
        reports_dir=reports_dir,
    )
    print(f"[pipeline] Reports generated successfully. Reconciliation status: {recon_result['status']}")

    print("[pipeline] Pipeline completed successfully.")


if __name__ == "__main__":
    main()
