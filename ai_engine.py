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

# Marcus Vance, the disciplined veteran FX trader persona
SYSTEM_INSTRUCTION = """
You are Marcus Vance, a 20-year veteran Head of FX Trading and ex-prop firm risk manager.
Your mission is to act as a strict, disciplined, and highly experienced mentor to the user.
Your core principles are:
1. Capital preservation is job #1. You care more about not losing money than making it.
2. Every single trade must have a hard Stop Loss (SL) and a logical Take Profit (TP).
3. Risk-to-Reward (R:R) must be at least 1:1.5, preferably 1:2 or more.
4. Dynamic position sizing must be respected. No oversized positions, no "going all in".
5. Never trade out of FOMO, anger, or revenge. If you see signs of emotional trading, shut it down immediately.
6. A professional trader trades a plan, not a whim. There must be a clear technical or fundamental catalyst.

You will receive trade proposals, charts, or journal entries from the user. You must analyze them and provide your veteran feedback.
"""

def review_trade_proposal(symbol: str, direction: str, entry: float, sl: float, tp: float, thesis: str, balance: float, risk_pct: float) -> dict:
    """
    Evaluates a proposed trade from a professional risk manager perspective.
    Returns a dictionary with decision, reasons, suggestions, and coaching feedback.
    """
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
    Please review this Forex trade proposal:
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
                {"role": "system", "content": SYSTEM_INSTRUCTION},
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

def analyze_chart(image_bytes: bytes, user_query: str = "") -> str:
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
                {"role": "system", "content": SYSTEM_INSTRUCTION},
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

def review_journal(notes: str, trades_summary: str = "") -> str:
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
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Journal review failed: {str(e)}"

def parse_natural_language_trade(text: str, balance: float, risk_pct: float) -> dict:
    """
    Parses natural language chat to identify if a trade proposal is present.
    If present, extracts parameters and performs a professional audit.
    If not, provides a chat response in Marcus Vance's persona.
    """
    if not client:
        return {
            "is_trade_proposal": False,
            "feedback": "OpenAI API Key not configured. Please set OPENAI_API_KEY in your .env file."
        }

    prompt = f"""
    The user is chatting with you. Inspect their message:
    "{text}"
    
    Account Context:
    - Balance: ${balance:,.2f}
    - Risk Percentage: {risk_pct}% (${balance * risk_pct / 100:,.2f} USD)
    
    Determine if they are proposing/suggesting a trade setup (buying/selling/longing/shorting an asset).
    
    If they ARE proposing a trade setup:
    1. Parse the setup: symbol (e.g. EURUSD), direction (LONG or SHORT), entry price, stop loss (SL), take profit (TP), and their reasoning/thesis.
    2. Audit the trade using your core disciplined criteria:
       - Stop loss and take profit must exist.
       - Risk-to-Reward ratio must be at least 1:1.5, preferably 1:2.
       - The entry price should be logical relative to SL/TP.
    3. Formulate your decision: APPROVED (if it fits structural rules and looks like a disciplined trade) or REJECTED.
    
    If they are NOT proposing a trade (e.g. just asking a question, saying hi, chatting, complaining about a loss):
    - Set is_trade_proposal = false.
    - Respond to their message in your persona as Marcus Vance, giving them trading wisdom, psychology coaching, or general guidance.
    - Note: If they are asking for trading signals, market updates, or session setups, advise them in your persona that they can trigger a live market scan and generate signals using the `/dropsignal <tokyo/london/new_york/close>` command, or that they can expect scheduled daily briefs during those sessions. Explain that this command scans live charts for high-probability setups.
    
    Respond STRICTLY in JSON format with the following keys:
    {{
        "is_trade_proposal": true or false,
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
        "feedback": "Your mentoring response/feedback in your persona as Marcus Vance."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
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
            "feedback": f"Marcus Vance is having trouble hearing you: {str(e)}"
        }

def generate_session_signal(session_name: str, technical_summary: str) -> dict:
    """
    Generates a structured trading session market analysis and drops a trade 
    signal if a high-probability trade exists.
    """
    if not client:
        return {
            "analysis": "OpenAI API Key not configured. Cannot generate session analysis.",
            "has_signal": False,
            "signal": None
        }

    prompt = f"""
    You are Marcus Vance, preparing your market brief for the **{session_name}** session open.
    
    Here is the live technical data compiled for major Forex currency pairs and commodities:
    {technical_summary}
    
    Your task is to write a professional, highly disciplined market analysis.
    
    Step 1: Write a concise, structured market overview (1-2 paragraphs) in markdown format. Evaluate the trends, support/resistance levels, and where the momentum lies. Speak like a senior PM mentor.
    
    Step 2: Look for high-probability trade setups conforming to our strict rules:
    - Setup must have a clear catalyst.
    - Risk-to-Reward ratio must be at least 1:2.
    - Stop loss must be placed at a logical invalidation point (e.g. above/below recent daily highs/lows or moving averages).
    
    If such a setup exists, formulate a trade signal.
    If no setup meets our high standards, state clearly: "No high-probability setups conform to our risk profile for this session. Capital preservation is key. We remain flat." Set has_signal = false and signal = null.
    
    Respond STRICTLY in JSON format with the following keys:
    {{
        "analysis": "Your markdown formatted session outlook written in your mentor persona.",
        "has_signal": true or false,
        "signal": {{
            "symbol": "string (e.g. EURUSD)",
            "direction": "LONG or SHORT",
            "entry": float (current spot rate or slightly adjusted limit entry),
            "sl": float (stop loss level),
            "tp": float (take profit target),
            "thesis": "1-sentence explanation of why we are taking this trade."
        }} or null
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
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
