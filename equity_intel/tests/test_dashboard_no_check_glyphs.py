"""No dashboard template shows a check mark, tick, cross or warning sign: state is written in words."""
import html
import re
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).resolve().parents[2] / "dashboard" / "templates").glob("*.html"))
# check marks and ballot marks (2713-2718), the white heavy check mark, ballot boxes, the cross mark and the warning sign
FORBIDDEN_CODEPOINTS = set(range(0x2713, 0x2719)) | {0x2705, 0x2611, 0x2612, 0x274C, 0x274E, 0x26A0}
FORBIDDEN_NAMES = ("&check;", "&checkmark;", "&cross;")


def _codepoints_in(text):
    found = set()
    for match in re.finditer(r"&#(x[0-9a-fA-F]+|[0-9]+);", text):
        digits = match.group(1)
        found.add(int(digits[1:], 16) if digits[0] in "xX" else int(digits))
    found |= {ord(c) for c in html.unescape(text)} | {ord(c) for c in text}
    return found & FORBIDDEN_CODEPOINTS


def test_the_templates_are_found():
    names = {t.name for t in TEMPLATES}
    assert {"stock_detail.html", "equity.html", "health_panel.html", "exceptions.html"} <= names


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.name)
def test_no_check_mark_entity_or_character_remains_in_any_dashboard_template(template):
    text = template.read_text(encoding="utf-8")
    assert _codepoints_in(text) == set(), template.name
    for name in FORBIDDEN_NAMES:
        assert name not in text, (template.name, name)


def test_the_detector_itself_finds_each_form():
    for sample in ("\u2713", "&#10003;", "&#x2713;", "&#X2717;", "\u26a0", "&#9888;", "&#10007;"):
        assert _codepoints_in(sample), sample
    assert _codepoints_in("&middot; &mdash; yes no &times;") == set()
