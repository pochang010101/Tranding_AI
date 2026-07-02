# Atlas Trading System — 生產環境部署指南

## 前置條件

| 項目 | 版本 |
|------|------|
| Docker Engine | 25+ |
| Docker Compose Plugin | 2.24+ |
| 伺服器 OS | Ubuntu 22.04 LTS 或同級 |
| Domain | 已解析 A record 至伺服器 IP |
| SSL 憑證 | Let's Encrypt (certbot) 或商業憑證 |

---

## 1. 環境變數設定

複製範本並填入生產值：

```bash
cp .env .env.prod
```

`.env.prod` 必填項目：

```env
ATLAS_DB_PASSWORD=<強密碼，至少 32 字元>
ATLAS_DB_USER=atlas
ATLAS_DB_NAME=atlas
ATLAS_REDIS_HOST=redis
ATLAS_DB_HOST=db

# 外部 API
FUGLE_API_KEY=<your_key>
OPENAI_API_KEY=<your_key>    # 若啟用 ML 功能

# 通知
LINE_NOTIFY_TOKEN=<your_token>
```

---

## 2. 首次啟動

```bash
# 在專案根目錄執行
docker compose -f docker/docker-compose.prod.yml --env-file .env.prod up -d --build

# 確認所有服務健康
docker compose -f docker/docker-compose.prod.yml ps
```

預期輸出：所有服務 Status 為 `healthy` 或 `running`。

### 初始化資料庫

```bash
# 執行 Alembic migration
docker compose -f docker/docker-compose.prod.yml --env-file .env.prod \
  exec app alembic upgrade head

# 匯入 seed data（首次部署）
docker compose -f docker/docker-compose.prod.yml --env-file .env.prod \
  exec app python scripts/seed_data.py
```

---

## 3. SSL 憑證設定

### 使用 Let's Encrypt（certbot）

```bash
# 安裝 certbot
sudo apt install -y certbot

# 取得憑證（nginx 必須已在監聽 80 port）
sudo certbot certonly --standalone \
  -d atlas.example.com \
  --email admin@example.com \
  --agree-tos

# 憑證位置
# /etc/letsencrypt/live/atlas.example.com/fullchain.pem
# /etc/letsencrypt/live/atlas.example.com/privkey.pem
```

取得憑證後：

1. 在 `docker/docker-compose.prod.yml` 取消 nginx volumes 的 SSL 憑證掛載註解
2. 在 `docker/nginx.conf` 取消 SSL server block 的註解，並填入正確 domain
3. 重新部署：`docker compose -f docker/docker-compose.prod.yml --env-file .env.prod up -d nginx`

### 自動續期

```bash
# 加入 crontab（每天 02:00 檢查）
echo "0 2 * * * certbot renew --quiet && docker compose -f /path/to/docker/docker-compose.prod.yml restart nginx" \
  | sudo tee -a /etc/crontab
```

---

## 4. 常用維護指令

```bash
# 查看所有服務狀態
docker compose -f docker/docker-compose.prod.yml ps

# 即時查看 app logs
docker compose -f docker/docker-compose.prod.yml logs -f app

# 查看 nginx access log
docker compose -f docker/docker-compose.prod.yml logs -f nginx

# 重啟單一服務（不停止其他服務）
docker compose -f docker/docker-compose.prod.yml restart app

# 更新應用程式（重新 build + 滾動重啟）
docker compose -f docker/docker-compose.prod.yml --env-file .env.prod \
  up -d --build app

# 進入 app container 執行指令
docker compose -f docker/docker-compose.prod.yml exec app bash

# 備份資料庫
docker compose -f docker/docker-compose.prod.yml exec db \
  pg_dump -U atlas atlas | gzip > backup_$(date +%Y%m%d).sql.gz

# 還原資料庫
gunzip -c backup_YYYYMMDD.sql.gz | \
  docker compose -f docker/docker-compose.prod.yml exec -T db \
  psql -U atlas atlas

# 停止所有服務（保留 volumes）
docker compose -f docker/docker-compose.prod.yml down

# 完全清除（含 volumes，資料會遺失）
docker compose -f docker/docker-compose.prod.yml down -v
```

---

## 5. 監控建議

- **應用健康**：`http://<domain>/_stcore/health`
- **Nginx 狀態**：`docker stats` 觀察各容器 CPU/Memory
- **DB 連線數**：`SELECT count(*) FROM pg_stat_activity;`
- **進階監控**：可加掛 Prometheus + Grafana（另行設定）

---

## 6. 常見問題

| 症狀 | 可能原因 | 解法 |
|------|----------|------|
| nginx 502 Bad Gateway | app 尚未健康 | `docker logs atlas-app-1` 查看啟動錯誤 |
| WebSocket 斷線 | proxy_read_timeout 太短 | 確認 nginx.conf `/_stcore/stream` 設定正確 |
| DB 連線失敗 | `.env.prod` 密碼未設定 | 確認 `ATLAS_DB_PASSWORD` 非空 |
| 靜態檔案 404 | volume 路徑錯誤 | 確認 `../app/static` 目錄存在 |
