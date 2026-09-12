# Regression-Testing Agent (Phase 1)

A Playwright Python agent that crawls the mock storefront in
[`../versions/`](../versions/), diffs a candidate version's behavior against
`v0-baseline`, and reports regressions. It is scored against
[`../fixtures/BUG_CATALOG.md`](../fixtures/BUG_CATALOG.md) and
[`../fixtures/CHANGE_CATALOG.md`](../fixtures/CHANGE_CATALOG.md), but it has
**no knowledge of either file** - it never hardcodes a bug ID, a selector
tied to a specific product, or a specific expected finding count. Everything
it reports comes from generic evidence capture and diffing.

## Why Playwright Python

Chosen over the Playwright/TS or Selenium alternatives for three reasons:
sync API fits an evidence-gathering crawl better than threading `async` through
every step; `page.on("console"/"pageerror"/"response")` map directly onto this
project's four evidence types (visual/console/network/DOM); and it keeps the
whole agent in one language with a straightforward `pip install` (no build step).

## Architecture

```
regression_agent/
  config.py       version URLs, test data, locator text-patterns
  recorder.py     per-page console/network event capture, sliceable per step
  visual_scan.py  DOM-geometry visual-anomaly scan (no vision model - see below)
  locators.py     generic text/role/label-based element discovery
  capture.py      the crawler: walks listing -> each product -> cart -> checkout
  rules.py        deterministic diff: baseline profile vs candidate profile -> Findings
  adjudicate.py   Claude call for the one ambiguous finding type (see below)
  report.py       renders report.json + report.md
  cli.py          `python -m regression_agent.cli`
```

### The crawl is generic, not fixture-specific

`capture.py` doesn't know "click `#add-to-cart-btn`" - it asks
`locators.find_clickable()` for the first visible clickable element whose
text matches a small set of e-commerce-vocabulary regexes (`config.PATTERNS`),
e.g. `add to (cart|bag|basket)`. This is what lets the *same* crawl code
run unmodified against v0-baseline, v1-buggy, and v1-clean even though
v1-clean renames "Add to Cart" -> "Add to Bag" and "Checkout" -> "Proceed to
Payment" - those are legitimate copy changes the agent must not choke on
(or worse, mistake for a dead flow).

For the checkout flow specifically, the crawler doesn't assume a fixed
number of steps: after filling the form and clicking the primary CTA, it
loops (bounded by `config.MAX_CHECKOUT_HOPS`) checking for a visible
success message and, if absent, looking for a new CTA (confirm/continue) to
click. This is what lets it walk straight through v1-clean's added
"review your order" screen (CHANGE-11) without any special-casing - it just
naturally records a 3-step path there vs. a 2-step path on baseline.

### Evidence captured per step

- **Console** - `error`/`warning`-level console messages and uncaught
  `pageerror` exceptions.
- **Network** - every response's URL, method, and status code.
- **Visual (no vision model)** - `visual_scan.py` runs one `page.evaluate()`
  that computes, from the live DOM: contrast ratio between a clickable
  element's text and its own background (catches "invisible button" bugs),
  an `<img>`'s rendered vs. natural aspect ratio (catches squished/stretched
  images), pairwise bounding-box overlap between visible interactive/text
  elements (catches collapsed/overlapping layouts), and height variance
  across a repeated grid/list's children (catches one card's layout blowing
  up). This is deliberately geometry-based, not pixel/vision-based - it
  stays cheap and fast, and Phase 0 explicitly scoped vision models out.
- **DOM/control reachability** - for each expected control (product link,
  add-to-cart, cart nav, qty +/-, checkout CTA, submit/confirm), whether it
  was found at all.

### Rules first, LLM only for the genuinely ambiguous case

`rules.py` flags, with `confidence: "high"` (no LLM involved):
- any console error/exception in the candidate that wasn't in baseline,
- any request that returned 2xx in baseline and now returns 4xx/5xx,
- any request that fired in baseline and now fires **zero** times for the
  same action (a control that's still visible but silently no longer wired
  up - see the product-4 case below),
- any new visual anomaly,
- any control reachable in baseline that's no longer reachable,
- checkout going from completing to not completing at all.

Only one case is routed to Claude (`adjudicate.py`, `claude-opus-5`,
structured output via a Pydantic `AdjudicationResult`): **the checkout path
still reaches success on both sides, but the path/DOM shape differs.** A
rule can't tell "a developer added a legitimate extra step" apart from "a
regression that happens to route around itself and still limp to a 200" -
that's a judgment call, so it's the only thing that costs a model call. If
no Anthropic credentials are configured, this is marked `"unresolved"` and
listed in the report's audit appendix - it is **never** defaulted to
"regression" (which would produce a false positive) or silently dropped.

## Running it

A `.venv` for this folder is already set up with everything installed
(`pip install -r requirements.txt` + `playwright install chromium`) - just
activate it:

```powershell
cd agent
.venv\Scripts\Activate.ps1     # PowerShell; use .venv\Scripts\activate.bat for cmd.exe

# In three other terminals, from the repo root:
node ..\versions\v0-baseline\server.js   # :3000
node ..\versions\v1-buggy\server.js      # :3001
node ..\versions\v1-clean\server.js      # :3002

python -m regression_agent.cli --target v1-buggy --out out/v1-buggy
python -m regression_agent.cli --target v1-clean --out out/v1-clean
```

Setting up from scratch elsewhere:

```bash
cd agent
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m playwright install chromium
```

## Scoring the agent (`scoring/`)

A separate package - `scoring/` - mechanically grades a `report.json` against
the ground-truth catalogs (`../fixtures/BUG_CATALOG.md`,
`../fixtures/CHANGE_CATALOG.md`). It does not touch or import
`regression_agent/` at all: it reads `report.json` as plain data, exactly as
a human grader would, which is also what makes it a check on the agent's
independence - see "Verifying no leakage" below.

```bash
python -m scoring.cli --report out/v1-buggy/report.json --target v1-buggy
python -m scoring.cli --report out/v1-clean/report.json --target v1-clean
```

Writes `scorecard.md` + `scorecard.json` next to the report, and also prints
the scorecard to stdout. `catalog_parser.py` parses both catalog tables into
structured records (bug ID, category, page types, product id, and - for
network bugs specifically - a resource hint like "image" vs "cart-track" vs
"products-fetch", since two different network bugs can land on the same
page/product). `matcher.py` maps each surfaced finding onto a bug using only
category + page/product (+ resource hint for network) - no fuzzy text
matching, no partial credit. Unmatched findings are never dropped; each gets
a "near-miss" annotation (which bug(s) it's close to and why it didn't
count) so a human can judge it instead of the harness guessing.

**Recall is reported two ways** for v1-buggy: over all 16 catalogued bugs,
and over just the ones actually reachable given BUG-13 removes the cart's
only path to checkout (3 bugs live there and can't be exercised through the
UI in this build - that's a property of this specific buggy build, not a
detection failure).

**Verifying no leakage:** `check_leakage()` regex-scans the raw
`report.json` text for any literal `BUG-NN`/`CHANGE-NN` string before
scoring, and the CLI's exit code is non-zero if any are found. The agent
must never see or reference a catalog ID - if this ever fires, the finding
pipeline has been contaminated with ground truth and the whole run's
results are suspect.

Writes `out/<target>/report.json` and `report.md`. Add `--save-captures` to
also dump the raw per-run evidence (`capture_baseline.json`/`capture_target.json`)
for debugging. Add `--no-adjudicate` to skip the Claude call entirely (any
ambiguous structural-divergence finding is then left unresolved rather than
auto-cleared or auto-flagged).

LLM adjudication needs Anthropic credentials (`ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, or `ant auth login`) - see `adjudicate.py`. Without
them the pipeline still runs and still produces a valid report; only the
ambiguous bucket goes unresolved.

## Validated results (this session)

Ran against the live fixture servers:

- **v1-buggy**: 26 findings, directly covering 11 of the 16 catalogued bugs
  with concrete evidence (BUG-01, 02, 05, 07, 08, 09, 10, 12, 13, 15, 16).
  3 bugs (BUG-04, 06, 11) live on the checkout page, which BUG-13 makes
  completely unreachable from the cart in this build - the agent correctly
  reports "checkout unreachable" rather than fabricating unreachable-page
  findings, which is the behavior a real QA pass would also produce.
- **v1-clean**: **0 findings reported.** The only rule that fired at all was
  the expected structural-divergence on checkout (2 steps -> 3 steps, i.e.
  CHANGE-11); with no API key available in this environment it was correctly
  left `"unresolved"` in the audit appendix rather than being flagged.
  Zero false positives on the wishlist feature, promo banner, live clock,
  copy changes, restyled buttons, or the new optional form field.
- **Bonus finding, not in the original catalog**: the new "network dropped
  to zero" rule discovered that BUG-12's uncaught exception (product id 4's
  missing `rating` field) is thrown *before* the "Add to Cart" button's
  click listener is attached in `product.js` - so for product 4, Add to
  Cart is completely inert (no console error, no network call, nothing
  added to cart), not just cosmetically showing a placeholder rating as
  `BUG_CATALOG.md` currently describes. Worth a catalog correction.

The 11/16 (85% of the 13 reachable) figure above is no longer just a
hand-count - it's mechanically reproduced by `scoring/` (see below), which
also caught and fixed a real over-crediting bug in its own matcher: an
early version credited BUG-14 ("confirmation text never appears") from
findings that were actually about *missing controls* (BUG-13/15/16's
territory), just because both shapes happen to be `category="dom-missing"`
on overlapping pages. The fix required matching on the finding's specific
evidence shape, not just category+page - see `scoring/matcher.py`'s
`_claim_matches`.

## Known limitations (honest, not swept under the rug)

- **BUG-03 not caught.** The seeded bug removes text truncation so a long
  product name wraps instead of being clipped - but in a CSS Grid with
  default `align-items: stretch`, every card in that row stretches to match,
  so no card's box is actually shorter/taller than its row-mates. The
  `uneven_siblings` heuristic doesn't fire. Catching this reliably would need
  per-element correspondence between baseline and candidate DOM snapshots
  (comparing the *same* named element's box across runs), which is a
  meaningfully bigger feature than the current page-level anomaly scan.
- **BUG-14 not caught.** Nothing currently checks "did clicking this produce
  the visible feedback text baseline showed." Building that generically
  (diffing visible-text-that-appeared-after-an-action between runs) is a
  reasonable next feature but wasn't built this session.
- **Locator vocabulary is e-commerce-flavored, not fully general.** Patterns
  like `checkout|proceed to payment` are generous but finite; a rename to
  wholly novel vocabulary (e.g. "Finalize") would need a pattern added, or a
  fallback to an LLM-based element-grounding step (not built).
- **No scoring harness.** This agent produces findings; comparing them
  field-by-field against `BUG_CATALOG.md`/`CHANGE_CATALOG.md` to compute
  precision/recall automatically is a natural next step, not built here.
