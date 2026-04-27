#!/usr/bin/env python3
"""Adversarial CI/CD gate runner.

Executes the adversarial robustness test suite and returns:
- Exit code 0 on all gates passed
- Exit code 1 on any gate failure
- JSON report written to adv_ci_gate_report.json

Usage:
    python ci_gate.py [pytest-args]

Example:
    python ci_gate.py -v --tb=short
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class CIGateRunner:
    """Run adversarial CI gate and generate failure reports."""

    def __init__(self) -> None:
        """Initialize CI gate runner."""
        self.test_dir = Path(__file__).parent / "tests"
        self.report_file = self.test_dir / "adv_ci_gate_report.json"

    def run(self, pytest_args: list[str] | None = None) -> int:
        """Execute adversarial robustness test suite.

        Args:
            pytest_args: Additional pytest command-line arguments.

        Returns:
            Exit code (0 = success, 1 = failure).
        """
        if pytest_args is None:
            pytest_args = []

        # Build pytest command
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir / "test_adversarial_ci_gate.py"),
            "-v",
            "--tb=short",
            "--color=yes",
        ] + pytest_args

        print(f"🚀 Running Adversarial CI/CD Gate...")
        print(f"   Command: {' '.join(cmd)}\n")

        # Execute tests
        result = subprocess.run(cmd, cwd=Path(__file__).parent)

        exit_code = result.returncode

        # Generate report if test failed
        if exit_code != 0:
            self._generate_failure_report()

        return exit_code

    def _generate_failure_report(self) -> None:
        """Generate JSON failure report with timestamp."""
        # Check if pytest already generated report
        if self.report_file.exists():
            with open(self.report_file) as f:
                report = json.load(f)
        else:
            # Create basic failure report
            report = {
                "status": "FAILED",
                "timestamp_ms": int(datetime.utcnow().timestamp() * 1000),
                "stage_results": {
                    "stage_1_clean_vs_fgsm": {
                        "status": "unknown",
                        "details": "Test execution failed before metrics collection",
                    },
                    "stage_2_pgd_robustness": {
                        "status": "unknown",
                        "details": "Test execution failed",
                    },
                    "stage_3_whitelist_flip": {
                        "status": "unknown",
                        "details": "Test execution failed",
                    },
                },
                "failed_gates": [],
            }

        # Add timestamp if missing
        if "timestamp_ms" not in report:
            report["timestamp_ms"] = int(datetime.utcnow().timestamp() * 1000)

        # Write report
        with open(self.report_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n📋 Gate failure report: {self.report_file}")
        print(json.dumps(report, indent=2))

    def check_report(self) -> dict[str, Any] | None:
        """Read and return the CI gate report if it exists.

        Returns:
            Parsed JSON report dict, or None if report doesn't exist.
        """
        if not self.report_file.exists():
            return None

        with open(self.report_file) as f:
            return json.load(f)


def main() -> int:
    """Main entry point."""
    runner = CIGateRunner()

    # Pass through any CLI arguments to pytest
    pytest_args = sys.argv[1:] if len(sys.argv) > 1 else []

    exit_code = runner.run(pytest_args)

    if exit_code == 0:
        print("\n✅ All adversarial robustness gates PASSED")
    else:
        print("\n❌ Adversarial robustness gate FAILED")
        report = runner.check_report()
        if report:
            print(f"\nFailed gates: {report.get('failed_gates', [])}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
