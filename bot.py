import os
import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv

import database
import exchange
import portfolio
import ai_engine
import charting

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

CHAT_ID_FILE = "chat_id.txt"
MODE_FILE = "mode.txt"

def get_current_mode() -> str:
    """Returns 'forex' or 'crypto' (defaults to 'forex')."""
    if os.path.exists(MODE_FILE):
        try:
            with open(MODE_FILE, "r") as f:
                mode = f.read().strip().lower()
                if mode in ["forex", "crypto"]:
                    return mode
        except Exception:
            pass
    return "forex"

def set_current_mode(mode: str):
    """Sets mode to 'forex' or 'crypto'."""
    mode = mode.lower().strip()
    if mode in ["forex", "crypto"]:
        with open(MODE_FILE, "w") as f:
            f.write(mode)

def save_chat_id(chat_id: int):
    """Saves chat ID to persist subscriber list for notifications."""
    chat_ids = set()
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE, "r") as f:
            for line in f:
                if line.strip().isdigit():
                    chat_ids.add(int(line.strip()))
    chat_ids.add(chat_id)
    with open(CHAT_ID_FILE, "w") as f:
        for cid in chat_ids:
            f.write(f"{cid}\n")

def get_chat_ids():
    """Returns list of all saved chat IDs."""
    if not os.path.exists(CHAT_ID_FILE):
        return []
    chat_ids = []
    with open(CHAT_ID_FILE, "r") as f:
        for line in f:
            if line.strip().isdigit():
                chat_ids.append(int(line.strip()))
    return chat_ids

# COMMAND HANDLERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the bot, sets up the chat ID, and welcomes the user."""
    chat_id = update.effective_chat.id
    save_chat_id(chat_id)
    
    # Ensure database is initialized
    database.init_db()
    
    acc = database.get_account()
    balance = acc['balance'] if acc else 10000.0
    risk_pct = acc['risk_pct'] if acc else 1.0
    
    welcome_text = (
        "💼 **Marcus Vance's Forex Trading Desk** 💼\n\n"
        "Welcome kid. I'm Marcus Vance, your Risk Manager. I have 20 years of experience trading these currency markets. "
        "I'm here to make sure you trade like a disciplined professional, not an emotional gambler.\n\n"
        f"You start with a **${balance:,.2f} USD** simulated account, risking **{risk_pct}%** (${balance * risk_pct / 100:,.2f} USD) per trade.\n\n"
        "**AI Chat Integration (Natural Language)**\n"
        "💬 You can now write setups in pure text! Just tell me your trade idea and I will audit it and show you confirmation buttons.\n"
        "   _Example: 'Marcus, let's long EURUSD entry 1.0920 stop loss 1.0850 target 1.1060 because hourly broke out.'_\n\n"
        "**Available Commands:**\n"
        "📂 `/portfolio` - Check balance, equity, and open positions.\n"
        "📊 `/trade <symbol> <LONG/SHORT> <entry> <sl> <tp> <thesis>` - Propose trade via parameters.\n"
        "📈 `/chart <symbol>` - Generate a live historical dark-mode chart of a pair.\n"
        "🔔 `/dropsignal <tokyo/london/new_york/close>` - Generate and drop session signal/analysis manually.\n"
        "❌ `/close <position_id>` - Manually close an open position.\n"
        "📈 `/history` - View the performance of closed trades.\n"
        "📓 `/journal <thoughts>` - Write your trading journal and get critique.\n"
        "⚙️ `/risk <1-5>` - Update risk percentage per trade (default 1.0%).\n"
        "🔄 `/reset [balance]` - Reset your account to clear all history and start fresh.\n\n"
        "📷 **Chart Analysis**: Upload a chart image (screenshot) and add a caption or ask a question to get my technical review."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays account information, stats, and open positions."""
    # Update equity first
    portfolio.update_portfolio()
    
    acc = database.get_account()
    if not acc:
        await update.message.reply_text("❌ Account not found. Run `/start` to initialize.")
        return
        
    stats = database.get_portfolio_stats()
    open_pos = database.get_open_positions()
    
    # Calculate current open positions details (with live floating P&L)
    open_pos_detailed = []
    for p in open_pos:
        details = portfolio.get_position_details(p['position_id'])
        if details:
            open_pos_detailed.append(details)
            
    risk_amount = acc['balance'] * (acc['risk_pct'] / 100.0)
    
    msg = (
        "💼 **Trading Desk Portfolio**\n"
        "-------------------------------------\n"
        f"💰 **Balance**: ${acc['balance']:,.2f} USD\n"
        f"📈 **Equity**: ${acc['equity']:,.2f} USD\n"
        f"🛡️ **Risk Limit**: {acc['risk_pct']}% (${risk_amount:,.2f} USD)\n\n"
        "📊 **Performance Metrics**:\n"
        f"• Total Trades: {stats['total_trades']}\n"
        f"• Win Rate: {stats['win_rate']:.1f}%\n"
        f"• Profit Factor: {stats['profit_factor']:.2f}\n"
        f"• Net Profit: {stats['net_profit']:+.2f} USD\n\n"
        "📂 **Open Positions**:\n"
    )
    
    if not open_pos_detailed:
        msg += "_No open positions at the moment._"
    else:
        for pos in open_pos_detailed:
            pnl_sign = "+" if pos['floating_pnl'] > 0 else ""
            msg += (
                f"• **#{pos['position_id']}** {pos['symbol']} {pos['direction']}\n"
                f"  Entry: {pos['entry_price']:.5f} | Current: {pos['current_price']:.5f}\n"
                f"  SL: {pos['stop_loss']:.5f} | TP: {pos['take_profit']:.5f}\n"
                f"  Floating P&L: **{pnl_sign}${pos['floating_pnl']:.2f} USD**\n"
            )
            
    await update.message.reply_text(msg, parse_mode="Markdown")

async def trade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes a trade proposal by running it through the AI risk manager."""
    # Correct format check
    if len(context.args) < 5:
        await update.message.reply_text(
            "❌ **Invalid Format**\n"
            "Use: `/trade <symbol> <LONG/SHORT> <entry> <sl> <tp> <thesis>`\n"
            "Example: `/trade EURUSD LONG 1.0920 1.0850 1.1060 In line with weekly trend.`",
            parse_mode="Markdown"
        )
        return
        
    try:
        symbol = context.args[0].upper()
        direction = context.args[1].upper()
        entry = float(context.args[2])
        sl = float(context.args[3])
        tp = float(context.args[4])
        thesis = " ".join(context.args[5:]) if len(context.args) > 5 else "No thesis provided."
    except ValueError:
        await update.message.reply_text("❌ Entry, SL, and TP must be positive decimal numbers.")
        return
        
    # Standard validation first
    is_valid, reason, _, _, rr = portfolio.calculate_risk_params(direction, entry, sl, tp)
    if not is_valid:
        await update.message.reply_text(f"❌ **Risk Management Block**:\n{reason}")
        return
        
    # Check if the market is closed
    norm_symbol = exchange.normalize_symbol(symbol)
    if exchange.is_market_closed_for_symbol(norm_symbol):
        await update.message.reply_text(
            f"❌ **Market Closed Block**:\n"
            f"The market for `{norm_symbol}` is currently closed (weekends/holidays).\n"
            f"Forex markets are closed from Friday 21:00 UTC to Sunday 21:00 UTC and on major global holidays.\n"
            f"Try trading active Cryptocurrency markets instead."
        )
        return
        
    # Get account stats for AI context
    acc = database.get_account()
    if not acc:
        await update.message.reply_text("❌ Account not initialized. Run `/start` first.")
        return
        
    # AI Review Status
    status_msg = await update.message.reply_text("🔍 *Marcus Vance is reviewing your trade proposal...*", parse_mode="Markdown")
    
    # Run through OpenAI AI Engine
    ai_review = ai_engine.review_trade_proposal(
        symbol=symbol,
        direction=direction,
        entry=entry,
        sl=sl,
        tp=tp,
        thesis=thesis,
        balance=acc['balance'],
        risk_pct=acc['risk_pct'],
        mode=get_current_mode()
    )
    
    await status_msg.delete()
    
    if ai_review.get("decision") == "APPROVED":
        # Execute trade
        execution = portfolio.propose_and_open_trade(symbol, direction, entry, sl, tp, thesis)
        if execution["success"]:
            success_msg = (
                "✅ **TRADE APPROVED & EXECUTED**\n\n"
                f"**Position #{execution['position_id']} Opened:**\n"
                f"• Symbol: {execution['symbol']}\n"
                f"• Direction: {execution['direction']}\n"
                f"• Size: {execution['size']:,} units\n"
                f"• Risk Amount: ${execution['risk_amount']:.2f} USD\n"
                f"• R:R Ratio: {execution['rr_ratio']:.2f}\n\n"
                f"💬 **Marcus Vance's Feedback**:\n_{ai_review.get('feedback')}_"
            )
            
            # Try to generate chart visualization
            try:
                chart_bytes = charting.generate_live_chart(symbol, entry, sl, tp, direction)
                await update.message.reply_photo(
                    photo=chart_bytes,
                    caption=f"📊 Position #{execution['position_id']} ({execution['symbol']} {execution['direction']}) Setup Chart"
                )
            except Exception as e:
                logger.error(f"Failed to generate and send trade chart: {e}")
                
            await update.message.reply_text(success_msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ **Execution Error**: {execution['reason']}")
    else:
        # Trade Rejected
        suggest_txt = ""
        if ai_review.get("suggested_sl") or ai_review.get("suggested_tp"):
            suggest_txt = "\n**Suggested Parameter Adjustments:**\n"
            if ai_review.get("suggested_sl"):
                suggest_txt += f"• Suggested SL: {ai_review.get('suggested_sl')}\n"
            if ai_review.get("suggested_tp"):
                suggest_txt += f"• Suggested TP: {ai_review.get('suggested_tp')}\n"
                
        reject_msg = (
            "❌ **TRADE REJECTED BY RISK MANAGER**\n\n"
            f"**Reason**: {ai_review.get('reason')}\n"
            f"{suggest_txt}\n"
            f"💬 **Marcus Vance's Feedback**:\n_{ai_review.get('feedback')}_"
        )
        await update.message.reply_text(reject_msg, parse_mode="Markdown")

async def close_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually closes a position."""
    if not context.args:
        await update.message.reply_text("❌ Use: `/close <position_id>`")
        return
        
    try:
        position_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Position ID must be an integer.")
        return
        
    status_msg = await update.message.reply_text("⚡ _Closing position at market rate..._")
    res = portfolio.force_close_position(position_id)
    await status_msg.delete()
    
    if res["success"]:
        pnl_sign = "+" if res["pnl"] > 0 else ""
        msg = (
            "✅ **Position Closed Manually**\n\n"
            f"Position #{position_id} closed at market price: **{res['exit_price']:.5f}**\n"
            f"P&L: **{pnl_sign}${res['pnl']:.2f} USD**\n"
            f"New Account Balance: **${res['new_balance']:,.2f} USD**"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ **Error**: {res['reason']}")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays recent closed trades."""
    closed = database.get_closed_positions(limit=10)
    if not closed:
        await update.message.reply_text("📈 No closed trades logged yet.")
        return
        
    msg = "📈 **Recent Trade History (Last 10)**\n-------------------------------------\n"
    for pos in closed:
        pnl_sign = "+" if pos['pnl'] > 0 else ""
        msg += (
            f"• **#{pos['position_id']}** {pos['symbol']} {pos['direction']}\n"
            f"  Entry: {pos['entry_price']:.5f} | Exit: {pos['exit_price']:.5f}\n"
            f"  P&L: **{pnl_sign}${pos['pnl']:.2f} USD** | Risked: ${pos['risk_amount']:.2f}\n"
        )
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def journal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves a journal entry and runs it through AI for critique."""
    if not context.args:
        await update.message.reply_text(
            "❌ **Invalid Format**\n"
            "Use: `/journal <thoughts, emotions, learnings, or market views>`"
        )
        return
        
    notes = " ".join(context.args)
    status_msg = await update.message.reply_text("📓 _Marcus Vance is analyzing your journal entry..._")
    
    # Get last few trades for AI context
    recent_closed = database.get_closed_positions(limit=3)
    trades_summary = ""
    for pos in recent_closed:
        pnl_sign = "+" if pos['pnl'] > 0 else ""
        trades_summary += f"• Trade #{pos['position_id']}: {pos['symbol']} {pos['direction']}, P&L: {pnl_sign}${pos['pnl']:.2f}\n"
        
    ai_feedback = ai_engine.review_journal(notes, trades_summary, mode=get_current_mode())
    
    # Save in DB
    database.add_journal_entry(notes=notes, lessons_learned=ai_feedback)
    
    await status_msg.delete()
    
    response_msg = (
        "📓 **Journal Entry Logged**\n\n"
        f"💬 **Marcus Vance's Mentor Critique**:\n\n{ai_feedback}"
    )
    await update.message.reply_text(response_msg, parse_mode="Markdown")

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the risk percentage per trade."""
    if not context.args:
        await update.message.reply_text("❌ Use: `/risk <percentage>` (e.g. `/risk 1.5` or `/risk 2`)")
        return
        
    try:
        risk_pct = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Risk must be a valid number.")
        return
        
    if risk_pct <= 0 or risk_pct > 5.0:
        await update.message.reply_text(
            "❌ **Risk Limit Denied**\n\n"
            "Marcus Vance: _'Risking more than 5% per trade is financial suicide. "
            "A disciplined professional keeps it under 2% and never exceeds 5%. "
            "Set a sensible risk percentage, kid.'_"
        )
        return
        
    database.update_account_risk(risk_pct)
    await update.message.reply_text(
        f"🛡️ **Risk Limit Updated**\n\n"
        f"Risk limit is set to **{risk_pct}%** of equity per trade. Sizing will adjust automatically."
    )

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the account portfolio to start clean."""
    balance = 10000.0
    if context.args:
        try:
            balance = float(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Reset balance must be a number.")
            return
            
    database.reset_account(balance)
    await update.message.reply_text(
        "🔄 **Trading Account Reset**\n\n"
        "Database wiped clean.\n"
        f"Simulated balance reset to **${balance:,.2f} USD** at 1.0% risk per trade.\n"
        "Marcus Vance: _'Fresh start. Let's see if you've learned any discipline.'_"
    )

# CHART COMMAND

async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and renders a live historical chart for a currency pair."""
    if not context.args:
        await update.message.reply_text(
            "❌ **Invalid Format**\n"
            "Use: `/chart <symbol>` (e.g. `/chart EURUSD` or `/chart GBPUSD`)"
        )
        return
        
    symbol = context.args[0].upper()
    status_msg = await update.message.reply_text(f"📊 _Fetching data and drawing chart for {symbol}..._")
    
    try:
        chart_bytes = charting.generate_live_chart(symbol)
        await status_msg.delete()
        await update.message.reply_photo(
            photo=chart_bytes,
            caption=f"📊 Live Chart for {symbol.upper()}"
        )
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"❌ **Error drawing chart**: {str(e)}")

# PHOTO / IMAGE HANDLER (CHART ANALYSIS)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles chart uploads and triggers vision analysis."""
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or ""
    
    # Strip '/analyze' command from caption if present
    if caption.startswith("/analyze"):
        caption = caption[8:].strip()
        
    status_msg = await update.message.reply_text("📸 *Marcus is downloading and examining your chart...*", parse_mode="Markdown")
    
    try:
        # Download photo into bytes
        photo_bytearray = await photo_file.download_as_bytearray()
        photo_bytes = bytes(photo_bytearray)
        
        # Analyze using OpenAI Vision
        analysis = ai_engine.analyze_chart(photo_bytes, caption, mode=get_current_mode())
        
        await status_msg.delete()
        await update.message.reply_text(
            f"📊 **Marcus Vance's Chart Analysis**:\n\n{analysis}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"❌ Failed to analyze image: {str(e)}")

# NATURAL LANGUAGE CHAT HANDLER

async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes plain text messages to identify trade proposals or chat response."""
    text = update.message.text
    chat_id = update.effective_chat.id
    save_chat_id(chat_id)
    
    # Get account balance and risk settings
    acc = database.get_account()
    if not acc:
        await update.message.reply_text("❌ Account not initialized. Run `/start` to start.")
        return
        
    status_msg = await update.message.reply_text("💬 _Marcus is reading your message..._")
    
    # Pass current time context
    current_time_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Parse using AI engine
    result = ai_engine.parse_natural_language_trade(
        text=text,
        balance=acc['balance'],
        risk_pct=acc['risk_pct'],
        current_time=current_time_str,
        mode=get_current_mode()
    )
    
    await status_msg.delete()
    
    is_trade = result.get("is_trade_proposal", False)
    is_dropsignal = result.get("is_dropsignal_request", False)
    feedback = result.get("feedback", "No response from risk manager.")
    
    if is_dropsignal:
        session = result.get("requested_session")
        if session:
            progress_msg = await update.message.reply_text(f"💬 Marcus: _\"{feedback}\"_")
            await run_session_analysis(session, chat_id, context)
            await progress_msg.delete()
            return
            
    if not is_trade:
        # Just chat/mentorship response
        await update.message.reply_text(feedback)
        return
        
    # It is a trade proposal
    setup = result.get("parsed_setup", {})
    symbol = setup.get("symbol")
    direction = setup.get("direction")
    entry = setup.get("entry")
    sl = setup.get("sl")
    tp = setup.get("tp")
    thesis = setup.get("thesis") or "No thesis provided."
    
    if not all([symbol, direction, entry, sl, tp]):
        await update.message.reply_text(
            f"❌ **Incomplete Trade Parameters Detected**\n\n"
            f"Marcus Vance: _'I detected a trade idea in your text, but some parameters are missing. "
            f"Ensure you specify the symbol, direction (LONG/SHORT), entry price, Stop Loss, and Take Profit.'_\n\n"
            f"**Parsed Setup:**\n"
            f"• Symbol: {symbol or 'missing'}\n"
            f"• Direction: {direction or 'missing'}\n"
            f"• Entry: {entry or 'missing'}\n"
            f"• SL: {sl or 'missing'}\n"
            f"• TP: {tp or 'missing'}\n\n"
            f"💬 **Feedback**:\n_{feedback}_"
        )
        return
        
    # Validate risk parameters
    is_struct_valid, reason, _, _, rr = portfolio.calculate_risk_params(direction, entry, sl, tp)
    decision = result.get("decision", "REJECTED")
    
    # Check if the market is closed
    norm_symbol = exchange.normalize_symbol(symbol)
    if exchange.is_market_closed_for_symbol(norm_symbol):
        await update.message.reply_text(
            f"❌ **Market Closed Block**\n\n"
            f"Marcus Vance: _'I detected a trade idea for {symbol.upper()} in your message, but that market is currently closed. "
            f"Forex markets are closed from Friday 21:00 UTC to Sunday 21:00 UTC and on major global holidays. "
            f"Only Crypto markets are active 24/7. Stay sharp.'_"
        )
        return
        
    if decision == "APPROVED" and is_struct_valid:
        # Save pending trade details in user_data
        context.user_data['pending_trade'] = {
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "thesis": thesis
        }
        
        # Build inline keyboard buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Trade", callback_data="confirm_pending_trade"),
                InlineKeyboardButton("❌ Discard", callback_data="discard_pending_trade")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        proposal_text = (
            f"🔍 **PROPOSED TRADE AUDIT (APPROVED)**\n\n"
            f"**Setup Details:**\n"
            f"• Asset: {symbol.upper()}\n"
            f"• Direction: {direction}\n"
            f"• Entry Level: {entry:.5f}\n"
            f"• Stop Loss: {sl:.5f}\n"
            f"• Take Profit: {tp:.5f}\n"
            f"• Risk-to-Reward: {rr:.2f}\n"
            f"• Thesis: {thesis}\n\n"
            f"💬 **Marcus Vance's Audit**:\n_{feedback}_\n\n"
            f"Do you want to execute this simulated trade?"
        )
        
        # Try to generate chart visualization
        try:
            chart_bytes = charting.generate_live_chart(symbol, entry, sl, tp, direction)
            await update.message.reply_photo(
                photo=chart_bytes,
                caption=f"📊 Proposed {symbol.upper()} Trade Chart"
            )
        except Exception as e:
            logger.error(f"Error drawing pending chart: {e}")
            
        await update.message.reply_text(proposal_text, reply_markup=reply_markup, parse_mode="Markdown")
        
    else:
        # Rejected setup
        reject_text = (
            f"❌ **TRADE AUDIT REJECTED BY RISK MANAGER**\n\n"
            f"**Setup Details:**\n"
            f"• Asset: {symbol.upper()}\n"
            f"• Direction: {direction}\n"
            f"• Entry Level: {entry}\n"
            f"• Stop Loss: {sl}\n"
            f"• Take Profit: {tp}\n\n"
            f"**Audit Finding**: {reason or result.get('reason')}\n\n"
            f"💬 **Marcus Vance's Feedback**:\n_{feedback}_"
        )
        await update.message.reply_text(reject_text, parse_mode="Markdown")

# CALLBACK QUERY HANDLER FOR INLINE BUTTONS

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button clicks for trade confirmation."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "confirm_pending_trade":
        trade = context.user_data.get('pending_trade')
        if not trade:
            await query.edit_message_text("❌ Pending trade expired or not found.")
            return
            
        # Execute trade
        execution = portfolio.propose_and_open_trade(
            symbol=trade['symbol'],
            direction=trade['direction'],
            entry=trade['entry'],
            sl=trade['sl'],
            tp=trade['tp'],
            thesis=trade['thesis']
        )
        
        # Clear pending
        context.user_data['pending_trade'] = None
        
        if execution["success"]:
            msg = (
                "✅ **TRADE EXECUTED SUCCESSFULLY**\n\n"
                f"**Position #{execution['position_id']} Opened:**\n"
                f"• Symbol: {execution['symbol']}\n"
                f"• Direction: {execution['direction']}\n"
                f"• Size: {execution['size']:,} units\n"
                f"• Risked: ${execution['risk_amount']:.2f} USD\n"
                f"• R:R Ratio: {execution['rr_ratio']:.2f}\n"
            )
            await query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await query.edit_message_text(f"❌ **Execution Error**: {execution['reason']}")
            
    elif data == "discard_pending_trade":
        context.user_data['pending_trade'] = None
        await query.edit_message_text("❌ **Trade proposal discarded.** Marcus: _'Good choice. If in doubt, stay flat.'_")
        
    elif data == "switch_mode_forex":
        set_current_mode("forex")
        await query.edit_message_text(
            "💱 **Switched to Forex Mode**\n\n"
            "AI Persona: **Marcus Vance (20-year FX Veteran)**\n"
            "Briefings and order approvals are optimized for Forex and Commodities."
        )
    elif data == "switch_mode_crypto":
        set_current_mode("crypto")
        await query.edit_message_text(
            "🪙 **Switched to Crypto Mode**\n\n"
            "AI Persona: **Marcus Vance (30-year Crypto Specialist)**\n"
            "Briefings and order approvals are optimized for Crypto, including market stability checks."
        )
        
    elif data.startswith("trigger_signal_"):
        session = data.replace("trigger_signal_", "")
        chat_id = query.message.chat.id
        
        # Edit current message to show scanning progress
        await query.edit_message_text(f"⚡ _Generating {session.upper()} analysis & scanning markets..._")
        
        # Run analysis and drop signal
        await run_session_analysis(session, chat_id, context)
        
        # Delete progress message
        try:
            await query.delete_message()
        except Exception:
            pass

# DAILY SESSION ALERTS & SIGNAL DROP

async def run_session_analysis(session_key: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Compiles market data and runs Marcus's session signal generator."""
    session_mapping = {
        "tokyo": ("Tokyo Session Open", ["AUDUSD=X", "USDJPY=X", "NZDUSD=X", "BTC-USD"]),
        "london": ("London Session Open", ["EURUSD=X", "GBPUSD=X", "EURGBP=X", "ETH-USD"]),
        "new_york": ("New York Session Open", ["EURUSD=X", "USDJPY=X", "GC=F", "SOL-USD"]),
        "close": ("NY Session Recap", ["EURUSD=X", "GBPUSD=X", "BTC-USD"])
    }
    
    session_key = session_key.lower().strip()
    if session_key not in session_mapping:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Unknown session: '{session_key}'. Use: tokyo, london, new_york, or close."
        )
        return
        
    session_name, all_symbols = session_mapping[session_key]
    
    current_mode = get_current_mode()
    
    # Filter symbols by active mode
    if current_mode == "crypto":
        # Keep only Crypto symbols (use a list of 50 cryptos instead of the session specific ones)
        symbols = [
            "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LTC", "BCH", "LINK",
            "AVAX", "SHIB", "DOT", "UNI", "NEAR", "ICP", "APT", "SUI", "AAVE", "FTM",
            "GRT", "LDO", "OP", "ARB", "TIA", "IMX", "FET", "FIL", "HBAR", "ATOM",
            "VET", "ETC", "ALGO", "RUNE", "EGLD", "FLOW", "SAND", "MANA", "GALA", "LRC",
            "BAT", "ENJ", "ANKR", "KNC", "ZRX", "ONT", "QTUM", "ZEC", "DASH", "WAVES"
        ]
        
        # Override session name to avoid trading sessions references
        crypto_session_names = {
            "tokyo": "Crypto Morning Briefing",
            "london": "Crypto Midday Briefing",
            "new_york": "Crypto Afternoon Briefing",
            "close": "Crypto Daily Recap"
        }
        session_name = crypto_session_names.get(session_key, "Crypto Market Briefing")
        
        forex_closed = True
        forex_notice_msg = "ℹ️ **Notice**: Operating in Crypto Mode. Market analysis and signal scanner evaluate 50 major cryptocurrencies.\n\n"
    else:
        # Forex mode: keep Forex/Commodity symbols and filter out closed ones
        symbols = [sym for sym in all_symbols if exchange.is_forex_symbol(sym) and not exchange.is_market_closed_for_symbol(sym)]
        forex_closed = False
        forex_notice_msg = ""
        
    if not symbols:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📊 **{session_name}**\n\nAll markets for this session are currently closed."
        )
        return
    
    # Get live technical stats
    technical_summary = exchange.get_market_summary(symbols)
    
    # Run through OpenAI to get signal & analysis
    current_time_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    analysis_data = ai_engine.generate_session_signal(session_name, technical_summary, current_time=current_time_str, forex_closed=forex_closed, mode=current_mode)
    
    analysis_text = (
        f"📅 **SESSION BRIEFING: {session_name.upper()}** 📅\n"
        f"-------------------------------------\n\n"
        f"{forex_notice_msg}"
        f"{analysis_data.get('analysis', 'No analysis generated.')}\n\n"
    )
    
    has_signal = analysis_data.get("has_signal", False)
    signal = analysis_data.get("signal")
    
    chart_bytes = None
    
    if has_signal and signal:
        symbol = signal.get("symbol")
        direction = signal.get("direction")
        entry = signal.get("entry")
        sl = signal.get("sl")
        tp = signal.get("tp")
        timeframe = signal.get("timeframe") or "1H"
        thesis = signal.get("thesis") or "Session signal trigger."
        
        # Append timeframe to the thesis for DB storage
        full_thesis = f"[{timeframe}] {thesis}"
        
        # Execute trade automatically
        execution = portfolio.propose_and_open_trade(symbol, direction, entry, sl, tp, full_thesis)
        
        if execution["success"]:
            analysis_text += (
                f"🚨 **MARCUS VANCE'S SESSION SIGNAL DETECTED** 🚨\n\n"
                f"**Trade Executed Automatically (Position #{execution['position_id']}):**\n"
                f"• Asset: {execution['symbol']}\n"
                f"• Direction: {execution['direction']}\n"
                f"• Timeframe: {timeframe}\n"
                f"• Entry Level: {entry:.5f}\n"
                f"• Stop Loss (SL): {sl:.5f}\n"
                f"• Take Profit (TP): {tp:.5f}\n"
                f"• Position Size: {execution['size']:,} units\n"
                f"• Thesis: {thesis}"
            )
            
            try:
                # Generate chart with overlays
                chart_bytes = charting.generate_live_chart(symbol, entry, sl, tp, direction)
            except Exception as e:
                logger.error(f"Error drawing session signal chart: {e}")
        else:
            analysis_text += (
                f"⚠️ **Session Signal Blocked**: {execution['reason']}\n"
                f"• Attempted: {direction} {symbol} @ {entry} (SL: {sl}, TP: {tp})"
            )
    else:
        analysis_text += (
            f"ℹ️ **No Trade Signal Generated**\n\n"
            f"Marcus Vance: _'Market conditions are currently unstable, choppy, or lack high-probability setups. "
            f"Standing aside is also a position. Capital preservation is priority #1.'_\n"
        )
            
    # If no signal was executed, let's draw a standard chart of the first pair as a visual aid
    if not chart_bytes and symbols:
        try:
            chart_bytes = charting.generate_live_chart(symbols[0])
        except Exception:
            pass
            
    # Send content
    if chart_bytes:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=chart_bytes,
                caption=f"📊 Live Market snapshot for {session_name}"
            )
        except Exception as e:
            logger.error(f"Error sending session photo: {e}")
        
    await context.bot.send_message(
        chat_id=chat_id,
        text=analysis_text,
        parse_mode="Markdown"
    )

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows user to switch the active trading mode (Forex or Crypto)."""
    if context.args:
        new_mode = context.args[0].lower().strip()
        if new_mode in ["forex", "crypto"]:
            set_current_mode(new_mode)
            await update.message.reply_text(
                f"🔄 **Trading Mode Switched**\n\n"
                f"Active Mode: **{new_mode.upper()}**\n"
                f"AI Persona: **Marcus Vance ({'30-year Crypto Specialist' if new_mode == 'crypto' else '20-year FX Veteran'})**"
            )
            return
        else:
            await update.message.reply_text("❌ Mode must be either `forex` or `crypto`.")
            return

    # No args: show active mode and provide buttons
    current_mode = get_current_mode()
    keyboard = [
        [
            InlineKeyboardButton("💱 Forex Mode", callback_data="switch_mode_forex"),
            InlineKeyboardButton("🪙 Crypto Mode", callback_data="switch_mode_crypto")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📊 **Active Trading Mode** 📊\n\n"
        f"Current Mode: **{current_mode.upper()}**\n"
        f"AI Persona: **Marcus Vance ({'30-year Crypto Specialist' if current_mode == 'crypto' else '20-year FX Veteran'})**\n\n"
        f"Choose a mode to switch active briefings, AI reviews, and trade validation settings:",
        reply_markup=reply_markup
    )

async def dropsignal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually triggers session signal drop."""
    current_mode = get_current_mode()
    if not context.args:
        # Instead of error, let's offer inline buttons for easier session trigger
        if current_mode == "crypto":
            keyboard = [
                [
                    InlineKeyboardButton("🌅 Morning Briefing", callback_data="trigger_signal_tokyo"),
                    InlineKeyboardButton("☀️ Midday Briefing", callback_data="trigger_signal_london")
                ],
                [
                    InlineKeyboardButton("🌤️ Afternoon Briefing", callback_data="trigger_signal_new_york"),
                    InlineKeyboardButton("🌙 Daily Recap", callback_data="trigger_signal_close")
                ]
            ]
            text = "⚡ **Select Crypto Briefing** ⚡\n\nChoose an update slot to scan the crypto market and generate signals manually:"
        else:
            keyboard = [
                [
                    InlineKeyboardButton("🇯🇵 Tokyo Open", callback_data="trigger_signal_tokyo"),
                    InlineKeyboardButton("🇬🇧 London Open", callback_data="trigger_signal_london")
                ],
                [
                    InlineKeyboardButton("🇺🇸 New York Open", callback_data="trigger_signal_new_york"),
                    InlineKeyboardButton("🏁 NY Close Recap", callback_data="trigger_signal_close")
                ]
            ]
            text = "⚡ **Select Trading Session** ⚡\n\nChoose a session to scan markets and generate trade signals manually:"
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
        
    session = context.args[0].lower()
    chat_id = update.effective_chat.id
    save_chat_id(chat_id)
    
    status_msg = await update.message.reply_text(f"⚡ _Generating {session.upper()} analysis & scanning markets..._")
    await run_session_analysis(session, chat_id, context)
    await status_msg.delete()

# REPEATING DAILY SCHEDULER JOBS

async def daily_session_analysis_job(context: ContextTypes.DEFAULT_TYPE):
    """Repeating daily signal job. Triggers analysis for specified sessions."""
    job_data = context.job.data # Passes "tokyo", "london", etc.
    chat_ids = get_chat_ids()
    for cid in chat_ids:
        try:
            await run_session_analysis(job_data, cid, context)
        except Exception as e:
            logger.error(f"Failed to drop scheduled signal to chat {cid}: {e}")

# REPEATING MARKET MONITORING JOB

async def check_sl_tp_job(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled task that checks for hit Stop Loss or Take Profit levels."""
    triggered = portfolio.check_and_trigger_sl_tp()
    if not triggered:
        return
        
    # Alert all active chat IDs
    chat_ids = get_chat_ids()
    for event in triggered:
        pnl_sign = "+" if event['pnl'] > 0 else ""
        msg = (
            f"🚨 **POSITION CLOSED AUTOMATICALLY** 🚨\n\n"
            f"Position #{event['position_id']} ({event['symbol']} {event['direction']}) "
            f"hit its **{event['trigger_type']}** at **{event['trigger_price']:.5f}**.\n\n"
            f"P&L: **{pnl_sign}${event['pnl']:.2f} USD**\n"
        )
        
        acc = database.get_account()
        if acc:
            msg += f"New Account Balance: **${acc['balance']:,.2f} USD**"
            
        for cid in chat_ids:
            try:
                await context.bot.send_message(chat_id=cid, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send alert to chat {cid}: {e}")

# BOT ENTRYPOINT

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not set or is still the default. Exiting.")
        return
        
    database.init_db()
    
    app = ApplicationBuilder().token(token).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("balance", portfolio_cmd))
    app.add_handler(CommandHandler("trade", trade_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(CommandHandler("dropsignal", dropsignal_cmd))
    app.add_handler(CommandHandler("close", close_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("journal", journal_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    
    # Callback query handler for confirmation buttons
    app.add_handler(CallbackQueryHandler(button_click))
    
    # Message Handlers
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    # Handle natural language trading chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat_message))
    
    # Background Market Job (runs every 30 seconds to check SL/TP)
    if app.job_queue:
        app.job_queue.run_repeating(check_sl_tp_job, interval=30, first=10)
        
        # Tokyo session: 00:00 UTC
        app.job_queue.run_daily(
            daily_session_analysis_job,
            time=datetime.time(hour=0, minute=0, second=0, tzinfo=datetime.timezone.utc),
            data="tokyo"
        )
        # London session: 07:00 UTC
        app.job_queue.run_daily(
            daily_session_analysis_job,
            time=datetime.time(hour=7, minute=0, second=0, tzinfo=datetime.timezone.utc),
            data="london"
        )
        # New York session: 12:00 UTC
        app.job_queue.run_daily(
            daily_session_analysis_job,
            time=datetime.time(hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc),
            data="new_york"
        )
        # NY Close: 17:00 UTC
        app.job_queue.run_daily(
            daily_session_analysis_job,
            time=datetime.time(hour=17, minute=0, second=0, tzinfo=datetime.timezone.utc),
            data="close"
        )
        
        logger.info("Background job queue initialized for SL/TP monitoring and session briefs.")
    else:
        logger.warning("Job queue not available. Dynamic SL/TP check and scheduled signals disabled.")
        
    logger.info("Starting Telegram Bot poll loop...")
    app.run_polling()

if __name__ == "__main__":
    main()
