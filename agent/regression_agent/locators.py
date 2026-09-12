"""Generic, text/role-based element discovery.

These helpers deliberately avoid hardcoded ids/classes wherever possible, so
the same crawl code keeps working when a target app renames an id or
restyles a control - only a genuinely missing/unreachable control should
fail to resolve. This is a heuristic, not a full semantic web agent: the
patterns are tuned to common e-commerce vocabulary (see config.PATTERNS),
and the product-card / form-field fallbacks are best-effort.
"""
import re

CLICKABLE = "button, a, input[type=submit], input[type=button]"


def _compile(patterns):
    return [re.compile(p, re.I) for p in patterns]


def find_clickable(scope, patterns):
    """Return the first visible clickable element matching any pattern, else None."""
    for rx in _compile(patterns):
        try:
            loc = scope.locator(CLICKABLE).filter(has_text=rx)
            if loc.count() == 0:
                continue
            first = loc.first
            if first.is_visible():
                return first
        except Exception:
            continue
    return None


def find_form_field(scope, keywords):
    """Find an input/textarea by associated <label> text (preferred), falling
    back to id/name/placeholder substring matching."""
    for kw in keywords:
        try:
            field = scope.get_by_label(re.compile(kw, re.I)).first
            if field.count() > 0:
                return field
        except Exception:
            continue
    for kw in keywords:
        safe = kw.replace("'", "").replace('"', "")
        try:
            field = scope.locator(
                f"input[id*='{safe}' i], input[name*='{safe}' i], "
                f"input[placeholder*='{safe}' i], textarea[id*='{safe}' i]"
            ).first
            if field.count() > 0:
                return field
        except Exception:
            continue
    return None


def discover_product_cards(page):
    """Return a Playwright Locator matching each product card on a listing page."""
    cards = page.locator(".product-card")
    try:
        if cards.count() > 0:
            return cards
    except Exception:
        pass
    # Fallback heuristic: repeated blocks that contain both an image and
    # dollar-amount text, when the app doesn't use a `.product-card` class.
    return page.locator("article, li, div").filter(has=page.locator("img")).filter(
        has_text=re.compile(r"\$\s?\d")
    )


def card_key(card, index):
    """Stable-ish identifier for a card across versions: prefer data-id."""
    try:
        data_id = card.get_attribute("data-id")
        if data_id:
            return data_id
    except Exception:
        pass
    return str(index)
