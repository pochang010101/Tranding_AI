"""SentimentService 測試 — 驗證四個因子計算與容錯。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from atlas.domain.sentiment import SentimentService
from atlas.enums import MarketType, SentimentLevel


@pytest.fixture()
def mock_dm():
    dm = AsyncMock()
    dm.fetch_daily_all = AsyncMock(return_value=[])
    return dm


@pytest.fixture()
def svc(mock_dm):
    return SentimentService(data_manager=mock_dm, cache=None)


# ── 外資期貨未平倉因子 ──────────────────────────────


class TestForeignFuturesScore:
    """測試 _calc_foreign_futures_score 各段映射。"""

    def _make_institutional_df(self, net_position: int) -> pd.DataFrame:
        return pd.DataFrame([
            {"identity": "外資", "long_volume": 0, "short_volume": 0,
             "net_volume": 0, "long_position": 0, "short_position": 0,
             "net_position": net_position},
        ])

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_extreme_greed(self, mock_fetch, svc):
        """淨多單 >= 20000 → 90 分"""
        mock_fetch.return_value = self._make_institutional_df(25000)
        score = svc._calc_foreign_futures_score()
        assert score == 90.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_greed(self, mock_fetch, svc):
        """淨多單 15000 → 70 + (5000/10000)*20 = 80"""
        mock_fetch.return_value = self._make_institutional_df(15000)
        score = svc._calc_foreign_futures_score()
        assert score == 80.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_neutral_positive(self, mock_fetch, svc):
        """淨多單 5000 → 50 + (5000/10000)*20 = 60"""
        mock_fetch.return_value = self._make_institutional_df(5000)
        score = svc._calc_foreign_futures_score()
        assert score == 60.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_neutral_zero(self, mock_fetch, svc):
        """淨口數 0 → 50"""
        mock_fetch.return_value = self._make_institutional_df(0)
        score = svc._calc_foreign_futures_score()
        assert score == 50.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_fear(self, mock_fetch, svc):
        """淨空單 -5000 → 30 + ((-5000 - -10000) / 10000) * 20 = 40"""
        mock_fetch.return_value = self._make_institutional_df(-5000)
        score = svc._calc_foreign_futures_score()
        assert score == 40.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_extreme_fear(self, mock_fetch, svc):
        """淨空單 -25000 → 10"""
        mock_fetch.return_value = self._make_institutional_df(-25000)
        score = svc._calc_foreign_futures_score()
        assert score == 10.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_empty_df_fallback(self, mock_fetch, svc):
        """空 DataFrame → fallback 50"""
        mock_fetch.return_value = pd.DataFrame()
        score = svc._calc_foreign_futures_score()
        assert score == 50.0

    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    def test_exception_fallback(self, mock_fetch, svc):
        """例外 → fallback 50"""
        mock_fetch.side_effect = RuntimeError("network error")
        score = svc._calc_foreign_futures_score()
        assert score == 50.0


# ── 融資使用率因子 ──────────────────────────────────


class TestMarginUsageScore:
    """測試 _calc_margin_usage_score 映射。"""

    def _make_margin_df(self, balance: int, limit: int) -> pd.DataFrame:
        return pd.DataFrame([
            {"code": "2330", "name": "台積電",
             "margin_buy": 0, "margin_sell": 0,
             "margin_balance": balance, "margin_limit": limit,
             "short_buy": 0, "short_sell": 0,
             "short_balance": 0, "short_limit": 0},
        ])

    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    def test_high_usage(self, mock_twse, mock_tpex, svc):
        """使用率 60% > 50% → 80"""
        mock_twse.return_value = self._make_margin_df(600, 1000)
        mock_tpex.return_value = pd.DataFrame()
        score = svc._calc_margin_usage_score()
        assert score == 80.0

    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    def test_medium_usage(self, mock_twse, mock_tpex, svc):
        """使用率 40% → 50 + (40-30)/20*30 = 65"""
        mock_twse.return_value = self._make_margin_df(400, 1000)
        mock_tpex.return_value = pd.DataFrame()
        score = svc._calc_margin_usage_score()
        assert score == 65.0

    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    def test_low_usage(self, mock_twse, mock_tpex, svc):
        """使用率 10% < 15% → 20"""
        mock_twse.return_value = self._make_margin_df(100, 1000)
        mock_tpex.return_value = pd.DataFrame()
        score = svc._calc_margin_usage_score()
        assert score == 20.0

    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    def test_empty_fallback(self, mock_twse, mock_tpex, svc):
        """無資料 → fallback 50"""
        mock_twse.return_value = pd.DataFrame()
        mock_tpex.return_value = pd.DataFrame()
        score = svc._calc_margin_usage_score()
        assert score == 50.0

    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    def test_exception_fallback(self, mock_twse, mock_tpex, svc):
        """例外 → fallback 50"""
        mock_twse.side_effect = RuntimeError("db down")
        score = svc._calc_margin_usage_score()
        assert score == 50.0


# ── P/C Ratio 因子 ──────────────────────────────────


class TestPCRatioScore:
    """測試 _calc_pc_ratio_score 映射。"""

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_extreme_greed(self, mock_fetch, svc):
        """P/C < 0.5 → 90"""
        mock_fetch.return_value = {"pc_ratio_oi": 0.4, "pc_ratio_volume": 0.5}
        score = svc._calc_pc_ratio_score()
        assert score == 90.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_greed(self, mock_fetch, svc):
        """P/C = 0.65 → 90 - (0.15/0.3)*10 = 85"""
        mock_fetch.return_value = {"pc_ratio_oi": 0.65}
        score = svc._calc_pc_ratio_score()
        assert score == 85.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_neutral(self, mock_fetch, svc):
        """P/C = 1.0 → 80 - (0.2/0.4)*60 = 50"""
        mock_fetch.return_value = {"pc_ratio_oi": 1.0}
        score = svc._calc_pc_ratio_score()
        assert score == 50.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_fear(self, mock_fetch, svc):
        """P/C = 1.2 → 20"""
        mock_fetch.return_value = {"pc_ratio_oi": 1.2}
        score = svc._calc_pc_ratio_score()
        assert score == 20.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_extreme_fear(self, mock_fetch, svc):
        """P/C > 1.5 → 10"""
        mock_fetch.return_value = {"pc_ratio_oi": 2.0}
        score = svc._calc_pc_ratio_score()
        assert score == 10.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_empty_fallback(self, mock_fetch, svc):
        """空 dict → fallback 50"""
        mock_fetch.return_value = {}
        score = svc._calc_pc_ratio_score()
        assert score == 50.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_exception_fallback(self, mock_fetch, svc):
        """例外 → fallback 50"""
        mock_fetch.side_effect = ConnectionError("timeout")
        score = svc._calc_pc_ratio_score()
        assert score == 50.0

    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    def test_fallback_to_volume_ratio(self, mock_fetch, svc):
        """OI ratio 為 0 時 fallback 到 volume ratio"""
        mock_fetch.return_value = {"pc_ratio_oi": 0.0, "pc_ratio_volume": 1.0}
        score = svc._calc_pc_ratio_score()
        assert score == 50.0  # P/C=1.0 → 50


# ── 整合測試：calculate 方法 ────────────────────────


class TestSentimentCalculate:
    """測試 calculate() 整合流程。"""

    @pytest.mark.asyncio
    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    async def test_all_factors_real(
        self, mock_inst, mock_twse, mock_tpex, mock_pc, mock_dm
    ):
        """四個因子全部接入 → 加權計算正確。"""
        # 外資淨多 15000 → 80 分
        mock_inst.return_value = pd.DataFrame([
            {"identity": "外資", "long_volume": 0, "short_volume": 0,
             "net_volume": 0, "long_position": 0, "short_position": 0,
             "net_position": 15000},
        ])
        # 融資使用率 40% → 65 分
        mock_twse.return_value = pd.DataFrame([
            {"code": "2330", "name": "T", "margin_buy": 0, "margin_sell": 0,
             "margin_balance": 400, "margin_limit": 1000,
             "short_buy": 0, "short_sell": 0,
             "short_balance": 0, "short_limit": 0},
        ])
        mock_tpex.return_value = pd.DataFrame()
        # P/C ratio 1.0 → 50 分
        mock_pc.return_value = {"pc_ratio_oi": 1.0}
        # 漲跌家數 → fallback 50（mock_dm 回空 list）
        mock_dm.fetch_daily_all = AsyncMock(return_value=[])

        svc = SentimentService(data_manager=mock_dm, cache=None)
        result = await svc.calculate(MarketType.TW)

        # 加權: 50*0.3 + 80*0.3 + 65*0.2 + 50*0.2 = 15+24+13+10 = 62
        assert result.index_value == 62.0
        assert result.level == SentimentLevel.GREED
        assert result.components["advance_decline"] == 50.0
        assert result.components["foreign_futures"] == 80.0
        assert result.components["margin_ratio"] == 65.0
        assert result.components["vix"] == 50.0

    @pytest.mark.asyncio
    @patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio")
    @patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all")
    @patch("atlas.infrastructure.margin_data.fetch_twse_margin_all")
    @patch("atlas.infrastructure.taifex_data.fetch_futures_institutional")
    async def test_all_factors_fail_fallback_50(
        self, mock_inst, mock_twse, mock_tpex, mock_pc, mock_dm
    ):
        """所有因子都失敗 → 全部 fallback 50 → 總分 50。"""
        mock_inst.side_effect = RuntimeError("fail")
        mock_twse.side_effect = RuntimeError("fail")
        mock_tpex.side_effect = RuntimeError("fail")
        mock_pc.side_effect = RuntimeError("fail")
        mock_dm.fetch_daily_all = AsyncMock(side_effect=RuntimeError("fail"))

        svc = SentimentService(data_manager=mock_dm, cache=None)
        result = await svc.calculate(MarketType.TW)

        assert result.index_value == 50.0
        assert result.level == SentimentLevel.NEUTRAL

    @pytest.mark.asyncio
    async def test_interface_unchanged(self, mock_dm):
        """公開方法簽名不變：calculate / get_current / get_history。"""
        svc = SentimentService(data_manager=mock_dm, cache=None)
        # calculate 回傳 SentimentResult
        with patch("atlas.infrastructure.taifex_data.fetch_futures_institutional",
                    return_value=pd.DataFrame()), \
             patch("atlas.infrastructure.margin_data.fetch_twse_margin_all",
                    return_value=pd.DataFrame()), \
             patch("atlas.infrastructure.margin_data.fetch_tpex_margin_all",
                    return_value=pd.DataFrame()), \
             patch("atlas.infrastructure.taifex_data.fetch_put_call_ratio",
                    return_value={}):
            result = await svc.calculate(MarketType.TW)
            assert hasattr(result, "level")
            assert hasattr(result, "index_value")
            assert hasattr(result, "components")

            # get_current 回傳快取
            current = await svc.get_current(MarketType.TW)
            assert current.index_value == result.index_value

            # get_history 回傳空 list
            history = await svc.get_history(
                MarketType.TW, date(2026, 1, 1), date(2026, 1, 31)
            )
            assert history == []
