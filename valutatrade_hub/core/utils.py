"""Утилиты: хеширование, TTL-кэш, декораторы confirm/timed, замер времени."""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import wraps


# хеширование
def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(8)


# ISO-UTC
def to_iso_z(dt: datetime | None = None) -> str:
    """Формат 2025-10-10T12:00:00Z (UTC, без микросекунд)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(value: str) -> datetime:
    """Обратный к to_iso_z: 2025-10-10T12:00:00Z -> aware datetime."""
    if not isinstance(value, str):
        raise TypeError("Ожидалась строка с ISO-временем")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# декораторы
def confirm_action(prompt: str = "Подтвердить? (y/n): ") -> Callable:
    """Запрашивает подтверждение. Обход: skip_confirm=True / VALUTA_YES=1."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, skip_confirm: bool = False, **kwargs):
            if skip_confirm or os.environ.get("VALUTA_YES") == "1":
                return func(*args, **kwargs)
            try:
                answer = input(prompt).strip().lower()
            except EOFError:
                answer = "n"
            if answer not in ("y", "yes", "д", "да"):
                print("Действие отменено")
                return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def timed(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"[timed] {func.__name__}: {elapsed_ms:.2f} ms", file=sys.stderr)

    return wrapper


# замыкание: TTL-кэш курсов
def make_rate_cache(ttl_seconds: int = 300):
    """Возвращает (get, put, clear) — замыкание над приватным store.

    Внутри всё работает с aware-UTC датами, чтобы не смешивать naive/aware.
    """
    store: dict[str, tuple[float, datetime]] = {}

    def get(key: str):
        entry = store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if datetime.now(timezone.utc) - ts < timedelta(seconds=ttl_seconds):
            return value, ts
        return None

    def put(key: str, value: float, ts: datetime | None = None) -> None:
        store[key] = (value, ts or datetime.now(timezone.utc))

    def clear() -> None:
        store.clear()

    return get, put, clear
