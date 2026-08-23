"""Durable key/value settings store.

Deliberately separate from the task/grocery repositories — settings have
a different lifecycle (edited via a widget, never imported/exported as
a backup) from domain data. Values are stored as JSON so any JSON-safe
type round-trips without extra casting logic here.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


class SettingsStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()
