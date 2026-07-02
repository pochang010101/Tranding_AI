#!/usr/bin/env bash
# retrain_model.sh — ML 模型定期重訓腳本
# 用法：直接執行或由 scheduler 呼叫
# 假設工作目錄為專案根目錄（models/ 在根目錄下）

set -euo pipefail

# ── 設定 ──────────────────────────────────────────────────
MODELS_DIR="${MODELS_DIR:-/app/models}"
LOG_DIR="${LOG_DIR:-/app/logs}"
MODEL_FILE="${MODELS_DIR}/atlas_rf.joblib"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="${LOG_DIR}/retrain_${TIMESTAMP}.log"

# ── 初始化 ────────────────────────────────────────────────
mkdir -p "${MODELS_DIR}" "${LOG_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log "=== 開始 ML 模型重訓 ==="

# ── 備份舊模型 ────────────────────────────────────────────
if [ -f "${MODEL_FILE}" ]; then
    BACKUP_FILE="${MODELS_DIR}/atlas_rf_${TIMESTAMP}.joblib.bak"
    cp "${MODEL_FILE}" "${BACKUP_FILE}"
    log "舊模型已備份：${BACKUP_FILE}"
else
    log "無舊模型，跳過備份"
fi

# ── 執行訓練 ──────────────────────────────────────────────
log "啟動訓練：python scripts/train_model.py"

PYTHONPATH="${PYTHONPATH:-/app}" python scripts/train_model.py 2>&1 | tee -a "${LOG_FILE}"
EXIT_CODE=${PIPESTATUS[0]}

if [ "${EXIT_CODE}" -eq 0 ]; then
    log "訓練成功，模型已儲存至 ${MODEL_FILE}"
else
    log "ERROR: 訓練失敗 (exit code ${EXIT_CODE})"
    # 還原舊模型
    if [ -n "${BACKUP_FILE:-}" ] && [ -f "${BACKUP_FILE}" ]; then
        cp "${BACKUP_FILE}" "${MODEL_FILE}"
        log "已還原舊模型：${MODEL_FILE}"
    fi
    exit "${EXIT_CODE}"
fi

# ── 清理超過 30 天的舊備份模型 ────────────────────────────
find "${MODELS_DIR}" -name "atlas_rf_*.joblib.bak" -mtime +30 -print -delete \
    | while read -r f; do log "已刪除舊模型備份：${f}"; done

log "=== 重訓完成 ==="
