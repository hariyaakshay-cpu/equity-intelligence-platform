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

PURE_BUILDERS = ["tileHtml", "universeTiles", "warningTiles", "qualityKpiTiles", "warningGroups", "warningChipsHtml", "layerCountNote", "layerTag",
                 "indicatorTiles", "sessionTile", "symbolQualityGroups", "symbolQualityHtml", "explorerHeads", "warningHasCode"]
TILE_BUILDERS = ["universeTiles", "warningTiles", "qualityKpiTiles", "indicatorTiles", "sessionTile"]
DOM_ACCESS = ("document.", "window.", "fetch(", "innerHTML", "querySelector", "addEventListener", "getElementById", "createElement", "localStorage")
# a check mark, tick, cross or warning sign in any form: the page states things in words, per layer
GLYPHS = ("\u2713", "\u2714", "\u2705", "\u2611", "\u2717", "\u2718", "\u274c", "\u274e", "\u26a0", "&#10003;", "&#10004;", "&#10007;", "&#9888;", "&check;", "&cross;")


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
    "'above EMA (no E4 scan)'", "<h3>Last run</h3>", "const tick", "tick(", "no price break detected",
    "possible price break (see below)", "[['symbol', 'symbol', false], ",
])
def test_the_old_mixed_layer_text_is_gone_from_the_script(old):
    assert old not in SCRIPT, old


@pytest.mark.parametrize("old", ["'latest closed session'", "<div>universe</div>", "const lg = b ?", "'52-week high', hp ?", "lg ? shareText(lg) : '\u2013'"])
def test_the_old_tile_and_card_text_is_gone_from_the_command_center(old):
    assert old not in _function_body("loadOverview"), old


def test_the_older_banner_note_is_gone_from_the_panel():
    assert "older OUTDATED banner" not in (TEMPLATE.parent / "health_panel.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- the new builders

@pytest.mark.parametrize("name", PURE_BUILDERS)
def test_each_tile_builder_is_a_pure_function_with_no_dom_access(name):
    body = _function_body(name)
    for forbidden in DOM_ACCESS:
        assert forbidden not in body, (name, forbidden)


@pytest.mark.parametrize("name", TILE_BUILDERS)
def test_every_tile_label_names_its_layer(name):
    labels = re.findall(r"label: '([^']*)'", _function_body(name))
    assert labels and all(label.startswith(("ScanRun: ", "E4: ")) for label in labels), labels


def test_the_tile_builders_cover_both_layers_and_the_expected_layer_owns_each_tile():
    layer_of = {name: {label.split(":")[0] for label in re.findall(r"label: '([^']*)'", _function_body(name))} for name in TILE_BUILDERS}
    assert layer_of == {"universeTiles": {"ScanRun", "E4"}, "warningTiles": {"ScanRun", "E4"}, "qualityKpiTiles": {"ScanRun", "E4"},
                        "indicatorTiles": {"E4"}, "sessionTile": {"ScanRun"}}


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


def test_every_command_center_tile_comes_from_a_labelled_builder_and_none_is_built_by_hand():
    body = _function_body("loadOverview")
    assert _kpi_calls(body) == []                                                           # no direct kpi( call is left: nothing can be unlabelled
    for call in ("universeTiles(run, b, data.e4_scan)", "warningTiles(dq)", "indicatorTiles(b)", "tileHtml(sessionTile(run))"):
        assert call in body, call
    # outside the kpi() definition, tileHtml and the X-Ray tab (not changed by this commit) no kpi( call exists anywhere in the script
    rest = SCRIPT
    for name in ("kpi", "tileHtml", "renderXray"):
        rest = rest.replace(_function_body(name), "")
    assert _kpi_calls(rest) == []
    assert _kpi_calls(_function_body("tileHtml")) == ["t.value, t.label, t.sub"]
    assert len(_kpi_calls(_function_body("renderXray"))) == 4                              # the X-Ray tab keeps its own tiles, unchanged


def test_the_last_run_card_is_labelled_scanrun():
    body = _function_body("loadOverview")
    assert "<h3>ScanRun: latest COMPLETE run</h3>" in body and "<div>universe version</div>" in body


# ---------------------------------------------------------------- no glyphs, per-layer words, Explorer layer tags

@pytest.mark.parametrize("glyph", GLYPHS)
def test_no_check_mark_tick_cross_or_warning_glyph_anywhere_in_the_page(glyph):
    assert glyph not in SOURCE, repr(glyph)


def test_the_stock_tab_data_quality_list_is_words_per_layer():
    groups_src = _function_body("symbolQualityGroups")
    assert "layer: 'ScanRun'" in groups_src and "layer: 'E4'" in groups_src
    assert "no COMPLETE E4 scan" in groups_src and "no quality row for this symbol" in groups_src and "session counts not recorded" in groups_src
    for glyph in GLYPHS:
        assert glyph not in groups_src and glyph not in _function_body("symbolQualityHtml")
    html = _function_body("symbolQualityHtml")
    assert "layerTag(g.layer)" in html and "esc(t)" in html
    body = _function_body("loadDetails")
    assert "symbolQualityHtml(symbolQualityGroups(r, q, !!data.e4_features, !!data.e4_scan, dq))" in body and "class=\"up\"" not in body.split("Data quality")[1][:300]


def test_the_stock_tab_states_each_fact_as_recorded_or_not_recorded_never_as_a_pass():
    groups_src = _function_body("symbolQualityGroups")
    for phrase in ("history gaps recorded", "no history gaps recorded", "price-break flag set", "price-break flag not set",
                   "listed in the corporate-action review file", "a break is recorded", "no break recorded"):
        assert phrase in groups_src, phrase
    assert not re.search(r"\b(pass|passed|ok|good|clean|healthy|safe)\b", groups_src.lower())


def test_every_explorer_column_header_carries_a_layer_tag():
    heads = _function_body("explorerHeads")
    scan, e4 = heads.split(".concat(", 1)
    assert [m for m in re.findall(r"'(ScanRun|E4)'\]", scan)] == ["ScanRun"] * 5
    assert re.findall(r"'(ScanRun|E4)'\]", e4) and set(re.findall(r"'(ScanRun|E4)'\]", e4)) == {"E4"}
    render = _function_body("renderCandidatesTable")
    assert "explorerHeads(e4)" in render and "([k, label, isNum, layer])" in render and "el('div', {class: 'hp-layer'}, [layer])" in render
    assert "[['symbol', 'symbol', false]" not in render


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
