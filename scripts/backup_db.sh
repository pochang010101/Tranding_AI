#!/usr/bin/env bash
# backup_db.sh — PostgreSQL 備份腳本
# 用法：直接執行或由 scheduler 呼叫
# 環境變數：ATLAS_DB_HOST, ATLAS_DB_PORT, ATLAS_DB_NAME, ATLAS_DB_USER, ATLAS_DB_PASSWORD

set -euo pipefail

# ── 設定 ──────────────────────────────────────────────────
DB_HOST="${ATLAS_DB_HOST:-db}"
DB_PORT="${ATLAS_DB_PORT:-5432}"
DB_NAME="${ATLAS_DB_NAME:-atlas}"
DB_USER="${ATLAS_DB_USER:-atlas}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS=7

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/atlas_${TIMESTAMP}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

# ── 初始化 ────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log "=== 開始備份 DB: ${DB_NAME} @ ${DB_HOST}:${DB_PORT} ==="

# ── 執行備份 ──────────────────────────────────────────────
export PGPASSWORD="${ATLAS_DB_PASSWORD:-}"

pg_dump \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${DB_USER}" \
    --no-password \
    --format=plain \
    --no-owner \
    --no-acl \
    "${DB_NAME}" \
    | gzip -9 > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
log "備份完成：${BACKUP_FILE} (${BACKUP_SIZE})"

# ── 刪除超過保留天數的舊備份 ──────────────────────────────
log "清理超過 ${RETENTION_DAYS} 天的舊備份..."
find "${BACKUP_DIR}" -name "atlas_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete \
    | while read -r f; do log "已刪除：${f}"; done

REMAINING=$(find "${BACKUP_DIR}" -name "atlas_*.sql.gz" | wc -l)
log "目前保留備份數：${REMAINING}"
log "=== 備份完成 ==="
