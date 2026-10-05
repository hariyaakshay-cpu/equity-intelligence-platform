"""Render survivorship_audit_v1.md from the audit result (spec 5A.2).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Every figure in the report is read from the result dictionary built by build_audit.py;
nothing is typed in by hand. The limits section is the only fixed prose.
"""
from __future__ import annotations

from datetime import date


def pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 2) if b else 0.0


def render_report(r: dict, by_year: dict, audited: int) -> str:
    w, rec = r["windows"], r["reconstruction"]
    i1, i2, i3, i4 = r["item1_entrants"], r["item2_membership"], r["item3_samples"], r["item4_reconstructability"]
    drift = r["drift_by_year"]
    out: list[str] = []
    a = out.append

    a("# Survivorship audit v1 (ML spec 5A.2)\n")
    a(f"RESEARCH ONLY — NOT A TRADING RECOMMENDATION. Built {r['built_at']}.\n")

    a("## Result\n")
    a(f"- **Membership reconstruction: {i4['status']}.** Membership is rebuilt backwards from the snapshot using NSE "
      "Indices press releases. The reconstructed set size minus the snapshot size (drift) is stored for every date "
      "(`survivorship_drift_by_date.csv`) and summarised by year below. No cutoff date is asserted.")
    a(f"- **Candidate samples** (current constituent × session, {w['D0_calendar_start']} to {w['D1']}): "
      f"{i3['candidate_samples']:,}. **{i3['not_member_share_pct']}%** use a name the reconstruction says was not in "
      f"the index at the time and **{i3['uncertain_share_pct']}%** have an unresolved membership chain. Read each "
      "year's share together with that year's drift.")
    a(f"- **The stored one-year window** ({w['W1'][0]} to {w['W1'][1]}): {i3['W1']['not_member_share_pct']}% of "
      "samples are reconstructed non-members (a name used before it entered the index).")
    a("- A dataset on today's constituents keeps the label `universe: current constituents — NOT point-in-time` "
      "unless the reviewer approves a drift bound. This audit measures the bias; it does not remove it.\n")

    a("## Inputs\n")
    a("| Input | sha256 |\n|---|---|")
    for k, v in r["inputs"].items():
        a(f"| {k} | `{v}` |")
    a("\nPress releases come from niftyindices.com (`sources/press_releases/`); `sources/fetch_log.json` lists every "
      f"file with its hash. The snapshot has {r['snapshot']['rows']} rows as of {r['snapshot']['as_of']} "
      "(one is HFCL, series BE).\n")

    a("## Item 1 — entrants inside the window\n")
    a(f"Current constituents whose first Upstox bar is after {w['D0_calendar_start']}: **{i1['W2_after_D0']}** of "
      f"{audited} audited. By year of first bar:\n")
    a("| Year | Entrants |\n|---|---|")
    for y, n in i1["by_year"].items():
        a(f"| {y} | {n} |")
    a(f"\nInside the stored window (first bar after {w['W1'][0]}): **{i1['W1_after_start']}**.")
    if i1["vendor_errors"]:
        a(f"\nVendor errors, left out of the sample counts: {', '.join(i1['vendor_errors'])}.")
    st = i1.get("stored_window")
    if st:
        short = ", ".join(f"{s} (first {d}, {n} bars)" for s, d, n in st["insufficient_history"])
        a(f"\nStored acquisition run `{st['run_id']}`: {st['status_counts']}. Insufficient stored history: {short}.")

    a("\n## Item 2 — membership evidence\n")
    a(f"Symbols that are not reconstructed as full-period members without an anomaly: {i2['no_full_period_W1']} of "
      f"{i2['symbols_audited']} over the stored window; {i2['no_full_period_W2']} over the full calendar span. "
      "Per-symbol counts: `survivorship_by_symbol.csv`.\n")

    a("## Item 3 — candidate samples by class, with drift\n")
    a("| Year | Member | Not a member | Uncertain chain | Samples | Not a member, % | Mean drift | Max abs drift "
      "|\n|---|---|---|---|---|---|---|---|")
    for y in sorted(by_year):
        c = by_year[y]
        n = sum(c.values())
        d = drift.get(y, drift.get(str(y), {}))
        a(f"| {y} | {c['MEMBER_RECONSTRUCTED']:,} | {c['NOT_MEMBER_RECONSTRUCTED']:,} | {c['UNCERTAIN_CHAIN']:,} | "
          f"{n:,} | {pct(c['NOT_MEMBER_RECONSTRUCTED'], n)} | {d.get('mean', '—')} | {d.get('max_abs', '—')} |")
    a("\nDrift is in names; positive means the rebuilt set is larger than the snapshot.\n")

    a("## Names in the index that are not in today's universe\n")
    a("The other side of survivorship: reconstructed members at a date that are absent from the 2026-09-24 list "
      "(sampled about monthly; an undercount wherever an exit was not found).\n")
    a("| Year | Mean members | Mean not in universe | Share, % |\n|---|---|---|---|")
    for y, v in r["members_not_in_universe_by_year"].items():
        a(f"| {y} | {v['mean_members']} | {v['mean_not_in_universe']} | {v['share_pct']} |")

    early = r["crosscheck_inclusion_before_first_bar"]
    a("\n## Cross-check: index entry before the first bar\n")
    a("A reconstructed entry date earlier than the stock's first Upstox bar is impossible unless the name is a "
      f"demerger spin-off included under a dummy symbol. Entries that fail: **{len(early)}**"
      + (": " + "; ".join(f"{s} entered {d}, first bar {f}" for d, s, f in early) + "." if early else "."))

    a("\n## Item 4 — reconstructability\n")
    a(f"**{i4['status']}.** `parse_press_releases.py` reads the Nifty 500 section of each press release; "
      "`reconstruct_membership.py` undoes the changes backwards from the snapshot and checks each change against the "
      f"set (`membership_anomalies.csv`). {rec['events_parsed_rows']} change rows were read, {rec['cancellations']} "
      f"revocations applied, {rec['anomalies']} checks failed overall, {rec['anomalies_on_current_constituents']} of "
      f"them on current constituents. Snapshot size: "
      f"{r['snapshot']['rows']}; drift by date is stored.")
    rv = i4["removed_names_vendor"]
    if rv:
        late = len(rv["last_bar_before_2026-09-01"])
        a("\n**Does the vendor still serve names that left the index?** From the symbols that left the index from "
          f"2020-03-27 on, are not in the snapshot and resolve by trading symbol in the local Upstox master, "
          f"{rv['sampled']} were sampled (deterministic, `vendor_sample90.py`). {rv['served_history']} returned bars; "
          f"{late} of those stop before 2026-09-01. {rv['unresolved_in_master']} such symbols do not resolve in the "
          "master at all (renamed, merged or delisted) and could not be sampled. Resolution is by symbol only "
          f"(ISIN not verified). Sample fetch: {rv['sample_calls']} calls, stopped: {rv['stopped']}.")

    a("\n## Limits\n")
    for t in (
        "Older years drift more: releases for 2011-2019 exist, but the rebuilt set grows past the snapshot size and "
        "some changes conflict. No cutoff is applied here.",
        "Renamed symbols are mapped by company-name continuity (`symbol_aliases.csv`, status INFERRED). That is "
        "inferred, not documentary.",
        "Inclusions with no found exit (for example AKZOINDIA, MFL, MAHINDCIE) leave those names out of the rebuilt "
        "set between entry and an unknown exit. They are not current constituents, so the sample classes are "
        "unaffected; the 'not in universe' table undercounts.",
        "Temporary index entries for demerged companies (dummy symbols) and the 'Exclusion of ...' releases are "
        "saved but not modelled. They last days to weeks.",
        "The deferred March 2020 rebalancing is handled by `void_events.csv`, citing the 13 May 2020 release.",
        "Candidate samples assume a bar on every session between a symbol's first and last bar. Holes belong to "
        "the data-quality audit.",
        "Any drift bound that decides which dates count as usable must be chosen and approved by the reviewer "
        "before a dataset relies on it.",
    ):
        a(f"- {t}")

    a("\n## Reproduce\n")
    a("```\npython research/ml/survivorship/fetch_sources.py\n"
      "python research/ml/survivorship/parse_press_releases.py\n"
      "python research/ml/survivorship/reconstruct_membership.py\n"
      "# from the repository root that holds .env and data/:\n"
      "python research/ml/survivorship/vendor_first_bars.py\n"
      "python research/ml/survivorship/vendor_first_bars.py --removed\n"
      "python research/ml/survivorship/build_audit.py\n```")
    return "\n".join(out) + "\n"
