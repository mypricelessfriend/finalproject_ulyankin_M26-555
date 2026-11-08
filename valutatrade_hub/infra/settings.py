"""Singleton SettingsLoader: конфигурация проекта.

Реализация Singleton через __new__:
    — проще читать и понимать, чем метакласс;
    — не тянет зависимостей и дополнительных модулей;
    — гарантирует один экземпляр на процесс (в т.ч. при повторных импортах).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULTS: dict[str, Any] = {
    "DATA_DIR": str(_PROJECT_ROOT / "data"),
    "LOG_PATH": str(_PROJECT_ROOT / "logs" / "actions.log"),
    "RATES_TTL_SECONDS": 300,
    "DEFAULT_BASE_CURRENCY": "USD",
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "text",
    "LOG_MAX_BYTES": 1_000_000,
    "LOG_BACKUP_COUNT": 3,
}

_PATH_KEYS = {"DATA_DIR", "LOG_PATH"}


class SettingsLoader:
    _instance: Optional["SettingsLoader"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "SettingsLoader":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False  # type: ignore[attr-defined]
            cls._instance = inst
        return cls._instance

    def __init__(self, config_path: Optional[Path] = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self._config_path = config_path
        self._config: dict[str, Any] = {}
        self._load()
        self._initialized = True  # type: ignore[attr-defined]

    # загрузка
    def _load(self) -> None:
        cfg: dict[str, Any] = dict(DEFAULTS)
        cfg.update(self._read_pyproject_section())
        cfg.update(self._read_json_override())
        for key in _PATH_KEYS:
            value = cfg.get(key)
            if value:
                p = Path(str(value))
                if not p.is_absolute():
                    p = (_PROJECT_ROOT / p).resolve()
                cfg[key] = str(p)
        self._config = cfg

    def _read_pyproject_section(self) -> dict[str, Any]:
        pyproject = self._config_path or (_PROJECT_ROOT / "pyproject.toml")
        if not pyproject.exists():
            return {}
        try:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        section = data.get("tool", {}).get("valutatrade", {})
        return dict(section) if isinstance(section, dict) else {}

    def _read_json_override(self) -> dict[str, Any]:
        path = _PROJECT_ROOT / "data" / "config.json"
        if not path.exists():
            return {}
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # публичный API
    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def reload(self) -> "SettingsLoader":
        self._load()
        return self

    def all(self) -> dict[str, Any]:
        return dict(self._config)