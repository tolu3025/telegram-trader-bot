"""
bitget_client.py
Bitget Exchange integration via CCXT library.
Supports sandbox (demo) and live trading modes.
Orders are only placed when BITGET_ENABLE_LIVE_TRADING=True.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Configuration from Environment ---
BITGET_API_KEY        = os.getenv("BITGET_API_KEY", "")
BITGET_API_SECRET     = os.getenv("BITGET_API_SECRET", "")
BITGET_PASSPHRASE     = os.getenv("BITGET_API_PASSPHRASE", "")
USE_SANDBOX           = os.getenv("BITGET_USE_SANDBOX", "True").lower() == "true"
LIVE_TRADING_ENABLED  = os.getenv("BITGET_ENABLE_LIVE_TRADING", "False").lower() == "true"

_exchange = None

def _get_exchange():
    """Lazy-initializes and returns the CCXT Bitget exchange instance."""
    global _exchange
    if _exchange is not None:
        return _exchange

    try:
        import ccxt
    except ImportError:
        logger.error("ccxt is not installed. Run: pip install ccxt")
        return None

    if not all([BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE]):
        logger.warning("Bitget API credentials not fully configured. Live trading disabled.")
        return None

    try:
        exchange = ccxt.bitget({
            "apiKey":     BITGET_API_KEY,
            "secret":     BITGET_API_SECRET,
            "password":   BITGET_PASSPHRASE,
            "options": {
                "defaultType": "swap",   # Perpetual futures
            }
        })

        if USE_SANDBOX:
            exchange.set_sandbox_mode(True)
            logger.info("Bitget client initialized in SANDBOX (Demo) mode.")
        else:
            logger.info("Bitget client initialized in LIVE trading mode.")

        _exchange = exchange
        return _exchange

    except Exception as e:
        logger.error(f"Failed to initialize Bitget exchange client: {e}")
        return None


def get_status() -> dict:
    """Returns the current Bitget integration status."""
    if not LIVE_TRADING_ENABLED:
        return {
            "enabled": False,
            "mode": "disabled",
            "message": "Bitget live trading is disabled. Bot is running in simulated paper trading mode."
        }
    ex = _get_exchange()
    if not ex:
        return {
            "enabled": False,
            "mode": "error",
            "message": "Bitget credentials missing or invalid. Live trading not available."
        }
    mode = "sandbox (demo)" if USE_SANDBOX else "LIVE (real funds)"
    return {
        "enabled": True,
        "mode": mode,
        "message": f"Bitget execution ACTIVE — {mode.upper()} mode."
    }


def get_account_balance() -> float:
    """
    Fetches the real available USDT balance from the Bitget USDT-M Futures account.
    Returns None if unable to fetch (e.g. API not configured or disabled).
    """
    if not LIVE_TRADING_ENABLED:
        return None

    ex = _get_exchange()
    if not ex:
        return None

    try:
        balance = ex.fetch_balance({"type": "swap"})
        usdt_balance = (
            balance.get("USDT", {}).get("free")
            or balance.get("USDT", {}).get("total")
            or 0.0
        )
        logger.info(f"Fetched Bitget USDT futures balance: ${usdt_balance:.2f}")
        return float(usdt_balance)
    except Exception as e:
        logger.error(f"Failed to fetch Bitget account balance: {e}")
        return None


def normalize_to_bitget_symbol(symbol: str, ex=None) -> str:
    """
    Converts yfinance-style crypto tickers or Forex symbols to Bitget perpetual swap symbols.
    Uses dynamic market lookup if the exchange client is provided.
    """
    clean_sym = symbol.upper().replace("=X", "").replace("-", "").replace("/", "")
    
    # If the active exchange client is provided, query actual listed markets for a precise match
    if ex:
        try:
            markets = ex.load_markets()
            for m_sym in markets:
                # Strip symbols to check matches (e.g. 'BTC/USDT:USDT' -> 'BTCUSDT')
                clean_m = m_sym.upper().replace("-", "").replace("/", "").split(":")[0]
                if clean_m == clean_sym or clean_m.replace("USDT", "USD") == clean_sym:
                    return m_sym
        except Exception as e:
            logger.debug(f"Dynamic symbol mapping failed: {e}")

    # Fallback to default crypto mapping format
    base = clean_sym.replace("USD", "").replace("USDT", "")
    return f"{base}/USDT:USDT"


def execute_order(symbol: str, direction: str, entry: float, sl: float, tp: float, size: float) -> dict:
    """
    Executes a perpetual futures order on Bitget.
    
    Args:
        symbol:    Asset ticker (e.g. 'BTC-USD', 'ETH-USD')
        direction: 'LONG' or 'SHORT'
        entry:     Target entry price (used as limit order price)
        sl:        Stop Loss price
        tp:        Take Profit price
        size:      Calculated position size
    
    Returns:
        dict with keys: success, order_id, message
    """
    if not LIVE_TRADING_ENABLED:
        return {
            "success": True,
            "order_id": "SIMULATED",
            "message": "Simulated order (Bitget live trading disabled)."
        }

    ex = _get_exchange()
    if not ex:
        return {"success": False, "order_id": None, "message": "Bitget client not initialized."}

    try:
        bitget_sym = normalize_to_bitget_symbol(symbol, ex)
        
        # In one-way (unilateral) mode: buy = open long, sell = open short
        side = "buy" if direction.upper() == "LONG" else "sell"

        # Fetch market info for minimum order size
        markets = ex.load_markets()
        if bitget_sym not in markets:
            return {"success": False, "order_id": None, "message": f"Symbol {bitget_sym} not found on Bitget."}

        market = markets[bitget_sym]
        min_qty = market.get("limits", {}).get("amount", {}).get("min", 0.001)

        # Set leverage to 10x — this reduces margin requirement so small accounts can trade
        LEVERAGE = 10
        try:
            ex.set_leverage(LEVERAGE, bitget_sym)
            logger.info(f"Set leverage to {LEVERAGE}x for {bitget_sym}")
        except Exception as le:
            logger.warning(f"Could not set leverage (may already be set): {le}")

        # Format calculated size using CCXT amount_to_precision
        raw_qty = max(min_qty, size)
        qty = float(ex.amount_to_precision(bitget_sym, raw_qty))

        # Guard: check if order value exceeds balance with leverage margin
        # Required margin = (qty * entry) / leverage
        try:
            live_balance = ex.fetch_balance({"type": "swap"})
            avail = float(live_balance.get("USDT", {}).get("free") or 0.0)
            if avail > 0:
                max_qty_for_balance = (avail * LEVERAGE * 0.95) / entry  # 95% of usable margin
                if qty * entry / LEVERAGE > avail:
                    # Reduce qty to fit within balance
                    safe_qty = float(ex.amount_to_precision(bitget_sym, max(min_qty, max_qty_for_balance)))
                    logger.warning(f"Order size {qty} exceeds balance capacity. Reduced to {safe_qty}")
                    qty = safe_qty
        except Exception as be:
            logger.warning(f"Balance guard check failed (non-fatal): {be}")

        # Dynamically fetch current position mode from exchange to prevent mismatches
        is_hedged = False
        try:
            mode_res = ex.fetch_position_mode(bitget_sym)
            is_hedged = mode_res.get("hedged", False)
            logger.info(f"Detected Bitget position mode for {bitget_sym}: {'Hedged' if is_hedged else 'One-Way'}")
        except Exception as pe:
            logger.warning(f"Could not fetch position mode: {pe}. Defaulting to One-Way.")

        if is_hedged:
            # Hedge mode order params
            params = {
                "tdMode": "cross",
                "posSide": "long" if direction.upper() == "LONG" else "short"
            }
            # SL/TP params in hedge mode
            sl_tp_params = {
                "tdMode": "cross",
                "posSide": "long" if direction.upper() == "LONG" else "short",
                "reduceOnly": True
            }
        else:
            # One-way mode order params
            params = {
                "tdMode": "cross",
                "tradeSide": "open"
            }
            # SL/TP params in one-way mode
            sl_tp_params = {
                "tdMode": "cross",
                "tradeSide": "close",
                "reduceOnly": True
            }

        entry_order = ex.create_order(
            symbol=bitget_sym,
            type="limit",
            side=side,
            amount=qty,
            price=entry,
            params=params
        )
        order_id = entry_order.get("id", "unknown")

        # Place Stop Loss trigger order (close direction is opposite of entry)
        try:
            sl_side = "sell" if direction.upper() == "LONG" else "buy"
            ex.create_order(
                symbol=bitget_sym,
                type="stop",
                side=sl_side,
                amount=qty,
                price=sl,
                params={
                    **sl_tp_params,
                    "stopPrice": sl,
                }
            )
        except Exception as e:
            logger.warning(f"SL order placement warning (non-fatal): {e}")

        # Place Take Profit trigger order
        try:
            tp_side = "sell" if direction.upper() == "LONG" else "buy"
            ex.create_order(
                symbol=bitget_sym,
                type="take_profit",
                side=tp_side,
                amount=qty,
                price=tp,
                params={
                    **sl_tp_params,
                    "stopPrice": tp,
                }
            )
        except Exception as e:
            logger.warning(f"TP order placement warning (non-fatal): {e}")

        mode_tag = "[SANDBOX]" if USE_SANDBOX else "[LIVE]"
        logger.info(f"{mode_tag} Bitget order placed: {direction} {bitget_sym} @ {entry} | SL:{sl} | TP:{tp} | OrderID:{order_id}")

        return {
            "success": True,
            "order_id": order_id,
            "bitget_symbol": bitget_sym,
            "message": f"{mode_tag} Order placed on Bitget. ID: {order_id}"
        }

    except Exception as e:
        logger.error(f"Bitget order execution failed: {e}")
        return {"success": False, "order_id": None, "message": f"Bitget execution error: {str(e)}"}


def close_position(symbol: str, direction: str) -> dict:
    """
    Closes an open perpetual position on Bitget for the given symbol.
    
    Args:
        symbol:    Asset ticker (e.g. 'BTC-USD')
        direction: 'LONG' or 'SHORT'
    
    Returns:
        dict with keys: success, message
    """
    if not LIVE_TRADING_ENABLED:
        return {"success": True, "message": "Simulated close (Bitget live trading disabled)."}

    ex = _get_exchange()
    if not ex:
        return {"success": False, "message": "Bitget client not initialized."}

    try:
        bitget_sym = normalize_to_bitget_symbol(symbol, ex)
        side = "sell" if direction.upper() == "LONG" else "buy"

        # Fetch open positions to get size
        positions = ex.fetch_positions([bitget_sym])
        target_pos = None
        for p in positions:
            if p.get("symbol") == bitget_sym and float(p.get("contracts", 0)) > 0:
                target_pos = p
                break

        if not target_pos:
            return {"success": False, "message": f"No open Bitget position found for {bitget_sym}."}

        qty = float(target_pos.get("contracts", 0))

        # Close at market price
        ex.create_order(
            symbol=bitget_sym,
            type="market",
            side=side,
            amount=qty,
            params={
                "tdMode": "cross",
                "posSide": "long" if direction.upper() == "LONG" else "short",
                "reduceOnly": True
            }
        )

        mode_tag = "[SANDBOX]" if USE_SANDBOX else "[LIVE]"
        logger.info(f"{mode_tag} Bitget position closed: {direction} {bitget_sym} qty:{qty}")
        return {"success": True, "message": f"{mode_tag} Bitget position closed for {bitget_sym}."}

    except Exception as e:
        logger.error(f"Bitget close position failed: {e}")
        return {"success": False, "message": f"Bitget close error: {str(e)}"}


def get_open_positions() -> list:
    """Fetches all open perpetual positions from Bitget."""
    if not LIVE_TRADING_ENABLED:
        return []

    ex = _get_exchange()
    if not ex:
        return []

    try:
        positions = ex.fetch_positions()
        active = [p for p in positions if float(p.get("contracts", 0)) > 0]
        return active
    except Exception as e:
        logger.error(f"Error fetching Bitget positions: {e}")
        return []
