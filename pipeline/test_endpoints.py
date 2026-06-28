"""
Thorough smoke/integration tests for pipeline API endpoints.
Run with: python pipeline/test_endpoints.py [--base URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_BASE = "http://127.0.0.1:8765"
TICKER = "RELIANCE.NS"


@dataclass
class TestResult:
    name: str
    method: str
    path: str
    expected_status: int
    actual_status: int
    passed: bool
    duration_ms: float
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None


def request(
    base: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 300,
) -> tuple[int, Any, float]:
    url = base + path
    data = None
    headers: Dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            elapsed = (time.perf_counter() - start) * 1000
            try:
                return resp.status, json.loads(raw), elapsed
            except json.JSONDecodeError:
                return resp.status, raw, elapsed
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw), elapsed
        except json.JSONDecodeError:
            return e.code, raw, elapsed


def run_test(
    base: str,
    name: str,
    method: str,
    path: str,
    expected_status: int,
    validate,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 300,
) -> TestResult:
    notes: List[str] = []
    try:
        status, data, elapsed = request(base, method, path, body=body, timeout=timeout)
        passed = status == expected_status
        if passed and validate:
            try:
                validate(data)
            except AssertionError as e:
                passed = False
                notes.append(str(e))
        if not passed and status != expected_status:
            notes.append(f"expected HTTP {expected_status}, got {status}")
        if isinstance(data, dict) and data.get("detail"):
            notes.append(f"detail: {str(data['detail'])[:200]}")
        return TestResult(
            name=name,
            method=method,
            path=path,
            expected_status=expected_status,
            actual_status=status,
            passed=passed,
            duration_ms=round(elapsed, 1),
            notes=notes,
        )
    except Exception as e:
        return TestResult(
            name=name,
            method=method,
            path=path,
            expected_status=expected_status,
            actual_status=-1,
            passed=False,
            duration_ms=0,
            error=str(e),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--ticker", default=TICKER)
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip slow LLM pipeline run")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    ticker = urllib.parse.quote(args.ticker, safe="")

    tests: List[TestResult] = []

    tests.append(
        run_test(
            base,
            "health",
            "GET",
            "/health",
            200,
            lambda d: (
                assert_eq(d.get("status"), "ok"),
                assert_eq(d.get("data_vendor"), "yfinance"),
                assert_true("polygon_configured" not in d, "polygon_configured should be removed"),
            ),
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "config",
            "GET",
            "/v1/config",
            200,
            lambda d: (
                assert_in("fast", d.get("pipeline_modes", [])),
                assert_eq(d.get("env", {}).get("data_vendor"), "yfinance"),
            ),
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "fundamentals",
            "GET",
            f"/v1/fundamentals/{ticker}?mode=standard",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_true(bool(d.get("one_line_verdict")), "missing one_line_verdict"),
                assert_true(bool(d.get("dimension_scores")), "missing dimension_scores"),
                assert_true(bool(d.get("source_data")), "missing source_data"),
            ),
            timeout=180,
        )
    )

    tests.append(
        run_test(
            base,
            "fundamentals_deep_mode",
            "GET",
            f"/v1/fundamentals/{ticker}?mode=deep",
            200,
            lambda d: assert_eq(d.get("ticker"), args.ticker.upper()),
            timeout=180,
        )
    )

    tests.append(
        run_test(
            base,
            "fundamentals_data",
            "GET",
            f"/v1/fundamentals/{ticker}/data?mode=standard",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_eq(d.get("mode"), "standard"),
                assert_true(bool(d.get("tier0")), "missing tier0"),
                assert_eq(d["tier0"].get("ticker"), args.ticker.upper()),
            ),
            timeout=180,
        )
    )

    tests.append(
        run_test(
            base,
            "news",
            "GET",
            f"/v1/news/{ticker}?max_results=3",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_eq(d.get("provider"), "tavily"),
                assert_true("api_key_configured" in d),
                assert_true(isinstance(d.get("results"), list)),
                assert_true(isinstance(d.get("formatted"), str)),
            ),
            timeout=60,
        )
    )

    tests.append(
        run_test(
            base,
            "news_max_results_bounds",
            "GET",
            f"/v1/news/{ticker}?max_results=10",
            200,
            lambda d: assert_true(len(d.get("results", [])) <= 10),
            timeout=60,
        )
    )

    tests.append(
        run_test(
            base,
            "earnings_mock",
            "GET",
            f"/v1/earnings/{ticker}/important-parts?source=mock",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_true(d.get("available") is True),
                assert_true(bool(d.get("data")), "earnings data empty"),
            ),
            timeout=60,
        )
    )

    tests.append(
        run_test(
            base,
            "earnings_auto",
            "GET",
            f"/v1/earnings/{ticker}/important-parts?source=auto",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_true("available" in d),
            ),
            timeout=60,
        )
    )

    tests.append(
        run_test(
            base,
            "ticker_context",
            "GET",
            f"/v1/tickers/{ticker}/context?max_news_results=2&earnings_source=mock",
            200,
            lambda d: (
                assert_eq(d.get("ticker"), args.ticker.upper()),
                assert_true("news" in d),
                assert_true("earnings_call" in d),
                assert_true(d["earnings_call"].get("available") is True),
            ),
            timeout=120,
        )
    )

    if not args.skip_pipeline:
        tests.append(
            run_test(
                base,
                "pipeline_run",
                "POST",
                "/v1/pipeline/run",
                200,
                lambda d: (
                    assert_true("results" in d),
                    assert_true(args.ticker.upper() in d["results"] or "_run_summary" in d["results"]),
                ),
                body={"tickers": [args.ticker.upper()], "force_refresh": False, "mode": "fast"},
                timeout=600,
            )
        )

    # Validation / error cases
    tests.append(
        run_test(
            base,
            "empty_ticker_rejected",
            "GET",
            "/v1/fundamentals/%20",
            400,
            lambda d: assert_true("detail" in d),
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "pipeline_empty_tickers",
            "POST",
            "/v1/pipeline/run",
            422,
            lambda d: assert_true("detail" in d),
            body={"tickers": [], "force_refresh": False, "mode": "fast"},
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "news_invalid_max_results",
            "GET",
            f"/v1/news/{ticker}?max_results=99",
            422,
            lambda d: assert_true("detail" in d),
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "earnings_invalid_source",
            "GET",
            f"/v1/earnings/{ticker}/important-parts?source=edgar",
            422,
            lambda d: assert_true("detail" in d),
            timeout=10,
        )
    )

    tests.append(
        run_test(
            base,
            "fundamentals_invalid_mode",
            "GET",
            f"/v1/fundamentals/{ticker}?mode=fast",
            422,
            lambda d: assert_true("detail" in d),
            timeout=10,
        )
    )

    # Print report
    passed = sum(1 for t in tests if t.passed)
    failed = [t for t in tests if not t.passed]

    print(f"\n{'='*72}")
    print(f"  Pipeline API Endpoint Tests — {base}")
    print(f"  Ticker: {args.ticker.upper()}")
    print(f"{'='*72}\n")

    for t in tests:
        mark = "PASS" if t.passed else "FAIL"
        print(f"  [{mark}] {t.method:4} {t.path}")
        print(f"         HTTP {t.actual_status} (expected {t.expected_status}) — {t.duration_ms}ms")
        if t.notes:
            for note in t.notes:
                print(f"         ↳ {note}")
        if t.error:
            print(f"         ↳ ERROR: {t.error}")

    print(f"\n{'='*72}")
    print(f"  Results: {passed}/{len(tests)} passed")
    if failed:
        print(f"  Failed: {', '.join(t.name for t in failed)}")
    print(f"{'='*72}\n")

    return 0 if not failed else 1


def assert_eq(a, b):
    if a != b:
        raise AssertionError(f"expected {b!r}, got {a!r}")


def assert_true(cond, msg="assertion failed"):
    if not cond:
        raise AssertionError(msg)


def assert_in(item, container):
    if item not in container:
        raise AssertionError(f"{item!r} not in {container!r}")


if __name__ == "__main__":
    sys.exit(main())
