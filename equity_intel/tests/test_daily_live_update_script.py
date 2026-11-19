"""scripts/equity_daily_live_update.py with a fake Upstox session (tmp dir only)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import equity_daily_live_update as upd  # noqa: E402


class Resp:
    def __init__(self, status, candles=None):
        self.status_code, self._c = status, candles or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"status": "success", "data": {"candles": self._c}}


def _setup(tmp_path, monkeypatch, replies):
    d = tmp_path / "daily_live"
    d.mkdir()
    for sym in ("KEC", "NIFTY500_INDEX"):
        (d / f"{sym}.csv").write_text("date,o,h,l,c,v\n2026-11-16,1.0,1.0,1.0,1.0,10.0\n2026-11-17,2.0,2.0,2.0,2.0,20.0\n")
    monkeypatch.setattr(upd, "DAILY", d)
    monkeypatch.setattr(upd, "PAUSE", 0)
    monkeypatch.setattr(upd, "keys", lambda: {"KEC": "NSE_EQ|K", "NIFTY500_INDEX": "NSE_INDEX|Nifty 500"})
    monkeypatch.setattr(upd.time, "sleep", lambda s: None)
    calls = []

    def get(self, url, timeout):
        calls.append(url)
        return replies.pop(0)
    monkeypatch.setattr(upd.requests.Session, "get", get)
    return d, calls


C17 = ["2026-11-17T00:00:00+05:30", 2, 2, 2, 2.5, 21, 0]
C18 = ["2026-11-18T00:00:00+05:30", 3, 3.5, 2.9, 3.2, 30, 0]


def test_merges_new_day_replaces_overlap_and_keeps_history(tmp_path, monkeypatch):
    d, calls = _setup(tmp_path, monkeypatch, [Resp(200, [C18, C17]), Resp(429), Resp(200, [C18])])
    assert upd.main() == 0
    rows = (d / "KEC.csv").read_text().splitlines()
    assert rows == ["date,o,h,l,c,v", "2026-11-16,1.0,1.0,1.0,1.0,10.0",
                    "2026-11-17,2.0,2.0,2.0,2.5,21.0", "2026-11-18,3.0,3.5,2.9,3.2,30.0"]
    assert "/days/1/" in calls[0] and calls[0].endswith("/2026-11-10")          # 7 days before 17 Nov
    assert (d / "NIFTY500_INDEX.csv").read_text().splitlines()[-1].startswith("2026-11-18")   # after one 429 retry


def test_failed_stock_keeps_its_file_and_index_failure_returns_1(tmp_path, monkeypatch):
    d, _ = _setup(tmp_path, monkeypatch, [Resp(500), Resp(500)])
    before = (d / "KEC.csv").read_text()
    assert upd.main() == 1 and (d / "KEC.csv").read_text() == before
