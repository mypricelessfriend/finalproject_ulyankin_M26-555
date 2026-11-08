"""Бизнес-логика: регистрация, аутентификация, портфель, курсы, buy/sell."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

from .currencies import get_currency, is_known, list_codes
from .exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
)
from .models import Portfolio, User, Wallet
from .utils import (
    confirm_action,
    make_rate_cache,
    parse_iso_z,
    timed,
    to_iso_z,
)

USERS_FILE = "users.json"
PORTFOLIOS_FILE = "portfolios.json"
RATES_FILE = "rates.json"


# синглтоны
def _db() -> DatabaseManager:
    """Singleton DatabaseManager — единая точка доступа к JSON-хранилищу."""
    return DatabaseManager()


def _settings() -> SettingsLoader:
    """Singleton SettingsLoader — конфигурация проекта (секция [tool.valutatrade])."""
    return SettingsLoader()


def _rates_ttl() -> timedelta:
    return timedelta(seconds=int(_settings().get("RATES_TTL_SECONDS", 300)))


# Замыкание-кэш в памяти (TTL берётся из настроек при импорте)
_cached_get, _cached_put, _cached_clear = make_rate_cache(
    ttl_seconds=int(_settings().get("RATES_TTL_SECONDS", 300))
)


# users
def _load_users() -> list[dict]:
    return _db().load(USERS_FILE, [])


def _find_user(username: str) -> User | None:
    for row in _load_users():
        if row["username"] == username:
            return User.from_dict(row)
    return None


def _find_user_by_id(user_id: int) -> User | None:
    for row in _load_users():
        if row["user_id"] == int(user_id):
            return User.from_dict(row)
    return None


def _username_taken(username: str) -> bool:
    return any(u["username"] == username for u in _load_users())


@log_action(action="REGISTER")
def register_user(username: str, password: str) -> User:
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")
    if not isinstance(password, str) or len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")
    if _username_taken(username):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    holder: dict[str, User] = {}

    def _users_updater(data: list[dict]) -> list[dict]:
        new_id = max((u["user_id"] for u in data), default=0) + 1
        user_obj = User.create(new_id, username, password)
        data.append(user_obj.to_dict())
        holder["user"] = user_obj
        return data

    _db().mutate(USERS_FILE, _users_updater, default=[])
    user = holder["user"]

    _db().mutate(
        PORTFOLIOS_FILE,
        lambda data: data + [{"user_id": user.user_id, "wallets": {}}],
        default=[],
    )
    return user


@log_action(action="LOGIN")
def authenticate(username: str, password: str) -> User:
    user = _find_user(username)
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


# portfolio
def load_portfolio(user: User) -> Portfolio:
    portfolios = _db().load(PORTFOLIOS_FILE, [])
    for row in portfolios:
        if row["user_id"] == user.user_id:
            wallets = {
                code: Wallet.from_dict({"currency_code": code, **w})
                for code, w in row["wallets"].items()
            }
            return Portfolio(user.user_id, wallets, user=user)
    pf = Portfolio(user.user_id, user=user)
    save_portfolio(pf)
    return pf


def save_portfolio(portfolio: Portfolio) -> None:
    payload = {
        "user_id": portfolio.user_id,
        "wallets": {code: {"balance": w.balance} for code, w in portfolio.wallets.items()},
    }

    def _updater(data: list[dict]) -> list[dict]:
        for i, row in enumerate(data):
            if row["user_id"] == portfolio.user_id:
                data[i] = payload
                return data
        data.append(payload)
        return data

    _db().mutate(PORTFOLIOS_FILE, _updater, default=[])


# rates
_STUB_RATES = {
    "USD_USD": 1.0,
    "EUR_USD": 1.0786,
    "GBP_USD": 1.27,
    "BTC_USD": 59337.21,
    "ETH_USD": 3720.00,
    "RUB_USD": 0.01016,
}


def _stub_rate(frm: str, to: str) -> float | None:
    if frm == to:
        return 1.0
    direct = _STUB_RATES.get(f"{frm}_{to}")
    if direct is not None:
        return direct
    reverse = _STUB_RATES.get(f"{to}_{frm}")
    if reverse is not None:
        return 1.0 / reverse
    return None


def known_currencies() -> list[str]:
    return list_codes()


def is_known_currency(code: str) -> bool:
    return is_known(code)


def _read_rates_pairs() -> tuple[dict[str, dict], str | None]:
    """Читает rates.json в формате {pairs: {...}, last_refresh: str}."""
    raw: Any = _db().load(RATES_FILE, {})
    if not isinstance(raw, dict):
        return {}, None
    pairs = raw.get("pairs")
    if not isinstance(pairs, dict):
        # backward-compat: старый плоский формат
        pairs = {k: v for k, v in raw.items() if isinstance(v, dict) and "rate" in v}
    return pairs, raw.get("last_refresh")


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = parse_iso_z(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@timed
def get_rate(frm: str, to: str, force_refresh: bool = False) -> tuple[float, datetime]:
    """
    Возвращает (rate, updated_at).
    Бросает:
        CurrencyNotFoundError — неизвестный код валюты;
        ApiRequestError        — не удалось получить курс.
    """
    from_currency = get_currency(frm)
    to_currency = get_currency(to)
    from_code, to_code = from_currency.code, to_currency.code
    key = f"{from_code}_{to_code}"

    if not force_refresh:
        hit = _cached_get(key)
        if hit is not None:
            return hit

    pairs, _ = _read_rates_pairs()
    entry = pairs.get(key)
    if not force_refresh and isinstance(entry, dict):
        ts = _parse_ts(entry.get("updated_at"))
        if ts and (datetime.now(timezone.utc) - ts) < _rates_ttl():
            rate = float(entry["rate"])
            _cached_put(key, rate, ts)
            return rate, ts

    # fallback: встроенный заглушечный курс
    rate = _stub_rate(from_code, to_code)
    if rate is None:
        raise ApiRequestError(f"курс {from_code}→{to_code} недоступен")

    now = datetime.now(timezone.utc)
    entry_payload = {
        "rate": rate,
        "updated_at": to_iso_z(now),
        "source": "CoreStub",
    }

    def _updater(data: Any) -> dict:
        if not isinstance(data, dict):
            data = {}
        current_pairs = data.get("pairs")
        if not isinstance(current_pairs, dict):
            # backward-compat: перенос из плоского формата
            current_pairs = {k: v for k, v in data.items() if isinstance(v, dict) and "rate" in v}
        current_pairs[key] = entry_payload
        return {"pairs": current_pairs, "last_refresh": to_iso_z(now)}

    _db().mutate(RATES_FILE, _updater, default={})
    _cached_put(key, rate, now)
    return rate, now


# buy / sell
@log_action(action="BUY", verbose=True)
def buy_currency(
    user_id: int,
    currency_code: str,
    amount: float,
    base: str = "USD",
) -> dict:
    user = _find_user_by_id(user_id)
    if user is None:
        raise ValueError(f"Пользователь с id={user_id} не найден")

    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    code = get_currency(currency_code).code
    base_code = get_currency(base).code

    portfolio = load_portfolio(user)
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)

    before = wallet.balance
    wallet.deposit(amount)

    rate: float | None = None
    cost_base: float | None = None
    try:
        rate, _ = get_rate(code, base_code)
        cost_base = amount * rate
    except (CurrencyNotFoundError, ApiRequestError):
        pass

    base_charged: float | None = None
    if code != base_code and cost_base is not None:
        base_wallet = portfolio.get_wallet(base_code)
        if base_wallet is not None and base_wallet.balance >= cost_base:
            base_wallet.withdraw(cost_base)
            base_charged = cost_base

    save_portfolio(portfolio)
    return {
        "currency": code,
        "amount": amount,
        "before": before,
        "after": wallet.balance,
        "rate": rate,
        "base": base_code,
        "cost_base": cost_base,
        "base_charged": base_charged,
        "cost_usd": cost_base if base_code == "USD" else None,
        "usd_charged": base_charged if base_code == "USD" else None,
    }


@confirm_action("Подтвердить продажу? (y/n): ")
@log_action(action="SELL", verbose=True)
def sell_currency(
    user_id: int,
    currency_code: str,
    amount: float,
    base: str = "USD",
) -> dict | None:
    user = _find_user_by_id(user_id)
    if user is None:
        raise ValueError(f"Пользователь с id={user_id} не найден")

    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    code = get_currency(currency_code).code
    base_code = get_currency(base).code

    portfolio = load_portfolio(user)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            f"Добавьте валюту: она создаётся автоматически при первой покупке."
        )

    before = wallet.balance
    wallet.withdraw(amount)

    rate: float | None = None
    revenue_base: float | None = None
    try:
        rate, _ = get_rate(code, base_code)
        revenue_base = amount * rate
    except (CurrencyNotFoundError, ApiRequestError):
        pass

    base_credited: float | None = None
    if code != base_code and revenue_base is not None:
        base_wallet = portfolio.get_wallet(base_code) or portfolio.add_currency(base_code)
        base_wallet.deposit(revenue_base)
        base_credited = revenue_base

    save_portfolio(portfolio)
    return {
        "currency": code,
        "amount": amount,
        "before": before,
        "after": wallet.balance,
        "rate": rate,
        "base": base_code,
        "revenue_base": revenue_base,
        "base_credited": base_credited,
        "revenue_usd": revenue_base if base_code == "USD" else None,
        "usd_credited": base_credited if base_code == "USD" else None,
    }
