"""Настройка логов (формат, уровень, ротация) для actions и parser."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .infra.settings import SettingsLoader

ACTIONS_LOGGER_NAME = "valutatrade"
PARSER_LOGGER_NAME = "valutatrade.parser"

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_action_logger: Optional[logging.Logger] = None
_parser_logger: Optional[logging.Logger] = None

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


def _make_handler(
    log_path: Path,
    level: int,
    fmt_kind: str,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(_JsonFormatter() if fmt_kind == "json" else _TextFormatter())
    return handler


def setup_logging(force: bool = False) -> logging.Logger:
    """Логгер доменных действий (actions.log)."""
    global _action_logger
    if _action_logger is not None and not force:
        return _action_logger

    settings = SettingsLoader()
    log_path = Path(str(settings.get("LOG_PATH")))
    level_name = str(settings.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt_kind = str(settings.get("LOG_FORMAT", "text")).lower()

    logger = logging.getLogger(ACTIONS_LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    logger.addHandler(
        _make_handler(
            log_path,
            level,
            fmt_kind,
            int(settings.get("LOG_MAX_BYTES", 1_000_000)),
            int(settings.get("LOG_BACKUP_COUNT", 3)),
        )
    )
    logger.propagate = False

    _action_logger = logger
    return logger


def get_logger() -> logging.Logger:
    return _action_logger if _action_logger is not None else setup_logging()


def setup_parser_logging(force: bool = False) -> logging.Logger:
    """Отдельный логгер Parser Service (logs/parser.log)."""
    global _parser_logger
    if _parser_logger is not None and not force:
        return _parser_logger

    settings = SettingsLoader()
    log_path = _PROJECT_ROOT / "logs" / "parser.log"
    level_name = str(settings.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt_kind = str(settings.get("LOG_FORMAT", "text")).lower()

    logger = logging.getLogger(PARSER_LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    logger.addHandler(
        _make_handler(
            log_path,
            level,
            fmt_kind,
            int(settings.get("LOG_MAX_BYTES", 1_000_000)),
            int(settings.get("LOG_BACKUP_COUNT", 3)),
        )
    )
    logger.propagate = False

    _parser_logger = logger
    return logger


def get_parser_logger() -> logging.Logger:
    return _parser_logger if _parser_logger is not None else setup_parser_logging()