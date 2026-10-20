"""Supporting dataset generator runner for PlanProof AI.

Delegates to data/generate_dataset.py while ensuring crisis_scenarios.csv
and dataset.csv are strictly protected from modification.
"""

from pathlib import Path
import sys

from data.generate_dataset import run_generator

if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent / "data"
    overwrite = "--overwrite" in sys.argv
    validate_only = "--validate-only" in sys.argv
    code = run_generator(data_dir=data_dir, overwrite=overwrite, validate_only=validate_only)
    sys.exit(code)
