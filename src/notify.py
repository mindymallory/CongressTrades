"""
Push notifications via NTFY.

NTFY (https://ntfy.sh) is a free, open-source push notification service.
You can self-host it or use the free public server.

Setup:
1. Install the NTFY app on your phone (iOS or Android)
2. Subscribe to your topic (e.g., "congress-trades-yourname")
3. Update NTFY_TOPIC in config.py
"""

import requests
from datetime import datetime

from . import config


def is_quiet_hours() -> bool:
    """Check if we're in quiet hours (shouldn't send notifications)."""
    current_hour = datetime.now().hour
    start_hour, end_hour = config.NOTIFY_HOURS
    return not (start_hour <= current_hour < end_hour)


def format_amount(amount_range: str) -> str:
    """Format amount range for display."""
    if not amount_range:
        return "Unknown"
    # Shorten common ranges
    return amount_range.replace(",000", "K").replace("$", "")


def send_notification(
    title: str,
    message: str,
    priority: int = 3,
    tags: list[str] = None,
    click_url: str = None
) -> bool:
    """
    Send a push notification via NTFY.

    Args:
        title: Notification title
        message: Notification body
        priority: 1 (min) to 5 (max), default 3
        tags: Emoji tags (e.g., ["chart_with_upwards_trend", "moneybag"])
        click_url: URL to open when notification is tapped

    Returns:
        True if sent successfully, False otherwise
    """
    if config.NTFY_TOPIC == "congress-trades-CHANGE-ME":
        print("WARNING: NTFY_TOPIC not configured. Edit src/config.py to enable notifications.")
        return False

    if is_quiet_hours():
        print(f"  Skipping notification (quiet hours: {config.NOTIFY_HOURS[0]}:00 - {config.NOTIFY_HOURS[1]}:00)")
        return False

    url = f"{config.NTFY_SERVER}/{config.NTFY_TOPIC}"

    headers = {
        "Title": title,
        "Priority": str(priority),
    }

    if tags:
        headers["Tags"] = ",".join(tags)

    if click_url:
        headers["Click"] = click_url

    try:
        response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  Failed to send notification: {e}")
        return False


def notify_new_trade(trade: dict) -> bool:
    """Send notification for a new trade."""
    if not config.NOTIFY_ON_NEW_TRADES:
        return False

    member = trade.get("member_name", "Unknown")
    chamber = trade.get("chamber", "").title()
    ticker = trade.get("ticker") or "N/A"
    tx_type = trade.get("transaction_type", "").replace("_", " ").title()
    amount = format_amount(trade.get("amount_range", ""))
    asset = trade.get("asset_description", "Unknown")

    # Truncate long asset descriptions
    if len(asset) > 50:
        asset = asset[:47] + "..."

    # Choose emoji based on transaction type
    if "purchase" in tx_type.lower():
        emoji = "chart_with_upwards_trend"
        action = "bought"
    elif "sale" in tx_type.lower():
        emoji = "chart_with_downwards_trend"
        action = "sold"
    else:
        emoji = "money_with_wings"
        action = tx_type.lower()

    title = f"{member} ({chamber})"

    if ticker and ticker != "N/A":
        message = f"{action.upper()} ${ticker}\nAmount: {amount}\n{asset}"
    else:
        message = f"{action.upper()}: {asset}\nAmount: {amount}"

    # Add owner info if available
    owner = trade.get("owner")
    if owner and owner.lower() != "self":
        message += f"\nOwner: {owner}"

    return send_notification(
        title=title,
        message=message,
        priority=3,
        tags=[emoji, "us"],
        click_url=trade.get("source_url")
    )


def notify_daily_digest(trades: list[dict]) -> bool:
    """Send a daily digest of new trades."""
    if not trades:
        return False

    # Count by type
    purchases = sum(1 for t in trades if "purchase" in t.get("transaction_type", "").lower())
    sales = sum(1 for t in trades if "sale" in t.get("transaction_type", "").lower())

    # Get unique members
    members = set(t.get("member_name", "Unknown") for t in trades)

    # Get top tickers
    tickers = {}
    for t in trades:
        ticker = t.get("ticker")
        if ticker and ticker != "N/A":
            tickers[ticker] = tickers.get(ticker, 0) + 1
    top_tickers = sorted(tickers.items(), key=lambda x: x[1], reverse=True)[:5]

    title = f"Congress Trades: {len(trades)} new today"

    lines = [
        f"Purchases: {purchases} | Sales: {sales}",
        f"Members trading: {len(members)}",
    ]

    if top_tickers:
        ticker_str = ", ".join(f"${t[0]}" for t in top_tickers)
        lines.append(f"Top tickers: {ticker_str}")

    message = "\n".join(lines)

    return send_notification(
        title=title,
        message=message,
        priority=3,
        tags=["newspaper", "us"]
    )


def send_test_notification() -> bool:
    """Send a test notification to verify setup."""
    return send_notification(
        title="Congress Trades Test",
        message="If you see this, notifications are working!",
        priority=3,
        tags=["white_check_mark"]
    )
