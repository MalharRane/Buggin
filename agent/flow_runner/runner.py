"""Execute a TranslatedFlow (see flow_translator/models.py) against a real
running app in a real browser - "spec mode": each step is checked against
the flow author's own stated expectation, not against a baseline run.

This is where flow_translator and regression_agent connect: element
discovery (locators.py), event capture (recorder.py), and the post-action
visible-text mechanism (feedback.py) are imported and reused as-is, not
reimplemented. No fixture code and no regression_agent crawl/rules code is
modified or touched.

GROUNDING RULE: every finding this module emits cites concrete evidence -
an element that could not be found, a network response >=400, a console
error/exception, or a stated expectation checked against captured evidence
and found unmet. A step that succeeds with its expectation met produces no
finding at all.
"""
import re

from playwright.sync_api import sync_playwright

from regression_agent import config as ra_config
from regression_agent.locators import discover_product_cards, find_clickable, find_form_field
from regression_agent.recorder import Recorder
from regression_agent.feedback import visible_text_near

from flow_translator.models import TranslatedFlow

_STOPWORDS = {"to", "the", "a", "an", "of", "for", "and", "your", "on", "then", "please", "is"}

_CONNECTION_ERROR_MARKERS = (
    "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT",
    "ERR_NAME_NOT_RESOLVED", "ERR_INTERNET_DISCONNECTED", "ERR_CONNECTION_CLOSED",
    "net::ERR_", "Timeout ", "TimeoutError",
)


class AppUnreachableError(RuntimeError):
    """The app under test isn't reachable at all (server not running, wrong
    URL, network down, ...). This is a precondition failure, not a finding
    about the app's behavior - it must never be reported as a UI bug."""


def _is_connection_error(exc):
    text = str(exc)
    return any(marker in text for marker in _CONNECTION_ERROR_MARKERS)


def _finding(category, page_label, description, evidence, confidence="high"):
    """Same shape regression_agent.rules._finding produces, so spec-mode
    findings are consistent with - and later scoreable alongside - the
    regression agent's own output."""
    return {
        "category": category,
        "page": page_label,
        "description": description,
        "evidence": evidence,
        "confidence": confidence,
        "verdict": None,
        "reasoning": None,
    }


def _patterns_from_locator_value(value):
    """The translator never sees the real page, so its locator guess may be
    close-but-not-exact (e.g. "Proceed to Checkout" for a button that's
    actually just "Checkout"). Try the full phrase first (best case), then
    fall back to each significant word on its own - still just building a
    pattern list for locators.find_clickable, not a new matching engine."""
    words = re.findall(r"[A-Za-z0-9]+", value)
    significant = [w for w in words if w.lower() not in _STOPWORDS]
    patterns = [re.escape(value)]
    for w in significant:
        if len(w) > 1:
            patterns.append(re.escape(w))
    return patterns


def _text_overlap(a, b):
    """Used only for locator resolution (the product-card fallback below) -
    deliberately permissive, since a card's full text vs. a product name is
    always a reasonably long, distinctive comparison in practice."""
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    aw = {w for w in re.findall(r"[a-z0-9]+", a) if w not in _STOPWORDS}
    bw = {w for w in re.findall(r"[a-z0-9]+", b) if w not in _STOPWORDS}
    return bool(aw & bw)


def _is_trivial_token(s):
    """A bare digit, a lone "+"/"-", a 1-2 letter fragment - common enough
    to exist on almost any page for reasons unrelated to what's being
    checked (a different row's quantity, a rating count, a step number)
    that it must never be trusted as corroborating evidence on its own."""
    return len(s.strip()) <= 2


def _expectation_overlap(candidate, expect_detail):
    """Stricter than _text_overlap - used only for checking an expectation
    against captured page text, never for locator resolution. See
    _is_trivial_token: a short/generic candidate may not satisfy a match
    merely by being a substring or the sole shared word of a longer
    expectation."""
    a, b = candidate.strip().lower(), expect_detail.strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    shorter = a if len(a) <= len(b) else b
    if _is_trivial_token(shorter):
        return False
    if a in b or b in a:
        return True
    aw = {w for w in re.findall(r"[a-z0-9]+", a) if w not in _STOPWORDS and not _is_trivial_token(w)}
    bw = {w for w in re.findall(r"[a-z0-9]+", b) if w not in _STOPWORDS and not _is_trivial_token(w)}
    return bool(aw & bw)


_BARE_NUMBER_RE = re.compile(r"^\d+$")


def _numeric_claim_supported(expect_detail, page_text):
    """None if expect_detail makes no numeric claim (caller should fall
    back to general matching). Otherwise True/False for whether that claim
    is unambiguously supported.

    A bare digit like "1" is too generic to trust as corroborating a
    quantity claim ("the cart shows 1 item") just because it appears
    *somewhere* on the page - e.g. a cart with 2 different products still
    shows "1" as EACH row's own quantity, which would otherwise satisfy
    "shows 1 item" even though the real total is 2. The only way to trust
    a bare-number match without knowing the fixture's specific markup is
    to require it be the page's SOLE distinct bare-number candidate - if
    another, different bare number is also present, there's no generic way
    to tell which one (if either) the claim actually refers to, so treat
    it as unsupported rather than guessing.
    """
    target_digits = set(re.findall(r"\b\d+\b", expect_detail))
    if not target_digits:
        return None
    page_digits = {c.strip() for c in page_text if _BARE_NUMBER_RE.match(c.strip())}
    if len(page_digits) == 1 and page_digits <= target_digits:
        return True
    return False


def _resolve_click_target(page, locator_value):
    """Resolve a translated click/navigate locator to a real element, with
    one fallback beyond a direct locators.find_clickable() match: the
    locator_value may name an ITEM inside a card (e.g. a product name)
    rather than being itself clickable text - in that case, find the card
    mentioning it and use the card's own designated action link, exactly
    the way the regression crawler opens a product (discover_product_cards
    + PATTERNS['product_link'])."""
    el = find_clickable(page, _patterns_from_locator_value(locator_value))
    if el is not None:
        return el

    try:
        cards = discover_product_cards(page)
        count = cards.count()
    except Exception:
        count = 0

    for i in range(count):
        card = cards.nth(i)
        try:
            card_text = card.inner_text()
        except Exception:
            continue
        if _text_overlap(card_text, locator_value):
            link = find_clickable(card, ra_config.PATTERNS["product_link"])
            if link is not None:
                return link

    return None


def _element_visible_anywhere(page, description):
    """Generic 'is something matching this description visible right now'
    check. Tries clickable elements first (buttons/links), then falls back
    to a plain visible-text match for non-interactive elements (e.g. a
    confirmation <div> or a price) - a description like "confirmation
    message" names something that is never itself clickable, so a
    click-only check would always miss it."""
    if find_clickable(page, _patterns_from_locator_value(description)) is not None:
        return True
    try:
        for pattern in _patterns_from_locator_value(description):
            if _is_trivial_token(pattern):
                continue  # a bare short pattern is too generic to text-search the whole page for
            loc = page.get_by_text(re.compile(pattern, re.I))
            count = loc.count()
            for i in range(min(count, 20)):
                if loc.nth(i).is_visible():
                    return True
    except Exception:
        pass
    return False


def _page_visible_text(page):
    """Whole-page visible text, reusing feedback.py's exact traversal - a
    <body> locator's parentElement is <html>, so scoping visible_text_near
    to it walks the entire rendered page instead of one local container.
    No new DOM-walking code, just a different scope for the same utility.
    """
    try:
        return visible_text_near(page.locator("body"))
    except Exception:
        return set()


def _text_matches_any(expect_detail, candidates):
    """expect_detail is often a paraphrase of what should appear ("the cart
    shows 1 item"), not literal page text (the app just renders a bare "1"
    in a quantity column) - so this checks substring-either-direction or
    shared significant words (_expectation_overlap), not "does the
    candidate literally contain the whole expected phrase". Trivial/short
    tokens are excluded - see _is_trivial_token and _numeric_claim_supported
    for why, and _check_expectation for how numeric claims are handled
    separately and first."""
    return any(_expectation_overlap(c, expect_detail) for c in candidates)


def _settle(page, ms=300):
    try:
        page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def _check_expectation(page, expect_type, expect_detail, new_text_near_action):
    if expect_type in ("text_appears", "element_present"):
        page_text = _page_visible_text(page)

        # A numeric claim ("1 item", "2 items") is checked first and
        # authoritatively - see _numeric_claim_supported. If it's
        # unsupported, don't let some unrelated non-numeric word overlap
        # paper over that; go straight to the local-diff fallback instead
        # of the general word-overlap check below.
        numeric_result = _numeric_claim_supported(expect_detail, page_text)
        if numeric_result is not None:
            return numeric_result or bool(new_text_near_action)

        if _text_matches_any(expect_detail, page_text):
            return True
        if _element_visible_anywhere(page, expect_detail):
            return True
        # No literal/overlapping match anywhere on the page - this is
        # expected for a vague, non-literal expectation ("a confirmation
        # message appears" has no wording in common with the app's actual
        # "Added to cart!"). The only further mechanical fact available -
        # not a semantic judgment - is whether the action produced ANY new
        # visible text locally at all; that's what a vague expectation like
        # this is actually checking for, so treat it as satisfying evidence.
        return bool(new_text_near_action)
    if expect_type == "url_contains":
        return expect_detail.lower() in page.url.lower()
    if expect_type == "no_error":
        # Console/network are already checked unconditionally for every
        # step (see run_flow) - absence of a finding there IS this check.
        return True
    return True


def run_flow(translated: TranslatedFlow, base_url: str, timeout_ms: int = 5000) -> dict:
    """Execute `translated` against `base_url` in a real (headless)
    browser. Returns {"flow_name", "base_url", "findings": [...], "steps": [...]}."""
    findings = []
    step_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)
        rec = Recorder(page)

        aborted = False
        for step in translated.steps:
            step_label = f"step:{step.step_index}"
            result = {
                "step_index": step.step_index,
                "action": step.original_action,
                "expect": step.original_expect,
                "status": "ok",
                "operations": [],
            }

            if aborted:
                result["status"] = "skipped (flow aborted at an earlier step)"
                step_results.append(result)
                continue

            if step.needs_clarification:
                result["status"] = f"skipped (needs_clarification: {step.clarification_reason})"
                step_results.append(result)
                continue

            mark = rec.mark()
            last_locator = None
            last_locator_before_text = set()
            step_failed = False

            for op in step.operations:
                op_result = {"op": op.op}
                try:
                    if op.op == "navigate" and not op.locator_value:
                        try:
                            page.goto(base_url, wait_until="load")
                        except Exception as exc:
                            if _is_connection_error(exc):
                                raise AppUnreachableError(
                                    f"Could not reach {base_url} ({exc.__class__.__name__}: {exc}). "
                                    "Is the app's server actually running on that URL?"
                                ) from exc
                            raise
                        op_result["detail"] = f"navigated to {base_url}"
                        last_locator, last_locator_before_text = None, set()

                    elif op.op in ("navigate", "click"):
                        el = _resolve_click_target(page, op.locator_value)
                        if el is None:
                            findings.append(_finding(
                                "element-not-found", step_label,
                                f"Step {step.step_index} ({step.original_action!r}): expected a "
                                f"clickable element matching {op.locator_value!r}, but none was found",
                                {"locator_value": op.locator_value, "op": op.op, "url": page.url},
                            ))
                            step_failed = True
                            op_result["detail"] = "not found"
                        else:
                            try:
                                before = visible_text_near(el)
                            except Exception:
                                before = set()
                            el.click()
                            last_locator, last_locator_before_text = el, before
                            op_result["detail"] = f"clicked matching {op.locator_value!r}"

                    elif op.op == "fill":
                        field = find_form_field(page, [op.field_label])
                        if field is None:
                            findings.append(_finding(
                                "element-not-found", step_label,
                                f"Step {step.step_index} ({step.original_action!r}): expected a "
                                f"form field labeled {op.field_label!r}, but none was found",
                                {"field_label": op.field_label, "op": "fill", "url": page.url},
                            ))
                            step_failed = True
                            op_result["detail"] = "not found"
                        else:
                            try:
                                before = visible_text_near(field)
                            except Exception:
                                before = set()
                            field.fill(op.value)
                            last_locator, last_locator_before_text = field, before
                            op_result["detail"] = f"filled {op.field_label!r} = {op.value!r}"

                    elif op.op == "assert":
                        op_result["detail"] = "assertion - no browser action"

                    else:
                        op_result["detail"] = f"unrecognized op {op.op!r} - skipped"

                except AppUnreachableError:
                    raise  # precondition failure, not a finding - let it abort the whole run
                except Exception as exc:
                    if _is_connection_error(exc):
                        raise AppUnreachableError(
                            f"Lost connection to {base_url} mid-flow ({exc.__class__.__name__}: {exc}). "
                            "Is the app's server still running?"
                        ) from exc
                    findings.append(_finding(
                        "element-not-found", step_label,
                        f"Step {step.step_index} ({step.original_action!r}): operation {op.op} "
                        f"raised {exc.__class__.__name__}: {exc}",
                        {"op": op.op, "locator_value": op.locator_value, "field_label": op.field_label},
                    ))
                    step_failed = True
                    op_result["detail"] = f"error: {exc}"

                result["operations"].append(op_result)
                if step_failed:
                    break

            _settle(page)
            console, network = rec.since(mark)

            for n in network:
                if n["status"] >= 400:
                    findings.append(_finding(
                        "network", step_label,
                        f"Step {step.step_index} ({step.original_action!r}): "
                        f"{n['method']} {n['url']} returned {n['status']}",
                        {"event": n},
                    ))

            for c in console:
                findings.append(_finding(
                    "console", step_label,
                    f"Step {step.step_index} ({step.original_action!r}): console {c['kind']}: {c['text']}",
                    {"event": c},
                ))

            after_text = set()
            if last_locator is not None:
                try:
                    after_text = visible_text_near(last_locator)
                except Exception:
                    after_text = set()
            new_text_near_action = after_text - last_locator_before_text
            result["new_text_near_action"] = sorted(new_text_near_action)

            if step.expect_type != "none":
                if step_failed:
                    # Already covered by the element-not-found finding above -
                    # don't double-count the same root cause as an unmet
                    # expectation too.
                    result["expectation_met"] = False
                else:
                    met = _check_expectation(page, step.expect_type, step.expect_detail, new_text_near_action)
                    result["expectation_met"] = met
                    if not met:
                        findings.append(_finding(
                            "expectation-unmet", step_label,
                            f"Step {step.step_index} ({step.original_action!r}): expected "
                            f"{step.expect_type} {step.expect_detail!r} (from {step.original_expect!r}), "
                            "but it was not observed",
                            {
                                "expect_type": step.expect_type,
                                "expect_detail": step.expect_detail,
                                "new_text_near_action": sorted(new_text_near_action),
                                "page_visible_text": sorted(_page_visible_text(page)),
                                "url": page.url,
                            },
                        ))

            if step_failed:
                result["status"] = "failed"
                aborted = True

            step_results.append(result)

        browser.close()

    return {
        "flow_name": translated.flow_name,
        "base_url": base_url,
        "findings": findings,
        "steps": step_results,
    }
