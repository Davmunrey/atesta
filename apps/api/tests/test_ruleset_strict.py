"""The strict main ruleset (#261, owner decision 2026-11-23): up-to-date branches, no approvals."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_required_checks_run_on_an_up_to_date_branch_without_a_review_gate() -> None:
    ruleset = json.loads((ROOT / ".github" / "rulesets" / "main-branch.json").read_text())
    rule = next(r for r in ruleset["rules"] if r["type"] == "required_status_checks")
    assert rule["parameters"]["strict_required_status_checks_policy"] is True
    review = next(r for r in ruleset["rules"] if r["type"] == "pull_request")
    assert review["parameters"]["required_approving_review_count"] == 0  # owner: no review gate
