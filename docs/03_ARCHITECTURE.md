# 架構設計書 — Atlas Trading System v5.0

> 文件版本：1.0 | 日期：2026-07-01 | 作者：SD（系統設計師）| 審核：PM

---

## 1. 架構概覽

### 1.1 五層架構圖

```
┌──────────────────────────────────────────────────────────────────┐
│                     L5  Presentation Layer                       │
│  Streamlit Pages (P-01~P-12) │ REST API │ WebSocket (盤中推送)  │
├──────────────────────────────────────────────────────────────────┤
│                     L4  Application Layer                        │
│  WorkflowEngine │ ScreenerEngine │ RealtimeRadar │ BacktestEngine│
│  ConclusionEngine │ NotificationHub │ SchedulerService          │
│  RiskSimulator │ PortfolioManager                                │
├──────────────────────────────────────────────────────────────────┤
│                     L3  Strategy Layer                           │
│  StrategyLibrary (22+策略) │ SMCModule │ MLEngine │ ScoringEngine│
│  IndicatorLibrary │ GapPredictor │ IPOModule │ MonteCarloSim     │
├──────────────────────────────────────────────────────────────────┤
│                     L2  Domain Layer                             │
│  MarketRegimeService │ SentimentService │ BreadthService         │
│  InternationalMarket │ UniverseManager │ FundFlowService         │
│  TradingCalendar │ IndustryAnalyzer                              │
├──────────────────────────────────────────────────────────────────┤
│                     L1  Infrastructure Layer                     │
│  DataManager │ QuoteAdapter (Fallback Chain) │ CacheManager      │
│  PostgreSQL (SQLAlchemy) │ Redis │ NotificationAdapters          │
│  Broker Adapters (shioaji/SKCOM) │ External API Clients          │
│  ConfigManager │ Logger │ HealthChecker                          │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 各層職責與邊界定義

| 層級                  | 名稱       | 職責                                                | 邊界規則                        |
| --------------------- | ---------- | --------------------------------------------------- | ------------------------------- |
| **L5 Presentation**   | 展示層     | UI 渲染、使用者互動、請求路由、回應格式化           | 不含業務邏輯，僅呼叫 L4         |
| **L4 Application**    | 應用層     | 編排業務流程（Use Case 實現）、跨模組協調、事件發布 | 不含指標計算，不直接存取 DB/API |
| **L3 Strategy**       | 策略層     | 策略計算、指標運算、ML 預測、評分引擎               | 純計算邏輯，透過介面取得資料    |
| **L2 Domain**         | 領域層     | 核心業務實體與領域服務                              | 業務規則核心，不依賴上層        |
| **L1 Infrastructure** | 基礎設施層 | 資料存取、外部通訊、快取、推播、設定管理            | 實作上層定義的介面              |

### 1.3 層間依賴規則

```
L5 → L4 → L3 → L2 → L1（僅允許上層呼叫下層）

禁止：
  ✗ L1 → L2/L3/L4/L5（反向依賴）
  ✗ L3 → L4（同級越級）
  ✗ L5 → L1（跳層直接存取基礎設施）

例外（透過介面反轉）：
  L2 定義 Repository Interface → L1 實作（Dependency Inversion）
  L4 定義 Event Interface → L1 實作推播（Observer Pattern）
```

---

## 2. 模組依賴圖

### 2.1 模組依賴關係

```
DataManager ─────────────┐
CacheManager ────────────┤
QuoteAdapter ────────────┤
ConfigManager ───────────┤ L1 基礎層（無上層依賴）
Logger ──────────────────┤
HealthChecker ───────────┤
NotificationAdapters ────┘

TradingCalendar ─────────┐
  └→ DataManager          │
MarketRegimeService ─────┤
  └→ DataManager, Cache   │
SentimentService ────────┤ L2 領域層
  └→ DataManager          │
BreadthService ──────────┤
  └→ DataManager          │
InternationalMarket ─────┤
  └→ DataManager          │
UniverseManager ─────────┤
  └→ DataManager, Cache   │
FundFlowService ─────────┤
  └→ DataManager          │
IndustryAnalyzer ────────┘
  └→ DataManager, FundFlowService

IndicatorLibrary ────────┐
  └→ DataManager          │
StrategyLibrary ─────────┤
  └→ IndicatorLibrary     │
SMCModule ───────────────┤ L3 策略層
  └→ IndicatorLibrary     │
MLEngine ────────────────┤
  └→ IndicatorLibrary,    │
     DataManager          │
ScoringEngine ───────────┤
  └→ IndicatorLibrary,    │
     FundFlowService      │
GapPredictor ────────────┤
  └→ InternationalMarket  │
IPOModule ───────────────┤
  └→ DataManager          │
MonteCarloSim ───────────┘
  └→ (純計算，無外部依賴)

ScreenerEngine ──────────┐
  └→ ScoringEngine,       │
     UniverseManager,     │
     IndustryAnalyzer,    │
     MLEngine, SMCModule  │
ConclusionEngine ────────┤
  └→ MarketRegimeService, │
     SentimentService,    │ L4 應用層
     IndustryAnalyzer     │
RealtimeRadar ───────────┤
  └→ QuoteAdapter,        │
     IndicatorLibrary,    │
     ConclusionEngine     │
BacktestEngine ──────────┤
  └→ StrategyLibrary,     │
     IndicatorLibrary,    │
     MonteCarloSim        │
WorkflowEngine ──────────┤
  └→ SchedulerService,    │
     TradingCalendar,     │
     ScreenerEngine,      │
     RealtimeRadar        │
NotificationHub ─────────┤
  └→ NotificationAdapters │
SchedulerService ────────┤
  └→ TradingCalendar      │
PortfolioManager ────────┤
  └→ DataManager,         │
     QuoteAdapter         │
RiskSimulator ───────────┘
  └→ MonteCarloSim,
     BacktestEngine
```

### 2.2 核心模組（必須先實作）

| 優先序 | 模組                | 理由                    |
| ------ | ------------------- | ----------------------- |
| 1      | ConfigManager       | 全系統設定基礎          |
| 2      | Logger              | 全系統日誌              |
| 3      | DataManager         | 資料存取抽象            |
| 4      | CacheManager        | Redis 封裝              |
| 5      | QuoteAdapter        | 即時報價 Fallback Chain |
| 6      | TradingCalendar     | 排程決策依據            |
| 7      | IndicatorLibrary    | 策略與評分基礎          |
| 8      | MarketRegimeService | 風控連動基礎            |

---

## 3. 設計模式

### 3.1 Strategy Pattern（策略模式）

| 項目         | 說明                                                                            |
| ------------ | ------------------------------------------------------------------------------- |
| **使用模組** | StrategyLibrary、ScoringEngine                                                  |
| **實作方式** | `BaseStrategy` ABC，22 策略各自繼承。ScoringEngine 的四主軸為獨立 `ScoringAxis` |
| **理由**     | 策略可獨立啟停、參數可調、新增不修改既有程式碼                                  |

### 3.2 Chain of Responsibility（Fallback Chain）

| 項目         | 說明                                           |
| ------------ | ---------------------------------------------- |
| **使用模組** | QuoteAdapter、DataManager、NotificationHub     |
| **實作方式** | 各資料源實作 `DataSourceHandler`，按優先鏈排列 |
| **理由**     | NFR-REL R-2 Fallback < 5 秒                    |

```
即時報價鏈：群益 SKCOM → shioaji → TWSE MIS → Redis Last-Good
日K線鏈：  TWSE OpenAPI → yfinance → FinMind → Redis 快取
推播通道鏈：Discord → LINE → Telegram → Email → 本地日誌
```

### 3.3 Observer Pattern（事件驅動）

| 項目         | 說明                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| **使用模組** | RealtimeRadar（發布）、NotificationHub/ConclusionEngine/PortfolioManager（訂閱） |
| **實作方式** | EventBus，偵測器觸發發布 DetectorAlert                                           |
| **理由**     | 盤中事件需同時觸發推播、降級、持倉更新                                           |

### 3.4 Factory Pattern（工廠模式）

| 項目         | 說明                                          |
| ------------ | --------------------------------------------- |
| **使用模組** | DataManager、StrategyLibrary、NotificationHub |
| **實作方式** | 根據市場類型動態建立對應實例                  |
| **理由**     | 一鍵切換台股/美股                             |

### 3.5 Repository Pattern（倉儲模式）

| 項目         | 說明                                      |
| ------------ | ----------------------------------------- |
| **使用模組** | 所有需存取 PostgreSQL 的模組              |
| **實作方式** | L2 定義 Interface → L1 以 SQLAlchemy 實作 |
| **理由**     | 隔離業務與資料存取，便於測試 mock         |

---

## 4. 關鍵序列圖

### 4.1 盤前分析流程（UC-001）

**參與模組**：SchedulerService → TradingCalendar → WorkflowEngine →
InternationalMarket → MarketRegimeService → SentimentService → GapPredictor →
NotificationHub

1. SchedulerService 於 08:00 觸發 cron
2. TradingCalendar.is_trading_day(today) — 否則中止
3. WorkflowEngine.run("pre_market")
4. InternationalMarket.fetch_us_close() — 美股四大指數 +
   8 檔代表性美股（Fallback: yfinance → Alpha Vantage → Redis）
5. InternationalMarket.fetch_futures() — 台指期夜盤
6. SentimentService.calculate(us_data, futures_data) → GREED/NEUTRAL/FEAR
7. MarketRegimeService.update() → BULL/RANGE/BEAR
8. GapPredictor.predict(us_data, futures_data) → 缺口方向與幅度
9. 彙整晨報
10. NotificationHub.broadcast("morning_report", report)
11. DataManager 寫入 PostgreSQL

**錯誤處理**：資料源失敗 → Fallback；全部失敗 → 晨報標註「資料不可用」+ 告警

### 4.2 盤中即時監控流程（UC-002）

**參與模組**：RealtimeRadar → QuoteAdapter → Detectors (×11) → EventBus →
ConclusionEngine + NotificationHub + PortfolioManager

1. 09:00 RealtimeRadar.start()
2. QuoteAdapter.connect() — Fallback Chain
3. 每 ≤3 秒推送報價 → Redis + 11 偵測器
4. 偵測器觸發 → EventBus.publish(DetectorAlert)
5. ConclusionEngine 即時計算等級 + 三層降級
6. PortfolioManager 更新持倉損益
7. NotificationHub 判斷推播門檻（正常 ≥Lv3，FEAR 時 ≥Lv4）
8. 所有告警寫入 PostgreSQL
9. 13:30 RealtimeRadar.stop()

**錯誤處理**：報價斷線 → Fallback < 5秒；單一偵測器例外 → 隔離；推播故障 →
Fallback 通道

### 4.3 盤後選股掃描流程（UC-003）

**參與模組**：WorkflowEngine → DataManager → IndicatorLibrary → ScreenerEngine →
ScoringEngine → ConclusionEngine → MLEngine → SMCModule → NotificationHub

1. 15:30 觸發盤後流程
2. DataManager.fetch_daily() — TWSE/TPEx/T86/MI_MARGN/FinMind → PostgreSQL
3. IndicatorLibrary.calculate_all(universe) — 全池技術指標
4. ScreenerEngine.scan() — 四主軸 + 三面向 → Top 50
5. MLEngine.predict() + SMCModule.analyze() — 輔助確認
6. ConclusionEngine.evaluate() — 結論七級 + 降級
7. 輸出 Top 10~20 精選
8. GapPredictor.verify() — 校驗今日缺口預測
9. NotificationHub.broadcast() — 推播精選清單

**錯誤處理**：資料延遲 → 重試 3 次（10s/30s/90s）；ML 失敗 → 退化純規則

### 4.4 回測執行流程（UC-004）

1. 使用者選擇策略與參數
2. BacktestEngine.configure() — Pydantic 驗證
3. DataManager.get_historical() — 歷史行情
4. IndicatorLibrary.calculate() — 策略所需指標
5. StrategyLibrary.get(name).generate_signal() — 進出場信號
6. BacktestEngine.execute() — 含成本 0.685% 模擬交易
7. calc_metrics() — 總報酬/年化/最大回撤/Sharpe/勝率/平均R
8. 可選：param_scan / ga_optimize / monte_carlo
9. 結果存入 PostgreSQL

### 4.5 Fallback 切換流程

1. QuoteAdapter.fetch() 呼叫主源
2. 成功 → 寫入 Redis Last-Good + 回傳
3. 失敗 → 記錄 + 指數退避重試（1s→2s→4s，max 3 次）
4. 重試耗盡 → 標記 UNHEALTHY → 傳遞至下一源
5. 全部失敗 → Redis Last-Good Value（標記 stale=True）
6. 快取也無 → AllSourcesExhaustedError + 推播告警
7. HealthChecker 每 60 秒 heartbeat → 連續 3 次成功 → 恢復 HEALTHY

---

## 5. 錯誤處理策略

### 5.1 自訂異常層次結構

```
AtlasBaseError
├── DataError
│   ├── DataSourceError
│   │   ├── ConnectionTimeoutError
│   │   ├── RateLimitExceededError
│   │   ├── AuthenticationError
│   │   └── DataFormatError
│   ├── DataValidationError
│   │   ├── MissingFieldError
│   │   ├── ValueOutOfRangeError
│   │   └── FutureFunctionError
│   ├── AllSourcesExhaustedError
│   └── NoDataAvailableError
├── StrategyError
│   ├── InsufficientDataError
│   ├── IndicatorCalculationError
│   ├── SignalGenerationError
│   └── OverfittingWarning
├── InfrastructureError
│   ├── DatabaseError
│   ├── CacheError
│   ├── NotificationError
│   │   └── AllChannelsFailedError
│   └── BrokerConnectionError
├── ConfigError
│   ├── MissingConfigError
│   └── InvalidConfigValueError
└── SecurityError
    ├── AuthenticationFailedError
    ├── AuthorizationError
    └── AccountLockedError
```

### 5.2 各層錯誤處理原則

| 層級 | 原則                                        |
| ---- | ------------------------------------------- |
| L1   | 捕獲技術例外，轉譯為自訂異常                |
| L2   | 處理業務規則違反                            |
| L3   | 隔離單一策略/指標失敗，標記 N/A 繼續        |
| L4   | 編排降級決策（ML 失敗→規則；資料延遲→快取） |
| L5   | 轉換為使用者友善訊息                        |

### 5.3 重試策略

| 場景         | 最大重試 | 退避方式        | 間隔             |
| ------------ | -------- | --------------- | ---------------- |
| 外部 API     | 3        | 指數            | 1s→2s→4s         |
| DB 連線      | 5        | 指數            | 0.5s→1s→2s→4s→8s |
| 推播         | 2        | 固定            | 3s               |
| 盤後資料     | 3        | 指數            | 10s→30s→90s      |
| 即時報價重連 | ∞        | 指數（上限60s） | 1s→2s→...→60s    |

### 5.4 降級策略

| 觸發條件        | 降級行為                             | 通知           |
| --------------- | ------------------------------------ | -------------- |
| 即時報價全斷    | Redis Last-Good，UI 顯示「快取模式」 | 推播告警       |
| ML 失敗         | 純規則評分，信心度標記 N/A           | 報告標註       |
| 單一策略失敗    | 跳過，其餘正常                       | 該欄位標記 ERR |
| 推播全斷        | 本地日誌 + 重試佇列                  | 無             |
| PostgreSQL 斷線 | 暫存 Redis，恢復後 flush             | 推播告警       |

---

## 6. 設定管理

### 6.1 設定層次（優先級由高到低）

1. 環境變數 / .env（最高）
2. Runtime 動態設定（Redis）
3. config/*.yaml（靜態）
4. 程式碼預設值（最低）

### 6.2 設定檔拆分

```
config/
├── base.yaml          # 全域基本設定
├── market_tw.yaml     # 台股專屬
├── market_us.yaml     # 美股專屬
├── strategies.yaml    # 策略參數
├── scoring.yaml       # 四主軸權重、三面向閾值
├── risk.yaml          # 風控參數
├── notification.yaml  # 推播設定
├── scheduler.yaml     # 排程時間表
└── backtest.yaml      # 回測成本模型
```

### 6.3 環境變數規範

- 前綴 `ATLAS_`
- `.env.example` 列全部變數名
- 啟動時 fail-fast 驗證
- 日誌禁輸出金鑰

### 6.4 動態 vs 靜態設定

| 分類 | 儲存        | 修改方式   | 範例                             |
| ---- | ----------- | ---------- | -------------------------------- |
| 靜態 | .env + yaml | 重啟生效   | DB連線、API金鑰、費氏均線        |
| 動態 | Redis       | UI即時生效 | 四主軸權重、偵測器啟停、風控門檻 |

---

## 7. 實作順序建議

### 7.1 實作分批計畫

| Batch | 內容                                                                        | 可平行                 | 前置        |
| ----- | --------------------------------------------------------------------------- | ---------------------- | ----------- |
| **0** | 專案骨架 + Docker + Schema + CI                                             | —                      | 無          |
| **1** | ConfigManager + Logger + DataManager + CacheManager                         | 4 模組平行             | Batch 0     |
| **2** | QuoteAdapter + HealthChecker + NotificationAdapters                         | 3 模組平行             | Batch 1     |
| **3** | TradingCalendar + MarketRegime + Sentiment + Universe + FundFlow + Industry | 6 模組平行             | Batch 1     |
| **4** | IndicatorLibrary + StrategyLibrary + ScoringEngine                          | Indicator 先行         | Batch 1,3   |
| **5** | MLEngine + SMCModule + GapPredictor + MonteCarlo + IPO                      | 5 模組平行             | Batch 4     |
| **6** | ScreenerEngine + ConclusionEngine + BacktestEngine + RiskSimulator          | Screener/Backtest 平行 | Batch 3,4,5 |
| **7** | RealtimeRadar + WorkflowEngine + Scheduler + NotificationHub + Portfolio    | Radar/Workflow 平行    | Batch 2,6   |
| **8** | Streamlit Pages P-01~P-12                                                   | 各頁面平行             | Batch 6,7   |

### 7.2 關鍵路徑

```
Batch 0 → 1 → 4 (IndicatorLibrary) → 6 (ScreenerEngine) → 7 → 8
```

最大平行度：Batch 3+4 期間可同時開發 8 個模組。

---

_SD 架構設計書完成。_
