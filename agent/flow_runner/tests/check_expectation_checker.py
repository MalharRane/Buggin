"""Regression tests pinning flow_runner's expectation-checker behavior in
both directions - it must not silently pass an unmet expectation, and it
must not fail a genuinely met one. See flow_runner/README.md for the two
real bugs these caught before the checker could be trusted.

These load PRE-TRANSLATED, saved JSON plans (tests/translated/*.json)
rather than calling the live LLM translator: translate_flow()'s output
varies between calls (different wording, occasionally a different
expect_type for the same input), which would make a test built on live
translation flaky for reasons that have nothing to do with the matcher
being pinned here. Loading a saved plan means these tests exercise ONLY
run_flow()'s deterministic logic (locator resolution + expectation
checking) - exactly what needs pinning.

Usage (requires versions/v0-baseline running - no GROQ_API_KEY needed,
since no live translation call is made):

    python -m flow_runner.tests.check_expectation_checker --url http://localhost:3000

To re-pin the translated plans after a deliberate flow_translator change
(needs GROQ_API_KEY):

    python -m flow_runner.tests.regenerate_translated
"""
import argparse
import json
import os
import sys

from flow_translator.models import TranslatedFlow

from ..runner import run_flow

_HERE = os.path.dirname(__file__)


def _load_translated(name):
    with open(os.path.join(_HERE, "translated", f"{name}.json"), encoding="utf-8") as f:
        return TranslatedFlow.model_validate(json.load(f))


def _run(name, url, timeout_ms):
    translated = _load_translated(name)
    return run_flow(translated, url, timeout_ms=timeout_ms)


def check_full_pass(url, timeout_ms):
    """checker_full_pass.yaml: 6 steps, 3 explicit `expect`s, runs to
    completion on a working app. Every expectation should hold - anything
    reported here is either a false-positive expectation failure or a
    genuine regression in locator resolution."""
    result = _run("checker_full_pass", url, timeout_ms)
    passed = len(result["findings"]) == 0
    detail = f"{len(result['findings'])} finding(s) (expected 0)"
    return passed, detail, result


def check_wrong_count(url, timeout_ms):
    """checker_wrong_count.yaml: adds 1 item, then claims 2 - no other
    telemetry signal exists, so the ONLY way to catch this is the
    expectation checker itself. Must produce exactly one
    expectation-unmet finding, nothing else."""
    result = _run("checker_wrong_count", url, timeout_ms)
    categories = [f["category"] for f in result["findings"]]
    passed = categories == ["expectation-unmet"]
    detail = f"finding categories: {categories} (expected exactly ['expectation-unmet'])"
    return passed, detail, result


def check_quantity_stress(url, timeout_ms):
    """checker_quantity_stress.yaml: adds 2 DIFFERENT products (qty 1
    each), then claims the cart shows 1 item. A bare "1" (one product
    row's own quantity) is a substring of "1 item" - this is the exact
    scenario that used to spuriously PASS before _numeric_claim_supported
    was added. Must produce exactly one expectation-unmet finding."""
    result = _run("checker_quantity_stress", url, timeout_ms)
    categories = [f["category"] for f in result["findings"]]
    passed = categories == ["expectation-unmet"]
    detail = f"finding categories: {categories} (expected exactly ['expectation-unmet'] - NOT a spurious pass)"
    return passed, detail, result


CHECKS = [
    ("checker_full_pass", check_full_pass),
    ("checker_wrong_count", check_wrong_count),
    ("checker_quantity_stress", check_quantity_stress),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of v0-baseline, e.g. http://localhost:3000")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    args = parser.parse_args(argv)

    all_passed = True
    for name, check_fn in CHECKS:
        try:
            passed, detail, _ = check_fn(args.url, args.timeout_ms)
        except Exception as exc:
            passed, detail = False, f"raised {exc.__class__.__name__}: {exc}"
        print(f"[{'PASS' if passed else 'FAIL'}] {name} - {detail}")
        all_passed = all_passed and passed

    print()
    if all_passed:
        print("All expectation-checker regression tests passed.")
        return 0
    print("Some expectation-checker regression tests FAILED - see above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
