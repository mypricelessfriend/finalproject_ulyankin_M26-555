"""Утилиты: хеширование, TTL-кэш, декораторы confirm/timed, замер времени."""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable


# хеширование
def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(8)


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
    """Возвращает (get, put, clear) — замыкание над приватным store."""
    store: dict[str, tuple[float, datetime]] = {}

    def get(key: str):
        entry = store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if datetime.now() - ts < timedelta(seconds=ttl_seconds):
            return value, ts
        return None

    def put(key: str, value: float, ts: datetime | None = None) -> None:
        store[key] = (value, ts or datetime.now())

    def clear() -> None:
        store.clear()

    return get, put, clear
