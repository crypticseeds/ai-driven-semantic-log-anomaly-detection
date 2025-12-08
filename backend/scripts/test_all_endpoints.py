#!/usr/bin/env python3
"""
Automated API Endpoint Testing Script

This script tests all API endpoints in the AI-Driven Semantic Log Anomaly Detection system.
It reports which endpoints succeed, fail, and what error codes are returned.

Usage:
    python backend/scripts/test_all_endpoints.py
    python backend/scripts/test_all_endpoints.py --base-url http://localhost:8000
    python backend/scripts/test_all_endpoints.py --verbose
"""

import argparse
import json
import sys
import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

# Default configuration
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30  # seconds


class EndpointTestResult:
    """Result of testing a single endpoint."""

    def __init__(
        self,
        method: str,
        endpoint: str,
        status_code: int | None = None,
        success: bool = False,
        error: str | None = None,
        response_time_ms: float | None = None,
        response_data: dict[str, Any] | None = None,
    ):
        self.method = method
        self.endpoint = endpoint
        self.status_code = status_code
        self.success = success
        self.error = error
        self.response_time_ms = response_time_ms
        self.response_data = response_data

    def __repr__(self) -> str:
        status = "✅ PASS" if self.success else "❌ FAIL"
        return f"{status} {self.method} {self.endpoint} - Status: {self.status_code}"


class EndpointTester:
    """Test all API endpoints."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        verbose: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose
        self.results: list[EndpointTestResult] = []
        self.test_log_id: str | None = None  # Store a log ID for testing endpoints that require it

    def log(self, message: str, level: str = "INFO"):
        """Print log message if verbose mode is enabled."""
        if self.verbose or level == "ERROR":
            print(f"[{level}] {message}")

    def test_endpoint(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        expected_status: int = 200,
        allow_errors: bool = False,
    ) -> EndpointTestResult:
        """Test a single endpoint."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=self.timeout)
            elif method == "POST":
                response = requests.post(url, params=params, json=json_data, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response_time_ms = (time.time() - start_time) * 1000

            # Try to parse JSON response
            response_data = None
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {"raw_response": response.text[:200]}  # First 200 chars

            # Determine success
            is_success = response.status_code == expected_status or (
                allow_errors and 200 <= response.status_code < 500
            )

            result = EndpointTestResult(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                success=is_success,
                error=None
                if is_success
                else f"Expected {expected_status}, got {response.status_code}",
                response_time_ms=response_time_ms,
                response_data=response_data,
            )

            self.log(f"{result}")
            return result

        except ConnectionError as e:
            response_time_ms = (time.time() - start_time) * 1000
            error_msg = f"Connection error: {str(e)}"
            self.log(f"❌ FAIL {method} {endpoint} - {error_msg}", "ERROR")
            return EndpointTestResult(
                method=method,
                endpoint=endpoint,
                success=False,
                error=error_msg,
                response_time_ms=response_time_ms,
            )

        except Timeout:
            response_time_ms = (time.time() - start_time) * 1000
            error_msg = f"Request timeout after {self.timeout}s"
            self.log(f"❌ FAIL {method} {endpoint} - {error_msg}", "ERROR")
            return EndpointTestResult(
                method=method,
                endpoint=endpoint,
                success=False,
                error=error_msg,
                response_time_ms=response_time_ms,
            )

        except RequestException as e:
            response_time_ms = (time.time() - start_time) * 1000
            error_msg = f"Request error: {str(e)}"
            self.log(f"❌ FAIL {method} {endpoint} - {error_msg}", "ERROR")
            return EndpointTestResult(
                method=method,
                endpoint=endpoint,
                success=False,
                error=error_msg,
                response_time_ms=response_time_ms,
            )

    def test_health_endpoints(self):
        """Test health and root endpoints."""
        print("\n" + "=" * 60)
        print("Testing Health & Root Endpoints")
        print("=" * 60)

        # Root endpoint
        result = self.test_endpoint("GET", "/")
        self.results.append(result)

        # Health check
        result = self.test_endpoint("GET", "/health")
        self.results.append(result)

        # Kafka health check (may return 503 if Kafka is down, which is acceptable)
        result = self.test_endpoint("GET", "/health/kafka", allow_errors=True)
        self.results.append(result)

    def test_logs_endpoints(self):
        """Test logs API endpoints."""
        print("\n" + "=" * 60)
        print("Testing Logs API Endpoints")
        print("=" * 60)

        # Search logs - basic
        result = self.test_endpoint("GET", "/api/v1/logs/search", params={"limit": 10})
        self.results.append(result)

        # Search logs - with query
        result = self.test_endpoint(
            "GET", "/api/v1/logs/search", params={"query": "test", "limit": 5}
        )
        self.results.append(result)

        # Search logs - with filters
        result = self.test_endpoint(
            "GET",
            "/api/v1/logs/search",
            params={"level": "ERROR", "limit": 5},
        )
        self.results.append(result)

        # Search logs - semantic search (may fail if no embeddings)
        result = self.test_endpoint(
            "GET",
            "/api/v1/logs/search",
            params={"query": "test", "use_semantic_search": "true", "limit": 5},
            allow_errors=True,
        )
        self.results.append(result)

        # Try to get a log ID from search results for subsequent tests
        search_result = self.test_endpoint("GET", "/api/v1/logs/search", params={"limit": 1})
        if search_result.success and search_result.response_data:
            results = search_result.response_data.get("results", [])
            if results:
                self.test_log_id = results[0].get("id")
                self.log(f"Found log ID for testing: {self.test_log_id}")

        # Get log by ID (if we have a log ID)
        if self.test_log_id:
            result = self.test_endpoint("GET", f"/api/v1/logs/{self.test_log_id}")
            self.results.append(result)
        else:
            # Test with invalid UUID to check error handling
            result = self.test_endpoint(
                "GET",
                "/api/v1/logs/00000000-0000-0000-0000-000000000000",
                expected_status=404,
            )
            self.results.append(result)

        # Run clustering (may take time)
        print("\n  Running clustering (this may take a while)...")
        result = self.test_endpoint("POST", "/api/v1/logs/clustering/run", allow_errors=True)
        self.results.append(result)

        # List clusters
        result = self.test_endpoint("GET", "/api/v1/logs/clustering/clusters", params={"limit": 10})
        self.results.append(result)

        # Get cluster by ID (test with cluster 0, may not exist)
        result = self.test_endpoint("GET", "/api/v1/logs/clustering/clusters/0", allow_errors=True)
        self.results.append(result)

        # Get outliers
        result = self.test_endpoint("GET", "/api/v1/logs/clustering/outliers", params={"limit": 10})
        self.results.append(result)

        # Detect anomalies - Isolation Forest
        result = self.test_endpoint(
            "POST",
            "/api/v1/logs/anomaly-detection/isolation-forest",
            params={"contamination": 0.1},
            allow_errors=True,
        )
        self.results.append(result)

        # Detect anomalies - Z-score
        result = self.test_endpoint(
            "POST",
            "/api/v1/logs/anomaly-detection/z-score",
            params={"threshold": 3.0},
            allow_errors=True,
        )
        self.results.append(result)

        # Detect anomalies - IQR
        result = self.test_endpoint(
            "POST",
            "/api/v1/logs/anomaly-detection/iqr",
            params={"multiplier": 1.5},
            allow_errors=True,
        )
        self.results.append(result)

        # Score log entry (if we have a log ID)
        if self.test_log_id:
            result = self.test_endpoint(
                "POST",
                f"/api/v1/logs/anomaly-detection/score/{self.test_log_id}",
                params={"method": "IsolationForest"},
                allow_errors=True,
            )
            self.results.append(result)

    def test_agent_endpoints(self):
        """Test agent API endpoints."""
        print("\n" + "=" * 60)
        print("Testing Agent API Endpoints")
        print("=" * 60)

        # Analyze anomaly
        result = self.test_endpoint(
            "POST",
            "/api/v1/agent/analyze-anomaly",
            params={"log_message": "Database connection failed", "include_root_cause": "true"},
            allow_errors=True,  # May fail if OpenAI API key not configured
        )
        self.results.append(result)

        # Analyze anomaly by ID (if we have a log ID)
        if self.test_log_id:
            result = self.test_endpoint(
                "POST",
                f"/api/v1/agent/analyze-anomaly/{self.test_log_id}",
                params={"include_root_cause": "true"},
                allow_errors=True,
            )
            self.results.append(result)

        # Analyze anomaly stream
        result = self.test_endpoint(
            "POST",
            "/api/v1/agent/analyze-anomaly/stream",
            params={"log_message": "Test error message"},
            allow_errors=True,
        )
        self.results.append(result)

        # Detect anomaly
        result = self.test_endpoint(
            "POST",
            "/api/v1/agent/detect-anomaly",
            params={"log_message": "User logged in successfully", "log_level": "INFO"},
            allow_errors=True,
        )
        self.results.append(result)

        # Root cause analysis
        result = self.test_endpoint(
            "POST",
            "/api/v1/agent/rca",
            params={"query": "What caused errors in the system?"},
            allow_errors=True,
        )
        self.results.append(result)

        # List agent tools
        result = self.test_endpoint("GET", "/api/v1/agent/tools")
        self.results.append(result)

    def run_all_tests(self):
        """Run all endpoint tests."""
        print("=" * 60)
        print("API Endpoint Testing Script")
        print("=" * 60)
        print(f"Base URL: {self.base_url}")
        print(f"Timeout: {self.timeout}s")
        print()

        # Test all endpoint groups
        self.test_health_endpoints()
        self.test_logs_endpoints()
        self.test_agent_endpoints()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed

        print(f"Total Endpoints Tested: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed / total * 100):.1f}%")

        # Group by status code
        status_codes: dict[int, int] = {}
        for result in self.results:
            if result.status_code:
                status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1

        if status_codes:
            print("\nStatus Code Distribution:")
            for code, count in sorted(status_codes.items()):
                print(f"  {code}: {count}")

        # Show failed endpoints
        failed_results = [r for r in self.results if not r.success]
        if failed_results:
            print("\n❌ Failed Endpoints:")
            for result in failed_results:
                error_info = f" - {result.error}" if result.error else ""
                print(
                    f"  {result.method} {result.endpoint} (Status: {result.status_code}){error_info}"
                )

        # Show response times
        response_times = [r.response_time_ms for r in self.results if r.response_time_ms]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            print("\nResponse Time Statistics:")
            print(f"  Average: {avg_time:.2f}ms")
            print(f"  Min: {min_time:.2f}ms")
            print(f"  Max: {max_time:.2f}ms")

        # Export results to JSON if requested
        if self.verbose:
            results_json = []
            for result in self.results:
                results_json.append(
                    {
                        "method": result.method,
                        "endpoint": result.endpoint,
                        "status_code": result.status_code,
                        "success": result.success,
                        "error": result.error,
                        "response_time_ms": result.response_time_ms,
                    }
                )
            print("\nDetailed results available in verbose mode")

        return failed == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test all API endpoints")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    tester = EndpointTester(base_url=args.base_url, timeout=args.timeout, verbose=args.verbose)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
