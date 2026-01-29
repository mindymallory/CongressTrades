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
