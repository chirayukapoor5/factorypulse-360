import pathlib

# Configuration constants for the FactoryPulse‑360 simulation

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent  # repository root
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_CURATED_DIR = BASE_DIR / "data" / "curated"
SQL_DIR = BASE_DIR / "sql"
DOCS_DIR = BASE_DIR / "docs"

# Simulation parameters (can be overridden via CLI arguments)
DEFAULT_SEED = 20261120
DEFAULT_DAYS = 90
NUM_LINES = 3
CELLS_PER_LINE = 2  # total cells = NUM_LINES * CELLS_PER_LINE = 6
SHIFTS_PER_DAY = 2
PRODUCT_FAMILIES = ["Family_A", "Family_B", "Family_C", "Family_D", "Family_E"]

# Derived constants
TOTAL_CELLS = NUM_LINES * CELLS_PER_LINE
TOTAL_MACHINES = TOTAL_CELLS * 4  # assume 4 machines per cell

# Dimension values
SHIFT_IDS = [1, 2]
LINE_IDS = list(range(1, NUM_LINES + 1))
CELL_IDS = [(line, cell) for line in LINE_IDS for cell in range(1, CELLS_PER_LINE + 1)]
MACHINE_IDS = [(line, cell, m) for line, cell in CELL_IDS for m in range(1, 5)]

# Reason codes for downtime and quality defects
REASON_DOWNTIME = ["Planned_Maintenance", "Mechanical_Failure", "Electrical_Failure", "Changeover", "Setup"]
REASON_DEFECT = ["Scrap", "Rework", "Minor_Defect"]
