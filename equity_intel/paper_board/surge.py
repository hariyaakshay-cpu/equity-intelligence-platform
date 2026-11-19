"""Volume-surge long, live paper test - rule logic only (no orders, no network).

Implements the FROZEN pre-registration docs/architecture/paper_board_surge_preregistration.md
(sha256 48726be2, commit e033872): trade rules S1-S6 and the R1-R3 review. The board
(scripts/equity_paper_board.py) calls step() once per check and stores the trades. Only
rule_intact() reads the disk: it re-hashes the frozen document. Paper only.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from equity_intel.paper_board import logic as pb

PREREG_SHA256 = "48726be23fb034e41f76cda2e08ef41d43860e455eae8adde6962971500b7206"
ROOT = Path(__file__).resolve().parents[2]
PREREG_DOC = ROOT / "docs" / "architecture" / "paper_board_surge_preregistration.md"
PREREG_SHA_FILE = ROOT / "research" / "paper_board" / "surge_long_prereg_2026-11-19.sha256"
FROZEN_LIST = {"SURGE_MIN_RATIO": 1.5, "SURGE_MIN_VALUE_CR": 10.0, "SURGE_FIRST_MINUTES": 15, "SURGE_TOP": 15}  # S1

TRIGGER_FROM, TRIGGER_TO = time(9, 30), time(13, 0)                    # S2
ENTRY_WAIT = timedelta(minutes=15)                                       # S3
CAP = 5                                                                  # S4
EXIT_FROM, EXIT_TO = time(15, 15), time(15, 30)                          # S5
COST_PCT = 0.18                                                          # S6
MIN_TRADES, MIN_SESSIONS = 300, 60                                       # R1
MAX_SYMBOL_SHARE, MAX_SECTOR_SHARE, MAX_DRAWDOWN = 0.10, 0.25, 20.0      # R2.3, R2.4, R3
RESAMPLES, SEED = 10_000, 20261119                                       # R2.2
FIELDS = ["date", "symbol", "status", "trigger_at", "ratio", "trigger_price", "change_pct", "entry_at",
          "entry_price", "exit_at", "exit_price", "exit_source", "gross_pct", "net_pct", "reason"]
VOID_NO_ENTRY = "no check with a price within 15 minutes of the trigger"


def rule_intact(doc: Path = PREREG_DOC, sha_file: Path = PREREG_SHA_FILE) -> tuple[bool, str]:
    """Surge trades are scored only while the frozen document and the S1 constants are unchanged."""
    try:
        digest = hashlib.sha256(Path(doc).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        recorded = Path(sha_file).read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError) as exc:
        return False, f"surge pre-registration unreadable ({type(exc).__name__}): surge trades not scored"
    if not digest == recorded == PREREG_SHA256:
        return False, "surge pre-registration changed (sha256 mismatch): surge trades not scored"
    changed = [k for k, v in FROZEN_LIST.items() if getattr(pb, k) != v]
    if changed:
        return False, f"surge list constants changed ({', '.join(changed)}): surge trades not scored"
    return True, "surge pre-registration sha256 48726be2 and S1 constants match"


def result(entry: float, exit_price: float) -> dict:
    """S6: gross % = (exit / entry - 1) x 100; net % = gross % - 0.18."""
    gross = (exit_price / entry - 1) * 100
    return {"status": "CLOSED", "gross_pct": round(gross, 3), "net_pct": round(gross - COST_PCT, 3)}


def fill_entries(trades: list[dict], quotes: dict, now: datetime) -> None:
    """S3: a waiting trade fills at the last price of the first later check that has one, within 15 minutes."""
    for t in trades:
        if t["status"] != "WAITING_ENTRY":
            continue
        trigger = datetime.fromisoformat(t["trigger_at"])
        if now <= trigger:
            continue
        if now - trigger > ENTRY_WAIT:
            t.update(status="VOID", reason=VOID_NO_ENTRY)
            continue
        q = quotes.get(t["symbol"])
        if q and q.get("ltp"):
            t.update(status="OPEN", entry_at=now.isoformat(timespec="seconds"), entry_price=float(q["ltp"]))


def new_triggers(trades_today: list[dict], surges: list[dict], quotes: dict, now: datetime) -> list[dict]:
    """S2 + S4: up-on-the-day stocks on the surge list, 09:30-13:00, higher ratio first then A-Z, 5 a session."""
    if not TRIGGER_FROM <= now.time() <= TRIGGER_TO:
        return []
    taken = {t["symbol"] for t in trades_today}
    slots = max(0, CAP - len(trades_today))              # a VOID trade still uses its slot
    ups = []
    for s in surges:
        q = quotes.get(s["symbol"]) or {}
        if s["symbol"] not in taken and q.get("prev_close") and (q.get("ltp") or 0) > q["prev_close"]:
            ups.append(s)
    ups.sort(key=lambda s: (-s["ratio"], s["symbol"]))
    stamp = now.isoformat(timespec="seconds")
    return [{"date": now.date().isoformat(), "symbol": s["symbol"], "status": "WAITING_ENTRY", "trigger_at": stamp,
             "ratio": s["ratio"], "trigger_price": s.get("ltp"), "change_pct": s.get("change_pct")}
            for s in ups[:slots]]


def exit_trades(trades: list[dict], quotes: dict, now: datetime) -> None:
    """S5: open trades exit at the last price of the first check between 15:15 and 15:30."""
    if not EXIT_FROM <= now.time() <= EXIT_TO:
        return
    for t in trades:
        q = quotes.get(t["symbol"])
        if t["status"] == "OPEN" and q and q.get("ltp"):
            t.update(result(float(t["entry_price"]), float(q["ltp"])), exit_at=now.isoformat(timespec="seconds"),
                     exit_price=float(q["ltp"]), exit_source="last_price_1515")


def step(trades_today: list[dict], surges: list[dict], quotes: dict, now: datetime) -> list[dict]:
    """One board check in rule order. Updates today's trades in place; returns the new ones for the caller to add."""
    fill_entries(trades_today, quotes, now)
    exit_trades(trades_today, quotes, now)
    return new_triggers(trades_today, surges, quotes, now)


def reconcile(trades: list[dict], daily: dict, today: date) -> int:
    """Next morning: earlier sessions' OPEN trades exit at the official close (S5); WAITING ones are VOID (S3)."""
    n = 0
    for t in trades:
        if t["date"] >= today.isoformat():
            continue
        if t["status"] == "WAITING_ENTRY":
            t.update(status="VOID", reason=VOID_NO_ENTRY)
            n += 1
        elif t["status"] == "OPEN":
            px, d = daily.get(t["symbol"]), date.fromisoformat(t["date"])
            if px is not None and d in px.index:
                close = float(px.loc[d, "c"])
                t.update(result(float(t["entry_price"]), close), exit_at=f"{t['date']}T15:30:00",
                         exit_price=close, exit_source="official_close")
                n += 1
    return n


def _closed(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("status") == "CLOSED" and t.get("net_pct") not in (None, "")]


def max_drawdown(trades: list[dict]) -> float:
    """R2.4: largest peak-to-trough fall of the cumulative net % (trades summed by date), starting from 0."""
    by_date: dict = {}
    for t in _closed(trades):
        by_date[t["date"]] = by_date.get(t["date"], 0.0) + float(t["net_pct"])
    cum = peak = worst = 0.0
    for d in sorted(by_date):
        cum += by_date[d]
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return round(worst, 3)


def bootstrap_ci(trades: list[dict], resamples: int = RESAMPLES, seed: int = SEED) -> tuple[float, float]:
    """R2.2: two-sided 95% interval of the mean net % per trade, resampling whole session dates."""
    blocks: dict = {}
    for t in _closed(trades):
        total, count = blocks.get(t["date"], (0.0, 0))
        blocks[t["date"]] = (total + float(t["net_pct"]), count + 1)
    days = [blocks[d] for d in sorted(blocks)]
    rng, k, means = random.Random(seed), len(days), []
    for _ in range(resamples):
        total = count = 0
        for _ in range(k):
            s, n = days[int(rng.random() * k)]
            total += s
            count += n
        means.append(total / count)
    means.sort()
    return round(means[math.ceil(0.025 * resamples) - 1], 4), round(means[math.ceil(0.975 * resamples) - 1], 4)


def max_share(trades: list[dict], key) -> float | None:
    """R2.3: the largest share of the summed net % held by one group (None when the sum is not positive)."""
    closed = _closed(trades)
    total = sum(float(t["net_pct"]) for t in closed)
    if total <= 0:
        return None
    groups: dict = {}
    for t in closed:
        groups[key(t)] = groups.get(key(t), 0.0) + float(t["net_pct"])
    return round(max(groups.values()) / total, 4)


def scorecard(trades: list[dict]) -> dict:
    closed = _closed(trades)
    if not closed:
        return {"trades": 0, "sessions": 0}
    nets = [float(t["net_pct"]) for t in closed]
    gross = [float(t["gross_pct"]) for t in closed]
    dates = sorted({t["date"] for t in closed})
    wins = sum(x > 0 for x in nets)
    return {"trades": len(nets), "sessions": len(dates), "wins": wins, "win_rate": round(wins / len(nets), 3),
            "avg_gross_pct": round(sum(gross) / len(gross), 3), "avg_net_pct": round(sum(nets) / len(nets), 3),
            "total_net_pct": round(sum(nets), 3), "max_drawdown_pts": max_drawdown(closed),
            "first": dates[0], "last": dates[-1]}


def review(trades: list[dict], sectors: dict, resamples: int = RESAMPLES, seed: int = SEED) -> dict:
    """R1-R3 verdict: NOT_YET, PASS or FAIL. sectors: symbol -> NIFTY 500 CSV Industry."""
    card = scorecard(trades)
    out = {**card, "ready": card["trades"] >= MIN_TRADES and card["sessions"] >= MIN_SESSIONS}
    dd = card.get("max_drawdown_pts", 0.0)
    if dd > MAX_DRAWDOWN:
        return {**out, "verdict": "FAIL", "reason": f"R3 early stop: drawdown {dd} points > {MAX_DRAWDOWN:g}"}
    if not out["ready"]:
        return {**out, "verdict": "NOT_YET",
                "reason": f"R1 needs {MIN_TRADES} closed trades and {MIN_SESSIONS} sessions"}
    nets = [float(t["net_pct"]) for t in _closed(trades)]
    lo, hi = bootstrap_ci(trades, resamples, seed)
    sym = max_share(trades, lambda t: t["symbol"])
    sec = max_share(trades, lambda t: sectors.get(t["symbol"]) or "UNKNOWN")
    checks = {"mean_net_above_zero": sum(nets) / len(nets) > 0, "ci95_above_zero": lo > 0,
              "symbol_share_ok": sym is not None and sym <= MAX_SYMBOL_SHARE,
              "sector_share_ok": sec is not None and sec <= MAX_SECTOR_SHARE,
              "drawdown_ok": dd <= MAX_DRAWDOWN}
    verdict = "PASS" if all(checks.values()) else "FAIL"
    reason = "R2: all checks pass" if verdict == "PASS" else "R2 failed: " + ", ".join(k for k, v in checks.items() if not v)
    return {**out, "ci95_net_pct": [lo, hi], "max_symbol_share": sym, "max_sector_share": sec,
            "checks": checks, "verdict": verdict, "reason": reason}
