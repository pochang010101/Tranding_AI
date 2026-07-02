"""pytest 共用 fixtures。"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from atlas.config import AtlasConfig
from atlas.enums import MarketType


@pytest.fixture()
def atlas_config() -> AtlasConfig:
    return AtlasConfig()


@pytest.fixture()
def sample_stock_id() -> str:
    return "2330"


@pytest.fixture()
def market_tw() -> MarketType:
    return MarketType.TW


@pytest.fixture()
def market_us() -> MarketType:
    return MarketType.US


@pytest.fixture()
def sample_ohlcv_df() -> pd.DataFrame:
    """產生 120 日 OHLCV 測試資料。"""
    rng = np.random.default_rng(42)
    n = 120
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
    close = 100.0
    rows = []
    for d in dates:
        change = rng.normal(0.001, 0.015)
        o = close
        c = close * (1 + change)
        h = max(o, c) * (1 + abs(rng.normal(0, 0.005)))
        l = min(o, c) * (1 - abs(rng.normal(0, 0.005)))
        v = int(rng.integers(5000, 50000))
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
        close = c
    return pd.DataFrame(rows)


@pytest.fixture()
def small_ohlcv_df() -> pd.DataFrame:
    """10 筆小型 OHLCV。"""
    return pd.DataFrame({
        "open": [100, 101, 102, 103, 104, 103, 102, 105, 106, 108],
        "high": [102, 103, 104, 105, 106, 105, 104, 107, 108, 110],
        "low": [99, 100, 101, 102, 103, 101, 100, 103, 104, 106],
        "close": [101, 102, 103, 104, 105, 102, 103, 106, 107, 109],
        "volume": [1000, 1200, 1100, 1300, 1500, 2000, 1800, 1600, 1400, 1700],
    })


@pytest.fixture()
def mock_data_manager():
    """Mock DataManager with async methods."""
    dm = AsyncMock()

    # 模擬 DailyBar
    bars = []
    close = 100.0
    rng = np.random.default_rng(42)
    for i in range(60):
        change = rng.normal(0.001, 0.015)
        c = close * (1 + change)
        bar = MagicMock()
        bar.close = c
        bar.high = c * 1.01
        bar.low = c * 0.99
        bar.open = close
        bar.volume = int(rng.integers(5000, 50000))
        bar.trade_date = date(2025, 1, 1)
        bars.append(bar)
        close = c

    dm.fetch_daily_bars = AsyncMock(return_value=bars)
    dm.fetch_revenue = AsyncMock(return_value={"yoy_growth": 15.0, "mom_growth": 3.0})
    return dm


@pytest.fixture()
def mock_event_bus():
    """Mock EventBus."""
    from atlas.infrastructure.event_bus import EventBus
    return EventBus()
