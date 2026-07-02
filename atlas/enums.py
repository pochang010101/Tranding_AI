"""atlas/enums.py — 全系統列舉定義。"""

from __future__ import annotations

from enum import IntEnum, StrEnum, auto


class MarketType(StrEnum):
    """支援的市場類型。"""

    TW = "TW"  # 台股 TWSE/TPEx
    US = "US"  # 美股 NYSE/NASDAQ


class RegimeState(StrEnum):
    """大盤趨勢三態，用於全系統風控連動（FR-MKT-01）。"""

    BULL = "BULL"    # 多頭：均線多頭排列 + 市場寬度正向
    RANGE = "RANGE"  # 盤整：無明確方向
    BEAR = "BEAR"    # 空頭：均線空頭排列 + 市場寬度負向


class SentimentLevel(StrEnum):
    """市場情緒五級（FR-MKT-02），映射 0-100 情緒指數。"""

    EXTREME_GREED = "EXTREME_GREED"  # 80-100：極度貪婪
    GREED = "GREED"                  # 60-79：貪婪
    NEUTRAL = "NEUTRAL"              # 40-59：中性
    FEAR = "FEAR"                    # 20-39：恐懼
    EXTREME_FEAR = "EXTREME_FEAR"    # 0-19：極度恐懼


class ConclusionLevel(IntEnum):
    """結論七級評等（FR-RSK-01），數值越高越偏多方。

    Lv5=優先進場，Lv0=觀望，Lv-2=空/出場。
    三層降級（大盤/情緒/產業勝率）會使等級下修。
    """

    LV5 = 5       # 優先進場
    LV4 = 4       # 積極做多
    LV3 = 3       # 可進場
    LV2 = 2       # 保守做多
    LV1 = 1       # 觀望偏多
    LV0 = 0       # 觀望
    LV_NEG1 = -1  # 偏空/減碼
    LV_NEG2 = -2  # 空/出場


class SignalType(StrEnum):
    """交易訊號類型（FR-RAD-02）。"""

    BUY = "BUY"          # 買入信號（B1/B2/B3）
    SELL = "SELL"        # 賣出信號（S1/S2/S3）
    NEUTRAL = "NEUTRAL"  # 中性，無明確方向
    ALERT = "ALERT"      # 警示（非買賣，僅提醒）


class DetectorType(StrEnum):
    """11 即時偵測器類型（FR-RAD-01）。"""

    INDUSTRY_SURGE = "INDUSTRY_SURGE"        # 產業急拉
    LARGE_ORDER = "LARGE_ORDER"              # 大單異常
    VOLUME_BREAKOUT = "VOLUME_BREAKOUT"      # 爆量啟動
    LAUNCH_TRIGGER = "LAUNCH_TRIGGER"        # 起漲觸發
    MA_BREAK = "MA_BREAK"                    # 均線跌破
    SHAKEOUT_RECOVER = "SHAKEOUT_RECOVER"    # 甩轎回穩
    DISTRIBUTION_WARN = "DISTRIBUTION_WARN"  # 出貨預警
    VOLUME_DIVERGE = "VOLUME_DIVERGE"        # 價量背離
    SPIKE = "SPIKE"                          # 急拉急殺
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"      # 流動性掃單（SMC）
    OB_RETEST = "OB_RETEST"                  # Order Block 回測（SMC）


class StrategyCategory(StrEnum):
    """22 日 K 策略分類（FR-STR-01）。"""

    O_SERIES = "O_SERIES"    # 隔日沖策略 (5 個)
    S_SERIES = "S_SERIES"    # 波段策略 (6 個)
    K_SERIES = "K_SERIES"    # 扣抵策略 (3 個)
    P_SERIES = "P_SERIES"    # 型態策略 (4 個)
    T_SERIES = "T_SERIES"    # 指標策略 (2 個)
    SD_SERIES = "SD_SERIES"  # 空頭策略 (4 個，蕭明道系列)


class TimeFrame(StrEnum):
    """K 線時間週期。"""

    DAILY = "DAILY"              # 日 K
    WEEKLY = "WEEKLY"            # 週 K
    MONTHLY = "MONTHLY"          # 月 K
    INTRADAY_1M = "INTRADAY_1M"  # 1 分 K
    INTRADAY_5M = "INTRADAY_5M"  # 5 分 K
    INTRADAY_TICK = "INTRADAY_TICK"  # Tick


class BacktestStatus(StrEnum):
    """回測任務狀態（FR-BKT-01）。"""

    PENDING = "PENDING"      # 排隊中
    RUNNING = "RUNNING"      # 執行中
    COMPLETED = "COMPLETED"  # 完成
    FAILED = "FAILED"        # 失敗


class WatchlistStatus(StrEnum):
    """觀察清單狀態（UC-010 持倉管理）。"""

    WATCHING = "WATCHING"  # 觀察中
    READY = "READY"        # 條件到位，待進場
    ENTERED = "ENTERED"    # 已進場
    EXITED = "EXITED"      # 已出場


class AspectVerdict(StrEnum):
    """三大面向判定結果（FR-SEL-02）。"""

    POSITIVE = "POSITIVE"  # 正面
    NEUTRAL = "NEUTRAL"    # 中性
    NEGATIVE = "NEGATIVE"  # 負面


class DataSourceHealth(StrEnum):
    """資料源健康狀態。"""

    HEALTHY = "HEALTHY"      # 正常
    DEGRADED = "DEGRADED"    # 降級（延遲增加）
    UNHEALTHY = "UNHEALTHY"  # 不健康（已 Fallback）


class ConfidenceLevel(StrEnum):
    """輔助信心度（FR-SEL-04）。"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NA = "N/A"  # 無法計算
