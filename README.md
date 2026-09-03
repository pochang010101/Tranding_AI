# Atlas Trading System v5.0

> 台股量化交易決策系統 — 從選股到交易的完整閉環

## 功能總覽

### 19 個分析頁面

| 頁面 | 功能 |
|------|------|
| P-01 總覽 | 大盤環境 + 持倉概覽 + 市場情緒儀表板 |
| P-02 盤前 | 美股四大指數(含漲跌點數) + 台指期夜盤 + ADR + 缺口預測 |
| P-03 雷達 | 11 個盤中偵測器 + 觀察股自動掃描 |
| P-04 選股 | 全市場掃描 + 均線/扣抵值篩選 + 觀察股持久化 |
| P-05 股池 | 自選股票池管理 + 標籤分類 |
| P-06 持倉 | 投資組合追蹤 + R-multiple 風控 |
| P-07 回測 | Walk-forward + 參數掃描 + 成本模型 |
| P-08 IPO | IPO 自動抓取 + 蜜月期追蹤 |
| P-09 產業 | 產業輪動偵測 + 族群強弱排序 |
| P-10 排程 | 自動化 SOP 排程管理 |
| P-11 設定 | 系統參數 + 通知頻道設定 |
| P-12 K 線 | 技術分析圖表 + 多指標疊圖 |
| P-13 紙上交易 | 模擬交易 + 手續費/稅模型 |
| P-14 價位分析 | 支撐/壓力/Fibonacci/買點/停損 |
| P-15 主力偵測 | 吸貨/洗盤/拉抬/出貨四階段判定 |
| P-16 因子健檢 | IC/ICIR/衰減分析 + 因子權重建議 |
| P-17 籌碼分析 | 融資融券 + 券資比 + 軋空/斷頭警戒 |
| P-18 對沖策略 | 基差分析 + 避險比 + 多空配對 |
| P-19 個股分析 | ECF 風格 13 區塊完整儀表板 |

### 決策閉環

```
盤前分析 (P-02)
  │  美股/期貨/ADR → 缺口預測 → 市場情緒
  ▼
全市場選股 (P-04)
  │  法人買賣超 + 量能 + 價格動能 → 標籤化排序
  ▼
盤中雷達 (P-03)
  │  觀察股自動匯入 → 11 訊號偵測器即時掃描
  ▼
交易決策 (P-14/P-15/P-17)
  │  價位分析 + 主力階段 + 籌碼 → 進場/停損/目標
  ▼
風控執行 (P-06/P-18)
  │  R-multiple 持倉管理 + 期貨對沖
  ▼
盤後復盤 (P-07/P-16)
     回測驗證 + 因子健檢 → 策略迭代
```

### 核心模組

| 類別 | 模組 | 說明 |
|------|------|------|
| 技術指標 | `indicator_lib` | MA / RSI / MACD / BB / ATR / KD / OBV / VP |
| 評分引擎 | `scoring_engine` | 4 軸 (產業→催化→資金→RS) + 3 面向評分 |
| SMC | `smc_module` | Order Blocks / FVG / Sweep / CRT |
| 主力偵測 | `smart_money_phase` | 吸貨/洗盤/拉抬/出貨四階段 |
| 多流派訊號 | `pattern_signals` | 葛蘭碧 / N底 / 均線排列 / 綜合評分 |
| 因子探勘 | `factor_mining` | IC / ICIR / 衰減 / 權重建議 |
| ML 預測 | `ml_engine` | RandomForest 預測 + 特徵重要性 |
| Monte Carlo | `monte_carlo` | 蒙地卡羅模擬 |
| 市場環境 | `market_regime` | Bull / Bear / Range 偵測 |
| 情緒分析 | `sentiment` | 5 級市場情緒評分 |
| 籌碼分析 | `margin_analysis` | 券資比/維持率/斷頭警戒/軋空判定 |
| 匯率因子 | `fx_factor` | TWD/USD 動能對出口股影響 |
| 對沖策略 | `hedge_strategy` | 基差分析/避險比/多空配對 |
| 即時報價 | `quote_adapter` | TWSE MIS → yfinance → cache fallback chain |
| 批次資料 | `twse_bulk` | MI_INDEX + T86 + TPEx + 處置股 |
| 期貨資料 | `taifex_data` | 台指期行情/法人未平倉/P/C ratio/基差 |
| 通知推播 | `notification_hub` | Discord → LINE → Telegram → Email fallback |

## 快速開始

### 環境需求

- Python 3.12+
- Docker + Docker Compose
- PostgreSQL 17 + Redis 7（由 Docker 提供）

### 開發環境

```bash
# 1. 啟動 DB + Redis
docker compose up -d db redis

# 2. 安裝依賴
pip install -e ".[dev]"

# 3. DB migration
export ATLAS_DATABASE_URL=postgresql://atlas:atlas_dev@localhost:5432/atlas
python -m alembic upgrade head

# 4. 種子資料（選用）
PYTHONPATH=. python scripts/seed_data.py

# 5. 啟動應用
streamlit run atlas/presentation/app.py
# 瀏覽 http://localhost:8501
```

### Docker 一鍵啟動

```bash
docker compose up --build -d
# 瀏覽 http://localhost:8501
```

### 生產環境部署

```bash
# 1. 建立環境設定
cp .env.example .env.prod
# 編輯 .env.prod 填入資料庫密碼、API Key、通知頻道 Token

# 2. 一鍵部署（含 SSL + Nginx 反向代理）
bash scripts/deploy.sh
# 瀏覽 https://your-domain

# 3. 查看日誌
docker compose -f docker/docker-compose.prod.yml logs -f

# 4. 停止服務
docker compose -f docker/docker-compose.prod.yml down
```

生產環境特性：
- Nginx 反向代理 + SSL（自動產生自簽憑證，建議替換 Let's Encrypt）
- 服務資源限制（CPU / Memory）
- Redis 啟用 AOF 持久化 + requirepass
- DB / Redis 不對外暴露 port
- JSON 日誌輪替

## 架構

### 5 層架構

```
┌─────────────────────────────────────────────┐
│  Presentation — Streamlit 19 頁             │
│  (app.py + service_container + auth)        │
├─────────────────────────────────────────────┤
│  Application — 選股 / 回測 / 紙上交易 / 排程  │
│  (screener, backtest, paper_trading,        │
│   realtime_radar, workflow, scheduler)      │
├─────────────────────────────────────────────┤
│  Strategy — 指標 / 評分 / SMC / 因子 / ML    │
│  (indicator_lib, scoring_engine, smc,       │
│   factor_mining, ml_engine, monte_carlo)    │
├─────────────────────────────────────────────┤
│  Domain — 情緒 / 籌碼 / 匯率 / 交易日曆     │
│  (market_regime, sentiment, portfolio,      │
│   margin_analysis, fx_factor, fund_flow)    │
├─────────────────────────────────────────────┤
│  Infrastructure — DB + Cache + API          │
│  (PostgreSQL 17, Redis 7, TWSE/TPEx,        │
│   期交所, yfinance, 通知推播)               │
└─────────────────────────────────────────────┘
```

### 資料流

```
TWSE / TPEx API ──→ DataManager ──→ PostgreSQL
                                      ↑
yfinance ──→ 即時報價 ──→ fallback chain ──→ Redis Cache
                                      ↑
期交所 TAIFEX ──→ 法人未平倉 / P/C Ratio / 大額交易人
```

### 目錄結構

```
atlas/
├── config.py                 # AtlasConfig（環境變數）
├── enums.py                  # MarketType, RegimeState, SignalType...
├── models/                   # 純 dataclass（非 ORM）
├── interfaces/               # ABCs / Protocols
├── infrastructure/
│   ├── orm/                  # 27 張 SQLAlchemy 2.0 ORM 表
│   ├── data_manager.py       # TWSE/TPEx 資料抓取 + DB 持久化
│   ├── quote_adapter.py      # 即時報價 fallback chain
│   ├── twse_bulk.py          # 批次 API（MI_INDEX, T86, 處置股）
│   ├── taifex_data.py        # 期交所資料
│   └── notifications/        # Discord / LINE / Telegram / Email
├── domain/
│   ├── market_regime.py      # 牛熊判定
│   ├── sentiment.py          # 5 級情緒
│   ├── margin_analysis.py    # 籌碼分析
│   └── fx_factor.py          # 匯率因子
├── strategy/
│   ├── indicator_lib.py      # 技術指標庫
│   ├── scoring_engine.py     # 4 軸評分引擎
│   ├── smc_module.py         # Smart Money Concepts
│   ├── smart_money_phase.py  # 主力四階段
│   ├── factor_mining.py      # 因子探勘
│   └── ml_engine.py          # ML 預測
├── application/
│   ├── screener_engine.py    # 選股引擎
│   ├── smart_screener.py     # 全市場智慧選股
│   ├── backtest_engine.py    # 回測引擎
│   ├── realtime_radar.py     # 盤中雷達
│   ├── paper_trading.py      # 紙上交易
│   └── scheduler.py          # APScheduler 排程
├── presentation/
│   ├── app.py                # Streamlit 入口
│   ├── service_container.py  # 服務容器（lazy singleton）
│   └── pages/                # P-01 ~ P-19
├── tests/                    # 579 tests
├── alembic/                  # DB migration
├── scripts/                  # 部署 / 種子 / 驗證腳本
└── docker/                   # Dockerfile + Compose
```

## 測試

```bash
# 全部測試（579 tests, ~16s, 不需外部服務）
PYTHONPATH=. pytest tests/ -q --tb=short

# 單一測試檔
PYTHONPATH=. pytest tests/unit/test_scoring_engine.py -x -q

# E2E 驗證（需真實 DB + 網路）
PYTHONPATH=. python scripts/verify_e2e.py

# Lint
ruff check atlas/
ruff format atlas/
```

## 監控

```bash
# 啟動 Prometheus + Grafana + Exporters
docker compose -f docker-compose.yml \
  -f docker/docker-compose.monitoring.yml up -d

# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000
```

監控元件：Prometheus、Grafana、PostgreSQL Exporter、Redis Exporter、Node Exporter。

## 自動排程

| 排程 | 時間 | 功能 |
|------|------|------|
| 盤前分析 | 08:00 | 國際行情 → 缺口預測 → 環境 → 情緒 |
| 盤中監控 | 09:00 | 啟動雷達掃描 |
| 盤後 SOP | 17:30 | 停雷達 → 資料更新 → 選股掃描 → 推播 |
| 月度重建 | 週日 20:00 | 重建股票池 |

非交易日自動跳過（月度重建除外）。

## 環境變數

複製 `.env.example` 並填入：

| 變數 | 說明 |
|------|------|
| `ATLAS_DB_PASSWORD` | PostgreSQL 密碼 |
| `ATLAS_REDIS_PASSWORD` | Redis 密碼（生產環境必填） |
| `FUGLE_API_KEY` | Fugle 即時報價 API Key |
| `DISCORD_WEBHOOK_URL` | Discord 通知 Webhook |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 推播 Token |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |

完整變數列表見 `.env.example`。

## 技術棧

| 類別 | 技術 |
|------|------|
| 語言 | Python 3.14 |
| Web UI | Streamlit 1.58 + Plotly 6.8 |
| 資料庫 | PostgreSQL 17 + SQLAlchemy 2.0 + Alembic |
| 快取 | Redis 7 |
| ML | scikit-learn (RandomForest) |
| HTTP | httpx (async) |
| 容器 | Docker multi-stage + Compose |
| CI/CD | GitHub Actions (lint → test → build) |
| 監控 | Prometheus + Grafana |
| Lint | ruff (E, F, W, I, N, UP, B, A, SIM) |

## License

Private — for internal use only.
