# Verified NSE equity trading calendar (ML spec 5A.1)

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

`nse_equity_calendar_v1.csv` is the session list for the NSE equity cash
market from 2011-01-01 to 2026-10-02: one row per calendar day, with
`is_session`, `session_type` (`REGULAR`, `MUHURAT`, `SPECIAL_LIVE`, `BUDGET`),
the closure reason, and the source of each decision. Its status, counts and
hashes are in `calendar_manifest_v1.json`. The vendor cross-check is in
`validation_report_v1.md`.

## How it is made

1. `fetch_sources.py` (read-only; run from the repository root) saves:
   - the NSE holiday master for each year;
   - an index of every NSE circular whose subject concerns a holiday or a
     trading session (all departments, by month);
   - the PDF of every circular cited in `resolutions.csv`;
   - Upstox daily bar dates for Nifty 500, Nifty 50 and RELIANCE.
2. `build_calendar.py` applies the rules in its docstring.
   - **NSE sources decide** what is a session: the holiday master, plus
     circulars for every exception (`resolutions.csv`).
   - **Vendor bars are only a cross-check.** The build fails unless every
     disagreement is explained, either by a resolution or by a recorded vendor
     gap (`vendor_gaps.csv`).

## What the sources showed

- **The holiday master is incomplete.** It does not list weekday Muhurat
  sessions. It also leaves out several Saturday special sessions and Budget
  days (2012-01-07, 2012-03-03, 2013-05-11, 2014-03-22, 2020-02-01,
  2024-01-20, 2024-05-18, 2025-02-01, 2026-02-01). All of them are added from
  circulars.
- **2012-11-11 is closed for equities.** The holiday master calls it
  "Dhanteras Trading", but circular NSE/CMTR/22063 says that session traded
  Gold ETFs only.
- **2025-10-21 is a Muhurat session.** The holiday master lists it as a
  holiday without the `*` Muhurat marker.
- **One vendor gap.** Upstox's Nifty 500 series has no bar on 2020-01-07, a
  regular session; Nifty 50 and RELIANCE both have one.

## Limits

- **No data before 2011.** The holiday-master API returns nothing earlier, so
  a longer span needs another source and a new `calendar_version`.
- **Muhurat days are sessions.** Their bars come from a short evening session;
  `session_type` lets a dataset treat them differently if its specification
  says so.
- **Not yet used anywhere.** Adopting this calendar in the dashboard or in
  `equity_intel` is a separate change, outside this artefact.
