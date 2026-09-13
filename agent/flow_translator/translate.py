"""Translate a user-authored Flow into a concrete, machine-executable
TranslatedFlow - via one Groq call per flow, no browser involved.

Uses the same provider/model family as regression_agent/adjudicate.py
(Groq, structured output via response_format json_schema), but this module
does not import from regression_agent - it's a standalone LLM call kept
consistent by convention, not by coupling.
"""
import json

from .models import Flow, TranslatedFlow

MODEL = "openai/gpt-oss-120b"  # same model pinned for regression_agent/adjudicate.py

SYSTEM_PROMPT = """You are a translator for a web-app testing tool. You convert a plain-language,
user-authored test flow into a concrete, machine-executable step plan - WITHOUT
running anything yourself, and without seeing any actual web page.

Downstream, a generic browser crawler will execute your plan by finding
elements the way a human would describe them - by visible TEXT, by ROLE
(button/link), or by a form field's LABEL - never by CSS/XPath selectors,
never by position (nth-child), never assuming a specific page's markup.
Every locator you produce must follow that convention.

For each user-authored step, produce exactly one translated step, in the
same order, with the same step_index (0-based). Do not add a step the user
didn't write. Do not drop or reinterpret an "expect" the user gave - it must
survive as a checkable expectation. If a step is too vague to translate into
concrete operations with confidence (it names no specific target, or it
bundles an entire untested feature into one vague phrase like "test the
checkout"), do NOT guess or fabricate a plan for it - instead set
needs_clarification to true, give a one-sentence clarification_reason, and
leave operations as an empty list.

Operation vocabulary - each operation has "op" plus only the fields relevant
to that op; leave every irrelevant field as an empty string "":

- "navigate": load a whole page. Set target_page to a short semantic name
  (e.g. "listing", "cart", "checkout", "home"). If reaching it requires
  clicking a nav element rather than being the flow's very first page load
  (e.g. "go to the cart" partway through a flow), ALSO set
  locator_by/locator_value/locator_role for that click.
- "click": click a visible element. Set locator_by to one of "text", "role",
  "label", or "url"; locator_value to the text/label/url-fragment to match;
  locator_role to a role hint like "button" or "link" if you can tell, else
  leave it "".
- "fill": fill one form field. Set field_label to the field's plain-language
  name (e.g. "name", "email", "address") and value to a concrete, obviously
  fake test value appropriate to that field (a fake full name, an
  address-shaped string, an email like "test.user@example.com" for any
  "valid email" style requirement). A single user step may require several
  fill operations plus a trailing click under ONE translated step (e.g.
  "fill name, email, address, then place the order" -> three fill
  operations followed by one click operation) - decompose freely, but never
  invent an operation for something the action text didn't ask for.
- "assert": the step itself performs no browser action - it is purely a
  check (e.g. "verify the price is shown"). Leave every field on this
  operation empty; the actual check goes in the step's expect_type/
  expect_detail, described below.

Expectation vocabulary (expect_type on the translated step, not on the
operation):
- "text_appears": expect_detail is the text that should become visible.
- "element_present": expect_detail describes (by visible text/role/label)
  the element that should exist.
- "url_contains": expect_detail is a URL fragment the page should navigate to.
- "no_error": no specific text/element check - just "this should complete
  without an error."
- "none": the user's step had no "expect" - do not fabricate one; expect_detail
  must be "" in this case.

Base every translated step ONLY on the user's own action/expect text for
that step. Never invent a step, an operation, or an expectation the user
did not write."""


def _flow_to_schema(step_count: int) -> dict:
    operation_schema = {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": ["navigate", "click", "fill", "assert"]},
            "target_page": {"type": "string"},
            "locator_by": {"type": "string", "enum": ["text", "role", "label", "url", ""]},
            "locator_value": {"type": "string"},
            "locator_role": {"type": "string"},
            "field_label": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": [
            "op", "target_page", "locator_by", "locator_value",
            "locator_role", "field_label", "value",
        ],
        "additionalProperties": False,
    }

    step_schema = {
        "type": "object",
        "properties": {
            "step_index": {"type": "integer"},
            "original_action": {"type": "string"},
            "original_expect": {"type": "string"},
            "operations": {"type": "array", "items": operation_schema},
            "expect_type": {
                "type": "string",
                "enum": ["text_appears", "element_present", "url_contains", "no_error", "none"],
            },
            "expect_detail": {"type": "string"},
            "needs_clarification": {"type": "boolean"},
            "clarification_reason": {"type": "string"},
        },
        "required": [
            "step_index", "original_action", "original_expect", "operations",
            "expect_type", "expect_detail", "needs_clarification", "clarification_reason",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "translated_flow",
            "schema": {
                "type": "object",
                "properties": {
                    "flow_name": {"type": "string"},
                    # Structurally enforced, not just prompted: exactly one
                    # output step per input step.
                    "steps": {
                        "type": "array",
                        "items": step_schema,
                        "minItems": step_count,
                        "maxItems": step_count,
                    },
                },
                "required": ["flow_name", "steps"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


def _build_prompt(flow: Flow) -> str:
    lines = [f'Flow name: "{flow.flow}"', "", "Steps (0-indexed):"]
    for i, step in enumerate(flow.steps):
        expect = step.expect if step.expect else "(none given)"
        lines.append(f'{i}. action: "{step.action}"')
        lines.append(f"   expect: {expect!r}" if step.expect else "   expect: none")
    lines.append("")
    lines.append(f"Produce exactly {len(flow.steps)} translated step(s), matching step_index 0..{len(flow.steps) - 1}.")
    return "\n".join(lines)


def _client():
    import groq
    return groq.Groq()  # reads GROQ_API_KEY from the environment


def translate_flow(flow: Flow) -> TranslatedFlow:
    """Translate `flow` into a TranslatedFlow. Raises on API/parse failure -
    this module does no silent fallback, since an un-executed, unvalidated
    plan should never be treated as usable by construction."""
    client = _client()
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(flow)},
        ],
        response_format=_flow_to_schema(len(flow.steps)),
    )
    raw = completion.choices[0].message.content
    translated = TranslatedFlow.model_validate_json(raw)

    # Ground truth for what the user actually wrote should never depend on
    # the model faithfully echoing it back - overwrite from the source flow
    # by index rather than trusting the model's copy.
    for i, step in enumerate(flow.steps):
        translated.steps[i].step_index = i
        translated.steps[i].original_action = step.action
        translated.steps[i].original_expect = step.expect

    return translated


def translate_flow_to_dict(flow: Flow) -> dict:
    return json.loads(translate_flow(flow).model_dump_json(indent=2))
