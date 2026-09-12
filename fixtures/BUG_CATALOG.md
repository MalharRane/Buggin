# BUG_CATALOG.md — Answer key for `versions/v1-buggy`

This is the ground truth for every bug deliberately seeded into **v1-buggy**
relative to **v0-baseline**. A testing agent's recall should be measured
against this table: every row it fails to surface is a false negative, and
anything it reports on `v1-buggy` that is *not* in this table (or in
`CHANGE_CATALOG.md`) is a false positive.

16 bugs total, 4 per category (a/b/c/d).

Legend for **Evidence type**:
- `visual-only` — a human/vision check would catch it; no console error and no failed network request.
- `network` — a request returns a 4xx/5xx status.
- `console` — an uncaught exception or an error-level `console` log; no failed HTTP request.
- `dom-missing` — an expected element/flow is absent; typically no console/network error either.

| Bug ID | Category | Page / Flow | Description | Element / Selector | Evidence type |
|---|---|---|---|---|---|
| BUG-01 | a — visual | Product Detail (`product.html`) | The "Add to Cart" button's text color is set to the same color as its own background, so the label is invisible. The button is still clickable and still works. | `#add-to-cart-btn` (CSS: `color` == `background`) | visual-only |
| BUG-02 | a — visual | Product Listing (`index.html`) | Product id 3's card image is forced to a mismatched height with `object-fit: fill`, squishing/stretching it out of its native aspect ratio. Other cards are unaffected. | `.product-card[data-id="3"] img` | visual-only |
| BUG-03 | a — visual | Product Listing (`index.html`) | `.product-name` lost its `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` rules, so product id 2's (deliberately long) name overflows/wraps out of its card instead of truncating cleanly. | `.product-name` (global rule); visible effect on `.product-card[data-id="2"]` | visual-only |
| BUG-04 | a — visual | Checkout (`checkout.html`) | `.checkout-form` fields are positioned absolutely with no offsets, so every form field (name, email, address) renders stacked directly on top of the others instead of flowing vertically. | `.checkout-form`, `.form-field` | visual-only |
| BUG-05 | b — network | Product Listing + Product Detail (product id 5) | Product id 5's `image` path in the catalog points to a file that does not exist (`/images/product5-missing.svg`), so the image request 404s wherever that product is rendered. | `.product-card[data-id="5"] img`, and `product.html?id=5` `<img>` | network (404) |
| BUG-06 | b — network | Checkout (`checkout.html`) | `POST /api/checkout` always responds `500 Internal Server Error`, regardless of form input. Placing an order always fails; the client shows a generic "Something went wrong" message and the success confirmation never appears. | `#place-order-btn` → `POST /api/checkout` | network (500) |
| BUG-07 | b — network | Product Detail (`product.html`), any product | Clicking "Add to Cart" fires a fire-and-forget analytics beacon (`POST /api/cart/track`) which always responds `400 Bad Request`. The item is still added to the cart correctly and the UI shows no error — **no visual change at all**. | `#add-to-cart-btn` → `POST /api/cart/track` | network (400), no visual change (telemetry-only) |
| BUG-08 | b — network | Product Detail (`product.html?id=6`) | `GET /api/products/6` always responds `404 Not Found` even though product id 6 exists in the catalog and displays fine on the listing page. Navigating to its detail page shows a "couldn't load this product" fallback. | `product.html?id=6` → `GET /api/products/6` | network (404) |
| BUG-09 | c — console | Product Detail (`product.html?id=2`) | Clicking "Add to Cart" for product id 2 reads `product.sku.toUpperCase()`, but no product has a `sku` field. This throws an uncaught `TypeError` that aborts the click handler *before* `Cart.add()` runs — the item is silently never added, and nothing on screen indicates a problem. | `#add-to-cart-btn` on `product.html?id=2` | console (uncaught TypeError), no visual change |
| BUG-10 | c — console | Cart (`cart.html`) | Clicking the quantity "+" button correctly updates and re-renders the quantity first, then calls `logQuantityChange(...)`, a function that does not exist anywhere in the app. This throws an uncaught `ReferenceError` on every increment click, after the (correct) UI update has already happened. | `.qty-increment` | console (uncaught ReferenceError), no visual change |
| BUG-11 | c — console | Checkout (`checkout.html`) | Submitting the checkout form schedules a call to `trackCheckoutStart(...)` via `setTimeout`, a function that does not exist. This throws an uncaught `ReferenceError` shortly after submit, independent of and in addition to whatever the checkout network call does (see BUG-06). | `#checkout-form` (submit handler) | console (uncaught ReferenceError), no visual change |
| BUG-12 | c — console | Product Detail (`product.html?id=4`) | The detail page first renders a `★ New` placeholder rating, then tries to fill in the real value via `product.rating.value`. Product id 4 has no `rating` field in the catalog, so this throws an uncaught `TypeError` — logged to console — but the page has already rendered successfully with the placeholder, so it still looks correct (shows "★ New" instead of a numeric rating). **Broader impact (found by the Phase 1 agent, not originally documented here):** in `product.js`, the `addEventListener('click', ...)` call for "Add to Cart" comes *after* this line. Because the exception is uncaught, it aborts `renderProductDetail()` before that listener is ever attached — so for product id 4 specifically, "Add to Cart" is completely inert (visible and clickable, but clicking it does nothing at all: no console error, no network call, item never added). This is a second, more severe symptom of the same root cause, not a separate bug. | `#product-rating` and `#add-to-cart-btn` on `product.html?id=4` | console (uncaught TypeError) **and** a silent action-does-nothing effect on Add to Cart (no further evidence at all — the click handler was never attached) |
| BUG-13 | d — DOM-missing | Cart (`cart.html`) | The "Checkout" button has been removed entirely from the cart page markup. There is no in-app way to navigate from the cart to `/checkout.html` (the page itself is still reachable by direct URL). | `#checkout-btn` (absent) | dom-missing (dead-end flow) |
| BUG-14 | d — DOM-missing | Product Detail (`product.html`), any product | The click handler looks up `#add-to-cart-feedback`, but that element was renamed to `#atc-feedback` in the rendered markup. The lookup is null-guarded, so nothing throws — the "Added to cart!" confirmation message simply never appears, for any product. (Contrast with BUG-09, which additionally prevents the item from being added at all, but only for product id 2.) | `#add-to-cart-feedback` (referenced by JS; not present — actual id is `#atc-feedback`) | dom-missing, no console/network error |
| BUG-15 | d — DOM-missing | Product Listing (`index.html`) | The "View Details" link is omitted specifically for product id 1's card. Its image, name, and price still render normally, but there is no way to click through to its detail page from the listing. | `.product-card[data-id="1"] a.view-details` (absent) | dom-missing (dead-end flow) |
| BUG-16 | d — DOM-missing | Cart (`cart.html`) | The quantity decrement ("-") button is missing from every cart row. Shoppers can increase quantity but have no way to decrease it or remove a single unit (removing an item entirely is not possible via the UI at all). | `.qty-decrement` (absent on all rows) | dom-missing |

## Notes on deliberate overlaps

- BUG-06 (checkout always 500) and BUG-11 (console error on checkout submit)
  both trigger from the same "Place Order" action but are independent bugs
  with independent evidence (network vs. console) — a thorough agent should
  report both.
- BUG-09 and BUG-14 both touch the "Add to Cart" flow on the product detail
  page but are distinguishable: BUG-14 affects the confirmation message for
  *every* product with no console error; BUG-09 additionally throws a console
  error and blocks the cart add, but *only* for product id 2.

## Telemetry-only vs. visual-only (why this matters)

A naive detector that requires *both* a visual difference **and** a
console/network signal before it will report anything would miss real bugs.
This fixture deliberately includes both extremes:

- **Visual-only, zero telemetry:** BUG-01, BUG-02, BUG-03, BUG-04 (all
  category a). No console error, no failed request — purely a look at the
  rendered page reveals them.
- **Telemetry-only, zero visual change:** BUG-07 (network), BUG-09, BUG-10,
  BUG-11, BUG-12 (console). The page looks identical to baseline; only a
  console listener or network listener would catch these.

A correct testing agent must flag both kinds.
