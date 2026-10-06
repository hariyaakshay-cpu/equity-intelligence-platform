"""Build the survivorship audit (spec 5A.2) from the reconstruction and the vendor first bars.

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Reads   reconstruct_membership.reconstruct()              membership, anomalies
        ../calendar/nse_equity_calendar_v1.csv            verified sessions (spec 5A.1)
        sources/vendor_first_bars.json                    first/last Upstox bar per current constituent
        sources/vendor_removed_names.json                 (optional) the same for names that left the index
        <db> (optional, read-only)                        the stored one-year window, for item 1 on current data
Writes  survivorship_audit_v1.json   every figure in the report, with input hashes
        survivorship_by_symbol.csv   per current constituent: first bar, membership evidence counts
        survivorship_by_year.csv     candidate samples by evidence class and year
        survivorship_audit_v1.md     the report

Definitions (all fixed here, none tuned to a result):
  candidate sample (s, t)   s a current constituent, t a calendar session with
                            first_bar(s) <= t <= min(last_bar(s), D1). Bars are assumed present on
                            every session in that range; holes are a data-quality matter (spec 5).
  drift(t)                  size of the reconstructed set in force at t, minus the snapshot size.
                            Excess size means missed inclusions (names wrongly kept as members), so
                            it indicates how far the reconstruction can be trusted at t. It is
                            stored per date (survivorship_drift_by_date.csv) and per year; no
                            cutoff is applied. Choosing one is a decision for the reviewer.
  anomaly window            for each failed check on a current constituent s at date d: [d, next
                            event of s). Membership of s in that window is not established.
  MEMBER_RECONSTRUCTED      s in the reconstructed set at t, no anomaly window covers (s, t).
  NOT_MEMBER_RECONSTRUCTED  s not in the reconstructed set at t, no anomaly window: the sample uses a
                            name that was not in the index then (look-ahead universe).
  UNCERTAIN_CHAIN           an anomaly window covers (s, t).
  Every class is read together with drift(t); none is called evidence by this script.
Run (from the repository root that holds data/):  python <path>/build_audit.py [--db data/equity_intel.db]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import reconstruct_membership as rm
from render_report import render_report

HERE = Path(__file__).resolve().parent
CALENDAR = HERE.parent / "calendar" / "nse_equity_calendar_v1.csv"
FIRST_BARS = HERE / "sources" / "vendor_sample90.json"     # the approved 90-symbol sample (vendor_sample90.py)
REMOVED = FIRST_BARS                                         # its "removed" block: 30 names that left the index
D1 = date(2026, 9, 29)            # last session before the next announced change (2026-09-30)
W1 = (date(2025, 9, 23), D1)      # the one-year window stored today (spec section 2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 2) if b else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/equity_intel.db")
    args = ap.parse_args()

    snap, intervals, anomalies, timeline, after, undated, cancelled, event_dates = rm.reconstruct()
    sessions = [r["date"] for r in csv.DictReader(CALENDAR.open(encoding="utf-8")) if r["is_session"] == "1"]
    sessions = [date.fromisoformat(d) for d in sessions if date.fromisoformat(d) <= D1]
    D0 = sessions[0]
    fb = json.loads(FIRST_BARS.read_text(encoding="utf-8"))["symbols"]
    vendor_errors = sorted(s for s, v in fb.items() if v["error"] or not v["first_bar"])

    # drift: set size in force over each state, minus the snapshot size. timeline[k] = (event date d_k,
    # files, size just before d_k), newest first; that size holds on [d_{k+1}, d_k).
    target = len(snap)
    drift_states = [(timeline[k + 1][0] if k + 1 < len(timeline) else date.min, timeline[k][2] - target)
                    for k in range(1, len(timeline))]
    if len(timeline) > 1:
        drift_states.append((timeline[1][0], 0))           # the state after the newest event is the snapshot
    drift_states.sort()

    def drift_at(t: date) -> int:
        cur = 0
        for start, dr in drift_states:
            if start <= t:
                cur = dr
        return cur

    anomaly_symbols = {s for _, _, s, _ in anomalies}
    windows = defaultdict(list)                            # current constituent -> [(start, end_exclusive)]
    for d, _, s, _ in anomalies:
        if s in snap:
            nxt = [e for e in event_dates[s] if e > d]
            windows[s].append((d, nxt[0] if nxt else date.max))
    critical = [d for d, _, s, kind in anomalies if s in snap]

    def member(s: str, t: date) -> bool:
        return any((a is None or a <= t) and t < b for a, b in intervals.get(s, ()))

    # ---- item 1: entrants (first bar inside a window)
    first = {s: date.fromisoformat(v["first_bar"]) for s, v in fb.items() if v["first_bar"]}
    entrants_w2 = sorted((first[s], s) for s in first if first[s] > D0)
    entrants_w1 = sorted((first[s], s) for s in first if first[s] > W1[0])
    entrants_by_year = Counter(d.year for d, _ in entrants_w2)

    # ---- items 2-3: candidate samples by evidence class
    classes = ("MEMBER_RECONSTRUCTED", "NOT_MEMBER_RECONSTRUCTED", "UNCERTAIN_CHAIN")
    by_year: dict[int, Counter] = defaultdict(Counter)
    by_year_w1: Counter = Counter()
    drift_by_year: dict[int, list[int]] = defaultdict(list)
    for t in sessions:
        drift_by_year[t.year].append(drift_at(t))
    per_symbol = {}
    for s in sorted(snap & set(first) - set(vendor_errors)):
        lo, hi = first[s], min(date.fromisoformat(fb[s]["last_bar"]), D1)
        c = Counter()
        for t in sessions:
            if t < lo or t > hi:
                continue
            if any(a <= t < b for a, b in windows.get(s, ())):
                cls = "UNCERTAIN_CHAIN"
            else:
                cls = "MEMBER_RECONSTRUCTED" if member(s, t) else "NOT_MEMBER_RECONSTRUCTED"
            c[cls] += 1
            by_year[t.year][cls] += 1
            if W1[0] <= t <= W1[1]:
                by_year_w1[cls] += 1
        per_symbol[s] = {"first_bar": lo.isoformat(), **{k: c[k] for k in classes},
                         "touched_by_anomaly": int(s in anomaly_symbols)}
    total = Counter()
    for y in by_year.values():
        total.update(y)
    n_all = sum(total.values())

    # symbols without evidence of full-period membership
    def full_period(s: str, lo: date, hi: date) -> bool:
        return all(member(s, t) and not any(a <= t < b for a, b in windows.get(s, ()))
                   for t in sessions if lo <= t <= hi)

    no_full_w1 = sorted(s for s in per_symbol if not full_period(s, *W1))
    no_full_w2 = sorted(s for s in per_symbol if not full_period(s, D0, D1))

    # members at t that are not in today's universe (the other side of survivorship)
    missing_by_year = {}
    for y in range(D0.year, D1.year + 1):
        ts = [t for t in sessions if t.year == y]
        sample = ts[:: max(1, len(ts) // 12)]              # about monthly
        tot = absent = 0
        for t in sample:
            members = {s for s, iv in intervals.items() if any((a is None or a <= t) and t < b for a, b in iv)}
            tot += len(members)
            absent += len(members - snap)
        missing_by_year[y] = {"sessions_sampled": len(sample), "mean_members": round(tot / len(sample), 1),
                              "mean_not_in_universe": round(absent / len(sample), 1), "share_pct": pct(absent, tot)}

    # ---- cross-check: an index entry cannot precede the stock's first bar (demerger spin-offs excepted)
    early = sorted((a.isoformat(), s, first[s].isoformat()) for s in per_symbol for a, _ in
                   ((x, y) for x, y in intervals.get(s, ()) if x is not None) if a < first[s])

    # ---- item 4: vendor history for names that left the index
    removed = None
    if REMOVED.exists():
        rv = json.loads(REMOVED.read_text(encoding="utf-8"))
        rem = rv["removed"]
        served = [s for s, v in rem.items() if v["first_bar"] and not v["error"]]
        removed = {"sampled": len(rem), "unresolved_in_master": len(rv["removed_unresolved"]),
                   "served_history": len(served), "errors": sorted(s for s, v in rem.items() if v["error"]),
                   "unresolved_symbols": rv["removed_unresolved"],
                   "last_bar_before_2026-09-01": sorted(s for s in served if rem[s]["last_bar"] < "2026-09-01"),
                   "sample_calls": rv["calls"], "stopped": rv["stopped"]}

    # ---- stored one-year window (item 1 on current data)
    stored = None
    if Path(args.db).exists():
        con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        run = con.execute("select run_id from acquisition_runs where status='COMPLETE' "
                          "order by run_started_at desc limit 1").fetchone()[0]
        rows = con.execute("select status, count(*) from symbol_acquisition_results where run_id=? "
                           "group by 1", (run,)).fetchall()
        short = con.execute("select symbol, first_date, observation_count from symbol_acquisition_results "
                            "where run_id=? and status='INSUFFICIENT_HISTORY' order by first_date", (run,)).fetchall()
        stored = {"run_id": run, "status_counts": dict(rows), "insufficient_history": short}

    result = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": {"snapshot_sha256": sha256(rm.SNAPSHOT), "events_sha256": sha256(rm.EVENTS),
                   "aliases_sha256": sha256(rm.ALIASES), "calendar_sha256": sha256(CALENDAR),
                   "vendor_first_bars_sha256": sha256(FIRST_BARS),
                   "press_release_fetch_log_sha256": sha256(HERE / "sources" / "fetch_log.json")},
        "windows": {"D0_calendar_start": D0.isoformat(), "D1": D1.isoformat(), "W1": [d.isoformat() for d in W1]},
        "drift_by_year": {y: {"mean": round(sum(v) / len(v), 2), "max_abs": max(abs(x) for x in v)}
                          for y, v in sorted(drift_by_year.items())},
        "snapshot": {"rows": len(snap), "as_of": rm.SNAP_DATE.isoformat()},
        "reconstruction": {"events_parsed_rows": sum(1 for _ in csv.DictReader(rm.EVENTS.open(encoding="utf-8"))),
                           "cancellations": len(cancelled), "anomalies": len(anomalies),
                           "anomalies_on_current_constituents": len(critical),
                           "post_snapshot_events": sorted(d.isoformat() for d in after),
                           "undated_files": sorted({r["file"] for r in undated})},
        "item1_entrants": {"W2_after_D0": len(entrants_w2), "by_year": dict(sorted(entrants_by_year.items())),
                           "W1_after_start": len(entrants_w1), "W1_list": [(d.isoformat(), s) for d, s in entrants_w1],
                           "vendor_errors": vendor_errors, "stored_window": stored},
        "item2_membership": {"symbols_audited": len(per_symbol),
                             "no_full_period_W1": len(no_full_w1), "no_full_period_W2": len(no_full_w2),
                             "no_full_period_W1_symbols": no_full_w1},
        "item3_samples": {"candidate_samples": n_all, "by_class": dict(total),
                          "not_member_share_pct": pct(total["NOT_MEMBER_RECONSTRUCTED"], n_all),
                          "uncertain_share_pct": pct(total["UNCERTAIN_CHAIN"], n_all),
                          "W1": {"by_class": dict(by_year_w1), "not_member_share_pct": pct(
                              by_year_w1["NOT_MEMBER_RECONSTRUCTED"], sum(by_year_w1.values()))}},
        "members_not_in_universe_by_year": missing_by_year,
        "crosscheck_inclusion_before_first_bar": early,
        "item4_reconstructability": {"status": "PARTIAL: drift stored per date, no cutoff applied; reviewer to choose",
                                     "removed_names_vendor": removed},
    }
    (HERE / "survivorship_audit_v1.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    with (HERE / "survivorship_by_symbol.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["symbol", "first_bar", *classes, "touched_by_anomaly"])
        for s, v in per_symbol.items():
            w.writerow([s, v["first_bar"], *(v[k] for k in classes), v["touched_by_anomaly"]])
    with (HERE / "survivorship_by_year.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["year", *classes, "samples", "not_member_pct", "mean_drift", "max_abs_drift"])
        for y in sorted(by_year):
            c = by_year[y]
            dv = drift_by_year[y]
            w.writerow([y, *(c[k] for k in classes), sum(c.values()), pct(c["NOT_MEMBER_RECONSTRUCTED"], sum(c.values())),
                        round(sum(dv) / len(dv), 2), max(abs(x) for x in dv)])
    with (HERE / "survivorship_drift_by_date.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["state_in_force_from", "reconstructed_set_size", "drift_vs_snapshot"])
        for start, dr in drift_states:
            w.writerow([start if start != date.min else "", target + dr, dr])
    (HERE / "survivorship_audit_v1.md").write_text(render_report(result, by_year, len(per_symbol)), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("windows", "item2_membership", "item3_samples")}, indent=1, default=str))


if __name__ == "__main__":
    main()
