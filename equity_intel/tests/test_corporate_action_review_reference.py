"""The manual corporate-action review CSV must always exist on disk, per
docs/architecture/equity_intel_scanner_v1_spec.md, Section 7: a run that
cannot read it ends ABORTED rather than silently treating "no file" the
same as "no entries". This test only proves the file itself is present and
correctly shaped -- it does not exercise scanner behavior (no scanner code
exists yet; that lands in Phase 2).
"""
import csv
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPORATE_ACTION_REVIEW_CSV = REPO_ROOT / "data" / "reference" / "corporate_action_review.csv"

EXPECTED_HEADER = ["symbol", "isin", "event_type", "effective_date", "reason", "reviewer", "review_state"]


def test_corporate_action_review_csv_exists():
    assert CORPORATE_ACTION_REVIEW_CSV.exists(), (
        f"{CORPORATE_ACTION_REVIEW_CSV} must always exist (header-only is allowed "
        "when there are no entries) -- its absence must abort a scan run, not be "
        "silently treated as an empty review list"
    )


def test_corporate_action_review_csv_has_the_frozen_header():
    with CORPORATE_ACTION_REVIEW_CSV.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == EXPECTED_HEADER
