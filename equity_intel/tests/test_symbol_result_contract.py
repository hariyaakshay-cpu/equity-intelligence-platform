"""SymbolScanResult contract shape tests -- no business logic, no I/O."""
from equity_intel.contracts.quality import DataStatus
from equity_intel.contracts.symbol_result import SymbolScanResult


def test_symbol_data_status_reuses_the_four_governed_data_status_values():
    result = SymbolScanResult(scan_run_id="R1", symbol="TCS", symbol_data_status=DataStatus.VALID)
    assert result.symbol_data_status in DataStatus


def test_flags_default_to_false_and_are_independent_of_status():
    result = SymbolScanResult(scan_run_id="R1", symbol="TCS", symbol_data_status=DataStatus.VALID)
    assert result.history_gaps_flag is False
    assert result.corporate_action_review_flag is False
    assert result.price_break_detected_flag is False
    assert result.non_eq_series_flag is False


def test_valid_status_can_still_carry_history_gaps_flag():
    result = SymbolScanResult(
        scan_run_id="R1",
        symbol="TCS",
        symbol_data_status=DataStatus.VALID,
        history_gaps_flag=True,
        missing_session_count=3,
    )
    assert result.symbol_data_status == DataStatus.VALID
    assert result.history_gaps_flag is True
    assert result.missing_session_count == 3


def test_optional_identity_fields_default_to_none():
    result = SymbolScanResult(scan_run_id="R1", symbol="TCS", symbol_data_status=DataStatus.FAILED)
    assert result.instrument_key is None
    assert result.isin is None
    assert result.series is None
    assert result.company_name is None
    assert result.sector is None
    assert result.status_reason is None


def test_symbol_scan_result_has_no_broker_or_oms_fields():
    result = SymbolScanResult(scan_run_id="R1", symbol="TCS", symbol_data_status=DataStatus.VALID)
    forbidden_substrings = ("broker", "order", "oms", "position", "execution")
    for name in result.__dataclass_fields__:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), name
