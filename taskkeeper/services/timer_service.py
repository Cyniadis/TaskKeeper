"""TimerService: play/pause/reset/elapsed, backed by SettingsStore.

Unlike raw st.session_state, this survives a page refresh within the
same DB — the SQLite connection is the source of truth, session_state
never is.
"""
from __future__ import annotations

from datetime import datetime

from ..persistence.settings_store import SettingsStore

_KEY_RUNNING = "timer_running"
_KEY_START = "timer_start_time"
_KEY_ACCUM = "timer_elapsed_accum"


class TimerService:
    def __init__(self, settings: SettingsStore) -> None:
        self._settings = settings

    def is_running(self) -> bool:
        return bool(self._settings.get(_KEY_RUNNING, False))

    def start(self) -> None:
        self._settings.set(_KEY_START, datetime.now().isoformat())
        self._settings.set(_KEY_RUNNING, True)

    def pause(self) -> None:
        if self.is_running():
            accum = self._settings.get(_KEY_ACCUM, 0.0) + self._current_segment_seconds()
            self._settings.set(_KEY_ACCUM, accum)
        self._settings.set(_KEY_RUNNING, False)
        self._settings.set(_KEY_START, None)

    def reset(self) -> None:
        self._settings.set(_KEY_RUNNING, False)
        self._settings.set(_KEY_START, None)
        self._settings.set(_KEY_ACCUM, 0.0)

    def elapsed_seconds(self) -> int:
        accum = self._settings.get(_KEY_ACCUM, 0.0)
        if self.is_running():
            accum += self._current_segment_seconds()
        return int(accum)

    def _current_segment_seconds(self) -> float:
        start_raw = self._settings.get(_KEY_START)
        if not start_raw:
            return 0.0
        return (datetime.now() - datetime.fromisoformat(start_raw)).total_seconds()
