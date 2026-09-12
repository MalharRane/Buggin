"""Deterministic diff engine: baseline CapturedRun vs. candidate CapturedRun
-> a list of Findings.

Everything with an unambiguous signal (a new console error, a request that
used to succeed and now doesn't, a new visual anomaly, a control that
existed and is now unreachable, a flow that used to complete and now
doesn't) is flagged directly here with confidence="high" - no LLM call
needed. The one genuinely ambiguous case - the checkout flow's path/DOM
*shape* changed but it still reaches success on both sides - is queued as
confidence="ambiguous" for adjudicate.py to resolve with an LLM, since a
rule can't tell a legitimate new step (CHANGE-11) apart from a regression
that happens to route around itself and still limp to a 200.
"""
from urllib.parse import urlsplit


def _norm_url(url):
    parts = urlsplit(url)
    return parts.path


def _finding(category, page, description, evidence, confidence="high"):
    return {
        "category": category,
        "page": page,
        "description": description,
        "evidence": evidence,
        "confidence": confidence,
        "verdict": None,
        "reasoning": None,
    }


def _diff_console(baseline_events, candidate_events, page_label, findings):
    seen_baseline = {(e["kind"], e["text"]) for e in baseline_events}
    for e in candidate_events:
        if (e["kind"], e["text"]) not in seen_baseline:
            findings.append(_finding(
                "console", page_label,
                f"New console {e['kind']}: {e['text']}",
                {"event": e},
            ))


def _diff_network(baseline_events, candidate_events, page_label, findings, check_dropped_to_zero=False):
    baseline_status = {}
    for e in baseline_events:
        baseline_status.setdefault(_norm_url(e["url"]), []).append(e["status"])

    for e in candidate_events:
        if e["status"] < 400:
            continue
        path = _norm_url(e["url"])
        prior_statuses = baseline_status.get(path)
        if prior_statuses is None or any(s < 400 for s in prior_statuses):
            findings.append(_finding(
                "network", page_label,
                f"{e['method']} {path} now returns {e['status']} "
                f"(baseline: {prior_statuses if prior_statuses is not None else 'not called'})",
                {"event": e, "baseline_statuses": prior_statuses},
            ))

    # This action reliably triggered network activity in baseline, and now
    # triggers NONE at all - not even a failed request. A control that is
    # still visible/clickable but silently does nothing (e.g. an earlier
    # uncaught exception in the same render pass prevented its click
    # listener from ever being attached) produces no other signal, so this
    # is the only way to catch it.
    if check_dropped_to_zero and baseline_events and not candidate_events:
        findings.append(_finding(
            "dom-missing", page_label,
            "This action used to trigger network activity and now triggers "
            "none at all - the control may still be visible but no longer "
            "wired up (silently non-functional)",
            {"baseline_network": baseline_events},
        ))


def _diff_visual(baseline_visual, candidate_visual, page_label, findings):
    def key(v):
        return tuple(sorted((k, str(val)) for k, val in v.items() if k != "ratio"))

    seen_baseline = {key(v) for v in baseline_visual}
    for v in candidate_visual:
        if v.get("type") == "scan_error":
            continue
        if key(v) not in seen_baseline:
            findings.append(_finding(
                "visual", page_label,
                f"New visual anomaly ({v.get('type')}): {v}",
                {"anomaly": v},
            ))


def _diff_control(baseline_found, candidate_found, page_label, control_name, findings):
    if baseline_found and not candidate_found:
        findings.append(_finding(
            "dom-missing", page_label,
            f"Control '{control_name}' was reachable in baseline but is no longer reachable",
            {"control": control_name},
        ))


def _diff_product(key, base_p, cand_p, findings):
    label = f"product:{key}"
    if base_p is None:
        return  # new product in candidate only - not a regression
    if cand_p is None:
        findings.append(_finding(
            "dom-missing", label,
            f"Product '{key}' is no longer discoverable on the listing page",
            {},
        ))
        return

    _diff_control(base_p["found_link"], cand_p["found_link"], label, "product detail link", findings)
    _diff_control(base_p["add_to_cart_found"], cand_p["add_to_cart_found"], label, "add to cart button", findings)

    _diff_console(base_p["detail_console"], cand_p["detail_console"], label + ":detail", findings)
    _diff_network(base_p["detail_network"], cand_p["detail_network"], label + ":detail", findings)
    _diff_visual(base_p["detail_visual"], cand_p["detail_visual"], label + ":detail", findings)

    _diff_console(base_p["add_to_cart_console"], cand_p["add_to_cart_console"], label + ":add-to-cart", findings)
    _diff_network(
        base_p["add_to_cart_network"], cand_p["add_to_cart_network"], label + ":add-to-cart", findings,
        check_dropped_to_zero=(base_p["add_to_cart_found"] and cand_p["add_to_cart_found"]),
    )


def _diff_cart(base_cart, cand_cart, findings):
    label = "cart"
    _diff_control(base_cart.get("reachable"), cand_cart.get("reachable"), label, "cart nav link", findings)
    _diff_console(base_cart["console"], cand_cart["console"], label, findings)
    _diff_network(base_cart["network"], cand_cart["network"], label, findings)
    _diff_visual(base_cart["visual"], cand_cart["visual"], label, findings)

    for control_name in ("increment", "decrement", "checkout_cta"):
        _diff_control(
            base_cart["controls"][control_name], cand_cart["controls"][control_name],
            label, f"{control_name} control", findings,
        )

    _diff_console(base_cart["increment_console"], cand_cart["increment_console"], label + ":increment", findings)
    _diff_console(base_cart["decrement_console"], cand_cart["decrement_console"], label + ":decrement", findings)


def _flatten_path_evidence(path):
    console, network, visual = [], [], []
    for step in path:
        console.extend(step.get("console", []))
        network.extend(step.get("network", []))
        visual.extend(step.get("visual", []))
    return console, network, visual


def _diff_checkout(base_co, cand_co, findings):
    label = "checkout"

    if base_co["reached"] and not cand_co["reached"]:
        findings.append(_finding(
            "dom-missing", label,
            "Checkout used to be reachable from the cart and no longer is",
            {},
        ))
        return

    if not base_co["reached"]:
        return  # nothing to compare

    if base_co["success"] and not cand_co["success"]:
        findings.append(_finding(
            "dom-missing", label,
            "Checkout used to complete successfully and no longer does "
            "(flow dead-ends before reaching a success confirmation)",
            {"candidate_path": [s["label"] for s in cand_co["path"]]},
        ))

    b_console, b_network, b_visual = _flatten_path_evidence(base_co["path"])
    c_console, c_network, c_visual = _flatten_path_evidence(cand_co["path"])
    _diff_console(b_console, c_console, label, findings)
    _diff_network(b_network, c_network, label, findings)
    _diff_visual(b_visual, c_visual, label, findings)

    if base_co["success"] and cand_co["success"]:
        base_shape = [s["label"].split("-")[0] for s in base_co["path"]]
        cand_shape = [s["label"].split("-")[0] for s in cand_co["path"]]
        if base_shape != cand_shape:
            findings.append(_finding(
                "structural-divergence", label,
                "Checkout still completes successfully, but the path/DOM "
                "structure to get there differs from baseline "
                f"(baseline: {len(base_co['path'])} step(s), candidate: {len(cand_co['path'])} step(s))",
                {
                    "baseline_path": [s["label"] for s in base_co["path"]],
                    "candidate_path": [s["label"] for s in cand_co["path"]],
                },
                confidence="ambiguous",
            ))


def diff_profiles(baseline, candidate):
    """Return a list of Finding dicts. Findings with confidence == "ambiguous"
    still need adjudicate.adjudicate() before they're final."""
    findings = []

    _diff_console(baseline["listing"]["console"], candidate["listing"]["console"], "listing", findings)
    _diff_network(baseline["listing"]["network"], candidate["listing"]["network"], "listing", findings)
    _diff_visual(baseline["listing"]["visual"], candidate["listing"]["visual"], "listing", findings)

    all_keys = set(baseline["products"]) | set(candidate["products"])
    for key in sorted(all_keys, key=lambda k: (len(k), k)):
        _diff_product(key, baseline["products"].get(key), candidate["products"].get(key), findings)

    _diff_cart(baseline["cart"], candidate["cart"], findings)
    _diff_checkout(baseline["checkout"], candidate["checkout"], findings)

    return findings
