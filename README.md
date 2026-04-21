# AI Trading Co-Pilot 🤖📈

> **Real-time decision intelligence for Indian NSE/BSE options & positional trading — delivered through Telegram.**

A production-grade, AI-powered trading assistant that ingests live market data from TrueData, runs a multi-layer scoring engine across 6 indicator groups, applies hard risk rules, and delivers structured trade recommendations directly to your Telegram chat — with an optional Claude / Groq / Gemini AI explanation.

---

## What This Project Does

When you send `/analyze NIFTY` on Telegram, the system:

1. **Fetches live candles** across 4 timeframes (5m / 15m / 1h / Daily) from TrueData WebSocket
2. **Runs 40+ technical indicators** grouped into 6 categories (Trend, Momentum, Volume, Volatility, Structure, Hybrid)
3. **Computes IIS** — Integrated Intelligence Score (−100 to +100)
4. **Computes MTFS** — Multi-Timeframe Score with higher-TF override logic
5. **Scores the Options Chain** — IV Rank, IV Percentile, PCR, Max Pain, GEX, IV Skew
6. **Detects Candlestick Patterns** — 11 patterns (Engulfing, Doji, Morning Star, Double Bottom, etc.)
7. **Aggregates News Sentiment** from Marketaux financial news API
8. **Computes FCS** — Final Conviction Score combining all signals
9. **Applies 8 Hard Risk Rules** — SL distance, RR ratio, ATR extreme, IV Rank, daily loss limit, event blackout, VIX bands, TF contradiction
10. **Sizes the Position** — lot-aware, capital-scaled, VIX-adjusted
11. **Renders a 6-section Telegram report** — via Claude AI, Groq (free), Gemini (free), or deterministic fallback

### Key Formulas

```
IIS  = Σ (group_score × weight × confidence) × 100          # range −100 to +100
MTFS = IIS_1d×0.30 + IIS_1h×0.30 + IIS_15m×0.25 + IIS_5m×0.15
FCS  = IIS×0.35 + MTFS×0.25 + Options×0.20 + Pattern×0.10 + News×0.10
```

---

## Architecture

```
TrueData WebSocket
        │
        ▼
 MarketDataService          OptionsChainService   MarketauxNews
 (tick → candle builder)    (REST snapshot)       (sentiment)
        │                          │                   │
        ▼                          ▼                   ▼
 TimescaleDB + Redis ◄────────  Analyzer  ─────────────┘
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
                  IndicatorEngine  MTFS/FCS  RiskEngine
                  (6 groups / 40+  Scoring   (8 hard rules)
                   indicators)
                        └───────────┬───────────┘
                                    ▼
                             AnalysisResult
                                    │
                                    ▼
                    Explainer (Claude / Groq / Gemini / Fallback)
                                    │
                                    ▼
                        Telegram Bot (19 commands)
                                    │
                           APScheduler (7 cron jobs)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Market Data | TrueData WebSocket (live) + REST (historical) |
| Indicators | pandas-ta-classic, scipy, numpy |
| Options Math | Black-Scholes (custom), scipy.optimize |
| Database | TimescaleDB 2.15 (PostgreSQL 16) — time-series hypertables |
| Cache | Redis 7 |
| ORM | SQLAlchemy 2.0 |
| Bot | python-telegram-bot 22 |
| AI Explanation | Anthropic Claude / Groq (free) / Gemini (free) |
| News | Marketaux API + VADER sentiment fallback |
| Scheduler | APScheduler 3 (cron jobs) |
| ML Engine | scikit-learn + XGBoost (Phase 2, after 500+ outcomes) |
| Infra | Docker Compose (TimescaleDB + Redis) |

---

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Onboarding wizard (capital, risk %, trading style) |
| `/analyze SYMBOL` | Full 6-section AI analysis report |
| `/quick SYMBOL` | 3-line quick signal |
| `/positional SYMBOL` | Positional/swing setup |
| `/swing SYMBOL` | Swing trade analysis |
| `/trade SYMBOL` | Options trade recommendation |
| `/iv SYMBOL` | IV Rank, Percentile, strategy selector |
| `/levels SYMBOL` | Key support/resistance + Fibonacci levels |
| `/news SYMBOL` | Latest news + sentiment score |
| `/watchlist` | Scan all watched symbols |
| `/addwatch SYMBOL` | Add symbol to watchlist |
| `/setcapital AMOUNT` | Update your trading capital |
| `/setrisk PCT` | Update risk per trade (%) |
| `/settings` | View current settings |
| `/alerts on\|off` | Toggle proactive alerts |
| `/history` | Recent signals + win/loss stats |
| `/learn` | Learning engine status |
| `/status` | System health check |
| `/help` | Full command reference |

---

## Proactive Alerts (Auto-sent)

- **09:00 IST** — Pre-market brief with your watchlist summary
- **09:30 IST** (Thursdays only) — Weekly expiry reminder + cutoff rules
- **Every 5 min** — Breakout/Breakdown scanner (price + RVOL confirmation)
- **Every 30 min** — IV Spike / IV Crush detection per symbol
- **15:30 IST** — EOD IV stored for future IV Rank/Percentile calculations
- **Sunday 02:00** — Weekly statistical learning engine update

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.11.x** | Must be 3.11 — not 3.12/3.13 |
| Docker Desktop | Latest | Runs TimescaleDB + Redis |
| Git | Any | For cloning |

### API Keys Needed

| Service | Required? | Cost | Where to get |
|---|---|---|---|
| **TrueData** | Yes | Trial free | [truedata.in](https://truedata.in) |
| **Telegram Bot** | Yes | Free | [@BotFather](https://t.me/BotFather) on Telegram |
| **Groq** (AI explanation) | Recommended | **Free** 14,400 req/day | [console.groq.com](https://console.groq.com) |
| Anthropic Claude | Optional | Paid | [console.anthropic.com](https://console.anthropic.com) |
| Google Gemini | Optional | **Free** 1,500 req/day | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Marketaux (news) | Optional | Free 100 req/day | [app.marketaux.com](https://app.marketaux.com) |

> If no AI key is provided, the system uses a deterministic fallback formatter.
> All signals, scores, levels, and risk rules still work perfectly without an AI key.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/Option_bot.git
cd Option_bot
```

### 2. Install Python 3.11

Download from [python.org](https://www.python.org/downloads/release/python-3119/)

Verify the installation:
```bash
py -3.11 --version
# Python 3.11.x
```

### 3. Create a virtual environment

```bash
py -3.11 -m venv .venv
```

Activate it:

| OS | Command |
|---|---|
| Windows | `.venv\Scripts\activate` |
| Mac / Linux | `source .venv/bin/activate` |

### 4. Install Python dependencies

```bash
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

This installs ~40 packages including pandas, numpy, scipy, sqlalchemy, redis, python-telegram-bot, anthropic, groq, APScheduler, xgboost, and more.

### 5. Install and start Docker Desktop

Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)

After installing, open Docker Desktop and wait for it to fully start, then verify:
```bash
docker --version
```

> **Windows users:** If you already have PostgreSQL installed locally, there may be a port conflict on 5432. The project is pre-configured to use port **5433** for Docker to avoid this.

### 6. Start the database and Redis cache

```bash
docker compose -f docker/docker-compose.yml up -d
```

Verify both containers are healthy:
```bash
docker ps
```
Expected output:
```
NAMES           STATUS          PORTS
copilot-pg      Up (healthy)    0.0.0.0:5433->5432/tcp
copilot-redis   Up              0.0.0.0:6379->6379/tcp
```

### 7. Configure your API keys

Open the `.env` file in the project root and fill in your credentials:

```env
# ── Telegram ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ADMIN_CHAT_IDS=your_telegram_chat_id

# ── TrueData ──────────────────────────────────────────
TRUEDATA_USER=your_truedata_username
TRUEDATA_PASSWORD=your_truedata_password
TRUEDATA_WS_PORT=8086        # 8086 = sandbox/trial | 8084 = production

# ── AI Explanation (fill ONE — first non-empty key wins) ──
GROQ_API_KEY=gsk_xxxxxxxxxxxx          # Free — recommended
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx  # Paid
# GEMINI_API_KEY=AIzaxxxxxxxxxx         # Free

# ── News Sentiment (optional) ─────────────────────────
MARKETAUX_KEY=your_marketaux_key
```

**How to get your Telegram Chat ID:**
1. Open Telegram and message [@userinfobot](https://t.me/userinfobot)
2. It replies with your numeric chat ID — paste it into `TELEGRAM_ADMIN_CHAT_IDS`

**How to create a Telegram Bot:**
1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you into `TELEGRAM_BOT_TOKEN`

### 8. Run database migrations

```bash
# Windows
.venv\Scripts\python.exe -m app.db.migrate

# Mac / Linux
.venv/bin/python -m app.db.migrate
```

Expected output:
```
applying_migration  file=001_schema.sql
applying_migration  file=init.sql
migrations_complete count=2
```

### 9. Run tests (verify everything works)

```bash
# Windows
.venv\Scripts\python.exe -m pytest -v

# Mac / Linux
.venv/bin/python -m pytest -v
```

Expected: **28 passed** in ~3 seconds.

### 10. Start the bot

```bash
# Windows
.venv\Scripts\python.exe -m app.main

# Mac / Linux
.venv/bin/python -m app.main
```

You should see:
```
startup        env=development
startup_complete
```

Open Telegram, find your bot, and send `/start` 🎉

---

## Project Structure

```
Option_bot/
├── app/
│   ├── alerts/           # Breakout, IV spike/crush, event & expiry alerts
│   ├── config/           # Settings (pydantic), all domain constants & weights
│   ├── core/             # Analyzer — full end-to-end scoring pipeline
│   ├── data/             # TrueData WS client, historical REST, candle builder, Redis cache
│   ├── db/               # SQLAlchemy models, session, repositories, migrations
│   ├── explain/          # Multi-provider AI explainer (Claude/Groq/Gemini/fallback)
│   ├── indicators/       # 6 indicator groups + IIS computation
│   │   ├── trend.py      # EMA, SMA, Supertrend, ADX, Aroon, PSAR, HMA, VWMA, KAMA, TEMA
│   │   ├── momentum.py   # RSI, MACD, Stochastic, StochRSI, CCI, ROC, Williams%R, TSI, CMO
│   │   ├── volume.py     # RVOL, OBV, CMF, MFI, VWAP, Accumulation/Distribution
│   │   ├── volatility.py # ATR, Bollinger Bands, Keltner Channel, Donchian, BB Squeeze
│   │   ├── structure.py  # Classic pivots, Fibonacci retracements, swing high/low levels
│   │   └── hybrid.py     # Ichimoku Cloud, Vortex, Coppock Curve, Fisher Transform
│   ├── learning/         # Phase 1 statistical + Phase 2 XGBoost engine with safety gates
│   ├── news/             # Marketaux client, VADER sentiment, macro event registry
│   ├── options/          # Black-Scholes IV/Greeks, IV Rank/Percentile, PCR, Max Pain, GEX
│   ├── patterns/         # 11 candlestick pattern detectors
│   ├── risk/             # Risk engine (8 hard rules), position sizer, daily P&L limits
│   ├── scheduler/        # APScheduler cron jobs (7 scheduled tasks)
│   ├── scoring/          # MTFS, FCS, regime detection
│   ├── telegram_bot/     # Bot handlers, service layer, application builder
│   ├── utils/            # IST clock helpers, structured logging
│   └── main.py           # Production entrypoint (bot + scheduler + data pipeline)
├── docker/
│   └── docker-compose.yml   # TimescaleDB 2.15 + Redis 7
├── sql/
│   ├── init.sql             # TimescaleDB + pg_trgm extensions
│   └── 001_schema.sql       # Full production schema (11 tables, hypertables, indexes)
├── tests/                   # 28 unit tests
├── .env                     # Your secrets — NEVER commit this file
├── .gitignore
├── requirements.txt
├── pytest.ini
└── spec.md                  # Full product blueprint (source of truth)
```

---

## Development Phases

| Phase | Weeks | What | Status |
|---|---|---|---|
| **Phase 1 — Foundation** | 1–4 | Data pipeline, all indicators, IIS/MTFS/FCS, Risk Engine, Options intelligence (BS/IV/PCR/MaxPain), Telegram bot (19 commands), Alerts, Scheduler, Statistical learning | ✅ Complete |
| **Phase 2 — ML Intelligence** | 5–7 | XGBoost model training on 500+ closed outcomes, feature engineering, blended FCS (30% ML + 70% rules) | 🟡 Scaffolded |
| **Phase 3 — Advanced Features** | 8–10 | Multi-leg strategies, portfolio Greeks, backtester, paper-trading mode | ⏳ Pending |
| **Phase 4 — Production Hardening** | 11–12 | Prometheus/Grafana monitoring, SLOs, load testing, deployment automation | ⏳ Pending |

---

## All Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather |
| `TELEGRAM_ADMIN_CHAT_IDS` | — | Comma-separated Telegram chat IDs |
| `TRUEDATA_USER` | — | TrueData login username |
| `TRUEDATA_PASSWORD` | — | TrueData password |
| `TRUEDATA_WS_URL` | push.truedata.in | WebSocket host |
| `TRUEDATA_WS_PORT` | 8084 | 8086 = sandbox, 8084 = production |
| `TRUEDATA_HISTORICAL_URL` | https://history.truedata.in | Historical REST base URL |
| `TRUEDATA_API_URL` | https://api.truedata.in | TrueData API base URL |
| `ANTHROPIC_API_KEY` | — | Claude API key (optional) |
| `ANTHROPIC_MODEL` | claude-sonnet-4-6 | Model to use |
| `GROQ_API_KEY` | — | Groq API key (optional, free) |
| `GEMINI_API_KEY` | — | Gemini API key (optional, free) |
| `MARKETAUX_KEY` | — | Marketaux news API key (optional) |
| `POSTGRES_DSN` | ...localhost:5433/copilot | TimescaleDB connection string |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection string |
| `DEFAULT_CAPITAL` | 500000 | Default trading capital in Rs |
| `DEFAULT_RISK_PCT` | 1.0 | Default risk per trade (%) |
| `DAILY_LOSS_LIMIT_PCT` | 3.0 | Daily loss limit (% of capital) |
| `APP_ENV` | development | development or production |
| `LOG_LEVEL` | INFO | DEBUG / INFO / WARNING / ERROR |

---

## Troubleshooting

**`User Already Connected` error on TrueData**

Force-logout your session by visiting this URL in your browser:
```
https://api.truedata.in/logoutRequest?user=YOUR_USER&password=YOUR_PASSWORD&port=8086
```

**Docker Desktop not starting / containers not found**

Make sure Docker Desktop application is fully started (whale icon in system tray), then:
```bash
docker context use desktop-linux   # Windows with WSL2
docker compose -f docker/docker-compose.yml up -d
```

**`python` runs 3.13 instead of 3.11 (Windows)**

Always use the venv Python directly:
```bash
.venv\Scripts\python.exe -m app.main
# or activate the venv first:
.venv\Scripts\activate
python -m app.main
```

**Port 5432 conflict (existing PostgreSQL)**

Already handled — Docker maps to port 5433. If you see connection errors, ensure `.env` has:
```env
POSTGRES_DSN=postgresql+psycopg2://copilot:copilot@localhost:5433/copilot
```

**Bot not responding on Telegram**

1. Run `docker ps` — ensure both containers are `Up (healthy)`
2. Check `.env` has a valid `TELEGRAM_BOT_TOKEN`
3. Make sure the bot is not already running in another terminal window
4. Try sending `/start` to your bot

---

## Important Disclaimers

- **Paper trade first.** Run the system for 2–4 weeks collecting signal outcomes before using real capital.
- **This is decision support, not financial advice.** The system enforces hard risk rules but cannot guarantee profits. All trading carries risk.
- **Never commit `.env`** — it contains your API credentials. It is listed in `.gitignore` but double-check before pushing.
- **TrueData trial** provides 15 days of bar history and up to 50 symbols. Replace with a production subscription for full live trading.

---

## License

MIT License

---

*Built with Python 3.11 · TrueData · TimescaleDB · Redis · python-telegram-bot · Groq / Anthropic Claude*
