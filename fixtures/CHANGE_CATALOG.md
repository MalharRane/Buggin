# CHANGE_CATALOG.md — Harmless changes in `versions/v1-clean`

This is the list of every intentional change in **v1-clean** relative to
**v0-baseline**. None of these are bugs — everything still works correctly.
This is the false-positive control: a correct testing agent run against
v1-clean should report **nothing**. Anything it flags here is a false
positive.

11 harmless changes total.

| Change ID | Page(s) | Description | Why it's harmless |
|---|---|---|---|
| CHANGE-01 | All pages | Brand color scheme restyled from indigo (`#4f46e5`) to teal (`#0d9488`) via the `--brand` / `--brand-dark` CSS variables. Affects the header logo, links, and primary buttons. | Purely cosmetic; contrast and layout are unaffected, all elements remain visible and clickable. |
| CHANGE-02 | Product Detail | "Add to Cart" button relabeled to "Add to Bag"; the confirmation message text changed from "Added to cart!" to "Added to bag!". | Copy-only rewording; the button's id, styling, and behavior (adds the item to the cart) are unchanged. |
| CHANGE-03 | Cart | "Checkout" button relabeled to "Proceed to Payment". | Copy-only rewording; the button's id and behavior (navigates to `/checkout.html`) are unchanged. |
| CHANGE-04 | Product Listing, Product Detail | New, genuinely-working "wishlist" heart toggle button (♡ / ♥) on every product card and on the detail page. State persists in `localStorage` under `buggin_wishlist`. | A real, working new feature — clicking it correctly toggles and persists state; it is not wired into cart or checkout, so it can't affect anything else. |
| CHANGE-05 | Product Listing | Rotating promo banner at the top of the page, cycling through 3 messages every 4 seconds (dynamic content — starts at a random message, so it also differs across page loads). | Cosmetic and expected to change over time / between loads; not a bug signal. |
| CHANGE-06 | All pages | Live clock in the footer (`#footer-clock`), updated every second via `setInterval`, showing the current time. | Dynamic content that is *expected* to differ on every load and every second; not a regression. |
| CHANGE-07 | Product Detail (product id 3) | Updated marketing copy for "Canvas Backpack": description extended to mention a "redesigned front pocket". | Text-only content update, no functional change. |
| CHANGE-08 | Cart | Quantity +/- buttons restyled from square (`border-radius: 6px`) to circular (`border-radius: 50%`). | Purely cosmetic; the buttons remain the same size, in the same place, and fully functional. |
| CHANGE-09 | All pages | Footer tagline text updated from "a fixture app for regression testing" to "your favorite corner store for testing fixtures". | Copy-only rewording. |
| CHANGE-10 | Checkout | New optional "Apartment / Suite (optional)" field added to the checkout form, between Address and the Place Order button. | Genuinely optional (no `required` attribute, not validated); the form still submits successfully whether or not it's filled in. |
| **CHANGE-11** ⚠️ **legitimate structural/flow change** | Checkout | Adds a working "Review your order" confirmation step to the checkout flow. Submitting the form (now labeled "Review Order") no longer calls the API directly — it shows a new intermediate screen (`#order-review`) with an order summary (items, total, name/email/address) and a "Confirm Order" button (`#confirm-order-btn`, plus a "Back" button `#back-to-form-btn`). Only clicking "Confirm Order" calls `POST /api/checkout`; on success the same `#order-success` confirmation is shown as before. | This **changes the action path vs. v0-baseline**: v0-baseline goes form-submit → `POST /api/checkout` → success in one step; v1-clean now goes form-submit → review screen → confirm-click → `POST /api/checkout` → success, an extra step with new DOM (`#order-review`, `#order-review-summary`, `#confirm-order-btn`, `#back-to-form-btn`) that does not exist in v0-baseline. Despite the changed path and structure, the flow **completes correctly end-to-end** (verified: fills form → review shows correct summary → confirm → 200 response → success confirmation shown) and nothing is broken. |

**Why CHANGE-11 exists:** this entry is deliberately different from CHANGE-01
through CHANGE-10 — it's not just cosmetic or additive, it's a real change to
the checkout *path and DOM structure*. It exists specifically to test
**replay-divergence handling** in a future replay-based auditor: an auditor
that replays a recorded v0-baseline checkout trace against v1-clean will see
the recorded action sequence diverge (the expected post-form-submit state —
success — never appears; an unfamiliar review screen appears instead). A
naive auditor that treats *any* path/DOM divergence from the baseline
recording as a regression will incorrectly flag this. A correct auditor must
recognize that the new step is reachable, coherent, and still ends in a
successful order — i.e., **legitimate divergence, not a regression** — and
must NOT flag it.

## Verifying "zero real bugs"

Every flow that exists in v0-baseline still works end-to-end in v1-clean:
product listing → product detail → add to cart → cart (increment/decrement
quantity) → checkout → review order → confirm order → success confirmation
(the "review order" step is new, per CHANGE-11 above). All network calls
(`GET /api/products`, `GET /api/products/:id`, `POST /api/checkout`,
`POST /api/cart/track`) return the same successful status codes as in
v0-baseline. No console errors are introduced.
