"""Хранилище Parser Service: rates.json (кэш) и exchange_rates.json (история)."""

from __future__ import annotations

from typing import Any

from valutatrade_hub.infra.database import DatabaseManager

from .config import ParserConfig


class ParserStorage:
    RATES_FILE = "rates.json"
    HISTORY_FILE = "exchange_rates.json"

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self._db = DatabaseManager()

    # -------------------- кэш rates.json --------------------
    def read_cache(self) -> dict[str, Any]:
        """Возвращает {'pairs': {...}, 'last_refresh': str|None}."""
        data = self._db.load(self.RATES_FILE, {})
        if not isinstance(data, dict):
            data = {}
        pairs = data.get("pairs")
        if not isinstance(pairs, dict):
            # backward-compat: старый плоский формат
            pairs = {k: v for k, v in data.items() if isinstance(v, dict) and "rate" in v}
        return {
            "pairs": pairs,
            "last_refresh": data.get("last_refresh"),
        }

    def write_cache(self, pairs: dict[str, dict], last_refresh: str) -> None:
        """Перезапись кэша целиком: {pairs, last_refresh}."""
        self._db.save(
            self.RATES_FILE,
            {"pairs": pairs, "last_refresh": last_refresh},
        )

    def merge_cache(self, new_pairs: dict[str, dict], last_refresh: str) -> int:
        """
        Обновляет кэш по правилу «апдейт побеждает, если updated_at свежее».
        Возвращает число фактически обновлённых пар.
        """
        updated = [0]

        def _updater(data: Any) -> dict:
            if not isinstance(data, dict):
                data = {}
            pairs = data.get("pairs")
            if not isinstance(pairs, dict):
                pairs = {}
            for key, entry in new_pairs.items():
                old = pairs.get(key)
                if not isinstance(old, dict):
                    pairs[key] = entry
                    updated[0] += 1
                    continue
                if _is_newer(entry.get("updated_at"), old.get("updated_at")):
                    pairs[key] = entry
                    updated[0] += 1
            data = {"pairs": pairs, "last_refresh": last_refresh}
            return data

        self._db.mutate(self.RATES_FILE, _updater, default={})
        return updated[0]

    # -------------------- история exchange_rates.json --------------------
    def read_history(self) -> list[dict]:
        data = self._db.load(self.HISTORY_FILE, [])
        if isinstance(data, dict) and "records" in data:
            data = data["records"]
        return data if isinstance(data, list) else []

    def append_history(self, records: list[dict]) -> int:
        """Добавляет записи, дедупликация по id. Возвращает число добавленных."""
        added = [0]

        def _updater(data: Any) -> list:
            if isinstance(data, dict) and "records" in data:
                data = data["records"]
            if not isinstance(data, list):
                data = []
            existing = {r.get("id") for r in data if isinstance(r, dict)}
            for rec in records:
                rid = rec.get("id")
                if not rid or rid in existing:
                    continue
                data.append(rec)
                existing.add(rid)
                added[0] += 1
            return data

        self._db.mutate(self.HISTORY_FILE, _updater, default=[])
        return added[0]


def _is_newer(new_ts: str | None, old_ts: str | None) -> bool:
    """Сравнение двух ISO-UTC-строк."""

    if not new_ts:
        return False
    if not old_ts:
        return True
    try:
        new_dt = _parse_iso(new_ts)
        old_dt = _parse_iso(old_ts)
    except ValueError:
        return True
    return new_dt > old_dt


def _parse_iso(s: str):
    from datetime import datetime

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
