"""Настройка логов (формат, уровень, ротация)."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade"
_logger: Optional[logging.Logger] = None

_EXTRA_FIELDS = (
    "action", "user_id", "username", "currency_code",
    "amount", "rate", "base", "result",
    "error_type", "error_message", "before", "after",
)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        return f"{record.levelname} {ts} {record.getMessage()}"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(force: bool = False) -> logging.Logger:
    global _logger
    if _logger is not None and not force:
        return _logger

    settings = SettingsLoader()
    log_path = Path(str(settings.get("LOG_PATH")))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level_name = str(settings.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt_kind = str(settings.get("LOG_FORMAT", "text")).lower()

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=int(settings.get("LOG_MAX_BYTES", 1_000_000)),
        backupCount=int(settings.get("LOG_BACKUP_COUNT", 3)),
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_JsonFormatter() if fmt_kind == "json" else _TextFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    return _logger if _logger is not None else setup_logging()