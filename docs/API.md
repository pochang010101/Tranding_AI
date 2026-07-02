# Atlas Trading System — API Reference

> 版本：v5.0 | 語言：Python 3.14 | 框架：Streamlit 1.58

---

## 目錄

1. [Service Container — 資料取得函式](#1-service-container--資料取得函式)
2. [IndicatorLibrary — 技術指標計算](#2-indicatorlibrary--技術指標計算)
3. [ScoringEngine — 四主軸三面向評分](#3-scoringengine--四主軸三面向評分)
4. [SMCModule — Smart Money Concepts 分析](#4-smcmodule--smart-money-concepts-分析)
5. [BacktestEngine — 歷史回測](#5-backtestengine--歷史回測)
6. [MonteCarloSimulator — 蒙地卡羅模擬](#6-montecarlosimulator--蒙地卡羅模擬)

---

## 1. Service Container — 資料取得函式

檔案：`atlas/presentation/service_container.py`

這些函式供 Streamlit 頁面直接呼叫，內建 `st.cache_data` 快取，所有快取跨 Streamlit session 共用。

---

### `fetch_stock_data(code, period)`

以 yfinance 取得台股／美股歷史 K 線資料。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | 必填 | 股票代碼（台股 4-6 碼數字；美股 1-5 碼字母） |
| `period` | `str` | `"6mo"` | yfinance 期間字串，如 `"1mo"` `"3mo"` `"6mo"` `"1y"` `"2y"` |

**快取 TTL：600 秒（10 分鐘）**

**回傳：`pd.DataFrame`**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `open` | `float` | 開盤價 |
| `high` | `float` | 最高價 |
| `low` | `float` | 最低價 |
| `close` | `float` | 收盤價 |
| `volume` | `float` | 成交量（股數） |

- Index 為 `DatetimeIndex`（UTC）
- 台股上市股自動加 `.TW` 後綴，上櫃股加 `.TWO`
- 若取得失敗或無資料，回傳空 `pd.DataFrame()`

---

### `fetch_stock_quote(code)`

取得即時報價。台股優先使用 TWSE MIS API，失敗時 fallback 至 yfinance。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | 必填 | 股票代碼 |

**快取 TTL：300 秒（5 分鐘）**

**回傳：`dict[str, Any]`**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `price` | `float` | 最新成交價（非交易時段 fallback 昨收） |
| `prev_close` | `float` | 昨日收盤價 |
| `open` | `float` | 今日開盤價 |
| `day_high` | `float` | 今日最高價 |
| `day_low` | `float` | 今日最低價 |
| `volume` | `int` | 今日成交量（股數；TWSE 張數 × 1000） |
| `source` | `str` | 資料來源：`"twse_mis"` / `"yfinance"` / `"error"` |

**Fallback 規則：**
- TWSE MIS 的 `z`（成交價）為 `"-"` 時，改用 `y`（昨收）
- `price == 0` 視為失敗，觸發 fallback

---

### `fetch_institutional_flow(code, days)`

取得三大法人當日買賣超（TWSE T86）。注意：`days` 參數目前保留未使用，僅取當日資料。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | 必填 | 台股代碼 |
| `days` | `int` | `5` | 保留參數（目前固定取當日） |

**快取 TTL：1800 秒（30 分鐘）**

**回傳：`dict[str, Any]`**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `foreign_net` | `int` | 外資買賣超（張） |
| `trust_net` | `int` | 投信買賣超（張） |
| `dealer_net` | `int` | 自營商買賣超（張） |
| `total_net` | `int` | 三大法人合計買賣超（張） |
| `source` | `str` | `"twse_t86"` 或 `"unavailable"` |
| `date` | `str` | 查詢日期，格式 `YYYYMMDD` |

- API 失敗時所有數值回傳 `0`，`source` 為 `"unavailable"`

---

### `fetch_margin_data(code)`

取得融資融券餘額（TWSE MI_MARGN）。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | 必填 | 台股代碼 |

**快取 TTL：1800 秒（30 分鐘）**

**回傳：`dict[str, Any]`**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `margin_balance` | `int` | 融資餘額（張） |
| `margin_change` | `int` | 融資增減（張，正=增加） |
| `short_balance` | `int` | 融券餘額（張） |
| `short_change` | `int` | 融券增減（張，正=增加） |
| `source` | `str` | `"twse_margn"` 或 `"unavailable"` |

- API 失敗時所有數值回傳 `0`，`source` 為 `"unavailable"`

---

### `fetch_financials(code)`

取得個股基本面資料（來源：yfinance `ticker.info` + `quarterly_financials`）。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | 必填 | 股票代碼 |

**快取 TTL：3600 秒（1 小時）**

**回傳：`dict[str, Any]`**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `eps` | `float \| None` | 每股盈餘（trailing EPS，無則 forward EPS） |
| `gross_margin` | `float \| None` | 毛利率（%，取最新一季） |
| `operating_margin` | `float \| None` | 營業利益率（%，取最新一季） |
| `revenue` | `int \| None` | 最新一季營業收入（原幣別） |
| `pe_ratio` | `float \| None` | 本益比（trailing P/E，無則 forward P/E） |
| `pb_ratio` | `float \| None` | 股價淨值比 |

- 任何欄位取得失敗均回傳 `None`，不拋出例外

---

### Service Container 單例工廠函式

以下函式以 `st.cache_resource` 維持全域單例，整個 Streamlit 應用程式只建立一個實例：

| 函式 | 回傳型別 | 說明 |
|------|----------|------|
| `get_indicator_lib()` | `IndicatorLibrary` | 技術指標庫 |
| `get_scoring_engine()` | `ScoringEngine` | 評分引擎 |
| `get_smc_module()` | `SMCModule` | SMC 分析模組 |
| `get_monte_carlo()` | `MonteCarloSimulator` | 蒙地卡羅模擬器 |
| `get_backtest_engine()` | `BacktestEngine` | 回測引擎 |
| `get_conclusion_engine()` | `ConclusionEngine` | 綜合結論引擎 |
| `get_portfolio_manager()` | `PortfolioManager` | 投資組合管理 |
| `get_trading_calendar()` | `TradingCalendar` | 交易日曆 |
| `get_notification_hub()` | `NotificationHub` | 通知中心（Discord / Telegram / LINE） |
| `get_workflow_engine()` | `WorkflowEngine` | 工作流引擎 |
| `get_scheduler()` | `Scheduler` | 自動排程器 |
| `get_ml_engine()` | `MLEngine` | 機器學習引擎（RandomForest） |
| `get_realtime_service()` | `RealtimePushService` | 即時推播服務（30 秒輪詢） |

---

## 2. IndicatorLibrary — 技術指標計算

檔案：`atlas/strategy/indicator_lib.py`
類別：`IndicatorLibrary(IIndicatorLibrary)`

純計算模組，不依賴外部 API。所有指標接受 `pd.Series` 或 `pd.DataFrame`，回傳結果同型別。

---

### `calculate_all(df, indicators)`

批次計算所有技術指標，一次呼叫即取得完整指標集。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `df` | `pd.DataFrame` | 必填 | 輸入 K 線資料，至少需含 `close` 欄位 |
| `indicators` | `list[str] \| None` | `None`（全部計算） | 指定要計算的指標子集 |

**`df` 必要欄位：**

| 欄位 | 必要 | 說明 |
|------|------|------|
| `close` | 必填 | 收盤價 |
| `high` | ATR、KD 必填 | 最高價 |
| `low` | ATR、KD 必填 | 最低價 |
| `volume` | OBV、費氏量均必填 | 成交量 |
| `open` | SMC 使用 | 開盤價 |

**`indicators` 可選值：**
`"fibonacci_ma"` / `"rsi"` / `"macd"` / `"bollinger"` / `"atr"` / `"kd"` / `"obv"`

**回傳：`pd.DataFrame`**（原始欄位 + 以下新增欄位）

| 新增欄位 | 說明 |
|----------|------|
| `MA8`, `MA21`, `MA55`, `MA89` | 費氏均線（SMA） |
| `MV5`, `MV13`, `MV34` | 費氏量均線（volume 存在時） |
| `RSI14`, `RSI6` | RSI（14 日 / 6 日） |
| `MACD`, `MACD_signal`, `MACD_hist` | MACD（12/26/9） |
| `BB_upper`, `BB_middle`, `BB_lower` | 布林通道（20 日，2σ） |
| `ATR14` | 平均真實波幅（14 日）；需要 high/low |
| `K9`, `D3` | 隨機指標 KD（9 日 K，3 日 D）；需要 high/low |
| `OBV` | 能量潮；需要 volume |

---

### 個別指標方法

| 方法 | 簽名 | 回傳 | 說明 |
|------|------|------|------|
| `moving_average` | `(series, period, ma_type="SMA")` | `pd.Series` | `ma_type`: `"SMA"` / `"EMA"` / `"WMA"` |
| `rsi` | `(series, period=14)` | `pd.Series` | Wilder's RSI（EWM alpha=1/period） |
| `macd` | `(series, fast=12, slow=26, signal=9)` | `tuple[Series, Series, Series]` | (MACD線, 訊號線, 柱狀圖) |
| `bollinger_bands` | `(series, period=20, std_dev=2.0)` | `tuple[Series, Series, Series]` | (上軌, 中軌, 下軌) |
| `atr` | `(high, low, close, period=14)` | `pd.Series` | EWM ATR |
| `stochastic` | `(high, low, close, k_period=9, d_period=3)` | `tuple[Series, Series]` | (K, D) |
| `obv` | `(close, volume)` | `pd.Series` | 能量潮累計值 |
| `fibonacci_ma` | `(df)` | `pd.DataFrame` | 費氏週期 (8/21/55/89) 均價，(5/13/34) 量均 |
| `deduction_offset` | `(series, ma_period)` | `pd.Series` | 扣抵值 = 今日 - N日前（正=均線上揚） |
| `relative_strength` | `(stock_series, benchmark_series, period=20)` | `pd.Series` | 股票 vs 基準 N 日報酬差 |
| `volume_profile` | `(df, bins=50)` | `pd.DataFrame` | 各價位成交量分布（`price_level`, `volume`，按量降序） |

---

## 3. ScoringEngine — 四主軸三面向評分

檔案：`atlas/strategy/scoring_engine.py`
類別：`ScoringEngine(IScoringEngine)`

**評分邏輯架構：**

```
四主軸（各 0-100，各佔 25% 權重）
  1. 產業輪動 (industry_rotation) — 產業 RS 排名分數
  2. 題材催化 (catalyst)          — 新聞/事件分數（待 NLP，目前固定 50）
  3. 資金流向 (fund_flow)         — 五維資金評分（見下方）
  4. 個股 RS  (relative_strength) — 個股 vs 大盤 20 日報酬差

三面向（POSITIVE / NEUTRAL / NEGATIVE）
  - 技術面：均線排列(MA8>MA21>MA55) + RSI(40-70) + MACD直方圖
  - 基本面：月營收 YoY > 10% 且 MoM > 0
  - 籌碼面：外資或投信連續買超 >= 3 日

硬性規則：至少 2 面向 POSITIVE 才 is_qualified=True
```

---

### `score_axis(code, market)` — async

計算四主軸分數。

| 參數 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼 |
| `market` | `MarketType` | `MarketType.TW` / `MarketType.US` |

**回傳：`AxisScore`**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼 |
| `industry_rotation` | `float` | 產業輪動分數 (0-100) |
| `catalyst` | `float` | 題材催化分數 (0-100) |
| `fund_flow` | `float` | 資金流向分數 (0-100) |
| `relative_strength` | `float` | 個股 RS 分數 (0-100) |
| `weights` | `tuple[float,float,float,float]` | 各主軸權重（預設均等 0.25） |
| `calc_date` | `date` | 計算日期 |

---

### `evaluate_aspects(code, market)` — async

評估三面向，判斷是否符合選股資格。

| 參數 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼 |
| `market` | `MarketType` | 市場類型 |

**回傳：`AspectResult`**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼 |
| `technical` | `AspectVerdict` | `POSITIVE` / `NEUTRAL` / `NEGATIVE` |
| `fundamental` | `AspectVerdict` | 同上 |
| `institutional` | `AspectVerdict` | 同上 |
| `technical_detail` | `dict` | `{ma_alignment, rsi14, macd_hist}` |
| `fundamental_detail` | `dict` | `{yoy, mom}`（月營收成長率 %） |
| `institutional_detail` | `dict` | `{foreign_consecutive, trust_consecutive}`（連續買超天數） |
| `is_qualified` | `bool` | 至少 2 面向 POSITIVE 時為 `True` |
| `rejection_reason` | `str` | 未達標時說明原因 |
| `calc_date` | `date` | 計算日期 |

---

### `score_batch(codes, market)` — async

批次評分（循序執行，失敗個股 log warning 後跳過）。

| 參數 | 型別 | 說明 |
|------|------|------|
| `codes` | `list[str]` | 股票代碼列表 |
| `market` | `MarketType` | 市場類型 |

**回傳：`list[tuple[AxisScore, AspectResult]]`**

---

### `get_fund_flow_score(code, market)` — async

五維資金評分明細。

**回傳：`dict[str, float]`**

| 鍵 | 說明 |
|----|------|
| `volume_anomaly` | 量能異常分數 (0-100) |
| `price_volume_match` | 價量配合分數 (0-100) |
| `relative_strength` | 相對強弱分數 (0-100) |
| `trend_continuation` | 趨勢延續分數 (0-100) |
| `institutional` | 法人分數（外資連續買超×5 + 投信×8，最高 100） |
| `total` | 五維平均分數 |

---

### `set_weights(axis_weights)` — async

調整四主軸權重。

| 參數 | 型別 | 說明 |
|------|------|------|
| `axis_weights` | `tuple[float,float,float,float]` | 依序：產業/題材/資金/RS，建議四者合計為 1.0 |

---

## 4. SMCModule — Smart Money Concepts 分析

檔案：`atlas/strategy/smc_module.py`
類別：`SMCModule(ISMCModule)`

偵測 Order Block、FVG、Liquidity Sweep、CRT，輸出市場偏向與信心分數。

---

### `analyze(code, df)`

綜合 SMC 分析（主要入口）。

| 參數 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼（用於 logging） |
| `df` | `pd.DataFrame` | K 線資料，需含 `open`, `high`, `low`, `close` |

**回傳：`dict[str, Any]`**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `order_blocks` | `list[dict]` | 最近 10 個 Order Block（見下方結構） |
| `fvg` | `list[dict]` | 最近 10 個 Fair Value Gap |
| `liquidity_sweeps` | `list[dict]` | 最近 10 個流動性掃單 |
| `crt` | `list[dict]` | 最近 10 個 CRT 結構 |
| `bias` | `str` | `"bullish"` / `"bearish"` / `"neutral"` |
| `confluence_score` | `float` | 多空信號佔比 %（0-100，越高=方向越一致） |

**`order_blocks` 元素結構：**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `type` | `str` | `"bullish"` / `"bearish"` |
| `price_low` | `float` | OB 下緣價格 |
| `price_high` | `float` | OB 上緣價格 |
| `bar_index` | `int` | K 棒索引（相對於 df） |
| `strength` | `float` | 相對強度（後一根 K 棒移動 / 近期平均波幅） |

**`fvg` 元素結構：**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `type` | `str` | `"bullish"` / `"bearish"` |
| `top` | `float` | 缺口上緣 |
| `bottom` | `float` | 缺口下緣 |
| `bar_index` | `int` | 缺口中心 K 棒索引 |
| `filled_pct` | `float` | 缺口已回補比例（0.0-1.0） |

**`liquidity_sweeps` 元素結構：**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `type` | `str` | `"bullish_sweep"` / `"bearish_sweep"` |
| `sweep_price` | `float` | 掃單極值價格 |
| `reference_level` | `float` | 被掃的前高/前低 |
| `bar_index` | `int` | K 棒索引 |
| `recovery_pct` | `float` | 收盤從極值回復的比例 % |

**`crt` 元素結構：**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `type` | `str` | `"bullish_crt"` / `"bearish_crt"` |
| `mother_high` | `float` | 母 K 最高 |
| `mother_low` | `float` | 母 K 最低 |
| `breakout_close` | `float` | 子 K 突破後收盤價 |
| `bar_index` | `int` | 子 K（Inside Bar）索引 |

---

### 個別偵測方法

| 方法 | 簽名 | 說明 |
|------|------|------|
| `detect_order_blocks` | `(df, lookback=50)` | 偵測 Order Block（反向 K 棒後強力突破） |
| `detect_fair_value_gaps` | `(df)` | 偵測 FVG（三根 K 棒第一與第三間缺口） |
| `detect_liquidity_sweep` | `(df, lookback=20)` | 偵測流動性掃單（突破前高/低後立即反轉） |
| `detect_crt` | `(df)` | 偵測 Inside Bar 突破（Candle Range Theory） |

---

## 5. BacktestEngine — 歷史回測

檔案：`atlas/application/backtest_engine.py`
類別：`BacktestEngine(IBacktestEngine)`

含台股成本模型的歷史策略回測引擎。

**成本模型（`include_cost=True` 時）：**

| 項目 | 費率 |
|------|------|
| 手續費 | 0.1425%（買賣各） |
| 證交稅 | 0.3%（賣出） |
| 滑價 | 0.085% |
| 合計 | ~0.685% per round-trip |

---

### `run(...)` — async

執行單次回測。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `strategy_name` | `str` | 必填 | 策略名稱（對應 StrategyLibrary 中的策略） |
| `codes` | `list[str]` | 必填 | 股票代碼列表 |
| `market` | `MarketType` | 必填 | 市場類型 |
| `start_date` | `date` | 必填 | 回測起始日 |
| `end_date` | `date` | 必填 | 回測結束日 |
| `initial_capital` | `float` | `1_000_000` | 初始資金（元） |
| `params` | `dict \| None` | `None` | 策略參數 |
| `include_cost` | `bool` | `True` | 是否扣除交易成本 |

**回傳：`BacktestResult`**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `run_id` | `str` | UUID 前 8 碼 |
| `strategy_name` | `str` | 策略名稱 |
| `market` | `MarketType` | 市場類型 |
| `start_date` / `end_date` | `date` | 回測期間 |
| `initial_capital` | `float` | 初始資金 |
| `final_capital` | `float` | 期末資金 |
| `total_return` | `float` | 總報酬 % |
| `annualized_return` | `float` | 年化報酬 %（簡化：總報酬 × 365/天數） |
| `max_drawdown` | `float` | 最大回撤 % |
| `sharpe_ratio` | `float` | Sharpe Ratio（年化，√252） |
| `win_rate` | `float` | 勝率 % |
| `total_trades` | `int` | 總交易筆數 |
| `winning_trades` | `int` | 獲利筆數 |
| `losing_trades` | `int` | 虧損筆數 |
| `avg_hold_days` | `float` | 平均持有天數 |
| `profit_factor` | `float` | 獲利因子（毛利 / 毛損） |
| `cost_model` | `dict` | 成本模型參數 |
| `trades` | `list[BacktestTrade]` | 交易明細列表 |
| `status` | `BacktestStatus` | `PENDING` / `RUNNING` / `COMPLETED` / `FAILED` |
| `params` | `dict` | 使用的策略參數 |
| `error_message` | `str` | 失敗時的錯誤訊息 |

**`BacktestTrade` 結構：**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 股票代碼 |
| `entry_date` / `exit_date` | `date` | 進出場日期 |
| `entry_price` / `exit_price` | `float` | 進出場價格 |
| `shares` | `int` | 股數（固定 1000 股） |
| `pnl` | `float` | 損益金額（元） |
| `pnl_pct` | `float` | 損益 % |
| `cost` | `float` | 交易成本（元） |
| `hold_days` | `int` | 持有天數 |
| `exit_reason` | `str` | 出場原因 |

---

### `param_scan(...)` — async

參數網格掃描，自動找最佳參數組合。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `strategy_name` | `str` | 必填 | 策略名稱 |
| `codes` | `list[str]` | 必填 | 股票代碼列表 |
| `market` | `MarketType` | 必填 | 市場類型 |
| `start_date` / `end_date` | `date` | 必填 | 回測期間 |
| `param_grid` | `dict[str, list]` | 必填 | 參數網格，如 `{"period": [10,20,30]}` |
| `metric` | `str` | `"sharpe_ratio"` | 排序指標（任何 `BacktestResult` 數值欄位） |

**回傳：`list[BacktestResult]`**（依 `metric` 降序排列）

---

### `walk_forward(...)` — async

Walk-Forward 分析，評估策略過擬合程度。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `strategy_name` | `str` | 必填 | 策略名稱 |
| `codes` | `list[str]` | 必填 | 股票代碼列表 |
| `market` | `MarketType` | 必填 | 市場類型 |
| `start_date` / `end_date` | `date` | 必填 | 總回測期間 |
| `num_windows` | `int` | `3` | 滾動視窗數量 |
| `in_sample_ratio` | `float` | `0.7` | 樣本內比例 |
| `param_grid` | `dict \| None` | `None` | 參數網格（有則在樣本內執行最佳化） |

**回傳：`list[WalkForwardResult]`**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `window_index` | `int` | 視窗序號（0 起始） |
| `in_sample_start` / `in_sample_end` | `date` | 樣本內期間 |
| `out_sample_start` / `out_sample_end` | `date` | 樣本外期間 |
| `in_sample_return` / `out_sample_return` | `float` | 各期間報酬 % |
| `in_sample_sharpe` / `out_sample_sharpe` | `float` | 各期間 Sharpe |
| `best_params` | `dict` | 樣本內最佳化參數 |
| `degradation_pct` | `float` | 效能衰退比 (out_sharpe/in_sharpe - 1) × 100 |

---

### `get_result(run_id)` — async

取得指定 `run_id` 的回測結果。回傳 `BacktestResult | None`。

---

## 6. MonteCarloSimulator — 蒙地卡羅模擬

檔案：`atlas/strategy/monte_carlo.py`
類別：`MonteCarloSimulator(IMonteCarloSimulator)`

以 Bootstrap 重抽樣評估策略的長期資金分布與風險。隨機種子固定為 `42`，確保結果可重現。

---

### `simulate(trades, num_paths, initial_capital)`

以實際歷史交易損益進行模擬（Bootstrap 重抽樣）。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `trades` | `list[float]` | 必填 | 歷史交易損益列表（元），通常來自 `BacktestResult.trades` |
| `num_paths` | `int` | `1000` | 模擬路徑數量 |
| `initial_capital` | `float` | `1_000_000` | 初始資金（元） |

---

### `simulate_with_params(win_rate, avg_win, avg_loss, ...)`

以參數化方式模擬（不需歷史交易資料）。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `win_rate` | `float` | 必填 | 勝率（0.0-1.0） |
| `avg_win` | `float` | 必填 | 平均獲利金額（元） |
| `avg_loss` | `float` | 必填 | 平均虧損金額（元，正數） |
| `num_trades` | `int` | `200` | 模擬交易筆數 |
| `num_paths` | `int` | `1000` | 模擬路徑數量 |
| `initial_capital` | `float` | `1_000_000` | 初始資金（元） |
| `risk_pct` | `float` | `0.02` | 每筆交易風險比例（佔當前資金） |

---

### 回傳：`MonteCarloResult`（兩種方法共用）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `num_paths` | `int` | 實際模擬路徑數 |
| `percentile_5` | `float` | 最終資金 5th 百分位（元）— 最悲觀情境 |
| `percentile_25` | `float` | 最終資金 25th 百分位（元） |
| `percentile_50` | `float` | 最終資金中位數（元） |
| `percentile_75` | `float` | 最終資金 75th 百分位（元） |
| `percentile_95` | `float` | 最終資金 95th 百分位（元）— 最樂觀情境 |
| `max_drawdown_median` | `float` | 最大回撤中位數 % |
| `max_drawdown_95` | `float` | 最大回撤 95th 百分位 % |
| `ruin_probability` | `float` | 破產機率（資金低於初始 50%，0.0-1.0） |
| `win_rate_used` | `float` | 實際使用的勝率 |
| `payoff_ratio_used` | `float` | 實際使用的損益比（avg_win/avg_loss） |
| `risk_pct_used` | `float` | 使用的風險比例（`simulate` 固定為 0.02） |
| `equity_curves` | `list[list[float]]` | 所有路徑淨值曲線（預設空 list，記憶體考量） |

---

*文件最後更新：2026-07-02*
