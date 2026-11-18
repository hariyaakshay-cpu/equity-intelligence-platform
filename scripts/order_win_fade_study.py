"""Run the order-win fade study once (docs/architecture/order_win_fade_preregistration.md).

    python scripts/order_win_fade_study.py

Builds observations with the unchanged v2.1 pipeline (order_win_event_study.build),
applies the frozen fade rules, prints the single verdict and writes
research/announcements/order_wins/fade/. Refuses to run if the pre-registration
or the shares file changed, or if results already exist. Paper research only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import order_win_event_study as v21  # noqa: E402
from equity_intel.announcements import event_study as es  # noqa: E402
from equity_intel.announcements import order_win_fade as fade  # noqa: E402

PREREG = ROOT / "docs" / "architecture" / "order_win_fade_preregistration.md"
PREREG_HASH = ROOT / "research" / "announcements" / "order_win_fade_prereg_2026-11-18.sha256"
SHARES = ROOT / "research" / "announcements" / "order_wins" / "shares_mcap17112026" / "shares.csv"
SHARES_SHA256 = "68b6e9a5d27364e0a2861184144ae0ceb6f12649d5d088af444e4309f9530c89"
OUT = ROOT / "research" / "announcements" / "order_wins" / "fade"


def main() -> None:
    expected = PREREG_HASH.read_text(encoding="utf-8").split()[0]
    actual = v21.text_sha256(PREREG)
    if actual != expected:
        raise SystemExit(f"pre-registration changed: {actual} != {expected}")
    shares_sha = hashlib.sha256(SHARES.read_bytes()).hexdigest()
    if shares_sha != SHARES_SHA256:
        raise SystemExit(f"shares file changed: {shares_sha} != {SHARES_SHA256}")
    if (OUT / "fade_meta.json").exists():
        raise SystemExit(f"{OUT / 'fade_meta.json'} exists: the fade study runs once and is never re-run")

    meta = {"prereg_sha256": actual, "shares_sha256": shares_sha,
            "run_ts": datetime.now().isoformat(timespec="seconds")}
    obs, info = v21.build(SHARES)
    with open(SHARES, encoding="utf-8") as fh:
        series = {r["symbol"]: r["series"] for r in csv.DictReader(fh)}
    syms = sorted(set(obs["symbol"]))
    prices = {s: es.load_prices(v21.PRICE_DIRS, s) for s in syms}
    d, drops = fade.fade_observations(obs, prices, series)
    res = fade.evaluate_fade(d)

    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "fade_observations.csv", index=False)
    meta.update(v21_build=info, fade_drops=dict(drops), result=res)
    (OUT / "fade_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    for k, v in res.items():
        print(f"{k:>24}: {v:.3f}" if isinstance(v, float) else f"{k:>24}: {v}")
    print(f"\nfade drops: {dict(drops)}\nVERDICT: {res['verdict']}. Wrote {OUT}")


if __name__ == "__main__":
    main()
