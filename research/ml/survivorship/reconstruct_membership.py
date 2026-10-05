"""Reconstruct Nifty 500 membership backwards from the snapshot (spec 5A.2 items 2 and 4).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Input:  data/reference/nifty500_constituents_2026-09-24.csv   (the snapshot, as of SNAP_DATE)
        nifty500_events.csv                                    (parse_press_releases.py)
Method: walk the events in reverse effective-date order. For an event effective on e, the set
        before e is  (set from e) - included + excluded.  Before applying an event, check it:
          INCLUDE_NOT_MEMBER   an included symbol is not a member just after e
          EXCLUDE_IS_MEMBER    an excluded symbol is still a member just after e
        Each check failure is an anomaly: a missing, mis-parsed or renamed event. The walk
        continues (nothing is repaired) and every anomaly is written out.
Output: membership_anomalies.csv     one row per failed check
        membership_timeline.csv      the set size after undoing each event date
        membership_intervals.csv     per symbol, the date ranges reconstructed as member, and
                                     whether any anomaly touches that symbol

Cancellations (CANCEL_INCLUDE / CANCEL_EXCLUDE: a later release revokes an announced change)
remove the matching announced event (same symbol, action and effective date, other file).
void_events.csv lists announced changes that a later release declared null and void.
symbol_aliases.csv maps a symbol used in an old release to the symbol it carries in the
snapshot; each row says what the evidence is and whether it is documentary or inferred.

Changes announced for dates after SNAP_DATE are not undone; they are listed.
Run from anywhere:  python research/ml/survivorship/reconstruct_membership.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SNAPSHOT = ROOT / "data" / "reference" / "nifty500_constituents_2026-09-24.csv"
SNAP_DATE = date(2026, 9, 24)
EVENTS = HERE / "nifty500_events.csv"
ALIASES = HERE / "symbol_aliases.csv"
VOIDS = HERE / "void_events.csv"


def load():
    snap = {r["Symbol"] for r in csv.DictReader(SNAPSHOT.open(encoding="utf-8"))}
    alias = ({r["old_symbol"]: r["new_symbol"] for r in csv.DictReader(ALIASES.open(encoding="utf-8"))}
             if ALIASES.exists() else {})
    rows = list(csv.DictReader(EVENTS.open(encoding="utf-8")))
    voids = list(csv.DictReader(VOIDS.open(encoding="utf-8"))) if VOIDS.exists() else []
    rows = [r for r in rows if not any(v["file"] == r["file"] and v["effective_date"] == r["effective_date"]
                                       and v["symbol"] in ("*", r["symbol"]) for v in voids)]
    cancelled = []
    for c in (r for r in rows if r["action"].startswith("CANCEL_")):
        kind = c["action"].removeprefix("CANCEL_")
        hit = [r for r in rows if r["action"] == kind and r["symbol"] == c["symbol"]
               and r["effective_date"] == c["effective_date"] and r["file"] != c["file"]]
        if hit:
            rows.remove(hit[-1])
            cancelled.append((c["file"], hit[-1]["file"], c["symbol"], kind, c["effective_date"]))
        else:
            cancelled.append((c["file"], "", c["symbol"], kind, c["effective_date"]))
    ev = defaultdict(lambda: {"INCLUDE": {}, "EXCLUDE": {}})
    undated = []
    for r in rows:
        if r["action"].startswith("CANCEL_"):
            continue
        if not r["effective_date"]:
            undated.append(r)
            continue
        ev[date.fromisoformat(r["effective_date"])][r["action"]][alias.get(r["symbol"], r["symbol"])] = r["file"]
    return snap, ev, undated, cancelled


def reconstruct():
    snap, ev, undated, cancelled = load()
    S = set(snap)
    anomalies, timeline = [], [(SNAP_DATE, "snapshot", len(S))]
    end_excl = min(after) if (after := [d for d in ev if d > SNAP_DATE]) else date.max
    open_since = {s: end_excl for s in S}           # symbol -> first date (going back) it is a member after
    intervals = defaultdict(list)                   # symbol -> [(start_inclusive, end_exclusive)]
    after = {d: ev[d] for d in after}
    for d in sorted((d for d in ev if d <= SNAP_DATE), reverse=True):
        inc, exc = ev[d]["INCLUDE"], ev[d]["EXCLUDE"]
        for s, f in inc.items():
            if s not in S:
                anomalies.append((d, f, s, "INCLUDE_NOT_MEMBER"))
        for s, f in exc.items():
            if s in S:
                anomalies.append((d, f, s, "EXCLUDE_IS_MEMBER"))
        # leaving the set going back = member starts at d
        for s in inc:
            if s in S and s in open_since:
                intervals[s].append((d, open_since.pop(s)))
        for s in exc:
            if s not in S or s not in open_since:
                open_since[s] = d
        S = (S - set(inc)) | set(exc)
        timeline.append((d, ",".join(sorted({*inc.values(), *exc.values()})), len(S)))
    for s, end in open_since.items():
        intervals[s].append((None, end))            # member since before the earliest event we hold
    event_dates = defaultdict(list)                 # symbol -> every date it appears in an event
    for d in sorted(ev):
        for s in (*ev[d]["INCLUDE"], *ev[d]["EXCLUDE"]):
            event_dates[s].append(d)
    return snap, intervals, anomalies, timeline, after, undated, cancelled, event_dates


def main():
    snap, intervals, anomalies, timeline, after, undated, cancelled, _ = reconstruct()
    with (HERE / "membership_anomalies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["effective_date", "file", "symbol", "check"])
        w.writerows(sorted(anomalies, reverse=True))
    with (HERE / "membership_timeline.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["effective_date", "files", "set_size_before_event"])
        w.writerows(timeline)
    bad = {s for _, _, s, _ in anomalies}
    with (HERE / "membership_intervals.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["symbol", "member_from", "member_until_exclusive", "in_snapshot", "touched_by_anomaly"])
        for s in sorted(intervals):
            for a, b in sorted(intervals[s], key=lambda x: (x[0] is None, x[0])):
                w.writerow([s, a or "", b, int(s in snap), int(s in bad)])
    with (HERE / "membership_cancellations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cancelling_file", "cancelled_file", "symbol", "cancelled_action", "effective_date"])
        w.writerows(cancelled)
    print("cancellations", len(cancelled), "unmatched", sum(1 for c in cancelled if not c[1]))
    print("anomalies", len(anomalies), "symbols", len(bad), "post-snapshot dates", sorted(after), "undated", len(undated))


if __name__ == "__main__":
    main()
