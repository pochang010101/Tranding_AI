"""atlas/models/scoring.py — 評分、面向、結論資料結構。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.enums import (
    AspectVerdict,
    ConclusionLevel,
    ConfidenceLevel,
    ConflictFlag,
    MarketType,
    SignalStrength,
)


@dataclass(frozen=True)
class AxisScore:
    """四大主軸評分結果（FR-SEL-01）。

    四主軸：產業輪動 / 題材催化 / 資金流向 / 個股 RS 優於大盤。
    各軸 0-100 分，加權合成「主軸總分」。

    Attributes:
        code: 股票代碼
        industry_rotation: 產業輪動強度分數 (0-100)
        catalyst: 題材催化事件分數 (0-100)
        fund_flow: 資金流向方向分數 (0-100)
        relative_strength: 個股 RS 優於大盤分數 (0-100)
        weights: 四主軸權重 (預設等權 [0.25, 0.25, 0.25, 0.25])
        total_score: 加權總分
        calc_date: 計算日期
    """

    code: str
    industry_rotation: float
    catalyst: float
    fund_flow: float
    relative_strength: float
    weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
    total_score: float = 0.0
    calc_date: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        if not isinstance(self.total_score, property):
            w = self.weights
            score = (
                self.industry_rotation * w[0]
                + self.catalyst * w[1]
                + self.fund_flow * w[2]
                + self.relative_strength * w[3]
            )
            object.__setattr__(self, "total_score", round(score, 2))


@dataclass(frozen=True)
class AspectResult:
    """三大面向評估結果（FR-SEL-02）。

    三面向：技術面 / 基本面 / 籌碼面。
    各面向輸出「正/中性/負」三態。
    硬性規則：至少兩面向為正才納入候選。

    Attributes:
        code: 股票代碼
        technical: 技術面判定
        fundamental: 基本面判定
        institutional: 籌碼面判定
        technical_detail: 技術面細項分數
        fundamental_detail: 基本面細項分數
        institutional_detail: 籌碼面細項分數
        is_qualified: 是否通過（>=2 面向為正）
        rejection_reason: 未通過原因
        calc_date: 計算日期
    """

    code: str
    technical: AspectVerdict
    fundamental: AspectVerdict
    institutional: AspectVerdict
    technical_detail: dict[str, float] = field(default_factory=dict)
    fundamental_detail: dict[str, float] = field(default_factory=dict)
    institutional_detail: dict[str, float] = field(default_factory=dict)
    is_qualified: bool = False
    rejection_reason: str = ""
    calc_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class ScanResult:
    """選股掃描結果（FR-SEL-03）。

    Attributes:
        code: 股票代碼
        name: 股票名稱
        market: 市場類型
        axis_score: 四主軸評分
        aspect: 三面向結果
        conclusion: 結論等級
        original_conclusion: 降級前原始等級
        downgrade_reasons: 降級原因列表
        auxiliary_confidence: 輔助確認信心度（七流派/ML/SMC）
        ml_prediction: ML 預測方向（True=看多）
        smc_confirmed: SMC 結構是否確認
        rank: 排名
        scan_date: 掃描日期
    """

    code: str
    name: str
    market: MarketType
    axis_score: AxisScore
    aspect: AspectResult
    conclusion: ConclusionLevel
    original_conclusion: ConclusionLevel
    downgrade_reasons: list[str] = field(default_factory=list)
    auxiliary_confidence: ConfidenceLevel = ConfidenceLevel.NA
    ml_prediction: bool | None = None
    smc_confirmed: bool | None = None
    rank: int = 0
    scan_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class ConclusionResult:
    """結論引擎輸出（FR-RSK-01 + FR-RSK-02）。

    Attributes:
        code: 股票代碼
        market: 市場類型
        raw_level: 原始結論等級（未降級）
        final_level: 最終結論等級（經三層降級 + 衝突降級）
        signal_strength: 訊號強度（方向閘門 × 動能分級）
        conflict_flags: 衝突標記列表（任一觸發 → 額外降一級）
        downgrade_sources: 降級原因追溯列表（如 "大盤空頭-1", "衝突:逆勢-1"）
        regime_downgrade: 大盤降級幅度（0 或 -1）
        sentiment_downgrade: 情緒降級幅度（0 或 -1）
        industry_downgrade: 產業勝率降級幅度（0 或 -1）
        conflict_downgrade: 衝突降級幅度（0 或 -1）
        scoring_detail: 各項評分明細
        timestamp: 計算時間
    """

    code: str
    market: MarketType
    raw_level: ConclusionLevel
    final_level: ConclusionLevel
    signal_strength: SignalStrength = SignalStrength.NEUTRAL
    conflict_flags: tuple[ConflictFlag, ...] = ()
    downgrade_sources: tuple[str, ...] = ()
    regime_downgrade: int = 0
    sentiment_downgrade: int = 0
    industry_downgrade: int = 0
    conflict_downgrade: int = 0
    scoring_detail: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
