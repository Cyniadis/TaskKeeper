"""Repository builder for GroceryItem."""
from __future__ import annotations

import sqlite3

from ..domain.grocery import GroceryItem
from .repository import SQLiteRepository


def build_grocery_repository(conn: sqlite3.Connection) -> SQLiteRepository[GroceryItem]:
    return SQLiteRepository(
        conn, "groceries",
        to_dict=lambda g: g.to_dict(),
        from_dict=GroceryItem.from_dict,
    )