"""Scanner shell proves the process shape only -- no business decision."""
import pytest

from equity_intel.scanner.shell import ScanPipeline


def test_pipeline_does_not_fabricate_a_universe_or_market_data():
    pipeline = ScanPipeline()
    with pytest.raises(NotImplementedError):
        pipeline._load_universe()
    with pytest.raises(NotImplementedError):
        pipeline._load_market_data()


def test_pipeline_does_not_fabricate_scores_classifications_or_candidates():
    pipeline = ScanPipeline()
    with pytest.raises(NotImplementedError, match="B2 scoring thresholds"):
        pipeline._score()
    with pytest.raises(NotImplementedError, match="B2 classification triggers"):
        pipeline._classify()
    with pytest.raises(NotImplementedError, match="D11"):
        pipeline._select_candidates()
    with pytest.raises(NotImplementedError, match="D12"):
        pipeline._persist_watchlist()


def test_pipeline_run_stops_before_any_unresolved_decision():
    pipeline = ScanPipeline()
    with pytest.raises(NotImplementedError):
        result = pipeline.run()
