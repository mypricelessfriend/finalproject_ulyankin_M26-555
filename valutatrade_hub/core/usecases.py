"""Бизнес-логика: регистрация, аутентификация, портфель, курсы, buy/sell."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .models import Portfolio, User, Wallet
from .utils import (
    confirm_action,
    load_json,
    log_action,
    make_rate_cache,
    save_json,
    timed,
)

USERS_FILE = "users.json"
PORTFOLIOS_FILE = "portfolios.json"
RATES_FILE = "rates.json"

MAX_RATE_AGE = timedelta(minutes=5)

# Замыкание-кэш в памяти (ttl=300 c)
_cached_get, _cached_put, _cached_clear = make_rate_cache(ttl_seconds=300)


# users
def _load_users() -> list[dict]:
    return load_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    save_json(USERS_FILE, users)


def _find_user(username: str) -> Optional[User]:
    for row in _load_users():
        if row["username"] == username:
            return User.from_dict(row)
    return None


def _username_taken(username: str) -> bool:
    return any(u["username"] == username for u in _load_users())


@log_action
def register_user(username: str, password: str) -> User:
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")
    if not isinstance(password, str) or len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")
    if _username_taken(username):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    users = _load_users()
    new_id = max((u["user_id"] for u in users), default=0) + 1
    user = User.create(new_id, username, password)
    users.append(user.to_dict())
    _save_users(users)

    portfolios = load_json(PORTFOLIOS_FILE, [])
    portfolios.append({"user_id": new_id, "wallets": {}})
    save_json(PORTFOLIOS_FILE, portfolios)
    return user


@log_action
def authenticate(username: str, password: str) -> User:
    user = _find_user(username)
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


# portfolio
def _load_portfolios() -> list[dict]:
    return load_json(PORTFOLIOS_FILE, [])


def _save_portfolios(portfolios: list[dict]) -> None:
    save_json(PORTFOLIOS_FILE, portfolios)


def load_portfolio(user: User) -> Portfolio:
    for row in _load_portfolios():
        if row["user_id"] == user.user_id:
            wallets = {
                code: Wallet.from_dict({"currency_code": code, **w})
                for code, w in row["wallets"].items()
            }
            return Portfolio(user.user_id, wallets, user=user)
    # если портфеля нет — создаём и сохраняем пустой
    pf = Portfolio(user.user_id, user=user)
    save_portfolio(pf)
    return pf


def save_portfolio(portfolio: Portfolio) -> None:
    portfolios = _load_portfolios()
    payload = {
        "user_id": portfolio.user_id,
        "wallets": {
            code: {"balance": w.balance}
            for code, w in portfolio.wallets.items()
        },
    }
    for i, row in enumerate(portfolios):
        if row["user_id"] == portfolio.user_id:
            portfolios[i] = payload
            break
    else:
        portfolios.append(payload)
    _save_portfolios(portfolios)


# rates
_STUB_RATES = {
    "USD_USD": 1.0,
    "EUR_USD": 1.0786,
    "BTC_USD": 59337.21,
    "ETH_USD": 3720.00,
    "RUB_USD": 0.01016,
}


def _load_rates() -> dict:
    return load_json(RATES_FILE, {})


def _save_rates(rates: dict) -> None:
    save_json(RATES_FILE, rates)


def _stub_rate(frm: str, to: str) -> Optional[float]:
    if frm == to:
        return 1.0
    direct = _STUB_RATES.get(f"{frm}_{to}")
    if direct is not None:
        return direct
    reverse = _STUB_RATES.get(f"{to}_{frm}")
    if reverse is not None:
        return 1.0 / reverse
    return None


def known_currencies() -> set[str]:
    codes: set[str] = set()
    keys = list(_STUB_RATES) + [k for k in _load_rates() if "_" in k and k.isupper()]
    for key in keys:
        parts = key.split("_")
        if len(parts) == 2 and all(parts):
            codes.update(parts)
    return codes


def is_known_currency(code: str) -> bool:
    return bool(code) and code.upper() in known_currencies()


@timed
def get_rate(frm: str, to: str, force_refresh: bool = False) -> tuple[float, datetime]:
    """
    Возвращает (rate, updated_at).
    1) Сначала смотрим in-memory кэш (замыкание).
    2) Потом rates.json (если моложе MAX_RATE_AGE).
    3) Иначе — «запрос к Parser Service» (заглушка) с обновлением файла и кэша.
    """
    frm, to = (frm or "").upper(), (to or "").upper()
    if not frm or not to:
        raise ValueError("Коды валют не могут быть пустыми")

    key = f"{frm}_{to}"
    if not force_refresh:
        hit = _cached_get(key)
        if hit is not None:
            return hit  # (rate, ts)

    rates = _load_rates()
    if not force_refresh and key in rates:
        try:
            ts = datetime.fromisoformat(rates[key]["updated_at"])
        except (KeyError, ValueError):
            ts = None
        if ts and (datetime.now() - ts) < MAX_RATE_AGE:
            rate = float(rates[key]["rate"])
            _cached_put(key, rate, ts)
            return rate, ts

    rate = _stub_rate(frm, to)
    if rate is None:
        raise LookupError(f"Курс {frm}→{to} недоступен. Повторите попытку позже.")

    now = datetime.now()
    rates[key] = {"rate": rate, "updated_at": now.isoformat()}
    rates["last_refresh"] = now.isoformat()
    rates["source"] = "StubParser"
    _save_rates(rates)
    _cached_put(key, rate, now)
    return rate, now


# buy / sell
@log_action
def buy_currency(user: User, currency_code: str, amount: float) -> dict:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    code = (currency_code or "").upper().strip()
    if not code:
        raise ValueError("Код валюты не может быть пустым")

    portfolio = load_portfolio(user)
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)

    before = wallet.balance
    wallet.deposit(amount)

    rate: Optional[float] = None
    cost_usd: Optional[float] = None
    try:
        rate, _ = get_rate(code, "USD")
        cost_usd = amount * rate
    except LookupError:
        pass

    # при покупке сумма списывается с USD-кошелька.
    # Делаем best-effort: если USD-кошелёк есть и баланса хватает — списываем.
    usd_charged: Optional[float] = None
    if code != "USD" and cost_usd is not None:
        usd_wallet = portfolio.get_wallet("USD")
        if usd_wallet is not None and usd_wallet.balance >= cost_usd:
            usd_wallet.withdraw(cost_usd)
            usd_charged = cost_usd

    save_portfolio(portfolio)
    return {
        "currency": code,
        "amount": amount,
        "before": before,
        "after": wallet.balance,
        "rate": rate,
        "cost_usd": cost_usd,
        "usd_charged": usd_charged,
    }


@confirm_action("Подтвердить продажу? (y/n): ")
@log_action
def sell_currency(user: User, currency_code: str, amount: float) -> dict | None:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    code = (currency_code or "").upper().strip()
    if not code:
        raise ValueError("Код валюты не может быть пустым")

    portfolio = load_portfolio(user)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            f"Добавьте валюту: она создаётся автоматически при первой покупке."
        )

    before = wallet.balance
    wallet.withdraw(amount)

    rate: Optional[float] = None
    revenue_usd: Optional[float] = None
    try:
        rate, _ = get_rate(code, "USD")
        revenue_usd = amount * rate
    except LookupError:
        pass

    # при продаже сумма начисляется на USD-кошелёк
    usd_credited: Optional[float] = None
    if code != "USD" and revenue_usd is not None:
        usd_wallet = portfolio.get_wallet("USD") or portfolio.add_currency("USD")
        usd_wallet.deposit(revenue_usd)
        usd_credited = revenue_usd

    save_portfolio(portfolio)
    return {
        "currency": code,
        "amount": amount,
        "before": before,
        "after": wallet.balance,
        "rate": rate,
        "revenue_usd": revenue_usd,
        "usd_credited": usd_credited,
    }