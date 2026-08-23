"""Repository builder + demo seed data for GroceryItem."""
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


def seed_sample_groceries(repository: SQLiteRepository[GroceryItem]) -> None:
    if repository.get_all():
        return
    samples = [
        ("🥦 Tomates", "to_buy"),
        ("🧀 Fromage", "to_buy"),
        ("☕ Café", "to_buy"),
        ("🥛 Crème", "bought"),
        ("🍺 Bière blonde", "bought"),
        ("🥚 Œufs", "bought"),
        ("🧼 Papier toilette", "bought"),
        ("🥦 Gaspacho", "not_to_buy"),
    ]
    for name, state in samples:
        repository.add(GroceryItem(name=name, state=state))
