from supabase import create_client, Client
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("Warning: SUPABASE_URL or SUPABASE_KEY not set in environment variables.")

def init_db():
    """Initializes the database tables. Done via DDL in Supabase."""
    if supabase:
        try:
            acc = get_account(1)
            if not acc:
                print("Account #1 not found. Initializing default account...")
                supabase.table("accounts").insert({
                    "account_id": 1,
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "risk_pct": 1.0
                }).execute()
        except Exception as e:
            print(f"Error initializing default account in init_db: {e}")

# ACCOUNT OPERATIONS
def get_account(account_id=1):
    if not supabase:
        return None
    try:
        response = supabase.table("accounts").select("*").eq("account_id", account_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error in get_account: {e}")
        return None

def update_account_balance(balance, equity, account_id=1):
    if not supabase:
        return
    try:
        supabase.table("accounts").update({"balance": balance, "equity": equity}).eq("account_id", account_id).execute()
    except Exception as e:
        print(f"Error in update_account_balance: {e}")

def update_account_risk(risk_pct, account_id=1):
    if not supabase:
        return
    try:
        supabase.table("accounts").update({"risk_pct": risk_pct}).eq("account_id", account_id).execute()
    except Exception as e:
        print(f"Error in update_account_risk: {e}")

def reset_account(balance=10000.0, account_id=1):
    if not supabase:
        return
    try:
        # Delete positions & journals
        supabase.table("positions").delete().neq("position_id", -1).execute()
        supabase.table("journals").delete().neq("journal_id", -1).execute()
        # Update account
        supabase.table("accounts").update({
            "balance": balance,
            "equity": balance,
            "risk_pct": 1.0
        }).eq("account_id", account_id).execute()
    except Exception as e:
        print(f"Error in reset_account: {e}")

# POSITION OPERATIONS
def open_position(symbol, direction, entry_price, size, stop_loss, take_profit, thesis, risk_amount):
    if not supabase:
        return None
    try:
        response = supabase.table("positions").insert({
            "symbol": symbol.upper(),
            "direction": direction.upper(),
            "entry_price": entry_price,
            "size": size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "OPEN",
            "thesis": thesis,
            "risk_amount": risk_amount
        }).execute()
        return response.data[0]["position_id"] if response.data else None
    except Exception as e:
        print(f"Error in open_position: {e}")
        return None

def get_open_positions():
    if not supabase:
        return []
    try:
        response = supabase.table("positions").select("*").eq("status", "OPEN").execute()
        return response.data
    except Exception as e:
        print(f"Error in get_open_positions: {e}")
        return []

def get_position(position_id):
    if not supabase:
        return None
    try:
        response = supabase.table("positions").select("*").eq("position_id", position_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error in get_position: {e}")
        return None

def close_position(position_id, exit_price, pnl):
    if not supabase:
        return 10000.0
    try:
        now_str = datetime.now().isoformat()
        supabase.table("positions").update({
            "status": "CLOSED",
            "exit_price": exit_price,
            "pnl": pnl,
            "closed_at": now_str
        }).eq("position_id", position_id).execute()
        
        # Fetch current account balance and update it
        account = get_account(1)
        if account:
            new_balance = account['balance'] + pnl
            update_account_balance(new_balance, new_balance, 1)
            return new_balance
        return 10000.0
    except Exception as e:
        print(f"Error in close_position: {e}")
        return 10000.0

def get_closed_positions(limit=50):
    if not supabase:
        return []
    try:
        response = supabase.table("positions").select("*").eq("status", "CLOSED").order("closed_at", desc=True).limit(limit).execute()
        return response.data
    except Exception as e:
        print(f"Error in get_closed_positions: {e}")
        return []

# JOURNAL OPERATIONS
def add_journal_entry(notes, market_regime=None, psychological_state=None, lessons_learned=None):
    if not supabase:
        return
    try:
        supabase.table("journals").insert({
            "market_regime": market_regime,
            "psychological_state": psychological_state,
            "notes": notes,
            "lessons_learned": lessons_learned
        }).execute()
    except Exception as e:
        print(f"Error in add_journal_entry: {e}")

def get_journal_entries(limit=10):
    if not supabase:
        return []
    try:
        response = supabase.table("journals").select("*").order("timestamp", desc=True).limit(limit).execute()
        return response.data
    except Exception as e:
        print(f"Error in get_journal_entries: {e}")
        return []

# STATISTICS CALCULATION
def get_portfolio_stats():
    if not supabase:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0
        }
    try:
        # Get all closed trades
        response = supabase.table("positions").select("pnl, risk_amount").eq("status", "CLOSED").execute()
        trades = response.data
        total_trades = len(trades)
        
        if total_trades == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_profit": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0
            }
            
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in trades if t['pnl'] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100
        net_profit = sum(t['pnl'] for t in trades)
        
        gross_profits = sum(wins)
        gross_losses = abs(sum(losses))
        
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)
        
        avg_win = sum(wins) / len(wins) if len(wins) > 0 else 0.0
        avg_loss = sum(losses) / len(losses) if len(losses) > 0 else 0.0
        
        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "net_profit": net_profit,
            "average_win": avg_win,
            "average_loss": avg_loss
        }
    except Exception as e:
        print(f"Error in get_portfolio_stats: {e}")
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0
        }
