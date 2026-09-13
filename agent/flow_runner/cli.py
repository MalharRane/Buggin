"""CLI entrypoint.

Usage:
    python -m flow_runner.cli --flow <path/to/flow.yaml> --url http://localhost:3001 --out out/run.json

Loads a flow file, translates it (flow_translator.translate_flow), executes
it in a real browser against --url (flow_runner.runner.run_flow), and
prints a readable summary plus the full JSON result.
"""
import argparse
import json
import os
import sys

from flow_translator.parser import load_flow
from flow_translator.translate import translate_flow

from .runner import AppUnreachableError, run_flow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", required=True, help="Path to a YAML/JSON flow file")
    parser.add_argument("--url", required=True, help="Base URL of the running app, e.g. http://localhost:3001")
    parser.add_argument("--out", default=None, help="Where to write the full JSON result")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    args = parser.parse_args(argv)

    flow = load_flow(args.flow)
    print(f"Loaded flow {flow.flow!r} with {len(flow.steps)} step(s). Translating via Groq...", file=sys.stderr)
    translated = translate_flow(flow)

    print(f"Executing against {args.url} ...", file=sys.stderr)
    try:
        result = run_flow(translated, args.url, timeout_ms=args.timeout_ms)
    except AppUnreachableError as exc:
        print(f"\nCould not run this flow: {exc}", file=sys.stderr)
        print("This is a precondition failure, not a finding about the app - "
              "check that the server is actually running at that URL.", file=sys.stderr)
        return 2

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.out}", file=sys.stderr)

    print(f"\n=== {result['flow_name']} @ {result['base_url']} ===")
    for s in result["steps"]:
        marker = "expect met" if s.get("expectation_met") is True else (
            "expect UNMET" if s.get("expectation_met") is False else "")
        print(f"  [{s['status']}] step {s['step_index']}: {s['action']}" + (f"  ({marker})" if marker else ""))

    print(f"\n{len(result['findings'])} finding(s):")
    for f in result["findings"]:
        print(f"  - [{f['category']}] {f['page']}: {f['description']}")
    if not result["findings"]:
        print("  (none)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
