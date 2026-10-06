"""dashboard.review_file.read_review_file: the shared, read-only review-CSV reader (tmp_path files only)."""
from dashboard import review_file
from equity_intel.scanner.corporate_actions import load_corporate_action_review

HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"
ROW = "AAA,,SPLIT,2026-09-10,face value split,akshay,UNREVIEWED\n"


def test_header_only_file_is_empty_never_zero_issues(tmp_path):
    csv = tmp_path / "review.csv"
    csv.write_text(HEADER, encoding="utf-8")
    state = review_file.read_review_file(csv, None)
    assert state["file_state"] == "empty" and state["entries"] == []
    assert state["message"] == "review file empty: no symbols reviewed"
    assert "0 issues" not in state["message"] and "version_note" not in state


def test_missing_file_is_unavailable(tmp_path):
    state = review_file.read_review_file(tmp_path / "absent.csv", None)
    assert state["file_state"] == "unavailable" and state["message"].startswith("review file unavailable")
    assert state["entries"] == [] and "version_note" not in state


def test_entries_are_returned_unfiltered_with_no_message(tmp_path):
    csv = tmp_path / "review.csv"
    csv.write_text(HEADER + ROW + "BBB,,BONUS,2026-09-11,x,akshay,UNREVIEWED\n", encoding="utf-8")
    state = review_file.read_review_file(csv, None)
    assert state["file_state"] == "has_entries" and state["message"] is None
    assert [e.symbol for e in state["entries"]] == ["AAA", "BBB"]


def test_version_note_only_when_the_run_recorded_a_different_version(tmp_path):
    csv = tmp_path / "review.csv"
    csv.write_text(HEADER + ROW, encoding="utf-8")
    current = load_corporate_action_review(csv).version
    assert "version_note" not in review_file.read_review_file(csv, current)
    assert "version_note" not in review_file.read_review_file(csv, None)
    assert "CURRENT file" in review_file.read_review_file(csv, "0" * 64)["version_note"]
