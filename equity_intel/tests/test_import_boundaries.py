"""Static import-boundary tests.

These tests never import the forbidden modules themselves (importing them
would defeat the point, and some of them have import-time side effects per
conftest.py's own warnings). Instead they statically parse every .py file
under equity_intel/ with the `ast` module and inspect the import statements
textually -- an architectural safety test, not a trading test.
"""
import ast
import pathlib

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN_PREFIXES = (
    "brokers",
    "core.paper_engine",
    "core.continuous_engine",
    "core.execution_engine",
    "core.oms.order_router",
    "core.oms.execution_service",
    "core.oms.paper_oms_adapter",
    "core.oms.db",
    "core.risk_manager",
    "strategies",
    "main",
    "core.historical_data",
)

# The single explicitly authorized exception (B1 freeze-policy exception row).
ALLOWED_OMS_IMPORT = "core.oms.execution_mode"


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


def test_no_equity_intel_module_imports_a_forbidden_trading_module():
    violations = []
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            for forbidden in FORBIDDEN_PREFIXES:
                if name == forbidden or name.startswith(forbidden + "."):
                    violations.append((str(path.relative_to(PACKAGE_ROOT.parent)), name))
    assert violations == [], f"forbidden imports found: {violations}"


def test_the_only_core_oms_import_anywhere_is_the_authorized_execution_mode_module():
    oms_imports = []
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            if name == "core.oms" or name.startswith("core.oms."):
                oms_imports.append((str(path.relative_to(PACKAGE_ROOT.parent)), name))
    for _, name in oms_imports:
        assert name == ALLOWED_OMS_IMPORT, name
    # And it must appear at least once, exactly where expected.
    assert any(name == ALLOWED_OMS_IMPORT for _, name in oms_imports)


def test_no_equity_intel_module_imports_main_module_by_star_or_direct_name():
    for path in _iter_python_files():
        for name in _imported_module_names(path):
            assert name != "main", str(path)
