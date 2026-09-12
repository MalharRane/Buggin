"""CLI entrypoint for the scoring harness.

Usage:
    python -m scoring.cli --report out/v1-buggy/report.json --target v1-buggy
    python -m scoring.cli --report out/v1-clean/report.json --target v1-clean

Reads the agent's report.json and the ground-truth catalogs, computes a
scorecard, and writes it to stdout plus a markdown file next to the report.
This module never touches or imports anything from regression_agent/ - it
only reads report.json as data, exactly as a human grader would.
"""
import argparse
import json
import os
import sys

from .catalog_parser import parse_bug_catalog, parse_change_catalog
from .scorecard import check_leakage, score_buggy_run, score_clean_run, render_buggy_markdown, render_clean_markdown

DEFAULT_BUG_CATALOG = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "BUG_CATALOG.md")
DEFAULT_CHANGE_CATALOG = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "CHANGE_CATALOG.md")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Path to the agent's report.json")
    parser.add_argument("--target", required=True, choices=["v1-buggy", "v1-clean"])
    parser.add_argument("--bug-catalog", default=DEFAULT_BUG_CATALOG)
    parser.add_argument("--change-catalog", default=DEFAULT_CHANGE_CATALOG)
    parser.add_argument("--out", default=None, help="Output .md path (default: alongside --report)")
    args = parser.parse_args(argv)

    leakage = check_leakage(args.report)

    if args.target == "v1-buggy":
        bugs = parse_bug_catalog(args.bug_catalog)
        score = score_buggy_run(args.report, bugs)
        markdown = render_buggy_markdown(score, leakage)
    else:
        parse_change_catalog(args.change_catalog)  # parsed for context/consistency; not needed for scoring math
        score = score_clean_run(args.report)
        markdown = render_clean_markdown(score, leakage)

    out_path = args.out or os.path.join(os.path.dirname(args.report), "scorecard.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    json_out_path = os.path.splitext(out_path)[0] + ".json"
    with open(json_out_path, "w", encoding="utf-8") as f:
        json.dump({"leakage": leakage, "score": score}, f, indent=2, default=list)

    print(markdown)
    print(f"\n(written to {out_path} and {json_out_path})", file=sys.stderr)
    return 1 if leakage else 0


if __name__ == "__main__":
    sys.exit(main())
