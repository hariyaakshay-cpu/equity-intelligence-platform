"""Static price-basis boundary test.

Why this exists. Upstox daily candles are split/bonus-adjusted at FETCH time
(research/upstox_adjustment_basis_check_2026-10-03.md). Prices stored by one
acquisition run therefore share one adjustment basis, dated by
acquisition_runs.run_started_at; prices stored by two runs fetched either side
of an ex-date do not. The rule is written up in
docs/architecture/equity_intel_price_basis_rule.md.

What this test enforces, by parsing source with `ast` (the modules under test
are never imported, so a violation can have no import-time side effect): every
SQL string under equity_intel/ (outside tests/), dashboard/ and scripts/ that
READS (FROM or JOIN) acquired_observations or acquired_benchmark must filter on
run_id in the same string. INSERT statements are not reads and are not checked.
Docstrings and other bare string statements are ignored.

What it does NOT prove: that the run_id filter is the right one, SQL assembled
from several separate string pieces (a "+" or an f-string placeholder), or a
Python-side merge of rows that came from two runs. It is a tripwire, not a proof.
"""
import ast
import pathlib
import re

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
SCAN_ROOTS = (PACKAGE_ROOT, REPO_ROOT / "dashboard", REPO_ROOT / "scripts")

_READS_RUN_SCOPED_TABLE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:acquired_observations|acquired_benchmark)\b", re.IGNORECASE)
# "scan_run_id" does not match: there is no word boundary before "run_id" inside it.
_FILTERS_ON_RUN_ID = re.compile(r"\brun_id\s*(?:=|IN\b)", re.IGNORECASE)


def _sql_candidates(source: str, filename: str = "<source>"):
    """(lineno, text) of every string that could be SQL: string constants and
    f-strings (constant parts only). Bare string statements (docstrings) and the
    constant pieces that are already part of an f-string are not reported."""
    tree = ast.parse(source, filename=filename)
    skip = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            skip.add(id(node.value))
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                skip.add(id(part))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            text = "".join(p.value for p in node.values
                           if isinstance(p, ast.Constant) and isinstance(p.value, str))
            found.append((node.lineno, text))
    return found


def run_scoped_read_sites(source: str, filename: str = "<source>"):
    """Line numbers of SQL strings that read a run-scoped price table."""
    return [lineno for lineno, text in _sql_candidates(source, filename)
            if _READS_RUN_SCOPED_TABLE.search(text)]


def run_scoped_read_violations(source: str, filename: str = "<source>"):
    """Line numbers of those reads that do not filter on run_id."""
    return [lineno for lineno, text in _sql_candidates(source, filename)
            if _READS_RUN_SCOPED_TABLE.search(text) and not _FILTERS_ON_RUN_ID.search(text)]


def _iter_production_python_files():
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            yield path


def test_run_scoped_price_tables_are_only_read_with_a_run_id_filter():
    violations = []
    for path in _iter_production_python_files():
        for lineno in run_scoped_read_violations(path.read_text(encoding="utf-8"), str(path)):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert not violations, (
        "SQL reads acquired_observations / acquired_benchmark without a run_id filter "
        "(see docs/architecture/equity_intel_price_basis_rule.md): " + ", ".join(violations))


def test_the_guard_sees_the_existing_reads():
    # A guard that finds nothing would pass vacuously; the code is known to have several reads.
    sites = 0
    for path in _iter_production_python_files():
        sites += len(run_scoped_read_sites(path.read_text(encoding="utf-8"), str(path)))
    assert sites >= 5, f"expected at least 5 run-scoped reads in production code, found {sites}"


def test_detector_flags_a_read_without_run_id():
    src = 'q = "SELECT close FROM acquired_observations WHERE symbol = ?"\n'
    assert run_scoped_read_violations(src) == [1]


def test_detector_flags_a_join_without_run_id():
    src = 'q = "SELECT 1 FROM scan_results r JOIN acquired_benchmark b ON b.trading_date = r.d"\n'
    assert run_scoped_read_violations(src) == [1]


def test_detector_accepts_a_read_with_run_id():
    src = 'q = ("SELECT close FROM acquired_observations "\n     "WHERE run_id = ? AND symbol = ?")\n'
    assert run_scoped_read_violations(src) == []
    src_in = 'q = "SELECT close FROM acquired_benchmark WHERE run_id IN (?, ?)"\n'
    assert run_scoped_read_violations(src_in) == []


def test_detector_ignores_inserts_and_docstrings():
    src = ('"""Reads FROM acquired_observations without a filter (prose, not SQL)."""\n'
           'q = "INSERT OR REPLACE INTO acquired_observations(a) VALUES(?)"\n')
    assert run_scoped_read_violations(src) == []


def test_detector_handles_fstrings():
    bad = 'def f(t):\n    return f"SELECT close FROM acquired_observations WHERE symbol = {t}"\n'
    good = 'def f(t):\n    return f"SELECT close FROM acquired_observations WHERE run_id = ? AND symbol = {t}"\n'
    assert run_scoped_read_violations(bad) == [2]
    assert run_scoped_read_violations(good) == []


def test_detector_does_not_count_scan_run_id_as_a_run_id_filter():
    src = 'q = "SELECT 1 FROM acquired_observations o JOIN price_fetch_snapshots s ON s.scan_run_id = ?"\n'
    assert run_scoped_read_violations(src) == [1]
