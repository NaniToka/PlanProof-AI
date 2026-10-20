"""Tests for safe dataset generation tooling and protection mechanisms."""

import json
from pathlib import Path

from data.generate_dataset import (
    generate_budget_splits_data,
    generate_vendor_checklists_data,
    run_generator,
)


def test_generator_reproducibility() -> None:
    """Verify that dataset generation produces identical deterministic output."""
    splits_run_1 = generate_budget_splits_data()
    splits_run_2 = generate_budget_splits_data()
    assert splits_run_1 == splits_run_2

    vendors_run_1 = generate_vendor_checklists_data()
    vendors_run_2 = generate_vendor_checklists_data()
    assert vendors_run_1 == vendors_run_2


def test_generator_skips_existing_unless_overwrite(tmp_path: Path) -> None:
    """Verify that existing JSON files are preserved when overwrite=False."""
    target_dir = tmp_path / "data"
    target_dir.mkdir()

    # Create dummy files
    dummy_budget = target_dir / "budget_splits.json"
    dummy_vendor = target_dir / "vendor_checklists.json"
    dummy_budget.write_text("dummy-budget", encoding="utf-8")
    dummy_vendor.write_text("dummy-vendor", encoding="utf-8")

    # Run without overwrite: should skip both (and fail validation on dummy content)
    exit_code = run_generator(data_dir=target_dir, overwrite=False)
    # Validation of dummy content will fail (code == 1)
    assert exit_code == 1
    # Files should still have dummy content untouched
    assert dummy_budget.read_text(encoding="utf-8") == "dummy-budget"
    assert dummy_vendor.read_text(encoding="utf-8") == "dummy-vendor"

    # Now run WITH overwrite: should replace dummy content with valid generated JSON
    exit_code_overwrite = run_generator(data_dir=target_dir, overwrite=True)
    assert exit_code_overwrite == 0
    assert "splits" in json.loads(dummy_budget.read_text(encoding="utf-8"))
    assert "vendors" in json.loads(dummy_vendor.read_text(encoding="utf-8"))


def test_generator_protects_crisis_csv(tmp_path: Path) -> None:
    """Verify that generator NEVER touches, overwrites, or regenerates crisis_scenarios.csv."""
    target_dir = tmp_path / "data"
    target_dir.mkdir()

    crisis_file = target_dir / "crisis_scenarios.csv"
    original_content = "id,event_type\nCR9999999,wedding\n"
    crisis_file.write_text(original_content, encoding="utf-8")

    # Run generator with overwrite=True
    run_generator(data_dir=target_dir, overwrite=True)

    # Crisis file must remain 100% untouched
    assert crisis_file.read_text(encoding="utf-8") == original_content


def test_generator_validate_only_mode(tmp_path: Path) -> None:
    """Verify that --validate-only validates valid datasets without modifications."""
    target_dir = tmp_path / "data"
    # Generate valid files first
    run_generator(data_dir=target_dir, overwrite=True)

    # Record mod times
    budget_mtime = (target_dir / "budget_splits.json").stat().st_mtime_ns
    vendor_mtime = (target_dir / "vendor_checklists.json").stat().st_mtime_ns

    # Run validate-only
    exit_code = run_generator(data_dir=target_dir, validate_only=True)
    assert exit_code == 0

    # Ensure mtimes did not change
    assert (target_dir / "budget_splits.json").stat().st_mtime_ns == budget_mtime
    assert (target_dir / "vendor_checklists.json").stat().st_mtime_ns == vendor_mtime
