"""
Scraper for House and Senate Stock Watcher APIs.

These APIs provide pre-parsed congressional trading data in JSON format.
Much easier than scraping the official government sites directly.
"""

import requests
from datetime import datetime, timedelta
from typing import Optional
from dateutil import parser as date_parser

from . import config
from . import db


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """Parse various date formats into YYYY-MM-DD."""
    if not date_str or date_str == "--":
        return None
    try:
        # Handle various formats
        parsed = date_parser.parse(date_str)
        return parsed.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def normalize_transaction_type(tx_type: str) -> str:
    """Normalize transaction type to lowercase standard form."""
    tx_type = tx_type.lower().strip()
    if "purchase" in tx_type:
        return "purchase"
    elif "sale" in tx_type:
        if "partial" in tx_type:
            return "sale_partial"
        elif "full" in tx_type:
            return "sale_full"
        return "sale"
    elif "exchange" in tx_type:
        return "exchange"
    return tx_type


def should_include_trade(trade: dict) -> bool:
    """Check if trade passes the configured filters."""
    # Filter by transaction type
    tx_type = trade.get("transaction_type", "").lower()
    if "purchase" in tx_type and not config.INCLUDE_PURCHASES:
        return False
    if "sale" in tx_type and not config.INCLUDE_SALES:
        return False

    # Filter by owner
    owner = (trade.get("owner") or "").lower()
    if "self" in owner and not config.INCLUDE_SELF:
        return False
    if "spouse" in owner and not config.INCLUDE_SPOUSE:
        return False
    if "dependent" in owner and not config.INCLUDE_DEPENDENT:
        return False
    if "joint" in owner and not config.INCLUDE_JOINT:
        return False

    # Filter by watchlist (if configured)
    if config.WATCH_TICKERS:
        ticker = trade.get("ticker", "")
        if ticker and ticker != "--":
            if ticker.upper() not in [t.upper() for t in config.WATCH_TICKERS]:
                return False
        else:
            return False  # Skip trades without tickers if watchlist is set

    if config.WATCH_MEMBERS:
        member_name = trade.get("member_name", "")
        if not any(m.lower() in member_name.lower() for m in config.WATCH_MEMBERS):
            return False

    return True


def fetch_house_trades() -> list[dict]:
    """Fetch all House trades from the House Stock Watcher API."""
    print("Fetching House trades...")
    try:
        response = requests.get(config.HOUSE_API, timeout=60)
        response.raise_for_status()
        data = response.json()
        print(f"  Retrieved {len(data)} House transactions")
        return data
    except requests.RequestException as e:
        print(f"  Error fetching House data: {e}")
        return []


def fetch_senate_trades() -> list[dict]:
    """Fetch all Senate trades from the Senate Stock Watcher API."""
    print("Fetching Senate trades...")
    try:
        response = requests.get(config.SENATE_API, timeout=60)
        response.raise_for_status()
        data = response.json()
        print(f"  Retrieved {len(data)} Senate transactions")
        return data
    except requests.RequestException as e:
        print(f"  Error fetching Senate data: {e}")
        return []


def process_house_trade(trade: dict) -> Optional[dict]:
    """Process a single House trade into our standard format."""
    # House format fields:
    # representative, district, transaction_date, disclosure_date,
    # ticker, asset_description, type, amount, cap_gains_over_200_usd, ptr_link

    member_name = trade.get("representative", "").strip()
    if not member_name:
        return None

    # Parse district for state (format: "CA09" or "TX32")
    district = trade.get("district", "")
    state = district[:2] if len(district) >= 2 else None

    transaction_date = parse_date(trade.get("transaction_date"))
    if not transaction_date:
        return None

    return {
        "member_name": member_name,
        "chamber": "house",
        "state": state,
        "district": district,
        "party": None,  # Not provided in API
        "transaction_date": transaction_date,
        "disclosure_date": parse_date(trade.get("disclosure_date")),
        "ticker": trade.get("ticker") if trade.get("ticker") != "--" else None,
        "asset_description": trade.get("asset_description", "Unknown"),
        "asset_type": None,  # Not provided
        "transaction_type": normalize_transaction_type(trade.get("type", "")),
        "amount_range": trade.get("amount", ""),
        "owner": None,  # House API doesn't provide this
        "comment": None,
        "source_url": trade.get("ptr_link"),
        "cap_gains_over_200": trade.get("cap_gains_over_200_usd") == "True"
    }


def process_senate_trade(trade: dict) -> Optional[dict]:
    """Process a single Senate trade into our standard format."""
    # Senate format fields:
    # senator, owner, ticker, asset_description, asset_type,
    # type, amount, comment, transaction_date, disclosure_date, ptr_link

    member_name = trade.get("senator", "").strip()
    if not member_name:
        return None

    transaction_date = parse_date(trade.get("transaction_date"))
    if not transaction_date:
        return None

    return {
        "member_name": member_name,
        "chamber": "senate",
        "state": None,  # Not provided in API
        "district": None,
        "party": None,  # Not provided in API
        "transaction_date": transaction_date,
        "disclosure_date": parse_date(trade.get("disclosure_date")),
        "ticker": trade.get("ticker") if trade.get("ticker") != "--" else None,
        "asset_description": trade.get("asset_description", "Unknown"),
        "asset_type": trade.get("asset_type"),
        "transaction_type": normalize_transaction_type(trade.get("type", "")),
        "amount_range": trade.get("amount", ""),
        "owner": trade.get("owner"),
        "comment": trade.get("comment"),
        "source_url": trade.get("ptr_link"),
        "cap_gains_over_200": None
    }


def sync_trades(
    lookback_days: Optional[int] = None,
    notify_callback: Optional[callable] = None
) -> dict:
    """
    Sync trades from both House and Senate APIs.

    Args:
        lookback_days: Only process trades from the last N days.
                      None = process all trades (for initial load)
        notify_callback: Function to call for each new trade (for notifications)

    Returns:
        dict with sync statistics
    """
    db.init_db()
    sync_id = db.start_sync("full")

    cutoff_date = None
    if lookback_days:
        cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        print(f"Processing trades since {cutoff_date}")

    new_trades = []
    processed = 0
    skipped_old = 0
    skipped_filter = 0
    duplicates = 0

    # Fetch and process House trades
    house_trades = fetch_house_trades()
    for raw_trade in house_trades:
        trade = process_house_trade(raw_trade)
        if not trade:
            continue

        # Skip old trades if lookback is set
        if cutoff_date and trade["transaction_date"] < cutoff_date:
            skipped_old += 1
            continue

        # Apply filters
        if not should_include_trade(trade):
            skipped_filter += 1
            continue

        # Get or create member
        member_id = db.get_or_create_member(
            name=trade["member_name"],
            chamber=trade["chamber"],
            party=trade["party"],
            state=trade["state"],
            district=trade["district"]
        )

        # Insert trade
        trade_id = db.insert_trade(
            member_id=member_id,
            transaction_date=trade["transaction_date"],
            disclosure_date=trade["disclosure_date"],
            ticker=trade["ticker"],
            asset_description=trade["asset_description"],
            asset_type=trade["asset_type"],
            transaction_type=trade["transaction_type"],
            amount_range=trade["amount_range"],
            owner=trade["owner"],
            comment=trade["comment"],
            source_url=trade["source_url"],
            cap_gains_over_200=trade["cap_gains_over_200"]
        )

        if trade_id:
            trade["id"] = trade_id
            new_trades.append(trade)
            processed += 1
        else:
            duplicates += 1

    # Fetch and process Senate trades
    senate_trades = fetch_senate_trades()
    for raw_trade in senate_trades:
        trade = process_senate_trade(raw_trade)
        if not trade:
            continue

        # Skip old trades if lookback is set
        if cutoff_date and trade["transaction_date"] < cutoff_date:
            skipped_old += 1
            continue

        # Apply filters
        if not should_include_trade(trade):
            skipped_filter += 1
            continue

        # Get or create member
        member_id = db.get_or_create_member(
            name=trade["member_name"],
            chamber=trade["chamber"],
            party=trade["party"],
            state=trade["state"],
            district=trade["district"]
        )

        # Insert trade
        trade_id = db.insert_trade(
            member_id=member_id,
            transaction_date=trade["transaction_date"],
            disclosure_date=trade["disclosure_date"],
            ticker=trade["ticker"],
            asset_description=trade["asset_description"],
            asset_type=trade["asset_type"],
            transaction_type=trade["transaction_type"],
            amount_range=trade["amount_range"],
            owner=trade["owner"],
            comment=trade["comment"],
            source_url=trade["source_url"],
            cap_gains_over_200=trade["cap_gains_over_200"]
        )

        if trade_id:
            trade["id"] = trade_id
            new_trades.append(trade)
            processed += 1
        else:
            duplicates += 1

    # Send notifications for new trades
    if notify_callback and new_trades:
        for trade in new_trades:
            notify_callback(trade)

    # Complete sync
    db.complete_sync(sync_id, len(new_trades))

    result = {
        "new_trades": len(new_trades),
        "duplicates": duplicates,
        "skipped_old": skipped_old,
        "skipped_filter": skipped_filter,
        "trades": new_trades
    }

    print(f"\nSync complete:")
    print(f"  New trades added: {result['new_trades']}")
    print(f"  Duplicates skipped: {result['duplicates']}")
    if skipped_old:
        print(f"  Skipped (too old): {result['skipped_old']}")
    if skipped_filter:
        print(f"  Skipped (filtered): {result['skipped_filter']}")

    return result
