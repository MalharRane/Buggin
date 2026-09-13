# Buggin

**Buggin** is an autonomous web-app regression-testing agent that grounds
every finding in mechanical evidence — network responses, console
exceptions, DOM/CSS geometry, or a behavior it learned from a baseline run —
and refuses to report anything it can't back up that way. Measured against a
controlled fixture with a hand-built answer key, it detects **12 of the 13
reachable seeded regressions** across four evidence types, produces **zero
false positives** on both a deliberately broken build and a benign
no-bugs-but-changed build, and correctly tells a legitimate structural
change apart from a regression using one narrow, evidence-only LLM call.

## The problem it solves

Most UI regression tooling picks one of two failure modes. Brittle
selector-based scripts break the moment a button gets renamed or a
confirmation screen gets added, generating noise on every legitimate
release. AI-driven "explorers" go the other way — they narrate plausible-
sounding bugs with nothing to back them up, so every report needs a human
to re-verify it before it's trustworthy. Buggin's thesis is narrower and
more testable: **report a regression only when it can be proven** — a
failed request, a thrown exception, a measurable layout defect, or a
documented behavioral change from baseline — **and say nothing otherwise.**
Precision is treated as a first-class metric, not an afterthought to recall.

## How it works

The repo is built in two halves. [`versions/`](versions/) holds three
copies of the same small e-commerce app — a **baseline** that works
correctly, a **buggy** build with 16 deliberately seeded regressions spread
evenly across four categories, and a **clean** build with 11 harmless
developer-style changes (reworded buttons, a restyle, a genuinely new
feature, live/dynamic content, and one deliberately real structural change
to the checkout flow) and zero real bugs. The clean build exists because
recall is only half the story: an agent that "finds" every seeded bug but
also flags half the harmless changes hasn't learned to distinguish a
regression from ordinary development — it's just reacting to any diff. Full
per-bug and per-change ground truth lives in
[`fixtures/BUG_CATALOG.md`](fixtures/BUG_CATALOG.md) and
[`fixtures/CHANGE_CATALOG.md`](fixtures/CHANGE_CATALOG.md).

[`agent/`](agent/) is the regression-testing agent itself — a Playwright
Python crawler that walks each build's listing, product, cart, and checkout
flows using semantic (role/text) locators rather than hardcoded selectors,
so a legitimate rename doesn't register as a broken flow. At each step it
captures four kinds of evidence: every network response's status code,
every console error and uncaught exception, a DOM-geometry scan for visual
defects (contrast, aspect-ratio distortion, element overlap, layout
collapse — no vision model involved), and a baseline-learned check for
missing post-action feedback (it diffs the visible text near a clicked
control before and after the click, and treats *baseline's own behavior* as
the expectation — so a reworded confirmation is never flagged, only a
confirmation that stops appearing at all). A deterministic rule engine then
diffs a candidate run against the baseline run and flags anything that
regressed. Only one situation is ambiguous enough to need judgment: a
checkout flow whose path changed shape but still completes successfully on
both sides. That single case is handed — with nothing but its own before/
after evidence, no fixture knowledge — to an LLM (Groq's
`openai/gpt-oss-120b`) to classify as a legitimate change or a regression.
The LLM never discovers bugs on its own; it only rules on a case the
deterministic rules already isolated.

## Two ways to define "correct"

Buggin supports two ways to define what "correct" means for the app under
test, both feeding the same grounded evidence engine that only ever flags
with mechanical proof. **Regression mode** (above) defines it as *matches
a known-good baseline run* — no spec, no catalog, just a diff against
working behavior. **Spec mode** (`agent/flow_translator/` +
`agent/flow_runner/`, newer) defines it as *whatever a user states
explicitly*: you write a light-structured, plain-language flow — a named
list of steps, each an action plus an optional expected outcome — an LLM
translates it into a concrete step plan (navigate/click/fill/assert,
targets described generically by text/role/label, never executed at
translation time), and `flow_runner` executes that plan through the same
network/console/DOM/visible-text evidence capture regression mode uses,
checking each stated expectation against what was actually observed. A
step that succeeds produces nothing; only a genuine failure or an unmet
expectation is reported, and it always cites the same kind of mechanical
evidence — no semantic judgment calls. One caveat carried over honestly:
spec-mode flows currently abort at the first step whose action genuinely
can't be performed (a missing element) rather than continuing past it — a
real coverage limitation, detailed in
[`agent/flow_runner/README.md`](agent/flow_runner/README.md) along with
the pinned regression tests that protect its expectation checker.

## Measured results

| Metric | Result | How it's computed |
|---|---|---|
| Recall, reachable bugs | **12 / 13 (92%)** | 3 of the 16 seeded bugs live behind a checkout button the buggy build itself removes, making them unreachable through the UI in this build — excluded from this denominator as a property of the build, not a detection gap |
| Recall, all seeded bugs | **12 / 16 (75%)** | Same numerator over the full catalog, unreachable bugs included |
| False positives, buggy build | **0** | Every reported finding traces to a real seeded bug; the handful that don't map to one specific bug ID are secondary evidence of bugs already credited elsewhere (e.g. a browser's own network-failure log echoing a 404 already caught), not spurious flags |
| False positives, clean build | **0** | The agent reported nothing on the 11-change benign build |
| Ambiguous structural change | **Correctly classified** | The one deliberately-planted "legitimate but structurally different" checkout flow was adjudicated `legitimate_change`, not flagged |

These numbers come from [`agent/scoring/`](agent/scoring/), a harness that
parses the catalogs into structured records and matches each finding to a
specific bug by category **and** the specific claim it makes (a missing-
control finding can't be credited to a missing-confirmation-text bug just
because both are in the same category) — not eyeballed, and reproducible
by anyone who runs the commands below. As a side effect of building it, the
agent surfaced a real gap in the hand-written answer key itself (a second,
undocumented symptom of one seeded bug) that got folded back into the
catalog — a small but genuine demonstration that its findings are grounded
in actual behavior, not fitted to the answer key.

## Honest limitations

- **Tested against a controlled fixture, not yet a real third-party app.**
  That was a deliberate choice — recall and precision are only measurable
  against a fixture with a known answer key. Running it against a real app
  (without ground truth to check against) is the natural next step, and a
  meaningfully different problem.
- **One seeded bug (BUG-03) is a known, documented miss.** It removes text
  truncation so a product name wraps instead of clipping — but in this
  fixture's CSS Grid, every card in that row stretches to match the tallest
  one, so no card's box actually differs in size from its neighbors, and
  the layout-variance heuristic never fires. Root cause and fix path are
  written up in [`agent/README.md`](agent/README.md).
- **The crawler assumes an e-commerce-shaped flow** (listing → detail →
  cart → checkout) and a fairly generous but finite vocabulary of button/
  link text. A real app with a different flow shape or unfamiliar
  vocabulary would need locator patterns extended, or a more general
  element-grounding step — not built yet.
- **Scope boundary:** this detects UI and behavioral regressions — broken
  requests, thrown exceptions, visual defects, missing feedback, dead
  flows. It does **not** check for security vulnerabilities, and it does
  **not** verify functional correctness against a spec (it has no notion of
  what an app is *supposed* to do beyond "does it still behave like
  baseline"). Do not mistake it for either of those.

## Run it yourself

```bash
# Three terminals, from the repo root - no dependencies to install:
node versions/v0-baseline/server.js   # :3000
node versions/v1-buggy/server.js      # :3001
node versions/v1-clean/server.js      # :3002
```

```powershell
# In a fourth terminal:
cd agent
.venv\Scripts\Activate.ps1

python -m regression_agent.cli --target v1-buggy --out out/v1-buggy
python -m regression_agent.cli --target v1-clean --out out/v1-clean

python -m scoring.cli --report out/v1-buggy/report.json --target v1-buggy
python -m scoring.cli --report out/v1-clean/report.json --target v1-clean
```

The first two commands crawl each build and write `report.md`/`report.json`
to `agent/out/<target>/`; the last two grade those reports against the
catalogs and write `scorecard.md`/`scorecard.json` alongside them — the
exact numbers in the table above. See [`agent/README.md`](agent/README.md)
for full setup from scratch, architecture notes, and every finding category
in detail.

## Roadmap

The planned next step is a real-app target: point the same evidence-capture
and rules engine at an actual third-party app via record-and-replay
(rather than the fixture's known flow shape), which is a genuinely
different and harder problem than measuring against a controlled answer
key. Nothing beyond that is built yet.
