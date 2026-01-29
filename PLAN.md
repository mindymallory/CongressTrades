# Congressional Trades Tracker - Project Plan

## Executive Summary

This document outlines options for building an app that tracks congressional stock trades from the last 5 years. I've researched the official data sources, competitor architectures, and technical options to present you with clear choices.

---

## Data Sources

### Official Government Sources
- **House**: https://disclosures-clerk.house.gov/FinancialDisclosure (XML available, easier to parse)
- **Senate**: https://efdsearch.senate.gov/search/home/ (PDFs, harder to parse)

### Free APIs (Already Scraped Data)
| Source | Format | Update Frequency |
|--------|--------|------------------|
| [House Stock Watcher](https://housestockwatcher.com/api) | JSON/CSV | Daily |
| [Senate Stock Watcher](https://senatestockwatcher.com/api) | JSON | As filed |
| [Finnhub](https://finnhub.io/docs/api/congressional-trading) | JSON | Free tier available |

**Recommendation**: Use House/Senate Stock Watcher APIs as primary source (free, already parsed). Fall back to official sources only if needed.

### Data Structure
Trades include:
- Member name, party, state, chamber
- Transaction date + disclosure date (gap = reporting delay, max 45 days)
- Ticker, asset description, transaction type (buy/sell)
- Amount range ($1K-$15K, $15K-$50K, etc. - not exact amounts)
- Owner (self/spouse/dependent child)

---

## Architecture Options

### Option A: Full Mobile App with Backend (Cloud-Hosted)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Mobile App     │◄────│  Push Service    │◄────│  Scraper        │
│  (React Native) │     │  (FCM/Expo)      │     │  (AWS Lambda)   │
└────────┬────────┘     └──────────────────┘     └────────┬────────┘
         │                                                │
         └──────────────────┬─────────────────────────────┘
                            ▼
                  ┌─────────────────────┐
                  │  Database           │
                  │  (Supabase)         │
                  └─────────────────────┘
```

**Components**:
- React Native + Expo mobile app (iOS + Android from single codebase)
- AWS Lambda scraper running daily via EventBridge cron
- Supabase for database + real-time subscriptions
- Expo Push / FCM for notifications

**Monthly Cost**: $0 (all free tiers)

**Pros**:
- Real mobile app you can install from app stores
- Push notifications work even when app is closed
- Scales to multiple users if you want to share it
- Professional architecture similar to competitors

**Cons**:
- Requires Apple Developer ($99/year) + Google Play ($25 one-time) to publish
- More complex setup and maintenance
- Must manage cloud services

---

### Option B: Local Desktop App + Mobile Companion

```
┌─────────────────┐     ┌──────────────────┐
│  Local Server   │────►│  Push Service    │
│  (Python/Node)  │     │  (Pushover/NTFY) │
│  + SQLite DB    │     └────────┬─────────┘
│  + Cron Job     │              │
└─────────────────┘              ▼
                        ┌─────────────────┐
                        │  Phone          │
                        │  (Notifications)│
                        └─────────────────┘
```

**Components**:
- Python or Node.js scraper running on your machine
- SQLite database stored locally
- Cron job for daily execution
- Pushover ($5 one-time) or NTFY (free) for push notifications to your phone
- Simple web UI (optional) for viewing data

**Monthly Cost**: $0 (or $5 one-time for Pushover)

**Pros**:
- Simplest to set up and maintain
- No cloud dependencies
- Complete control over your data
- No app store fees
- Can run on Raspberry Pi for always-on operation

**Cons**:
- Requires your computer to be on (or a Raspberry Pi)
- No "real" mobile app - just notifications
- Harder to share with others

---

### Option C: Hybrid - Local Scraper + Hosted Notifications

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Local Scraper  │────►│  Supabase        │◄────│  Mobile App     │
│  (Python/cron)  │     │  (Database +     │     │  (React Native) │
│                 │     │   Real-time)     │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Components**:
- Local Python scraper with cron (runs on your machine)
- Supabase for database + real-time triggers for notifications
- Simple React Native app that subscribes to Supabase real-time

**Monthly Cost**: $0

**Pros**:
- Scraper runs locally (no cloud compute needed)
- Real mobile app with push notifications
- Database accessible from anywhere
- Easier to debug scraper issues

**Cons**:
- Still need app store fees to publish
- Depends on your machine being on to scrape

---

### Option D: CLI + Email/SMS Alerts (Simplest)

```
┌─────────────────┐     ┌──────────────────┐
│  Python Script  │────►│  Email/SMS       │
│  + SQLite       │     │  (Gmail/Twilio)  │
│  + Cron         │     └──────────────────┘
└─────────────────┘
```

**Components**:
- Python script run via cron
- SQLite database
- Email via Gmail SMTP (free) or SMS via Twilio (~$0.01/msg)

**Monthly Cost**: $0 (email) or ~$0.30/month (SMS, 30 msgs)

**Pros**:
- Absolute simplest to build and maintain
- No app development required
- Works on any computer
- Email is free and reliable

**Cons**:
- No mobile app
- Email notifications less immediate than push
- Basic functionality only

---

## Cost Comparison Summary

| Option | Setup Effort | Monthly Cost | One-Time Cost | Best For |
|--------|--------------|--------------|---------------|----------|
| **A: Full Mobile** | High | $0 | $124 (app stores) | Polished experience |
| **B: Local + Push** | Medium | $0 | $0-5 | Personal use, always-on |
| **C: Hybrid** | Medium-High | $0 | $124 (app stores) | Balance of features |
| **D: CLI + Email** | Low | $0 | $0 | Quick & simple |

---

## My Recommendation

**For personal use**: Start with **Option B (Local + Push via NTFY)**

Here's why:
1. **Zero ongoing cost** - NTFY is completely free
2. **Simple setup** - Python script + SQLite + cron
3. **Push notifications work great** - NTFY has iOS/Android apps
4. **No app store fees** - Use NTFY's existing app
5. **Can upgrade later** - Database schema transfers to any architecture

### Technical Stack for Option B:
- **Language**: Python 3.11+
- **Database**: SQLite (stored in `~/.congress_trades/trades.db`)
- **Data Source**: House/Senate Stock Watcher APIs
- **Notifications**: NTFY (free, self-hostable, iOS/Android apps)
- **Scheduler**: System cron (Linux/Mac) or Task Scheduler (Windows)
- **Optional Web UI**: Flask or FastAPI for viewing trades

### If you want a "real" mobile app:
Go with **Option A** but:
- Skip the app stores initially (use Expo Go for personal testing)
- Only pay for app stores if you want to distribute to others
- The $0/month cost is accurate for personal use

---

## Features to Implement

### Phase 1: Core (MVP)
- [ ] Scrape all trades from last 5 years (historical backfill)
- [ ] Store in SQLite database with proper schema
- [ ] Daily cron job to fetch new trades
- [ ] Push notification when new trades detected
- [ ] Basic filtering (by member, ticker, party)

### Phase 2: Enhanced
- [ ] Web dashboard to view trades
- [ ] Filter by committee membership
- [ ] Track specific tickers (watchlist)
- [ ] Calculate reporting delay (transaction date vs disclosure date)
- [ ] Aggregate statistics (who trades most, etc.)

### Phase 3: Advanced
- [ ] Correlation with committee assignments
- [ ] Stock performance after disclosure
- [ ] Portfolio simulation ("if you copied X")
- [ ] Export to CSV/JSON

---

## Database Schema

```sql
CREATE TABLE members (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    chamber TEXT NOT NULL,  -- 'house' or 'senate'
    party TEXT,
    state TEXT,
    district TEXT,  -- NULL for senators
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    member_id INTEGER REFERENCES members(id),
    transaction_date DATE NOT NULL,
    disclosure_date DATE NOT NULL,
    ticker TEXT,
    asset_description TEXT NOT NULL,
    asset_type TEXT,
    transaction_type TEXT NOT NULL,  -- 'purchase' or 'sale'
    amount_range TEXT NOT NULL,  -- '$1,001 - $15,000', etc.
    owner TEXT,  -- 'Self', 'Spouse', 'Dependent Child', 'Joint'
    comment TEXT,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(member_id, transaction_date, ticker, transaction_type, amount_range)
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER REFERENCES trades(id),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'sent'
);

CREATE INDEX idx_trades_ticker ON trades(ticker);
CREATE INDEX idx_trades_date ON trades(transaction_date);
CREATE INDEX idx_trades_member ON trades(member_id);
```

---

## Timeline Estimate

| Phase | Tasks |
|-------|-------|
| **Phase 1** | Core scraper, database, notifications |
| **Phase 2** | Web UI, filtering, watchlists |
| **Phase 3** | Analytics, correlations, export |

---

## Questions for You

1. **Which architecture option do you prefer?** (A, B, C, or D)

2. **Do you need a mobile app, or are push notifications to your phone sufficient?**
   - If just notifications: Option B or D
   - If real app needed: Option A or C

3. **Will you run this on an always-on machine?**
   - Yes (desktop/server/Raspberry Pi): Option B, C, or D
   - No (laptop that sleeps): Option A (cloud-hosted)

4. **Do you want to share this with others, or is it just for personal use?**
   - Personal only: Option B is perfect
   - Share with others: Option A is better

5. **Any specific members or tickers you want to track?** (Can add watchlist feature)

---

## Next Steps

Once you decide on an architecture, I'll:
1. Set up the project structure
2. Implement the database schema
3. Build the scraper with API integration
4. Set up notifications (NTFY, Expo Push, etc.)
5. Create the cron job configuration
6. (If mobile app) Build the React Native app

Let me know which option you'd like to proceed with!
