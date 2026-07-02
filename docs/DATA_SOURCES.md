# Atlas Trading System — Data Sources Reference

> 版本：v5.0 | 更新：2026-07-02

所有外部資料源的 URL、用途、TTL、限制與 Fallback 策略。

---

## 目錄

1. [資料流概覽](#1-資料流概覽)
2. [TWSE MIS API — 即時報價](#2-twse-mis-api--即時報價)
3. [TWSE T86 — 三大法人買賣超](#3-twse-t86--三大法人買賣超)
4. [TWSE MI_MARGN — 融資融券](#4-twse-mi_margn--融資融券)
5. [TWSE STOCK_DAY — 歷史日 K 線](#5-twse-stock_day--歷史日-k-線)
6. [TWSE STOCK_DAY_ALL — 全市場當日行情](#6-twse-stock_day_all--全市場當日行情)
7. [TWSE newlisting — 新上市股票](#7-twse-newlisting--新上市股票)
8. [TPEx — 上櫃股票](#8-tpex--上櫃股票)
9. [MOPS — 公開資訊觀測站（季報 / 月營收）](#9-mops--公開資訊觀測站季報--月營收)
10. [yfinance — 歷史資料與國際報價](#10-yfinance--歷史資料與國際報價)
11. [Fallback Chain 彙整](#11-fallback-chain-彙整)
12. [Rate Limit 防護](#12-rate-limit-防護)

---

## 1. 資料流概覽

```
即時報價請求
  └── QuoteAdapter (quote_adapter.py)
        ├── [台股] TWSE MIS --> yfinance --> LastGoodCache --> yfinance_last_close
        └── [美股] yfinance --> LastGoodCache

歷史 K 線請求
  └── DataManager (data_manager.py)
        ├── Redis Cache (TTL 1h)
        ├── PostgreSQL 17
        └── External fallback: yfinance --> TWSE STOCK_DAY

法人 / 融資 / 財報
  └── DataManager
        ├── TWSE T86 (法人)
        ├── TWSE MI_MARGN (融資券)
        └── MOPS HTML (月營收 / 季報)
              └── Fallback: yfinance quarterly_financials
```

---

## 2. TWSE MIS API — 即時報價

| 項目 | 內容 |
|------|------|
| **用途** | 台股盤中即時報價（約 5 秒延遲） |
| **Base URL** | `https://mis.twse.com.tw/stock/api/getStockInfo.jsp` |
| **方法** | HTTP GET |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**請求參數：**

| 參數 | 說明 | 範例 |
|------|------|------|
| `ex_ch` | 交易所前綴_代碼.tw，多檔以 `\|` 分隔 | `tse_2330.tw\|otc_6669.tw` |
| `json` | 固定為 `"1"` | `1` |
| `_` | 毫秒時間戳（防快取） | `1719888000000` |

**代碼前綴規則：**
- 上市股：`tse_{code}.tw`
- 上櫃股：`otc_{code}.tw`（OTC_CODES 常數定義，見 `atlas/constants.py`）
- 未知時先試 `tse`，回傳 `msgArray` 為空再試 `otc`

**回應關鍵欄位（msgArray 中的 item）：**

| 欄位 | 說明 |
|------|------|
| `c` | 股票代碼 |
| `n` | 股票名稱 |
| `z` | 最新成交價（非交易時段為 `"-"`） |
| `y` | 昨日收盤價 |
| `o` | 開盤價 |
| `h` | 最高價 |
| `l` | 最低價 |
| `v` | 累計成交量（張，1 張=1000 股） |
| `a` | 五檔賣價（`_` 分隔） |
| `b` | 五檔買價（`_` 分隔） |
| `d` | 日期（YYYYMMDD） |
| `t` | 時間（HH:MM:SS） |

**TTL：300 秒（service_container）/ 快取 TTL 3600 秒（QuoteAdapter LastGoodCache）**

**已知限制：**
- 非交易時段 `z` 欄位為 `"-"`，系統自動 fallback 至 `y`（昨收）
- 批次上限：一次最多 50 檔（`_TWSE_BATCH_LIMIT = 50`）
- HTTP timeout：10 秒
- price=0 視為無效，觸發下一層 fallback

**Fallback：** yfinance → LastGoodCache → yfinance_last_close（取最近 5 日收盤）

---

## 3. TWSE T86 — 三大法人買賣超

| 項目 | 內容 |
|------|------|
| **用途** | 外資、投信、自營商當日買賣超（張） |
| **URL** | `https://www.twse.com.tw/fund/T86` |
| **方法** | HTTP GET |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**請求參數：**

| 參數 | 說明 | 範例 |
|------|------|------|
| `response` | 固定 `"json"` | `json` |
| `date` | 查詢日期 | `20260702` |
| `selectType` | `"ALLBUT0999"`（全部非零股） | `ALLBUT0999` |

**回應 data 陣列欄位索引（0-based）：**

| 索引 | 說明 |
|------|------|
| 0 | 股票代碼 |
| 2 | 外資買進（張） |
| 3 | 外資賣出（張） |
| 4 | 外資買賣超（張） |
| 5 | 投信買進（張） |
| 6 | 投信賣出（張） |
| 7 | 投信買賣超（張） |
| 8 | 自營商買進（張） |
| 9 | 自營商賣出（張） |
| 10 | 自營商買賣超（張） |

**TTL：1800 秒（30 分鐘）**

**已知限制：**
- 僅提供當日最新資料，歷史需逐日查詢
- 查詢歷史時每次請求需間隔 3 秒（rate limit 保護）
- 非交易日回應為空
- 數值含逗號（如 `"1,234"`），解析時需移除

**Fallback：** API 失敗時回傳全 0 值，`source` 標記為 `"unavailable"`

---

## 4. TWSE MI_MARGN — 融資融券

| 項目 | 內容 |
|------|------|
| **用途** | 台股融資餘額、融券餘額及增減 |
| **URL** | `https://www.twse.com.tw/exchangeReport/MI_MARGN` |
| **方法** | HTTP GET |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**請求參數：**

| 參數 | 說明 |
|------|------|
| `response` | 固定 `"json"` |
| `date` | 查詢日期（YYYYMMDD） |
| `selectType` | `"ALL"`（全部） |

**回應 creditList 陣列欄位索引（0-based）：**

| 索引 | 說明 |
|------|------|
| 0 | 股票代碼 |
| 5 | 融資增減（張） |
| 6 | 融資餘額（張） |
| 11 | 融券增減（張） |
| 12 | 融券餘額（張） |

**TTL：1800 秒（30 分鐘）**

**已知限制：**
- 僅提供當日或指定交易日資料
- 查詢歷史需逐日，每次間隔 3 秒
- 非交易日或假日回應 `creditList` 為空

**Fallback：** API 失敗時回傳全 0 值，`source` 標記為 `"unavailable"`

---

## 5. TWSE STOCK_DAY — 歷史日 K 線

| 項目 | 內容 |
|------|------|
| **用途** | 個股歷史月 K 線資料（作為 yfinance 失敗時的備援） |
| **URL** | `https://www.twse.com.tw/exchangeReport/STOCK_DAY` |
| **方法** | HTTP GET |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**請求參數：**

| 參數 | 說明 |
|------|------|
| `response` | 固定 `"json"` |
| `date` | 查詢月份第一天（YYYYMMDD） |
| `stockNo` | 股票代碼 |

**回應 data 陣列欄位索引（0-based）：**

| 索引 | 說明 |
|------|------|
| 0 | 日期（民國年，`YYY/MM/DD`，需加 1911 轉西元） |
| 1 | 成交股數 |
| 2 | 成交金額 |
| 3 | 開盤價 |
| 4 | 最高價 |
| 5 | 最低價 |
| 6 | 收盤價 |
| 7 | 漲跌價差 |
| 8 | 成交筆數 |

**TTL：DB 快取 3600 秒（Redis）**

**已知限制：**
- 每次 API 呼叫只回傳一個月資料，跨月需逐月查詢
- 每次查詢間隔 3 秒（rate limit 保護）
- HTTP timeout：30 秒
- 民國年格式需轉換（民國年 + 1911 = 西元年）
- 此資料源僅用於 yfinance 失敗時的 fallback

**Fallback 順序（DataManager）：** yfinance（優先）→ TWSE STOCK_DAY

---

## 6. TWSE STOCK_DAY_ALL — 全市場當日行情

| 項目 | 內容 |
|------|------|
| **用途** | 取得全台股當日收盤行情（選股掃描使用） |
| **URL** | `https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL` |
| **方法** | HTTP GET |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**請求參數：**

| 參數 | 說明 |
|------|------|
| `response` | 固定 `"json"` |
| `date` | 查詢日期（YYYYMMDD） |

**回應 data 陣列欄位索引（0-based）：**

| 索引 | 說明 |
|------|------|
| 0 | 股票代碼 |
| 2 | 成交股數 |
| 3 | 成交金額 |
| 4 | 開盤價 |
| 5 | 最高價 |
| 6 | 最低價 |
| 7 | 收盤價 |

**TTL：1800 秒（30 分鐘）**

**已知限制：**
- 非交易日回應 data 為空
- HTTP timeout：30 秒
- 只含上市股（上市部分），上櫃需另查 TPEx

---

## 7. TWSE newlisting — 新上市股票

| 項目 | 內容 |
|------|------|
| **用途** | 取得新上市/IPO 股票列表 |
| **URL** | `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2` |
| **方法** | HTTP GET（HTML 解析） |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**使用模組：** `atlas/strategy/ipo_module.py`

**已知限制：**
- HTML 格式，使用 `pd.read_html(StringIO(resp.text))` 解析
- 直接傳入字串給 `pd.read_html()` 在 Python 3.14 新版 pandas 會被當作檔案路徑而失敗，必須包在 `StringIO`

---

## 8. TPEx — 上櫃股票

| 項目 | 內容 |
|------|------|
| **用途** | 上櫃股票行情與資料（OTC 市場） |
| **Base URL** | `https://www.tpex.org.tw` |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**上櫃股識別：** `atlas/constants.py` 中的 `OTC_CODES` set 與 `is_otc(code)` 函式。

**yfinance 後綴：** 上市股用 `.TW`，上櫃股用 `.TWO`。

**TWSE MIS 前綴：** 上市股用 `tse_`，上櫃股用 `otc_`。

**已知限制：**
- TPEx 直接 API 整合仍在開發中（Phase 3）
- 目前上櫃股報價透過 TWSE MIS `otc_` 前綴取得
- 上櫃歷史資料透過 yfinance `.TWO` 後綴取得

---

## 9. MOPS — 公開資訊觀測站（季報 / 月營收）

### 9a. 月營收

| 項目 | 內容 |
|------|------|
| **用途** | 個股月營收、YoY 成長率、MoM 成長率 |
| **URL 格式** | `https://mops.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月份}_0.html` |
| **方法** | HTTP GET（HTML 解析） |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**範例 URL：** `https://mops.twse.com.tw/nas/t21/sii/t21sc03_115_6_0.html`（民國 115 年 6 月）

**回傳 dict 結構（`DataManager.fetch_revenue`）：**

| 鍵 | 型別 | 說明 |
|----|------|------|
| `code` | `str` | 股票代碼 |
| `year` | `int` | 西元年 |
| `month` | `int` | 月份 |
| `revenue` | `int` | 當月營業收入（千元） |
| `yoy_growth` | `float` | 年增率 % |
| `mom_growth` | `float` | 月增率 % |

**TTL：無快取（每次直接查詢）**

**已知限制：**
- HTML 格式，解析方式為 `pd.read_html(resp.text)` 掃描所有表格
- 必須使用 `StringIO` 包裝（Python 3.14 pandas 相容性）
- 民國年轉換：`tw_year = year - 1911`
- HTTP timeout：30 秒
- 表格格式可能依月份不同有細微差異

---

### 9b. 季報（損益表）

| 項目 | 內容 |
|------|------|
| **用途** | 個股季 EPS、毛利率、營業利益率、稅後淨利、營業收入 |
| **URL** | `https://mops.twse.com.tw/mops/web/ajax_t163sb04` |
| **方法** | HTTP POST（application/x-www-form-urlencoded） |
| **認證** | 無需 API Key |
| **費用** | 免費 |

**POST Body 格式：**
```
encodeURIComponent=1&step=1&firstin=1&off=1&co_id={code}&year={民國年}&season={季度}
```

**解析欄位：**

| HTML 標籤關鍵字 | 對應欄位 | 說明 |
|-----------------|----------|------|
| `每股盈餘` | `eps` | `float` |
| `營業收入` | `revenue` | `int`（千元） |
| `毛利率` | `gross_margin` | `float`（%） |
| `營益率` / `營業利益率` | `operating_margin` | `float`（%） |
| `稅後淨利` / `本期淨利` / `本期稅後淨利` | `net_income` | `int`（千元） |

**TTL：無快取（每次直接查詢）**

**已知限制：**
- HTML POST 介面，需 `StringIO` 包裝後以 `pd.read_html` 解析
- HTTP timeout：30 秒
- 表格格式可能依公司類型（上市/上櫃/金融業）而異
- 至少需解析到一個非 `None` 欄位才視為成功

**Fallback：** yfinance `ticker.quarterly_financials`

---

## 10. yfinance — 歷史資料與國際報價

| 項目 | 內容 |
|------|------|
| **用途** | 台股/美股歷史日 K 線、即時快照、基本面資料 |
| **套件版本** | yfinance（PyPI 最新版） |
| **認證** | 無需 API Key |
| **費用** | 免費（有請求頻率限制） |
| **延遲** | 美股 15-20 分鐘；台股盤後 |

**台股 Ticker 格式：**

| 類型 | 格式 | 範例 |
|------|------|------|
| 上市股 | `{code}.TW` | `2330.TW` |
| 上櫃股 | `{code}.TWO` | `6669.TWO` |
| 美股 | `{ticker}` | `AAPL` |

**主要用途：**

| 功能 | API | 說明 |
|------|-----|------|
| 歷史 K 線（主要來源） | `ticker.history(start, end, auto_adjust=False)` | DataManager fallback chain 第一順位 |
| 即時快照（台股備援） | `ticker.fast_info` | 取 `last_price`, `day_high`, `day_low`, `last_volume` 等 |
| 歷史資料快取備援 | `ticker.history(period="5d")` | QuoteAdapter 最終 fallback，取最近收盤 |
| 基本面（`fetch_financials`） | `ticker.info` + `ticker.quarterly_financials` | EPS、P/E、P/B、毛利率、營業利益率 |
| 季報 Fallback | `ticker.quarterly_financials` | MOPS 失敗時使用 |

**TTL（service_container）：**
- 歷史 K 線：600 秒（10 分鐘）
- 基本面：3600 秒（1 小時）

**已知限制：**
- 同步 API，所有呼叫透過 `asyncio.to_thread()` 或 `run_in_executor()` 執行
- 請求過於頻繁會被 Yahoo Finance 短暫封鎖（503 / 429）
- `fast_info` 無即時五檔買賣價，`bid_price`/`ask_price` 用 `last_price` 代替
- `yfinance` 不提供成交金額（`amount` 固定為 `0`）
- `adj_close` 欄位對應 `Adj Close`（除權息調整後收盤價）

**Fallback：** yfinance 失敗時最終依賴 `LastGoodCache`（Redis + in-memory）

---

## 11. Fallback Chain 彙整

### 即時報價 Fallback Chain

```
台股
  1. TWSE MIS API          -- 主要來源，約 5 秒延遲
  2. yfinance fast_info    -- TWSE 失敗時
  3. LastGoodCache         -- Redis (TTL 3600s) + in-memory fallback
  4. yfinance last_close   -- 取最近 5 日最後收盤（is_stale=True）

美股
  1. yfinance fast_info    -- 主要來源
  2. LastGoodCache         -- Redis (TTL 3600s) + in-memory fallback
```

### 歷史 K 線 Fallback Chain

```
1. Redis Cache             -- TTL 3600s
2. PostgreSQL 17           -- 本地儲存
3. yfinance                -- 外部來源第一優先
4. TWSE STOCK_DAY          -- 台股備援（逐月查詢，間隔 3s）
→ 全部失敗: raise AllSourcesExhaustedError
```

### 季報資料 Fallback Chain

```
1. MOPS ajax_t163sb04     -- 公開資訊觀測站（POST）
2. yfinance quarterly_financials -- MOPS 失敗時
→ 全部失敗: raise DataSourceError
```

---

## 12. Rate Limit 防護

| 資料源 | 防護措施 |
|--------|----------|
| TWSE T86 | 每日查詢間隔 `asyncio.sleep(3.0)` |
| TWSE MI_MARGN | 每日查詢間隔 `asyncio.sleep(3.0)` |
| TWSE STOCK_DAY | 每月查詢間隔 `asyncio.sleep(3.0)` |
| TWSE MIS | 批次上限 50 檔/次；HTTP timeout 10s |
| MOPS | HTTP timeout 30s；無自動重試 |
| yfinance | HTTP timeout 30s；同步轉非同步（`asyncio.to_thread`）；無自動重試 |
| QuoteAdapter | 全部 fallback 後仍失敗拋出 `QuoteUnavailableError` |

**LastGoodCache 機制：**
- 每次成功報價自動回寫 Redis（TTL 3600s）及 in-memory dict
- Redis 不可用時自動降級為 in-memory（不拋出例外）
- 取出快取報價時標記 `is_stale=True`，供上層判斷資料新鮮度

---

*文件最後更新：2026-07-02*
