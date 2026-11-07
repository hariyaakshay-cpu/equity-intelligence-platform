"""Run announcement event study v1 (DEV, then HOLDOUT once).

    python scripts/announcement_event_study.py --raw-dir research/announcements/coverage_<ts>/raw --phase dev
    python scripts/announcement_event_study.py --raw-dir <same> --phase holdout

Refuses to run if the pre-registration file changed. HOLDOUT runs once, only
for category x horizon pairs that passed DEV; holdout observations are never
written to disk before that run. Paper research only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from equity_intel.announcements import event_study as es  # noqa: E402

PREREG = ROOT / "docs" / "architecture" / "announcement_event_study_preregistration.md"
PREREG_HASH = ROOT / "research" / "announcements" / "event_study_prereg_2026-11-08.sha256"
PRICE_DIRS = [ROOT / "data" / "daily_history_early", ROOT / "data" / "daily_history"]
DEFAULT_OUT = ROOT / "research" / "announcements" / "event_study_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_prereg() -> str:
    expected = PREREG_HASH.read_text(encoding="utf-8").split()[0]
    actual = sha256(PREREG)
    if actual != expected:
        raise SystemExit(f"pre-registration changed: {actual} != {expected}")
    return actual


def build(raw_dir: Path):
    ann = es.load_announcements(raw_dir)
    if ann.empty:
        raise SystemExit(f"no announcements found in {raw_dir}")
    index = es.load_prices(PRICE_DIRS, es.INDEX_SYMBOL)
    sessions = sorted(index.index)
    prices = {s: es.load_prices(PRICE_DIRS, s) for s in sorted(ann["symbol"].unique())}
    prices = {s: p for s, p in prices.items() if p is not None}
    obs, drops = es.build_observations(ann, prices, index, sessions)
    info = {"announcements": len(ann),
            "announcements_by_ts_source": ann["ts_source"].value_counts().to_dict(),
            "symbols_in_announcements": int(ann["symbol"].nunique()),
            "symbols_with_prices": len(prices),
            "first_event": str(ann["event_ts"].min()), "last_event": str(ann["event_ts"].max())}
    return obs, drops, info


def show(df: pd.DataFrame) -> None:
    cols = ["category", "horizon", "n", "sessions", "mean_net_abn_pct",
            "mean_net_raw_pct", "lower_bound_pct", "max_symbol_share", "verdict"]
    with pd.option_context("display.width", 200, "display.max_rows", 500,
                           "display.float_format", "{:.3f}".format):
        print(df[cols].sort_values(["verdict", "mean_net_abn_pct"],
                                   ascending=[False, False]).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--phase", required=True, choices=["dev", "holdout"])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    prereg_sha = check_prereg()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.raw_dir.parent / "manifest.csv"
    meta = {"phase": args.phase, "prereg_sha256": prereg_sha,
            "raw_dir": str(args.raw_dir),
            "raw_manifest_sha256": sha256(manifest) if manifest.exists() else None,
            "run_ts": datetime.now().isoformat(timespec="seconds")}

    if args.phase == "dev":
        obs, drops, info = build(args.raw_dir)
        cats = es.eligible_categories(obs)
        k_tests = len(cats) * len(es.HORIZONS)
        if not cats:
            raise SystemExit("no category has >= 300 DEV observations at H0")
        pairs = [(c, h) for c in cats for h in es.HORIZONS]
        res = es.evaluate(obs, pairs, "dev", k_tests)
        obs[obs["period"] == "dev"].to_csv(args.out / "dev_observations.csv", index=False)
        res.to_csv(args.out / "dev_results.csv", index=False)
        meta.update(info, eligible_categories=cats, k_tests=k_tests,
                    drops=dict(drops), dev_pass=int((res["verdict"] == "PASS").sum()))
        (args.out / "dev_meta.json").write_text(json.dumps(meta, indent=2, default=str))
        show(res)
        print(f"\nK={k_tests} tests; DEV PASS: {meta['dev_pass']}. Wrote {args.out}")
        return

    dev_meta_path = args.out / "dev_meta.json"
    if not dev_meta_path.exists():
        raise SystemExit("run --phase dev first")
    dev_meta = json.loads(dev_meta_path.read_text())
    if dev_meta["prereg_sha256"] != prereg_sha:
        raise SystemExit("DEV ran under a different pre-registration")
    dev = pd.read_csv(args.out / "dev_results.csv")
    pairs = [(r.category, r.horizon) for r in dev.itertuples() if r.verdict == "PASS"]
    try:
        with open(args.out / "holdout.lock", "x", encoding="utf-8") as f:
            f.write(meta["run_ts"])
    except FileExistsError:
        raise SystemExit("HOLDOUT already ran once; it is never re-run")
    if not pairs:
        (args.out / "holdout_results.md").write_text(
            "No category x horizon passed DEV; HOLDOUT not evaluated.\n")
        print("No DEV passes; HOLDOUT not evaluated.")
        return
    obs, drops, info = build(args.raw_dir)
    res = es.evaluate(obs, pairs, "holdout", dev_meta["k_tests"])
    obs[(obs["period"] == "holdout")
        & obs.set_index(["category", "horizon"]).index.isin(pairs)].to_csv(
        args.out / "holdout_observations.csv", index=False)
    res.to_csv(args.out / "holdout_results.csv", index=False)
    meta.update(info, pairs=pairs, drops=dict(drops))
    (args.out / "holdout_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    show(res)
    print(f"\nHOLDOUT PASS: {int((res['verdict'] == 'PASS').sum())}. Wrote {args.out}")


if __name__ == "__main__":
    main()
