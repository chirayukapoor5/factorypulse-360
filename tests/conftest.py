import hashlib
import os
import pathlib
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, Generator, Tuple

import pytest


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    """Returns the absolute path to the repository root."""
    return pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_env(tmp_path: pathlib.Path) -> Dict[str, pathlib.Path]:
    """Prepares a clean isolated directory structure within tmp_path."""
    env = {
        "root": tmp_path,
        "data": tmp_path / "data",
        "raw": tmp_path / "data" / "raw",
        "faulty": tmp_path / "data" / "raw" / "faulty",
        "curated": tmp_path / "data" / "curated",
        "reports": tmp_path / "reports" / "analytics",
        "bi_handoff": tmp_path / "bi_handoff",
        "bi_dimensions": tmp_path / "bi_handoff" / "dimensions",
        "bi_facts": tmp_path / "bi_handoff" / "facts",
        "bi_exceptions": tmp_path / "bi_handoff" / "exceptions",
        "db_path": tmp_path / "data" / "factorypulse.db",
    }
    for p in env.values():
        if p != env["db_path"]:
            p.mkdir(parents=True, exist_ok=True)
    return env


@pytest.fixture
def isolated_db(tmp_path: pathlib.Path, repo_root: pathlib.Path) -> Generator[sqlite3.Connection, None, None]:
    """Compiles an isolated SQLite database from sql/schema.sql with PRAGMA foreign_keys = ON."""
    db_path = tmp_path / "test_factorypulse.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    schema_file = repo_root / "sql" / "schema.sql"
    if schema_file.exists():
        with open(schema_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

    # Add trigger for machine key foreign key validation if missing
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS fk_factproduction_machinekey BEFORE INSERT ON FactProduction
        FOR EACH ROW BEGIN
            SELECT RAISE(FAIL, 'Invalid MachineKey')
            WHERE (SELECT COUNT(*) FROM DimMachine WHERE MachineKey = NEW.MachineKey) = 0;
        END;
    """)
    conn.commit()

    yield conn
    conn.close()


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set:
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


@pytest.fixture
def populated_db(isolated_db: sqlite3.Connection) -> sqlite3.Connection:
    """Populates canonical dimensional entities into isolated_db."""
    conn = isolated_db

    # 1. DimDate (30 days from 2024-01-01)
    date_cols = _get_table_columns(conn, "DimDate")
    start = datetime(2024, 1, 1)
    for i in range(30):
        d = start + timedelta(days=i)
        row = {
            "DateKey": int(d.strftime("%Y%m%d")),
            "Date": d.strftime("%Y-%m-%d"),
            "Year": d.year,
            "Month": d.month,
            "Day": d.day,
            "Week": d.isocalendar()[1],
            "WeekOfYear": d.isocalendar()[1],
            "DayOfWeek": d.weekday() + 1,
            "IsWeekend": 1 if d.weekday() >= 5 else 0,
        }
        filtered = {k: v for k, v in row.items() if k in date_cols}
        placeholders = ", ".join(["?"] * len(filtered))
        cols = ", ".join(filtered.keys())
        conn.execute(f"INSERT OR REPLACE INTO DimDate ({cols}) VALUES ({placeholders})", list(filtered.values()))

    # 2. DimShift (2 shifts)
    shift_cols = _get_table_columns(conn, "DimShift")
    shifts = [
        {"ShiftKey": 1, "ShiftId": 1, "ShiftName": "Shift 1", "StartTime": "06:00:00", "EndTime": "14:00:00", "ScheduledMinutes": 480.0},
        {"ShiftKey": 2, "ShiftId": 2, "ShiftName": "Shift 2", "StartTime": "14:00:00", "EndTime": "22:00:00", "ScheduledMinutes": 480.0},
    ]
    for s in shifts:
        filtered = {k: v for k, v in s.items() if k in shift_cols}
        placeholders = ", ".join(["?"] * len(filtered))
        cols = ", ".join(filtered.keys())
        conn.execute(f"INSERT OR REPLACE INTO DimShift ({cols}) VALUES ({placeholders})", list(filtered.values()))

    # 3. DimLine (3 production lines)
    line_cols = _get_table_columns(conn, "DimLine")
    lines = [
        {"LineKey": 1, "LineId": 1, "LineName": "Line 1", "PlantArea": "Smart Power"},
        {"LineKey": 2, "LineId": 2, "LineName": "Line 2", "PlantArea": "Smart Power"},
        {"LineKey": 3, "LineId": 3, "LineName": "Line 3", "PlantArea": "Smart Power"},
    ]
    for l in lines:
        filtered = {k: v for k, v in l.items() if k in line_cols}
        placeholders = ", ".join(["?"] * len(filtered))
        cols = ", ".join(filtered.keys())
        conn.execute(f"INSERT OR REPLACE INTO DimLine ({cols}) VALUES ({placeholders})", list(filtered.values()))

    # 4. DimMachine (24 machines: 3 lines * 2 cells * 4 machines)
    mach_cols = _get_table_columns(conn, "DimMachine")
    m_idx = 1
    for line in range(1, 4):
        for cell in range(1, 3):
            cell_key = (line - 1) * 2 + cell
            for m in range(1, 5):
                row = {
                    "MachineKey": m_idx,
                    "MachineId": f"M{line}{cell}{m}",
                    "LineKey": line,
                    "CellKey": cell_key,
                    "CellId": cell,
                    "MachineName": f"Machine {line}{cell}{m}",
                    "StageSequence": m,
                    "IsEndOfLine": 1 if m == 4 else 0,
                }
                filtered = {k: v for k, v in row.items() if k in mach_cols}
                placeholders = ", ".join(["?"] * len(filtered))
                cols = ", ".join(filtered.keys())
                conn.execute(f"INSERT OR REPLACE INTO DimMachine ({cols}) VALUES ({placeholders})", list(filtered.values()))
                m_idx += 1

    # 5. DimProduct (5 products)
    prod_cols = _get_table_columns(conn, "DimProduct")
    products = [
        {"ProductKey": 1, "ProductId": "P1", "ProductFamily": "Family_A", "ProductName": "Product A", "IdealCycleTimeSeconds": 60.0, "IdealCycleTimeMinutes": 1.0},
        {"ProductKey": 2, "ProductId": "P2", "ProductFamily": "Family_B", "ProductName": "Product B", "IdealCycleTimeSeconds": 60.0, "IdealCycleTimeMinutes": 1.0},
        {"ProductKey": 3, "ProductId": "P3", "ProductFamily": "Family_C", "ProductName": "Product C", "IdealCycleTimeSeconds": 60.0, "IdealCycleTimeMinutes": 1.0},
        {"ProductKey": 4, "ProductId": "P4", "ProductFamily": "Family_D", "ProductName": "Product D", "IdealCycleTimeSeconds": 60.0, "IdealCycleTimeMinutes": 1.0},
        {"ProductKey": 5, "ProductId": "P5", "ProductFamily": "Family_E", "ProductName": "Product E", "IdealCycleTimeSeconds": 60.0, "IdealCycleTimeMinutes": 1.0},
    ]
    for p in products:
        filtered = {k: v for k, v in p.items() if k in prod_cols}
        placeholders = ", ".join(["?"] * len(filtered))
        cols = ", ".join(filtered.keys())
        conn.execute(f"INSERT OR REPLACE INTO DimProduct ({cols}) VALUES ({placeholders})", list(filtered.values()))

    # 6. DimReason (Downtime and Defect reasons)
    reason_cols = _get_table_columns(conn, "DimReason")
    cat_col = "Category" if "Category" in reason_cols else "ReasonCategory"
    reasons = [
        {"ReasonKey": 1, "ReasonCode": "Planned_Maintenance", cat_col: "Downtime", "ReasonDescription": "Scheduled maintenance"},
        {"ReasonKey": 2, "ReasonCode": "Mechanical_Failure", cat_col: "Downtime", "ReasonDescription": "Mechanical breakdown"},
        {"ReasonKey": 3, "ReasonCode": "Electrical_Failure", cat_col: "Downtime", "ReasonDescription": "Electrical breakdown"},
        {"ReasonKey": 4, "ReasonCode": "Changeover", cat_col: "Downtime", "ReasonDescription": "Tooling changeover"},
        {"ReasonKey": 5, "ReasonCode": "Setup", cat_col: "Downtime", "ReasonDescription": "Line setup and adjustment"},
        {"ReasonKey": 6, "ReasonCode": "Scrap", cat_col: "Defect", "ReasonDescription": "Defective scrap unit"},
        {"ReasonKey": 7, "ReasonCode": "Rework", cat_col: "Defect", "ReasonDescription": "Reworked unit"},
        {"ReasonKey": 8, "ReasonCode": "Minor_Defect", cat_col: "Defect", "ReasonDescription": "Minor cosmetic defect"},
    ]
    for r in reasons:
        filtered = {k: v for k, v in r.items() if k in reason_cols}
        placeholders = ", ".join(["?"] * len(filtered))
        cols = ", ".join(filtered.keys())
        conn.execute(f"INSERT OR REPLACE INTO DimReason ({cols}) VALUES ({placeholders})", list(filtered.values()))

    conn.commit()
    return conn


@pytest.fixture
def run_pipeline_cli(repo_root: pathlib.Path) -> Callable[..., subprocess.CompletedProcess]:
    """Helper fixture executing src/run_pipeline.py in an isolated subprocess with PYTHONPATH set."""
    def _run(*args: str, **kwargs) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)
        cmd = [sys.executable, str(repo_root / "src" / "run_pipeline.py"), *args]
        return subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            **kwargs,
        )
    return _run


def _hash_file(path: pathlib.Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def _get_data_directory_hashes(data_dir: pathlib.Path) -> Dict[str, str]:
    hashes = {}
    if data_dir.exists():
        for p in data_dir.rglob("*"):
            if p.is_file():
                rel_path = str(p.relative_to(data_dir))
                hashes[rel_path] = _hash_file(p)
    return hashes


@pytest.fixture(scope="session", autouse=True)
def repo_immutability_guard(repo_root: pathlib.Path) -> Generator[None, None, None]:
    """Session-level guard ensuring files in data/ remain completely unmodified throughout test runs."""
    data_dir = repo_root / "data"
    pre_hashes = _get_data_directory_hashes(data_dir)

    yield

    post_hashes = _get_data_directory_hashes(data_dir)

    # Check for modified or deleted files
    for rel_path, pre_h in pre_hashes.items():
        if rel_path not in post_hashes:
            pytest.fail(f"REPOSITORY MUTATION DETECTED: Committed data file was deleted during tests: {rel_path}")
        elif post_hashes[rel_path] != pre_h:
            pytest.fail(f"REPOSITORY MUTATION DETECTED: Committed data file was modified during tests: {rel_path}")

    # Check for newly created files
    for rel_path in post_hashes:
        if rel_path not in pre_hashes:
            pytest.fail(f"REPOSITORY MUTATION DETECTED: New file was created in repository data/ during tests: {rel_path}")
