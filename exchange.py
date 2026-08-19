import yfinance as yf
import re

def normalize_symbol(symbol: str) -> str:
    """
    Normalizes forex symbols (e.g. 'EUR/USD', 'eurusd', 'USD-JPY') 
    to Yahoo Finance format (e.g. 'EURUSD=X', 'USDJPY=X').
    """
    # Remove non-alphanumeric characters
    clean = re.sub(r'[^a-zA-Z0-9]', '', symbol).upper()
    
    # Check if it already has the Yahoo Finance suffix
    if clean.endswith('X'):
        # e.g. EURUSD=X or EURUSDX
        if not clean.endswith('=X') and len(clean) == 7: # e.g. EURUSDX
            clean = clean[:-1] + '=X'
        return clean
    
    # Forex pairs are usually 6 letters (e.g. EURUSD)
    if len(clean) == 6:
        return f"{clean}=X"
    
    # Special commodities standard for forex traders (Gold/Silver)
    if clean == "XAUUSD" or clean == "GOLD":
        return "GC=F" # Gold Futures (Yahoo Finance standard)
    if clean == "XAGUSD" or clean == "SILVER":
        return "SI=F" # Silver Futures
        
    return clean

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
            summary_parts.append(
                f"Asset: {display_name} ({norm_sym})\n"
                f"- Current Spot Rate: {spot:.5f}\n"
                f"- 24h High: {high_24h:.5f} | 24h Low: {low_24h:.5f}\n"
                f"- 20h SMA: {sma_20:.5f} | 50h SMA: {sma_50:.5f}\n"
                f"- Short-term Trend: {trend} (relative to 20h SMA)\n"
            )
        except Exception as e:
            print(f"Error summarising {sym}: {e}")
            
    if not summary_parts:
        return "Unable to retrieve market data summary."
        
    return "\n---\n".join(summary_parts)
