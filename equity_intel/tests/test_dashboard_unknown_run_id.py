"""/api/equity/candidates and /api/equity/sectors: an unknown run_id is a 404, not an empty 200.

Databases are tmp_path files. A missing run_id still resolves to the latest COMPLETE run, and a database with no
runs still returns the existing empty 200.
"""
import pytest

from dashboard.app import create_app
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

CANDIDATES = "/api/equity/candidates"
SECTORS = "/api/equity/sectors"


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def test_candidates_with_unknown_run_id_is_404(db, client):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    res = client.get(f"{CANDIDATES}?run_id=nope")
    assert res.status_code == 404 and "'nope'" in res.get_json()["error"]


def test_sectors_with_unknown_run_id_is_404(db, client):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    res = client.get(f"{SECTORS}?run_id=nope")
    assert res.status_code == 404 and "'nope'" in res.get_json()["error"]


def test_a_real_run_id_still_returns_200(db, client):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    for url in (CANDIDATES, SECTORS):
        res = client.get(f"{url}?run_id=r1")
        assert res.status_code == 200 and res.get_json()["run_id"] == "r1"


def test_no_run_id_still_uses_the_latest_complete_run(db, client):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    for url in (CANDIDATES, SECTORS):
        res = client.get(url)
        assert res.status_code == 200 and res.get_json()["run_id"] == "r1"


def test_database_with_no_runs_still_returns_the_empty_200(client):
    for url in (CANDIDATES, SECTORS):
        res = client.get(url)
        assert res.status_code == 200 and res.get_json()["run_id"] is None
