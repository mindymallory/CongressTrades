#!/usr/bin/env python3
"""
Congress Trades Tracker

Track congressional stock trades and get push notifications when politicians trade.

Usage:
    python main.py init          # Initialize database with 5 years of data
    python main.py sync --notify # Check for new trades and send notifications
    python main.py recent        # Show recent trades
    python main.py search --ticker NVDA  # Search by ticker
    python main.py test-notify   # Test push notifications
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
