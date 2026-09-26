"""Static database-connection boundary test.

Like equity_intel/tests/test_import_boundaries.py, this proves properties
by parsing source with `ast` -- never by importing the modules under test,
so a violation can never have an import-time side effect.

Rules, by module location:

- Any module under equity_intel/, except tests/ and the one reserved,
  not-yet-created path equity_intel/persistence/connection.py, may NOT
  import sqlite3 in any form (plain, aliased, from-import, aliased
  from-import). This is an import-level ban, not a call-based one: the
  earlier draft flagged any ".connect(...)" attribute call regardless of
  what object it was called on, which would false-flag an unrelated
  ".connect()" method on some other object entirely. An import-level ban
  has no such false positive, and persistence work belongs solely in
  persistence/connection.py once that module exists (out of scope until
  B2/B3 resolve; see equity_intel/persistence/repositories.py). This test
  is written so that path is the only one that will ever be allowed to
  import sqlite3 outside tests/.
- sqlalchemy (in any form: plain import, aliased import, any from-import)
  is banned everywhere under equity_intel/, tests included.
- core.database (this repo's own, unrelated ORM package -- see
  docs/architecture/equity_intel_boundary_decision.md) is likewise banned
  everywhere under equity_intel/.
- Inside tests/, sqlite3 may be imported freely, but any call actually
  bound to sqlite3's connect() (tracked through real import aliases, not
  by attribute-name-only matching) must pass exactly one argument, the
  literal string ":memory:". A test's unrelated ".connect()" call on some
  other object is never flagged, because only calls resolved back to an
  sqlite3 import in the same file are inspected.
"""
import ast
import pathlib

import pytest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The only module path ever allowed to import sqlite3 outside tests/.
# It does not exist yet; when it is created, it must be named exactly this.
ALLOWED_CONNECTION_MODULE = PACKAGE_ROOT / "persistence" / "connection.py"

FORBIDDEN_IMPORT_PREFIXES = ("core.database", "sqlalchemy")


def _iter_all_python_files():
    yield from PACKAGE_ROOT.rglob("*.py")


def _is_test_file(path: pathlib.Path) -> bool:
    return "tests" in path.parts


def _imported_module_names_from_tree(tree: ast.AST):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _imported_module_names(path: pathlib.Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    return _imported_module_names_from_tree(tree)


def _imports_sqlite3(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "sqlite3" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                return True
    return False


def _imports_sqlalchemy(tree: ast.AST) -> bool:
    for name in _imported_module_names_from_tree(tree):
        if name == "sqlalchemy" or name.startswith("sqlalchemy."):
            return True
    return False


def _sqlite3_bound_names(tree: ast.AST):
    """Local names in this file that are actually bound to sqlite3: the
    module itself (however aliased) and any names imported directly from
    it (however aliased)."""
    module_aliases = set()
    from_import_map = {}  # local name -> original name imported from sqlite3
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                for alias in node.names:
                    from_import_map[alias.asname or alias.name] = alias.name
    return module_aliases, from_import_map


def _find_sqlite3_connect_calls(tree: ast.AST):
    """Yield only Call nodes actually resolved back to sqlite3's connect,
    via real import tracking -- never by matching the attribute name
    ".connect" against an arbitrary, unrelated object."""
    module_aliases, from_import_map = _sqlite3_bound_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "connect"
            and isinstance(func.value, ast.Name)
            and func.value.id in module_aliases
        ):
            yield node
        elif (
            isinstance(func, ast.Name)
            and func.id in from_import_map
            and from_import_map[func.id] == "connect"
        ):
            yield node


def _violations_for_module(path: pathlib.Path, tree: ast.AST):
    violations = []
    is_test = _is_test_file(path)
    is_allowed_connection_module = path == ALLOWED_CONNECTION_MODULE

    if _imports_sqlalchemy(tree):
        violations.append("sqlalchemy import")

    if not is_test and not is_allowed_connection_module and _imports_sqlite3(tree):
        violations.append("sqlite3 import outside persistence/connection.py")

    if is_test:
        for call in _find_sqlite3_connect_calls(tree):
            ok = (
                len(call.args) == 1
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == ":memory:"
            )
            if not ok:
                violations.append("non-':memory:' sqlite3.connect call")

    return violations


def _snippet_is_flagged(source: str, path: pathlib.Path) -> bool:
    """Used only by the self-test below, to exercise the detection logic
    directly against in-memory source, never against a real file."""
    tree = ast.parse(source)
    return bool(_violations_for_module(path, tree))


def test_only_persistence_connection_module_may_import_sqlite3():
    violations = []
    for path in _iter_all_python_files():
        if _is_test_file(path) or path == ALLOWED_CONNECTION_MODULE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        if _imports_sqlite3(tree):
            violations.append(str(path.relative_to(PACKAGE_ROOT.parent)))
    assert violations == [], f"sqlite3 imported outside persistence/connection.py: {violations}"


def test_tests_only_call_sqlite3_connect_with_the_memory_literal():
    violations = []
    for path in _iter_all_python_files():
        if not _is_test_file(path):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for call in _find_sqlite3_connect_calls(tree):
            ok = (
                len(call.args) == 1
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == ":memory:"
            )
            if not ok:
                violations.append(str(path.relative_to(PACKAGE_ROOT.parent)))
    assert violations == [], f"forbidden test sqlite3.connect call(s) found: {violations}"


def test_no_equity_intel_module_imports_core_database_or_sqlalchemy():
    violations = []
    for path in _iter_all_python_files():
        for name in _imported_module_names(path):
            for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                if name == forbidden or name.startswith(forbidden + "."):
                    violations.append((str(path.relative_to(PACKAGE_ROOT.parent)), name))
    assert violations == [], f"forbidden import(s) found: {violations}"


_FAKE_NON_TEST_PATH = PACKAGE_ROOT / "features" / "fake_module_for_self_test.py"


@pytest.mark.parametrize(
    "label, source",
    [
        ("plain_import", "import sqlite3\n"),
        ("aliased_import", "import sqlite3 as x\n"),
        ("from_import_aliased", "from sqlite3 import connect as db_connect\n"),
        ("sqlalchemy_import", "import sqlalchemy\n"),
        ("sqlalchemy_from_import_create_engine", "from sqlalchemy import create_engine\n"),
    ],
)
def test_detection_flags_each_known_form_outside_the_connection_module(label, source):
    assert _snippet_is_flagged(source, _FAKE_NON_TEST_PATH), f"{label} should have been flagged: {source!r}"


def test_detection_allows_sqlite3_import_inside_the_connection_module():
    source = "import sqlite3\n"
    assert not _snippet_is_flagged(source, ALLOWED_CONNECTION_MODULE)


def test_detection_does_not_flag_a_clean_snippet():
    clean_source = "x = 1\ndef f():\n    return x + 1\n"
    assert not _snippet_is_flagged(clean_source, _FAKE_NON_TEST_PATH)


_FAKE_TEST_PATH = PACKAGE_ROOT / "tests" / "fake_test_for_self_test.py"


@pytest.mark.parametrize(
    "label, source, expect_flagged",
    [
        ("aliased_module_call_wrong_arg", 'import sqlite3 as s\ns.connect("x.db")\n', True),
        ("aliased_from_import_call_wrong_arg", 'from sqlite3 import connect as c\nc("x.db")\n', True),
        ("plain_call_memory_literal", 'import sqlite3\nsqlite3.connect(":memory:")\n', False),
        ("unrelated_object_connect_call_no_sqlite3_import", 'sock.connect("x")\n', False),
    ],
)
def test_detection_in_test_files_tracks_real_sqlite3_aliases(label, source, expect_flagged):
    assert _snippet_is_flagged(source, _FAKE_TEST_PATH) == expect_flagged, label
