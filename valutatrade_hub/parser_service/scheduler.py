"""Простой планировщик периодического обновления курсов."""

from __future__ import annotations

import threading
import time

from valutatrade_hub.logging_config import get_parser_logger

from .updater import RatesUpdater


class RatesScheduler:
    """
    Два режима:
      run_once()      — один проход (используется CLI update-rates);
      start()/stop()  — фоновый поток, обновление раз в interval секунд.
    """

    def __init__(
        self,
        updater: RatesUpdater,
        interval_seconds: int = 300,
        source: str | None = None,
    ) -> None:
        self.updater = updater
        self.interval_seconds = max(1, int(interval_seconds))
        self.source = source
        self.logger = get_parser_logger()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> dict:
        return self.updater.run_update(source=self.source)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="RatesScheduler", daemon=True)
        self._thread.start()
        self.logger.info(
            "Scheduler started (every %ss, source=%s)",
            self.interval_seconds,
            self.source or "all",
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        self.logger.info("Scheduler stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Scheduled update failed: %s", exc)
            # ждём interval или stop, что раньше
            if self._stop_event.wait(self.interval_seconds):
                break
        # финальный "прогрев" времени — только для тестов
        time.sleep(0)
