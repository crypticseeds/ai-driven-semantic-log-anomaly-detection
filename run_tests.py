#!/usr/bin/env python3
"""
Simple script to run all tests locally from the project root.
Similar to CI workflow but excludes test_kafka_service.py (see DEV-41).

This script runs all tests in backend/tests, which includes:
- Unit tests: test_pii_service.py, test_qdrant_service.py, test_clustering_service.py, test_anomaly_detection_service.py, test_llm_reasoning_service.py, etc.
  (test_kafka_service.py excluded - see DEV-41)
- Integration tests: test_ingestion_flow.py
- Config tests: test_config.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure we're in the project root
project_root = Path(__file__).parent
os.chdir(project_root)


def parse_test_output(line):
    """Parse pytest output to extract test name and status."""
    # Match patterns like:
    # "backend/tests/test_file.py::TestClass::test_method PASSED"
    # "backend/tests/test_file.py::test_function FAILED"
    # "backend/tests/test_file.py::TestClass::test_method [ 10%]"
    # Also handle relative paths
    test_pattern = r"([^\s]+::[^\s]+)\s+(PASSED|FAILED|ERROR|SKIPPED|\[.*%\])"
    match = re.search(test_pattern, line)
    if match:
        test_name = match.group(1)
        status = match.group(2)
        return test_name, status
    return None, None


def run_tests():
    """Run all tests and display progress with test names."""
    print(f"\n{'=' * 60}")
    print("Running All Tests")
    print(f"{'=' * 60}\n")

    # Run pytest with verbose output
    # This includes all tests in backend/tests:
    # - Unit tests: test_pii_service.py, test_qdrant_service.py, test_clustering_service.py, test_anomaly_detection_service.py, test_llm_reasoning_service.py, etc.
    #   (test_kafka_service.py excluded - see DEV-41)
    # - Integration tests: test_ingestion_flow.py
    # - Config tests: test_config.py
    # Set rootdir explicitly to project root to avoid pytest auto-detecting backend/ as rootdir
    # Exclude Kafka tests until they are fixed - see Linear issue DEV-41
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "pytest",
        "backend/tests",
        "--ignore=backend/tests/unit/test_kafka_service.py",  # Exclude until DEV-41 is fixed
        "--rootdir",
        str(project_root),
        "-v",
        "--tb=short",
        # Suppress warnings for cleaner output
        # Uncomment the line below if you need to see warning summaries
        # "--disable-warnings",  # Can be uncommented if needed to see warnings
        "-W",
        "ignore",  # Ignore all warnings for cleaner test output
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
    )

    failed_tests = []
    passed_tests = []
    test_time = None

    # Stream output in real-time
    for line in process.stdout:
        # Extract test execution time from pytest summary
        # Pattern: "52 passed in 5.07s" or "52 passed, 2 failed in 5.07s"
        time_match = re.search(r"in\s+([\d.]+)s", line)
        if time_match:
            test_time = time_match.group(1)
            continue  # Skip the pytest summary line

        # Filter out warning summary sections and duration info for cleaner output
        # Uncomment the condition below if you need to see warnings/durations
        if any(
            keyword in line.lower()
            for keyword in [
                "warnings summary",
                "pydanticdeprecatedsince20",
                "deprecationwarning",
                "=============================== warnings summary ===============================",
                "slowest",
                "durations",
                "============================= slowest",
                "=============================",  # Filter pytest summary separator lines
            ]
        ):
            continue  # Skip warning and duration lines

        # Parse for test names and status before printing
        test_name, status = parse_test_output(line)

        if test_name:
            # Show which test is running
            if status and "[" in status:  # Progress indicator like [ 10%]
                print(f"▶ Running: {test_name} {status}")
            elif status == "PASSED":
                print(f"✅ PASSED: {test_name}")
                passed_tests.append(test_name)
            elif status == "FAILED":
                print(f"❌ FAILED: {test_name}")
                failed_tests.append(test_name)
            elif status == "ERROR":
                print(f"⚠️  ERROR: {test_name}")
                failed_tests.append(test_name)
            elif status == "SKIPPED":
                print(f"⏭️  SKIPPED: {test_name}")
        else:
            # Print other pytest output (like collection, errors, etc.)
            print(line, end="")

    # Wait for process to complete
    return_code = process.wait()

    return return_code == 0, failed_tests, passed_tests, test_time


def main():
    """Run all tests and show summary."""
    success, failed_tests, passed_tests, test_time = run_tests()

    print(f"\n{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}")
    print(f"Total passed: {len(passed_tests)}")
    print(f"Total failed: {len(failed_tests)}")
    if test_time:
        print(f"Execution time: {test_time}s")

    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
        if failed_tests:
            print(f"\nFailed tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"  ❌ {test}")
    print(f"{'=' * 60}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
