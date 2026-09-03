"""E2E 測試 fixtures — 需要真實 DB + Redis + 網路。

執行方式：
    ATLAS_E2E=1 PYTHONPATH=. pytest tests/e2e/ -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# 全域 skip：未設定 ATLAS_E2E=1 時跳過整個目錄
# ---------------------------------------------------------------------------
if os.getenv("ATLAS_E2E", "0") != "1":
    pytest.skip(
        "E2E tests require ATLAS_E2E=1 and real DB/Redis/network",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Streamlit cache 裝飾器 → no-op（E2E 不跑 Streamlit server）
# ---------------------------------------------------------------------------
_st_mock = MagicMock()


def _passthrough(*args, **kwargs):
    """讓 @st.cache_resource / @st.cache_data 直接回傳原函數。"""
    def decorator(fn):
        return fn
    if args and callable(args[0]):
        return args[0]
    return decorator


_st_mock.cache_resource = _passthrough
_st_mock.cache_data = _passthrough
_st_mock.cache_resource.clear = lambda: None
_st_mock.cache_data.clear = lambda: None

# 在 import service_container 之前先注入 mock streamlit
sys.modules.setdefault("streamlit", _st_mock)

# 現在可安全 import service_container
from atlas.presentation.service_container import (  # noqa: E402
    fetch_institutional_flow,
    fetch_margin_data,
    fetch_stock_data,
    fetch_stock_quote,
    get_indicator_lib,
    get_price_level_calc,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def indicator_lib():
    """真實 IndicatorLibrary 實例。"""
    return get_indicator_lib()


@pytest.fixture(scope="session")
def price_level_calc():
    """真實 PriceLevelCalculator 實例。"""
    return get_price_level_calc()


@pytest.fixture(scope="session")
def tsmc_6mo_df():
    """台積電 6 個月歷史 OHLCV（session 級快取）。"""
    df = fetch_stock_data("2330", "6mo")
    if df.empty:
        pytest.skip("無法取得台積電 6mo 資料（可能網路問題）")
    return df


@pytest.fixture(scope="session")
def tsmc_3mo_df():
    """台積電 3 個月歷史 OHLCV。"""
    df = fetch_stock_data("2330", "3mo")
    if df.empty:
        pytest.skip("無法取得台積電 3mo 資料")
    return df


@pytest.fixture(scope="session")
def tsmc_1mo_df():
    """台積電 1 個月歷史 OHLCV。"""
    df = fetch_stock_data("2330", "1mo")
    if df.empty:
        pytest.skip("無法取得台積電 1mo 資料")
    return df
