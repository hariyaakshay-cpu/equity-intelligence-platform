# Daily pre-registration (2026-10-28): one covered file no longer matches its recorded hash

Recorded for the record on 2026-11-01. No result has been produced from this pre-registration.

`research/daily_prereg_2026-10-28.sha256` was written 2026-10-27 21:02:32 UTC and covers four files.
Verified 2026-11-01, three still match and one does not:

| File | Recorded | Current | Result |
|---|---|---|---|
| docs/architecture/equity_intel_daily_signals_preregistration_DRAFT.md | acb47ddf… | acb47ddf… | OK |
| equity_intel/scoring/provisional_v0.py | 4ce5fedee… | 4ce5fedee… | OK |
| equity_intel/scoring/components_v0.py | aba011aa9… | aba011aa9… | OK |
| scripts/equity_daily_history_fetch.py | d4313a55dccf4bbc19b5f85d13d2201c26e8ba985fd5b9b67f28fa19c7bc052c | d5eca7231300e5dfe244a52b54dbd222dd93fa77e53d6ab6521dec7a6eea4a24 | FAILED |

What is known: the file's mtime is 2026-10-27 21:25:32 UTC, 23 minutes after the manifest was written.
What is not known: what changed. The file was untracked at the time, so no earlier copy of those bytes
exists in this repository and the difference cannot be reconstructed.

Scope: the file is the Upstox daily-candle download tool. The design document and both scoring modules
still match, so the decision rules of the study are intact; the discrepancy is in the data-acquisition
tool only. That is not a licence to treat the manifest as satisfied.

Standing rule: this manifest is void for any result produced after 2026-10-27 21:25 UTC. Before the
daily study is run, record a fresh manifest over the then-current files and cite that one in the result.
