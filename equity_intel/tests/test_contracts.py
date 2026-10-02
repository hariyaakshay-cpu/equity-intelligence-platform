"""Contracts hold shape only: no default business values."""
from datetime import date

from equity_intel.contracts.candidate import Candidate, WatchlistEntry
from equity_intel.contracts.classification import ClassificationResult
from equity_intel.contracts.features import FeatureSet
from equity_intel.contracts.market_data import BenchmarkObservation, InstrumentMember, OHLCVObservation
from equity_intel.contracts.quality import DataQualityResult, DataStatus
from equity_intel.contracts.scoring import ComponentResult, CompositeResult, ScoringConfig
from equity_intel.contracts.state import ScanState


def test_ohlcv_observation_has_no_default_values():
    obs = OHLCVObservation(
        instrument_id="X", observation_date=date(2026, 1, 1), high=1.0, low=1.0, close=1.0, volume=None
    )
    assert obs.volume is None


def test_instrument_member_defaults_are_all_none_or_unset():
    member = InstrumentMember(symbol="X")
    assert member.sector is None
    assert member.secondary_vendor_ticker is None
    assert member.active is None


def test_data_status_vocabulary_is_exactly_the_four_governed_values():
    assert {s.value for s in DataStatus} == {"VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED"}


def test_data_quality_result_reason_is_free_form_not_enum():
    result = DataQualityResult(status=DataStatus.FAILED, reason="DQ_BAD_BARS")
    assert isinstance(result.reason, str)


def test_feature_set_defaults_are_all_none():
    fs = FeatureSet(instrument_id="X")
    assert fs.ema_short is None
    assert fs.rsi is None
    assert fs.relative_volume is None
    assert fs.distance_from_high is None
    assert fs.atr_percent is None


def test_component_result_score_has_no_hardcoded_default():
    cr = ComponentResult(component_name="trend")
    assert cr.score is None


def test_composite_result_default_composite_is_none_not_zero():
    comp = CompositeResult(instrument_id="X")
    assert comp.composite is None
    assert comp.components == ()


def test_scoring_config_carries_no_default_cutoff_or_watchlist_size():
    config = ScoringConfig()
    assert config.candidate_cutoff is None
    assert config.watchlist_limit is None
    assert config.score_version is None


def test_classification_result_is_free_form_not_frozen_vocabulary():
    result = ClassificationResult(instrument_id="X")
    assert result.tags == []
    assert result.primary is None
    # Free-form: any string may be appended, nothing constrains it to a
    # pre-approved vocabulary member.
    result2 = ClassificationResult(instrument_id="X", tags=["ANYTHING_AT_ALL"], primary="ANYTHING_AT_ALL")
    assert result2.tags == ["ANYTHING_AT_ALL"]


def test_scan_state_vocabulary_matches_the_four_architected_states():
    assert {s.value for s in ScanState} == {"SCORED", "ELIGIBLE", "CANDIDATE", "WATCHLISTED"}


def test_candidate_and_watchlist_entry_have_no_broker_or_oms_fields():
    candidate = Candidate(instrument_id="X", scan_id="S1", state=ScanState.SCORED)
    watchlist_entry = WatchlistEntry(instrument_id="X", scan_id="S1")
    for record in (candidate, watchlist_entry):
        field_names = {f for f in record.__dataclass_fields__}
        forbidden_substrings = ("broker", "order", "oms", "position", "execution")
        for name in field_names:
            lowered = name.lower()
            assert not any(bad in lowered for bad in forbidden_substrings), name


def test_benchmark_observation_does_not_select_a_benchmark_source():
    obs = BenchmarkObservation(benchmark_id="whatever-caller-picks", observation_date=date(2026, 1, 1), close=100.0)
    assert obs.benchmark_id == "whatever-caller-picks"
