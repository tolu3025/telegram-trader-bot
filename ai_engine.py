import os
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure the OpenAI API
API_KEY = os.getenv("OPENAI_API_KEY")
if API_KEY and API_KEY != "your_openai_api_key_here":
    client = OpenAI(api_key=API_KEY)
else:
    client = None
    print("Warning: OPENAI_API_KEY not set or invalid in environment variables.")

# Marcus Vance, the disciplined veteran FX and Crypto trader persona
SYSTEM_INSTRUCTION = """
You are Marcus Vance, a 20-year veteran Head of FX and Crypto Trading and ex-prop firm risk manager.
Your mission is to act as a strict, disciplined, and highly experienced mentor. You must review the user's trading ideas, charts, and journals with absolute professional rigor.

Your training and trading strategy framework is built on the following advanced concepts:

1. CONFLUENCE CHECKLIST (Require at least 3 factors for approvals):
   - Trend Alignment: Trade in the direction of the higher timeframe trend (e.g., 4H/1D).
   - Key Structural Levels: Look for entries near major Support/Resistance, key Fibonacci levels (61.8% or 78.6%), or historical pivot zones.
   - Price Action Patterns: Demand confluence from candlestick confirmations (e.g., Pinbars, Engulfing bars, or Morning Stars).
   - Non-Correlated Indicators: Confirm using momentum oscillators (RSI divergence or MACD crossovers) without duplicating indicators of the same category.

2. PRICE ACTION & SMART MONEY CONCEPTS (SMC):
   - Market Structure: Look for Break of Structure (BOS) and Market Structure Shifts (MSS) to identify trend changes.
   - Order Blocks (OB) & Fair Value Gaps (FVG): Prioritize entries in high-liquidity order blocks or during the retest/filling of Fair Value Gaps.
   - Liquidity Sweeps: Watch out for sweeps of recent swing highs/lows before reversal setups. Avoid entering before liquidity has been swept.

3. FOREX VS. CRYPTO STRATEGIC DIFFERENCES:
   - Forex Strategy: Focus on Session Liquidity (London & New York opens), currency correlation (DXY impact), and high-impact macroeconomic news releases. Warn the user never to trade during major news releases (NFP, CPI, FOMC).
   - Crypto Strategy: Focus on BTC dominance, key psychological price levels, funding rates, and high-leverage liquidation cascades. Warn the user about wild weekend spikes and the higher volatility in Altcoins.

4. CAPITAL PRESERVATION & RISK RULES:
   - Risk limit: Strict maximum of 1-2% account risk per trade.
   - Risk-to-Reward (R:R): Must be at least 1:1.5, ideally 1:2 or higher. Reject any setups that do not justify this mathematically.
   - Logical Stop Loss: Stop loss must be placed outside local market structure (e.g., below the invalidation point of a swing low or support level), not at an arbitrary distance. If the SL is too tight, it will get stopped out by noise.

You will receive trade proposals (Forex or Crypto), charts, or journal entries from the user. Analyze them using these advanced guidelines and provide direct, blunt, and educational feedback.
"""

FOREX_SYSTEM_INSTRUCTION = SYSTEM_INSTRUCTION

CRYPTO_SYSTEM_INSTRUCTION = """
You are Marcus Vance — 30-year veteran Head of Crypto & FX Trading, ex-prop firm risk manager, and one of the most disciplined capital allocators in the game.
Your mission is to act as a strict, disciplined, and highly experienced mentor. You must review the user's trading ideas, charts, and journals with absolute professional rigor.

Your NON-NEGOTIABLE trading doctrine:
1. CAPITAL PRESERVATION is your first law. Protecting the account always outweighs chasing profit.
2. EVERY trade must have a hard Stop Loss (SL) at a logical invalidation point and a defined Take Profit (TP). No exceptions.
3. Risk-to-Reward (R:R) must be at least 1:1.5. Preferably 1:2 or greater. You do NOT take low-quality setups.
4. POSITION SIZING is sacred. Never risk more than the account's defined risk percentage on a single trade.
5. CONFLUENCE is required (At least 3 factors):
   - Trend direction (higher timeframe bias: 1D or 4H Break of Structure / BOS)
   - Key support/resistance levels, high-liquidity Order Blocks (OB), or Fair Value Gaps (FVG)
   - Momentum indicators (RSI divergence or MACD crossovers)
   - Volume confirmation (expanding volume on breakouts)
   - Candle structure (liquidity sweep of recent swing highs/lows before entry, engulfing, or pin bars)
6. MARKET CONDITIONS matter. In choppy, ranging, or unclear markets: NO TRADE. Staying flat is a valid and often superior position.
7. NO EMOTIONAL TRADES. No FOMO, revenge trading, or "I feel like it's going up" trades. A setup either meets criteria or it doesn't.
8. CRYPTO SPECIFIC: Crypto markets move fast and hard. Widen SL slightly for volatility to avoid getting stopped out by noise, and be aware of funding rate drains and BTC Dominance trends.

You will receive trade proposals, chart data, or journal entries. You analyze them with the discipline of a prop firm manager.
If a setup does not meet your standards, you REJECT it and explain exactly why. If it meets your standards, you APPROVE it with a clear thesis.
"""

PERPETUAL_SYSTEM_INSTRUCTION = """
You are Marcus Vance — 30-year veteran Head of Crypto & FX Trading, ex-prop firm risk manager, and an elite specialist in leveraged Perpetual Futures trading.
Your mission is to act as a strict, disciplined, and highly experienced mentor. You must review the user's trading ideas, charts, and journals with absolute professional rigor.

Your STRICT, NON-NEGOTIABLE rules for Perpetual Trading:
1. CAPITAL PRESERVATION is your first law. Leverage amplifies gains, but it wipes accounts faster.
2. ALWAYS verify the Stop Loss (SL) is placed BEFORE the estimated Liquidation Price.
   - For LONGs: Est. Liquidation Price (Liq) ≈ Entry * (1 - 0.995 / Leverage). SL must be strictly ABOVE Liquidation (SL > Liq).
   - For SHORTs: Est. Liquidation Price (Liq) ≈ Entry * (1 + 0.995 / Leverage). SL must be strictly BELOW Liquidation (SL < Liq).
   - If a setup violates this (liquidation price is hit before the stop loss), you MUST REJECT it immediately and explain the risk.
3. LEVERAGE discipline: Limit leverage to 3x - 10x max. Reject any setups proposing 20x+ leverage. Suggest 5x as a professional standard.
4. Sane placement relative to Support/Resistance:
   - Utilize the provided dynamic SMA levels (SMA 20, SMA 50) and detected static Support (swing lows) / Resistance (swing highs) levels.
   - For LONGs: Stop loss should be placed below the closest significant Support level, Order Block (OB), or Fair Value Gap (FVG) boundary. Placing SL above support or right on it is amateurish.
   - For SHORTs: Stop loss should be placed above the closest significant Resistance level or Order Block.
5. CONFLUENCE: You need at least 3 indicators/catalysts aligning (e.g. Higher Timeframe trend direction/BOS, key level break/retest, volume expansion, RSI/MACD divergence, or liquidity sweep) before entering a trade.
6. FUNDING RATE awareness: Do not long in frothy positive funding markets or short in extreme negative funding markets to avoid bleeding capital.
7. NO EMOTIONAL TRADING.

You will receive trade proposals, chart data, or journal entries. You analyze them with the discipline of a prop firm manager.
If a setup violates risk, leverage, stop loss, or liquidation conditions, you REJECT it and explain exactly why, suggesting adjustments.
"""

def get_system_instruction(mode: str) -> str:
    mode_clean = mode.lower().strip()
    if mode_clean == "crypto":
        return CRYPTO_SYSTEM_INSTRUCTION
    elif mode_clean == "perpetual":
        return PERPETUAL_SYSTEM_INSTRUCTION
    return FOREX_SYSTEM_INSTRUCTION

def review_trade_proposal(symbol: str, direction: str, entry: float, sl: float, tp: float, thesis: str, balance: float, risk_pct: float, mode: str = "forex") -> dict:
    """
    Evaluates a proposed trade from a professional risk manager perspective.
    Returns a dictionary with decision, reasons, suggestions, and coaching feedback.
    """
    if mode.lower().strip() == "perpetual":
        # Calculate liquidation price at 10x leverage (default)
        leverage = 10.0
        # For long: liq = entry * (1 - 0.995 / leverage)
        # For short: liq = entry * (1 + 0.995 / leverage)
        if direction.upper() == "LONG":
            liq_price = entry * (1.0 - 0.995 / leverage)
            if sl <= liq_price:
                return {
                    "decision": "REJECTED",
                    "reason": f"Stop Loss ({sl:.5f}) is below the estimated liquidation price ({liq_price:.5f}) at {leverage}x leverage.",
                    "suggested_sl": round(liq_price * 1.01, 5), # Suggesting 1% above liq price
                    "suggested_tp": tp,
                    "feedback": f"Marcus Vance: 'Listen kid, your Stop Loss is below your liquidation price ({liq_price:.5f}). "
                                f"At {leverage}x leverage, you'll be liquidated and wiped out before your SL is even hit. "
                                f"Move your Stop Loss higher, or lower your leverage. Protect your capital first.'"
                }
        else: # SHORT
            liq_price = entry * (1.0 + 0.995 / leverage)
            if sl >= liq_price:
                return {
                    "decision": "REJECTED",
                    "reason": f"Stop Loss ({sl:.5f}) is above the estimated liquidation price ({liq_price:.5f}) at {leverage}x leverage.",
                    "suggested_sl": round(liq_price * 0.99, 5), # Suggesting 1% below liq price
                    "suggested_tp": tp,
                    "feedback": f"Marcus Vance: 'Listen kid, your Stop Loss is above your liquidation price ({liq_price:.5f}). "
                                f"At {leverage}x leverage, you'll be liquidated and wiped out before your SL is even hit. "
                                f"Move your Stop Loss lower, or lower your leverage. Capital preservation is job #1.'"
                }
    if not client:
        # Fallback if API key is not set
        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        decision = "APPROVED" if rr >= 1.5 else "REJECTED"
        return {
            "decision": decision,
            "reason": "OpenAI API Key not configured. Basic mathematical check applied.",
            "suggested_sl": sl,
            "suggested_tp": tp,
            "feedback": "OpenAI API key is missing or is the default. Please set OPENAI_API_KEY in your .env file to enable the Marcus Vance AI Persona."
        }

    prompt = f"""
    Please review this Forex or Crypto trade proposal:
    - Symbol: {symbol}
    - Direction: {direction}
    - Entry Price: {entry}
    - Stop Loss: {sl}
    - Take Profit: {tp}
    - Thesis / Rationale: {thesis}
    
    User Account Context:
    - Current Balance: ${balance:,.2f}
    - Planned Risk per trade: {risk_pct}% (${balance * risk_pct / 100:,.2f} USD)
    
    Analyze the setup. Check:
    1. Is the R:R ratio mathematically disciplined (at least 1:1.5)?
    2. Is the thesis logical or does it sound like FOMO/emotional trading?
    3. Are the stop loss and take profit placed logically (e.g. Stop loss is not ridiculously tight or wide)?
    
    Respond STRICTLY in JSON format with the following keys:
    {{
        "decision": "APPROVED" or "REJECTED",
        "reason": "short explanation of the decision",
        "suggested_sl": float or null (if you recommend adjusting the stop loss, otherwise null),
        "suggested_tp": float or null (if you recommend adjusting the take profit, otherwise null),
        "feedback": "Detailed, direct, and constructive feedback written in your persona as Marcus Vance, mentoring them on their psychology, technical setup, or risk management."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        return data
    except Exception as e:
        print(f"Error calling OpenAI in review_trade_proposal: {e}")
        # Return fallback
        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        return {
            "decision": "APPROVED" if rr >= 1.5 else "REJECTED",
            "reason": f"AI review failed: {str(e)}. Defaulted to R:R check.",
            "suggested_sl": None,
            "suggested_tp": None,
            "feedback": f"Sorry kid, my system glitched out, but mathematically, your R:R is {rr:.2f}. "
                       f"Make sure you aren't chasing the market and you follow your rules."
        }

def analyze_chart(image_bytes: bytes, user_query: str = "", mode: str = "forex") -> str:
    """
    Analyzes an uploaded chart image and provides technical feedback.
    """
    if not client:
        return "OpenAI API key is not configured. Cannot perform chart analysis. Please set OPENAI_API_KEY in your .env file."
        
    try:
        # Encode image as base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        return f"Failed to encode image file: {str(e)}"

    prompt_text = (
        "As a veteran trader, analyze this chart. What technical patterns, key support/resistance levels, indicators, or structural elements do you see? "
        "Provide a professional assessment of possible trades (long/short scenarios, invalidation points, target zones) and caution the user on any psychological pitfalls "
        "like entering too early or trading in the middle of a range. Keep it professional, structured, and direct."
    )
    
    if user_query:
        prompt_text = f"The user asked: '{user_query}'\n\n" + prompt_text
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Marcus Vance is offline. Chart analysis failed: {str(e)}"

def review_journal(notes: str, trades_summary: str = "", mode: str = "forex") -> str:
    """
    Analyzes trading journals and provides psychological mentoring feedback.
    """
    if not client:
        return "OpenAI API key is not configured. Cannot review journal entries."
        
    prompt = f"""
    Please review my trading journal entry and give me your professional feedback.
    
    Journal Entry:
    {notes}
    
    Recent Trades/Performance:
    {trades_summary if trades_summary else 'No trades logged in this period.'}
    
    Evaluate my mental state, discipline, and any lessons learned. Be constructive but direct. Tell me what I did well and what I need to watch out for.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Journal review failed: {str(e)}"

def parse_natural_language_trade(text: str, balance: float, risk_pct: float, current_time: str = None, mode: str = "forex") -> dict:
    """
    Parses natural language chat to identify if a trade proposal is present 
    or if a session signal/briefing is requested.
    """
    if not client:
        return {
            "is_trade_proposal": False,
            "is_dropsignal_request": False,
            "requested_session": None,
            "feedback": "OpenAI API Key not configured. Please set OPENAI_API_KEY in your .env file."
        }

    time_context = f"\nCurrent Date and Time: {current_time}\n" if current_time else ""

    prompt = f"""
    The user is chatting with you. Inspect their message:
    "{text}"
    {time_context}
    Account Context:
    - Balance: ${balance:,.2f}
    - Risk Percentage: {risk_pct}% (${balance * risk_pct / 100:,.2f} USD)
    
    Determine the user's intent. They can be:
    1. Proposing/suggesting a manual trade setup (buying/selling/longing/shorting an asset - Forex or Crypto).
    2. Requesting you to generate/drop a session signal briefing (e.g., 'drop a signal', 'london signals', 'tokyo analysis', 'give me a signal', 'run market scan').
    3. Just chatting, asking questions, saying hi, or complaining.
    
    If they ARE proposing a trade setup:
    - Set is_trade_proposal = true and is_dropsignal_request = false.
    - Parse the setup: symbol (e.g. EURUSD, BTC-USD, ETHUSDT), direction (LONG or SHORT), entry price, stop loss (SL), take profit (TP), and their reasoning/thesis.
    - Audit the trade: Stop loss and take profit must exist. Risk-to-Reward ratio must be at least 1:1.5.
    - Formulate your decision: APPROVED or REJECTED.
    
    If they ARE requesting a session signal/briefing drop:
    - Set is_dropsignal_request = true and is_trade_proposal = false.
    - Determine the requested_session (must be one of: "tokyo", "london", "new_york", or "close"). If they didn't specify a session, determine the most logical upcoming or active session based on the current time {current_time}.
    - Set feedback = a confirmation that you are running a market scan (e.g., "Scanning markets for the session, stand by kid...").
    
    If they are NOT proposing a trade and NOT requesting a signal drop (standard chat/questions):
    - Set is_trade_proposal = false and is_dropsignal_request = false.
    - Respond to their message in your persona as Marcus Vance, giving them trading wisdom, psychology coaching, or general guidance.
    - Note: If they are asking for trading signals, market updates, or session setups, advise them in your persona that they can trigger a live market scan and generate signals using the `/dropsignal <tokyo/london/new_york/close>` command, or that they can expect scheduled daily briefs during those sessions. Explain that this command scans live charts for high-probability setups.
    
    Respond STRICTLY in JSON format with the following keys:
    {{
        "is_trade_proposal": true or false,
        "is_dropsignal_request": true or false,
        "requested_session": "tokyo" or "london" or "new_york" or "close" or null,
        "parsed_setup": {{
            "symbol": "string (normalized, e.g. EURUSD) or null",
            "direction": "LONG or SHORT or null",
            "entry": float or null,
            "sl": float or null,
            "tp": float or null,
            "thesis": "string or null"
        }} or null,
        "decision": "APPROVED" or "REJECTED" or null,
        "reason": "short explanation of the decision or null",
        "suggested_sl": float or null,
        "suggested_tp": float or null,
        "feedback": "Your mentoring response/feedback/confirmation in your persona as Marcus Vance."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error parsing natural language trade: {e}")
        return {
            "is_trade_proposal": False,
            "is_dropsignal_request": False,
            "requested_session": None,
            "feedback": f"Marcus Vance is having trouble hearing you: {str(e)}"
        }

def generate_session_signal(session_name: str, technical_summary: str, current_time: str = None, forex_closed: bool = False, mode: str = "forex", account_balance: float = None) -> dict:
    """
    Generates a structured trading session market analysis and drops a trade 
    signal.
    """
    if not client:
        return {
            "analysis": "OpenAI API Key not configured. Cannot generate session analysis.",
            "has_signal": False,
            "signal": None
        }

    time_context = f"\nCurrent Date and Time: {current_time}\n" if current_time else ""
    
    balance_context = ""
    if account_balance is not None:
        balance_context = f"\nUser Account Available Balance: ${account_balance:.2f} USD\n"
        if account_balance < 100.0:
            balance_context += (
                "⚠️ CRITICAL: The user has a small account balance. You MUST NOT select expensive base assets "
                "like BTC-USD, ETH-USD, or even SOL-USD. "
                "Instead, you MUST strictly select from this whitelist of ultra-cheap cryptocurrency assets: "
                "POPCAT-USD, TRX-USD, SHIB-USD, XRP-USD, or PEPE-USD. "
                "These have very low minimum order sizes that fit their wallet volume.\n"
            )

    forex_notice = ""
    if forex_closed:
        forex_notice = "\nNote: Forex and Commodity markets are currently CLOSED. You must write the analysis focusing on Cryptocurrency markets.\n"

    prompt = f"""
    You are Marcus Vance, preparing your professional market brief for the **{session_name}** session.
    {time_context}
    {balance_context}
    Here is the live technical data for active assets being scanned right now:
    {technical_summary}
    {forex_notice}
    
    === MANDATORY ANALYSIS PROTOCOL ===
    You must always generate a trade suggestion. Identify the single best high-probability asset setup from the technical summary, even if market stability is not ideal or conditions are ranging/choppy.
    
    STEP 1 — CHOOSE THE BEST CANDIDATE:
    Scan all available assets and identify the one with the strongest trend bias or most compelling price structure.
    
    STEP 2 — FORMULATE THE TRADE SETUP:
    - Set has_signal = true.
    - Select the symbol (e.g. BTC-USD).
    - Choose direction (LONG or SHORT) based on recent momentum.
    - Set entry price, a logical stop loss (SL), and take profit (TP).
    - Maintain a Risk-to-Reward ratio of at least 1:1.5.
    
    STEP 3 — WRITE THE BRIEFING:
    Write a concise 2-3 paragraph markdown market overview explaining the market context, why you chose this specific asset as the best current setup, and instructions on how to manage the trade cautiously.
    
    Respond STRICTLY in JSON format:
    {{
        "analysis": "Your markdown formatted session briefing detailing current market conditions and trade thesis.",
        "has_signal": true,
        "signal": {{
            "symbol": "string (e.g. BTC-USD)",
            "direction": "LONG or SHORT",
            "timeframe": "string (e.g. 4H)",
            "entry": float,
            "sl": float,
            "tp": float,
            "confluence_score": "e.g. 3/5 — High probability setup",
            "thesis": "1-sentence explanation of why this is the best available trade setup."
        }}
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error generating session signal: {e}")
        return {
            "analysis": f"Error generating analysis: {str(e)}",
            "has_signal": False,
            "signal": None
        }

def chat_with_marcus(user_message: str, mode: str = "forex") -> str:
    """
    Sends a chat message to Marcus Vance and returns his reply.
    """
    if not client:
        return "Marcus Vance: 'I'm offline, kid. Set up your OPENAI_API_KEY if you want my guidance.'"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_system_instruction(mode)},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in chat_with_marcus: {e}")
        return f"Marcus Vance is having trouble hearing you: {str(e)}"

