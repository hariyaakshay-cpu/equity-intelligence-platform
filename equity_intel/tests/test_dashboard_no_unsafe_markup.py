"""The dashboard never switches off HTML escaping: no `|safe` filter in a template and no Markup( in code.

Everything echoed into a page (query values, entry text, company names) relies on Jinja's autoescape.
"""
import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"
SAFE_FILTER = re.compile(r"\|\s*safe\b")
MARKUP_CALL = re.compile(r"\bMarkup\s*\(")
ESCAPING_OFF = re.compile(r"\{%-?\s*autoescape\s+(false|off)\b|render_template_string", re.I)


def _files(pattern):
    return sorted(p for p in DASHBOARD.rglob(pattern) if "__pycache__" not in p.parts)


def test_the_scan_actually_covers_the_dashboard_files():
    # A minimum plus named files, never an exact count: later phases add templates and modules.
    templates = {p.name for p in _files("*.html")}
    modules = {p.name for p in _files("*.py")}
    assert len(templates) >= 1 and len(modules) >= 1
    assert {"exceptions.html", "stock_detail.html", "base.html"} <= templates
    assert {"app.py", "queries.py", "exceptions.py"} <= modules


def test_no_dashboard_template_uses_the_safe_filter():
    offenders = [f"{p.name}:{n}" for p in _files("*.html")
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if SAFE_FILTER.search(line)]
    assert offenders == []


def test_no_dashboard_code_calls_markup():
    offenders = [f"{p.name}:{n}" for p in _files("*.py")
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if MARKUP_CALL.search(line)]
    assert offenders == []


def test_no_template_turns_autoescape_off_and_no_code_renders_a_string_template():
    offenders = [f"{p.name}:{n}" for pattern in ("*.html", "*.py") for p in _files(pattern)
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if ESCAPING_OFF.search(line)]
    assert offenders == []


def test_the_patterns_do_catch_what_they_are_meant_to_catch():
    assert SAFE_FILTER.search("{{ x|safe }}") and SAFE_FILTER.search("{{ x | safe }}")
    assert not SAFE_FILTER.search("{{ x|length }}") and not SAFE_FILTER.search("unsafe_value")
    assert MARKUP_CALL.search("return Markup(text)") and MARKUP_CALL.search("Markup (x)")
    assert not MARKUP_CALL.search("a_Markup_name") and not MARKUP_CALL.search("# markup is not used")
