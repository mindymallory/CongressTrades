"""
Database operations for Congress Trades Tracker.

Uses SQLite for local storage - no external database needed.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the database if needed."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            chamber TEXT NOT NULL,  -- 'house' or 'senate'
            party TEXT,
            state TEXT,
            district TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, chamber)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER REFERENCES members(id),
            transaction_date DATE NOT NULL,
            disclosure_date DATE,
            ticker TEXT,
            asset_description TEXT NOT NULL,
            asset_type TEXT,
            transaction_type TEXT NOT NULL,  -- 'purchase' or 'sale' or 'exchange'
            amount_range TEXT NOT NULL,
            owner TEXT,  -- 'Self', 'Spouse', 'Dependent Child', 'Joint'
            comment TEXT,
            source_url TEXT,
            cap_gains_over_200 BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(member_id, transaction_date, ticker, asset_description, transaction_type, amount_range, owner)
        );

        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,  -- 'house' or 'senate' or 'full'
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            trades_added INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'  -- 'running', 'completed', 'failed'
        );

        CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
        CREATE INDEX IF NOT EXISTS idx_trades_transaction_date ON trades(transaction_date);
        CREATE INDEX IF NOT EXISTS idx_trades_disclosure_date ON trades(disclosure_date);
        CREATE INDEX IF NOT EXISTS idx_trades_member ON trades(member_id);
        CREATE INDEX IF NOT EXISTS idx_members_name ON members(name);

        -- Price cache for stock prices
        CREATE TABLE IF NOT EXISTS price_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            price_date DATE NOT NULL,
            close_price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, price_date)
        );

        -- Calculated returns for each trade
        CREATE TABLE IF NOT EXISTS trade_returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER REFERENCES trades(id),
            entry_date DATE NOT NULL,
            entry_price REAL NOT NULL,
            return_30d REAL,  -- 30-day forward return
            return_30d_date DATE,  -- Date of 30-day price
            return_current REAL,  -- Current return (updated each run)
            return_current_date DATE,  -- Date of current price
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_id)
        );

        -- Historical Sharpe ratio snapshots
        CREATE TABLE IF NOT EXISTS sharpe_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER REFERENCES members(id),
            snapshot_date DATE NOT NULL,
            sharpe_30d REAL,
            sharpe_current REAL,
            num_trades INTEGER NOT NULL,
            mean_return_30d REAL,
            std_return_30d REAL,
            mean_return_current REAL,
            std_return_current REAL,
            win_rate_30d REAL,
            win_rate_current REAL,
            total_return_30d REAL,
            total_return_current REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(member_id, snapshot_date)
        );

        CREATE INDEX IF NOT EXISTS idx_price_cache_ticker ON price_cache(ticker);
        CREATE INDEX IF NOT EXISTS idx_price_cache_date ON price_cache(price_date);
        CREATE INDEX IF NOT EXISTS idx_trade_returns_trade ON trade_returns(trade_id);
        CREATE INDEX IF NOT EXISTS idx_sharpe_snapshots_member ON sharpe_snapshots(member_id);
        CREATE INDEX IF NOT EXISTS idx_sharpe_snapshots_date ON sharpe_snapshots(snapshot_date);
    """)

    conn.commit()
    conn.close()


def get_or_create_member(
    name: str,
    chamber: str,
    party: Optional[str] = None,
    state: Optional[str] = None,
    district: Optional[str] = None
) -> int:
    """Get existing member ID or create new member, return ID."""
    conn = get_connection()
    cursor = conn.cursor()

    # Try to find existing member
    cursor.execute(
        "SELECT id FROM members WHERE name = ? AND chamber = ?",
        (name, chamber)
    )
    row = cursor.fetchone()

    if row:
        member_id = row["id"]
        # Update party/state/district if provided and different
        if party or state or district:
            cursor.execute("""
                UPDATE members
                SET party = COALESCE(?, party),
                    state = COALESCE(?, state),
                    district = COALESCE(?, district)
                WHERE id = ?
            """, (party, state, district, member_id))
            conn.commit()
    else:
        cursor.execute("""
            INSERT INTO members (name, chamber, party, state, district)
            VALUES (?, ?, ?, ?, ?)
        """, (name, chamber, party, state, district))
        conn.commit()
        member_id = cursor.lastrowid

    conn.close()
    return member_id


def insert_trade(
    member_id: int,
    transaction_date: str,
    disclosure_date: Optional[str],
    ticker: Optional[str],
    asset_description: str,
    asset_type: Optional[str],
    transaction_type: str,
    amount_range: str,
    owner: Optional[str] = None,
    comment: Optional[str] = None,
    source_url: Optional[str] = None,
    cap_gains_over_200: Optional[bool] = None
) -> Optional[int]:
    """
    Insert a trade if it doesn't already exist.
    Returns the trade ID if inserted, None if duplicate.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO trades (
                member_id, transaction_date, disclosure_date, ticker,
                asset_description, asset_type, transaction_type, amount_range,
                owner, comment, source_url, cap_gains_over_200
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            member_id, transaction_date, disclosure_date, ticker,
            asset_description, asset_type, transaction_type, amount_range,
            owner, comment, source_url, cap_gains_over_200
        ))
        conn.commit()
        trade_id = cursor.lastrowid
        conn.close()
        return trade_id
    except sqlite3.IntegrityError:
        # Duplicate trade
        conn.close()
        return None


def get_recent_trades(days: int = 7, limit: int = 100) -> list[dict]:
    """Get trades from the last N days."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.*,
            m.name as member_name,
            m.chamber,
            m.party,
            m.state
        FROM trades t
        JOIN members m ON t.member_id = m.id
        WHERE t.disclosure_date >= date('now', ?)
        ORDER BY t.disclosure_date DESC, t.transaction_date DESC
        LIMIT ?
    """, (f"-{days} days", limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_trades_by_ticker(ticker: str, limit: int = 100) -> list[dict]:
    """Get all trades for a specific ticker."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.*,
            m.name as member_name,
            m.chamber,
            m.party,
            m.state
        FROM trades t
        JOIN members m ON t.member_id = m.id
        WHERE UPPER(t.ticker) = UPPER(?)
        ORDER BY t.transaction_date DESC
        LIMIT ?
    """, (ticker, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_trades_by_member(name: str, limit: int = 100) -> list[dict]:
    """Get all trades for a specific member (partial match)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.*,
            m.name as member_name,
            m.chamber,
            m.party,
            m.state
        FROM trades t
        JOIN members m ON t.member_id = m.id
        WHERE m.name LIKE ?
        ORDER BY t.transaction_date DESC
        LIMIT ?
    """, (f"%{name}%", limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_trade_count() -> dict:
    """Get counts of trades in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM trades")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM members")
    members = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM trades
        WHERE disclosure_date >= date('now', '-7 days')
    """)
    last_week = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) as total FROM trades
        WHERE disclosure_date >= date('now', '-1 days')
    """)
    today = cursor.fetchone()["total"]

    conn.close()
    return {
        "total_trades": total,
        "total_members": members,
        "trades_last_week": last_week,
        "trades_today": today
    }


def start_sync(sync_type: str) -> int:
    """Start a sync operation, return sync_log ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sync_log (sync_type) VALUES (?)",
        (sync_type,)
    )
    conn.commit()
    sync_id = cursor.lastrowid
    conn.close()
    return sync_id


def complete_sync(sync_id: int, trades_added: int, status: str = "completed") -> None:
    """Mark a sync operation as complete."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sync_log
        SET completed_at = CURRENT_TIMESTAMP, trades_added = ?, status = ?
        WHERE id = ?
    """, (trades_added, status, sync_id))
    conn.commit()
    conn.close()


def get_last_sync() -> Optional[dict]:
    """Get info about the last successful sync."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sync_log
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# Price Cache Functions
# =============================================================================

def get_cached_prices(ticker: str, start_date: str, end_date: str) -> dict:
    """Get cached prices for a ticker within date range. Returns {date: price}."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price_date, close_price FROM price_cache
        WHERE ticker = ? AND price_date BETWEEN ? AND ?
        ORDER BY price_date
    """, (ticker, start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return {row["price_date"]: row["close_price"] for row in rows}


def cache_prices(ticker: str, prices: dict) -> int:
    """Store prices in cache. prices = {date_str: price}. Returns count added."""
    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    for date_str, price in prices.items():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO price_cache (ticker, price_date, close_price)
                VALUES (?, ?, ?)
            """, (ticker, date_str, price))
            added += 1
        except sqlite3.Error:
            pass
    conn.commit()
    conn.close()
    return added


def get_all_cached_tickers() -> list[str]:
    """Get list of tickers that have cached prices."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ticker FROM price_cache")
    rows = cursor.fetchall()
    conn.close()
    return [row["ticker"] for row in rows]


# =============================================================================
# Trade Returns Functions
# =============================================================================

def get_trade_return(trade_id: int) -> Optional[dict]:
    """Get calculated returns for a trade."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trade_returns WHERE trade_id = ?", (trade_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_trade_return(
    trade_id: int,
    entry_date: str,
    entry_price: float,
    return_30d: Optional[float] = None,
    return_30d_date: Optional[str] = None,
    return_current: Optional[float] = None,
    return_current_date: Optional[str] = None
) -> int:
    """Insert or update trade return. Returns the row id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trade_returns
            (trade_id, entry_date, entry_price, return_30d, return_30d_date,
             return_current, return_current_date, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(trade_id) DO UPDATE SET
            return_30d = COALESCE(excluded.return_30d, trade_returns.return_30d),
            return_30d_date = COALESCE(excluded.return_30d_date, trade_returns.return_30d_date),
            return_current = excluded.return_current,
            return_current_date = excluded.return_current_date,
            updated_at = CURRENT_TIMESTAMP
    """, (trade_id, entry_date, entry_price, return_30d, return_30d_date,
          return_current, return_current_date))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_all_trade_returns() -> list[dict]:
    """Get all trade returns with member info."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            tr.*,
            t.ticker,
            t.transaction_date,
            t.transaction_type,
            t.amount_range,
            m.id as member_id,
            m.name as member_name,
            m.chamber,
            m.party
        FROM trade_returns tr
        JOIN trades t ON tr.trade_id = t.id
        JOIN members m ON t.member_id = m.id
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_trades_needing_returns() -> list[dict]:
    """Get trades that don't have returns calculated yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            t.id,
            t.ticker,
            t.transaction_date,
            t.transaction_type,
            m.id as member_id,
            m.name as member_name
        FROM trades t
        JOIN members m ON t.member_id = m.id
        LEFT JOIN trade_returns tr ON t.id = tr.trade_id
        WHERE t.ticker IS NOT NULL
          AND t.ticker != ''
          AND t.transaction_type IN ('purchase', 'sale')
          AND tr.id IS NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# Sharpe Snapshot Functions
# =============================================================================

def save_sharpe_snapshot(
    member_id: int,
    snapshot_date: str,
    sharpe_30d: Optional[float],
    sharpe_current: Optional[float],
    num_trades: int,
    mean_return_30d: Optional[float] = None,
    std_return_30d: Optional[float] = None,
    mean_return_current: Optional[float] = None,
    std_return_current: Optional[float] = None,
    win_rate_30d: Optional[float] = None,
    win_rate_current: Optional[float] = None,
    total_return_30d: Optional[float] = None,
    total_return_current: Optional[float] = None
) -> int:
    """Save a Sharpe ratio snapshot. Returns row id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sharpe_snapshots
            (member_id, snapshot_date, sharpe_30d, sharpe_current, num_trades,
             mean_return_30d, std_return_30d, mean_return_current, std_return_current,
             win_rate_30d, win_rate_current, total_return_30d, total_return_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(member_id, snapshot_date) DO UPDATE SET
            sharpe_30d = excluded.sharpe_30d,
            sharpe_current = excluded.sharpe_current,
            num_trades = excluded.num_trades,
            mean_return_30d = excluded.mean_return_30d,
            std_return_30d = excluded.std_return_30d,
            mean_return_current = excluded.mean_return_current,
            std_return_current = excluded.std_return_current,
            win_rate_30d = excluded.win_rate_30d,
            win_rate_current = excluded.win_rate_current,
            total_return_30d = excluded.total_return_30d,
            total_return_current = excluded.total_return_current
    """, (member_id, snapshot_date, sharpe_30d, sharpe_current, num_trades,
          mean_return_30d, std_return_30d, mean_return_current, std_return_current,
          win_rate_30d, win_rate_current, total_return_30d, total_return_current))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_sharpe_history(member_id: int, limit: int = 100) -> list[dict]:
    """Get Sharpe ratio history for a member."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sharpe_snapshots
        WHERE member_id = ?
        ORDER BY snapshot_date DESC
        LIMIT ?
    """, (member_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_latest_sharpe_all_members() -> list[dict]:
    """Get the latest Sharpe snapshot for all members."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            ss.*,
            m.name as member_name,
            m.chamber,
            m.party
        FROM sharpe_snapshots ss
        JOIN members m ON ss.member_id = m.id
        WHERE ss.snapshot_date = (
            SELECT MAX(snapshot_date) FROM sharpe_snapshots
        )
        ORDER BY ss.sharpe_30d DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_member_id_by_name(name: str) -> Optional[int]:
    """Get member ID by exact name match."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM members WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row["id"] if row else None
