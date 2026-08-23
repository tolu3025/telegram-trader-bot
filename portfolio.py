import logging
import database
import exchange
import bitget_client
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_forex_currencies(symbol: str):
    """
    Extracts base and quote currency from a symbol (e.g. 'EURUSD' -> 'EUR', 'USD').
    """
    clean_sym = symbol.replace("=X", "").replace("/", "").replace("-", "").upper()
    if clean_sym.endswith("USDT"):
        return clean_sym[:-4], "USDT"
    if len(clean_sym) == 6:
        return clean_sym[:3], clean_sym[3:]
    # Fallback for commodities
    if clean_sym in ["GC=F", "GLD", "XAUUSD"]:
        return "XAU", "USD"
    if clean_sym in ["SI=F", "SLV", "XAGUSD"]:
        return "XAG", "USD"
    return clean_sym, "USD"

def get_quote_to_usd_rate(quote_currency: str) -> float:
    """Returns the conversion rate from quote currency to USD."""
    quote_currency = quote_currency.upper()
    if quote_currency in ["USD", "USDT"]:
        return 1.0
    
    # Try QuoteCurrency/USD
    try:
        return exchange.get_live_price(f"{quote_currency}USD")
    except Exception:
        pass
        
    # Try USD/QuoteCurrency and take reciprocal
    try:
        usd_quote = exchange.get_live_price(f"USD{quote_currency}")
        if usd_quote > 0:
            return 1.0 / usd_quote
    except Exception:
        pass
        
    return 1.0

def calculate_risk_params(direction: str, entry: float, sl: float, tp: float):
    """
    Validates trade setup parameters and checks if it matches disciplined criteria:
    - Proper SL/TP positioning relative to entry
    - Minimum Risk-to-Reward ratio (default >= 1.5 or 2.0)
    """
    direction = direction.upper()
    if direction not in ["LONG", "SHORT"]:
        return False, "Direction must be LONG or SHORT", 0, 0, 0
        
    if entry <= 0 or sl <= 0 or tp <= 0:
        return False, "Prices must be positive numbers", 0, 0, 0
        
    if direction == "LONG":
        if sl >= entry:
            return False, "For a LONG trade, Stop Loss must be strictly below entry price", 0, 0, 0
        if tp <= entry:
            return False, "For a LONG trade, Take Profit must be strictly above entry price", 0, 0, 0
        risk_dist = entry - sl
        reward_dist = tp - entry
    else: # SHORT
        if sl <= entry:
            return False, "For a SHORT trade, Stop Loss must be strictly above entry price", 0, 0, 0
        if tp >= entry:
            return False, "For a SHORT trade, Take Profit must be strictly below entry price", 0, 0, 0
        risk_dist = sl - entry
        reward_dist = entry - tp
        
    rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
    
    # Disciplined rule: Risk-to-Reward must be at least 1:1.5
    # Using 1.49 threshold (not 1.5 exactly) to handle floating-point precision
    # where a true 1.5 R:R may compute as 1.4999... and get incorrectly rejected.
    if rr_ratio < 1.49:
        return False, f"Risk-to-Reward ratio ({rr_ratio:.2f}) is too low. Disciplined professional traders require at least 1:1.5 R:R.", risk_dist, reward_dist, rr_ratio
        
    return True, "Setup complies with basic structural rules.", risk_dist, reward_dist, rr_ratio

def calculate_position_size(symbol: str, direction: str, entry: float, sl: float, risk_amount_usd: float) -> tuple:
    """
    Calculates position size in base currency units based on USD risk.
    Formula: Size = Risk_USD / (Risk_Distance * Quote_to_USD_rate)
    """
    base, quote = parse_forex_currencies(symbol)
    quote_to_usd = get_quote_to_usd_rate(quote)
    
    risk_distance = abs(entry - sl)
    if risk_distance == 0:
        raise ValueError("Stop loss cannot equal entry price.")
        
    size = risk_amount_usd / (risk_distance * quote_to_usd)
    
    # If size is small (common in Crypto e.g. BTC), round to 6 decimal places, otherwise 2.
    rounded_size = round(size, 6) if size < 0.1 else round(size, 2)
    return rounded_size, quote_to_usd

def calculate_pnl(direction: str, entry: float, exit: float, size: float, quote_to_usd: float) -> float:
    """Calculates P&L in USD for a closed position."""
    direction = direction.upper()
    if direction == "LONG":
        pnl_quote = size * (exit - entry)
    else: # SHORT
        pnl_quote = size * (entry - exit)
        
    return round(pnl_quote * quote_to_usd, 2)

def propose_and_open_trade(symbol: str, direction: str, entry: float, sl: float, tp: float, thesis: str, auto_adjust: bool = False):
    """
    Processes a trade proposal. 
    1. Validates risk-to-reward (with optional auto-adjustment).
    2. Validates symbol.
    3. Fetches account stats and calculates size.
    4. Opens the trade in the DB.
    """
    # 1. Structural checks
    is_struct_valid, reason, risk_dist, reward_dist, rr = calculate_risk_params(direction, entry, sl, tp)
    if not is_struct_valid:
        if auto_adjust and "Risk-to-Reward ratio" in reason:
            # Auto-adjust TP to achieve exactly 1.5 R:R
            if direction.upper() == "LONG":
                tp = entry + (1.5 * risk_dist)
            else:
                tp = entry - (1.5 * risk_dist)
            # Re-validate structural parameters
            is_struct_valid, reason, risk_dist, reward_dist, rr = calculate_risk_params(direction, entry, sl, tp)
        
        if not is_struct_valid:
            return {"success": False, "reason": reason}
        
    # 2. Check symbol
    try:
        norm_sym = exchange.normalize_symbol(symbol)
        if exchange.is_market_closed_for_symbol(norm_sym):
            return {"success": False, "reason": "The market for this asset is currently closed (weekends)."}
        # Ensure we can get a price (validates the symbol exists)
        _ = exchange.get_live_price(norm_sym)
    except Exception as e:
        return {"success": False, "reason": f"Invalid symbol or unable to fetch market rate: {str(e)}"}
        
    # 3. Get Account info and calculate sizing
    acc = database.get_account()
    if not acc:
        return {"success": False, "reason": "Account not initialized."}
    
    # Use LIVE Bitget balance if available, otherwise fall back to DB balance
    live_balance = bitget_client.get_account_balance()
    if live_balance is not None and live_balance > 0:
        balance = live_balance
        logger.info(f"Using live Bitget balance for sizing: ${balance:.2f}")
    else:
        balance = acc['balance']
        logger.info(f"Using local DB balance for sizing: ${balance:.2f}")
    
    risk_pct = acc['risk_pct']
    risk_amount_usd = balance * (risk_pct / 100.0)
    
    try:
        size, quote_to_usd = calculate_position_size(norm_sym, direction, entry, sl, risk_amount_usd)
    except Exception as e:
        return {"success": False, "reason": f"Error calculating position size: {str(e)}"}
        
    # 4. Open position in database
    pos_id = database.open_position(
        symbol=norm_sym,
        direction=direction.upper(),
        entry_price=entry,
        size=size,
        stop_loss=sl,
        take_profit=tp,
        thesis=thesis,
        risk_amount=risk_amount_usd
    )
    
    # 5. Route to Bitget exchange if live trading is enabled
    bitget_result = bitget_client.execute_order(
        symbol=norm_sym,
        direction=direction,
        entry=entry,
        sl=sl,
        tp=tp,
        size=size
    )
    bitget_msg = bitget_result.get("message", "")
    bitget_order_id = bitget_result.get("order_id", None)
    
    return {
        "success": True,
        "position_id": pos_id,
        "symbol": norm_sym,
        "direction": direction.upper(),
        "size": size,
        "risk_amount": risk_amount_usd,
        "rr_ratio": rr,
        "bitget_order_id": bitget_order_id,
        "bitget_message": bitget_msg
    }

def get_position_details(position_id: int):
    """Retrieves full details of a position including current P&L."""
    pos = database.get_position(position_id)
    if not pos:
        return None
        
    if pos['status'] == 'CLOSED':
        return pos
        
    # For open positions, fetch live price and calculate floating PNL
    try:
        live_price = exchange.get_live_price(pos['symbol'])
        base, quote = parse_forex_currencies(pos['symbol'])
        quote_to_usd = get_quote_to_usd_rate(quote)
        floating_pnl = calculate_pnl(pos['direction'], pos['entry_price'], live_price, pos['size'], quote_to_usd)
        
        pos_dict = dict(pos)
        pos_dict['current_price'] = live_price
        pos_dict['floating_pnl'] = floating_pnl
        return pos_dict
    except Exception:
        # If live price fails, return position as-is with 0 floating PNL
        pos_dict = dict(pos)
        pos_dict['current_price'] = pos['entry_price']
        pos_dict['floating_pnl'] = 0.0
        return pos_dict

def update_portfolio():
    """
    Updates the equity of the account by checking all open positions
    and updating their floating P&L.
    """
    acc = database.get_account()
    if not acc:
        return
        
    open_pos = database.get_open_positions()
    total_floating_pnl = 0.0
    
    for pos in open_pos:
        try:
            live_price = exchange.get_live_price(pos['symbol'])
            base, quote = parse_forex_currencies(pos['symbol'])
            quote_to_usd = get_quote_to_usd_rate(quote)
            pnl = calculate_pnl(pos['direction'], pos['entry_price'], live_price, pos['size'], quote_to_usd)
            total_floating_pnl += pnl
        except Exception:
            pass
            
    new_equity = acc['balance'] + total_floating_pnl
    database.update_account_balance(acc['balance'], new_equity)
    return new_equity

def check_and_trigger_sl_tp():
    """
    Scans all open positions and checks if the live price has hit
    either the Stop Loss or Take Profit. Triggers a simulated close if so.
    Returns list of triggered events (closed position descriptions).
    """
    open_pos = database.get_open_positions()
    triggered_events = []
    
    for pos in open_pos:
        if exchange.is_market_closed_for_symbol(pos['symbol']):
            continue
            
        try:
            live_price = exchange.get_live_price(pos['symbol'])
            direction = pos['direction'].upper()
            sl = pos['stop_loss']
            tp = pos['take_profit']
            
            triggered = False
            trigger_type = ""
            trigger_price = 0.0
            
            if direction == "LONG":
                if live_price <= sl:
                    triggered = True
                    trigger_type = "Stop Loss"
                    trigger_price = sl  # Close at SL price to simulate exact SL fill
                elif live_price >= tp:
                    triggered = True
                    trigger_type = "Take Profit"
                    trigger_price = tp
            else: # SHORT
                if live_price >= sl:
                    triggered = True
                    trigger_type = "Stop Loss"
                    trigger_price = sl
                elif live_price <= tp:
                    triggered = True
                    trigger_type = "Take Profit"
                    trigger_price = tp
                    
            if triggered:
                base, quote = parse_forex_currencies(pos['symbol'])
                quote_to_usd = get_quote_to_usd_rate(quote)
                final_pnl = calculate_pnl(direction, pos['entry_price'], trigger_price, pos['size'], quote_to_usd)
                
                database.close_position(pos['position_id'], trigger_price, final_pnl)
                triggered_events.append({
                    "position_id": pos['position_id'],
                    "symbol": pos['symbol'],
                    "direction": direction,
                    "trigger_type": trigger_type,
                    "trigger_price": trigger_price,
                    "pnl": final_pnl
                })
        except Exception as e:
            print(f"Error checking SL/TP for position {pos['position_id']}: {e}")
            
    return triggered_events

def force_close_position(position_id: int):
    """Manually closes a position at current market price."""
    pos = database.get_position(position_id)
    if not pos or pos['status'] != 'OPEN':
        return {"success": False, "reason": "Position not found or already closed."}
        
    try:
        live_price = exchange.get_live_price(pos['symbol'])
        base, quote = parse_forex_currencies(pos['symbol'])
        quote_to_usd = get_quote_to_usd_rate(quote)
        final_pnl = calculate_pnl(pos['direction'], pos['entry_price'], live_price, pos['size'], quote_to_usd)
        
        new_balance = database.close_position(position_id, live_price, final_pnl)
        
        # Also close on Bitget exchange if live trading enabled
        bitget_client.close_position(
            symbol=pos['symbol'],
            direction=pos['direction']
        )
        
        return {
            "success": True,
            "exit_price": live_price,
            "pnl": final_pnl,
            "new_balance": new_balance
        }
    except Exception as e:
        return {"success": False, "reason": f"Error closing position: {str(e)}"}
