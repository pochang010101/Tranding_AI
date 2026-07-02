# Atlas Trading System v5.0

High win-rate quantitative trading decision system for TW/US markets.

## Architecture

```
L5 Presentation   Streamlit + Plotly (13 pages, real data)
L4 Application    Screener / Conclusion / Backtest / Workflow / Paper Trading
L3 Strategy       Indicator / Scoring / SMC / ML / Monte Carlo
L2 Domain         Calendar / Regime / Sentiment / Portfolio
L1 Infrastructure PostgreSQL + Redis + EventBus + Notifications
```

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env
# Edit .env with your API keys (Discord/Telegram/LINE optional)

# 2. Start all services
docker compose up --build -d

# 3. Open browser
open http://localhost:8501
```

## Features

- **13 Streamlit Pages** with live data (yfinance + TWSE API)
  - P-01 Dashboard: Market regime, RSI sentiment, live quotes
  - P-02 Premarket: US index/stock analysis, gap prediction
  - P-03 Radar: Real-time signal monitoring
  - P-04 Screener: 30-stock scan with 4-axis scoring
  - P-05 Universe: 4-layer stock pool filtering
  - P-06 Portfolio: Position tracking with live P&L
  - P-07 Backtest: Strategy backtesting + Monte Carlo simulation
  - P-08 IPO: Subscription tracking + honeymoon monitoring
  - P-09 Industry: RS ranking + fund flow proxy
  - P-10 Scheduler: Workflow management + manual trigger
  - P-11 Settings: API keys, notification test, health check
  - P-12 K-line: Interactive candlestick + indicators + SMC overlay
  - P-13 Paper Trading: Simulated order execution
- **Automated Workflows** (pre-market/intraday/post-market/monthly rebuild)
- **Notification Push** (Discord/Telegram/LINE with fallback chain)
- **Paper Trading** with commission/tax model
- **Walk-Forward Analysis** with parameter optimization

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests (164 tests, <1s)
pytest tests/ -v

# Lint
ruff check atlas/
ruff format atlas/

# Database migration
export ATLAS_DATABASE_URL=postgresql://atlas:atlas_dev@localhost:5432/atlas
python -m alembic upgrade head
```

## Project Structure

```
atlas/
  config.py              Global config (env vars)
  enums.py               13 Enums
  events.py              9 Event types
  exceptions.py          20+ Exception hierarchy
  models/                7 files, 17 Dataclasses
  interfaces/            5 files, 27 ABC/Protocol
  infrastructure/
    orm/                 27 ORM models (SQLAlchemy 2.0)
    data_manager.py      TWSE/yfinance fallback + DB persistence
    quote_adapter.py     TWSE MIS + yfinance + cache fallback chain
    event_bus.py         Async pub/sub
    logger.py            JSON structured logging
    health_checker.py    Component health + auto-recovery
    notification_hub.py  Discord/LINE/Telegram/Email fallback
    notifications/       Channel adapters (Discord/LINE/Telegram/Email)
  domain/
    trading_calendar.py  Trading day/holiday/market hours
    market_regime.py     Bull/Bear/Range detection
    sentiment.py         5-level market sentiment
    portfolio.py         Position tracking + R-multiple
    fund_flow.py         Institutional flow analysis
    industry_analyzer.py Industry rotation detection
  strategy/
    indicator_lib.py     MA/RSI/MACD/BB/ATR/KD/OBV/VP
    scoring_engine.py    4-axis + 3-aspect scoring
    smc_module.py        SMC/ICT (OB/FVG/Sweep/CRT)
    ml_engine.py         RandomForest prediction
    monte_carlo.py       Monte Carlo simulation
  application/
    screener_engine.py   Universe -> Score -> Rank -> Top N
    conclusion_engine.py 7-level + 3-layer downgrade
    backtest_engine.py   Cost model + Walk-Forward + Param Scan
    workflow_engine.py   Pre/Intra/Post market SOP + auto-notify
    realtime_radar.py    11 intraday detectors
    paper_trading.py     Simulated trading with commission/tax
    scheduler.py         Cron-based auto scheduler
  presentation/
    app.py               Streamlit entry point
    service_container.py Shared backend services + caching
    pages/               P-01 to P-13 (13 pages)
    components/          Theme / Sidebar / Charts
tests/                   164 tests (unit + integration)
docker/                  Dockerfile + entrypoint.sh
alembic/                 DB migrations (27 tables + 12 indexes)
```

## Selection Logic

**Four Axes** (entry): Industry Rotation -> Catalyst -> Fund Flow -> RS

**Three Aspects** (validation): Technical + Fundamental + Institutional

At least 2 of 3 aspects must be positive to qualify.

## Automated Schedules

| Schedule | Cron | Workflow |
|----------|------|----------|
| Pre-market | `0 8 * * 1-5` | International data + gap prediction + regime |
| Intraday | `0 9 * * 1-5` | Start radar monitoring |
| Post-market | `45 13 * * 1-5` | Stop radar + data update + screening |
| Monthly rebuild | `0 20 * * 0` | Rebuild stock universe |

Non-trading days automatically skipped (except monthly rebuild).

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI | Streamlit 1.58 + Plotly 6.8 |
| Database | PostgreSQL 17 |
| Cache | Redis 7 |
| ML | scikit-learn (RandomForest) |
| ORM | SQLAlchemy 2.0 |
| Migration | Alembic |
| Container | Docker + docker-compose |
| CI | GitHub Actions |
| Testing | pytest 9.0 (164 tests) |
| Data | yfinance + TWSE/TPEx OpenData |

## Environment Variables

See [.env.example](.env.example) for all configuration options.

Key variables:
- `ATLAS_DATABASE_URL` — PostgreSQL connection string
- `ATLAS_REDIS_HOST` — Redis host
- `DISCORD_WEBHOOK_URL` — Discord notification
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Telegram notification
- `LINE_CHANNEL_TOKEN` — LINE notification

## License

MIT
