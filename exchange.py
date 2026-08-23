import yfinance as yf
import re
from datetime import datetime, timezone

FIAT_CURRENCIES = {
    "EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY", 
    "SGD", "HKD", "SEK", "NOK", "DKK", "MXN", "ZAR", "TRY", 
    "CNH", "RUB", "INR"
}

KNOWN_CRYPTOS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LTC", "BCH", "LINK",
    "AVAX", "SHIB", "DOT", "UNI", "NEAR", "ICP", "APT", "SUI", "AAVE", "FTM",
    "GRT", "LDO", "OP", "ARB", "TIA", "IMX", "FET", "FIL", "HBAR", "ATOM",
    "VET", "ETC", "ALGO", "RUNE", "EGLD", "FLOW", "SAND", "MANA", "GALA", "LRC",
    "BAT", "ENJ", "ANKR", "KNC", "ZRX", "ONT", "QTUM", "ZEC", "DASH", "WAVES",
    "OMG", "ICX", "COMP", "SUSHI", "CRV",
    "POPCAT", "PIE", "TRX", "TRON"
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

def detect_support_resistance(df, spot: float, window: int = 5) -> tuple:
    """
    Finds swing highs and swing lows to identify static support and resistance levels near the spot price.
    """
    if df.empty or len(df) < (window * 2 + 1):
        return [], []
        
    highs = df['High'].values
    lows = df['Low'].values
    n = len(df)
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, n - window):
        # Check swing high
        is_high = True
        for j in range(1, window + 1):
            if highs[i] < highs[i-j] or highs[i] < highs[i+j]:
                is_high = False
                break
        if is_high:
            swing_highs.append(float(highs[i]))
            
        # Check swing low
        is_low = True
        for j in range(1, window + 1):
            if lows[i] > lows[i-j] or lows[i] > lows[i+j]:
                is_low = False
                break
        if is_low:
            swing_lows.append(float(lows[i]))
            
    # Filter support levels (below spot) and resistance levels (above spot)
    supports = [s for s in swing_lows if s < spot]
    resistances = [r for r in swing_highs if r > spot]
    
    # Sort: supports descending (closest first), resistances ascending (closest first)
    supports.sort(reverse=True)
    resistances.sort()
    
    # De-duplicate close levels (within 0.3%)
    def deduplicate(levels):
        deduped = []
        for lvl in levels:
            if not deduped or all(abs(lvl - d) / d > 0.003 for d in deduped):
                deduped.append(lvl)
        return deduped
        
    supports = deduplicate(supports)[:3] # Top 3 closest supports
    resistances = deduplicate(resistances)[:3] # Top 3 closest resistances
    
    # Fallback to rolling min/max if no swing levels found
    if not supports and not df.empty:
        supports = [float(df['Low'].min())]
    if not resistances and not df.empty:
        resistances = [float(df['High'].max())]
        
    return supports, resistances

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
    from concurrent.futures import ThreadPoolExecutor
    summary_parts = []
    
    def process_symbol(sym):
        try:
            norm_sym = exchange.normalize_symbol(sym) if 'exchange' in globals() else normalize_symbol(sym)
            ticker = yf.Ticker(norm_sym)
            
            # Download 5 days of 1-hour bars
            df = ticker.history(period="5d", interval="1h")
            if df.empty:
                return None
                
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
            
            # Detect support and resistance
            supports, resistances = detect_support_resistance(df, spot)
            
            display_name = sym.upper().replace("=X", "")
            decimals = 2 if spot >= 100 else 5
            
            support_str = ", ".join(f"{s:.{decimals}f}" for s in supports) if supports else "None detected"
            resistance_str = ", ".join(f"{r:.{decimals}f}" for r in resistances) if resistances else "None detected"
            
            return (
                f"Asset: {display_name} ({norm_sym})\n"
                f"- Current Spot Rate: {spot:.{decimals}f}\n"
                f"- 24h High: {high_24h:.{decimals}f} | 24h Low: {low_24h:.{decimals}f}\n"
                f"- Dynamic Support/Resistance: SMA 20 ({sma_20:.{decimals}f}) | SMA 50 ({sma_50:.{decimals}f})\n"
                f"- Detected Static Support (Swing Lows): {support_str}\n"
                f"- Detected Static Resistance (Swing Highs): {resistance_str}\n"
                f"- Short-term Trend: {trend} (relative to 20h SMA)\n"
            )
        except Exception as e:
            print(f"Error summarising {sym}: {e}")
            return None

    # Process in parallel using a thread pool
    with ThreadPoolExecutor(max_workers=min(len(symbols), 20)) as executor:
        results = executor.map(process_symbol, symbols)
        
    for res in results:
        if res:
            summary_parts.append(res)
            
    if not summary_parts:
        return "Unable to retrieve market data summary."
        
    return "\n---\n".join(summary_parts)
