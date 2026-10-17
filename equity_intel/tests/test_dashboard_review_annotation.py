"""Snapshot Audit: the facts-only review-file annotation (pages and JSON).

The CSV is always a tmp_path file reached through stock_detail.review_csv_path (the one patch point); the real
data/reference file is never read. Databases are tmp_path files. The window is the half-open range
(older run's started_at date, newer run's started_at date], both from scan_runs (ScanRun layer).
"""
import html
import re
from pathlib import Path

import pytest

from dashboard import stock_detail
from dashboard.app import create_app
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars, _three_runs
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"
SENTENCE = "listed in the review file; this page does not say it explains any difference"
PAGE = "/equity/snapshot-audit"
SYMBOL_PAGE = "/equity/snapshot-audit/symbol/AAA"
API = "/api/equity/snapshot-audit"
FORBIDDEN = ("because", "due to", "caused", "result of", "explained by", "0 issues", "no issues")


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _csv(monkeypatch, tmp_path, *rows, header=HEADER):
    path = tmp_path / "review.csv"
    path.write_text(header + "".join(rows), encoding="utf-8")
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: path)
    return path


def _row(symbol, event_type, date, state="PENDING"):
    return f"{symbol},INE000A00000,{event_type},{date},recorded text,rev,{state}\n"


def _text(markup):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _block(markup):
    match = re.search(r'<div class="card" id="review-annotation">(.*?)\n</div>', markup, re.S)
    return match.group(1) if match else None


def _api(client, query="base=r1&other=r3"):
    res = client.get(f"{API}?{query}")
    assert res.status_code == 200
    return res.get_json()


# ---------------------------------------------------------------- inside / outside the window

def test_entry_inside_the_window_is_shown_with_all_five_facts_and_the_exact_sentence(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"))
    body = _api(client)["review_annotation"]
    assert body["sentence"] == SENTENCE and body["layer"] == "ScanRun"
    assert body["rows"] == [{"symbol": "AAA", "event_type": "SPLIT", "effective_date": "2026-09-02"}]
    assert (body["older_started_at"], body["newer_started_at"]) == ("2026-09-01T09:00:00", "2026-09-03T09:00:00")
    res = client.get(f"{PAGE}?base=r1&other=r3")
    block = _text(_block(res.get_data(as_text=True)))
    for fact in ("AAA", "SPLIT", "2026-09-02", "2026-09-01T09:00:00", "2026-09-03T09:00:00", SENTENCE):
        assert fact in block


def test_the_page_and_json_state_the_half_open_window(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"))
    note = ("window: effective_date after the older run's start date and on or before the newer run's start date "
            "(both from scan_runs.started_at)")
    assert _api(client)["review_annotation"]["window_note"] == note
    assert note in _text(_block(client.get(f"{PAGE}?base=r1&other=r3").get_data(as_text=True)))
    assert note in _text(_block(client.get(f"{SYMBOL_PAGE}?base=r1&other=r3").get_data(as_text=True)))


def test_entries_outside_the_window_show_nothing(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-08-31"), _row("AAA", "BONUS", "2026-09-04"))
    assert _api(client)["review_annotation"] is None
    assert _block(client.get(f"{PAGE}?base=r1&other=r3").get_data(as_text=True)) is None


def test_window_is_half_open_older_date_excluded_newer_date_included(db, client, monkeypatch, tmp_path):
    _three_runs(db)  # r2 starts 2026-09-02, r3 starts 2026-09-03
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"), _row("BBB", "BONUS", "2026-09-03"))
    rows = _api(client, "base=r2&other=r3")["review_annotation"]["rows"]
    assert [(r["symbol"], r["effective_date"]) for r in rows] == [("BBB", "2026-09-03")]


def test_all_review_states_are_listed_including_resolved(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02", "RESOLVED"), _row("BBB", "BONUS", "2026-09-03", "PENDING"))
    assert len(_api(client)["review_annotation"]["rows"]) == 2


# ---------------------------------------------------------------- file states

def test_header_only_file_shows_nothing_and_never_says_zero_issues(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path)
    assert _api(client)["review_annotation"] is None
    page = client.get(f"{PAGE}?base=r1&other=r3").get_data(as_text=True)
    assert _block(page) is None and "0 issues" not in page and "review-annotation" not in page


def test_invalid_file_shows_nothing_and_does_not_crash(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, header="symbol,isin\n")
    assert _api(client)["review_annotation"] is None
    assert client.get(f"{PAGE}?base=r1&other=r3").status_code == 200
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: Path(tmp_path / "missing.csv"))
    assert _api(client)["review_annotation"] is None
    assert client.get(f"{PAGE}?base=r1&other=r3").status_code == 200


def test_unparseable_effective_date_is_skipped_and_counted_not_guessed(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "not-a-date"), _row("BBB", "BONUS", "2026-09-02"))
    body = _api(client)["review_annotation"]
    assert [r["symbol"] for r in body["rows"]] == ["BBB"] and body["skipped_unparseable"] == 1


# ---------------------------------------------------------------- scope

def test_swapped_base_and_other_use_the_older_and_newer_run_start_dates(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"))
    body = _api(client, "base=r3&other=r1")["review_annotation"]
    assert (body["older_started_at"], body["newer_started_at"]) == ("2026-09-01T09:00:00", "2026-09-03T09:00:00")
    assert len(body["rows"]) == 1


def test_drilldown_shows_only_entries_for_its_own_symbol(db, client, monkeypatch, tmp_path):
    for n in (1, 2, 3):
        _make_run(db, f"r{n}", f"2026-09-0{n}T09:00:00",
                  [("AAA", "VALID", _bars(revised_on=n if n > 1 else None)), ("BBB", "VALID", _bars())])
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"), _row("BBB", "BONUS", "2026-09-02"))
    api = client.get(f"/api/equity/snapshot-audit/symbol/AAA?base=r1&other=r3").get_json()["review_annotation"]
    assert [r["symbol"] for r in api["rows"]] == ["AAA"]
    page = client.get(f"{SYMBOL_PAGE}?base=r1&other=r3").get_data(as_text=True)
    block = _text(_block(page))
    assert "SPLIT" in block and "BONUS" not in block and SENTENCE in block
    client_page = client.get(f"/equity/snapshot-audit/symbol/BBB?base=r1&other=r3").get_data(as_text=True)
    assert "BONUS" in _text(_block(client_page)) and "SPLIT" not in _text(_block(client_page))


def test_drilldown_for_a_symbol_without_entries_shows_nothing(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("ZZZ", "SPLIT", "2026-09-02"))
    page = client.get(f"{SYMBOL_PAGE}?base=r1&other=r3").get_data(as_text=True)
    assert _block(page) is None


# ---------------------------------------------------------------- wording, demo, boundaries

def test_annotation_makes_no_causal_claim(db, client, monkeypatch, tmp_path):
    _three_runs(db)
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"))
    block = _text(_block(client.get(f"{PAGE}?base=r1&other=r3").get_data(as_text=True))).lower()
    block = block.replace(SENTENCE, "")
    for word in FORBIDDEN + ("explain",):
        assert word not in block, word


def test_demo_mode_never_reads_the_real_file(db, monkeypatch, tmp_path):
    _three_runs(db)

    def boom():
        raise AssertionError("the review file must not be read in demo mode")

    monkeypatch.setattr(stock_detail, "review_csv_path", boom)
    demo = create_app(demo=True, db_path=db).test_client()
    res = demo.get(f"{API}?base=r1&other=r3")
    assert res.status_code == 200 and res.get_json()["review_annotation"] is None
    assert demo.get(f"{PAGE}?base=r1&other=r3").status_code == 200


def test_no_comparison_available_has_no_annotation(db, client, monkeypatch, tmp_path):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _csv(monkeypatch, tmp_path, _row("AAA", "SPLIT", "2026-09-02"))
    body = client.get(API).get_json()
    assert body["comparison_available"] is False and body["review_annotation"] is None


def test_module_has_no_sqlite_import():
    source = (Path(__file__).resolve().parents[2] / "dashboard" / "review_annotation.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import sqlite3|from sqlite3)", source, re.M)
