"""Render findings (from rules.diff_profiles, optionally passed through
adjudicate.adjudicate) as JSON and Markdown reports."""
import json
from datetime import datetime, timezone


def write_json(findings, run_meta, path):
    payload = {"run": run_meta, "findings": findings}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _final_findings(findings):
    """Findings the report should actually surface: every high-confidence
    finding, plus ambiguous ones adjudicated as a real regression. Ambiguous
    findings cleared as "legitimate_change" (or left "unresolved") are kept
    out of the headline list but still shown in an appendix for auditing."""
    surfaced, cleared = [], []
    for f in findings:
        if f["confidence"] == "high":
            surfaced.append(f)
        elif f["verdict"] == "regression":
            surfaced.append(f)
        else:
            cleared.append(f)
    return surfaced, cleared


def write_markdown(findings, run_meta, path):
    surfaced, cleared = _final_findings(findings)

    lines = [
        f"# Regression report - {run_meta['target_name']} vs {run_meta['baseline_name']}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Baseline: {run_meta['baseline_url']}  ",
        f"Candidate: {run_meta['target_url']}",
        "",
        f"**{len(surfaced)} finding(s) to report.**",
        "",
    ]

    if not surfaced:
        lines.append("No regressions found.")
        lines.append("")
    else:
        by_category = {}
        for f in surfaced:
            by_category.setdefault(f["category"], []).append(f)
        for category in ("visual", "network", "console", "dom-missing", "feedback-missing", "structural-divergence"):
            items = by_category.get(category, [])
            if not items:
                continue
            lines.append(f"## {category} ({len(items)})")
            lines.append("")
            for f in items:
                lines.append(f"- **{f['page']}**: {f['description']}")
                if f.get("verdict") == "regression":
                    lines.append(f"  - *LLM verdict: regression* — {f.get('reasoning', '')}")
            lines.append("")

    if cleared:
        lines.append("## Findings NOT reported (cleared or unresolved)")
        lines.append("")
        lines.append(
            "These were structural divergences flagged as ambiguous by the "
            "rule engine, then adjudicated. They are listed here for audit "
            "purposes only - they are not part of the regression count above."
        )
        lines.append("")
        for f in cleared:
            lines.append(f"- **{f['page']}**: {f['description']}")
            lines.append(f"  - *Verdict: {f.get('verdict')}* — {f.get('reasoning', '')}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
