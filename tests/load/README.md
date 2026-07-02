# Atlas v5.0 — Load Testing

## 概覽

Atlas 的 UI 層是 Streamlit（WebSocket-based）。Load test 策略：

| 層次 | 工具 | 說明 |
|------|------|------|
| HTTP 層 | locust | 健康端點 + 頁面載入 + 靜態資源 |
| 並發掃描 | benchmark.py | ThreadPoolExecutor 模擬 10 並發股票掃描 |

> Streamlit 的互動行為（widget 更新、圖表渲染）需要 WebSocket 協議，locust 的 `HttpUser` 無法模擬完整互動。若需 WebSocket load test，改用 `websocket-client` 或 `artillery`。

---

## 安裝

```bash
pip install locust
# 或加入 dev dependencies
pip install -r requirements-dev.txt
```

確認 Atlas app 正在運行（預設 port 8503）：

```bash
# 啟動 Atlas
streamlit run atlas/app.py --server.port 8503

# 確認健康端點
curl http://localhost:8503/healthz
```

---

## 執行方式

### 互動模式（Web UI）

```bash
locust -f tests/load/locustfile.py --host http://localhost:8503
```

開啟瀏覽器 `http://localhost:8089`，設定 user 數與 spawn rate 後點 Start。

### Headless 模式（CI / 自動化）

```bash
# 20 users, spawn rate 5/s, 執行 60 秒，輸出 CSV
locust -f tests/load/locustfile.py \
       --host http://localhost:8503 \
       --headless \
       -u 20 \
       -r 5 \
       --run-time 60s \
       --csv tests/load/results/report \
       --html tests/load/results/report.html
```

### 壓力測試（找上限）

```bash
# 逐步增加到 100 users
locust -f tests/load/locustfile.py \
       --host http://localhost:8503 \
       --headless \
       -u 100 \
       -r 10 \
       --run-time 120s \
       --csv tests/load/results/stress
```

---

## User 類型

| Class | 行為 | Wait Time |
|-------|------|-----------|
| `StreamlitBrowserUser` | 模擬一般使用者：瀏覽頁面 + 健康檢查 + 靜態資源 | 1–5s |
| `APIHeavyUser` | 模擬監控 / 頻繁刷新的 power user | 0.5–2s |

Task 權重：
- `health_check` (weight=5) — 最高頻，模擬 uptime 監控
- `view_main_page` (weight=3)
- `browse_random_page` (weight=2)
- `fetch_static_asset` (weight=1)

---

## Baseline 指標（本機開發環境）

| 指標 | 目標值 | 說明 |
|------|--------|------|
| `/healthz` p50 | < 50 ms | 健康端點必須極快 |
| `/healthz` p95 | < 100 ms | |
| `GET /` p50 | < 500 ms | 首頁含 HTML + JS bundle |
| `GET /` p95 | < 1000 ms | |
| 失敗率 (20 users) | < 1% | 正常負載不應有錯誤 |
| 失敗率 (100 users) | < 5% | 壓力測試允許少量失敗 |
| RPS (20 users) | > 50 req/s | |

> 以上 baseline 基於單機 Docker 部署（PostgreSQL + Redis 同機）。生產環境（分離 DB）p95 應更低。

---

## 並發掃描 Benchmark

```bash
# 執行 benchmark（包含 concurrent scan 測試）
python scripts/benchmark.py
```

預期輸出（最後一段）：

```
Concurrent scan (10 workers, 10 stocks each)
  Total time  : XXX ms
  Per-worker  : XXX ms (median)
  p95 latency : XXX ms
  Throughput  : XX.X stocks/sec
```

目標：10 並發 × 10 股票掃描，總時間 < 5000 ms（p95 < 2000 ms）。

---

## 結果解讀

### CSV 輸出欄位

`report_stats.csv` 主要欄位：
- `Median Response Time` — 一般使用者感受到的延遲
- `95%ile` — 尾端延遲，SLA 通常以此為準
- `Requests/s` — 系統吞吐量
- `Failure Count` — 5xx 錯誤數

### 常見問題

| 症狀 | 可能原因 | 解法 |
|------|----------|------|
| p95 > 2000ms | DB 連線池耗盡 | 增加 `pool_size` |
| 失敗率上升 | Streamlit worker 數不足 | 調整 `server.maxUploadSize` 或改用多 worker |
| `/healthz` 回 502 | Streamlit 未啟動 | 確認 app process |
| RPS 停在低點 | GIL 瓶頸（CPU-bound） | 考慮 `--server.workers` 或拆分 API layer |

---

## 輸出目錄

```
tests/load/results/        # .gitignore 建議加入此目錄
├── report_stats.csv
├── report_stats_history.csv
├── report_failures.csv
└── report.html
```

建議在 `.gitignore` 加入：
```
tests/load/results/
```
