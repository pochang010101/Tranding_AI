"""投資因子策略庫 — 18 個主流量化因子定義與計算。

涵蓋價值型、動能型、技術型、籌碼型、品質型、產業型六大類別，
每個因子提供 compute_factor 方法回傳 pd.Series（index=日期）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)


class FactorCategory(Enum):
    VALUE = "價值型"
    MOMENTUM = "動能型"
    TECHNICAL = "技術型"
    INSTITUTIONAL = "籌碼型"
    QUALITY = "品質型"
    INDUSTRY = "產業型"


@dataclass(frozen=True)
class FactorDefinition:
    """因子定義。"""

    name: str                    # 因子代碼 e.g. "PER_low"
    display_name: str            # 中文名 e.g. "低本益比"
    category: FactorCategory
    description: str             # 策略說明
    direction: int               # 1=值越大越好, -1=值越小越好
    benchmark: str               # 參考基準說明


# ── 因子策略庫 ─────────────────────────────────────


class FactorStrategyLibrary:
    """主流量化因子策略庫 — 18 個因子定義與計算。"""

    def __init__(self) -> None:
        self._factors: dict[str, FactorDefinition] = {}
        self._ind = IndicatorLibrary()
        self._register_all()

    def _register_all(self) -> None:
        """註冊所有因子。"""
        defs = [
            # ── 價值型 (direction=-1) ──
            FactorDefinition(
                "PER_low", "低本益比", FactorCategory.VALUE,
                "本益比倒數，越高代表越便宜", -1, "大盤平均 PE",
            ),
            FactorDefinition(
                "PBR_low", "低股淨比", FactorCategory.VALUE,
                "股價淨值比倒數，越高代表越便宜", -1, "大盤平均 PB",
            ),
            FactorDefinition(
                "DY_high", "高殖利率", FactorCategory.VALUE,
                "現金殖利率，越高越好", 1, "定存利率 1.5%",
            ),
            # ── 動能型 (direction=1) ──
            FactorDefinition(
                "MOM_20d", "20日動能", FactorCategory.MOMENTUM,
                "近 20 個交易日報酬率", 1, "大盤同期漲幅",
            ),
            FactorDefinition(
                "MOM_60d", "60日動能", FactorCategory.MOMENTUM,
                "近 60 個交易日報酬率", 1, "大盤同期漲幅",
            ),
            FactorDefinition(
                "MOM_120d", "120日動能", FactorCategory.MOMENTUM,
                "近 120 個交易日報酬率", 1, "大盤同期漲幅",
            ),
            FactorDefinition(
                "REV_MOM", "營收動能", FactorCategory.MOMENTUM,
                "月營收 YoY 成長率", 1, "產業平均 YoY",
            ),
            # ── 技術型 ──
            FactorDefinition(
                "MA_ALIGN", "均線排列分數", FactorCategory.TECHNICAL,
                "MA8>MA21>MA55 = 3 分，MA8>MA21 = 2 分", 1, "多頭排列 = 3",
            ),
            FactorDefinition(
                "RSI_REVERT", "RSI均值回歸", FactorCategory.TECHNICAL,
                "RSI 偏離 50 的絕對值，越小代表越中性", -1, "RSI = 50（中性）",
            ),
            FactorDefinition(
                "VOL_BREAK", "量能突破", FactorCategory.TECHNICAL,
                "成交量 / 20日均量比值", 1, "1.0 為平均量",
            ),
            FactorDefinition(
                "MACD_TREND", "MACD趨勢", FactorCategory.TECHNICAL,
                "MACD histogram 近 5 日斜率", 1, "正值代表動能增強",
            ),
            # ── 籌碼型 (direction=1) ──
            FactorDefinition(
                "FOREIGN_STREAK", "外資連買天數", FactorCategory.INSTITUTIONAL,
                "外資連續買入天數（正=連買、負=連賣）", 1, "連買 5 日以上為強勢",
            ),
            FactorDefinition(
                "TRUST_STREAK", "投信連買天數", FactorCategory.INSTITUTIONAL,
                "投信連續買入天數", 1, "連買 3 日以上為關注",
            ),
            FactorDefinition(
                "SMART_MONEY", "主力階段分數", FactorCategory.INSTITUTIONAL,
                "accumulation=3, markup=2, shakeout=1, distribution=0",
                1, "吸貨期 = 3",
            ),
            FactorDefinition(
                "MARGIN_RATIO", "券資比", FactorCategory.INSTITUTIONAL,
                "融券餘額 / 融資餘額，>30% 可能軋空", 1, "30% 為軋空門檻",
            ),
            # ── 品質型 (direction=1) ──
            FactorDefinition(
                "GM_STABLE", "毛利率穩定度", FactorCategory.QUALITY,
                "近 4 季毛利率平均 / 標準差（Sharpe-like）", 1, "越高代表越穩定",
            ),
            FactorDefinition(
                "REV_GROWTH", "營收成長率", FactorCategory.QUALITY,
                "最近季營收 YoY 成長率", 1, "正成長為基本門檻",
            ),
            # ── 產業型 (direction=1) ──
            FactorDefinition(
                "SECTOR_RS", "產業相對強弱", FactorCategory.INDUSTRY,
                "個股所屬產業近 20 日 RS vs 大盤", 1, "正值代表強於大盤",
            ),
        ]
        for fd in defs:
            self._factors[fd.name] = fd

    def get_all(self) -> list[FactorDefinition]:
        """取得所有因子定義。"""
        return list(self._factors.values())

    def get_by_category(self, cat: FactorCategory) -> list[FactorDefinition]:
        """依類別取得因子。"""
        return [f for f in self._factors.values() if f.category == cat]

    def get(self, name: str) -> FactorDefinition | None:
        """依名稱取得因子定義。"""
        return self._factors.get(name)

    def compute_factor(
        self,
        name: str,
        ohlcv_df: pd.DataFrame,
        fundamentals: dict[str, Any] | None = None,
        flow_data: dict[str, Any] | None = None,
    ) -> pd.Series:
        """計算單一因子值（回傳 Series，index 為日期）。

        Args:
            name: 因子代碼
            ohlcv_df: OHLCV DataFrame（需含 date/close/volume 等欄位）
            fundamentals: 基本面資料 dict（PE、PB、dividend_yield 等）
            flow_data: 籌碼資料 dict（foreign_streak、trust_streak 等）

        Returns:
            pd.Series，NaN 代表資料不足。
        """
        compute_map = {
            "PER_low": self._compute_per_low,
            "PBR_low": self._compute_pbr_low,
            "DY_high": self._compute_dy_high,
            "MOM_20d": lambda df, f, fl: self._compute_momentum(df, 20),
            "MOM_60d": lambda df, f, fl: self._compute_momentum(df, 60),
            "MOM_120d": lambda df, f, fl: self._compute_momentum(df, 120),
            "REV_MOM": self._compute_rev_mom,
            "MA_ALIGN": self._compute_ma_align,
            "RSI_REVERT": self._compute_rsi_revert,
            "VOL_BREAK": self._compute_vol_break,
            "MACD_TREND": self._compute_macd_trend,
            "FOREIGN_STREAK": self._compute_foreign_streak,
            "TRUST_STREAK": self._compute_trust_streak,
            "SMART_MONEY": self._compute_smart_money,
            "MARGIN_RATIO": self._compute_margin_ratio,
            "GM_STABLE": self._compute_gm_stable,
            "REV_GROWTH": self._compute_rev_growth,
            "SECTOR_RS": self._compute_sector_rs,
        }
        fn = compute_map.get(name)
        if fn is None:
            logger.warning("未知因子: %s", name)
            return pd.Series(dtype=float)
        try:
            return fn(ohlcv_df, fundamentals or {}, flow_data or {})
        except Exception:
            logger.exception("計算因子 %s 失敗", name)
            return pd.Series(dtype=float)

    # ── 價值型計算 ──────────────────────────────────

    def _compute_per_low(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        pe = fund.get("pe_ratio")
        if pe and pe > 0:
            val = 1.0 / pe
            return pd.Series(val, index=df.get("date", df.index))
        return pd.Series(np.nan, index=df.get("date", df.index))

    def _compute_pbr_low(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        pb = fund.get("pb_ratio")
        if pb and pb > 0:
            val = 1.0 / pb
            return pd.Series(val, index=df.get("date", df.index))
        return pd.Series(np.nan, index=df.get("date", df.index))

    def _compute_dy_high(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        dy = fund.get("dividend_yield", np.nan)
        return pd.Series(dy, index=df.get("date", df.index))

    # ── 動能型計算 ──────────────────────────────────

    def _compute_momentum(self, df: pd.DataFrame, period: int) -> pd.Series:
        close = df["close"]
        mom = close / close.shift(period) - 1
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(mom.values, index=idx)

    def _compute_rev_mom(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        rev_yoy = fund.get("revenue_yoy", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(rev_yoy, index=idx)

    # ── 技術型計算 ──────────────────────────────────

    def _compute_ma_align(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        close = df["close"]
        ma8 = self._ind.moving_average(close, 8)
        ma21 = self._ind.moving_average(close, 21)
        ma55 = self._ind.moving_average(close, 55)

        score = pd.Series(0.0, index=close.index)
        score = score.where(~(ma8 > ma21), 2.0)
        score = score.where(~((ma8 > ma21) & (ma21 > ma55)), 3.0)
        # MA8 < MA21 但 close > MA55 → 1 分
        score = score.where(~((score == 0.0) & (close > ma55)), 1.0)

        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(score.values, index=idx)

    def _compute_rsi_revert(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        rsi = self._ind.rsi(df["close"], 14)
        deviation = (rsi - 50).abs()
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(deviation.values, index=idx)

    def _compute_vol_break(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        vol = df["volume"].astype(float)
        ma20_vol = vol.rolling(20).mean()
        ratio = vol / ma20_vol.replace(0, np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(ratio.values, index=idx)

    def _compute_macd_trend(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        _, _, hist = self._ind.macd(df["close"])
        # 近 5 日斜率（線性回歸）
        slope = hist.rolling(5).apply(self._linreg_slope, raw=True)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(slope.values, index=idx)

    @staticmethod
    def _linreg_slope(arr: np.ndarray) -> float:
        """簡易線性回歸斜率。"""
        n = len(arr)
        if n < 2:
            return np.nan
        x = np.arange(n, dtype=float)
        x_mean = x.mean()
        y_mean = arr.mean()
        denom = ((x - x_mean) ** 2).sum()
        if denom == 0:
            return 0.0
        return float(((x - x_mean) * (arr - y_mean)).sum() / denom)

    # ── 籌碼型計算 ──────────────────────────────────

    def _compute_foreign_streak(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        streak = flow.get("foreign_streak", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(streak, index=idx)

    def _compute_trust_streak(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        streak = flow.get("trust_streak", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(streak, index=idx)

    def _compute_smart_money(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        phase = flow.get("smart_money_phase", "")
        phase_score = {
            "accumulation": 3, "shakeout": 1, "markup": 2, "distribution": 0,
        }
        val = phase_score.get(phase, np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(val, index=idx)

    def _compute_margin_ratio(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        ratio = flow.get("margin_ratio", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(ratio, index=idx)

    # ── 品質型計算 ──────────────────────────────────

    def _compute_gm_stable(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        gm_list = fund.get("gross_margins", [])
        idx = df["date"] if "date" in df.columns else df.index
        if not gm_list or len(gm_list) < 2:
            return pd.Series(np.nan, index=idx)
        arr = np.array(gm_list, dtype=float)
        mean_gm = float(np.mean(arr))
        std_gm = float(np.std(arr, ddof=1))
        val = mean_gm / std_gm if std_gm > 0 else 0.0
        return pd.Series(val, index=idx)

    def _compute_rev_growth(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        growth = fund.get("revenue_growth", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(growth, index=idx)

    # ── 產業型計算 ──────────────────────────────────

    def _compute_sector_rs(
        self, df: pd.DataFrame, fund: dict, flow: dict
    ) -> pd.Series:
        sector_rs = flow.get("sector_rs", np.nan)
        idx = df["date"] if "date" in df.columns else df.index
        return pd.Series(sector_rs, index=idx)
