# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Atlas Trading System v5.0 — a quantitative trading decision system for Taiwan (P0) and US (P1) stock markets. Built with a 5-layer architecture: Presentation (Streamlit) → Application → Strategy → Domain → Infrastructure (PostgreSQL + Redis).

## Common Commands

```bash
# Install dependencies (editable mode with dev tools)
pip install -e ".[dev]"

# Run all tests (~248 tests, <1s)
PYTHONPATH=. pytest tests/ -q --tb=short

# Run a single test file
PYTHONPATH=. pytest tests/unit/test_scoring_engine.py -x -q --tb=short

# Run a specific test
PYTHONPATH=. pytest tests/unit/test_models.py::TestClassName::test_method -x --tb=long

# Lint
ruff check atlas/
ruff format atlas/

# Start full stack (app + PostgreSQL 17 + Redis 7)
docker compose up --build -d

# Run Streamlit locally (requires PG + Redis running)
streamlit run atlas/presentation/app.py

# Database migration
export ATLAS_DATABASE_URL=postgresql://atlas:atlas_dev@localhost:5432/atlas
python -m alembic upgrade head

# Seed data
PYTHONPATH=. python scripts/seed_data.py

# E2E verification
PYTHONPATH=. python scripts/verify_e2e.py

# ML model training
PYTHONPATH=. python scripts/train_model.py
```

## Architecture

```
atlas/
  config.py              AtlasConfig dataclass (aggregates all sub-configs from env vars)
  enums.py               MarketType, RegimeState, SentimentLevel, ConclusionLevel, SignalType, etc.
  constants.py           OTC_CODES, timeouts, labels
  events.py              Domain event types for EventBus pub/sub
  exceptions.py          Exception hierarchy (20+ types)
  models/                Dataclasses (not ORM) — market_data, signals, scoring, backtest, etc.
  interfaces/            ABCs/Protocols for domain, application, infrastructure

  infrastructure/
    orm/                 27 SQLAlchemy 2.0 ORM models (base.py defines Base)
    db.py                Database session management
    cache.py             Redis wrapper
    data_manager.py      TWSE/TPEx/yfinance data fetching with fallback + DB persistence
    quote_adapter.py     Real-time quote: TWSE MIS → yfinance → cache (fallback chain)
    event_bus.py         Async pub/sub event bus
    notification_hub.py  Multi-channel notification dispatcher
    notifications/       Channel adapters: Discord, LINE, Telegram, Email

  domain/
    trading_calendar.py  Trading day/holiday/market hours logic
    market_regime.py     Bull/Bear/Range detection
    sentiment.py         5-level market sentiment scoring
    portfolio.py         Position tracking with R-multiple risk
    fund_flow.py         Institutional flow analysis
    industry_analyzer.py Industry rotation detection

  strategy/
    indicator_lib.py     Technical indicators: MA/RSI/MACD/BB/ATR/KD/OBV/VP
    scoring_engine.py    4-axis (Industry→Catalyst→Flow→RS) + 3-aspect scoring
    smc_module.py        Smart Money Concepts (Order Blocks, FVG, Sweep, CRT)
    ml_engine.py         RandomForest prediction + feature importance
    monte_carlo.py       Monte Carlo simulation

  application/
    screener_engine.py   Universe → Score → Rank → Top N pipeline
    conclusion_engine.py 7-level conclusion with 3-layer downgrade
    backtest_engine.py   Walk-forward + parameter scan + cost model
    realtime_radar.py    11 intraday signal detectors
    paper_trading.py     Simulated trading with commission/tax
    workflow_engine.py   Pre/Intra/Post market automated SOP
    scheduler.py         APScheduler cron-based auto scheduler

  presentation/
    app.py               Streamlit entry point
    service_container.py Lazy-init singleton services via st.cache_resource
    auth.py              Session-based login
    pages/               P-01 to P-13 (Dashboard, Premarket, Radar, Screener, Universe,
                         Portfolio, Backtest, IPO, Industry, Scheduler, Settings, K-line,
                         Paper Trading)
    components/          Theme, sidebar, chart helpers

tests/                   Unit + integration tests (conftest.py has shared fixtures)
alembic/                 DB migrations (initial 27-table schema + performance indexes)
scripts/                 seed_data.py, verify_e2e.py, train_model.py, benchmark.py
docker/                  Dockerfile (multi-stage, python:3.12-slim), entrypoint.sh
```

## Key Design Patterns

- **Fallback chains**: Quote sources (TWSE MIS → yfinance → cache), notifications (Discord → LINE → Telegram → Email)
- **Service container**: `atlas/presentation/service_container.py` uses `@st.cache_resource` for lazy singleton initialization — all Streamlit pages get services from here
- **Config from env**: `AtlasConfig` in `config.py` reads all settings from environment variables with sensible defaults
- **ORM vs Models**: `atlas/models/` contains pure dataclasses for domain logic; `atlas/infrastructure/orm/` contains SQLAlchemy ORM models for persistence
- **Event-driven**: `EventBus` in infrastructure handles async pub/sub between components

## Testing Conventions

- All tests are in `tests/unit/` and `tests/integration/`
- Shared fixtures in `tests/conftest.py` (sample OHLCV DataFrames, mock DataManager, mock EventBus)
- Tests run without external services (DB/Redis mocked) — fast execution (<1s)
- `PYTHONPATH=.` is required when running from project root

## Known Gotchas

- `asyncpg` uses `$1,$2` params — `::type` casts conflict; pass Python-native types instead
- TWSE MIS API returns `z="-"` (not None) for non-trading hours — must fallback to `y` (yesterday's close)
- `pd.read_html(resp.text)` on Python 3.14 treats short strings as file paths → use `pd.read_html(StringIO(resp.text))`
- `asyncio.get_event_loop()` raises RuntimeError in Python 3.12+ threads without running loop → use `asyncio.run()`
- `strategy` table has a NOT NULL UNIQUE `code` column — INSERT must include it
- RSI returns NaN for purely monotonic series (min_periods constraint)

## Ruff Configuration

- Target: Python 3.12
- Line length: 100
- Rules: E, F, W, I, N, UP, B, A, SIM (E501 ignored)
- First-party imports: `atlas`

## Docker

- Multi-stage build: `docker/Dockerfile` (builder + runtime, non-root `atlas` user)
- Compose: `docker-compose.yml` (app + postgres:17 + redis:7-alpine)
- Monitoring: `docker/docker-compose.monitoring.yml` (Prometheus + Grafana)
- Production: `docker/docker-compose.prod.yml`
- `.dockerignore` excludes `*.md` but keeps `README.md`

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`): lint → syntax-check → test (with PG17 + Redis 7 services) → docker build (master only). Uses Python 3.14 with `allow-prereleases: true`.
