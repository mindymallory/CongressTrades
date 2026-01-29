# Congress Trades Tracker

Track congressional stock trades and get push notifications when politicians buy or sell stocks.

Data sourced from [House Stock Watcher](https://housestockwatcher.com/) and [Senate Stock Watcher](https://senatestockwatcher.com/).

## Features

- Downloads 5 years of historical congressional trades
- Daily sync checks for new trades
- Push notifications via NTFY (free, works on iOS/Android)
- Search by ticker or member name
- Filter by transaction type, amount, and watchlist
- SQLite database (no server needed)
- Windows Task Scheduler integration

## Quick Start (Windows)

### 1. Install Python

Download Python 3.10+ from [python.org](https://www.python.org/downloads/). During install, check "Add Python to PATH".

### 2. Install Dependencies

Open Command Prompt in this folder and run:

```cmd
pip install -r requirements.txt
```

### 3. Set Up Notifications (NTFY)

1. Install the **NTFY app** on your phone:
   - [iOS App Store](https://apps.apple.com/us/app/ntfy/id1625396347)
   - [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy)

2. Open the app and tap **"Subscribe to topic"**

3. Enter a unique topic name (e.g., `congress-trades-yourname-2024`)
   - Make it hard to guess so strangers can't send you notifications!

4. Edit `src/config.py` and set your topic:
   ```python
   NTFY_TOPIC = "congress-trades-yourname-2024"  # Your topic name
   ```

### 4. Initialize the Database

This downloads ~5 years of historical trades (takes about 1 minute):

```cmd
python main.py init
```

### 5. Test Notifications

```cmd
python main.py test-notify
```

You should receive a test notification on your phone.

### 6. Set Up Daily Sync (Optional)

To automatically check for new trades every morning:

1. Open PowerShell **as Administrator**
2. Navigate to the project folder
3. Run:

```powershell
.\scripts\setup_task.ps1 -Time "07:00"
```

This creates a Windows Task Scheduler task that runs at 7 AM daily.

**Note:** If your laptop is asleep at 7 AM, the task will run when it wakes up.

## Usage

### Check for New Trades
```cmd
python main.py sync --notify
```

### View Recent Trades
```cmd
python main.py recent --days 7
```

### Search by Ticker
```cmd
python main.py search --ticker NVDA
```

### Search by Member
```cmd
python main.py search --member Pelosi
```

### Check Database Status
```cmd
python main.py status
```

### Manual Sync (Double-Click)

Double-click `scripts/run_once.bat` to manually sync and check for new trades.

## Configuration

Edit `src/config.py` to customize:

### Watchlist (Only Get Notified for Specific Tickers/Members)

```python
WATCH_TICKERS = [
    "AAPL",
    "NVDA",
    "MSFT",
]

WATCH_MEMBERS = [
    "Pelosi",
    "Tuberville",
]
```

### Notification Settings

```python
NOTIFY_ON_NEW_TRADES = True    # Notify for each new trade
DAILY_DIGEST = False           # Or just one daily summary
NOTIFY_HOURS = (7, 22)         # Only notify between 7 AM and 10 PM
```

### Filter by Transaction Type

```python
INCLUDE_PURCHASES = True
INCLUDE_SALES = True
```

### Filter by Owner

```python
INCLUDE_SELF = True
INCLUDE_SPOUSE = True
INCLUDE_DEPENDENT = True
```

## Data Location

Your database is stored at:
- Windows: `C:\Users\YourName\.congress_trades\trades.db`

To change this, set the `CONGRESS_TRADES_DATA` environment variable.

## Commands Reference

| Command | Description |
|---------|-------------|
| `python main.py init` | Initialize database with 5 years of data |
| `python main.py sync --notify` | Check for new trades, send notifications |
| `python main.py sync --days 30` | Sync trades from last 30 days |
| `python main.py recent` | Show trades from last 7 days |
| `python main.py recent --days 30` | Show trades from last 30 days |
| `python main.py search --ticker AAPL` | Search by ticker symbol |
| `python main.py search --member Pelosi` | Search by member name |
| `python main.py status` | Show database statistics |
| `python main.py test-notify` | Send a test notification |

## Task Scheduler Commands

```powershell
# Set up daily sync at 7 AM
.\scripts\setup_task.ps1 -Time "07:00"

# Change sync time to 8:30 AM
.\scripts\setup_task.ps1 -Time "08:30"

# Remove scheduled task
.\scripts\setup_task.ps1 -Remove

# Run task immediately (from regular cmd)
schtasks /run /tn "CongressTradesSync"
```

## Troubleshooting

### "python is not recognized"
- Reinstall Python and check "Add Python to PATH"
- Or use the full path: `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`

### No notifications received
1. Check your NTFY_TOPIC in `src/config.py`
2. Make sure you're subscribed to the same topic in the NTFY app
3. Run `python main.py test-notify` to verify

### Task doesn't run when laptop wakes
- The task has `StartWhenAvailable` enabled, so it should run when laptop wakes
- Check Task Scheduler history for errors
- Make sure Python is in your PATH

### Database errors
- Delete `~/.congress_trades/trades.db` and run `python main.py init` again

## Data Sources

- **House**: [House Stock Watcher API](https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json)
- **Senate**: [Senate Stock Watcher API](https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json)

These are maintained by open-source projects that scrape the official government disclosure sites.

## Legal

Congressional financial disclosures are public records. This tool is for personal informational use only. Not financial advice.
