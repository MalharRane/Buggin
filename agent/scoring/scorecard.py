"""Compute and render the scorecard for one agent run against the catalogs."""
import json
import re

from .matcher import match_findings_to_bugs


def check_leakage(report_path):
    """Scan the raw report.json TEXT for any literal catalog ID. The agent
    (regression_agent/*) must never know these - it's pure evidence in,
    findings out. Returns a list of matched strings (empty = clean)."""
    with open(report_path, "r", encoding="utf-8") as f:
        raw = f.read()
    return sorted({f"{prefix}-{num}" for prefix, num in
                   re.findall(r"\b(BUG|CHANGE)-(\d+)\b", raw)})


def _is_surfaced(finding):
    """Mirrors report.py's own surfaced/cleared split: a finding is an
    actual reported regression if it's high-confidence, or if it was
    ambiguous and the LLM adjudicated it as a regression."""
    return finding["confidence"] == "high" or finding.get("verdict") == "regression"


def _checkout_unreachable(findings):
    for f in findings:
        if (f["category"] == "dom-missing" and f["page"] == "checkout"
                and "reachable" in f["description"].lower()):
            return True
    return False


def score_buggy_run(report_path, bugs):
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    findings = report["findings"]
    surfaced = [f for f in findings if _is_surfaced(f)]

    bug_hits, unmatched = match_findings_to_bugs(surfaced, bugs)

    checkout_blocked = _checkout_unreachable(surfaced)
    blocked_bug_ids = {b["id"] for b in bugs if checkout_blocked and "checkout" in b["page_types"]}

    total_bugs = len(bugs)
    hit_bug_ids = set(bug_hits.keys())
    reachable_bug_ids = {b["id"] for b in bugs} - blocked_bug_ids

    per_bug = []
    for bug in bugs:
        hits = bug_hits.get(bug["id"], [])
        per_bug.append({
            "id": bug["id"],
            "category": bug["category"],
            "description": bug["description"],
            "hit": len(hits) > 0,
            "multiplicity": len(hits),
            "blocked": bug["id"] in blocked_bug_ids,
            "matching_findings": hits,
        })

    return {
        "target": report["run"]["target_name"],
        "total_findings_reported": len(surfaced),
        "total_findings_raw": len(findings),
        "total_bugs": total_bugs,
        "bugs_hit": len(hit_bug_ids),
        "recall_all": len(hit_bug_ids) / total_bugs if total_bugs else 0.0,
        "reachable_bug_count": len(reachable_bug_ids),
        "bugs_hit_reachable": len(hit_bug_ids & reachable_bug_ids),
        "recall_reachable": (
            len(hit_bug_ids & reachable_bug_ids) / len(reachable_bug_ids)
            if reachable_bug_ids else 0.0
        ),
        "checkout_blocked": checkout_blocked,
        "blocked_bug_ids": sorted(blocked_bug_ids),
        "per_bug": per_bug,
        "unmatched": unmatched,
        "duplicates": [b for b in per_bug if b["multiplicity"] > 1],
    }


def score_clean_run(report_path):
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    findings = report["findings"]
    surfaced = [f for f in findings if _is_surfaced(f)]
    withheld = [f for f in findings if not _is_surfaced(f)]

    return {
        "target": report["run"]["target_name"],
        "false_positive_count": len(surfaced),
        "false_positives": surfaced,
        "correctly_withheld_count": len(withheld),
        "correctly_withheld": withheld,
    }


def render_buggy_markdown(score, leakage):
    lines = [
        f"# Scorecard - {score['target']} vs BUG_CATALOG.md",
        "",
    ]
    if leakage:
        lines += [
            f"**LEAKAGE WARNING: report.json contains catalog ID(s): {', '.join(leakage)}**",
            "The agent must never reference catalog IDs - investigate before trusting this run.",
            "",
        ]
    lines += [
        f"Findings reported (surfaced): {score['total_findings_reported']} "
        f"(raw findings incl. withheld: {score['total_findings_raw']})",
        "",
        f"**Recall over all {score['total_bugs']} catalogued bugs: "
        f"{score['bugs_hit']}/{score['total_bugs']} = {score['recall_all']:.0%}**",
        "",
        f"**Recall over the {score['reachable_bug_count']} reachable bugs "
        f"(excludes {len(score['blocked_bug_ids'])} blocked by BUG-13's missing checkout button): "
        f"{score['bugs_hit_reachable']}/{score['reachable_bug_count']} = {score['recall_reachable']:.0%}**",
        "",
    ]

    if score["blocked_bug_ids"]:
        lines.append(f"Blocked/unreachable bugs (checkout unreachable): {', '.join(score['blocked_bug_ids'])}")
        lines.append("")

    lines.append("## Per-bug results")
    lines.append("")
    lines.append("| Bug | Category | Status | Findings matched |")
    lines.append("|---|---|---|---|")
    for b in score["per_bug"]:
        if b["hit"]:
            status = f"HIT ({b['multiplicity']}x)" if b["multiplicity"] > 1 else "HIT"
        elif b["blocked"]:
            status = "MISS (unreachable)"
        else:
            status = "MISS"
        lines.append(f"| {b['id']} | {b['category']} | {status} | {b['multiplicity']} |")
    lines.append("")

    if score["duplicates"]:
        lines.append("## Duplicate hits (one bug, multiple findings)")
        lines.append("")
        for b in score["duplicates"]:
            lines.append(f"- **{b['id']}** matched by {b['multiplicity']} findings:")
            for f in b["matching_findings"]:
                lines.append(f"  - `{f['page']}`: {f['description']}")
        lines.append("")

    lines.append(f"## Unmatched findings (candidate false positives) - {len(score['unmatched'])}")
    lines.append("")
    lines.append(
        "These findings did not map to any catalog bug under strict "
        "category+page/product matching. Some may be real bugs missing "
        "from the catalog (see BUG-12's own history) - judge each on its "
        "merits, they are not assumed wrong."
    )
    lines.append("")
    for u in score["unmatched"]:
        f = u["finding"]
        near = f" (near-miss: {', '.join(u['near_miss_bug_ids'])})" if u["near_miss_bug_ids"] else ""
        lines.append(f"- **[{f['category']}] {f['page']}**: {f['description']}{near}")
    lines.append("")

    return "\n".join(lines)


def render_clean_markdown(score, leakage):
    lines = [
        f"# Scorecard - {score['target']} vs CHANGE_CATALOG.md",
        "",
    ]
    if leakage:
        lines += [
            f"**LEAKAGE WARNING: report.json contains catalog ID(s): {', '.join(leakage)}**",
            "",
        ]
    lines += [
        f"**False positives: {score['false_positive_count']}** "
        "(v1-clean is a clean build - every reported finding is a false positive by definition)",
        "",
        f"Correctly routed to adjudication and withheld (not flagged): "
        f"{score['correctly_withheld_count']}",
        "",
    ]

    if score["false_positives"]:
        lines.append("## False positives")
        lines.append("")
        for f in score["false_positives"]:
            lines.append(f"- **[{f['category']}] {f['page']}**: {f['description']}")
        lines.append("")

    if score["correctly_withheld"]:
        lines.append("## Correctly withheld (not counted as false positives)")
        lines.append("")
        for f in score["correctly_withheld"]:
            lines.append(f"- **{f['page']}**: {f['description']}")
            lines.append(f"  - verdict: {f.get('verdict')} — {f.get('reasoning', '')}")
        lines.append("")

    return "\n".join(lines)
