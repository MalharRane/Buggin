"""One-off utility: re-translate the flows in tests/flows/ and overwrite
the pinned JSON in tests/translated/. Only run this deliberately, after a
flow_translator change you've reviewed - it calls the live Groq LLM
(needs GROQ_API_KEY) and its output is non-deterministic, so re-running it
casually will churn the pinned files with no real change underneath.

Usage:
    python -m flow_runner.tests.regenerate_translated
"""
import json
import os
import sys

from flow_translator.parser import load_flow
from flow_translator.translate import translate_flow

_HERE = os.path.dirname(__file__)
_NAMES = ["checker_full_pass", "checker_wrong_count", "checker_quantity_stress"]


def main():
    for name in _NAMES:
        flow = load_flow(os.path.join(_HERE, "flows", f"{name}.yaml"))
        translated = translate_flow(flow)
        payload = json.loads(translated.model_dump_json(indent=2))
        out_path = os.path.join(_HERE, "translated", f"{name}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out_path} ({len(payload['steps'])} steps) - review the diff before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
