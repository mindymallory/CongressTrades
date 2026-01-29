"""
Configuration for Congress Trades Tracker.

Edit these settings to customize your experience.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env")

# =============================================================================
# FMP API (Financial Modeling Prep)
# =============================================================================
# Set via environment variable or .env file
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")

# =============================================================================
# NTFY NOTIFICATIONS
# =============================================================================
# NTFY is a free push notification service. To set up:
# 1. Install NTFY app on your phone (iOS/Android)
# 2. Subscribe to a unique topic name (make it hard to guess!)
# 3. Put that topic name here

NTFY_TOPIC = "congress-trades-mindy-yoyo"  # Your unique topic
NTFY_SERVER = "https://ntfy.sh"  # Default public server (or self-host)

# Notification settings
NOTIFY_ON_NEW_TRADES = True  # Send notification for each new trade
DAILY_DIGEST = False  # Send a single daily summary instead of individual notifications
NOTIFY_HOURS = (7, 22)  # Only send notifications between these hours (24h format)

# =============================================================================
# WATCHLIST (Optional)
# =============================================================================
# Get notified only for specific tickers or members
# Leave empty [] to get ALL trades

WATCH_TICKERS = [
    # "AAPL",
    # "NVDA",
    # "MSFT",
]

WATCH_MEMBERS = [
    # "Pelosi",
    # "Tuberville",
]

# =============================================================================
# DATA SETTINGS
# =============================================================================
# Database stored in project folder for easy backup
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "trades.db"

# Data source: Capitol Trades (scraped)
CAPITOL_TRADES_URL = "https://www.capitoltrades.com/trades"
TRADES_PER_PAGE = 12

# How far back to fetch on initial load (days)
INITIAL_LOOKBACK_DAYS = 365 * 5  # 5 years

# =============================================================================
# FILTERING
# =============================================================================
# Minimum trade amount to notify (by range)
# Options: "$1,001 - $15,000", "$15,001 - $50,000", "$50,001 - $100,000",
#          "$100,001 - $250,000", "$250,001 - $500,000", "$500,001 - $1,000,000",
#          "$1,000,001 - $5,000,000", "$5,000,001 - $25,000,000", etc.
MIN_AMOUNT_RANGE = None  # None = all trades, or set like "$50,001 - $100,000"

# Filter by transaction type
INCLUDE_PURCHASES = True
INCLUDE_SALES = True

# Filter by owner
INCLUDE_SELF = True
INCLUDE_SPOUSE = True
INCLUDE_DEPENDENT = True
INCLUDE_JOINT = True
