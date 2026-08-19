import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "trading_bot.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY DEFAULT 1,
        balance REAL NOT NULL,
        equity REAL NOT NULL,
        risk_pct REAL DEFAULT 1.0,
        currency TEXT DEFAULT 'USD',
        created_at TEXT NOT NULL
    )
    """)
    
    # 2. Positions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS positions (
        position_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL, -- 'LONG' or 'SHORT'
        entry_price REAL NOT NULL,
        size REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN', -- 'OPEN' or 'CLOSED'
        exit_price REAL,
        pnl REAL,
        opened_at TEXT NOT NULL,
        closed_at TEXT,
        thesis TEXT,
        risk_amount REAL NOT NULL
    )
    """)
    
    # 3. Journal Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS journals (
        journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        market_regime TEXT,
        psychological_state TEXT,
        notes TEXT NOT NULL,
        lessons_learned TEXT
    )
    """)
    
    # Check if a default account exists, if not create one with $10,000 balance
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE account_id = 1")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO accounts (account_id, balance, equity, risk_pct, currency, created_at) VALUES (1, 10000.0, 10000.0, 1.0, 'USD', ?)",
            (now_str,)
        )
    
    conn.commit()
    conn.close()

# ACCOUNT OPERATIONS
def get_account(account_id=1):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_account_balance(balance, equity, account_id=1):
    conn = get_db_connection()
    conn.execute(
        "UPDATE accounts SET balance = ?, equity = ? WHERE account_id = ?",
        (balance, equity, account_id)
    )
    conn.commit()
    conn.close()

def update_account_risk(risk_pct, account_id=1):
    conn = get_db_connection()
    conn.execute(
        "UPDATE accounts SET risk_pct = ? WHERE account_id = ?",
        (risk_pct, account_id)
    )
    conn.commit()
    conn.close()

def reset_account(balance=10000.0, account_id=1):
    conn = get_db_connection()
    now_str = datetime.now().isoformat()
    # Delete positions & journals
    conn.execute("DELETE FROM positions")
    conn.execute("DELETE FROM journals")
    # Update account
    conn.execute(
        "UPDATE accounts SET balance = ?, equity = ?, risk_pct = 1.0, created_at = ? WHERE account_id = ?",
        (balance, balance, now_str, account_id)
    )
    conn.commit()
    conn.close()

# POSITION OPERATIONS
def open_position(symbol, direction, entry_price, size, stop_loss, take_profit, thesis, risk_amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO positions 
        (symbol, direction, entry_price, size, stop_loss, take_profit, status, opened_at, thesis, risk_amount)
        VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
        """,
        (symbol.upper(), direction.upper(), entry_price, size, stop_loss, take_profit, now_str, thesis, risk_amount)
    )
    position_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return position_id

def get_open_positions():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_position(position_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def close_position(position_id, exit_price, pnl):
    conn = get_db_connection()
    now_str = datetime.now().isoformat()
    conn.execute(
        """
        UPDATE positions 
        SET status = 'CLOSED', exit_price = ?, pnl = ?, closed_at = ? 
        WHERE position_id = ?
        """,
        (exit_price, pnl, now_str, position_id)
    )
    
    # Fetch current account balance and update it
    account = conn.execute("SELECT balance, equity FROM accounts WHERE account_id = 1").fetchone()
    new_balance = account['balance'] + pnl
    # Note: Equity will equal balance when all positions are closed, but let's update it here
    conn.execute(
        "UPDATE accounts SET balance = ?, equity = ? WHERE account_id = 1",
        (new_balance, new_balance)
    )
    
    conn.commit()
    conn.close()
    return new_balance

def get_closed_positions(limit=50):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT ?", 
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# JOURNAL OPERATIONS
def add_journal_entry(notes, market_regime=None, psychological_state=None, lessons_learned=None):
    conn = get_db_connection()
    now_str = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO journals (timestamp, market_regime, psychological_state, notes, lessons_learned)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_str, market_regime, psychological_state, notes, lessons_learned)
    )
    conn.commit()
    conn.close()

def get_journal_entries(limit=10):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM journals ORDER BY timestamp DESC LIMIT ?", 
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# STATISTICS CALCULATION
def get_portfolio_stats():
    conn = get_db_connection()
    
    # Get all closed trades
    rows = conn.execute("SELECT pnl, risk_amount FROM positions WHERE status = 'CLOSED'").fetchall()
    conn.close()
    
    trades = [dict(r) for r in rows]
    total_trades = len(trades)
    
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "max_drawdown": 0.0 # Will calculate from account history or set 0 for now
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

# Initialize database tables on load
if __name__ not in ("__main__",):
    init_db()
