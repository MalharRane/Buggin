"""LLM adjudication for the one bucket the rule engine can't resolve on its
own: a checkout flow whose path/DOM structure changed but which still
reaches a successful terminal state on both baseline and candidate. A rule
can't tell "a developer added a legitimate extra step" (not a regression)
apart from "something broke and the flow now limps through an unintended
detour to a technically-successful end state" (a regression) - that call
needs judgment, so it's the only thing sent to an LLM.

Every other finding in rules.py is already unambiguous (a new console
error, a request that regressed from 2xx to non-2xx, a new visual anomaly,
a control that's no longer reachable, a flow that no longer completes at
all, or missing post-action feedback text) and is never routed through
here.

Uses Groq (not Anthropic) - see MODEL below, pinned from a live query
against https://api.groq.com/openai/v1/models.
"""
import json
import os

from pydantic import BaseModel

MODEL = "openai/gpt-oss-120b"  # Groq-hosted; supports response_format json_schema (structured_outputs)

SYSTEM_PROMPT = """You are adjudicating one finding for a web-app regression-testing agent.

You will be given ONE finding where a checkout-style flow's path/DOM
structure differs between a known-good baseline run and a candidate run of
a (possibly changed) version of the same app. This finding type is only
ever raised when BOTH runs reached a successful terminal state (the flow
completed on both sides) - that is guaranteed by how the finding was
generated, not something you need to verify. Deterministic checks upstream
have already separately confirmed there is no new console error, no new
failed network request, and no new visual anomaly anywhere along either
path - this finding is ONLY about the path/structure differing. Do not
assume, infer, or invent any fact beyond the evidence JSON you are given;
if the evidence doesn't say it, it isn't true.

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


_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "adjudication_result",
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["legitimate_change", "regression"]},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["verdict", "confidence", "reasoning"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


def _client():
    import groq
    return groq.Groq()  # reads GROQ_API_KEY from the environment


def adjudicate(findings):
    """Mutates and returns `findings`: every finding with
    confidence == "ambiguous" gets a verdict/reasoning filled in (or an
    "unresolved" verdict if the LLM call itself fails, e.g. no credentials
    configured - this must never crash the whole report, and must never
    default to "regression" just because the call failed)."""
    for finding in findings:
        if finding["confidence"] != "ambiguous":
            continue

        prompt = (
            f"Finding: {finding['description']}\n\n"
            "Evidence (JSON) - this is the ONLY evidence available for this "
            "finding; do not assume or invent anything beyond it:\n"
            f"{json.dumps(finding['evidence'], indent=2)}\n\n"
            "Does the changed checkout flow shown above still accomplish its "
            "goal (a legitimate change), or is it a regression? Classify this finding."
        )

        try:
            client = _client()
            completion = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=_RESPONSE_FORMAT,
            )
            raw = completion.choices[0].message.content
            result = AdjudicationResult.model_validate_json(raw)
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
    return bool(os.environ.get("GROQ_API_KEY"))
