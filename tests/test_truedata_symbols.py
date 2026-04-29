from app.data.symbols import (
    canonicalize_instrument,
    truedata_historical_symbol,
    truedata_options_chain_symbol,
    truedata_to_internal_symbol,
    truedata_ws_symbol,
)


def test_india_vix_aliases_are_canonicalized() -> None:
    assert canonicalize_instrument("INDIA VIX") == "INDIAVIX"
    assert canonicalize_instrument("indiavix") == "INDIAVIX"
    assert truedata_ws_symbol("INDIAVIX") == "INDIA VIX"
    assert truedata_historical_symbol("INDIAVIX") == "INDIA VIX"
    assert truedata_to_internal_symbol("INDIA VIX") == "INDIAVIX"


def test_nifty_symbols_are_split_by_api_surface() -> None:
    assert canonicalize_instrument("NIFTY-I") == "NIFTY"
    assert truedata_ws_symbol("NIFTY") == "NIFTY-I"
    assert truedata_historical_symbol("NIFTY") == "NIFTY-I"
    assert truedata_options_chain_symbol("NIFTY-I") == "NIFTY"
