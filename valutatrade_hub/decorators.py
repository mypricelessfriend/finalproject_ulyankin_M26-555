"""Декоратор @log_action для доменных операций."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from .logging_config import get_logger

_SIG_CACHE: dict[Callable, inspect.Signature] = {}


def _get_sig(func: Callable) -> inspect.Signature:
    if func not in _SIG_CACHE:
        _SIG_CACHE[func] = inspect.signature(func)
    return _SIG_CACHE[func]


def _resolve_username(user_id: int) -> str | None:
    """Ленивая попытка достать username по user_id (без циклических импортов)."""
    try:
        from .core.usecases import _find_user_by_id

        user_obj = _find_user_by_id(int(user_id))
        return user_obj.username if user_obj else None
    except Exception:
        return None


def _extract_context(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    try:
        bound = _get_sig(func).bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments
    except Exception:
        return ctx

    # username/user_id: поддерживаем оба варианта сигнатуры
    user = params.get("user")
    if user is not None:
        uid = getattr(user, "user_id", None)
        uname = getattr(user, "username", None)
        if uid is not None:
            ctx["user_id"] = uid
        if uname:
            ctx["username"] = uname
    elif "user_id" in params and params["user_id"] is not None:
        uid = params["user_id"]
        ctx["user_id"] = uid
        uname = _resolve_username(int(uid))
        if uname:
            ctx["username"] = uname
    elif "username" in params and isinstance(params["username"], str):
        ctx["username"] = params["username"]

    # Доменные поля, извлекаемые из сигнатуры
    for key, out_key in (
        ("currency_code", "currency_code"),
        ("currency", "currency_code"),
        ("amount", "amount"),
        ("rate", "rate"),
        ("base", "base"),
        ("frm", "from"),
        ("to", "to"),
    ):
        value = params.get(key)
        if value is not None:
            ctx.setdefault(out_key, value)
    return ctx


def _fmt_amount(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_rate(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_message(
    action: str,
    ctx: dict[str, Any],
    result: str,
    exc: BaseException | None = None,
    verbose_extra: dict[str, Any] | None = None,
) -> str:
    parts = [action]
    if ctx.get("username"):
        parts.append(f"user='{ctx['username']}'")
    elif ctx.get("user_id") is not None:
        parts.append(f"user_id={ctx['user_id']}")
    if ctx.get("currency_code"):
        parts.append(f"currency='{ctx['currency_code']}'")
    if ctx.get("amount") is not None:
        parts.append(f"amount={_fmt_amount(ctx['amount'])}")
    if ctx.get("rate") is not None:
        parts.append(f"rate={_fmt_rate(ctx['rate'])}")
    if ctx.get("base"):
        parts.append(f"base='{ctx['base']}'")
    parts.append(f"result={result}")

    if verbose_extra:
        if "before" in verbose_extra:
            parts.append(f"before={_fmt_amount(verbose_extra['before'])}")
        if "after" in verbose_extra:
            parts.append(f"after={_fmt_amount(verbose_extra['after'])}")

    if exc is not None:
        parts.append(f"error_type={type(exc).__name__}")
        parts.append(f"error_message={str(exc)!r}")
    return " ".join(parts)


def log_action(
    func: Callable | None = None,
    *,
    action: str | None = None,
    verbose: bool = False,
) -> Callable:
    """
    Использование:
        @log_action
        def sell_currency(...): ...

        @log_action(action="BUY", verbose=True)
        def buy_currency(...): ...
    """

    def _make(f: Callable) -> Callable:
        action_name = (action or f.__name__).upper()

        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger()
            ctx = _extract_context(f, args, kwargs)

            try:
                result = f(*args, **kwargs)
            except Exception as exc:
                msg = _format_message(action_name, ctx, "ERROR", exc)
                logger.error(
                    msg,
                    extra={
                        "action": action_name,
                        "result": "ERROR",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        **ctx,
                    },
                )
                raise

            # Обогащаем контекст из результата функции
            verbose_extra: dict[str, Any] = {}
            if isinstance(result, dict):
                if "currency" in result and "currency_code" not in ctx:
                    ctx["currency_code"] = result["currency"]
                for key in ("amount", "rate", "base"):
                    if key in result and key not in ctx:
                        ctx[key] = result[key]
                if verbose:
                    if "before" in result:
                        verbose_extra["before"] = result["before"]
                    if "after" in result:
                        verbose_extra["after"] = result["after"]

            # По ТЗ: если rate есть, а base не указан явно — подразумеваем USD
            if ctx.get("rate") is not None and not ctx.get("base"):
                ctx["base"] = "USD"

            extra: dict[str, Any] = {"action": action_name, "result": "OK", **ctx}
            if verbose_extra:
                extra.update(verbose_extra)

            msg = _format_message(action_name, ctx, "OK", verbose_extra=verbose_extra)
            logger.info(msg, extra=extra)
            return result

        return wrapper

    if isinstance(func, str):
        return _make_named(func, verbose)
    if func is None:
        return _make
    return _make(func)


def _make_named(name: str, verbose: bool) -> Callable:
    def decorator(f: Callable) -> Callable:
        return log_action(f, action=name, verbose=verbose)

    return decorator
