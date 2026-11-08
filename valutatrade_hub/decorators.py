"""Декоратор @log_action для доменных операций."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Optional

from .logging_config import get_logger

_SIG_CACHE: dict[Callable, inspect.Signature] = {}


def _get_sig(func: Callable) -> inspect.Signature:
    if func not in _SIG_CACHE:
        _SIG_CACHE[func] = inspect.signature(func)
    return _SIG_CACHE[func]


def _extract_context(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    try:
        bound = _get_sig(func).bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments
    except Exception:
        return ctx

    user = params.get("user")
    if user is not None:
        uid = getattr(user, "user_id", None)
        uname = getattr(user, "username", None)
        if uid is not None:
            ctx["user_id"] = uid
        if uname:
            ctx["username"] = uname

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


def _format_message(
    action: str,
    ctx: dict[str, Any],
    result: str,
    exc: Optional[BaseException] = None,
) -> str:
    parts = [action]
    if ctx.get("username"):
        parts.append(f"user='{ctx['username']}'")
    elif ctx.get("user_id") is not None:
        parts.append(f"user_id={ctx['user_id']}")
    if ctx.get("currency_code"):
        parts.append(f"currency='{ctx['currency_code']}'")
    if ctx.get("amount") is not None:
        try:
            parts.append(f"amount={float(ctx['amount']):.4f}")
        except (TypeError, ValueError):
            parts.append(f"amount={ctx['amount']}")
    if ctx.get("rate") is not None:
        try:
            parts.append(f"rate={float(ctx['rate']):.2f}")
        except (TypeError, ValueError):
            parts.append(f"rate={ctx['rate']}")
    if ctx.get("base"):
        parts.append(f"base='{ctx['base']}'")
    parts.append(f"result={result}")
    if exc is not None:
        parts.append(f"error_type={type(exc).__name__}")
        parts.append(f"error_message={str(exc)!r}")
    return " ".join(parts)


def log_action(
    func: Optional[Callable] = None,
    *,
    action: Optional[str] = None,
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
                logger.error(msg, extra={"action": action_name,
                                         "result": "ERROR",
                                         "error_type": type(exc).__name__,
                                         "error_message": str(exc),
                                         **ctx})
                raise

            extra: dict[str, Any] = {"action": action_name, "result": "OK", **ctx}
            if verbose and isinstance(result, dict):
                if "before" in result:
                    extra["before"] = result["before"]
                if "after" in result:
                    extra["after"] = result["after"]
            logger.info(_format_message(action_name, ctx, "OK"), extra=extra)
            return result

        return wrapper

    if isinstance(func, str):  # @log_action("BUY")
        return _make_named(func, verbose)
    if func is None:  # @log_action() / @log_action(action="BUY")
        return _make
    return _make(func)


def _make_named(name: str, verbose: bool) -> Callable:
    def decorator(f: Callable) -> Callable:
        return log_action(f, action=name, verbose=verbose)
    return decorator