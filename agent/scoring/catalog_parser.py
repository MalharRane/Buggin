"""Parse fixtures/BUG_CATALOG.md and fixtures/CHANGE_CATALOG.md into
structured records the matcher can compare findings against.

This module is allowed to know catalog IDs and structure - it IS the ground
truth reader. What must never happen is the AGENT (regression_agent/*)
knowing any of this; see cli.py's leakage check for that guard.
"""
import re

# Only BUG-12's catalog entry documents a second, independent evidence
# channel in prose that isn't a single machine-parseable keyword (it reads
# "a silent action-does-nothing effect ... no further evidence at all",
# which is exactly what a category="dom-missing" finding with empty
# evidence looks like in the agent's report). This override exists because
# that specific sentence was added to the catalog by hand after the agent's
# own report surfaced the behavior - it is not inferred from the agent, and
# it is not applied to any other row. No other row in BUG_CATALOG.md has a
# secondary channel described this way as of this writing.
SECONDARY_EVIDENCE_OVERRIDES = {
    "BUG-12": {"dom-missing"},
}

_CATEGORY_LETTER_TO_NAME = {
    "a": "visual",
    "b": "network",
    "c": "console",
    "d": "dom-missing",
}

_NEGATION_RE = re.compile(
    r"no\s+[a-z/\s]*?\b(visual|console|network|dom-missing)\b[a-z\s]*?(?=[,.(]|$)",
    re.IGNORECASE,
)
_ID_PATTERNS = [
    re.compile(r'data-id="(\d+)"'),
    re.compile(r"\bid=(\d+)\b"),
    re.compile(r"product id (\d+)", re.IGNORECASE),
]


def _split_row(line):
    line = line.strip()
    if not line.startswith("|"):
        return None
    cells = [c.strip() for c in line.split("|")]
    # A well-formed "| a | b | c |" row splits into ['', a, b, c, ''].
    if len(cells) >= 2 and cells[0] == "" and cells[-1] == "":
        cells = cells[1:-1]
    return cells


def _extract_product_id(text):
    for pattern in _ID_PATTERNS:
        m = pattern.search(text)
        if m:
            return int(m.group(1))
    return None


def _extract_page_types(page_flow_text):
    lower = page_flow_text.lower()
    types = set()
    if "listing" in lower:
        types.add("listing")
    if "detail" in lower:
        types.add("product-detail")
    if "checkout" in lower:
        types.add("checkout")
    if "cart" in lower and "checkout" not in lower:
        types.add("cart")
    return types


def _extract_network_resource_hint(text):
    """Only meaningful for category="network" bugs. Two different network
    bugs can share the same page_type/product_id (e.g. BUG-05's broken
    product-5 image and BUG-07's cart/track beacon both surface evidence on
    product 5's pages) - page/product alone isn't precise enough to tell
    them apart, so pull out which resource is actually being talked about."""
    lower = text.lower()
    if "/images/" in lower or ".svg" in lower or (re.search(r"\bimg\b", lower) and "/api/" not in lower):
        return "image"
    if "cart/track" in lower:
        return "cart-track"
    if "/api/checkout" in lower:
        return "checkout-submit"
    if "/api/products/" in lower or re.search(r"products/\d", lower):
        return "products-fetch"
    return None


def _extract_visual_claim(description_text):
    """Which of visual_scan.py's four anomaly types this bug's own
    description is actually describing. Required because two different
    visual bugs can land on the same page (category+page alone isn't
    specific enough - see the dom-missing analogue below, which is the bug
    this whole module of checks exists to fix)."""
    lower = description_text.lower()
    if "background" in lower and ("color" in lower or "invisible" in lower):
        return "low_contrast"
    if "aspect ratio" in lower or "squish" in lower or "stretch" in lower or "mismatched height" in lower:
        return "distorted_image"
    if "overlap" in lower or "on top of" in lower or "stacked" in lower:
        return "overlap"
    if "overflow" in lower or "wraps out of" in lower or "wrap" in lower:
        # The closest thing the scanner can produce for "text spills/wraps
        # and the layout reflows" is the sibling-height-variance check.
        return "uneven_siblings"
    return None


_GENERIC_JS_ERROR_NAMES = {
    "error", "typeerror", "referenceerror", "syntaxerror", "rangeerror",
    "evalerror", "urierror",
}


def _extract_console_keyword(description_text):
    """Pull the specific identifier this bug's console error is about (a
    function name, or the last segment of a property-access chain) out of
    the description's backtick-quoted code spans. Two different console
    bugs can share a page/product; the identifier is what actually
    distinguishes "TypeError reading toUpperCase" from "TypeError reading
    value" as evidence for two different bugs - generic exception class
    names like "TypeError" itself appear in nearly every row's prose and
    would match everything, so they're excluded even though "TypeError"
    technically looks camelCase.
    """
    # Scope the scan to the sentence(s) up through the actual error mention.
    # BUG-12's description, for example, goes on afterward to describe a
    # *second*, unrelated symptom (mentioning addEventListener,
    # renderProductDetail, etc.) - scanning the whole description would
    # pick up those generic DOM/JS API names instead of the property that
    # actually failed.
    error_mention = re.search(r"TypeError|ReferenceError|SyntaxError|RangeError", description_text, re.IGNORECASE)
    if error_mention:
        end = description_text.find(".", error_mention.end())
        if end != -1:
            description_text = description_text[: end + 1]

    spans = re.findall(r"`([^`]+)`", description_text)
    fallback = None
    for span in spans:
        cleaned = re.sub(r"\(.*\)$", "", span).strip()
        candidate = cleaned.split(".")[-1] if "." in cleaned else cleaned
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", candidate):
            continue
        if candidate.lower() in _GENERIC_JS_ERROR_NAMES:
            continue
        if re.search(r"[a-z][A-Z]", candidate):  # camelCase - a real identifier, not prose
            return candidate
        fallback = fallback or candidate
    return fallback


def _extract_dom_missing_claim(description_text, selector_text, evidence_type_text):
    """(claim_type, keyword_words) for a dom-missing bug. This is the fix
    for the over-crediting bug: "a control is gone" and "text never
    appears after an action" are different claims that happen to share
    category=dom-missing and often the same page - without this, any
    finding of either shape credits every bug of either shape on that page.
    """
    combined_lower = f"{description_text} {selector_text} {evidence_type_text}".lower()

    if "confirmation message" in combined_lower or "feedback message" in combined_lower:
        return "feedback_missing", frozenset()

    if "silent action-does-nothing" in combined_lower or "no further evidence at all" in combined_lower:
        return "silent_action", frozenset()

    if "(absent" in selector_text.lower():
        # Pull the LAST id/class token out of the selector (the actual
        # missing element - e.g. in ".product-card[...] a.view-details
        # (absent)" that's ".view-details", not the parent ".product-card"
        # or attribute-selector noise like "data"/"id"), split it into
        # words, e.g. ".qty-decrement" -> {"qty", "decrement"}. Backticks
        # are stripped first since Markdown wraps selectors in them.
        cleaned = selector_text.replace("`", "")
        tokens = re.findall(r"[#.][a-zA-Z][\w-]*", cleaned)
        token = tokens[-1] if tokens else cleaned
        words = frozenset(w.lower() for w in re.split(r"[^a-zA-Z]+", token) if len(w) > 2)
        return "control_missing", words

    return None, frozenset()


def _extract_subflow(selector_text, category):
    # Visual anomalies are captured passively off a page-load DOM scan, never
    # off a specific click action - even when the selector text happens to
    # name an add-to-cart-flavored element (e.g. BUG-01's `#add-to-cart-btn`,
    # a CSS/contrast issue visible on render, not tied to clicking it). Don't
    # extract a subflow for those, or it would falsely fail to match a
    # correctly-captured page-load visual finding (which never carries a
    # subflow) against a bug whose selector just happens to mention a button.
    if category == "visual":
        return None
    lower = selector_text.lower()
    if "add to cart" in lower or "add-to-cart" in lower or "cart/track" in lower:
        return "add-to-cart"
    if "qty-increment" in lower:
        return "increment"
    if "qty-decrement" in lower:
        return "decrement"
    if "checkout-form" in lower or "place-order-btn" in lower:
        return "submit"
    return None


def _extract_secondary_categories(evidence_text, primary):
    """Best-effort: find category keywords in `evidence_text` that are not
    inside a "no X ..." negation phrase and are not the primary category
    itself. This deliberately does NOT catch prose like BUG-12's - that's
    what SECONDARY_EVIDENCE_OVERRIDES is for. Kept generic so a future row
    that plainly writes "network AND console" gets picked up automatically.
    """
    negated_spans = [m.span() for m in _NEGATION_RE.finditer(evidence_text)]

    def is_negated(pos):
        return any(start <= pos < end for start, end in negated_spans)

    found = set()
    for name in ("visual", "console", "network", "dom-missing"):
        for m in re.finditer(re.escape(name), evidence_text, re.IGNORECASE):
            if not is_negated(m.start()):
                found.add(name)
                break
    found.discard(primary)
    return found


def parse_bug_catalog(path):
    """Return a list of bug-record dicts, one per BUG-NN row."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    bugs = []
    for line in lines:
        cells = _split_row(line)
        if not cells or not cells[0].startswith("BUG-"):
            continue
        if len(cells) != 6:
            continue  # malformed/separator row
        bug_id, category_cell, page_flow, description, selector, evidence_type = cells

        letter = category_cell.strip()[0].lower()
        category = _CATEGORY_LETTER_TO_NAME.get(letter)
        if category is None:
            continue

        combined_text = f"{page_flow} {selector}"
        product_id = _extract_product_id(combined_text)
        page_types = _extract_page_types(page_flow)
        subflow = _extract_subflow(selector, category)

        accepted = {category}
        accepted |= _extract_secondary_categories(evidence_type, category)
        accepted |= SECONDARY_EVIDENCE_OVERRIDES.get(bug_id, set())

        network_resource_hint = (
            _extract_network_resource_hint(combined_text) if category == "network" else None
        )
        visual_claim_type = _extract_visual_claim(description) if "visual" in accepted else None
        console_keyword = _extract_console_keyword(description) if "console" in accepted else None
        dom_missing_claim_type, dom_missing_keywords = (
            _extract_dom_missing_claim(description, selector, evidence_type)
            if "dom-missing" in accepted else (None, frozenset())
        )

        bugs.append({
            "id": bug_id,
            "category": category,
            "accepted_categories": accepted,
            "page_flow_text": page_flow,
            "description": description,
            "selector_text": selector,
            "evidence_type_text": evidence_type,
            "page_types": page_types,
            "product_id": product_id,  # None means "any product" / page-level
            "subflow": subflow,
            "network_resource_hint": network_resource_hint,
            "visual_claim_type": visual_claim_type,
            "console_keyword": console_keyword,
            "dom_missing_claim_type": dom_missing_claim_type,
            "dom_missing_keywords": dom_missing_keywords,
        })

    return bugs


def parse_change_catalog(path):
    """Return a list of change-record dicts, one per CHANGE-NN row. Used
    only for context/annotation on v1-clean runs - v1-clean scoring doesn't
    need to map findings to specific changes (every finding is a false
    positive by definition), but showing which change a false positive
    landed near helps a human judge it faster."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changes = []
    for line in lines:
        cells = _split_row(line)
        if not cells:
            continue
        id_match = re.search(r"CHANGE-(\d+)", cells[0])
        if not id_match or len(cells) != 4:
            continue
        change_id = f"CHANGE-{id_match.group(1)}"
        page, description, why_harmless = cells[1], cells[2], cells[3]
        changes.append({
            "id": change_id,
            "page_text": page,
            "description": description,
            "why_harmless": why_harmless,
            "is_structural_flow_change": "structural" in cells[0].lower() or "structural" in description.lower(),
        })

    return changes
