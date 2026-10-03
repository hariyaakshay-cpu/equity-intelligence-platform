# nse-equity-calendar-v1 — validation report

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Status: **VALIDATED**. Span 2011-01-01 to 2026-10-02, NSE equity cash market.
Sessions: 3904 (BUDGET 4, MUHURAT 15, REGULAR 3876, SPECIAL_LIVE 9).
Output: `nse_equity_calendar_v1.csv` sha256 `7babff066e13c8137d10fbabb03246d95b8779b0363affe6287e4ddd1d183e72`.

## Vendor cross-check

| Instrument | Bars in span | Sessions without a bar |
|---|---|---|
| nifty500 | 3903 | 1 |
| nifty50 | 3904 | 0 |
| reliance | 3904 | 0 |

Discrepancies found: 1; unresolved: 0.

| Date | Instrument | Finding | Resolution |
|---|---|---|---|
| 2020-01-07 | nifty500 | session without vendor bar | VENDOR GAP — Regular Tuesday: not in the NSE holiday master, no holiday circular, and Nifty 50 and RELIANCE both have bars. The Upstox Nifty 500 series is missing this day; the calendar is unchanged and the gap is carried to the data-quality audit. |

## Resolutions (all exceptions to the holiday master)

| Date | Status | Type | Circulars | Note |
|---|---|---|---|---|
| 2011-10-26 | SESSION | MUHURAT | NSE/CMTR/19187 | Muhurat trading (Diwali); holiday master lists the day with * |
| 2012-01-07 | SESSION | SPECIAL_LIVE | NSE/CMTR/19734 | Special session for live trading (Saturday); absent from holiday master |
| 2012-03-03 | SESSION | SPECIAL_LIVE | NSE/CMTR/20063 | Special session for live trading (Saturday); absent from holiday master |
| 2012-04-28 | SESSION | SPECIAL_LIVE | NSE/CMTR/20561 | Special session for live trading (Saturday) |
| 2012-09-08 | SESSION | SPECIAL_LIVE | NSE/CMTR/21547 | Special session for live trading (Saturday) |
| 2012-11-11 | CLOSED |  | NSE/CMTR/22063 | Dhanteras special session traded Gold ETFs only; not an equity session (vendor correctly has no bar) |
| 2012-11-13 | SESSION | MUHURAT | NSE/CMTR/22027 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2013-05-11 | SESSION | SPECIAL_LIVE | NSE/CMTR/23302 | Special session for live trading (Saturday); absent from holiday master |
| 2013-11-03 | SESSION | MUHURAT | NSE/CMTR/24773 | Muhurat trading (Diwali); holiday master lists the day with * |
| 2014-03-22 | SESSION | SPECIAL_LIVE | NSE/CMTR/26045 | Special live trading session from BCP site (Saturday); absent from holiday master |
| 2014-10-23 | SESSION | MUHURAT | NSE/CMTR/27779 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2015-02-28 | SESSION | BUDGET | NSE/CMTR/28939 | Live trading session on Union Budget day (Saturday) |
| 2015-11-11 | SESSION | MUHURAT | NSE/CMTR/31047 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2016-10-30 | SESSION | MUHURAT | NSE/CMTR/33424 | Muhurat trading (Diwali); holiday master lists the day with * |
| 2017-10-19 | SESSION | MUHURAT | NSE/CMTR/35993 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2018-11-07 | SESSION | MUHURAT | NSE/CMTR/39216 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2019-10-27 | SESSION | MUHURAT | NSE/CMTR/42403 | Muhurat trading (Diwali); circular PDF is an image so the date is taken from the holiday master * entry and confirmed by vendor bars |
| 2020-02-01 | SESSION | BUDGET | NSE/CMTR/43290 | Live trading session on Union Budget day (Saturday); absent from holiday master |
| 2020-11-14 | SESSION | MUHURAT | NSE/CMTR/46230 | Muhurat trading (Diwali); holiday master lists the day with * |
| 2021-11-04 | SESSION | MUHURAT | NSE/CMTR/50050 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2022-10-24 | SESSION | MUHURAT | NSE/CMTR/54023 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2023-11-12 | SESSION | MUHURAT | NSE/CMTR/59124 | Muhurat trading (Diwali); holiday master lists the day with * |
| 2024-01-20 | SESSION | SPECIAL_LIVE | NSE/MSD/59999;NSE/MSD/60340 | Special live trading session (Saturday); later moved to the primary site; absent from holiday master |
| 2024-03-02 | SESSION | SPECIAL_LIVE | NSE/MSD/60677 | Special live trading session with intraday switch-over to DR site (Saturday) |
| 2024-05-18 | SESSION | SPECIAL_LIVE | NSE/MSD/61893 | Special live trading session with intraday switch-over to DR site (Saturday); absent from holiday master |
| 2024-11-01 | SESSION | MUHURAT | NSE/CMTR/64628 | Muhurat trading (Diwali); weekday not listed in holiday master |
| 2025-02-01 | SESSION | BUDGET | NSE/CMTR/65729 | Live trading session on Union Budget day (Saturday); absent from holiday master |
| 2025-10-21 | SESSION | MUHURAT | NSE/CMTR/70319 | Muhurat trading (Diwali); holiday master lists the day as a holiday without * |
| 2026-02-01 | SESSION | BUDGET | NSE/CMTR/72349 | Live trading session on Union Budget day (Sunday); absent from holiday master |
