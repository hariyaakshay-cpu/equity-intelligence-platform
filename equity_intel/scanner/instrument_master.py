"""Acquisition of the Upstox NSE instrument master.

Upstox has no authenticated REST endpoint for this (core/providers/
upstox_provider.py's get_instruments() calls GET v3/market/instruments,
which returns a live 404 -- confirmed against the real API on 2026-09-28;
the same call is what services/instrument_sync_service.py's NSE sync uses
too, so that sync is broken the same way, independent of this module).
Per direct instruction, neither of those two files is touched here.

The real instrument master is instead a public, unauthenticated, gzipped
JSON file per exchange:

    https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz

confirmed live: 77,668 rows, each a dict with (at least) the fields
segment, name, exchange, isin, instrument_type, instrument_key, lot_size,
freeze_quantity, exchange_token, tick_size, trading_symbol, qty_multiplier,
security_type. This module downloads and parses that file; instrument_
mapping.py filters it. See equity_intel/scanner/instrument_mapping.py's
module docstring for the segment/instrument_type filter itself.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import requests

from equity_intel.config import IST

NSE_INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

# Recorded as scan_runs.abort_reason when the instrument master could not
# be downloaded at all (network failure, non-200 response, or a body that
# doesn't gunzip/parse as JSON) -- distinct from INSTRUMENT_MAP_EMPTY
# (instrument_mapping.py), which is a successful download that then
# matched zero of the universe's ISINs. Wiring the actual RUNNING ->
# ABORTED transition is Phase 3's ScanRun lifecycle work.
INSTRUMENT_MASTER_UNAVAILABLE = "INSTRUMENT_MASTER_UNAVAILABLE"

_DOWNLOAD_TIMEOUT_SECONDS = 30


class InstrumentMasterUnavailableError(RuntimeError):
    """Raised when the instrument master cannot be downloaded, or the
    downloaded/given file cannot be read as gzipped JSON."""


@dataclass(frozen=True)
class InstrumentMaster:
    """One loaded instrument master: its raw rows plus enough provenance
    to record on the ScanRun (see instrument_mapping.map_universe_isins,
    which consumes this directly)."""

    rows: List[dict]
    source: str  # the URL fetched, or the local file path given
    fetched_at: str  # IST, +05:30 offset
    file_sha256: str
    total_rows: int


def _now_ist(now: Optional[datetime]) -> datetime:
    return now if now is not None else datetime.now(IST)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_gzip_json(data: bytes) -> List[dict]:
    try:
        decompressed = gzip.decompress(data)
        rows = json.loads(decompressed)
    except (OSError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        raise InstrumentMasterUnavailableError(f"instrument master is not valid gzipped JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise InstrumentMasterUnavailableError(
            f"instrument master JSON root must be a list, got {type(rows).__name__}"
        )
    return rows


def fetch_and_save_instrument_master(
    dest_dir: Union[str, Path],
    *,
    url: str = NSE_INSTRUMENT_MASTER_URL,
    now: Optional[datetime] = None,
) -> Path:
    """Download the instrument master and save it under `dest_dir` as
    upstox_NSE_instruments_<YYYY-MM-DD>_<sha256[:8]>.json.gz (matching the
    naming convention data/reference/*.json.gz already uses and is
    gitignored for -- see .gitignore). The sha256 prefix is not cosmetic:
    without it, a second download on the same calendar day (e.g. a smoke
    run followed by the full run, or a retry after a partial failure)
    would silently overwrite the file an earlier run's
    instrument_map_provenance_json.source/file_sha256 still points to.
    `dest_dir` is created if it doesn't exist.

    Raises:
        InstrumentMasterUnavailableError: on any network failure, timeout,
            or non-200 response. Never lets a requests exception escape
            directly -- the caller (Phase 3's ScanRun lifecycle) catches
            exactly this one exception type to abort the run with
            abort_reason=INSTRUMENT_MASTER_UNAVAILABLE.
    """
    try:
        response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise InstrumentMasterUnavailableError(f"failed to download instrument master from {url}: {exc}") from exc

    date_str = _now_ist(now).date().isoformat()
    sha8 = _sha256_bytes(response.content)[:8]
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"upstox_NSE_instruments_{date_str}_{sha8}.json.gz"
    dest_path.write_bytes(response.content)
    return dest_path


def load_instrument_master(
    path: Union[str, Path],
    *,
    source: Optional[str] = None,
    now: Optional[datetime] = None,
) -> InstrumentMaster:
    """Load an already-downloaded (or offline/test fixture) instrument
    master file from disk.

    `source` defaults to str(path) -- pass the original download URL
    explicitly (e.g. from fetch_instrument_master) when the on-disk path
    is just a local cache and the URL is the more meaningful provenance
    value.

    Raises:
        InstrumentMasterUnavailableError: if the file doesn't exist or
            isn't valid gzipped JSON.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InstrumentMasterUnavailableError(f"cannot read instrument master file {path}: {exc}") from exc

    rows = _parse_gzip_json(data)
    return InstrumentMaster(
        rows=rows,
        source=source or str(path),
        fetched_at=_now_ist(now).isoformat(),
        file_sha256=_sha256_bytes(data),
        total_rows=len(rows),
    )


def fetch_instrument_master(
    dest_dir: Union[str, Path],
    *,
    url: str = NSE_INSTRUMENT_MASTER_URL,
    now: Optional[datetime] = None,
) -> InstrumentMaster:
    """Download the instrument master, save it under `dest_dir`, and load
    it in one step -- the normal (online) path for a real scan run.
    `source` on the returned InstrumentMaster is `url`, not the local
    cache path, since the URL is what actually identifies the data.
    """
    at = _now_ist(now)
    path = fetch_and_save_instrument_master(dest_dir, url=url, now=at)
    return load_instrument_master(path, source=url, now=at)
