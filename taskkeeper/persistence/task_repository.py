"""Repository builders for RecurringChore/OneTimeTask."""
from __future__ import annotations

import sqlite3

from ..domain.task import OneTimeTask, RecurringChore
from .repository import SQLiteRepository


def build_chore_repository(conn: sqlite3.Connection) -> SQLiteRepository[RecurringChore]:
    return SQLiteRepository(
        conn, "recurring_chores",
        to_dict=lambda c: c.to_dict(),
        from_dict=RecurringChore.from_dict,
    )


def build_onetime_repository(conn: sqlite3.Connection) -> SQLiteRepository[OneTimeTask]:
    return SQLiteRepository(
        conn, "onetime_tasks",
        to_dict=lambda t: t.to_dict(),
        from_dict=OneTimeTask.from_dict,
    )