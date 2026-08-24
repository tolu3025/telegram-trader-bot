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


class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def chat_with_marcus(req: ChatRequest):
    """Send a free-form message to Marcus Vance AI and get a response."""
    import bot
    mode = bot.get_current_mode()
    
    reply = ai_engine.chat_with_marcus(
        user_message=req.message,
        mode=mode
    )
    return {"reply": reply}


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
    import asyncio
    import threading

    def run_bot_in_thread():
        """
        Run the Telegram bot in a dedicated background thread with its own
        asyncio event loop. We manually drive the bot lifecycle instead of
        calling app.run_polling() which installs UNIX signal handlers and
        therefore only works from the main thread.
        """
        import os
        from telegram.ext import ApplicationBuilder
        import bot as bot_module

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token or token == "your_telegram_bot_token_here":
            print("Bot thread: TELEGRAM_BOT_TOKEN not set – bot disabled.")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run():
            # Build the application the same way bot.main() does, but
            # use initialize/start/updater.start_polling directly so we
            # never touch signal handlers.
            from telegram.ext import ApplicationBuilder
            builder = ApplicationBuilder().token(token)
            try:
                # python-telegram-bot >=20 supports job-queue via APScheduler;
                # keep it enabled so scheduled jobs work.
                pass
            except Exception:
                pass

            # Let bot_module register all handlers onto a fresh Application
            # by temporarily monkey-patching its run_polling call.
            import bot as bm
            original_run_polling = None

            tg_app = builder.build()

            # Re-register all handlers using bot_module's internal setup
            bm._register_handlers(tg_app)

            try:
                await tg_app.initialize()
                await tg_app.start()
                if tg_app.updater:
                    await tg_app.updater.start_polling()
                # Start job queue if available
                if tg_app.job_queue:
                    await tg_app.job_queue.start()
                print("Bot thread: Telegram bot is running.")
                # Keep thread alive
                await asyncio.Event().wait()
            except Exception as e:
                print(f"Bot thread inner error: {e}")
            finally:
                try:
                    if tg_app.updater:
                        await tg_app.updater.stop()
                    await tg_app.stop()
                    await tg_app.shutdown()
                except Exception:
                    pass

        try:
            loop.run_until_complete(_run())
        except Exception as e:
            print(f"Bot thread error: {e}")
        finally:
            loop.close()

    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)

