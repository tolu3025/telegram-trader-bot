import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import database
import exchange
import portfolio
import ai_engine
import bitget_client

app = FastAPI(title="Marcus Vance Trading Console")

# Enable CORS for Telegram WebApp environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schemas
class TradeRequest(BaseModel):
    symbol: str
    direction: str
    entry: float
    sl: float
    tp: float
    thesis: str

class CloseRequest(BaseModel):
    position_id: int

@app.on_event("startup")
def startup_event():
    database.init_db()

@app.get("/api/status")
def get_status():
    """Returns exchange connectivity status, current mode, and balance."""
    # Read active mode from file
    import bot
    mode = bot.get_current_mode()
    
    # Get Bitget status
    bg_status = bitget_client.get_status()
    
    # Fetch free balance
    live_balance = bitget_client.get_account_balance()
    if live_balance is None:
        acc = database.get_account()
        balance = acc['balance'] if acc else 10000.0
        is_live = False
    else:
        balance = live_balance
        is_live = True
        
    return {
        "mode": mode,
        "exchange": "Bitget",
        "live_execution": bg_status["enabled"],
        "exchange_mode": bg_status["mode"],
        "balance": balance,
        "is_live_balance": is_live
    }

@app.get("/api/positions")
def get_positions():
    """Fetches open positions from database augmented with live P&L details."""
    open_pos = database.get_open_positions()
    detailed_positions = []
    for pos in open_pos:
        details = portfolio.get_position_details(pos['position_id'])
        if details:
            detailed_positions.append(details)
    return detailed_positions

@app.get("/api/history")
def get_history():
    """Fetches recent closed trades."""
    closed = database.get_closed_positions(limit=20)
    return [dict(pos) for pos in closed]

@app.post("/api/trade")
def place_trade(req: TradeRequest):
    """Processes a trade proposal by running it through AI and executing if approved."""
    import bot
    mode = bot.get_current_mode()
    acc = database.get_account()
    if not acc:
        raise HTTPException(status_code=400, detail="Account not initialized.")
        
    # Get current balance for AI context
    live_balance = bitget_client.get_account_balance()
    balance = live_balance if live_balance is not None else acc['balance']
    
    # 1. Run through AI Review
    ai_review = ai_engine.review_trade_proposal(
        symbol=req.symbol,
        direction=req.direction,
        entry=req.entry,
        sl=req.sl,
        tp=req.tp,
        thesis=req.thesis,
        balance=balance,
        risk_pct=acc['risk_pct'],
        mode=mode
    )
    
    if ai_review.get("decision") != "APPROVED":
        return {
            "success": False,
            "decision": "REJECTED",
            "reason": ai_review.get("reason"),
            "feedback": ai_review.get("feedback"),
            "suggested_sl": ai_review.get("suggested_sl"),
            "suggested_tp": ai_review.get("suggested_tp")
        }
        
    # 2. Execute trade
    execution = portfolio.propose_and_open_trade(
        symbol=req.symbol,
        direction=req.direction,
        entry=req.entry,
        sl=req.sl,
        tp=req.tp,
        thesis=req.thesis
    )
    
    if not execution["success"]:
        raise HTTPException(status_code=400, detail=execution["reason"])
        
    return {
        "success": True,
        "decision": "APPROVED",
        "position_id": execution["position_id"],
        "symbol": execution["symbol"],
        "size": execution["size"],
        "risk_amount": execution["risk_amount"],
        "feedback": ai_review.get("feedback")
    }

@app.post("/api/close")
def close_position(req: CloseRequest):
    """Closes an open position."""
    res = portfolio.force_close_position(req.position_id)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["reason"])
    return res

@app.get("/api/market-scan")
def market_scan():
    """Trigger a fast market scan and return structured details of symbols."""
    import bot
    mode = bot.get_current_mode()
    
    if mode == "forex":
        symbols = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "GC=F"]
    else:
        # Crypto or perpetual
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"]
        
    scan_results = []
    for sym in symbols:
        try:
            norm_sym = exchange.normalize_symbol(sym)
            ticker = exchange.yf.Ticker(norm_sym)
            df = ticker.history(period="5d", interval="1h")
            if df.empty:
                continue
                
            close_prices = df['Close'].astype(float)
            spot = float(close_prices.iloc[-1])
            
            # SMAs
            sma_20 = float(close_prices.rolling(window=min(20, len(close_prices))).mean().iloc[-1])
            sma_50 = float(close_prices.rolling(window=min(50, len(close_prices))).mean().iloc[-1])
            
            # Static levels
            supports, resistances = exchange.detect_support_resistance(df, spot)
            
            scan_results.append({
                "symbol": sym.replace("=X", ""),
                "ticker": norm_sym,
                "spot": spot,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "supports": supports,
                "resistances": resistances,
                "trend": "BULLISH" if spot > sma_20 else "BEARISH"
            })
        except Exception as e:
            print(f"Fast scan failed for {sym}: {e}")
            
    return scan_results

# Serve web console
@app.get("/")
def get_index():
    return FileResponse("templates/index.html")

# Create templates and static directories if not exists
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
