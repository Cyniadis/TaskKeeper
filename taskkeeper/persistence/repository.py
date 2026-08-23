"""Generic Repository[T] over SQLite.

One interface every domain-object store implements — a new domain type
gets a repository by writing two small to_row/from_row functions and a
table name, not a whole new persistence module. Rows are stored as
`(id TEXT PRIMARY KEY, payload TEXT)`, where `payload` is the object's
own to_dict() serialized as JSON — keeps the schema generic while still
being real SQL (an index on `id`, real transactions on replace_all)
rather than the old "read the whole file, write the whole file" JSON
approach.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Callable, Generic, Protocol, TypeVar

T = TypeVar("T")


class Repository(Protocol[T]):
    def get_all(self) -> list[T]: ...
    def get(self, item_id: str) -> T | None: ...
    def add(self, item: T) -> None: ...
    def update(self, item: T) -> None: ...
    def delete(self, item_id: str) -> None: ...
    def replace_all(self, items: list[T]) -> None: ...


class SQLiteRepository(Generic[T]):
    """Concrete Repository[T] backed by one SQLite table."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        table: str,
        to_dict: Callable[[T], dict],
        from_dict: Callable[[dict], T],
    ) -> None:
        self._conn = connection
        self._table = table
        self._to_dict = to_dict
        self._from_dict = from_dict
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self._table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._conn.commit()

    def get_all(self) -> list[T]:
        rows = self._conn.execute(f"SELECT payload FROM {self._table}").fetchall()
        return [self._from_dict(json.loads(row[0])) for row in rows]

    def get(self, item_id: str) -> T | None:
        row = self._conn.execute(
            f"SELECT payload FROM {self._table} WHERE id = ?", (item_id,)
        ).fetchone()
        return self._from_dict(json.loads(row[0])) if row else None

    def add(self, item: T) -> None:
        payload = self._to_dict(item)
        self._conn.execute(
            f"INSERT INTO {self._table} (id, payload) VALUES (?, ?)",
            (payload["id"], json.dumps(payload)),
        )
        self._conn.commit()

    def update(self, item: T) -> None:
        payload = self._to_dict(item)
        self._conn.execute(
            f"UPDATE {self._table} SET payload = ? WHERE id = ?",
            (json.dumps(payload), payload["id"]),
        )
        self._conn.commit()

    def delete(self, item_id: str) -> None:
        self._conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))
        self._conn.commit()

    def replace_all(self, items: list[T]) -> None:
        with self._conn:
            self._conn.execute(f"DELETE FROM {self._table}")
            for item in items:
                payload = self._to_dict(item)
                self._conn.execute(
                    f"INSERT INTO {self._table} (id, payload) VALUES (?, ?)",
                    (payload["id"], json.dumps(payload)),
                )
