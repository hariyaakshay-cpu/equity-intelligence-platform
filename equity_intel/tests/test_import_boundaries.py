"""Static import-boundary tests.

These tests never import the forbidden modules themselves (importing them
would defeat the point, and some of them have import-time side effects per
conftest.py's own warnings). Instead they statically parse every .py file
under equity_intel/ with the `ast` module and inspect the import statements
textually -- an architectural safety test, not a trading test.

FORBIDDEN_PREFIXES is imported from equity_intel.scanner.execution_guard
rather than defined here, so the static check in this file and the runtime
check in execution_guard.py can never drift apart.
"""
import ast
import pathlib

from equity_intel.scanner.execution_guard import FORBIDDEN_PREFIXES

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Frozen expectation for FORBIDDEN_PREFIXES: written out explicitly so that
# shrinking or otherwise weakening the canonical tuple requires deliberately
# editing this test, not just an incidental change elsewhere.
EXPECTED_FORBIDDEN_PREFIXES = (
    "brokers",
    "core.paper_engine",
    "core.continuous_engine",
    "core.execution_engine",
    "core.oms",
    "core.risk_manager",
    "strategies",
    "main",
    "core.historical_data",
)

# This repo's own data-layer packages, which are NOT trading infrastructure
# and must remain importable even as FORBIDDEN_PREFIXES evolves.
ALLOWED_CORE_PREFIXES = (
    "core.providers",
    "core.database",
    "core.models",
)


def _iter_python_files():
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        yield path


def _imported_module_names(path: pathlib.Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def test_forbidden_prefixes_equals_the_explicitly_written_out_expected_set():
    assert FORBIDDEN_PREFIXES == EXPECTED_FORBIDDEN_PREFIXES


def test_no_equity_intel_module_imports_a_forbidden_trading_module():
    violations = []
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            for forbidden in FORBIDDEN_PREFIXES:
                if name == forbidden or name.startswith(forbidden + "."):
                    violations.append((str(path.relative_to(PACKAGE_ROOT.parent)), name))
    assert violations == [], f"forbidden imports found: {violations}"


def test_no_core_oms_import_exists_anywhere_with_no_exception():
    oms_imports = []
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            if name == "core.oms" or name.startswith("core.oms."):
                oms_imports.append((str(path.relative_to(PACKAGE_ROOT.parent)), name))
    assert oms_imports == [], f"core.oms import found (no exception permitted): {oms_imports}"


def test_core_providers_database_and_models_are_not_treated_as_forbidden():
    for allowed in ALLOWED_CORE_PREFIXES:
        for forbidden in FORBIDDEN_PREFIXES:
            assert not (allowed == forbidden or allowed.startswith(forbidden + ".")), (
                f"{allowed} unexpectedly matches forbidden prefix {forbidden!r}"
            )


def test_no_equity_intel_module_imports_main_module_by_star_or_direct_name():
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            assert name != "main", str(path)
