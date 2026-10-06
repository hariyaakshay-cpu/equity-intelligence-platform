"""Exceptions page: the corporate-action review-file panel (CORPORATE_ACTION_REVIEW category only).

The CSV is always a tmp_path file reached through stock_detail.review_csv_path (the one patch point);
the real data/reference file is never read. Runs are built per case by test_dashboard_exceptions_api helpers.
"""
import hashlib
import html
import json
import re

import pytest

from dashboard import stock_detail
from dashboard.app import create_app
from equity_intel.scanner.corporate_actions import load_corporate_action_review
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_exceptions_api import CATEGORY_ROWS, _run

HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"
CATEGORY = "category=CORPORATE_ACTION_REVIEW"


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _csv(monkeypatch, tmp_path, content):
    path = tmp_path / "review.csv"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: path)
    return path


def _page(client, query=CATEGORY):
    res = client.get("/equity/exceptions?" + query)
    return res, res.get_data(as_text=True)


def _panel(text):
    return text.split('id="review-file"')[1]


# ---------------------------------------------------------------- the three file states

def test_header_only_file_says_empty_never_zero_issues(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER)
    _run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])])  # nothing flagged
    res, text = _page(client)
    assert res.status_code == 200
    assert 'id="review-file-state">review file empty: no symbols reviewed</p>' in text
    for forbidden in ("0 issues", "no corporate actions", "no issues"):
        assert forbidden not in text.lower(), forbidden
    assert "no symbols with CORPORATE_ACTION_REVIEW in run r1 (2 evaluated)" in text  # the table's own zero wording
    assert "<table>" not in _panel(text) and "Flagged in this run: 0" in _panel(text)


def test_missing_or_invalid_file_is_unavailable_not_an_error(db, client, monkeypatch, tmp_path):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: tmp_path / "absent.csv")
    res, text = _page(client)
    assert res.status_code == 200 and "review file unavailable" in _panel(text) and "Traceback" not in text
    _csv(monkeypatch, tmp_path, "symbol,isin\nAAA,\n")  # required columns missing
    res, text = _page(client)
    assert res.status_code == 200 and "review file unavailable" in _panel(text) and "missing required column" in _panel(text)


def test_entries_are_listed_and_linked_only_for_symbols_in_the_run(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,face value split,akshay,UNREVIEWED\n"
                                         "AAA,,BONUS,2026-08-01,old bonus,akshay,RESOLVED\n"
                                         "NOTINRUN,,SPLIT,2026-09-11,x,akshay,UNREVIEWED\n")
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    panel = _panel(_page(client)[1])
    assert "entries in the file now: 3" in panel and "Flagged in this run: 1" in panel
    rows = {m.group(1): m.group(0) for m in re.finditer(r"<tr>\s*<td>(?:<a [^>]*>)?(\w+)(?:</a>)?</td>.*?</tr>", panel, re.S)}
    assert 'href="/equity/stock/DDD"' in rows["DDD"] and "<td>yes</td>\n        <td>yes</td>" in rows["DDD"]  # in run, flagged
    assert 'href="/equity/stock/AAA"' in rows["AAA"] and "<td>yes</td>\n        <td>no</td>" in rows["AAA"]    # in run, not flagged
    assert "href" not in rows["NOTINRUN"] and "<td>no</td>" in rows["NOTINRUN"] and "not recorded" in rows["NOTINRUN"]
    assert "face value split" in panel and "UNREVIEWED" in panel and "RESOLVED" in panel
    assert "no review action" in panel


def test_version_note_only_when_the_file_differs_from_the_version_the_run_used(db, client, monkeypatch, tmp_path):
    path = _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,r,akshay,UNREVIEWED\n")
    _run(db, "r-old", "2026-09-01T09:00:00", CATEGORY_ROWS, review="rv-OLD")
    assert 'id="review-version-note"' in _page(client)[1] and "CURRENT file" in _page(client)[1]
    _run(db, "r-new", "2026-09-02T09:00:00", CATEGORY_ROWS, review=load_corporate_action_review(path).version)
    assert 'id="review-version-note"' not in _page(client)[1]


# ---------------------------------------------------------------- consistency notes

def test_flagged_symbols_with_an_empty_file_are_called_out(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER)
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)  # DDD is flagged
    text = _page(client)[1]
    assert 'id="review-consistency-note">1 symbol(s) are flagged in run r1, but the current review file has no entries' in text
    assert "review file empty: no symbols reviewed" in text and "href=\"/equity/stock/DDD\"" in text


def test_entries_without_any_flagged_symbol_are_explained_by_the_flag_rule(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + "AAA,,BONUS,2026-08-01,old,akshay,RESOLVED\n")
    _run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])])
    note = html.unescape(_page(client)[1].split('id="review-consistency-note">')[1].split("</p>")[0])
    assert "the file has 1 entry, but no symbol is flagged in run r1" in note
    assert "not RESOLVED" in note and "inside the symbol's fetched window" in note


def test_consistent_state_has_no_consistency_note(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,r,akshay,UNREVIEWED\n")
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    assert 'id="review-consistency-note"' not in _page(client)[1]


# ---------------------------------------------------------------- scope, demo, safety

def test_panel_appears_only_on_the_corporate_action_review_category(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER)
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    assert 'id="review-file"' in _page(client)[1]
    for category in ("FAILED", "STALE", "INSUFFICIENT_HISTORY", "HISTORY_GAPS", "NON_EQ_SERIES", "PRICE_BREAK_DETECTED"):
        text = _page(client, f"category={category}")[1]
        assert 'id="review-file"' not in text and "review file empty" not in text, category
        assert client.get(f"/api/equity/exceptions?category={category}").get_json()["review_file"] is None


def test_the_review_file_is_not_read_for_other_categories(db, client, monkeypatch):
    def boom():
        raise AssertionError("review file read for a category that does not show it")
    monkeypatch.setattr(stock_detail, "review_csv_path", boom)
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    assert _page(client, "category=STALE")[0].status_code == 200


def test_demo_mode_does_not_read_the_real_review_file(db, monkeypatch):
    def boom():
        raise AssertionError("demo mode must not read the real review file")
    monkeypatch.setattr(stock_detail, "review_csv_path", boom)
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    res = create_app(demo=True, db_path=db).test_client().get("/equity/exceptions?" + CATEGORY)
    text = res.get_data(as_text=True)
    assert res.status_code == 200 and "review file is not read in demo mode (demo data is fabricated)" in text
    assert "DEMO DATA - NOT REAL" in text


def test_json_route_carries_the_same_panel(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,face value split,akshay,UNREVIEWED\n")
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    panel = client.get("/api/equity/exceptions?" + CATEGORY).get_json()["review_file"]
    assert panel["file_state"] == "has_entries" and panel["total_entries"] == 1 and panel["flagged_in_run"] == 1
    assert panel["entries"][0]["symbol"] == "DDD" and panel["entries"][0]["flagged_in_run"] is True
    assert panel["entries"][0]["stock_url"] == "/equity/stock/DDD"
    empty = _csv(monkeypatch, tmp_path, HEADER)
    assert client.get("/api/equity/exceptions?" + CATEGORY).get_json()["review_file"]["message"] == \
        "review file empty: no symbols reviewed"
    assert empty.exists()


def test_entry_fields_are_html_escaped(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + 'DDD,,SPLIT,2026-09-10,"<script>alert(1)</script>",<img src=x>,UNREVIEWED\n')
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client)[1]
    assert "<script>alert(1)" not in text and "<img src=x" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text and "&lt;img src=x&gt;" in text


def test_reading_the_panel_never_writes_the_csv_or_the_database(db, client, monkeypatch, tmp_path):
    csv_path = _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,r,akshay,UNREVIEWED\n")
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = (digest(csv_path), digest(db), sorted(p.name for p in tmp_path.iterdir()))
    for _ in range(2):
        assert _page(client)[0].status_code == 200
        assert client.get("/api/equity/exceptions?" + CATEGORY).status_code == 200
    assert (digest(csv_path), digest(db), sorted(p.name for p in tmp_path.iterdir())) == before


def test_panel_has_no_score_rank_signal_or_secret_text(db, client, monkeypatch, tmp_path):
    _csv(monkeypatch, tmp_path, HEADER + "DDD,,SPLIT,2026-09-10,r,akshay,UNREVIEWED\n")
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client)[1]
    for forbidden in (".env", "UPSTOX", "access_token", "Bearer"):
        assert forbidden not in text
    visible = re.sub(r"<[^>]+>", " ", _panel(text)).lower()
    assert not re.search(r"\b(score|rank|ranked|signal|buy|sell|target|confidence)\b", visible)
    keys = json.dumps(sorted(client.get("/api/equity/exceptions?" + CATEGORY).get_json()["review_file"])).lower()
    assert not re.search(r"score|rank|signal", keys)
