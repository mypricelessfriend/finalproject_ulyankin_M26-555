"""Singleton DatabaseManager: абстракция над JSON-хранилищем."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .settings import SettingsLoader


class DatabaseManager:
    _instance: DatabaseManager | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> DatabaseManager:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False  # type: ignore[attr-defined]
            cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        settings = SettingsLoader()
        self._data_dir = Path(settings.get("DATA_DIR"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True  # type: ignore[attr-defined]

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def path_for(self, filename: str) -> Path:
        return self._data_dir / filename

    # ---------- операции ----------
    def load(self, filename: str, default: Any = None) -> Any:
        path = self.path_for(filename)
        if not path.exists():
            return [] if default is None else default
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return [] if default is None else default

    def save(self, filename: str, data: Any) -> None:
        path = self.path_for(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".__tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def mutate(
        self,
        filename: str,
        updater: Callable[[Any], Any],
        default: Any = None,
    ) -> Any:
        """Атомарный read-modify-write."""
        data = self.load(filename, default)
        new_data = updater(data)
        self.save(filename, new_data)
        return new_data
