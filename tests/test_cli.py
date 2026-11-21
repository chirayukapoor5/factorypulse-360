import pathlib
import pytest


@pytest.mark.tier1
def test_cli_help_flag(run_pipeline_cli):
    """F1: Invoking --help should exit with code 0 and display usage options."""
    res = run_pipeline_cli("--help")
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"
    stdout = res.stdout.lower()
    assert "usage:" in stdout or "factorypulse" in stdout
    assert "--seed" in stdout
    assert "--days" in stdout


@pytest.mark.tier1
def test_cli_defaults_execution(run_pipeline_cli, tmp_path):
    """F1: Invoking CLI with default options writes output without error."""
    out_dir = tmp_path / "default_out"
    res = run_pipeline_cli("--output-dir", str(out_dir), "--days", "1")
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"
    assert out_dir.exists(), f"Output directory {out_dir} was not created"
    assert (out_dir / "data" / "factorypulse.db").exists() or (out_dir / "factorypulse.db").exists() or (out_dir / "curated").exists() or (out_dir / "data" / "curated").exists()


@pytest.mark.tier1
def test_cli_explicit_seed_parameter(run_pipeline_cli, tmp_path):
    """F1: Explicit --seed parameter is parsed and accepted."""
    out_dir = tmp_path / "seed_out"
    res = run_pipeline_cli("--seed", "12345", "--days", "1", "--output-dir", str(out_dir))
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"
    assert (out_dir / "data" / "curated" / "FactProduction.csv").exists() or (out_dir / "curated" / "FactProduction.csv").exists()


@pytest.mark.tier1
def test_cli_explicit_days_parameter(run_pipeline_cli, tmp_path):
    """F1: Explicit --days parameter is parsed and accepted."""
    out_dir = tmp_path / "days_out"
    res = run_pipeline_cli("--days", "5", "--output-dir", str(out_dir))
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"


@pytest.mark.tier1
def test_cli_explicit_start_date_parameter(run_pipeline_cli, tmp_path):
    """F1: Explicit --start-date parameter is parsed and accepted."""
    out_dir = tmp_path / "date_out"
    res = run_pipeline_cli("--start-date", "2024-06-01", "--days", "1", "--output-dir", str(out_dir))
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"


@pytest.mark.tier1
def test_cli_explicit_output_dir_parameter(run_pipeline_cli, tmp_path):
    """F1: Explicit --output-dir parameter isolates output files."""
    custom_dir = tmp_path / "custom_dir"
    res = run_pipeline_cli("--output-dir", str(custom_dir), "--days", "1")
    assert res.returncode == 0, f"Expected exit code 0, got {res.returncode}. stderr: {res.stderr}"
    assert custom_dir.exists(), "Custom output directory was not created"


@pytest.mark.tier2
def test_cli_unrecognized_argument_rejected(run_pipeline_cli):
    """F1: Unknown argument should be rejected with argparse standard exit code 2."""
    res = run_pipeline_cli("--unrecognized-argument-xyz")
    assert res.returncode == 2, f"Expected exit code 2 for unrecognized arg, got {res.returncode}"
    assert "unrecognized arguments" in res.stderr or "error" in res.stderr.lower()


@pytest.mark.tier2
def test_cli_invalid_seed_non_integer(run_pipeline_cli, tmp_path):
    """F1: Passing non-integer seed should exit with code 2."""
    res = run_pipeline_cli("--seed", "not_a_number", "--output-dir", str(tmp_path))
    assert res.returncode == 2, f"Expected exit code 2 for invalid seed, got {res.returncode}"
    assert "invalid int value" in res.stderr.lower() or "error" in res.stderr.lower()


@pytest.mark.tier2
def test_cli_invalid_days_non_integer(run_pipeline_cli, tmp_path):
    """F1: Passing non-integer days should exit with code 2."""
    res = run_pipeline_cli("--days", "three_days", "--output-dir", str(tmp_path))
    assert res.returncode == 2, f"Expected exit code 2 for invalid days, got {res.returncode}"
    assert "invalid int value" in res.stderr.lower() or "error" in res.stderr.lower()


@pytest.mark.tier2
def test_cli_invalid_date_format(run_pipeline_cli, tmp_path):
    """F1: Passing slash-delimited date format YYYY/MM/DD should be rejected with non-zero exit."""
    res = run_pipeline_cli("--start-date", "2024/01/01", "--days", "1", "--output-dir", str(tmp_path))
    assert res.returncode != 0, "Pipeline should reject malformed date format '2024/01/01'"


@pytest.mark.tier2
def test_cli_impossible_calendar_date(run_pipeline_cli, tmp_path):
    """F1: Passing non-existent calendar date (e.g. Feb 30) should be rejected with non-zero exit."""
    res = run_pipeline_cli("--start-date", "2024-02-30", "--days", "1", "--output-dir", str(tmp_path))
    assert res.returncode != 0, "Pipeline should reject impossible date '2024-02-30'"


@pytest.mark.tier2
def test_cli_non_positive_days(run_pipeline_cli, tmp_path):
    """F1: Passing zero or negative days should fail validation with non-zero exit."""
    res_zero = run_pipeline_cli("--days", "0", "--output-dir", str(tmp_path / "z"))
    res_neg = run_pipeline_cli("--days", "-5", "--output-dir", str(tmp_path / "n"))
    assert res_zero.returncode != 0, f"Pipeline should reject --days 0 with non-zero exit, got {res_zero.returncode}"
    assert res_neg.returncode != 0, f"Pipeline should reject --days -5 with non-zero exit, got {res_neg.returncode}"
