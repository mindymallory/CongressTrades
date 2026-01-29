"""
Scraper for Capitol Trades website.

Extracts congressional trading data from capitoltrades.com.
"""

import requests
import json
import re
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
        parsed = date_parser.parse(date_str)
        return parsed.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def normalize_transaction_type(tx_type: str) -> str:
    """Normalize transaction type to lowercase standard form."""
    tx_type = tx_type.lower().strip()
    if tx_type == "buy":
        return "purchase"
    elif tx_type == "sell":
        return "sale"
    elif "purchase" in tx_type:
        return "purchase"
    elif "sale" in tx_type:
        return "sale"
    elif "exchange" in tx_type:
        return "exchange"
    return tx_type


def value_to_amount_range(value: Optional[int]) -> str:
    """Convert numeric value to amount range string."""
    if value is None:
        return "Unknown"
    if value <= 1000:
        return "$1 - $1,000"
    elif value <= 15000:
        return "$1,001 - $15,000"
    elif value <= 50000:
        return "$15,001 - $50,000"
    elif value <= 100000:
        return "$50,001 - $100,000"
    elif value <= 250000:
        return "$100,001 - $250,000"
    elif value <= 500000:
        return "$250,001 - $500,000"
    elif value <= 1000000:
        return "$500,001 - $1,000,000"
    elif value <= 5000000:
        return "$1,000,001 - $5,000,000"
    else:
        return "$5,000,001+"


def should_include_trade(trade: dict) -> bool:
    """Check if trade passes the configured filters."""
    tx_type = trade.get("transaction_type", "").lower()
    if "purchase" in tx_type and not config.INCLUDE_PURCHASES:
        return False
    if "sale" in tx_type and not config.INCLUDE_SALES:
        return False

    owner = (trade.get("owner") or "").lower()
    if "self" in owner and not config.INCLUDE_SELF:
        return False
    if "spouse" in owner and not config.INCLUDE_SPOUSE:
        return False
    if "dependent" in owner and not config.INCLUDE_DEPENDENT:
        return False
    if "joint" in owner and not config.INCLUDE_JOINT:
        return False

    if config.WATCH_TICKERS:
        ticker = trade.get("ticker", "")
        if ticker:
            ticker_base = ticker.split(":")[0] if ":" in ticker else ticker
            if ticker_base.upper() not in [t.upper() for t in config.WATCH_TICKERS]:
                return False
        else:
            return False

    if config.WATCH_MEMBERS:
        member_name = trade.get("member_name", "")
        if not any(m.lower() in member_name.lower() for m in config.WATCH_MEMBERS):
            return False

    return True


def fetch_capitol_trades_page(page: int = 1) -> list[dict]:
    """Fetch a single page of trades from Capitol Trades."""
    url = f"{config.CAPITOL_TRADES_URL}?page={page}"

    try:
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()

        # Unescape the embedded JSON
        text = response.text.replace('\\"', '"')

        # Find the data array
        data_match = re.search(r'"data":(\[)', text)
        if not data_match:
            return []

        start = data_match.start(1)
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text[start:])

        return data
    except Exception as e:
        print(f"  Error fetching page {page}: {e}")
        return []


def process_capitol_trade(raw_trade: dict) -> Optional[dict]:
    """Process a Capitol Trades record into our standard format."""
    politician = raw_trade.get("politician", {})
    issuer = raw_trade.get("issuer", {})

    first_name = politician.get("firstName", "")
    last_name = politician.get("lastName", "")
    member_name = f"{first_name} {last_name}".strip()

    if not member_name:
        return None

    transaction_date = parse_date(raw_trade.get("txDate"))
    if not transaction_date:
        return None

    # Get ticker - format is like "AAPL:US"
    ticker = issuer.get("issuerTicker", "")
    if ticker and ":" in ticker:
        ticker = ticker.split(":")[0]  # Take just the symbol part

    chamber = raw_trade.get("chamber", "").lower()
    state = politician.get("_stateId", "").upper() if politician.get("_stateId") else None
    party = politician.get("party", "")

    # Convert value to amount range
    value = raw_trade.get("value")
    amount_range = value_to_amount_range(value)

    # Map owner field
    owner = raw_trade.get("owner", "")
    owner_map = {
        "self": "Self",
        "spouse": "Spouse",
        "joint": "Joint",
        "child": "Dependent Child",
        "dependent": "Dependent Child"
    }
    owner = owner_map.get(owner.lower(), owner.title() if owner else None)

    return {
        "member_name": member_name,
        "chamber": chamber,
        "state": state,
        "district": None,
        "party": party,
        "transaction_date": transaction_date,
        "disclosure_date": parse_date(raw_trade.get("pubDate")),
        "ticker": ticker if ticker else None,
        "asset_description": issuer.get("issuerName", "Unknown"),
        "asset_type": "Stock",
        "transaction_type": normalize_transaction_type(raw_trade.get("txType", "")),
        "amount_range": amount_range,
        "owner": owner,
        "comment": raw_trade.get("comment"),
        "source_url": f"https://www.capitoltrades.com/trades?txId={raw_trade.get('_txId', '')}",
        "cap_gains_over_200": None
    }


def fetch_all_trades(max_pages: int = 100) -> list[dict]:
    """Fetch all trades from Capitol Trades with pagination."""
    all_trades = []

    print("Fetching trades from Capitol Trades...")
    for page in range(1, max_pages + 1):
        trades = fetch_capitol_trades_page(page)

        if not trades:
            print(f"  No more trades at page {page}")
            break

        all_trades.extend(trades)
        print(f"  Page {page}: {len(trades)} trades (total: {len(all_trades)})")

        # Stop if we got fewer than expected (last page)
        if len(trades) < config.TRADES_PER_PAGE:
            break

    print(f"  Retrieved {len(all_trades)} trades total")
    return all_trades


def sync_trades(
    lookback_days: Optional[int] = None,
    notify_callback: Optional[callable] = None,
    max_pages: int = 100
) -> dict:
    """
    Sync trades from Capitol Trades.

    Args:
        lookback_days: Only process trades from the last N days.
        notify_callback: Function to call for each new trade.
        max_pages: Maximum number of pages to fetch.

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
    skipped_old = 0
    skipped_filter = 0
    duplicates = 0

    # Fetch all trades
    raw_trades = fetch_all_trades(max_pages=max_pages)

    for raw_trade in raw_trades:
        trade = process_capitol_trade(raw_trade)
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
