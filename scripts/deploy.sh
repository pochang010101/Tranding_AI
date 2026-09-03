#!/bin/bash
# Atlas Trading System v5.0 — 生產環境一鍵部署
# 用法：bash scripts/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker/docker-compose.prod.yml"

echo "=== Atlas v5.0 Production Deploy ==="
echo "Project: $PROJECT_DIR"
echo ""

# ── 1. 檢查 .env.prod ──────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env.prod" ]; then
    echo "ERROR: .env.prod 不存在"
    echo "  請從 .env.example 複製並填入生產環境密碼："
    echo "  cp .env.example .env.prod && vim .env.prod"
    exit 1
fi

# 檢查必要密碼
source "$PROJECT_DIR/.env.prod"
if [ -z "${ATLAS_DB_PASSWORD:-}" ]; then
    echo "ERROR: ATLAS_DB_PASSWORD 未設定（.env.prod）"
    exit 1
fi

# ── 2. 檢查 SSL 證書 ───────────────────────────────────
SSL_DIR="$PROJECT_DIR/docker/nginx/ssl"
if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
    echo "WARNING: SSL 證書不存在，生成自簽憑證（僅限測試）..."
    mkdir -p "$SSL_DIR"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_DIR/key.pem" \
        -out "$SSL_DIR/cert.pem" \
        -subj "/CN=atlas.local" \
        2>/dev/null
    echo "  自簽憑證已建立：$SSL_DIR/"
    echo "  生產環境請替換為 Let's Encrypt 或正式憑證"
    echo ""
fi

# ── 3. 確保 models 目錄存在 ─────────────────────────────
mkdir -p "$PROJECT_DIR/models"

# ── 4. 啟動 DB + Redis（先讓它們 healthy）─────────────
echo "--- Starting DB & Redis ---"
cd "$PROJECT_DIR"
docker compose -f "$COMPOSE_FILE" up -d db redis
echo "  等待服務啟動..."
sleep 5

# 等待 DB healthy
echo -n "  DB: "
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U atlas >/dev/null 2>&1; then
        echo "ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "TIMEOUT — 請檢查 DB 日誌"
        docker compose -f "$COMPOSE_FILE" logs db --tail=20
        exit 1
    fi
    sleep 2
done

# ── 5. DB Migration ────────────────────────────────────
echo "--- Running DB migration ---"
docker compose -f "$COMPOSE_FILE" up -d app
sleep 10
docker compose -f "$COMPOSE_FILE" exec -T app python -m alembic upgrade head || {
    echo "WARNING: Migration 可能失敗，請手動檢查"
}

# ── 6. Build & Deploy 全部服務 ──────────────────────────
echo "--- Building & deploying all services ---"
docker compose -f "$COMPOSE_FILE" up --build -d

# ── 7. 等待健康檢查 ────────────────────────────────────
echo "--- Waiting for health checks ---"
sleep 15

echo ""
echo "=== Service Status ==="
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "=== Deploy Complete ==="
echo "  HTTP:  http://localhost  (redirects to HTTPS)"
echo "  HTTPS: https://localhost"
echo "  Health: https://localhost/health"
echo ""
echo "  查看日誌：docker compose -f docker/docker-compose.prod.yml logs -f"
echo "  停止服務：docker compose -f docker/docker-compose.prod.yml down"
