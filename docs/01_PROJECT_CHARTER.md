# Project Charter — Atlas Trading System v5.0

> 專案代號：**Atlas v5** | 文件版本：1.0 | 日期：2026-07-01

---

## 1. 專案願景

**打造一套高勝率、多市場、全自動化的量化交易決策系統**，融合四套既有系統精華，覆蓋台股、美股、中國 A 股三大市場，從選股到出場全流程紀律化執行。

**終極目標**：有紀律 / 賺多虧極少 / 財富自由

**系統價值主張**：精準 / 高獲利 / 多重測試驗證 / 自動化 / 優質介面 / 實體資料庫 / 即時資料來源 / 重要參考數據

---

## 2. 專案範疇

### 2.1 涵蓋市場

| 市場               | 交易時段    | 資料源                              | 優先級      |
| ------------------ | ----------- | ----------------------------------- | ----------- |
| 台股 (TWSE/TPEx)   | 09:00-13:30 | TWSE API / 群益 / shioaji / FinMind | P0 (核心)   |
| 美股 (NYSE/NASDAQ) | 21:30-04:00 | yfinance / Alpha Vantage / Polygon  | P1 (第二期) |

### 2.2 核心功能矩陣

| 功能領域           | 子功能                                                 | 來源系統精華                          |
| ------------------ | ------------------------------------------------------ | ------------------------------------- |
| **多面向選股邏輯** | 七流派融合 + ML 預測 + O'Neil 16分 + 扣抵共振          | 全部四套                              |
| **選股池管理**     | 多市場股票池 + 四層篩選 + 月度重建 + 產業分散          | Atlas + Signal Radar                  |
| **產業狀況分析**   | 產業 RS 輪動 + 熱力圖 + 產業勝率 + 族群資金流          | Signal Radar + Atlas                  |
| **資金流向追蹤**   | 三大法人 + 融資融券 + 五維資金評分 + 籌碼集中度        | MasterTalks + Signal Radar            |
| **重點策略指標**   | 22 日K策略 + 20 模組 + SMC/ICT + 五層訊號              | Atlas + Signal Radar                  |
| **盤中雷達推播**   | 11 偵測器 + 6 盤中訊號 + Pivot 突破 + 多通道推播       | Signal Radar + Atlas + Stock_Strategy |
| **工作流程自動化** | 盤前/盤中/盤後 SOP + 排程引擎 + 交易日曆               | 全部四套                              |
| **回測調整機制**   | 含成本回測 + 參數掃描 + 基因演算法 + 蒙地卡羅          | 全部四套                              |
| **風控系統**       | 結論七級 + 三層降級 + 情緒六大連動 + R 倍數 + ATR 倉位 | Signal Radar + Stock_Strategy         |
| **市場環境感知**   | 大盤趨勢 + 市場情緒 + 市場寬度 + 國際行情 + 缺口預測   | Signal Radar                          |
| **IPO 工具**       | 公開申購掃描 + 蜜月期追蹤                              | Signal Radar                          |

### 2.3 非功能需求

| 項目     | 目標                                      |
| -------- | ----------------------------------------- |
| 介面品質 | 現代化 Web UI，深/亮主題，RWD 響應式      |
| 資料庫   | PostgreSQL 實體資料庫（取代 SQLite/JSON） |
| 即時性   | 盤中報價延遲 < 3 秒                       |
| 可靠性   | 三層 Fallback，單一 API 故障不停擺        |
| 自動化   | 全流程排程，交易日自動執行，非交易日跳過  |
| 可測試性 | 單元測試覆蓋率 > 80%，回測結果可重現      |
| 部署     | Docker 容器化，一鍵啟動                   |
| 安全     | 金鑰環境變數化，敏感資料不進版控          |

---

## 3. 四套系統精華統一方案

### 3.1 可統一的共通基礎

| 共通項     | 現狀                             | 統一方案                           |
| ---------- | -------------------------------- | ---------------------------------- |
| 資料源     | 四套各自實作 TWSE/yfinance       | 統一 DataManager 服務層            |
| 即時報價   | TWSE MIS + 群益 + shioaji 分散   | 統一 QuoteAdapter（優先鏈）        |
| 推播       | Discord/LINE/Telegram/Email 分散 | 統一 NotificationHub（多通道路由） |
| 持久化     | SQLite + JSON 混用               | PostgreSQL + Redis 快取            |
| SOP 工作流 | 四套各自排程                     | 統一 WorkflowEngine + Scheduler    |
| 技術指標   | 重複實作 MA/RSI/MACD             | 統一 IndicatorLibrary              |
| 市場環境   | 各自判斷大盤                     | 統一 MarketRegimeService           |
| 回測引擎   | 各自實作                         | 統一 BacktestEngine + CostModel    |

### 3.2 各系統獨家精華（直接遷入）

| 精華模組                          | 來源           | 遷入方式                             |
| --------------------------------- | -------------- | ------------------------------------ |
| RandomForest ML 預測 + 防未來函數 | MasterTalks    | 新增 MLEngine 模組                   |
| 費氏扣抵共振 K-1/K-2/K-3          | Atlas          | 納入 StrategyLibrary                 |
| 22 策略 + 四大模組融合評分        | Atlas          | 納入 StrategyLibrary + ScoringEngine |
| SMC/ICT (OB/FVG/Liquidity/CRT)    | Signal Radar   | 新增 SMCModule                       |
| 結論七級 + 三層降級 + 情緒連動    | Signal Radar   | 納入 ConclusionEngine                |
| 11 即時偵測器                     | Signal Radar   | 納入 RealtimeDetectors               |
| IPO 工具 + 缺口預測校驗           | Signal Radar   | 新增 IPOModule + GapPredictor        |
| O'Neil 16 分制 + 型態分類         | Stock_Strategy | 納入 ScreenerEngine                  |
| 蒙地卡羅模擬                      | Stock_Strategy | 納入 RiskSimulator                   |
| 三層 Fallback 架構                | Stock_Strategy | 全系統採用此設計模式                 |

---

## 4. SDLC 階段與交付物

| 階段                  | 交付物                                    | 負責角色    | 狀態   |
| --------------------- | ----------------------------------------- | ----------- | ------ |
| **Phase 0: 啟動**     | 專案章程、利害關係人分析                  | PM          | 進行中 |
| **Phase 1: 需求分析** | SRS 需求規格書、Use Case、資料流圖        | SA          | 待啟動 |
| **Phase 2: 系統設計** | 架構設計書、DB Schema、API 規格、模組介面 | SD          | 待啟動 |
| **Phase 3: 詳細設計** | 類別圖、序列圖、狀態圖、演算法規格        | SD          | 待啟動 |
| **Phase 4: 實作**     | 原始碼、單元測試、程式文件                | PG          | 待啟動 |
| **Phase 5: 測試**     | 測試計畫、測試案例、測試報告、效能報告    | QA          | 待啟動 |
| **Phase 6: 部署**     | 部署手冊、Docker Compose、CI/CD、監控     | DevOps      | 待啟動 |
| **Phase 7: 維運**     | 維運手冊、SOP、故障排除指南               | DevOps + PM | 待啟動 |

---

## 5. 角色與分工

| 角色                    | 職責                                     | 委派方式                   |
| ----------------------- | ---------------------------------------- | -------------------------- |
| **PM (專案經理)**       | 規劃進度、協調資源、風險管理、向老闆回報 | Claude 主體 (我)           |
| **SA (系統分析師)**     | 需求訪談、功能分析、Use Case、資料流     | Subagent #1                |
| **SD (系統設計師)**     | 架構設計、DB 設計、API 設計、技術選型    | Subagent #2                |
| **PG (程式設計師)**     | 編碼實作、單元測試、Code Review          | Subagent #3~N (依模組拆分) |
| **QA (測試工程師)**     | 測試計畫、自動化測試、回歸測試           | Subagent #QA               |
| **DevOps (部署工程師)** | Docker 化、CI/CD、監控、部署             | Subagent #DevOps           |

### 工作流程

```
老闆 (你)
  |
  v
PM (我) — 彙整分析、產出報告、提出建議
  |
  v
老闆確認 → PM 發號施令 → Subagents 執行
  |                            |
  v                            v
PM 驗收 ← Subagents 回報結果
  |
  v
PM 向老闆回報成果
```

---

## 6. 技術架構概覽

```
┌─────────────────────────────────────────────────────┐
│                   Presentation Layer                 │
│  Streamlit (主 UI) + REST API (外部整合) + Mobile    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                  Application Layer                   │
│  WorkflowEngine | ScreenerEngine | RealtimeRadar    │
│  ConclusionEngine | BacktestEngine | RiskSimulator  │
│  NotificationHub | SchedulerService                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                   Strategy Layer                     │
│  StrategyLibrary (22+策略) | SMCModule | MLEngine   │
│  IndicatorLibrary | ScoringEngine | GapPredictor    │
│  IPOModule | MonteCarloSimulator                     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                    Domain Layer                      │
│  MarketRegimeService | SentimentService              │
│  BreadthService | InternationalMarket                │
│  UniverseManager | PortfolioManager                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│                 Infrastructure Layer                 │
│  DataManager | QuoteAdapter (Fallback Chain)         │
│  PostgreSQL | Redis | SQLite(legacy compat)          │
│  Discord/LINE/Telegram/Email Adapters                │
│  shioaji | Capital SKCOM | TWSE MIS | yfinance      │
└─────────────────────────────────────────────────────┘
```

---

## 7. 實作分期計畫

### Phase 1: 基礎建設 (Foundation)

- 專案結構 + PostgreSQL Schema + DataManager + QuoteAdapter
- IndicatorLibrary + 統一技術指標
- 三層 Fallback 架構模式
- 預計工作量：中

### Phase 2: 核心引擎 (Core Engines)

- ScreenerEngine (整合七流派 + O'Neil + ML)
- StrategyLibrary (22 策略 + SMC + 扣抵共振)
- ConclusionEngine (結論七級 + 三層降級)
- MarketRegimeService (環境感知)
- 預計工作量：大

### Phase 3: 即時系統 (Realtime)

- RealtimeRadar (11 偵測器 + 6 盤中訊號)
- QuoteAdapter (群益/shioaji/TWSE MIS)
- NotificationHub (Discord/LINE/Telegram)
- 預計工作量：大

### Phase 4: 回測與風控 (Backtest & Risk)

- BacktestEngine (含成本模型)
- 參數掃描 + 基因演算法優化
- 蒙地卡羅模擬器
- R 倍數追蹤 + ATR 倉位計算
- 預計工作量：中

### Phase 5: 自動化與排程 (Automation)

- WorkflowEngine + SchedulerService
- 盤前/盤中/盤後 SOP 自動化
- 交易日曆整合
- GitHub Actions / Windows Task Scheduler
- 預計工作量：中

### Phase 6: 介面與體驗 (UI/UX)

- Streamlit 現代化 Dashboard
- 多市場切換
- 深/亮主題 + RWD
- 互動式 K 線 + 策略疊加
- 預計工作量：大

### Phase 7: 美股擴展 (US Market)

- 美股資料源 + 策略適配
- 台美跨市場相關性分析（ADR 溢價、費半連動）
- 預計工作量：中

---

## 8. 風險評估

| 風險              | 影響             | 緩解措施                             |
| ----------------- | ---------------- | ------------------------------------ |
| API 來源變動/斷線 | 資料中斷         | 三層 Fallback + 快取                 |
| 過度擬合          | 回測漂亮實盤虧損 | 防未來函數 + Walk-forward + 蒙地卡羅 |
| 系統複雜度過高    | 維護困難         | 模組化 + 清晰介面 + 文件化           |
| 單一市場依賴      | 市場系統性風險   | 台股 + 美股雙市場分散                |
| 資料品質問題      | 訊號失準         | 資料校驗 + 異常偵測 + 缺口校驗閉環   |

---

## 9. 成功指標

| 指標         | 目標值 | 量測方式           |
| ------------ | ------ | ------------------ |
| 選股命中率   | > 65%  | 盤後追蹤 30 日報酬 |
| 平均 R 倍數  | > 2.0  | 交易日誌統計       |
| 最大回撤     | < 15%  | 帳戶級回撤監控     |
| 系統可用率   | > 99%  | 排程執行成功率     |
| 推播延遲     | < 5 秒 | 偵測到推播送達時間 |
| 回測可重現性 | 100%   | 相同參數相同結果   |

---

## 10. 下一步行動 (PM 建議)

1. **請老闆確認本章程**：範疇、優先級、分期計畫是否符合預期
2. **啟動 SA 需求分析**：委派 SA subagent 產出 SRS 需求規格書
3. **啟動 SD 架構設計**：委派 SD subagent 產出技術架構設計書 + DB Schema
4. **建立專案骨架**：初始化 Tranding_AI 專案結構 + Git

---

_PM 報告完畢，等待老闆指示。_
