"""
Sharpe Ratio Analysis for Congressional Trading

Calculates and stores risk-adjusted returns for each Congress member.
All data is stored in the database for historical tracking.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import yfinance as yf

from . import config
from . import db

# Risk-free rate (annual) - approximate current Treasury rate
RISK_FREE_RATE_ANNUAL = 0.045  # 4.5%
RISK_FREE_RATE_DAILY = RISK_FREE_RATE_ANNUAL / 252


def get_trades_for_analysis() -> pd.DataFrame:
    """Get all trades with tickers from the database."""
    conn = db.get_connection()
    query = """
        SELECT
            t.id as trade_id,
            m.id as member_id,
            m.name as member_name,
            m.chamber,
            m.party,
            t.ticker,
            t.transaction_date,
            t.transaction_type,
            t.amount_range
        FROM trades t
        JOIN members m ON t.member_id = m.id
        WHERE t.ticker IS NOT NULL
          AND t.ticker != ''
          AND t.transaction_type IN ('purchase', 'sale')
        ORDER BY t.transaction_date
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['transaction_date'] = pd.to_datetime(df['transaction_date'])
    return df


def get_cached_price_df(ticker: str) -> pd.DataFrame:
    """Get cached prices as a DataFrame."""
    conn = db.get_connection()
    df = pd.read_sql_query(
        "SELECT price_date, close_price FROM price_cache WHERE ticker = ? ORDER BY price_date",
        conn, params=(ticker,)
    )
    conn.close()
    if not df.empty:
        df['price_date'] = pd.to_datetime(df['price_date'])
        df.set_index('price_date', inplace=True)
    return df


def fetch_and_cache_prices(tickers: list[str], start_date: datetime) -> dict:
    """Fetch prices from Yahoo Finance and cache them. Returns {ticker: price_series}."""
    print(f"Fetching prices for {len(tickers)} tickers...")

    all_prices = {}
    batch_size = 50
    today = datetime.now()

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}: {len(batch)} tickers...")

        try:
            data = yf.download(
                batch,
                start=start_date,
                end=today,
                progress=False,
                auto_adjust=True
            )

            if len(batch) == 1:
                if not data.empty:
                    ticker = batch[0]
                    prices = data['Close'].dropna()
                    all_prices[ticker] = prices
                    # Cache prices
                    price_dict = {d.strftime('%Y-%m-%d'): float(p) for d, p in prices.items()}
                    db.cache_prices(ticker, price_dict)
            else:
                if 'Close' in data.columns.get_level_values(0):
                    for ticker in batch:
                        if ticker in data['Close'].columns:
                            prices = data['Close'][ticker].dropna()
                            if not prices.empty:
                                all_prices[ticker] = prices
                                # Cache prices
                                price_dict = {d.strftime('%Y-%m-%d'): float(p) for d, p in prices.items()}
                                db.cache_prices(ticker, price_dict)

        except Exception as e:
            print(f"    Error: {e}")

    print(f"  Cached prices for {len(all_prices)} tickers")
    return all_prices


def get_prices_for_tickers(tickers: list[str], start_date: datetime) -> dict:
    """Get prices from cache or fetch from Yahoo Finance."""
    prices = {}
    tickers_to_fetch = []

    # Check cache first
    for ticker in tickers:
        cached = get_cached_price_df(ticker)
        if not cached.empty and len(cached) > 10:
            prices[ticker] = cached['close_price']
        else:
            tickers_to_fetch.append(ticker)

    print(f"  {len(prices)} tickers from cache, {len(tickers_to_fetch)} to fetch")

    # Fetch missing tickers
    if tickers_to_fetch:
        fetched = fetch_and_cache_prices(tickers_to_fetch, start_date)
        prices.update(fetched)

    return prices


def calculate_and_store_returns(trades_df: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """Calculate returns for each trade and store in database."""
    results = []
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    for _, trade in trades_df.iterrows():
        ticker = trade['ticker']
        trade_date = trade['transaction_date']
        tx_type = trade['transaction_type']
        trade_id = int(trade['trade_id'])  # Convert numpy int64 to Python int

        if ticker not in prices or prices[ticker].empty:
            continue

        price_series = prices[ticker]

        try:
            # Find entry price (nearest date on or after trade date)
            available_dates = price_series.index
            valid_dates = available_dates[available_dates >= trade_date]

            if len(valid_dates) == 0:
                continue

            entry_date = valid_dates[0]
            entry_price = float(price_series[entry_date])
            entry_date_str = entry_date.strftime('%Y-%m-%d')

            # 30-day return
            target_date_30 = entry_date + timedelta(days=30)
            valid_30 = available_dates[available_dates >= target_date_30]

            return_30d = None
            return_30d_date = None
            if len(valid_30) > 0:
                exit_date_30 = valid_30[0]
                exit_price_30 = float(price_series[exit_date_30])
                return_30d = (exit_price_30 - entry_price) / entry_price
                return_30d_date = exit_date_30.strftime('%Y-%m-%d')

            # Current return
            if len(price_series) > 0:
                current_price = float(price_series.iloc[-1])
                return_current = (current_price - entry_price) / entry_price
            else:
                return_current = None

            # Flip sign for sales
            if tx_type == 'sale':
                if return_30d is not None:
                    return_30d = -return_30d
                if return_current is not None:
                    return_current = -return_current

            # Store in database
            db.upsert_trade_return(
                trade_id=trade_id,
                entry_date=entry_date_str,
                entry_price=entry_price,
                return_30d=return_30d,
                return_30d_date=return_30d_date,
                return_current=return_current,
                return_current_date=today_str
            )

            results.append({
                'trade_id': trade_id,
                'member_id': trade['member_id'],
                'member_name': trade['member_name'],
                'chamber': trade['chamber'],
                'party': trade['party'],
                'ticker': ticker,
                'transaction_type': tx_type,
                'return_30d': return_30d,
                'return_current': return_current,
            })

        except Exception:
            continue

    return pd.DataFrame(results)


def calculate_and_store_sharpe(returns_df: pd.DataFrame, snapshot_date: str) -> tuple:
    """Calculate Sharpe ratios and store snapshots. Returns (sharpe_30d_df, sharpe_current_df)."""

    rf_30d = RISK_FREE_RATE_DAILY * 30
    rf_annual = RISK_FREE_RATE_ANNUAL

    results_30d = []
    results_current = []

    for member_id in returns_df['member_id'].unique():
        member_id = int(member_id)  # Convert numpy int64 to Python int
        member_data = returns_df[returns_df['member_id'] == member_id]
        member_name = member_data['member_name'].iloc[0]
        chamber = member_data['chamber'].iloc[0]
        party = member_data['party'].iloc[0]

        # 30-day Sharpe
        valid_30d = member_data['return_30d'].dropna()
        sharpe_30d = None
        mean_30d = None
        std_30d = None
        win_rate_30d = None
        total_return_30d = None

        if len(valid_30d) >= 2:
            mean_30d = float(valid_30d.mean())
            std_30d = float(valid_30d.std())
            if std_30d > 0:
                sharpe_30d = (mean_30d - rf_30d) / std_30d
            win_rate_30d = float((valid_30d > 0).mean())
            total_return_30d = float((1 + valid_30d).prod() - 1)

        # Current Sharpe
        valid_current = member_data['return_current'].dropna()
        sharpe_current = None
        mean_current = None
        std_current = None
        win_rate_current = None
        total_return_current = None

        if len(valid_current) >= 2:
            mean_current = float(valid_current.mean())
            std_current = float(valid_current.std())
            if std_current > 0:
                sharpe_current = (mean_current - rf_annual) / std_current
            win_rate_current = float((valid_current > 0).mean())
            total_return_current = float((1 + valid_current).prod() - 1)

        num_trades = len(member_data)

        # Store snapshot
        db.save_sharpe_snapshot(
            member_id=member_id,
            snapshot_date=snapshot_date,
            sharpe_30d=sharpe_30d,
            sharpe_current=sharpe_current,
            num_trades=num_trades,
            mean_return_30d=mean_30d,
            std_return_30d=std_30d,
            mean_return_current=mean_current,
            std_return_current=std_current,
            win_rate_30d=win_rate_30d,
            win_rate_current=win_rate_current,
            total_return_30d=total_return_30d,
            total_return_current=total_return_current
        )

        results_30d.append({
            'member_id': member_id,
            'member_name': member_name,
            'chamber': chamber,
            'party': party,
            'num_trades': num_trades,
            'sharpe_ratio': sharpe_30d,
            'mean_return': mean_30d,
            'std_return': std_30d,
            'win_rate': win_rate_30d,
            'total_return': total_return_30d,
        })

        results_current.append({
            'member_id': member_id,
            'member_name': member_name,
            'chamber': chamber,
            'party': party,
            'num_trades': num_trades,
            'sharpe_ratio': sharpe_current,
            'mean_return': mean_current,
            'std_return': std_current,
            'win_rate': win_rate_current,
            'total_return': total_return_current,
        })

    df_30d = pd.DataFrame(results_30d)
    df_current = pd.DataFrame(results_current)

    # Sort by Sharpe ratio
    if not df_30d.empty:
        df_30d = df_30d.sort_values('sharpe_ratio', ascending=False, na_position='last')
    if not df_current.empty:
        df_current = df_current.sort_values('sharpe_ratio', ascending=False, na_position='last')

    return df_30d, df_current


def run_analysis(verbose: bool = True) -> dict:
    """Run full Sharpe ratio analysis and store results in database."""

    if verbose:
        print("=" * 60)
        print("Congressional Trading Sharpe Ratio Analysis")
        print("=" * 60)
        print()

    # Get trades
    if verbose:
        print("Loading trades from database...")
    trades = get_trades_for_analysis()
    if verbose:
        print(f"  Found {len(trades)} trades with tickers")

    if trades.empty:
        print("No trades to analyze.")
        return {"error": "No trades"}

    # Get unique tickers
    tickers = trades['ticker'].unique().tolist()
    if verbose:
        print(f"  Unique tickers: {len(tickers)}")

    # Get date range
    min_date = trades['transaction_date'].min() - timedelta(days=5)
    if verbose:
        print(f"  Date range: {min_date.strftime('%Y-%m-%d')} to present")
        print()

    # Get prices (from cache or fetch)
    if verbose:
        print("Getting stock prices...")
    prices = get_prices_for_tickers(tickers, min_date)
    if verbose:
        print()

    # Calculate and store returns
    if verbose:
        print("Calculating and storing returns...")
    returns_df = calculate_and_store_returns(trades, prices)
    if verbose:
        print(f"  Calculated returns for {len(returns_df)} trades")
        print()

    # Calculate and store Sharpe ratios
    snapshot_date = datetime.now().strftime('%Y-%m-%d')
    if verbose:
        print(f"Calculating Sharpe ratios (snapshot: {snapshot_date})...")
    sharpe_30d, sharpe_current = calculate_and_store_sharpe(returns_df, snapshot_date)
    if verbose:
        print(f"  Stored snapshots for {len(sharpe_30d)} members")
        print()

    # Display results
    if verbose:
        print("=" * 60)
        print("TOP 10 MEMBERS BY 30-DAY SHARPE RATIO")
        print("=" * 60)
        print(f"{'Member':<25} {'Chamber':<8} {'Party':<12} {'Trades':>7} {'Sharpe':>8} {'Win%':>6}")
        print("-" * 60)
        for _, row in sharpe_30d.head(10).iterrows():
            sharpe = row['sharpe_ratio']
            sharpe_str = f"{sharpe:>8.2f}" if sharpe is not None and abs(sharpe) < 1000 else "    N/A"
            win = row['win_rate']
            win_str = f"{win*100:>5.1f}%" if win is not None else "   N/A"
            print(f"{row['member_name'][:24]:<25} {row['chamber']:<8} {str(row['party'])[:11]:<12} "
                  f"{row['num_trades']:>7} {sharpe_str} {win_str}")

        print()
        print("=" * 60)
        print("TOP 10 MEMBERS BY CURRENT SHARPE RATIO")
        print("=" * 60)
        print(f"{'Member':<25} {'Chamber':<8} {'Party':<12} {'Trades':>7} {'Sharpe':>8} {'Win%':>6}")
        print("-" * 60)
        for _, row in sharpe_current.head(10).iterrows():
            sharpe = row['sharpe_ratio']
            sharpe_str = f"{sharpe:>8.2f}" if sharpe is not None and abs(sharpe) < 1000 else "    N/A"
            win = row['win_rate']
            win_str = f"{win*100:>5.1f}%" if win is not None else "   N/A"
            print(f"{row['member_name'][:24]:<25} {row['chamber']:<8} {str(row['party'])[:11]:<12} "
                  f"{row['num_trades']:>7} {sharpe_str} {win_str}")

        print()
        print(f"Results stored in database with snapshot date: {snapshot_date}")

    return {
        "trades_analyzed": len(returns_df),
        "members_analyzed": len(sharpe_30d),
        "snapshot_date": snapshot_date,
        "sharpe_30d": sharpe_30d,
        "sharpe_current": sharpe_current,
    }


def get_member_sharpe_history(member_name: str) -> pd.DataFrame:
    """Get Sharpe ratio history for a member."""
    member_id = db.get_member_id_by_name(member_name)
    if not member_id:
        # Try partial match
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM members WHERE name LIKE ?", (f"%{member_name}%",))
        row = cursor.fetchone()
        conn.close()
        if row:
            member_id = row["id"]
        else:
            return pd.DataFrame()

    history = db.get_sharpe_history(member_id)
    return pd.DataFrame(history)
