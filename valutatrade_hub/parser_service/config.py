"""Конфигурация Parser Service (API-ключ, URL, списки валют, пути)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ParserConfig:
    # API-ключ — только из переменной окружения, не из кода
    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY", "").strip()
    )

    # Эндпоинты
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    # Списки валют
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    # Пути (для отображения; фактическая запись — через DatabaseManager)
    RATES_FILE_PATH: str = "data/rates.json"
    HISTORY_FILE_PATH: str = "data/exchange_rates.json"

    # Сетевые параметры
    REQUEST_TIMEOUT: int = 10

    # ---------- helpers ----------
    def resolved_rates_path(self) -> Path:
        p = Path(self.RATES_FILE_PATH)
        return p if p.is_absolute() else (_PROJECT_ROOT / p)

    def resolved_history_path(self) -> Path:
        p = Path(self.HISTORY_FILE_PATH)
        return p if p.is_absolute() else (_PROJECT_ROOT / p)

    def has_exchangerate_key(self) -> bool:
        return bool(self.EXCHANGERATE_API_KEY)