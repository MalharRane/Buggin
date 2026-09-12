# Buggin — Phase 0: Test Fixture + Answer Key

This repo is **Phase 0** of a web-app regression-testing project. It contains
only the *fixture* — the small mock e-commerce app being tested, in three
controlled versions — and the documented ground truth for what changed
between them. It does **not** contain any testing agent, Playwright code, or
test logic. That comes in a later phase, and will be measured against the
catalogs in [`fixtures/`](fixtures/).

## The app

A minimal mock e-commerce storefront: no framework, no build step, no
database — plain HTML/CSS/JS served by a ~90-line Node script that uses only
built-in `http`/`fs` modules (no `npm install` required, no dependencies).
Product data lives in a static `data/products.json` per version; the cart is
kept in the browser's `localStorage`.

Pages/flows, present identically in all three versions:
- **Product listing** (`/index.html`) — a grid of 6 products (image, name, price).
- **Product detail** (`/product.html?id=N`) — one product, "Add to Cart".
- **Cart** (`/cart.html`) — items, quantities, total, "Checkout".
- **Checkout** (`/checkout.html`) — name/email/address form, "Place Order",
  and a success confirmation state.

## Three versions, three folders

Each version is a **separate, fully self-contained folder** under
[`versions/`](versions/) with its own `server.js`, `package.json`, and
`public/` directory — rather than three git branches. This was the
deliberate choice: folders let all three run **simultaneously**, side by
side, on different ports, with zero branch-switching. That matters here
because a testing agent (in a later phase) will likely want to diff or
compare live behavior across versions in the same session, and comparing
three running servers is far simpler than checking out branches one at a
time. The tradeoff is some duplicated code between the three folders — an
acceptable cost, since the whole point of this fixture is that every file is
small, controlled, and independently readable, not that the three versions
share a codebase.

| Version | Folder | Port | Purpose |
|---|---|---|---|
| **V0 — baseline** | [`versions/v0-baseline`](versions/v0-baseline) | 3000 | Known-good reference. Everything works. |
| **V1 — buggy** | [`versions/v1-buggy`](versions/v1-buggy) | 3001 | Identical to V0 plus 16 deliberately seeded bugs. See [`fixtures/BUG_CATALOG.md`](fixtures/BUG_CATALOG.md). |
| **V1 — clean** | [`versions/v1-clean`](versions/v1-clean) | 3002 | Identical to V0 plus 11 harmless developer-style changes (including one legitimate checkout flow/structure change) and zero real bugs. See [`fixtures/CHANGE_CATALOG.md`](fixtures/CHANGE_CATALOG.md). |

### Running each version

No dependencies to install. From the repo root:

```bash
node versions/v0-baseline/server.js   # http://localhost:3000
node versions/v1-buggy/server.js      # http://localhost:3001
node versions/v1-clean/server.js      # http://localhost:3002
```

(Or `cd` into a version's folder and run `npm start` / `node server.js`.) All
three can run at once, in separate terminals, since they listen on different
ports and each has its own `localStorage` origin.

## Why V1-CLEAN exists

The obvious failure mode for a regression-testing agent is missing real
bugs (false negatives) — that's what V1-buggy and its answer key measure.
The *less* obvious, easy-to-overlook failure mode is an agent that's too
trigger-happy: flagging reworded button text, a restyled header, or a
timestamp that changes every second as if they were bugs. An agent that
"finds" 16 issues on V1-buggy but also "finds" 8 issues on V1-clean hasn't
actually learned to distinguish real regressions from normal development —
it's just pattern-matching on "the app changed."

V1-clean is that trap, deliberately laid: every change in it is something a
real developer would legitimately ship (copy tweaks, a restyle, a genuinely
working new feature, dynamic content that's supposed to change on every
load). **The correct output of a good testing agent run against V1-clean is
an empty report.** Any finding there is a false positive, and
[`fixtures/CHANGE_CATALOG.md`](fixtures/CHANGE_CATALOG.md) is the exact list
to check false positives against.

Together, V1-buggy and V1-clean let a later phase measure both **recall**
(bugs found ÷ 16 seeded bugs) and **precision** (real findings ÷ total
findings, using V1-clean to surface any false positives) — not just one or
the other.

One entry in V1-clean (CHANGE-11) goes further than cosmetic/copy tweaks: it
adds a genuine extra step to the checkout flow, changing the action path and
DOM structure versus v0-baseline. It's there specifically to test a future
**replay-based** auditor, which may compare a recorded v0-baseline action
trace against v1-clean's live behavior — that comparison will diverge at
checkout by design. A correct auditor has to tell "the path changed but the
flow still legitimately completes" apart from "the path changed because
something broke." See CHANGE-11 in
[`fixtures/CHANGE_CATALOG.md`](fixtures/CHANGE_CATALOG.md) for the full
rationale.

## Bug design notes

The 16 seeded bugs in V1-buggy are spread evenly across four categories (4
each): pure visual/CSS breaks with no console or network error, network
failures (4xx/5xx), uncaught console/JS errors, and missing/broken DOM
elements or dead-end flows. Critically, the set also includes bugs at both
extremes of "evidence type":

- **Visual-only, no telemetry at all** (BUG-01 through BUG-04): a screenshot
  or DOM inspection catches these; a console/network listener sees nothing.
- **Telemetry-only, no visual change** (BUG-07, BUG-09 through BUG-12): the
  rendered page is pixel-identical to baseline; only a console or network
  listener catches these.

This split exists so that a naive detector requiring *both* a visual diff
*and* a technical signal before reporting anything is provably inadequate —
it would miss roughly a third of the seeded bugs. Full detail, per-bug
selectors, and exact evidence type are in
[`fixtures/BUG_CATALOG.md`](fixtures/BUG_CATALOG.md).

## Phase 0 vs. Phase 1

This README originally described Phase 0 only: no Playwright, no test
runner, no agent code, no vision model calls, no database - just the
fixture and its answer key.

**Phase 1 now exists** in [`agent/`](agent/): a Playwright Python
regression-testing agent that crawls the fixture generically (no knowledge
of the bug/change catalogs), captures console/network/DOM/visual-geometry
evidence, diffs it against a baseline run, and uses an LLM only to
adjudicate the one genuinely ambiguous finding type - a checkout flow whose
path changed but still succeeds (the CHANGE-11 case). See
[`agent/README.md`](agent/README.md) for architecture, how to run it, and
an honest list of what it does and doesn't catch yet.
