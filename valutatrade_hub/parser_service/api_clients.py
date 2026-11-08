"""Клиенты внешних API: CoinGecko и ExchangeRate-API."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import get_parser_logger

from .config import ParserConfig


class BaseApiClient(ABC):
    """Единый интерфейс: fetch_rates() -> {'BTC_USD': 59337.21, ...}."""

    SOURCE: str = ""
    SOURCE_KEY: str = ""

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.logger = get_parser_logger()
        self._last_meta: dict[str, Any] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]: ...

    def _meta(self, **extra: Any) -> dict:
        base = dict(self._last_meta)
        base.update(extra)
        return base


class CoinGeckoClient(BaseApiClient):
    SOURCE = "CoinGecko"
    SOURCE_KEY = "coingecko"

    def fetch_rates(self) -> dict[str, float]:
        ids = ",".join(
            self.config.CRYPTO_ID_MAP[c]
            for c in self.config.CRYPTO_CURRENCIES
            if c in self.config.CRYPTO_ID_MAP
        )
        if not ids:
            return {}

        params = {
            "ids": ids,
            "vs_currencies": self.config.BASE_CURRENCY.lower(),
        }

        started = time.perf_counter()
        try:
            resp = requests.get(
                self.config.COINGECKO_URL,
                params=params,
                timeout=self.config.REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            raise ApiRequestError(f"CoinGecko: сетевая ошибка ({exc})") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 429:
            raise ApiRequestError("CoinGecko: превышен лимит запросов (429)")
        if resp.status_code != 200:
            raise ApiRequestError(f"CoinGecko: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiRequestError(f"CoinGecko: некорректный JSON ({exc})") from exc

        base = self.config.BASE_CURRENCY
        result: dict[str, float] = {}
        for code in self.config.CRYPTO_CURRENCIES:
            coin_id = self.config.CRYPTO_ID_MAP.get(code)
            if not coin_id:
                continue
            entry = data.get(coin_id)
            if not isinstance(entry, dict):
                continue
            rate = entry.get(base.lower())
            if isinstance(rate, (int, float)) and not isinstance(rate, bool):
                result[f"{code}_{base}"] = float(rate)

        self.logger.info(
            "Fetched %d rates from CoinGecko in %d ms",
            len(result),
            elapsed_ms,
        )
        self._last_meta = {"request_ms": elapsed_ms, "status_code": resp.status_code}
        return result


class ExchangeRateApiClient(BaseApiClient):
    SOURCE = "ExchangeRate-API"
    SOURCE_KEY = "exchangerate"

    def fetch_rates(self) -> dict[str, float]:
        if not self.config.has_exchangerate_key():
            raise ApiRequestError(
                "ExchangeRate-API: не задан EXCHANGERATE_API_KEY — "
                "задайте переменную окружения EXCHANGERATE_API_KEY и повторите запуск"
            )

        url = (
            f"{self.config.EXCHANGERATE_API_URL}/"
            f"{self.config.EXCHANGERATE_API_KEY}/latest/"
            f"{self.config.BASE_CURRENCY}"
        )

        started = time.perf_counter()
        try:
            resp = requests.get(
                url,
                timeout=self.config.REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            raise ApiRequestError(f"ExchangeRate-API: сетевая ошибка ({exc})") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 429:
            raise ApiRequestError("ExchangeRate-API: превышен лимит запросов (429)")
        if resp.status_code == 401:
            raise ApiRequestError("ExchangeRate-API: неверный API-ключ (401)")
        if resp.status_code != 200:
            raise ApiRequestError(f"ExchangeRate-API: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiRequestError(f"ExchangeRate-API: некорректный JSON ({exc})") from exc

        if data.get("result") != "success":
            reason = data.get("error-type") or "unknown"
            raise ApiRequestError(f"ExchangeRate-API: {reason}")

        rates = data.get("rates") or {}
        base = self.config.BASE_CURRENCY
        result: dict[str, float] = {}
        for code in self.config.FIAT_CURRENCIES:
            rate = rates.get(code)
            if isinstance(rate, (int, float)) and not isinstance(rate, bool):
                result[f"{code}_{base}"] = float(rate)

        self.logger.info(
            "Fetched %d rates from ExchangeRate-API in %d ms",
            len(result),
            elapsed_ms,
        )
        self._last_meta = {"request_ms": elapsed_ms, "status_code": resp.status_code}
        return result
