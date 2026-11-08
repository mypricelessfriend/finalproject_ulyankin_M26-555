"""Иерархия валют: Currency (ABC) → FiatCurrency / CryptoCurrency + реестр."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Абстрактный базовый класс валюты."""

    def __init__(self, name: str, code: str) -> None:
        self.name = name
        self.code = code

    # ---------- свойства с валидацией ----------
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя валюты не может быть пустым")
        self._name = value.strip()

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Код валюты должен быть строкой")
        normalized = value.strip().upper()
        if not 2 <= len(normalized) <= 5:
            raise ValueError("Код валюты должен содержать 2–5 символов")
        if any(ch.isspace() for ch in normalized):
            raise ValueError("Код валюты не должен содержать пробелов")
        if not normalized.isalnum():
            raise ValueError("Код валюты должен состоять из букв/цифр")
        self._code = normalized

    # ---------- контракт ----------
    @abstractmethod
    def get_display_info(self) -> str:
        """Строковое представление для UI/логов."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self._code!r}, name={self._name!r})"


class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны/зоны эмиссии."""

    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта: алгоритм и рыночная капитализация."""

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        super().__init__(name, code)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым")
        if not isinstance(market_cap, (int, float)) or market_cap < 0:
            raise ValueError("market_cap должен быть неотрицательным числом")
        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {_fmt_mcap(self.market_cap)})"
        )


def _fmt_mcap(value: float) -> str:
    """1.12e12 (без плюса и ведущих нулей в экспоненте)."""
    if value == 0:
        return "0"
    text = f"{value:.2e}"  # 1.12e+12
    mantissa, exp = text.split("e")
    sign = ""
    if exp.startswith(("+", "-")):
        sign = "" if exp[0] == "+" else "-"
        exp = exp[1:]
    exp = exp.lstrip("0") or "0"
    return f"{mantissa}e{sign}{exp}"


# --------------------------- реестр ---------------------------
_REGISTRY: dict[str, Currency] = {}


def _register(currency: Currency) -> None:
    _REGISTRY[currency.code] = currency


_register(FiatCurrency("US Dollar", "USD", "United States"))
_register(FiatCurrency("Euro", "EUR", "Eurozone"))
_register(FiatCurrency("British Pound", "GBP", "United Kingdom"))
_register(FiatCurrency("Russian Ruble", "RUB", "Russia"))
_register(CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12))
_register(CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11))


def get_currency(code: str) -> Currency:
    """Фабрика: получить валюту по коду или бросить CurrencyNotFoundError."""
    if not isinstance(code, str) or not code.strip():
        raise CurrencyNotFoundError(code if isinstance(code, str) else str(code))
    key = code.strip().upper()
    currency = _REGISTRY.get(key)
    if currency is None:
        raise CurrencyNotFoundError(key)
    return currency


def is_known(code: str) -> bool:
    try:
        get_currency(code)
        return True
    except CurrencyNotFoundError:
        return False


def list_codes() -> list[str]:
    return sorted(_REGISTRY.keys())


def all_currencies() -> list[Currency]:
    return list(_REGISTRY.values())
