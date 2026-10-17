"""/api/equity/candidates: a bad numeric filter is a 400 that names the parameter, not Python's own message."""
import pytest

from dashboard.app import create_app
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

URL = "/api/equity/candidates"


@pytest.fixture
def client(db):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    return create_app(demo=False, db_path=db).test_client()


def test_garbage_value_names_the_parameter_and_not_pythons_message(client):
    res = client.get(f"{URL}?rsi_min=abc")
    error = res.get_json()["error"]
    assert res.status_code == 400
    assert "rsi_min" in error and "'abc'" in error and "could not convert" not in error


@pytest.mark.parametrize("query,name", [("dist_max=nan", "dist_max"), ("rvol_min=inf", "rvol_min")])
def test_non_finite_value_names_the_parameter(client, query, name):
    res = client.get(f"{URL}?{query}")
    assert res.status_code == 400 and name in res.get_json()["error"]


def test_valid_value_without_an_e4_scan_keeps_its_existing_message(client):
    # The fixture has no E4 scan, so a well-formed filter is refused for that reason, as before this change.
    res = client.get(f"{URL}?rsi_min=10")
    assert res.status_code == 400 and "COMPLETE E4 indicator scan" in res.get_json()["error"]


def test_empty_value_is_ignored(client):
    assert client.get(f"{URL}?rsi_min=").status_code == 200
