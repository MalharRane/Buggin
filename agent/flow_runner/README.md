# flow_runner

Executes a `TranslatedFlow` (from `flow_translator/`, sub-phase 1) against a
real running app in a real Playwright browser - "spec mode": each step is
checked against the flow author's own stated `expect`, not against a
baseline run. See the module docstrings in `runner.py`/`cli.py` for the
mechanics; this file documents the abort behavior's actual (and remaining)
limitations, and the regression test suite pinning the expectation
checker's correctness.

## Abort behavior: fatal vs. non-fatal is already distinguished

Only one thing aborts a flow: a step's operation whose target element
**cannot be resolved at all** (a button/link/field that genuinely isn't
there), or an operation that raises an exception. That step is marked
`"failed"`, and every step after it is recorded as `"skipped (flow aborted
at an earlier step)"` without being executed.

**An unmet `expect`, or a console/network error on an action that *did*
otherwise execute, does NOT abort the flow.** This already matches the
fatal/non-fatal distinction that matters: "the action itself couldn't
happen, so there's no way to check the next step's precondition" is a
different situation from "the action happened, but its result was wrong or
undesirable" - the page is still in a normal, navigable state in the
second case, so later steps are still attempted. This is directly visible
in a real run: `checkout_backpack.yaml` against `versions/v1-buggy` hits an
unmet expectation at step 2 (BUG-14 - no confirmation text after Add to
Cart) and **still proceeds** to step 3 (go to the cart, which succeeds) -
it only actually stops at step 4, for the unrelated reason that the
checkout button doesn't exist at all (BUG-13, a genuine `element-not-found`).

### The real remaining limitation: abort is flow-wide, not step-scoped

What's still coarse is the *scope* of a fatal abort. Once any step hits
`element-not-found`, **every subsequent step is skipped unconditionally**
- even a later step whose own precondition doesn't actually depend on the
failed one. In practice, most hand-authored flows genuinely are a strict
chain (each step needs the page state the previous one produced), so this
rarely costs real coverage - but it's a real, un-examined assumption, and
is the source of the coverage difference between two runs of the same flow
shape against `versions/v1-buggy`, differing only in which product they
open:

| Flow | Product | Steps reached | Findings |
|---|---|---|---|
| `checker_full_pass.yaml` shape → `checkout.yaml`/Classic Tee (product 1) | product's card has no "View Details" link at all (BUG-15) | stops at step 1 | 3 (BUG-05 from step 0, then BUG-15) |
| `checkout_backpack.yaml` → Canvas Backpack (product 3) | reaches checkout before hitting a wall | stops at step 4 | 6 (BUG-05, BUG-07, BUG-14, then BUG-13) |

Same app, same bug catalog, same flow shape - a 2x difference in findings,
purely because of which product happened to hit a *fatal* wall first (a
non-fatal one, as shown above, does not cut a run short). **A single
flow_runner run is not a substitute for the regression agent's own crawl**
(built to keep going and characterize the whole app); it's a targeted
check of one specific user journey, up to the first thing that stops that
journey cold.

### Planned refinement (not built yet)

Attempt each subsequent step regardless of an earlier fatal failure,
rather than skipping the rest of the flow outright. If a later step's own
precondition genuinely isn't met either, its own locator resolution will
honestly produce its own `element-not-found` finding - no worse than
today's blanket skip, and it stops silently discarding steps that might
have turned out to be independently reachable (e.g. via a different nav
path) rather than actually chained to the failed one. This is **not
implemented** - `run_flow` still skips everything after the first fatal
step unconditionally.

## Expectation-checker correctness: pinned regression tests

The checker was under-exercised in early validation (most flows aborted
before reaching more than one or two `expect` checks). Three adversarial
flows caught and fixed two real bugs in `_check_expectation` before it
could be trusted:

1. **False negative**: `element_present` only checked clickable elements
   and page-wide text-overlap, missing a genuinely-present but
   non-clickable confirmation `<div>` and a vague description with no
   literal wording in common with the real text ("confirmation message" vs
   "Added to cart!"). Fixed by giving `element_present` the same
   non-clickable-text and local-diff fallbacks `text_appears` already had.
2. **False positive** (the more dangerous direction): a cart holding 2
   *different* products (each with its own quantity of 1) was checked
   against the deliberately wrong claim "the cart shows 1 item" - and
   passed, because a bare `"1"` (one product's row quantity) is a
   substring of `"1 item"`, and nothing in the original matching logic
   distinguished "a stray matching digit exists somewhere" from "this
   number is the answer to the question being asked." Fixed with
   `_numeric_claim_supported`: a bare-digit claim is only trusted if it's
   the page's **sole** distinct bare-number candidate; if a different bare
   number is also present (as it was here - the header badge correctly
   showed "2"), the claim is treated as unsupported rather than guessed at.

### Running the regression suite

`tests/` pins these three flows as first-class test artifacts:

```
flow_runner/tests/
  flows/
    checker_full_pass.yaml        - 6 steps, 3 explicit `expect`s, runs to completion
    checker_wrong_count.yaml      - adds 1 item, wrongly claims 2 (no other signal)
    checker_quantity_stress.yaml  - adds 2 DIFFERENT items, wrongly claims "1 item"
  translated/*.json               - PINNED translator output for each flow above
  check_expectation_checker.py    - loads the pinned JSON and asserts the verdicts
  regenerate_translated.py        - re-translates and overwrites the pinned JSON
```

```bash
# Needs versions/v0-baseline running - does NOT need GROQ_API_KEY
python -m flow_runner.tests.check_expectation_checker --url http://localhost:3000
```

Expected output: all three `[PASS]`, exit code 0.
`checker_full_pass` must produce zero findings; `checker_wrong_count` and
`checker_quantity_stress` must produce exactly one `expectation-unmet`
finding each and nothing else.

**Why pinned JSON instead of calling the live translator each time**:
`translate_flow()` calls Groq, and its output is non-deterministic - the
same input can come back with different wording or even a different
`expect_type` across calls (observed directly: the confirmation-text step
translated as `text_appears` in one run and `element_present` in another).
A test built on live translation would be flaky for reasons that have
nothing to do with the matcher being pinned. Loading a saved,
already-reviewed translated plan means these tests exercise *only*
`run_flow()`'s deterministic logic - locator resolution and expectation
checking - which is exactly what needs pinning. Re-generate the pinned
plans only deliberately, after a reviewed `flow_translator` change
(`python -m flow_runner.tests.regenerate_translated`, needs
`GROQ_API_KEY`), and diff the output before committing it.

**If you change `_check_expectation`, `_text_overlap`,
`_expectation_overlap`, or `_numeric_claim_supported`, re-run this suite**
before trusting the result - this class of bug is easy to reintroduce and
easy to miss without a deliberately adversarial test.
