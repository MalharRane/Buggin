"""CLI entrypoint.

Usage:
    python -m flow_translator.cli --flow examples/checkout.yaml --out out/checkout.json

Loads a flow file, translates it via translate_flow(), and writes the
result as readable JSON. Does not touch a browser and does not import
regression_agent/scoring.
"""
import argparse
import json
import os
import sys

from .parser import load_flow
from .translate import translate_flow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", required=True, help="Path to a YAML/JSON flow file")
    parser.add_argument("--out", default=None, help="Where to write the translated JSON (default: stdout only)")
    args = parser.parse_args(argv)

    flow = load_flow(args.flow)
    print(f"Loaded flow {flow.flow!r} with {len(flow.steps)} step(s). Translating...", file=sys.stderr)

    translated = translate_flow(flow)
    payload = json.loads(translated.model_dump_json(indent=2))
    text = json.dumps(payload, indent=2)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.out}", file=sys.stderr)

    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
