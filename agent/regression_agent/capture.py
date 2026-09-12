"""The crawler: walks the app's flows once and records evidence.

Produces a plain nested-dict "CapturedRun" (JSON-serializable) rather than a
bespoke class hierarchy, since the only consumers are a diff function
(rules.py) and a JSON/Markdown report writer (report.py).

The crawl is generic on purpose - see locators.py and visual_scan.py for
why - so the same code runs unmodified against v0-baseline, v1-buggy, and
v1-clean, and would run against a real app with the same page shapes.
"""
from . import config
from .locators import find_clickable, find_form_field, discover_product_cards, card_key
from .recorder import Recorder
from .visual_scan import run_visual_scan


def _settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(config.ACTION_SETTLE_MS)


def _step(rec, page, action):
    """Run `action(page)`, return (console_events, network_events) captured
    strictly during it."""
    mark = rec.mark()
    action(page)
    _settle(page)
    return rec.since(mark)


def _text_present(page, patterns):
    """True if any pattern matches VISIBLE text - a hidden success div
    (display:none, class="hidden") that hasn't been revealed yet must not
    count, or the crawler would think checkout succeeded before submitting."""
    import re as _re
    for p in patterns:
        try:
            loc = page.get_by_text(_re.compile(p, _re.I))
            if loc.count() == 0:
                continue
            for idx in range(loc.count()):
                if loc.nth(idx).is_visible():
                    return True
        except Exception:
            continue
    return False


def _capture_product(page, rec, base_url, index):
    """Visit one product card from the listing page (index-th card), walk
    into its detail page and attempt Add to Cart, then return to the
    listing. Returns (key, profile_dict)."""
    cards = discover_product_cards(page)
    count = cards.count()
    if index >= count:
        return None, None

    card = cards.nth(index)
    key = card_key(card, index)
    profile = {
        "found_link": False,
        "detail_reached": False,
        "detail_console": [],
        "detail_network": [],
        "detail_visual": [],
        "add_to_cart_found": False,
        "add_to_cart_console": [],
        "add_to_cart_network": [],
    }

    link = find_clickable(card, config.PATTERNS["product_link"])
    if link is None:
        return key, profile
    profile["found_link"] = True

    def _click_link(_page):
        link.click()

    console, network = _step(rec, page, _click_link)
    profile["detail_console"] = console
    profile["detail_network"] = network
    profile["detail_reached"] = True
    profile["detail_visual"] = run_visual_scan(page)

    add_btn = find_clickable(page, config.PATTERNS["add_to_cart"])
    if add_btn is not None:
        profile["add_to_cart_found"] = True

        def _click_add(_page):
            add_btn.click()

        console, network = _step(rec, page, _click_add)
        profile["add_to_cart_console"] = console
        profile["add_to_cart_network"] = network

    # Back to the listing for the next card.
    def _go_back(_page):
        _page.goto(base_url, wait_until="load")

    _step(rec, page, _go_back)

    return key, profile


def _capture_cart(page, rec):
    result = {
        "console": [],
        "network": [],
        "visual": [],
        "controls": {"increment": False, "decrement": False, "checkout_cta": False},
        "increment_console": [],
        "increment_network": [],
        "decrement_console": [],
        "decrement_network": [],
    }

    nav_cart = find_clickable(page, config.PATTERNS["cart_nav"])
    if nav_cart is None:
        result["reachable"] = False
        return result
    result["reachable"] = True

    def _click_cart_nav(_page):
        nav_cart.click()

    console, network = _step(rec, page, _click_cart_nav)
    result["console"] = console
    result["network"] = network
    result["visual"] = run_visual_scan(page)

    inc = find_clickable(page, config.PATTERNS["qty_increment"])
    dec = find_clickable(page, config.PATTERNS["qty_decrement"])
    checkout_cta = find_clickable(page, config.PATTERNS["checkout_cta"])
    result["controls"]["increment"] = inc is not None
    result["controls"]["decrement"] = dec is not None
    result["controls"]["checkout_cta"] = checkout_cta is not None

    if inc is not None:
        def _click_inc(_page):
            inc.click()

        console, network = _step(rec, page, _click_inc)
        result["increment_console"] = console
        result["increment_network"] = network

    # Re-locate decrement after a possible re-render from the increment click.
    dec = find_clickable(page, config.PATTERNS["qty_decrement"])
    if dec is not None:
        def _click_dec(_page):
            dec.click()

        console, network = _step(rec, page, _click_dec)
        result["decrement_console"] = console
        result["decrement_network"] = network

    return result


def _capture_checkout(page, rec):
    result = {"reached": False, "path": [], "success": False}

    checkout_cta = find_clickable(page, config.PATTERNS["checkout_cta"])
    if checkout_cta is None:
        return result

    def _click_checkout(_page):
        checkout_cta.click()

    console, network = _step(rec, page, _click_checkout)
    result["reached"] = True
    result["path"].append({
        "label": "checkout-entry",
        "console": console,
        "network": network,
        "visual": run_visual_scan(page),
    })

    for hop in range(config.MAX_CHECKOUT_HOPS):
        if _text_present(page, config.PATTERNS["success_text"]):
            result["success"] = True
            break

        # Best-effort form fill; a no-op on screens with no matching fields.
        for field_key, keywords in config.CHECKOUT_TEST_DATA.items():
            field = find_form_field(page, keywords)
            if field is not None:
                try:
                    field.fill(config.CHECKOUT_TEST_VALUES[field_key])
                except Exception:
                    pass

        cta = find_clickable(page, config.PATTERNS["submit_order"])
        if cta is None:
            cta = find_clickable(page, config.PATTERNS["confirm_order"])
        if cta is None:
            result["path"].append({"label": f"hop-{hop}-dead-end", "console": [], "network": [], "visual": []})
            break

        def _click_cta(_page):
            cta.click()

        console, network = _step(rec, page, _click_cta)
        result["path"].append({
            "label": f"hop-{hop}",
            "console": console,
            "network": network,
            "visual": run_visual_scan(page),
        })
    else:
        # Loop exhausted without an explicit break for success/dead-end.
        result["success"] = _text_present(page, config.PATTERNS["success_text"])

    if not result["success"]:
        result["success"] = _text_present(page, config.PATTERNS["success_text"])

    return result


def run_capture(page, base_url, version_name, max_products=6):
    """Run the full crawl against `base_url` and return a JSON-serializable dict."""
    rec = Recorder(page)

    def _go_home(_page):
        _page.goto(base_url, wait_until="load")

    listing_console, listing_network = _step(rec, page, _go_home)
    listing_visual = run_visual_scan(page)

    products = {}
    cards = discover_product_cards(page)
    n = min(cards.count(), max_products)
    for i in range(n):
        key, profile = _capture_product(page, rec, base_url, i)
        if key is not None:
            products[key] = profile

    cart = _capture_cart(page, rec)
    checkout = _capture_checkout(page, rec) if cart.get("controls", {}).get("checkout_cta") else {
        "reached": False, "path": [], "success": False,
    }

    return {
        "version": version_name,
        "base_url": base_url,
        "listing": {
            "console": listing_console,
            "network": listing_network,
            "visual": listing_visual,
            "product_count": n,
        },
        "products": products,
        "cart": cart,
        "checkout": checkout,
    }
