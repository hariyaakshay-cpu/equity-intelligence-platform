"""Extract Nifty 500 inclusions and exclusions from the saved press releases (spec 5A.2).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Reads  sources/press_releases/pdf/*.pdf  (see fetch_sources.py), converts each with
`pdftotext -raw`, and keeps only the section that concerns the Nifty 500 itself
(titled "Nifty 500", "NIFTY 500 Index", "S&P CNX 500", "CNX 500", and nothing
else: "Nifty500 Shariah", "Nifty500 Multicap ..." and similar are different indices).

Writes  nifty500_events.csv  with one row per company per action:
    file, release_date, effective_date, action (INCLUDE|EXCLUDE), symbol, name
and  parse_report.json  listing files with a Nifty 500 section, files whose
section yielded no rows, and rows whose symbol could not be read.

Some releases (revocations, corrections) instead use one table with the columns
Index Name | Security Name | Symbol | Remarks. Its "Nifty 500" rows are read too; a remark
"Exclusion revoked" or "Inclusion revoked" becomes action CANCEL_EXCLUDE / CANCEL_INCLUDE.

Nothing is guessed: a row without a readable symbol is reported, not repaired.

Run from anywhere:  python research/ml/survivorship/parse_press_releases.py
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDFS = HERE / "sources" / "press_releases" / "pdf"
OUT_CSV = HERE / "nifty500_events.csv"
OUT_REPORT = HERE / "parse_report.json"

HEADER = re.compile(r"^\s*(?:\d{1,2}|[A-Za-z])[\.\)]\s*(?:S&P\s+)?(?:CNX\s+|NIFTY\s*)500(?:\s+Index)?\s*:?\s*$", re.I)
ANY_HEADER = re.compile(r"^\s*(?:\d{1,2}|[A-Za-z])[\.\)]\s+\S")
EFFECTIVE = re.compile(
    r"(?:effective\s+from|w\.?e\.?f\.?|with\s+effect\s+from)[:\s]+(?:\w+day,?\s+)?([A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\.?,?\s+\d{4})",
    re.I)
ROW = re.compile(r"^(\d{1,3})\s+(.+?)\s+([A-Z0-9][A-Z0-9&\-]*)\s*$")
REMARK_ROW = re.compile(r"^(?:(.+?)\s+)?([A-Z0-9][A-Z0-9&\-]*)\s+(Inclusion|Exclusion)(\s+revoked)?\*{0,2}\s*$", re.I)
INDEX_ROW = re.compile(r"^(?:\d{1,2}\s+)?(?:S&P\s+)?(?:CNX\s+|NIFTY\s*)500(?:\s+Index)?\s*$", re.I)
NEXT_INDEX = re.compile(r"^\d{1,2}\s+\S")
ACTION = re.compile(r"\b(?:being|are|is)\s+(excluded|included)\b|\b(excluded|included)\s*:?\s*$|following.*?(excluded|included)", re.I)


def parse_date(text: str):
    t = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text).replace(",", " ").replace(".", " ")
    t = re.sub(r"\s+", " ", t).strip()
    for fmt in ("%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def release_date(name: str):
    m = re.search(r"ind_prs(\d{2})(\d{2})(\d{4})", name)
    return datetime(int(m[3]), int(m[2]), int(m[1])).date() if m else None


def pdf_text(path: Path) -> str:
    return subprocess.run(["pdftotext", "-raw", str(path), "-"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def nifty500_sections(lines):
    """Yield the lines of each Nifty 500 section, up to the next numbered index heading."""
    i = 0
    while i < len(lines):
        if HEADER.match(lines[i]):
            j = i + 1
            while j < len(lines) and not (ANY_HEADER.match(lines[j]) and not HEADER.match(lines[j])):
                j += 1
            yield lines[i + 1:j]
            i = j
        else:
            i += 1


def rows_of(section):
    action, pending = None, None
    for line in section:
        s = line.strip()
        m = ACTION.search(s)
        if m and not ROW.match(s):
            action = (m.group(1) or m.group(2) or m.group(3)).lower()
            pending = None
            continue
        if action is None:
            continue
        r = ROW.match(s)
        if r and not r.group(3).isdigit() and not re.search(r"\b(Ltd|Limited|Co|Corp|Company|Inc|India)\.?$", r.group(3)):
            yield action, r.group(3), r.group(2).strip()
            pending = None
        elif re.match(r"^\d{1,3}\s+\S", s):
            yield action, None, s
    return


def remark_rows(lines):
    """Rows of the Nifty 500 entry in an Index Name | Security Name | Symbol | Remarks table."""
    if not any(re.search(r"Index Name.*Remarks|Remarks", l) and "Symbol" in l for l in lines):
        return
    inside = False
    for line in lines:
        s = line.strip()
        if INDEX_ROW.match(s):
            inside = True
            continue
        if inside and NEXT_INDEX.match(s) and not REMARK_ROW.match(s):
            inside = False
        m = REMARK_ROW.match(s) if inside else None
        if m:
            kind = m.group(3).upper().replace("INCLUSION", "INCLUDE").replace("EXCLUSION", "EXCLUDE")
            yield ("CANCEL_" + kind if m.group(4) else kind), m.group(2), (m.group(1) or "").strip()


def main():
    events, report = [], {"files_with_section": 0, "no_rows": [], "unreadable_rows": [], "no_effective_date": []}
    for pdf in sorted(PDFS.glob("*.pdf")):
        text = pdf_text(pdf)
        lines = [l for l in text.splitlines() if l.strip()]
        sections = list(nifty500_sections(lines))
        table = list(remark_rows(lines))
        if not sections and not table:
            continue
        report["files_with_section"] += 1
        flat = " ".join(lines[:40])
        # a release may cite an earlier date before stating its own ("shall become effective from ..."),
        # so the last effective-date phrase in the opening lines is the one that applies
        ems = list(EFFECTIVE.finditer(flat)) or list(EFFECTIVE.finditer(" ".join(lines)))[:1]
        eff = parse_date(ems[-1].group(1)) if ems else None
        if eff is None:
            report["no_effective_date"].append(pdf.name)
        n = 0
        for sec in sections:
            for action, symbol, name in rows_of(sec):
                if symbol is None:
                    report["unreadable_rows"].append({"file": pdf.name, "row": name})
                    continue
                n += 1
                events.append({"file": pdf.name, "release_date": release_date(pdf.name),
                               "effective_date": eff, "action": "INCLUDE" if action == "included" else "EXCLUDE",
                               "symbol": symbol, "name": name})
        for action, symbol, name in table:
            n += 1
            events.append({"file": pdf.name, "release_date": release_date(pdf.name), "effective_date": eff,
                           "action": action, "symbol": symbol, "name": name})
        if n == 0:
            report["no_rows"].append(pdf.name)
    events.sort(key=lambda e: (e["effective_date"] or e["release_date"], e["file"], e["action"], e["symbol"]))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "release_date", "effective_date", "action", "symbol", "name"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(events)
    report["rows"] = len(events)
    OUT_REPORT.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})


if __name__ == "__main__":
    main()
