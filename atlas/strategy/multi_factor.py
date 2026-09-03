"""多因子組合策略引擎 — 預設策略 + z-score 標準化 + 簡易回測。

提供 8 種主流多因子策略預設，支援自訂因子組合。
每個因子經 winsorize + z-score 標準化後加權求和，
依綜合分數排序選出 top N 股票。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorWeight:
    """單因子權重設定。"""

    name: str
    weight: float
    direction: int  # 1 (正向：值越大越好) 或 -1 (反向：值越小越好)
    category: str


@dataclass(frozen=True)
class MultiFactorPreset:
    """預設多因子策略。"""

    name: str  # 策略代碼
    display_name: str  # 中文名
    description: str  # 策略說明
    factors: list[tuple[str, float, int]]  # [(factor_name, weight, direction)]
    rebalance_freq: str  # "monthly" / "weekly" / "quarterly"
    top_n: int  # 選前 N 檔


@dataclass
class MultiFactorResult:
    """多因子計算結果。"""

    strategy_name: str
    description: str
    weights: list[FactorWeight]
    composite_scores: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    top_picks: list[str] = field(default_factory=list)
    backtest_summary: dict | None = None


# ---------------------------------------------------------------------------
# 8 個預設策略
# ---------------------------------------------------------------------------

_PRESETS: list[MultiFactorPreset] = [
    MultiFactorPreset(
        name="value_investing",
        display_name="價值投資",
        description="聚焦低估值股票，買入低本益比、低股價淨值比、高殖利率標的，"
        "適合穩健型投資人長期持有。",
        factors=[("per", 0.4, -1), ("pbr", 0.3, -1), ("dividend_yield", 0.3, 1)],
        rebalance_freq="monthly",
        top_n=20,
    ),
    MultiFactorPreset(
        name="momentum",
        display_name="動能策略",
        description="追蹤價格動能，買入近期漲幅領先且量能放大的股票，"
        "適合趨勢行情中短線操作。",
        factors=[
            ("momentum_60d", 0.4, 1),
            ("momentum_20d", 0.3, 1),
            ("volume_breakout", 0.3, 1),
        ],
        rebalance_freq="weekly",
        top_n=15,
    ),
    MultiFactorPreset(
        name="quality_growth",
        display_name="品質成長",
        description="選擇營收持續成長、毛利率穩定的高品質成長股，"
        "兼顧估值合理性，適合中長線布局。",
        factors=[
            ("revenue_growth", 0.3, 1),
            ("gross_margin_stability", 0.3, 1),
            ("revenue_momentum", 0.2, 1),
            ("per", 0.2, -1),
        ],
        rebalance_freq="monthly",
        top_n=20,
    ),
    MultiFactorPreset(
        name="institutional_follow",
        display_name="法人追蹤",
        description="跟隨法人連續買超方向，結合主力吸貨階段判斷，"
        "適合想搭法人順風車的投資人。",
        factors=[
            ("foreign_net_buy", 0.35, 1),
            ("investment_trust_buy", 0.35, 1),
            ("smart_money_phase", 0.3, 1),
        ],
        rebalance_freq="weekly",
        top_n=15,
    ),
    MultiFactorPreset(
        name="technical_breakout",
        display_name="技術突破",
        description="偵測均線多頭排列、量能突破、MACD 翻多的技術面強勢股，"
        "適合技術分析導向的短線交易。",
        factors=[
            ("ma_alignment", 0.3, 1),
            ("volume_breakout", 0.3, 1),
            ("macd_trend", 0.2, 1),
            ("momentum_20d", 0.2, 1),
        ],
        rebalance_freq="weekly",
        top_n=15,
    ),
    MultiFactorPreset(
        name="mean_reversion",
        display_name="均值回歸",
        description="買入超跌但基本面穩健的優質股，等待價格回歸合理區間，"
        "適合逆勢佈局有耐心的投資人。",
        factors=[
            ("rsi_reversion", 0.4, 1),
            ("pbr", 0.3, -1),
            ("dividend_yield", 0.3, 1),
        ],
        rebalance_freq="monthly",
        top_n=20,
    ),
    MultiFactorPreset(
        name="multi_factor_composite",
        display_name="多因子綜合",
        description="均衡配置動能、法人、技術、估值、成長、量能六類因子，"
        "降低單一因子失效風險，適合追求穩定超額報酬。",
        factors=[
            ("momentum_60d", 0.2, 1),
            ("foreign_net_buy", 0.2, 1),
            ("ma_alignment", 0.2, 1),
            ("per", 0.15, -1),
            ("revenue_growth", 0.15, 1),
            ("volume_breakout", 0.1, 1),
        ],
        rebalance_freq="monthly",
        top_n=20,
    ),
    MultiFactorPreset(
        name="high_dividend_defense",
        display_name="高股息防禦",
        description="防禦型策略，重壓高殖利率與毛利穩定股，輔以超跌篩選，"
        "適合空頭市場或保守型資金配置。",
        factors=[
            ("dividend_yield", 0.4, 1),
            ("gross_margin_stability", 0.3, 1),
            ("rsi_reversion", 0.3, 1),
        ],
        rebalance_freq="quarterly",
        top_n=15,
    ),
]

# 因子名稱 → category 對照
_FACTOR_CATEGORIES: dict[str, str] = {
    "per": "估值",
    "pbr": "估值",
    "dividend_yield": "股利",
    "momentum_60d": "動能",
    "momentum_20d": "動能",
    "volume_breakout": "量能",
    "revenue_growth": "成長",
    "gross_margin_stability": "品質",
    "revenue_momentum": "成長",
    "foreign_net_buy": "籌碼",
    "investment_trust_buy": "籌碼",
    "smart_money_phase": "籌碼",
    "ma_alignment": "技術",
    "macd_trend": "技術",
    "rsi_reversion": "技術",
}


class MultiFactorEngine:
    """多因子組合策略引擎。"""

    def __init__(self) -> None:
        self._presets: dict[str, MultiFactorPreset] = {}
        self._register_presets()

    # ------------------------------------------------------------------
    # 公開方法
    # ------------------------------------------------------------------

    def get_preset(self, name: str) -> MultiFactorPreset:
        """取得預設策略。"""
        if name not in self._presets:
            raise KeyError(f"找不到預設策略: {name}")
        return self._presets[name]

    def list_presets(self) -> list[MultiFactorPreset]:
        """列出所有預設策略。"""
        return list(self._presets.values())

    def compute_composite(
        self,
        preset_name: str,
        factor_values: dict[str, pd.Series],
    ) -> MultiFactorResult:
        """計算多因子綜合分數。

        1. 每個因子 z-score 標準化（winsorize 1%/99%）
        2. 依 direction 調整方向
        3. 加權求和
        4. 排名取 top_n
        """
        preset = self.get_preset(preset_name)

        weights: list[FactorWeight] = []
        scored_parts: list[pd.Series] = []

        for factor_name, weight, direction in preset.factors:
            category = _FACTOR_CATEGORIES.get(factor_name, "其他")
            fw = FactorWeight(
                name=factor_name,
                weight=weight,
                direction=direction,
                category=category,
            )
            weights.append(fw)

            if factor_name not in factor_values:
                logger.warning("因子 %s 資料缺失，跳過", factor_name)
                continue

            raw = factor_values[factor_name]
            z = self._zscore(raw)
            scored_parts.append(z * direction * weight)

        if not scored_parts:
            return MultiFactorResult(
                strategy_name=preset.display_name,
                description=preset.description,
                weights=weights,
                composite_scores=pd.Series(dtype=float),
                top_picks=[],
            )

        # 合併所有因子（outer join → 缺值補 0）
        combined = pd.concat(scored_parts, axis=1).fillna(0).sum(axis=1)
        combined = combined.sort_values(ascending=False)

        top_picks = self.rank_stocks(combined, preset.top_n)

        return MultiFactorResult(
            strategy_name=preset.display_name,
            description=preset.description,
            weights=weights,
            composite_scores=combined,
            top_picks=top_picks,
        )

    def rank_stocks(
        self,
        composite_scores: pd.Series,
        top_n: int = 20,
    ) -> list[str]:
        """依綜合分數排序取前 N 檔。"""
        if composite_scores.empty:
            return []
        sorted_scores = composite_scores.sort_values(ascending=False)
        return list(sorted_scores.index[:top_n])

    def backtest_preset(
        self,
        preset_name: str,
        factor_history: dict[str, dict[str, pd.Series]],
        returns_dict: dict[str, pd.Series],
        periods: int = 12,
    ) -> dict:
        """簡易回測：每期選股 → 算等權報酬 → 統計。

        Args:
            preset_name: 預設策略名稱。
            factor_history: {date_str: {factor_name: Series(code→value)}}
            returns_dict: {date_str: Series(code→return)}
            periods: 回測期數（取前 N 期）。

        Returns:
            回測統計 dict。
        """
        preset = self.get_preset(preset_name)

        # 按時間排序取前 periods 期
        sorted_dates = sorted(factor_history.keys())[:periods]

        period_returns: list[float] = []
        prev_picks: set[str] = set()
        turnovers: list[float] = []

        for dt in sorted_dates:
            fv = factor_history[dt]
            if dt not in returns_dict:
                continue

            ret_series = returns_dict[dt]

            # 計算 composite
            result = self.compute_composite(preset_name, fv)
            picks = set(result.top_picks)

            if not picks:
                continue

            # 等權報酬
            pick_returns = ret_series.reindex(list(picks)).dropna()
            if pick_returns.empty:
                period_returns.append(0.0)
            else:
                period_returns.append(float(pick_returns.mean()))

            # 換手率
            if prev_picks:
                overlap = len(picks & prev_picks)
                turnover = 1 - overlap / max(len(picks), 1)
                turnovers.append(turnover)
            prev_picks = picks

        if not period_returns:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "avg_turnover": 0.0,
                "period_returns": [],
            }

        # 統計
        ret_arr = np.array(period_returns)
        total_return = float(np.prod(1 + ret_arr / 100) - 1) * 100
        n_periods = len(ret_arr)

        # 年化（假設月度 12 期 = 1 年）
        if n_periods > 0 and total_return > -100:
            annualized = (
                ((1 + total_return / 100) ** (12 / n_periods)) - 1
            ) * 100
        else:
            annualized = -100.0

        win_rate = float(np.mean(ret_arr > 0))

        # 最大回撤
        cumulative = np.cumprod(1 + ret_arr / 100)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - peak) / peak * 100
        max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Sharpe ratio（假設無風險利率 0）
        mean_ret = float(np.mean(ret_arr))
        std_ret = float(np.std(ret_arr, ddof=1)) if len(ret_arr) > 1 else 0.0
        sharpe = mean_ret / std_ret if std_ret > 1e-8 else 0.0

        avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0

        return {
            "total_return": round(total_return, 4),
            "annualized_return": round(annualized, 4),
            "win_rate": round(win_rate, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe, 4),
            "avg_turnover": round(avg_turnover, 4),
            "period_returns": [round(r, 4) for r in period_returns],
        }

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _register_presets(self) -> None:
        """註冊所有預設策略。"""
        for p in _PRESETS:
            self._presets[p.name] = p

    @staticmethod
    def _zscore(series: pd.Series) -> pd.Series:
        """Z-score 標準化（去極端值：winsorize 1%/99%）。"""
        s = series.dropna()
        if len(s) < 2:
            return pd.Series(0.0, index=series.index)

        lower = float(s.quantile(0.01))
        upper = float(s.quantile(0.99))
        clipped = s.clip(lower, upper)

        mean = float(clipped.mean())
        std = float(clipped.std(ddof=1))

        if std < 1e-8:
            return pd.Series(0.0, index=series.index)

        result = (series.fillna(mean) - mean) / std
        return result
