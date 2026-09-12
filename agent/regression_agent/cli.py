"""CLI entrypoint.

Usage:
    python -m regression_agent.cli --target v1-buggy --out out/v1-buggy
    python -m regression_agent.cli --target v1-clean --out out/v1-clean

Runs the crawler against v0-baseline (from --baseline-url, default
http://localhost:3000) and the named target, diffs them, adjudicates any
ambiguous structural-divergence findings, and writes report.json +
report.md into --out.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

from . import config
from .capture import run_capture
from .rules import diff_profiles
from .adjudicate import adjudicate, has_api_credentials
from .report import write_json, write_markdown


def _crawl(base_url, name, timeout_ms):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            result = run_capture(page, base_url, name)
        finally:
            browser.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target version name, e.g. v1-buggy or v1-clean")
    parser.add_argument("--target-url", default=None, help="Override target base URL")
    parser.add_argument("--baseline-url", default=config.DEFAULT_VERSIONS["v0-baseline"])
    parser.add_argument("--baseline-name", default="v0-baseline")
    parser.add_argument("--out", required=True, help="Output directory for report.json/report.md")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="Playwright default action timeout")
    parser.add_argument("--no-adjudicate", action="store_true", help="Skip the LLM adjudication step entirely")
    parser.add_argument("--save-captures", action="store_true", help="Also save the raw capture JSON for both runs")
    args = parser.parse_args(argv)

    target_url = args.target_url or config.DEFAULT_VERSIONS.get(args.target)
    if target_url is None:
        parser.error(f"Unknown target '{args.target}' - pass --target-url explicitly")

    os.makedirs(args.out, exist_ok=True)

    print(f"Crawling baseline ({args.baseline_name}) at {args.baseline_url} ...", file=sys.stderr)
    baseline_run = _crawl(args.baseline_url, args.baseline_name, args.timeout_ms)

    print(f"Crawling target ({args.target}) at {target_url} ...", file=sys.stderr)
    target_run = _crawl(target_url, args.target, args.timeout_ms)

    if args.save_captures:
        with open(os.path.join(args.out, "capture_baseline.json"), "w", encoding="utf-8") as f:
            json.dump(baseline_run, f, indent=2)
        with open(os.path.join(args.out, "capture_target.json"), "w", encoding="utf-8") as f:
            json.dump(target_run, f, indent=2)

    print("Diffing against baseline ...", file=sys.stderr)
    findings = diff_profiles(baseline_run, target_run)

    ambiguous_count = sum(1 for f in findings if f["confidence"] == "ambiguous")
    if ambiguous_count and not args.no_adjudicate:
        if not has_api_credentials():
            print(
                f"Warning: {ambiguous_count} ambiguous finding(s) need LLM adjudication "
                "but no Anthropic credentials were found (ANTHROPIC_API_KEY / "
                "ANTHROPIC_AUTH_TOKEN / ant auth login). They will be marked 'unresolved'.",
                file=sys.stderr,
            )
        print(f"Adjudicating {ambiguous_count} ambiguous finding(s) ...", file=sys.stderr)
        adjudicate(findings)
    elif ambiguous_count:
        print(f"Skipping adjudication for {ambiguous_count} ambiguous finding(s) (--no-adjudicate).", file=sys.stderr)

    run_meta = {
        "baseline_name": args.baseline_name,
        "baseline_url": args.baseline_url,
        "target_name": args.target,
        "target_url": target_url,
    }
    write_json(findings, run_meta, os.path.join(args.out, "report.json"))
    write_markdown(findings, run_meta, os.path.join(args.out, "report.md"))

    surfaced = [f for f in findings if f["confidence"] == "high" or f.get("verdict") == "regression"]
    print(f"\n{len(surfaced)} finding(s) reported. See {args.out}/report.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
