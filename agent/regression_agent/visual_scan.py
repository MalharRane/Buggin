"""Generic, DOM-geometry-based visual anomaly scanner.

No vision model, no screenshots-as-pixels comparison - just computed styles
and getBoundingClientRect() math run in-page via page.evaluate(). This is
deliberately generic (it doesn't know which selector to look at); it scans
whatever is currently visible and reports four kinds of anomaly:

  - low_contrast:    a clickable element's text color is nearly identical
                      to its own background (an "invisible button").
  - distorted_image:  an <img>'s rendered aspect ratio diverges sharply from
                      its natural (source) aspect ratio.
  - overlap:          two independent visible elements' boxes overlap by
                      more than half of the smaller one's area.
  - uneven_siblings:  repeated sibling blocks (e.g. a card grid) whose
                      rendered heights vary far more than layout drift would
                      explain - a proxy for "layout collapsed for one item".

Thresholds are deliberately conservative so legitimate restyles (new but
still-readable color scheme, circular vs. square buttons, an added
optional field) do not trip them.
"""

_VISUAL_SCAN_JS = r"""
() => {
  function luminance(r, g, b) {
    const a = [r, g, b].map(v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
  }
  function parseColor(str) {
    const m = str && str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? +m[4] : 1 };
  }
  function contrastRatio(fg, bg) {
    const l1 = luminance(fg.r, fg.g, fg.b) + 0.05;
    const l2 = luminance(bg.r, bg.g, bg.b) + 0.05;
    return l1 > l2 ? l1 / l2 : l2 / l1;
  }
  function describeEl(el) {
    const id = el.id ? '#' + el.id : '';
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\s+/).join('.') : '';
    return el.tagName.toLowerCase() + id + cls;
  }

  const findings = [];

  // 1. Low-contrast ("invisible") clickable elements.
  document.querySelectorAll('button, a, input[type=submit], input[type=button]').forEach(el => {
    const text = (el.innerText || el.value || '').trim();
    if (!text) return;
    if (el.offsetParent === null) return; // not visible
    const style = getComputedStyle(el);
    const fg = parseColor(style.color);
    let bgEl = el, bg = null;
    while (bgEl && !bg) {
      const c = parseColor(getComputedStyle(bgEl).backgroundColor);
      if (c && c.a > 0) bg = c;
      bgEl = bgEl.parentElement;
    }
    if (fg && bg) {
      const ratio = contrastRatio(fg, bg);
      if (ratio < 1.5) {
        findings.push({ type: 'low_contrast', selector: describeEl(el), text, ratio: Math.round(ratio * 100) / 100 });
      }
    }
  });

  // 2. Distorted image aspect ratio.
  document.querySelectorAll('img').forEach(img => {
    if (img.naturalWidth > 0 && img.naturalHeight > 0 && img.offsetWidth > 0 && img.offsetHeight > 0) {
      const naturalRatio = img.naturalWidth / img.naturalHeight;
      const renderedRatio = img.offsetWidth / img.offsetHeight;
      const diff = Math.abs(naturalRatio - renderedRatio) / naturalRatio;
      if (diff > 0.2) {
        findings.push({
          type: 'distorted_image', selector: describeEl(img), src: img.src,
          naturalRatio: Math.round(naturalRatio * 100) / 100,
          renderedRatio: Math.round(renderedRatio * 100) / 100,
        });
      }
    }
  });

  // 3. Overlapping independent elements.
  const boxed = Array.from(document.querySelectorAll(
    'button, a, input, label, h1, h2, [class*=name], [class*=price], [class*=title]'
  ))
    .filter(el => el.offsetParent !== null)
    .map(el => ({ el, rect: el.getBoundingClientRect() }))
    .filter(o => o.rect.width > 2 && o.rect.height > 2);

  for (let i = 0; i < boxed.length; i++) {
    for (let j = i + 1; j < boxed.length; j++) {
      const a = boxed[i], b = boxed[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ix = Math.max(0, Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left));
      const iy = Math.max(0, Math.min(a.rect.bottom, b.rect.bottom) - Math.max(a.rect.top, b.rect.top));
      const overlapArea = ix * iy;
      const smallerArea = Math.min(a.rect.width * a.rect.height, b.rect.width * b.rect.height);
      if (smallerArea > 0 && overlapArea / smallerArea > 0.5) {
        findings.push({
          type: 'overlap', a: describeEl(a.el), b: describeEl(b.el),
          ratio: Math.round((overlapArea / smallerArea) * 100) / 100,
        });
      }
    }
  }

  // 4. Uneven sibling heights in a repeated grid/list.
  document.querySelectorAll('[class*=grid], [class*=list]').forEach(container => {
    const children = Array.from(container.children).filter(c => c.offsetParent !== null);
    if (children.length >= 3) {
      const heights = children.map(c => c.getBoundingClientRect().height).filter(h => h > 0);
      if (heights.length >= 3) {
        const max = Math.max(...heights), min = Math.min(...heights);
        if (min > 0 && max / min > 1.3) {
          findings.push({
            type: 'uneven_siblings', container: describeEl(container),
            max: Math.round(max), min: Math.round(min),
          });
        }
      }
    }
  });

  return findings;
}
"""


def run_visual_scan(page):
    """Return a list of anomaly dicts found on the currently loaded page."""
    try:
        return page.evaluate(_VISUAL_SCAN_JS)
    except Exception as exc:
        return [{"type": "scan_error", "error": str(exc)}]
