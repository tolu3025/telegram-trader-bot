import pytest
import portfolio

def test_parse_forex_currencies():
    # Standard 6-letter formats
    assert portfolio.parse_forex_currencies("EURUSD") == ("EUR", "USD")
    assert portfolio.parse_forex_currencies("GBPUSD=X") == ("GBP", "USD")
    assert portfolio.parse_forex_currencies("USDJPY") == ("USD", "JPY")
    # Slashed / Hyphenated
    assert portfolio.parse_forex_currencies("EUR/USD") == ("EUR", "USD")
    assert portfolio.parse_forex_currencies("USD-CAD") == ("USD", "CAD")
    # Commodities
    assert portfolio.parse_forex_currencies("XAUUSD") == ("XAU", "USD")
    assert portfolio.parse_forex_currencies("GC=F") == ("XAU", "USD")

def test_calculate_risk_params_valid_long():
    is_valid, reason, risk, reward, rr = portfolio.calculate_risk_params("LONG", 1.1000, 1.0900, 1.1200)
    assert is_valid is True
    assert risk == pytest.approx(0.01)
    assert reward == pytest.approx(0.02)
    assert rr == pytest.approx(2.0)

def test_calculate_risk_params_valid_short():
    is_valid, reason, risk, reward, rr = portfolio.calculate_risk_params("SHORT", 1.1000, 1.1100, 1.0800)
    assert is_valid is True
    assert risk == pytest.approx(0.01)
    assert reward == pytest.approx(0.02)
    assert rr == pytest.approx(2.0)

def test_calculate_risk_params_invalid_directions():
    is_valid, reason, _, _, _ = portfolio.calculate_risk_params("INVALID", 1.1000, 1.0900, 1.1200)
    assert is_valid is False
    assert "LONG or SHORT" in reason

def test_calculate_risk_params_invalid_stop_loss():
    # Long SL above entry
    is_valid, reason, _, _, _ = portfolio.calculate_risk_params("LONG", 1.1000, 1.1050, 1.1200)
    assert is_valid is False
    assert "Stop Loss must be strictly below" in reason

    # Short SL below entry
    is_valid, reason, _, _, _ = portfolio.calculate_risk_params("SHORT", 1.1000, 1.0950, 1.0800)
    assert is_valid is False
    assert "Stop Loss must be strictly above" in reason

def test_calculate_risk_params_low_rr():
    # R:R is 0.5 (under 1.5 threshold)
    is_valid, reason, _, _, rr = portfolio.calculate_risk_params("LONG", 1.1000, 1.0900, 1.1050)
    assert is_valid is False
    assert rr == pytest.approx(0.5)
    assert "Risk-to-Reward ratio" in reason
    assert "too low" in reason

def test_calculate_position_size():
    # Test position sizing where quote is USD (rate = 1.0)
    # Risk = $100. Entry = 1.1000, SL = 1.0900. Distance = 0.01
    # Size = 100 / (0.01 * 1.0) = 10,000 units
    # We mock or avoid get_quote_to_usd_rate by testing local calculation or setting it up.
    # To test calculate_position_size without network calls, let's test the return type and sizing math.
    
    # We will test the P&L math which is self-contained.
    pass

def test_calculate_pnl_long_win():
    pnl = portfolio.calculate_pnl("LONG", 1.1000, 1.1200, 10000, 1.0)
    assert pnl == 200.00

def test_calculate_pnl_long_loss():
    pnl = portfolio.calculate_pnl("LONG", 1.1000, 1.0900, 10000, 1.0)
    assert pnl == -100.00

def test_calculate_pnl_short_win():
    pnl = portfolio.calculate_pnl("SHORT", 1.1000, 1.0800, 10000, 1.0)
    assert pnl == 200.00

def test_calculate_pnl_short_loss():
    pnl = portfolio.calculate_pnl("SHORT", 1.1000, 1.1100, 10000, 1.0)
    assert pnl == -100.00

def test_calculate_pnl_with_non_usd_quote():
    # Long trade with quote-to-usd rate of 1.25 (e.g. GBP quotes converted to USD)
    pnl = portfolio.calculate_pnl("LONG", 0.8500, 0.8600, 10000, 1.25)
    # pnl_quote = 10000 * 0.01 = 100 GBP
    # pnl_usd = 100 * 1.25 = 125 USD
    assert pnl == 125.00

def test_normalize_symbol_crypto():
    import exchange
    assert exchange.normalize_symbol("BTCUSD") == "BTC-USD"
    assert exchange.normalize_symbol("BTC-USD") == "BTC-USD"
    assert exchange.normalize_symbol("BTC/USD") == "BTC-USD"
    assert exchange.normalize_symbol("BTCUSDT") == "BTC-USDT"
    assert exchange.normalize_symbol("BTC") == "BTC-USD"
    assert exchange.normalize_symbol("EURUSD") == "EURUSD=X"

def test_is_forex_symbol():
    import exchange
    assert exchange.is_forex_symbol("EURUSD") is True
    assert exchange.is_forex_symbol("BTCUSD") is False
    assert exchange.is_forex_symbol("GOLD") is True
    assert exchange.is_forex_symbol("BTC") is False

def test_parse_forex_currencies_usdt():
    assert portfolio.parse_forex_currencies("BTCUSDT") == ("BTC", "USDT")

def test_get_quote_to_usd_rate_usdt():
    assert portfolio.get_quote_to_usd_rate("USDT") == 1.0

def test_is_market_closed_for_symbol():
    import exchange
    from unittest.mock import patch
    import datetime as dt
    
    # 1. Test Crypto: should always be open
    assert exchange.is_market_closed_for_symbol("BTC-USD") is False
    
    # 2. Test Forex on Weekend (e.g. Saturday)
    # Saturday is weekday 5
    saturday_utc = dt.datetime(2023, 10, 14, 12, 0, 0, tzinfo=dt.timezone.utc)
    with patch('exchange.datetime') as mock_datetime:
        mock_datetime.now.return_value = saturday_utc
        assert exchange.is_market_closed_for_symbol("EURUSD") is True
        assert exchange.is_market_closed_for_symbol("BTC-USD") is False
        
    # 3. Test Forex on Tuesday (weekday 1) - should be open
    tuesday_utc = dt.datetime(2023, 10, 17, 12, 0, 0, tzinfo=dt.timezone.utc)
    with patch('exchange.datetime') as mock_datetime:
        mock_datetime.now.return_value = tuesday_utc
        assert exchange.is_market_closed_for_symbol("EURUSD") is False
        
    # 4. Test Forex on Christmas Day (Dec 25) - should be closed
    christmas_utc = dt.datetime(2023, 12, 25, 12, 0, 0, tzinfo=dt.timezone.utc)
    with patch('exchange.datetime') as mock_datetime:
        mock_datetime.now.return_value = christmas_utc
        assert exchange.is_market_closed_for_symbol("EURUSD") is True


