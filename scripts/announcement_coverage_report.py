"""Announcement feasibility - Step 1b report: coverage and timestamp quality.

    python scripts/announcement_coverage_report.py research/announcements/coverage_<ts>

Reads the raw files and manifest written by announcement_coverage_fetch.py and
writes coverage_report.csv and timestamp_quality_report.md into the same
folder. No returns, no prices. Paper research only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from equity_intel.announcements.event_study import load_announcements  # noqa: E402

GAP_FLAG_SEC = 3600


def block(obj, **kw) -> str:
    """Plain-text table in a code fence (no tabulate dependency)."""
    return "```\n" + obj.to_string(**kw) + "\n```"


def bucket(ts) -> str:
    m = ts.hour * 60 + ts.minute
    return "pre_0915" if m < 555 else ("market_0915_1530" if m <= 930 else "after_1530")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("coverage_dir", type=Path)
    args = ap.parse_args()
    d = args.coverage_dir

    man = pd.read_csv(d / "manifest.csv")
    ann = load_announcements(d / "raw")
    ann["year"] = ann["event_ts"].dt.year
    ann["has_dissem"] = ann["exchdisstime"].notna()
    ann["has_seconds"] = ann["an_dt"].dt.second != 0
    ann["gap_sec"] = (ann["exchdisstime"] - ann["an_dt"]).dt.total_seconds()
    ann["bucket"] = ann["event_ts"].map(bucket)

    man["year"] = pd.to_datetime(man["day"]).dt.year
    man["failed"] = (man["http_status"] != 200) | man["error"].notna()
    per_day = man.groupby("year").agg(days_requested=("day", "size"),
                                      days_failed=("failed", "sum"),
                                      days_zero=("n_records", lambda s: int((s == 0).sum())))
    per_year = ann.groupby("year").agg(
        announcements=("symbol", "size"), symbols=("symbol", "nunique"),
        pct_dissem=("has_dissem", "mean"), pct_seconds=("has_seconds", "mean"),
        gaps_over_1h=("gap_sec", lambda s: int((s.abs() > GAP_FLAG_SEC).sum())),
        median_gap_sec=("gap_sec", "median"))
    split = pd.crosstab(ann["year"], ann["bucket"], normalize="index")
    report = per_day.join(per_year, how="outer").join(split, how="outer")
    report.to_csv(d / "coverage_report.csv")

    gaps = ann[ann["gap_sec"].abs() > GAP_FLAG_SEC].sort_values("gap_sec", key=abs,
                                                                 ascending=False)
    cats = ann["category"].value_counts()
    lines = [
        f"# Announcement coverage and timestamp quality - {d.name}", "",
        f"- Days requested: {len(man)}; failed: {int(man['failed'].sum())}; "
        f"returned 0 records: {int((man['n_records'] == 0).sum())}",
        f"- Announcements (deduplicated): {len(ann)}; symbols: {ann['symbol'].nunique()}",
        f"- With dissemination time: {ann['has_dissem'].mean():.1%}; "
        f"gaps over 1 hour: {len(gaps)}",
        f"- Time of day: " + ", ".join(f"{k} {v:.1%}" for k, v in
                                       ann["bucket"].value_counts(normalize=True).items()),
        "", "## Per year", "", block(report.round(3)), "",
        "## Largest dissemination gaps (top 20)", "",
        gaps.head(20)[["symbol", "category", "an_dt", "exchdisstime", "gap_sec"]]
        .pipe(block, index=False) if len(gaps) else "None.", "",
        "## Categories (top 40)", "", block(cats.head(40)), "",
        "## Failed or empty days", "",
        man[man["failed"] | (man["n_records"] == 0)][
            ["day", "http_status", "n_records", "error"]].pipe(block, index=False), ""]
    (d / "timestamp_quality_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:7]))
    print(f"\nWrote {d / 'coverage_report.csv'} and timestamp_quality_report.md")


if __name__ == "__main__":
    main()
