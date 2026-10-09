"""String-level checks on the JavaScript inside dashboard/templates/equity.html.

There is no JavaScript runtime in the test environment, so these tests read the template source. They show that the
old mixed-layer tile text is gone, that the new tile builders are pure (no DOM access) and name a layer in every
label, and that the page still fetches the same URLs. They do NOT show that the code runs: that is checked in a
real browser (see the commit report), and a syntax or runtime error in loadOverview would not fail these tests.
"""
import re
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "dashboard" / "templates" / "equity.html"
SOURCE = TEMPLATE.read_text(encoding="utf-8")
SCRIPT = re.search(r"<script>(.*?)</script>", SOURCE, re.S).group(1)

PURE_BUILDERS = ["tileHtml", "universeTiles", "warningTiles", "qualityKpiTiles", "warningGroups", "warningChipsHtml", "layerCountNote", "layerTag"]
DOM_ACCESS = ("document.", "window.", "fetch(", "innerHTML", "querySelector", "addEventListener", "getElementById", "createElement", "localStorage")
# the three Command Center tiles whose labels do not name their layer yet (the next commit labels them and shrinks this list)
PENDING_UNLABELLED_TILES = ["lg ? shareText(lg)", "hp ? hp.buckets[0].count", "run.latest_closed_session || '–'"]


def _function_body(name, source=SCRIPT):
    start = source.index(f"function {name}(")
    brace = source.index("{", source.index(")", start))
    depth = 0
    for i in range(brace, len(source)):
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[start:i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _kpi_calls(body):
    """The text after every `kpi(` in `body`, up to its matching closing parenthesis."""
    calls = []
    for match in re.finditer(r"\bkpi\(", body):
        depth, i = 1, match.end()
        while depth:
            depth += {"(": 1, ")": -1}.get(body[i], 0)
            i += 1
        calls.append(body[match.end():i - 1])
    return calls


# ---------------------------------------------------------------- the old text is gone

@pytest.mark.parametrize("old", [
    "'universe'", "'data health'", "data.outdated", "OUTDATED (approximate", "outdated-banner", "'symbols in run'", "'with a warning'", "'no warning'",
    "b ? b.symbols_with_features : run.requested_symbols", "dq.symbols_without_warning + ' / '", "<h3>Data health</h3>",
    "Object.entries(dq.warning_counts)", "dq.symbols_total", "dq.symbols_with_warnings", "dq.symbols_without_warning",
])
def test_the_old_mixed_layer_text_is_gone_from_the_script(old):
    assert old not in SCRIPT, old


def test_the_older_banner_note_is_gone_from_the_panel():
    assert "older OUTDATED banner" not in (TEMPLATE.parent / "health_panel.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- the new builders

@pytest.mark.parametrize("name", PURE_BUILDERS)
def test_each_tile_builder_is_a_pure_function_with_no_dom_access(name):
    body = _function_body(name)
    for forbidden in DOM_ACCESS:
        assert forbidden not in body, (name, forbidden)


@pytest.mark.parametrize("name", ["universeTiles", "warningTiles", "qualityKpiTiles"])
def test_every_tile_label_names_its_layer(name):
    labels = re.findall(r"label: '([^']*)'", _function_body(name))
    assert len(labels) >= 2 and all(label.startswith(("ScanRun: ", "E4: ")) for label in labels), labels
    assert any(label.startswith("ScanRun: ") for label in labels) and any(label.startswith("E4: ") for label in labels)


def test_the_tiles_never_add_the_two_layers_together():
    for name in ("universeTiles", "warningTiles", "qualityKpiTiles", "warningGroups", "warningChipsHtml", "layerCountNote"):
        body = _function_body(name)
        assert not re.search(r"scanrun\.[a-z_]+\s*\+\s*[a-z]\.[a-z_]+|\be\.[a-z_]+\s*\+\s*s\.[a-z_]+|\bs\.[a-z_]+\s*\+\s*e\.[a-z_]+", body), name


def test_an_absent_e4_layer_is_stated_in_words():
    for name in ("universeTiles", "warningTiles", "qualityKpiTiles"):
        assert "no COMPLETE E4 scan" in _function_body(name), name
    assert "no COMPLETE E4 scan" in _function_body("warningChipsHtml")


def test_the_wording_is_recorded_warning_not_health():
    for name in ("warningTiles", "qualityKpiTiles", "warningGroups", "layerCountNote"):
        body = _function_body(name).lower()
        assert "recorded warning" in body or "warnings by type" in body, name
        assert "health" not in body and not re.search(r"\bpass(ed|es)?\b", body), name
    assert "never added together" in _function_body("layerCountNote")


def test_dynamic_text_in_the_chip_and_warning_builders_is_escaped():
    for name in ("warningChipsHtml", "warningsHtml", "layerTag"):
        body = _function_body(name)
        assert "esc(" in body, name
    assert "esc(g.title)" in _function_body("warningChipsHtml") and "esc(k)" in SCRIPT


def test_the_command_center_builds_its_layer_tiles_with_the_builders():
    body = _function_body("loadOverview")
    for call in ("universeTiles(run, b, data.e4_scan)", "warningTiles(dq)", "warningChipsHtml(dq", "layerCountNote(dq)", "tileHtml"):
        assert call in body, call
    assert "qualityKpiTiles(dq)" in _function_body("renderQuality") and "warningChipsHtml(dq" in _function_body("renderQuality")


def test_the_only_tiles_still_built_with_kpi_in_the_command_center_are_the_three_pending_ones():
    calls = _kpi_calls(_function_body("loadOverview"))
    assert len(calls) == len(PENDING_UNLABELLED_TILES) == 3, calls
    for call, expected_start in zip(calls, PENDING_UNLABELLED_TILES):
        assert call.startswith(expected_start), (call[:60], expected_start)


def test_the_data_quality_tab_keeps_its_filter_chips_and_row_clicks():
    body = _function_body("renderQuality")
    assert "data-q" in body and "querySelectorAll('[data-q]')" in body and "tr[data-sym]" in body
    assert "<th>ScanRun status</th>" in body and "recorded warnings and reasons" in body


def test_a_warning_with_parts_shows_each_part_with_its_layer():
    body = _function_body("warningsHtml")
    assert "w.parts" in body and "layerTag(p.layer)" in body and "layerTag(w.layer)" in body


def test_the_quality_filter_finds_a_code_that_lives_in_a_warning_part():
    # the E4 break of a price-break warning is counted under e4_break, so the chip must find it there too
    helper = _function_body("warningHasCode")
    assert "w.code === code" in helper and "w.parts" in helper and "p.code === code" in helper
    for forbidden in DOM_ACCESS:
        assert forbidden not in helper
    body = _function_body("renderQuality")
    assert "warningHasCode(w, qualityFilter)" in body and "w.code === qualityFilter" not in body


# ---------------------------------------------------------------- what must not change

def test_the_page_fetches_exactly_the_urls_it_fetched_before():
    urls = re.findall(r"fetch\('([^']*)'", SCRIPT)
    assert len(urls) == 7 and set(urls) == {
        "/api/equity/summary", "/api/equity/sectors?run_id=", "/api/equity/candidates?", "/api/equity/stock/", "/api/equity/scan-history"}


def test_the_template_has_no_safe_filter_no_external_resource_and_no_health_fetch():
    assert "|safe" not in SOURCE and "autoescape" not in SOURCE.lower()
    assert not re.search(r"""(src|href)=["']https?://""", SOURCE) and "/api/equity/health" not in SOURCE
    assert re.search(r"<script>", SOURCE) and SOURCE.count("<script") == 1                   # still one inline script, none added
