"""Abstract repository interfaces -- no concrete data source.

None of these classes connects to a database, a broker, or a market-data
vendor. Each abstract method raises NotImplementedError. A concrete
implementation is out of scope for this scaffold and requires a
separately authorized task once B3 (data source) and, where relevant, B2
are resolved.
"""
from __future__ import annotations

import abc
from typing import Iterable, Optional, Sequence

from equity_intel.contracts.candidate import Candidate, WatchlistEntry
from equity_intel.contracts.classification import ClassificationResult
from equity_intel.contracts.features import FeatureSet
from equity_intel.contracts.market_data import BenchmarkObservation, InstrumentMember, OHLCVObservation
from equity_intel.contracts.quality import DataQualityResult
from equity_intel.contracts.scoring import CompositeResult


class UniverseRepository(abc.ABC):
    """Source of the NIFTY 500 (or other) universe membership. Which
    source/vendor this reads from is an unresolved B3 decision."""

    @abc.abstractmethod
    def list_members(self) -> Iterable[InstrumentMember]:
        raise NotImplementedError(
            "B3 NIFTY 500 universe source is not yet selected"
        )


class MarketDataRepository(abc.ABC):
    """Source of per-instrument OHLCV history and the benchmark series.
    Which vendor this reads from is an unresolved B3 decision."""

    @abc.abstractmethod
    def get_observations(self, instrument_id: str) -> Sequence[OHLCVObservation]:
        raise NotImplementedError("B3 market-data vendor is not yet selected")

    @abc.abstractmethod
    def get_benchmark_observations(self, benchmark_id: str) -> Sequence[BenchmarkObservation]:
        raise NotImplementedError("B3 benchmark source is not yet selected")


class FeatureRepository(abc.ABC):
    @abc.abstractmethod
    def save_features(self, scan_id: str, features: FeatureSet) -> None:
        raise NotImplementedError("Persistence target data/equity_intel.db does not exist yet")

    @abc.abstractmethod
    def save_quality(self, scan_id: str, quality: DataQualityResult) -> None:
        raise NotImplementedError("Persistence target data/equity_intel.db does not exist yet")


class ScoreRepository(abc.ABC):
    @abc.abstractmethod
    def save_composite(self, scan_id: str, composite: CompositeResult) -> None:
        raise NotImplementedError("Persistence target data/equity_intel.db does not exist yet")

    @abc.abstractmethod
    def save_classification(self, scan_id: str, classification: ClassificationResult) -> None:
        raise NotImplementedError("Persistence target data/equity_intel.db does not exist yet")


class CandidateRepository(abc.ABC):
    @abc.abstractmethod
    def save_candidate(self, candidate: Candidate) -> None:
        raise NotImplementedError(
            "B2 candidate cutoff (D11) is unresolved; no candidate may be persisted"
        )


class WatchlistRepository(abc.ABC):
    """The terminal boundary. A concrete implementation of this interface
    may ONLY write to a paper_watchlist table. It must never call a
    broker, the OMS, or core.paper_engine."""

    @abc.abstractmethod
    def save_watchlist_entry(self, entry: WatchlistEntry) -> None:
        raise NotImplementedError(
            "B2 watchlist size (D12) is unresolved; no watchlist entry may be persisted"
        )
