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


def normalize_to_bitget_symbol(symbol: str) -> str:
    """
    Converts yfinance-style crypto tickers to Bitget perpetual swap symbols.
    Examples:
      BTC-USD  -> BTC/USDT:USDT
      ETH-USD  -> ETH/USDT:USDT
      SOL-USD  -> SOL/USDT:USDT
    """
    # Strip Yahoo Finance suffixes
    base = symbol.upper().replace("-USD", "").replace("-USDT", "").replace("=X", "").replace("-", "").replace("/", "")
    # Bitget USDT-margined perpetual format
    return f"{base}/USDT:USDT"


def execute_order(symbol: str, direction: str, entry: float, sl: float, tp: float) -> dict:
    """
    Executes a perpetual futures order on Bitget.
    
    Args:
        symbol:    Asset ticker (e.g. 'BTC-USD', 'ETH-USD')
        direction: 'LONG' or 'SHORT'
        entry:     Target entry price (used as limit order price)
        sl:        Stop Loss price
        tp:        Take Profit price
    
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
        bitget_sym = normalize_to_bitget_symbol(symbol)
        side = "buy" if direction.upper() == "LONG" else "sell"

        # Fetch market info for minimum order size
        markets = ex.load_markets()
        if bitget_sym not in markets:
            return {"success": False, "order_id": None, "message": f"Symbol {bitget_sym} not found on Bitget."}

        market = markets[bitget_sym]
        min_qty = market.get("limits", {}).get("amount", {}).get("min", 0.001)

        # Use minimum size (portfolio.py already sized, this is just exchange execution)
        qty = max(min_qty, 0.001)

        # Place entry limit order
        params = {
            "tdMode": "cross",       # Cross margin
            "posSide": "long" if direction.upper() == "LONG" else "short",
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

        # Place Stop Loss (trigger order)
        try:
            sl_side = "sell" if direction.upper() == "LONG" else "buy"
            ex.create_order(
                symbol=bitget_sym,
                type="stop",
                side=sl_side,
                amount=qty,
                price=sl,
                params={
                    **params,
                    "stopPrice": sl,
                    "stopLossPrice": sl,
                }
            )
        except Exception as e:
            logger.warning(f"SL order placement warning (non-fatal): {e}")

        # Place Take Profit (trigger order)
        try:
            tp_side = "sell" if direction.upper() == "LONG" else "buy"
            ex.create_order(
                symbol=bitget_sym,
                type="take_profit",
                side=tp_side,
                amount=qty,
                price=tp,
                params={
                    **params,
                    "stopPrice": tp,
                    "takeProfitPrice": tp,
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
        bitget_sym = normalize_to_bitget_symbol(symbol)
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
