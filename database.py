from supabase import create_client, Client
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "your_supabase_url_here" and SUPABASE_KEY != "your_supabase_key_here":
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Connected to Supabase database successfully.")
    except Exception as e:
        supabase = None
        print(f"Failed to connect to Supabase: {e}. Falling back to SQLite.")
else:
    supabase = None
    print("Supabase credentials not configured in environment variables. Falling back to SQLite.")

DB_FILE = "trading.db"

def get_sqlite_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database tables."""
    if supabase:
        try:
            acc = get_account(1)
            if not acc:
                print("Account #1 not found. Initializing default account in Supabase...")
                supabase.table("accounts").insert({
                    "account_id": 1,
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "risk_pct": 1.0
                }).execute()
        except Exception as e:
            print(f"Error initializing default account in init_db: {e}")
    else:
        # Initialize SQLite tables
        conn = get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY,
                balance REAL,
                equity REAL,
                risk_pct REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                size REAL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT,
                thesis TEXT,
                risk_amount REAL,
                exit_price REAL,
                pnl REAL,
                closed_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS journals (
                journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_regime TEXT,
                psychological_state TEXT,
                notes TEXT,
                lessons_learned TEXT,
                timestamp TEXT
            )
        """)
        
        # Insert default account if not exists
        cursor.execute("SELECT * FROM accounts WHERE account_id = 1")
        if not cursor.fetchone():
            print("Account #1 not found. Initializing default account in SQLite...")
            cursor.execute("INSERT INTO accounts (account_id, balance, equity, risk_pct) VALUES (1, 10000.0, 10000.0, 1.0)")
            
        conn.commit()
        conn.close()

# ACCOUNT OPERATIONS
def get_account(account_id=1):
    if supabase:
        try:
            response = supabase.table("accounts").select("*").eq("account_id", account_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error in get_account: {e}")
            return None
    else:
        conn = get_sqlite_conn()
        row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

def update_account_balance(balance, equity, account_id=1):
    if supabase:
        try:
            supabase.table("accounts").update({"balance": balance, "equity": equity}).eq("account_id", account_id).execute()
        except Exception as e:
            print(f"Error in update_account_balance: {e}")
    else:
        conn = get_sqlite_conn()
        conn.execute("UPDATE accounts SET balance = ?, equity = ? WHERE account_id = ?", (balance, equity, account_id))
        conn.commit()
        conn.close()

def update_account_risk(risk_pct, account_id=1):
    if supabase:
        try:
            supabase.table("accounts").update({"risk_pct": risk_pct}).eq("account_id", account_id).execute()
        except Exception as e:
            print(f"Error in update_account_risk: {e}")
    else:
        conn = get_sqlite_conn()
        conn.execute("UPDATE accounts SET risk_pct = ? WHERE account_id = ?", (risk_pct, account_id))
        conn.commit()
        conn.close()

def reset_account(balance=10000.0, account_id=1):
    if supabase:
        try:
            supabase.table("positions").delete().neq("position_id", -1).execute()
            supabase.table("journals").delete().neq("journal_id", -1).execute()
            supabase.table("accounts").update({
                "balance": balance,
                "equity": balance,
                "risk_pct": 1.0
            }).eq("account_id", account_id).execute()
        except Exception as e:
            print(f"Error in reset_account: {e}")
    else:
        conn = get_sqlite_conn()
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM journals")
        conn.execute("UPDATE accounts SET balance = ?, equity = ?, risk_pct = 1.0 WHERE account_id = ?", (balance, balance, account_id))
        conn.commit()
        conn.close()

# POSITION OPERATIONS
def open_position(symbol, direction, entry_price, size, stop_loss, take_profit, thesis, risk_amount):
    if supabase:
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
    else:
        conn = get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO positions (symbol, direction, entry_price, size, stop_loss, take_profit, status, thesis, risk_amount)
            VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
        """, (symbol.upper(), direction.upper(), entry_price, size, stop_loss, take_profit, thesis, risk_amount))
        pos_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return pos_id

def get_open_positions():
    if supabase:
        try:
            response = supabase.table("positions").select("*").eq("status", "OPEN").execute()
            return response.data
        except Exception as e:
            print(f"Error in get_open_positions: {e}")
            return []
    else:
        conn = get_sqlite_conn()
        rows = conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
        conn.close()
        return [dict(r) for r in rows]

def get_position(position_id):
    if supabase:
        try:
            response = supabase.table("positions").select("*").eq("position_id", position_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error in get_position: {e}")
            return None
    else:
        conn = get_sqlite_conn()
        row = conn.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

def close_position(position_id, exit_price, pnl):
    if supabase:
        try:
            now_str = datetime.now().isoformat()
            supabase.table("positions").update({
                "status": "CLOSED",
                "exit_price": exit_price,
                "pnl": pnl,
                "closed_at": now_str
            }).eq("position_id", position_id).execute()
            
            account = get_account(1)
            if account:
                new_balance = account['balance'] + pnl
                update_account_balance(new_balance, new_balance, 1)
                return new_balance
            return 10000.0
        except Exception as e:
            print(f"Error in close_position: {e}")
            return 10000.0
    else:
        conn = get_sqlite_conn()
        now_str = datetime.now().isoformat()
        conn.execute("UPDATE positions SET status = 'CLOSED', exit_price = ?, pnl = ?, closed_at = ? WHERE position_id = ?", (exit_price, pnl, now_str, position_id))
        conn.commit()
        
        row = conn.execute("SELECT balance FROM accounts WHERE account_id = 1").fetchone()
        new_balance = 10000.0
        if row:
            new_balance = row['balance'] + pnl
            conn.execute("UPDATE accounts SET balance = ?, equity = ? WHERE account_id = 1", (new_balance, new_balance))
            conn.commit()
            
        conn.close()
        return new_balance

def get_closed_positions(limit=50):
    if supabase:
        try:
            response = supabase.table("positions").select("*").eq("status", "CLOSED").order("closed_at", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            print(f"Error in get_closed_positions: {e}")
            return []
    else:
        conn = get_sqlite_conn()
        rows = conn.execute("SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

# JOURNAL OPERATIONS
def add_journal_entry(notes, market_regime=None, psychological_state=None, lessons_learned=None):
    if supabase:
        try:
            supabase.table("journals").insert({
                "market_regime": market_regime,
                "psychological_state": psychological_state,
                "notes": notes,
                "lessons_learned": lessons_learned
            }).execute()
        except Exception as e:
            print(f"Error in add_journal_entry: {e}")
    else:
        conn = get_sqlite_conn()
        conn.execute("""
            INSERT INTO journals (market_regime, psychological_state, notes, lessons_learned, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (market_regime, psychological_state, notes, lessons_learned, datetime.now().isoformat()))
        conn.commit()
        conn.close()

def get_journal_entries(limit=10):
    if supabase:
        try:
            response = supabase.table("journals").select("*").order("timestamp", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            print(f"Error in get_journal_entries: {e}")
            return []
    else:
        conn = get_sqlite_conn()
        rows = conn.execute("SELECT * FROM journals ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

# STATISTICS CALCULATION
def get_portfolio_stats():
    if supabase:
        try:
            response = supabase.table("positions").select("pnl, risk_amount").eq("status", "CLOSED").execute()
            trades = response.data
        except Exception as e:
            print(f"Error in get_portfolio_stats: {e}")
            return {
                "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_profit": 0.0, "average_win": 0.0, "average_loss": 0.0
            }
    else:
        conn = get_sqlite_conn()
        rows = conn.execute("SELECT pnl, risk_amount FROM positions WHERE status = 'CLOSED'").fetchall()
        trades = [dict(r) for r in rows]
        conn.close()
        
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
