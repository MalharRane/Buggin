"""Data model for the natural-language flow translator.

Two halves: the INPUT shape (what a user hand-writes in YAML/JSON - see
../flow_translator/examples/*.yaml) and the OUTPUT shape (a concrete,
machine-executable step plan an LLM produces from it). Nothing here
executes a browser or imports regression_agent/scoring - this module only
translates and validates.

Output-side fields deliberately avoid Optional/nullable types (every field
is always present, with "" / [] / "none" as the "not applicable" sentinel)
because that keeps the JSON schema handed to Groq's strict structured-
output mode flat and simple - no nullable-object or union-type edge cases
to get wrong.
"""
from typing import List

from pydantic import BaseModel


# ---- Input: what the user writes ----


class FlowStep(BaseModel):
    action: str
    expect: str = ""  # "" means the user gave no expectation for this step


class Flow(BaseModel):
    flow: str
    steps: List[FlowStep]


# ---- Output: the translated, concrete step plan ----


class Operation(BaseModel):
    op: str  # "navigate" | "click" | "fill" | "assert"

    # navigate
    target_page: str = ""  # short semantic name, e.g. "listing", "cart", "checkout"

    # click / navigate-via-click - locator strategy mirrors locators.py's
    # text/role/label discovery, never a CSS/XPath/nth-child selector
    locator_by: str = ""  # "text" | "role" | "label" | "url" | ""
    locator_value: str = ""
    locator_role: str = ""  # e.g. "button", "link" - a hint, not required

    # fill
    field_label: str = ""  # plain-language field name, e.g. "email"
    value: str = ""  # concrete test value


class TranslatedStep(BaseModel):
    step_index: int
    original_action: str
    original_expect: str  # "" if the user gave none

    operations: List[Operation]

    expect_type: str  # "text_appears" | "element_present" | "url_contains" | "no_error" | "none"
    expect_detail: str  # "" when expect_type == "none"

    needs_clarification: bool
    clarification_reason: str  # "" when needs_clarification is False


class TranslatedFlow(BaseModel):
    flow_name: str
    steps: List[TranslatedStep]
