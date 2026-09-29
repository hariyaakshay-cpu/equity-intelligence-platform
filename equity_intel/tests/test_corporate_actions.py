"""Tests for equity_intel.scanner.corporate_actions."""
import pytest

from equity_intel.scanner.corporate_actions import (
    CorporateActionReviewCSVInvalidError,
    is_under_review,
    load_corporate_action_review,
)

_HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"


def _write_csv(path, rows):
    path.write_text(_HEADER + "".join(rows), encoding="utf-8")


def test_header_only_file_is_valid_and_empty(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, [])
    review = load_corporate_action_review(path)
    assert review.entries == []
    assert len(review.version) == 64  # sha256 hex digest


def test_loads_entries_with_all_fields(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["TCS,INE1,SPLIT,2026-06-15,1:2 split,akshay,PENDING\n"])
    review = load_corporate_action_review(path)
    assert len(review.entries) == 1
    entry = review.entries[0]
    assert entry.symbol == "TCS"
    assert entry.isin == "INE1"
    assert entry.event_type == "SPLIT"
    assert entry.effective_date == "2026-06-15"
    assert entry.reason == "1:2 split"
    assert entry.reviewer == "akshay"
    assert entry.review_state == "PENDING"


def test_missing_file_raises(tmp_path):
    with pytest.raises(CorporateActionReviewCSVInvalidError):
        load_corporate_action_review(tmp_path / "does_not_exist.csv")


def test_missing_required_column_raises(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text("symbol,isin,event_type,effective_date,reason,reviewer\n", encoding="utf-8")  # no review_state
    with pytest.raises(CorporateActionReviewCSVInvalidError):
        load_corporate_action_review(path)


def test_is_under_review_true_for_non_resolved_entry_inside_window(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["TCS,INE1,SPLIT,2026-06-15,note,akshay,PENDING\n"])
    review = load_corporate_action_review(path)
    assert is_under_review(review, "TCS", "2026-01-01", "2026-12-31") is True


def test_is_under_review_false_when_resolved(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["TCS,INE1,SPLIT,2026-06-15,note,akshay,RESOLVED\n"])
    review = load_corporate_action_review(path)
    assert is_under_review(review, "TCS", "2026-01-01", "2026-12-31") is False


def test_is_under_review_false_when_effective_date_outside_window(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["TCS,INE1,SPLIT,2027-06-15,note,akshay,PENDING\n"])
    review = load_corporate_action_review(path)
    assert is_under_review(review, "TCS", "2026-01-01", "2026-12-31") is False


def test_is_under_review_false_for_a_different_symbol(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["INFY,INE2,MERGER,2026-06-15,note,akshay,PENDING\n"])
    review = load_corporate_action_review(path)
    assert is_under_review(review, "TCS", "2026-01-01", "2026-12-31") is False


def test_is_under_review_boundary_dates_are_inclusive(tmp_path):
    path = tmp_path / "review.csv"
    _write_csv(path, ["TCS,INE1,SPLIT,2026-01-01,note,akshay,PENDING\n"])
    review = load_corporate_action_review(path)
    assert is_under_review(review, "TCS", "2026-01-01", "2026-12-31") is True
