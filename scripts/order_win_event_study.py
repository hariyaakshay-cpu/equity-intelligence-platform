"""Run order-win event study v2 (DEV, then HOLDOUT once).

    python scripts/order_win_event_study.py symbols                  # write symbols.csv (no returns)
    python scripts/order_win_event_study.py dev --shares <shares.csv>
    python scripts/order_win_event_study.py holdout --shares <same shares.csv>

Refuses to run if the pre-registration changed. HOLDOUT runs once, only for
horizons whose PRIMARY row passed DEV. Paper research only.
"""
from __future__ import annotations

import argparse
import csv
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
from equity_intel.announcements import order_wins as ow  # noqa: E402

PREREG = ROOT / "docs" / "architecture" / "order_win_event_study_preregistration.md"
PREREG_HASH = ROOT / "research" / "announcements" / "order_win_prereg_2026-11-08.sha256"
RAW_DIRS = sorted((ROOT / "research" / "announcements").glob("coverage_*/raw"))
UNIVERSE_DIRS = [ROOT / "data" / "daily_history_early", ROOT / "data" / "daily_history"]
PRICE_DIRS = UNIVERSE_DIRS + [ROOT / "data" / "daily_history_orders"]
OUT = ROOT / "research" / "announcements" / "order_wins"


def text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_prereg() -> str:
    expected = PREREG_HASH.read_text(encoding="utf-8").split()[0]
    actual = text_sha256(PREREG)
    if actual != expected:
        raise SystemExit(f"pre-registration changed: {actual} != {expected}")
    return actual


def full_runs() -> list[Path]:
    """Raw dirs from --all-days runs only (manifest with > 1000 days)."""
    keep = []
    for d in RAW_DIRS:
        man = d.parent / "manifest.csv"
        if man.exists() and sum(1 for _ in open(man, encoding="utf-8")) > 1000:
            keep.append(d)
    return keep


def load_wins() -> tuple[pd.DataFrame, list[str]]:
    dirs = full_runs()
    if not dirs:
        raise SystemExit("no complete --all-days announcement download found")
    ann = pd.concat([es.load_announcements(d) for d in dirs], ignore_index=True)
    ann = ann.drop_duplicates(subset=["symbol", "category", "an_dt", "attachment"])
    return ow.extract_order_wins(ann), [str(d) for d in dirs]


def load_shares(path: Path) -> dict[str, float]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                v = float(r["issued_size"])
            except (TypeError, ValueError):
                continue
            if v > 0:
                out[r["symbol"]] = v
    return out


def build(shares_path: Path):
    wins, dirs = load_wins()
    index = es.load_prices(UNIVERSE_DIRS, es.INDEX_SYMBOL)
    sessions = sorted(index.index)
    units, unit_drops = ow.build_units(wins, sessions)
    prices = {s: es.load_prices(PRICE_DIRS, s) for s in sorted(units["symbol"].unique())}
    prices = {s: p for s, p in prices.items() if p is not None}
    universe_syms = sorted({p.stem for d in UNIVERSE_DIRS for p in d.glob("*.csv")}
                           - {es.INDEX_SYMBOL})
    universe = {s: es.load_prices(UNIVERSE_DIRS, s) for s in universe_syms}
    bench = ow.EqualWeightBenchmark(universe, sessions)
    obs, drops = ow.build_observations(units, prices, index, bench,
                                       load_shares(shares_path), sessions)
    drops.update(unit_drops)
    info = {"raw_dirs": dirs, "order_wins": len(wins), "units": len(units),
            "symbols": int(units["symbol"].nunique()), "symbols_with_prices": len(prices),
            "drops": dict(drops)}
    return obs, info


def show(res: pd.DataFrame) -> None:
    cols = ["threshold", "role", "horizon", "n", "sessions", "mean_net_abn_pct",
            "mean_net_raw_pct", "mean_net_abn_index_pct", "lower_bound_pct",
            "max_symbol_share", "verdict"]
    with pd.option_context("display.width", 220, "display.float_format", "{:.3f}".format):
        print(res.reindex(columns=cols).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("phase", choices=["symbols", "dev", "holdout"])
    ap.add_argument("--shares", type=Path)
    args = ap.parse_args()
    prereg_sha = check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)

    if args.phase == "symbols":
        wins, dirs = load_wins()
        syms = sorted(wins["symbol"].unique())
        with open(OUT / "symbols.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["symbol"])
            w.writerows([s] for s in syms)
        print(f"{len(wins)} order wins, {len(syms)} symbols from {dirs}; wrote symbols.csv")
        return

    if not args.shares:
        raise SystemExit("--shares is required")
    meta = {"phase": args.phase, "prereg_sha256": prereg_sha, "shares_file": str(args.shares),
            "shares_sha256": hashlib.sha256(args.shares.read_bytes()).hexdigest(),
            "run_ts": datetime.now().isoformat(timespec="seconds")}

    if args.phase == "dev":
        if (OUT / "dev_results.csv").exists():
            raise SystemExit("DEV results already exist; delete them deliberately to re-run")
        obs, info = build(args.shares)
        res = ow.evaluate(obs, "dev")
        obs[obs["period"] == "dev"].to_csv(OUT / "dev_observations.csv", index=False)
        res.to_csv(OUT / "dev_results.csv", index=False)
        meta.update(info, dev_pass=int((res["verdict"] == "PASS").sum()))
        (OUT / "dev_meta.json").write_text(json.dumps(meta, indent=2, default=str))
        show(res)
        print(f"\nPRIMARY DEV PASS: {meta['dev_pass']} of {ow.K_TESTS}. Wrote {OUT}")
        return

    dev_meta = json.loads((OUT / "dev_meta.json").read_text())
    if dev_meta["prereg_sha256"] != prereg_sha or dev_meta["shares_sha256"] != meta["shares_sha256"]:
        raise SystemExit("HOLDOUT must use the same pre-registration and shares file as DEV")
    dev = pd.read_csv(OUT / "dev_results.csv")
    horizons = list(dev[(dev["role"] == "PRIMARY") & (dev["verdict"] == "PASS")]["horizon"])
    try:
        with open(OUT / "holdout.lock", "x", encoding="utf-8") as f:
            f.write(meta["run_ts"])
    except FileExistsError:
        raise SystemExit("HOLDOUT already ran once; it is never re-run")
    if not horizons:
        (OUT / "holdout_results.md").write_text("No PRIMARY horizon passed DEV; HOLDOUT not evaluated.\n")
        print("No DEV passes; HOLDOUT not evaluated.")
        return
    obs, info = build(args.shares)
    res = ow.evaluate(obs, "holdout", horizons)
    res = res[res["role"] == "PRIMARY"]
    obs[obs["period"] == "holdout"].to_csv(OUT / "holdout_observations.csv", index=False)
    res.to_csv(OUT / "holdout_results.csv", index=False)
    meta.update(info, horizons=horizons)
    (OUT / "holdout_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    show(res)
    print(f"\nHOLDOUT PASS: {int((res['verdict'] == 'PASS').sum())}. Wrote {OUT}")


if __name__ == "__main__":
    main()
