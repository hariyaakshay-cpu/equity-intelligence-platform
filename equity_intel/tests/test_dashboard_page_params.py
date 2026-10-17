"""/api/equity/candidates and /api/equity/scan-history: bad paging is a 400 naming the parameter, never silently reset."""
import pytest

from dashboard.app import create_app
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

URLS = ("/api/equity/candidates", "/api/equity/scan-history")


@pytest.fixture
def client(db):
    _make_run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    return create_app(demo=False, db_path=db).test_client()


@pytest.mark.parametrize("url", URLS)
@pytest.mark.parametrize("query,name", [
    ("page=abc", "page"), ("page=0", "page"), ("page=-1", "page"),
    ("page_size=abc", "page_size"), ("page_size=0", "page_size"), ("page_size=201", "page_size"),
    ("page_size=100000", "page_size")])
def test_bad_paging_is_a_400_naming_the_parameter(client, url, query, name):
    res = client.get(f"{url}?{query}")
    assert res.status_code == 400 and name in res.get_json()["error"]


@pytest.mark.parametrize("url", URLS)
def test_boundary_values_are_accepted(client, url):
    res = client.get(f"{url}?page=1&page_size=200")
    assert res.status_code == 200 and res.get_json()["page_size"] == 200


@pytest.mark.parametrize("url", URLS)
def test_no_paging_parameters_use_the_defaults(client, url):
    body = client.get(url).get_json()
    assert body["page"] == 1 and body["page_size"] == 25


@pytest.mark.parametrize("url", URLS)
def test_empty_values_fall_back_to_the_defaults(client, url):
    body = client.get(f"{url}?page=&page_size=").get_json()
    assert body["page"] == 1 and body["page_size"] == 25
