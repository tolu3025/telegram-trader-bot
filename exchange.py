import yfinance as yf
import re
from datetime import datetime, timezone

FIAT_CURRENCIES = {
    "EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY", 
    "SGD", "HKD", "SEK", "NOK", "DKK", "MXN", "ZAR", "TRY", 
    "CNH", "RUB", "INR"
}

KNOWN_CRYPTOS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "TON", 
    "SHIB", "AVAX", "DOT", "LINK", "LTC", "NEAR", "SUI", "PEPE",
    "WIF", "FET", "RNDR", "ICP", "UNI"
}

def normalize_symbol(symbol: str) -> str:
    """
    Normalizes forex symbols (e.g. 'EUR/USD', 'eurusd', 'USD-JPY') 
    and crypto symbols (e.g. 'BTC/USD', 'btcusd', 'BTC-USDT')
    to Yahoo Finance format (e.g. 'EURUSD=X', 'BTC-USD').
    """
    # Remove non-alphanumeric characters
    clean = re.sub(r'[^a-zA-Z0-9]', '', symbol).upper()
    
    # Special commodities standard for forex traders (Gold/Silver)
    if clean in ["XAUUSD", "GOLD"]:
        return "GC=F" # Gold Futures (Yahoo Finance standard)
    if clean in ["XAGUSD", "SILVER"]:
        return "SI=F" # Silver Futures
        
    # Check if it is a known crypto base ticker
    if clean in KNOWN_CRYPTOS:
        return f"{clean}-USD"
        
    # Check if it ends with USD or USDT
    if clean.endswith("USD") or clean.endswith("USDT"):
        suffix = "USD" if clean.endswith("USD") else "USDT"
        prefix = clean[:-3] if clean.endswith("USD") else clean[:-4]
        # If prefix is a known crypto or not in standard fiat list
        if prefix in KNOWN_CRYPTOS or prefix not in FIAT_CURRENCIES:
            return f"{prefix}-{suffix}"
            
    # Check if it already has the Yahoo Finance suffix
    if clean.endswith('X'):
        # e.g. EURUSD=X or EURUSDX
        if not clean.endswith('=X') and len(clean) == 7: # e.g. EURUSDX
            clean = clean[:-1] + '=X'
        return clean
    
    # Forex pairs are usually 6 letters (e.g. EURUSD)
    if len(clean) == 6:
        return f"{clean}=X"
        
    return clean

def is_forex_symbol(symbol: str) -> bool:
    """
    Returns True if the symbol is a Forex pair or Commodity.
    """
    norm = normalize_symbol(symbol)
    return norm.endswith("=X") or norm in ["GC=F", "SI=F"]

def is_market_closed_for_symbol(symbol: str) -> bool:
    """
    Checks if the market for a given symbol is currently closed.
    Forex markets are closed from Friday 21:00 UTC to Sunday 21:00 UTC and on major global holidays.
    Crypto markets never close.
    """
    if is_forex_symbol(symbol):
        now = datetime.now(timezone.utc)
        
        # Check for major fixed-date global forex holidays
        # Christmas Day (Dec 25) and New Year's Day (Jan 1)
        if (now.month == 12 and now.day == 25) or (now.month == 1 and now.day == 1):
            return True
            
        weekday = now.weekday() # Monday is 0, Sunday is 6
        if weekday == 4 and now.hour >= 21:
            return True
        if weekday == 5:
            return True
        if weekday == 6 and now.hour < 21:
            return True
    return False


def get_live_price(symbol: str) -> float:
    """
    Fetches the live price of a Forex pair or commodity from Yahoo Finance.
    Returns float price.
    """
    ticker_str = normalize_symbol(symbol)
    ticker = yf.Ticker(ticker_str)
    
    # Try fast_info
    try:
        price = ticker.fast_info.last_price
        if price is not None and price > 0:
            return float(price)
    except Exception:
        pass
        
    # Try history (1-minute intervals for last day)
    try:
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            price = df['Close'].iloc[-1]
            if price is not None and price > 0:
                return float(price)
    except Exception:
        pass
        
    # Try downloading history directly
    try:
        data = yf.download(ticker_str, period="1d", interval="1m", progress=False)
        if not data.empty:
            price = data['Close'].iloc[-1]
            if price is not None:
                # pandas download might return a series or single float depending on multi-index
                if hasattr(price, 'item'):
                    price = price.item()
                price = float(price)
                if price > 0:
                    return price
    except Exception:
        pass

    # Final fallback: ticker.info (can be slow/throttled)
    try:
        info = ticker.info
        for key in ['regularMarketPrice', 'ask', 'bid', 'previousClose']:
            if key in info and info[key] is not None and info[key] > 0:
                return float(info[key])
    except Exception:
        pass

    raise ValueError(f"Could not fetch live rate for ticker '{ticker_str}' (original: '{symbol}')")

def is_valid_symbol(symbol: str) -> bool:
    """Verifies if the symbol has a fetchable price."""
    try:
        price = get_live_price(symbol)
        return price > 0
    except Exception:
        return False

def get_market_summary(symbols: list) -> str:
    """
    Downloads recent price history for a list of symbols and generates a 
    structured technical summary (spot, high, low, SMA indicators) for the AI.
    """
    summary_parts = []
    for sym in symbols:
        try:
            norm_sym = normalize_symbol(sym)
            ticker = yf.Ticker(norm_sym)
            
            # Download 5 days of 1-hour bars
            df = ticker.history(period="5d", interval="1h")
            if df.empty:
                continue
                
            close_prices = df['Close']
            # If multi-index, grab first column
            if hasattr(close_prices, 'columns'):
                close_prices = close_prices.iloc[:, 0]
                
            close_prices = close_prices.astype(float)
            spot = float(close_prices.iloc[-1])
            
            # High/Low of last 24 bars (roughly 24 hours of trading time)
            recent_bars = df.tail(min(24, len(df)))
            high_24h = float(recent_bars['High'].max()) if 'High' in recent_bars.columns else spot
            low_24h = float(recent_bars['Low'].min()) if 'Low' in recent_bars.columns else spot
            
            # Handle multi-index columns for high/low fallback
            if hasattr(high_24h, 'item'): high_24h = high_24h.item()
            if hasattr(low_24h, 'item'): low_24h = low_24h.item()
            
            # Calculate SMAs
            sma_20 = float(close_prices.rolling(window=min(20, len(close_prices))).mean().iloc[-1])
            sma_50 = float(close_prices.rolling(window=min(50, len(close_prices))).mean().iloc[-1])
            
            trend = "BULLISH" if spot > sma_20 else "BEARISH"
            
            display_name = sym.upper().replace("=X", "")
            decimals = 2 if spot >= 100 else 5
            summary_parts.append(
                f"Asset: {display_name} ({norm_sym})\n"
                f"- Current Spot Rate: {spot:.{decimals}f}\n"
                f"- 24h High: {high_24h:.{decimals}f} | 24h Low: {low_24h:.{decimals}f}\n"
                f"- 20h SMA: {sma_20:.{decimals}f} | 50h SMA: {sma_50:.{decimals}f}\n"
                f"- Short-term Trend: {trend} (relative to 20h SMA)\n"
            )
        except Exception as e:
            print(f"Error summarising {sym}: {e}")
            
    if not summary_parts:
        return "Unable to retrieve market data summary."
        
    return "\n---\n".join(summary_parts)
