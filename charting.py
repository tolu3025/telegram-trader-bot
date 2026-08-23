import matplotlib
# Use non-interactive Agg backend to avoid GUI threads issues in Telegram bot
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf
import io
from datetime import datetime, timedelta
import exchange

def generate_live_chart(symbol: str, entry: float = None, sl: float = None, tp: float = None, direction: str = None) -> bytes:
    """
    Downloads historical price data (5 days of 1-hour candles) from yfinance 
    and generates a styled, premium dark-mode line chart with optional 
    Entry, Stop Loss, and Take Profit overlays.
    
    Returns:
        bytes: The PNG image bytes of the chart.
    """
    ticker_str = exchange.normalize_symbol(symbol)
    
    # 1. Download price history (5 days, 1-hour interval is clean for Forex)
    try:
        data = yf.download(ticker_str, period="5d", interval="1h", progress=False)
        if data.empty:
            # Try fallback to daily
            data = yf.download(ticker_str, period="1mo", interval="1d", progress=False)
            if data.empty:
                raise ValueError(f"No price history found for {ticker_str}")
    except Exception as e:
        raise ValueError(f"Failed to fetch market data for charting: {str(e)}")

    # Get closing prices series
    # yfinance download returns a multi-index column if single ticker in newer versions sometimes,
    # let's extract the Close column reliably.
    if 'Close' in data.columns:
        prices = data['Close']
    else:
        raise ValueError("Close prices not found in downloaded data.")

    # Flatten if multi-index
    if hasattr(prices, 'columns'):
        prices = prices.iloc[:, 0]
        
    dates = prices.index
    values = prices.values.astype(float)
    
    current_price = values[-1]
    decimals = 2 if current_price >= 100 else 5

    # 2. Style the Plot (Dark Mode Theme)
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    
    # Background coloring
    fig.patch.set_facecolor('#121214')
    ax.set_facecolor('#18181b')
    
    # Grid lines styling
    ax.grid(True, color='#27272a', linestyle='--', linewidth=0.5)
    
    # Plot the price line
    ax.plot(dates, values, color='#38bdf8', linewidth=2, label="Price")
    
    # Create gradient/area fill under the curve
    ax.fill_between(dates, values, min(values) - (max(values)-min(values))*0.1, 
                    color='#38bdf8', alpha=0.08)

    # 3. Add Trade Overlays if provided
    if entry is not None:
        ax.axhline(y=entry, color='#eab308', linestyle='--', linewidth=1.5, label=f"Entry: {entry:.{decimals}f}")
        
    if sl is not None:
        ax.axhline(y=sl, color='#ef4444', linestyle=':', linewidth=1.8, label=f"Stop Loss: {sl:.{decimals}f}")
        
    if tp is not None:
        ax.axhline(y=tp, color='#22c55e', linestyle='-.', linewidth=1.8, label=f"Take Profit: {tp:.{decimals}f}")
        
    # Highlight Direction (Long / Short shading)
    if direction and entry and sl:
        direction = direction.upper()
        if direction == "LONG":
            ax.fill_between(dates, entry, sl, color='#ef4444', alpha=0.05, label="Risk Zone")
            if tp:
                ax.fill_between(dates, entry, tp, color='#22c55e', alpha=0.05, label="Reward Zone")
        elif direction == "SHORT":
            ax.fill_between(dates, entry, sl, color='#ef4444', alpha=0.05, label="Risk Zone")
            if tp:
                ax.fill_between(dates, entry, tp, color='#22c55e', alpha=0.05, label="Reward Zone")

    # 4. Axes & Spine Styling
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#3f3f46')
    ax.spines['bottom'].set_color('#3f3f46')
    
    ax.tick_params(colors='#a1a1aa', labelsize=8)
    
    # Formatting date axis nicely
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d %H:%M'))
    fig.autofmt_xdate()

    # 5. Labels & Title
    base_sym = symbol.upper().replace("=X", "")
    if len(base_sym) == 6 and not base_sym.endswith("X"):
        display_name = f"{base_sym[:3]}/{base_sym[3:]}"
    elif "-" in base_sym:
        display_name = base_sym.replace("-", "/")
    else:
        display_name = base_sym
        
    title_text = f"📊 {display_name} Live Chart  |  Spot: {current_price:.{decimals}f}"
    ax.set_title(title_text, color='#f4f4f5', fontsize=12, fontweight='bold', pad=15)
    
    # Legend settings
    ax.legend(loc="upper left", facecolor='#18181b', edgecolor='#27272a', fontsize=8, labelcolor='#e4e4e7')

    # Adjust limits to fit lines
    all_levels = [v for v in [entry, sl, tp] if v is not None]
    if all_levels:
        min_y = min(min(values), min(all_levels))
        max_y = max(max(values), max(all_levels))
        padding = (max_y - min_y) * 0.1
        ax.set_ylim(min_y - padding, max_y + padding)

    # 6. Save figure to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), bbox_inches='tight')
    buf.seek(0)
    
    # Close figures to avoid memory leaks
    plt.close(fig)
    
    return buf.getvalue()
