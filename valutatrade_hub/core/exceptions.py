"""Пользовательские исключения ValutaTrade Hub."""

from __future__ import annotations


class ValutaTradeError(Exception):
    """Базовое исключение домена."""


class CurrencyNotFoundError(ValutaTradeError):
    """Неизвестная валюта (нет в реестре)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class InsufficientFundsError(ValutaTradeError):
    """Недостаточно средств на кошельке."""

    def __init__(self, available: float, required: float, code: str) -> None:
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {_fmt(available)} {code}, "
            f"требуется {_fmt(required)} {code}"
        )


class ApiRequestError(ValutaTradeError):
    """Сбой при обращении к внешнему API / Parser Service."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


def _fmt(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text or "0"
