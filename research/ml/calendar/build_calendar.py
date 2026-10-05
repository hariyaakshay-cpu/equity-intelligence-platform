"""Build and validate the verified NSE equity trading calendar (spec 5A.1).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Inputs (all under research/ml/calendar/, fetched by fetch_sources.py):
    sources/nse_holiday_master/trading_<year>.json   primary: exchange holidays
    resolutions.csv                                   primary: special sessions and
                                                      exceptions, each citing NSE circulars
    vendor_gaps.csv                                   vendor-side gaps: the calendar is
                                                      right and the vendor series is not
    sources/vendor_bars/*.json                        cross-check only
Outputs:
    nse_equity_calendar_v1.csv    one row per calendar day in the span
    calendar_manifest_v1.json     version, span, counts, input and output hashes
    validation_report_v1.md       vendor cross-check; the build fails if any
                                  discrepancy is unresolved

Rules:
1. Start from every weekday in the span.
2. Holiday-master CM entries on weekdays close the day, except entries marked
   as sessions ("*" Muhurat, "Special Live Trading", "Union Budget").
   Weekend entries change nothing unless marked as sessions.
3. resolutions.csv overrides 1-2 and sets the session type; every row cites
   at least one circular.
4. Every date where a vendor instrument disagrees with the result must be
   explained by a resolutions.csv row (calendar exception) or a vendor_gaps.csv
   row (vendor series wrong, with evidence); otherwise the build stops.

Run from anywhere:  python research/ml/calendar/build_calendar.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources"
VERSION = "nse-equity-calendar-v1"
SPAN = (date(2011, 1, 1), date(2026, 10, 2))
SESSION_MARKERS = ("*", "Special Live Trading", "Union Budget", "Dhanteras Trading")
VENDOR_FILES = ("nifty500", "nifty50", "reliance")
OUT_CSV = HERE / "nse_equity_calendar_v1.csv"
OUT_MANIFEST = HERE / "calendar_manifest_v1.json"
OUT_REPORT = HERE / "validation_report_v1.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_holiday_master():
    entries = {}
    for year in range(SPAN[0].year, SPAN[1].year + 1):
        data = json.loads((SRC / f"nse_holiday_master/trading_{year}.json").read_text(encoding="utf-8"))
        if not data.get("CM"):
            raise SystemExit(f"holiday master {year}: no CM entries")
        for row in data["CM"]:
            day = datetime.strptime(row["tradingDate"], "%d-%b-%Y").date()
            entries[day] = row["description"].strip()
    return entries


def load_resolutions():
    with open(HERE / "resolutions.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for row in rows:
        day = date.fromisoformat(row["date"])
        if day in out:
            raise SystemExit(f"duplicate resolution for {day}")
        if row["status"] not in ("SESSION", "CLOSED") or not row["circulars"].strip():
            raise SystemExit(f"resolution {day}: bad status or no circular")
        out[day] = row
    return out


def build():
    hm = load_holiday_master()
    res = load_resolutions()
    rows = {}
    day = SPAN[0]
    while day <= SPAN[1]:
        desc = hm.get(day)
        marked = bool(desc) and any(m in desc for m in SESSION_MARKERS)
        if day.weekday() < 5:
            session = not desc or marked
        else:
            session = marked
        row = {
            "date": day.isoformat(),
            "weekday": day.strftime("%a"),
            "is_session": session,
            "session_type": "REGULAR" if session else "",
            "closure_reason": "" if session else (desc or "weekend"),
            "holiday_master": desc or "",
            "source": "nse_holiday_master" if desc else "weekday_rule",
        }
        if day in res:
            r = res[day]
            row["is_session"] = r["status"] == "SESSION"
            row["session_type"] = r["session_type"] if row["is_session"] else ""
            row["closure_reason"] = "" if row["is_session"] else r["note"]
            row["source"] = "resolution:" + r["circulars"]
        rows[day] = row
        day += timedelta(days=1)
    return rows, hm, res


def load_vendor_gaps():
    with open(HERE / "vendor_gaps.csv", newline="", encoding="utf-8") as fh:
        return {(date.fromisoformat(r["date"]), r["instrument"]): r for r in csv.DictReader(fh)}


def validate(rows, res, gaps):
    vendor = {
        name: {date.fromisoformat(d) for d in json.loads((SRC / f"vendor_bars/{name}.json").read_text())["dates"]}
        for name in VENDOR_FILES
    }
    sessions = {d for d, r in rows.items() if r["is_session"]}
    findings, unresolved = [], []
    for name, bars in vendor.items():
        bars = {d for d in bars if SPAN[0] <= d <= SPAN[1]}
        for d in sorted(bars - sessions):
            findings.append((d, name, "vendor bar on a closed day"))
        for d in sorted(sessions - bars):
            findings.append((d, name, "session without vendor bar"))
    for d, name, what in findings:
        if d not in res and (d, name) not in gaps:
            unresolved.append((d, name, what))
    return vendor, findings, unresolved


def main():
    rows, hm, res = build()
    gaps = load_vendor_gaps()
    vendor, findings, unresolved = validate(rows, res, gaps)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(next(iter(rows.values())).keys()), lineterminator="\n")
        w.writeheader()
        for d in sorted(rows):
            w.writerow({**rows[d], "is_session": int(rows[d]["is_session"])})

    sessions = [r for r in rows.values() if r["is_session"]]
    types = Counter(r["session_type"] for r in sessions)
    per_year = Counter(r["date"][:4] for r in sessions)
    vendor_cover = {
        n: {"bars_in_span": len([d for d in b if SPAN[0] <= d <= SPAN[1]]),
            "sessions_without_bar": len([r for r in sessions if date.fromisoformat(r["date"]) not in b])}
        for n, b in vendor.items()
    }
    inputs = sorted(
        [p for p in SRC.rglob("*") if p.is_file() and p.name != "fetch_log.json"]
        + [HERE / "resolutions.csv", HERE / "vendor_gaps.csv"])
    manifest = {
        "calendar_version": VERSION,
        "label": "RESEARCH ONLY — NOT A TRADING RECOMMENDATION",
        "status": "VALIDATED" if not unresolved else "FAILED",
        "span": [SPAN[0].isoformat(), SPAN[1].isoformat()],
        "segment": "NSE equity cash market (CM)",
        "built_at": datetime.now(UTC).isoformat(),
        "sessions": len(sessions),
        "session_types": dict(types),
        "sessions_per_year": dict(sorted(per_year.items())),
        "resolutions": len(res),
        "vendor_gaps": len(gaps),
        "vendor_cross_check": vendor_cover,
        "discrepancies_found": len(findings),
        "discrepancies_unresolved": len(unresolved),
        "output_sha256": sha256(OUT_CSV),
        "input_sha256": {p.relative_to(HERE).as_posix(): sha256(p) for p in inputs},
        "known_limits": [
            "Span starts 2011-01-01: the NSE holiday-master API returns no data before 2011.",
            "Span ends 2026-10-02 (last verified day); later days need a new version.",
            "Muhurat sessions are short evening sessions; they are sessions here, typed MUHURAT.",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# {VERSION} — validation report",
        "",
        "RESEARCH ONLY — NOT A TRADING RECOMMENDATION.",
        "",
        f"Status: **{manifest['status']}**. Span {SPAN[0]} to {SPAN[1]}, NSE equity cash market.",
        f"Sessions: {len(sessions)} ({', '.join(f'{k} {v}' for k, v in sorted(types.items()))}).",
        f"Output: `{OUT_CSV.name}` sha256 `{manifest['output_sha256']}`.",
        "",
        "## Vendor cross-check",
        "",
        "| Instrument | Bars in span | Sessions without a bar |",
        "|---|---|---|",
    ]
    for n, c in vendor_cover.items():
        lines.append(f"| {n} | {c['bars_in_span']} | {c['sessions_without_bar']} |")
    lines += ["", f"Discrepancies found: {len(findings)}; unresolved: {len(unresolved)}.", "",
              "| Date | Instrument | Finding | Resolution |", "|---|---|---|---|"]
    for d, name, what in findings:
        r, g = res.get(d), gaps.get((d, name))
        if r:
            text = f"{r['status']} {r['session_type']} — {r['circulars']}: {r['note']}"
        elif g:
            text = f"VENDOR GAP — {g['evidence']}"
        else:
            text = "**UNRESOLVED**"
        lines.append(f"| {d} | {name} | {what} | {text} |")
    lines += ["", "## Resolutions (all exceptions to the holiday master)", "",
              "| Date | Status | Type | Circulars | Note |", "|---|---|---|---|---|"]
    for d in sorted(res):
        r = res[d]
        lines.append(f"| {d} | {r['status']} | {r['session_type']} | {r['circulars']} | {r['note']} |")
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({k: manifest[k] for k in ("status", "sessions", "session_types",
                      "discrepancies_found", "discrepancies_unresolved")}, indent=1))
    if unresolved:
        for u in unresolved:
            print("UNRESOLVED", *u)
        sys.exit(1)


if __name__ == "__main__":
    main()
