"""Утилиты: хеширование, JSON-хранилище, декораторы, замыкание-кэш, замер времени."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(filename: str, default: Any = None) -> Any:
    _ensure_data_dir()
    path = DATA_DIR / filename
    if not path.exists():
        return [] if default is None else default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return [] if default is None else default


def save_json(filename: str, data: Any) -> None:
    _ensure_data_dir()
    path = DATA_DIR / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(8)


# декораторы
def log_action(func: Callable) -> Callable:
    """Логирует вызов функции в stderr (stdout не засоряем)."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"[{ts}] CALL {func.__name__}", file=sys.stderr)
        try:
            result = func(*args, **kwargs)
            print(f"[{ts}] OK   {func.__name__}", file=sys.stderr)
            return result
        except Exception as exc:
            print(f"[{ts}] FAIL {func.__name__}: {exc}", file=sys.stderr)
            raise
    return wrapper


def confirm_action(prompt: str = "Подтвердить? (y/n): ") -> Callable:
    """Запрашивает подтверждение. Можно обойти через skip_confirm=True."""
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
    """Замеряет время выполнения через time.perf_counter."""
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
def make_rate_cache(ttl_seconds: int = 300) -> tuple[Callable, Callable, Callable]:
    """
    Возвращает (get, put, clear). Внутри — замыкание над словарём store:
    get(key) -> (value, ts) | None
    put(key, value, ts=None)
    """
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