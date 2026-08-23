"""GroceryService: business rules for GroceryItem, no Streamlit dependency."""
from __future__ import annotations

import json
from datetime import date

from ..domain.grocery import GroceryItem, GroceryState
from ..persistence.repository import Repository


class GroceryService:
    def __init__(self, repository: Repository[GroceryItem]) -> None:
        self._repo = repository

    def get_all(self) -> list[GroceryItem]:
        return self._repo.get_all()

    def mark_bought(self, item_id: str, bought_date: date) -> None:
        item = self._repo.get(item_id)
        if item is None:
            return
        item.mark_bought(bought_date)
        self._repo.update(item)

    def set_state(self, item_id: str, state: GroceryState) -> None:
        item = self._repo.get(item_id)
        if item is None:
            return
        item.set_state(state)
        self._repo.update(item)

    def add(self, name: str) -> GroceryItem:
        item = GroceryItem(name=name)
        self._repo.add(item)
        return item

    def remove(self, item_ids: list[str]) -> None:
        for item_id in item_ids:
            self._repo.delete(item_id)

    def apply_edits(self, item_id: str, changes: dict) -> None:
        item = self._repo.get(item_id)
        if item is None:
            return
        for field_name, value in changes.items():
            item.set_field(field_name, value)
        self._repo.update(item)

    def export_json(self) -> bytes:
        payload = [g.to_dict() for g in self._repo.get_all()]
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
