"""atlas/models/market_env.py — 市場環境相關資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from atlas.enums import MarketType, RegimeState, SentimentLevel


@dataclass(frozen=True)
class MarketRegimeResult:
    """大盤環境判定結果（FR-MKT-01）。

    Attributes:
        market: 市場類型
        regime: 趨勢三態
        ma_alignment: 均線排列描述（如 'MA8 > MA21 > MA55 > MA89'）
        breadth_score: 市場寬度分數 (0-100)
        trend_strength: 趨勢強度 (-100 到 +100)
        previous_regime: 前一次判定結果
        changed: 是否發生狀態轉換
        detail: 判定邏輯細節
        calc_date: 計算日期
    """

    market: MarketType
    regime: RegimeState
    ma_alignment: str
    breadth_score: float
    trend_strength: float
    previous_regime: RegimeState | None = None
    changed: bool = False
    detail: str = ""
    calc_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class SentimentResult:
    """市場情緒計算結果（FR-MKT-02）。

    Attributes:
        market: 市場類型
        level: 情緒等級
        index_value: 情緒指數 (0-100)
        components: 組成因子分數明細
        position_cap: 因情緒連動的倉位上限（%）
        risk_pct_adj: 因情緒連動的單筆風險%
        previous_level: 前一次情緒等級
        shifted: 是否發生等級轉換
        calc_date: 計算日期
    """

    market: MarketType
    level: SentimentLevel
    index_value: float
    components: dict[str, float] = field(default_factory=dict)
    position_cap: float = 1.0
    risk_pct_adj: float = 0.02
    previous_level: SentimentLevel | None = None
    shifted: bool = False
    calc_date: date = field(default_factory=date.today)
