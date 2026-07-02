# Atlas Trading System v5.0

高勝率量化交易決策系統 — 台股/美股全市場覆蓋。

## Architecture

```
L5 Presentation   Streamlit + Plotly (12 pages)
L4 Application    Screener / Conclusion / Backtest / Workflow
L3 Strategy       Indicator / Scoring / SMC / ML / Monte Carlo
L2 Domain         Calendar / Regime / Sentiment / Portfolio
L1 Infrastructure PostgreSQL + Redis + EventBus + Notifications
```

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env
# Edit .env with your API keys

# 2. Start all services
docker compose up --build -d

# 3. Open browser
open http://localhost:8501
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests (148 tests, <1s)
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
    event_bus.py         Async pub/sub
    logger.py            JSON structured logging
    health_checker.py    Component health + auto-recovery
    notification_hub.py  Discord/LINE/Telegram/Email
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
    backtest_engine.py   Cost model + Walk-Forward
    workflow_engine.py   Pre/Intra/Post market SOP
    realtime_radar.py    11 intraday detectors
  presentation/
    app.py               Streamlit entry point
    pages/               P-01 to P-12 (12 pages)
    components/          Theme / Sidebar / Charts
tests/                   148 tests (unit + integration)
docker/                  Dockerfile + entrypoint.sh
alembic/                 DB migrations (27 tables)
```

## Selection Logic

**Four Axes** (entry): Industry Rotation -> Catalyst -> Fund Flow -> RS **Three
Aspects** (validation): Technical + Fundamental + Institutional At least 2 of 3
aspects must be positive to qualify.

## Tech Stack

| Component | Technology                  |
| --------- | --------------------------- |
| UI        | Streamlit 1.58 + Plotly 6.8 |
| Database  | PostgreSQL 17               |
| Cache     | Redis 7                     |
| ML        | scikit-learn (RandomForest) |
| ORM       | SQLAlchemy 2.0              |
| Migration | Alembic                     |
| Container | Docker + docker-compose     |
| CI        | GitHub Actions              |
| Testing   | pytest 9.0 (148 tests)      |

## Environment Variables

See [.env.example](.env.example) for all configuration options.

## License

MIT
