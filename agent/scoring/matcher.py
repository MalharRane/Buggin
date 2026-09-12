"""Map an agent report's findings onto catalog bug records.

Matching is deliberately mechanical and conservative - four gates, all
required:
  1. category must be one of the bug's accepted_categories (a network
     finding never satisfies a console-category bug, etc.)
  2. the finding's page/product must fall within the bug's declared
     page_types + product_id (or the bug applies to "any product")
  3. for network bugs, the finding's URL must name the same resource the
     bug's selector does (image vs cart/track vs products-fetch vs
     checkout - see catalog_parser._extract_network_resource_hint)
  4. the finding's *specific* evidence must support the bug's *specific*
     claim, not just share its category and page (see _claim_matches) -
     this is what stops, e.g., a "the decrement button is gone" finding
     from being credited to "the checkout button is gone" just because
     both are dom-missing findings on the cart page, or a "control X is
     unreachable" finding from being credited to "confirmation text never
     appears" just because both are dom-missing on a product-detail page.
No fuzzy text matching, no scoring by description similarity - if a finding
doesn't clear every gate, it does not count as a hit, full stop. Findings
that don't match anything are surfaced individually (never silently
dropped) with a "near-miss" hint when something almost lines up, so a human
can make the judgment call the harness deliberately does not make for them.
"""
import json

from .catalog_parser import _extract_network_resource_hint


def _finding_network_url(finding):
    event = finding.get("evidence", {}).get("event")
    if isinstance(event, dict):
        return event.get("url")
    return None


def finding_page_info(page_label):
    """('listing' | 'product-detail' | 'cart' | 'checkout', product_id|None, subflow|None)"""
    if page_label == "listing":
        return "listing", None, None
    if page_label == "cart" or page_label.startswith("cart:"):
        subflow = page_label.split(":", 1)[1] if ":" in page_label else None
        return "cart", None, subflow
    if page_label == "checkout":
        return "checkout", None, None
    if page_label.startswith("product:"):
        parts = page_label.split(":")
        pid = int(parts[1]) if parts[1].isdigit() else None
        subflow = parts[2] if len(parts) > 2 else None
        # A bare "product:{id}" (no suffix) covers a control check that
        # happens while still on the listing page (the card's detail link)
        # - see capture.py's _capture_product. Accept either page type for
        # that shape; a ":detail"/":add-to-cart" suffix is unambiguous.
        page_type = "product-detail" if subflow else "listing-or-detail"
        return page_type, pid, subflow
    return "unknown", None, None


def _page_type_compatible(finding_page_type, bug_page_types):
    if finding_page_type == "listing-or-detail":
        return "listing" in bug_page_types or "product-detail" in bug_page_types
    return finding_page_type in bug_page_types


def _mentions_product(finding, product_id):
    """For page-level findings (e.g. a 'listing' finding about one product's
    image), check whether the finding's own text/evidence names that
    product - used only when the bug is product-specific but the finding's
    page label itself carries no product id (e.g. BUG-05 on the listing)."""
    blob = json.dumps(finding).lower()
    needles = [f'product{product_id}', f'data-id="{product_id}"', f"id={product_id}"]
    return any(n in blob for n in needles)


def _dom_missing_evidence_shape(finding):
    """What KIND of dom-missing observation this finding actually is - the
    three shapes rules.py currently produces. A bug whose claim_type is
    "feedback_missing" (BUG-14) will never match any of these, because no
    current finding shape represents "checked for text X and it was
    absent" - that's the point: it should MISS until the agent gains that
    check, not get credited by an unrelated control-missing finding just
    because both happen to be category=dom-missing on the same page."""
    evidence = finding.get("evidence", {})
    if "control" in evidence:
        return "control_missing", evidence["control"]
    if "baseline_network" in evidence:
        return "silent_action", None
    return "flow_broken", None


def _claim_matches(finding, bug):
    """The specificity gate: category+page/product is necessary but not
    sufficient. Two bugs can share both (BUG-13's checkout button and
    BUG-16's decrement button are both dom-missing on the cart page; BUG-05's
    image and a hypothetical second image bug could both be "visual" on the
    same product) - this checks that the finding's *specific* evidence
    actually supports *this* bug's specific claim, not just its category
    and location.
    """
    category = finding["category"]

    if category == "visual":
        anomaly = finding.get("evidence", {}).get("anomaly")
        finding_type = anomaly.get("type") if isinstance(anomaly, dict) else None
        return bool(bug.get("visual_claim_type")) and finding_type == bug["visual_claim_type"]

    if category == "console":
        keyword = bug.get("console_keyword")
        return bool(keyword) and keyword in json.dumps(finding)

    if category == "dom-missing":
        claim_type = bug.get("dom_missing_claim_type")
        if claim_type is None:
            return False
        shape, control_value = _dom_missing_evidence_shape(finding)
        if claim_type != shape:
            return False
        if claim_type == "control_missing":
            control_lower = (control_value or "").lower()
            for word in bug["dom_missing_keywords"]:
                w = word.lower()
                singular = w[:-1] if w.endswith("s") and len(w) > 3 else w
                if singular in control_lower or w in control_lower:
                    return True
            return False
        return True  # silent_action: category+page/product+shape match is specific enough

    return True  # network is already gated by resource-hint in finding_matches_bug


def finding_matches_bug(finding, bug):
    if finding["category"] not in bug["accepted_categories"]:
        return False

    f_page_type, f_product_id, _ = finding_page_info(finding["page"])
    if f_page_type == "unknown":
        return False
    if not _page_type_compatible(f_page_type, bug["page_types"]):
        return False

    if bug["product_id"] is not None:
        if f_product_id is not None:
            if f_product_id != bug["product_id"]:
                return False
        # Finding has no product id of its own (e.g. a page-level "listing"
        # finding) but the bug is product-specific - only count it if the
        # finding's own content names that product.
        elif not _mentions_product(finding, bug["product_id"]):
            return False

    # Two different network bugs can land on the same page/product (e.g.
    # BUG-05's broken image and BUG-07's cart/track beacon both surface on
    # product 5's pages) - page/product alone can't tell them apart, so
    # also require the finding's actual URL to name the same resource the
    # bug's selector does, whenever both sides resolve to a hint.
    if bug["category"] == "network" and bug.get("network_resource_hint"):
        finding_url = _finding_network_url(finding)
        if finding_url:
            finding_hint = _extract_network_resource_hint(finding_url)
            if finding_hint and finding_hint != bug["network_resource_hint"]:
                return False

    if not _claim_matches(finding, bug):
        return False

    return True


def _near_miss(finding, bugs):
    """Best-effort: find bug(s) whose page/product line up with this
    finding even though the category didn't, so a human reviewer sees WHY
    it's plausible rather than just "unmatched"."""
    f_page_type, f_product_id, _ = finding_page_info(finding["page"])
    candidates = []
    for bug in bugs:
        if not _page_type_compatible(f_page_type, bug["page_types"]):
            continue
        if bug["product_id"] is not None:
            if f_product_id is not None and f_product_id != bug["product_id"]:
                continue
            if f_product_id is None and not _mentions_product(finding, bug["product_id"]):
                continue
        candidates.append(bug["id"])
    return candidates


def match_findings_to_bugs(findings, bugs):
    """Returns (bug_hits, unmatched) where:
      bug_hits: {bug_id: [finding, ...]} - only bugs with >=1 hit are keys
      unmatched: [{"finding": f, "near_miss_bug_ids": [...]}]
    A single finding may match more than one bug in principle (none do in
    this catalog, but the loop doesn't assume otherwise) and is recorded
    against every bug it satisfies.
    """
    bug_hits = {}
    unmatched = []

    for finding in findings:
        matched_any = False
        for bug in bugs:
            if finding_matches_bug(finding, bug):
                bug_hits.setdefault(bug["id"], []).append(finding)
                matched_any = True
        if not matched_any:
            unmatched.append({
                "finding": finding,
                "near_miss_bug_ids": _near_miss(finding, bugs),
            })

    return bug_hits, unmatched
