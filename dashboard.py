"""
Congress Trades Dashboard

A local Streamlit dashboard to visualize congressional trading data.
Run with: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src import db
from src import config

# Page config
st.set_page_config(
    page_title="Congress Trades Tracker",
    page_icon="🏛️",
    layout="wide"
)

# Initialize database
db.init_db()

# Title
st.title("🏛️ Congress Trades Tracker")
st.markdown("---")

# Sidebar filters
st.sidebar.header("Filters")

# Chamber filter
chamber_filter = st.sidebar.selectbox(
    "Chamber",
    ["All", "House", "Senate"]
)

# Top N members
top_n = st.sidebar.slider("Top N Members", 10, 50, 20)

# Days for recent trades
recent_days = st.sidebar.slider("Recent Trades (days)", 7, 90, 30)

# Main content - tabs
tab1, tab2, tab3 = st.tabs(["📊 Sharpe Rankings", "📈 Member Details", "🔄 Recent Trades"])

# ============== TAB 1: Sharpe Rankings ==============
with tab1:
    st.header("Sharpe Ratio Rankings")

    # Get latest Sharpe data
    rankings = db.get_latest_sharpe_all_members()

    if not rankings:
        st.warning("No Sharpe data found. Run `py main.py analyze` first.")
    else:
        df = pd.DataFrame(rankings)

        # Apply chamber filter
        if chamber_filter != "All":
            df = df[df['chamber'] == chamber_filter.lower()]

        # Filter out extreme/invalid Sharpe values
        df_valid = df[df['sharpe_30d'].notna() & (df['sharpe_30d'].abs() < 100)].copy()

        if df_valid.empty:
            st.warning("No valid Sharpe ratios to display.")
        else:
            # Top performers
            df_top = df_valid.nlargest(top_n, 'sharpe_30d')

            col1, col2 = st.columns(2)

            with col1:
                st.subheader(f"Top {top_n} by 30-Day Sharpe Ratio")

                # Bar chart
                fig = px.bar(
                    df_top,
                    x='sharpe_30d',
                    y='member_name',
                    orientation='h',
                    color='chamber',
                    color_discrete_map={'house': '#1f77b4', 'senate': '#ff7f0e'},
                    hover_data=['win_rate_30d', 'num_trades']
                )
                fig.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    height=max(400, top_n * 25),
                    showlegend=True,
                    legend_title="Chamber"
                )
                fig.update_xaxes(title="Sharpe Ratio (30-day)")
                fig.update_yaxes(title="")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Win Rate vs Sharpe Ratio")

                # Scatter plot
                df_scatter = df_valid[df_valid['win_rate_30d'].notna()].copy()
                df_scatter['win_rate_pct'] = df_scatter['win_rate_30d'] * 100

                fig2 = px.scatter(
                    df_scatter,
                    x='sharpe_30d',
                    y='win_rate_pct',
                    color='chamber',
                    size='num_trades',
                    hover_name='member_name',
                    color_discrete_map={'house': '#1f77b4', 'senate': '#ff7f0e'},
                    labels={
                        'sharpe_30d': 'Sharpe Ratio (30-day)',
                        'win_rate_pct': 'Win Rate (%)',
                        'num_trades': 'Number of Trades'
                    }
                )
                fig2.update_layout(height=500)
                st.plotly_chart(fig2, use_container_width=True)

            # Data table
            st.subheader("Full Rankings Table")

            display_df = df_valid[['member_name', 'chamber', 'sharpe_30d', 'win_rate_30d', 'num_trades']].copy()
            display_df.columns = ['Member', 'Chamber', 'Sharpe (30d)', 'Win Rate', 'Trades']
            display_df['Win Rate'] = display_df['Win Rate'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A")
            display_df['Sharpe (30d)'] = display_df['Sharpe (30d)'].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "N/A")
            display_df['Chamber'] = display_df['Chamber'].str.title()
            display_df = display_df.reset_index(drop=True)
            display_df.index = display_df.index + 1

            st.dataframe(display_df, use_container_width=True, height=400)

# ============== TAB 2: Member Details ==============
with tab2:
    st.header("Member Details")

    # Get all members for dropdown
    conn = db.get_connection()
    members_df = pd.read_sql_query("SELECT DISTINCT name FROM members ORDER BY name", conn)
    conn.close()

    if members_df.empty:
        st.warning("No members found in database.")
    else:
        selected_member = st.selectbox("Select Member", members_df['name'].tolist())

        if selected_member:
            # Get member's trades
            trades = db.get_trades_by_member(selected_member, limit=100)

            if trades:
                trades_df = pd.DataFrame(trades)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Trades", len(trades_df))
                with col2:
                    buys = len(trades_df[trades_df['transaction_type'] == 'purchase'])
                    st.metric("Purchases", buys)
                with col3:
                    sells = len(trades_df[trades_df['transaction_type'] == 'sale'])
                    st.metric("Sales", sells)

                # Get Sharpe history
                conn = db.get_connection()
                member_id_result = conn.execute(
                    "SELECT id FROM members WHERE name = ?", (selected_member,)
                ).fetchone()

                if member_id_result:
                    member_id = member_id_result['id']
                    sharpe_history = pd.read_sql_query(
                        """SELECT snapshot_date, sharpe_30d, sharpe_current, win_rate_30d, num_trades
                           FROM sharpe_snapshots WHERE member_id = ? ORDER BY snapshot_date""",
                        conn, params=(member_id,)
                    )
                    conn.close()

                    if not sharpe_history.empty and len(sharpe_history) > 1:
                        st.subheader("Sharpe Ratio History")

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=sharpe_history['snapshot_date'],
                            y=sharpe_history['sharpe_30d'],
                            mode='lines+markers',
                            name='30-Day Sharpe'
                        ))
                        fig.update_layout(
                            xaxis_title="Date",
                            yaxis_title="Sharpe Ratio",
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    conn.close()

                # Recent trades table
                st.subheader("Recent Trades")
                display_trades = trades_df[['transaction_date', 'ticker', 'transaction_type', 'amount_range']].copy()
                display_trades.columns = ['Date', 'Ticker', 'Type', 'Amount']
                display_trades['Type'] = display_trades['Type'].str.title()
                st.dataframe(display_trades, use_container_width=True, height=400)
            else:
                st.info(f"No trades found for {selected_member}")

# ============== TAB 3: Recent Trades ==============
with tab3:
    st.header(f"Recent Trades (Last {recent_days} Days)")

    # Get recent trades
    trades = db.get_recent_trades(days=recent_days, limit=500)

    if not trades:
        st.warning(f"No trades found in the last {recent_days} days.")
    else:
        trades_df = pd.DataFrame(trades)

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Trades", len(trades_df))
        with col2:
            unique_members = trades_df['member_name'].nunique()
            st.metric("Active Members", unique_members)
        with col3:
            purchases = len(trades_df[trades_df['transaction_type'] == 'purchase'])
            st.metric("Purchases", purchases)
        with col4:
            sales = len(trades_df[trades_df['transaction_type'] == 'sale'])
            st.metric("Sales", sales)

        st.markdown("---")

        # Filter options
        col1, col2 = st.columns(2)
        with col1:
            tx_type_filter = st.selectbox(
                "Transaction Type",
                ["All", "Purchase", "Sale"],
                key="tx_filter"
            )
        with col2:
            ticker_search = st.text_input("Search Ticker", key="ticker_search")

        # Apply filters
        filtered_df = trades_df.copy()
        if tx_type_filter != "All":
            filtered_df = filtered_df[filtered_df['transaction_type'] == tx_type_filter.lower()]
        if ticker_search:
            filtered_df = filtered_df[filtered_df['ticker'].str.contains(ticker_search.upper(), na=False)]

        # Most traded tickers
        if not filtered_df.empty and 'ticker' in filtered_df.columns:
            st.subheader("Most Traded Tickers")
            ticker_counts = filtered_df['ticker'].value_counts().head(15)

            fig = px.bar(
                x=ticker_counts.values,
                y=ticker_counts.index,
                orientation='h',
                labels={'x': 'Number of Trades', 'y': 'Ticker'}
            )
            fig.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

        # Trades table
        st.subheader("Trade Details")
        display_df = filtered_df[['transaction_date', 'member_name', 'chamber', 'ticker', 'transaction_type', 'amount_range']].copy()
        display_df.columns = ['Date', 'Member', 'Chamber', 'Ticker', 'Type', 'Amount']
        display_df['Chamber'] = display_df['Chamber'].str.title()
        display_df['Type'] = display_df['Type'].str.title()

        st.dataframe(display_df, use_container_width=True, height=500)

# Footer
st.markdown("---")
st.caption(f"Data from Capitol Trades | Last updated: Check `py main.py status` for sync info")
