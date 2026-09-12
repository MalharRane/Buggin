"""LLM adjudication for the one bucket the rule engine can't resolve on its
own: a checkout flow whose path/DOM structure changed but which still
reaches a successful terminal state on both baseline and candidate. A rule
can't tell "a developer added a legitimate extra step" (not a regression)
apart from "something broke and the flow now limps through an unintended
detour to a technically-successful end state" (a regression) - that call
needs judgment, so it's the only thing sent to Claude.

Every other finding in rules.py is already unambiguous (a new console
error, a request that regressed from 2xx to non-2xx, a new visual anomaly,
a control that's no longer reachable, a flow that no longer completes at
all) and is never routed through here.
"""
import json
import os

from pydantic import BaseModel

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are adjudicating findings for a web-app regression-testing agent.

You will be given ONE finding where a checkout-style flow's path/DOM
structure differs between a known-good baseline run and a candidate run of
a (possibly changed) version of the same app - but BOTH runs reached a
successful terminal state (the flow completed). Deterministic checks have
already confirmed there is no new console error, no new failed network
request, and no new visual anomaly anywhere along either path - this
finding is ONLY about the path/structure differing.

Decide:
- "legitimate_change": the extra/different step(s) look like a real,
  coherent, working product change (e.g. an added confirmation/review
  screen, a reordered step, a renamed but present control) - the kind of
  change a developer would ship on purpose. The flow still makes sense to a
  user and completes correctly.
- "regression": the structural change looks like an accidental side effect
  of something breaking - e.g. a nonsensical detour, a step that shouldn't
  exist, evidence the flow only "succeeds" by accident, or missing/garbled
  content in the intermediate step(s).

Base your call only on the evidence given. Be concise."""


class AdjudicationResult(BaseModel):
    verdict: str  # "legitimate_change" or "regression"
    confidence: float  # 0.0-1.0
    reasoning: str


def _client():
    import anthropic
    return anthropic.Anthropic()


def adjudicate(findings):
    """Mutates and returns `findings`: every finding with
    confidence == "ambiguous" gets a verdict/reasoning filled in (or an
    "unresolved" verdict if the LLM call itself fails, e.g. no credentials
    configured - this must never crash the whole report)."""
    for finding in findings:
        if finding["confidence"] != "ambiguous":
            continue

        prompt = (
            f"Finding: {finding['description']}\n\n"
            f"Evidence (JSON):\n{json.dumps(finding['evidence'], indent=2)}\n\n"
            "Classify this finding."
        )

        try:
            client = _client()
            response = client.messages.parse(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_format=AdjudicationResult,
            )
            result = response.parsed_output
            finding["verdict"] = result.verdict
            finding["reasoning"] = result.reasoning
            finding["llm_confidence"] = result.confidence
        except Exception as exc:
            finding["verdict"] = "unresolved"
            finding["reasoning"] = (
                f"LLM adjudication failed ({exc.__class__.__name__}: {exc}). "
                "This finding needs manual review - it was not auto-flagged "
                "as a regression, but it was also not cleared."
            )

    return findings


def has_api_credentials():
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
    )
