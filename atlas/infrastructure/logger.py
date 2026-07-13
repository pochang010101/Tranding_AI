"""結構化日誌設定 — JSON 檔案輸出 + 彩色 Console。"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "atlas.log"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_DEFAULT_LEVEL = "INFO"

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """JSON 格式 log formatter。"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            entry["extra"] = record.extra_data
        return json.dumps(entry, ensure_ascii=False, default=str)


class _ColorFormatter(logging.Formatter):
    """Console 彩色 formatter。"""

    _COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:<8}{self._RESET}"
        return super().format(record)


def setup_logging(debug: bool = False) -> None:
    """設定全域日誌（Console + JSON 檔案輪轉）。"""
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    env_level = os.getenv("ATLAS_LOG_LEVEL", "").upper()
    level_name = env_level if env_level in ("DEBUG", "INFO", "WARNING", "ERROR") else _DEFAULT_LEVEL
    if debug:
        level_name = "DEBUG"
    level = getattr(logging, level_name)

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(
        _ColorFormatter("%(asctime)s %(levelname)s %(name)s — %(message)s", datefmt="%H:%M:%S")
    )
    root.addHandler(console)

    # File handler (JSON)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter())
    root.addHandler(file_handler)

    # 降低第三方庫噪音
    for noisy in ("httpx", "httpcore", "urllib3", "yfinance", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).info("Logging initialized (level=%s)", level_name)


def get_logger(name: str) -> logging.Logger:
    """取得 logger 快捷函式。"""
    return logging.getLogger(name)
