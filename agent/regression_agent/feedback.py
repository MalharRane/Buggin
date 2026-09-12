"""Generic post-action feedback detection.

Captures the set of visible text nodes near a control immediately before
and after clicking it. The DIFF (newly-appeared text) is the evidence that
an action produced user-visible feedback at all - without ever knowing what
that feedback is supposed to say. rules.py compares this diff between a
baseline run and a candidate run: if baseline's click produced new text and
the candidate's click produces none, that's a regression (a confirmation
that used to appear no longer does) - regardless of what the text said, so
a legitimate rewording never trips it.

Scoped to the clicked element's parent container, not the whole page. A
whole-page diff would be swamped by unrelated incidental UI updates that
happen to fire from the same click (e.g. a cart-item counter elsewhere in
the header incrementing) - those are real but unrelated side effects, and
including them would mask a missing *local* confirmation message by making
the page-wide diff look non-empty regardless of whether the actual
feedback near the button appeared.
"""
import re

_TIME_LIKE_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)?$", re.IGNORECASE)

_VISIBLE_TEXT_NEAR_JS = r"""
(el) => {
  const root = el.parentElement || el;
  const results = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const text = node.textContent.trim();
      if (!text) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility === 'hidden' || +style.opacity === 0) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  let node;
  while ((node = walker.nextNode())) {
    results.push(node.textContent.trim());
  }
  return results;
}
"""


def visible_text_near(locator):
    """Set of visible text strings within the clicked element's immediate
    parent container. Filters out timestamp-shaped strings (e.g. a live
    clock) so a page with a ticking clock doesn't look like every action
    produces feedback regardless of whether it actually did."""
    try:
        texts = locator.evaluate(_VISIBLE_TEXT_NEAR_JS)
    except Exception:
        return set()
    return {t for t in texts if not _TIME_LIKE_RE.match(t)}
