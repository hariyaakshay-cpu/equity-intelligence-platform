"""Scanner orchestration shell -- stages only, no business logic.

    load universe
        -> load market data
        -> validate data
        -> compute raw features
        -> score              (BLOCKED: B2 band tables unresolved)
        -> classify           (BLOCKED: B2 trigger thresholds unresolved)
        -> select candidates  (BLOCKED: B2 candidate cutoff D11 unresolved)
        -> persist watchlist  (BLOCKED: B2 watchlist size D12 unresolved)

Every stage after "compute raw features" raises NotImplementedError naming
the exact governance gate blocking it. This module never fabricates a
candidate list, a watchlist, or any placeholder score. It contains no
import of brokers.*, core.paper_engine, core.continuous_engine,
core.execution_engine, core.oms.order_router, core.oms.execution_service,
core.oms.paper_oms_adapter, core.oms.db, core.risk_manager, strategies.*,
main, or core.historical_data -- see equity_intel/tests/test_import_boundaries.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from equity_intel.contracts.market_data import InstrumentMember
from equity_intel.contracts.scoring import ScoringConfig
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded


class ScanBlockedError(RuntimeError):
    """Raised when a stage cannot proceed because it depends on an
    unresolved B2 or B3 governance decision."""


@dataclass
class ScanPipelineResult:
    """Records only which stages ran, never a fabricated business result."""

    stages_completed: List[str] = field(default_factory=list)


class ScanPipeline:
    """A non-functional shell proving the intended process shape.

    Instantiating and running this class never produces a real universe,
    real market data, a real score, a real candidate, or a real watchlist
    row. It exists to establish the process boundary (separate from
    algo_trader's main.py / core/continuous_engine.py) and to prove that
    the forbidden-module guard (assert_no_forbidden_modules_loaded(),
    checking FORBIDDEN_PREFIXES in execution_guard.py) runs before any
    stage.
    """

    def __init__(self, scoring_config: ScoringConfig | None = None) -> None:
        self._scoring_config = scoring_config or ScoringConfig()

    def run(self) -> ScanPipelineResult:
        assert_no_forbidden_modules_loaded()
        result = ScanPipelineResult()
        self._load_universe()
        result.stages_completed.append("load_universe")
        self._load_market_data()
        result.stages_completed.append("load_market_data")
        self._validate_data()
        result.stages_completed.append("validate_data")
        self._compute_features()
        result.stages_completed.append("compute_features")
        self._score()
        return result

    def _load_universe(self) -> "list[InstrumentMember]":
        raise NotImplementedError(
            "B3 NIFTY 500 universe source is BLOCKED (not yet selected)"
        )

    def _load_market_data(self) -> None:
        raise NotImplementedError(
            "B3 market-data vendor is BLOCKED (not yet selected)"
        )

    def _validate_data(self) -> None:
        raise NotImplementedError(
            "B3 validation thresholds (minimum history, volume usability, "
            "trading calendar) are BLOCKED (unresolved; see D18/D19)"
        )

    def _compute_features(self) -> None:
        raise NotImplementedError(
            "Raw feature computation requires real market data from a "
            "BLOCKED B3 source"
        )

    def _score(self) -> None:
        raise NotImplementedError(
            "B2 scoring thresholds are not yet authoritative "
            "(see B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md, Section 18)"
        )

    def _classify(self) -> None:
        raise NotImplementedError(
            "B2 classification triggers are not yet authoritative (D10)"
        )

    def _select_candidates(self) -> None:
        raise NotImplementedError(
            "B2 candidate cutoff is UNRESOLVED (D11: AUTHORITY: NONE)"
        )

    def _persist_watchlist(self) -> None:
        raise NotImplementedError(
            "B2 watchlist size is UNRESOLVED (D12: AUTHORITY: NONE); "
            "data/equity_intel.db does not exist yet"
        )
