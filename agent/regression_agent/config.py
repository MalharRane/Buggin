"""Static configuration for the regression-testing agent.

The agent is intentionally generic: it has no knowledge of the seeded bug
catalog (fixtures/BUG_CATALOG.md) or the harmless-change catalog
(fixtures/CHANGE_CATALOG.md). It navigates via semantic locators (role/text
patterns, form labels) so it keeps working across cosmetic renames, and it
flags only structural/behavioral anomalies relative to a recorded baseline
run. Scoring the findings against those catalogs is a separate, later step.
"""

DEFAULT_VERSIONS = {
    "v0-baseline": "http://localhost:3000",
    "v1-buggy": "http://localhost:3001",
    "v1-clean": "http://localhost:3002",
}

# Dummy data used to fill in checkout-style forms. Fields are discovered by
# label text (see locators.find_form_field), not by hardcoded element id, so
# this keeps working across id renames.
CHECKOUT_TEST_DATA = {
    "name": ["full name", "name"],
    "email": ["email"],
    "address": ["address"],
}
CHECKOUT_TEST_VALUES = {
    "name": "Regression Tester",
    "email": "regression.tester@example.com",
    "address": "123 Test Street, Testville",
}

# Case-insensitive regex patterns used to semantically locate controls.
# Intentionally a little generous (covering common e-commerce synonyms)
# since the agent must keep working across legitimate copy changes (e.g.
# "Add to Cart" -> "Add to Bag", "Checkout" -> "Proceed to Payment").
PATTERNS = {
    "product_link": [r"view details", r"\bdetails\b", r"view product", r"^view$"],
    "add_to_cart": [r"add to (cart|bag|basket)"],
    # No trailing \b: a cart-count badge is often concatenated into the link's
    # text (e.g. "Cart" + a "3" badge renders as visible text "Cart3").
    "cart_nav": [r"^cart"],
    "qty_increment": [r"^\+$", r"increase", r"increment"],
    "qty_decrement": [r"^-$", r"decrease", r"decrement"],
    "checkout_cta": [r"checkout", r"proceed to payment", r"^proceed$"],
    "submit_order": [r"place order", r"review order", r"^continue$", r"submit order"],
    "confirm_order": [r"confirm order", r"^confirm$", r"place order"],
    "success_text": [r"thank you", r"order.*(placed|confirmed|received)", r"\bsuccess\b"],
}

MAX_CHECKOUT_HOPS = 4  # bound on how many extra CTA screens the agent will follow
NAV_TIMEOUT_MS = 5000
ACTION_SETTLE_MS = 300  # brief wait after an action for console/network events to land
