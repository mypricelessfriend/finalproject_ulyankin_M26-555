"""RatesUpdater: оркестрация опроса клиентов, объединение, сохранение."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import get_parser_logger

from .api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from .config import ParserConfig
from .storage import ParserStorage


def _now_iso_z() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _record_id(from_code: str, to_code: str, ts: str) -> str:
    return f"{from_code}_{to_code}_{ts}"


class RatesUpdater:
    """Точка входа логики парсинга."""

    def __init__(
        self,
        config: ParserConfig,
        storage: ParserStorage,
        clients: Optional[Iterable[BaseApiClient]] = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.clients: list[BaseApiClient] = (
            list(clients) if clients is not None
            else [CoinGeckoClient(config), ExchangeRateApiClient(config)]
        )
        self.logger = get_parser_logger()

    # -------------------- public --------------------
    def run_update(self, source: Optional[str] = None) -> dict:
        """
        Опросить клиентов (опционально — только source),
        сохранить историю и обновить кэш.

        Возвращает сводку:
            {
              'total_rates': int,
              'errors': [ {'source': str, 'error': str}, ... ],
              'last_refresh': str,
              'sources_ok': [str, ...],
              'sources_failed': [str, ...],
            }
        """
        selected = self._select_clients(source)
        self.logger.info(
            "Starting rates update (source=%s, clients=%s)",
            source or "all",
            [c.SOURCE for c in selected],
        )

        merged: dict[str, float] = {}
        per_source_meta: dict[str, dict] = {}
        errors: list[dict] = []
        sources_ok: list[str] = []

        for client in selected:
            self.logger.info("Fetching from %s...", client.SOURCE)
            try:
                rates = client.fetch_rates()
            except ApiRequestError as exc:
                self.logger.error("Failed to fetch from %s: %s", client.SOURCE, exc)
                errors.append({"source": client.SOURCE, "error": str(exc)})
                continue
            except Exception as exc:  # неожиданные — тоже не валим весь процесс
                self.logger.exception(
                    "Unexpected error from %s: %s", client.SOURCE, exc
                )
                errors.append({"source": client.SOURCE, "error": str(exc)})
                continue

            self.logger.info(
                "Fetching from %s... OK (%d rates)", client.SOURCE, len(rates)
            )
            for key, rate in rates.items():
                merged[key] = rate
                per_source_meta[key] = {
                    **client._meta(),
                    "source": client.SOURCE,
                    "raw_id": self._raw_id_for(client, key),
                }
            sources_ok.append(client.SOURCE)

        now_ts = _now_iso_z()
        last_refresh = now_ts

        # сохранить историю
        history_records = self._build_history(merged, per_source_meta, now_ts)
        added = self.storage.append_history(history_records)
        self.logger.info(
            "History: %d new records appended (total candidates: %d)",
            added,
            len(history_records),
        )

        # обновить кэш
        pairs = self._build_cache_pairs(merged, per_source_meta, now_ts)
        if pairs:
            self.storage.merge_cache(pairs, last_refresh)
            self.logger.info(
                "Writing %d rates to %s...",
                len(pairs),
                self.config.RATES_FILE_PATH,
            )
        else:
            self.logger.warning("No rates were fetched; cache not updated")

        return {
            "total_rates": len(pairs),
            "errors": errors,
            "last_refresh": last_refresh,
            "sources_ok": sources_ok,
            "sources_failed": [e["source"] for e in errors],
        }

    # -------------------- internals --------------------
    def _select_clients(self, source: Optional[str]) -> list[BaseApiClient]:
        if not source:
            return self.clients
        key = source.strip().lower()
        selected = [c for c in self.clients if c.SOURCE_KEY == key]
        if not selected:
            raise ApiRequestError(f"Неизвестный источник '{source}'")
        return selected

    @staticmethod
    def _raw_id_for(client: BaseApiClient, pair_key: str) -> Optional[str]:
        # pair_key = 'BTC_USD'; для CoinGecko вернём 'bitcoin'
        if isinstance(client, CoinGeckoClient):
            from_code = pair_key.split("_", 1)[0]
            return client.config.CRYPTO_ID_MAP.get(from_code)
        return None

    def _build_history(
        self,
        merged: dict[str, float],
        meta: dict[str, dict],
        ts: str,
    ) -> list[dict]:
        records = []
        for key, rate in merged.items():
            parts = key.split("_", 1)
            if len(parts) != 2:
                continue
            from_code, to_code = parts
            m = meta.get(key, {})
            records.append(
                {
                    "id": _record_id(from_code, to_code, ts),
                    "from_currency": from_code,
                    "to_currency": to_code,
                    "rate": rate,
                    "timestamp": ts,
                    "source": m.get("source", "unknown"),
                    "meta": {
                        "raw_id": m.get("raw_id"),
                        "request_ms": m.get("request_ms"),
                        "status_code": m.get("status_code"),
                    },
                }
            )
        return records

    def _build_cache_pairs(
        self,
        merged: dict[str, float],
        meta: dict[str, dict],
        ts: str,
    ) -> dict[str, dict]:
        pairs = {}
        for key, rate in merged.items():
            pairs[key] = {
                "rate": rate,
                "updated_at": ts,
                "source": meta.get(key, {}).get("source", "unknown"),
            }
        return pairs