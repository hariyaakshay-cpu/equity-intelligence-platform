# coverage_20261108T133738 (2012-01-02 to 2018-09-13)

The fetch run ended without writing manifest.csv. `manifest_reconstructed.csv`
was rebuilt on 2026-11-18 from the raw files on disk (same columns;
http_status and retrieved_ts unknown, left blank).

Checked against data/daily_history_early/NIFTY500_INDEX.csv (from 2013-10-01):
- 4 trading sessions without data: 2014-09-22, 2014-09-23, 2014-09-24 (NSE
  returned []) and 2017-05-15 (no file). To be re-fetched in a separate
  coverage run (2026-11-18).
- The other 34 empty files are all market holidays.
