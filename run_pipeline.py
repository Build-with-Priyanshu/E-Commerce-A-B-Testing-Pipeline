"""Run the Python stages of the converted MySQL pipeline in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT_DIR = PROJECT_ROOT / "scripts"
STAGES = [
    "test_connection.py",
    "generate_ecomm_data.py",
    "fix_sample_size.py",
    "validate_experiment.py",
    "collect_experiment_data.py",
    "analyse_experiment_data.py",
]


def main():
    for stage in STAGES:
        print(f"\n{'=' * 70}\nRunning {stage}\n{'=' * 70}", flush=True)
        subprocess.run(
            [sys.executable, str(SCRIPT_DIR / stage)],
            cwd=PROJECT_ROOT,
            check=True,
        )
    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()

#   code to run the script:  python run_pipeline.py