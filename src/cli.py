"""
Command-line interface for Congress Trades Tracker.
"""

import argparse
import sys
from datetime import datetime

from . import config
from . import db
from . import scraper
from . import notify


def cmd_sync(args):
    """Sync trades from APIs."""
    print(f"Congress Trades Sync - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Determine notification callback
    notify_callback = None
    if args.notify:
        if config.DAILY_DIGEST:
            # Collect trades, send digest at end
            notify_callback = None  # Handle separately
        else:
            notify_callback = notify.notify_new_trade

    # Run sync
    lookback = args.days if args.days else None
    result = scraper.sync_trades(
        lookback_days=lookback,
        notify_callback=notify_callback
    )

    # Send daily digest if configured
    if args.notify and config.DAILY_DIGEST and result["trades"]:
        notify.notify_daily_digest(result["trades"])

    return 0 if result["new_trades"] >= 0 else 1


def cmd_init(args):
    """Initialize database and do initial data load."""
    print("Initializing Congress Trades database...")
    print(f"Data directory: {config.DATA_DIR}")
    print(f"Database: {config.DB_PATH}")
    print()

    db.init_db()
    print("Database schema created.")
    print()

    if args.skip_data:
        print("Skipping initial data load (--skip-data flag).")
        return 0

    print(f"Loading historical data (last {config.INITIAL_LOOKBACK_DAYS // 365} years)...")
    print("This may take a minute on first run...")
    print()

    result = scraper.sync_trades(lookback_days=config.INITIAL_LOOKBACK_DAYS)

    print()
    print(f"Initialization complete!")
    print(f"Total trades loaded: {result['new_trades']}")

    counts = db.get_trade_count()
    print(f"Total members: {counts['total_members']}")

    return 0


def cmd_status(args):
    """Show database status."""
    db.init_db()
    counts = db.get_trade_count()
    last_sync = db.get_last_sync()

    print("Congress Trades Status")
    print("=" * 40)
    print(f"Database: {config.DB_PATH}")
    print()
    print(f"Total trades: {counts['total_trades']:,}")
    print(f"Total members: {counts['total_members']}")
    print(f"Trades (last 7 days): {counts['trades_last_week']}")
    print(f"Trades (today): {counts['trades_today']}")
    print()

    if last_sync:
        print(f"Last sync: {last_sync['completed_at']}")
        print(f"  Trades added: {last_sync['trades_added']}")
    else:
        print("No sync history found. Run 'congress-trades init' first.")

    return 0


def cmd_recent(args):
    """Show recent trades."""
    db.init_db()
    trades = db.get_recent_trades(days=args.days, limit=args.limit)

    if not trades:
        print(f"No trades found in the last {args.days} days.")
        return 0

    print(f"Recent trades (last {args.days} days)")
    print("=" * 80)

    for trade in trades:
        date = trade["transaction_date"]
        member = trade["member_name"][:20].ljust(20)
        chamber = trade["chamber"][0].upper()
        ticker = (trade["ticker"] or "N/A")[:6].ljust(6)
        tx_type = trade["transaction_type"][:8].ljust(8)
        amount = trade["amount_range"][:20] if trade["amount_range"] else "Unknown"

        print(f"{date} | {member} ({chamber}) | {ticker} | {tx_type} | {amount}")

    print()
    print(f"Showing {len(trades)} trades")
    return 0


def cmd_search(args):
    """Search trades by ticker or member."""
    db.init_db()

    if args.ticker:
        trades = db.get_trades_by_ticker(args.ticker, limit=args.limit)
        title = f"Trades for ${args.ticker.upper()}"
    elif args.member:
        trades = db.get_trades_by_member(args.member, limit=args.limit)
        title = f"Trades by members matching '{args.member}'"
    else:
        print("Error: Specify --ticker or --member")
        return 1

    if not trades:
        print(f"No trades found.")
        return 0

    print(title)
    print("=" * 80)

    for trade in trades:
        date = trade["transaction_date"]
        member = trade["member_name"][:20].ljust(20)
        chamber = trade["chamber"][0].upper()
        ticker = (trade["ticker"] or "N/A")[:6].ljust(6)
        tx_type = trade["transaction_type"][:8].ljust(8)
        amount = trade["amount_range"][:20] if trade["amount_range"] else "Unknown"

        print(f"{date} | {member} ({chamber}) | {ticker} | {tx_type} | {amount}")

    print()
    print(f"Showing {len(trades)} trades")
    return 0


def cmd_test_notify(args):
    """Send a test notification."""
    print("Sending test notification...")
    print(f"  Server: {config.NTFY_SERVER}")
    print(f"  Topic: {config.NTFY_TOPIC}")
    print()

    if notify.send_test_notification():
        print("Test notification sent! Check your phone.")
        return 0
    else:
        print("Failed to send notification. Check your config.")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Track congressional stock trades",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize database with historical data")
    init_parser.add_argument("--skip-data", action="store_true", help="Skip loading historical data")

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync new trades from APIs")
    sync_parser.add_argument("--days", type=int, default=7, help="Only fetch trades from last N days (default: 7)")
    sync_parser.add_argument("--notify", action="store_true", help="Send push notifications for new trades")

    # status command
    subparsers.add_parser("status", help="Show database status")

    # recent command
    recent_parser = subparsers.add_parser("recent", help="Show recent trades")
    recent_parser.add_argument("--days", type=int, default=7, help="Number of days (default: 7)")
    recent_parser.add_argument("--limit", type=int, default=50, help="Max trades to show (default: 50)")

    # search command
    search_parser = subparsers.add_parser("search", help="Search trades")
    search_parser.add_argument("--ticker", type=str, help="Search by ticker symbol")
    search_parser.add_argument("--member", type=str, help="Search by member name")
    search_parser.add_argument("--limit", type=int, default=50, help="Max trades to show (default: 50)")

    # test-notify command
    subparsers.add_parser("test-notify", help="Send a test notification")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "init": cmd_init,
        "sync": cmd_sync,
        "status": cmd_status,
        "recent": cmd_recent,
        "search": cmd_search,
        "test-notify": cmd_test_notify,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
