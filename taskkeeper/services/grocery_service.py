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

    def import_json(self, raw_bytes: bytes) -> list[GroceryItem]:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {exc}") from exc
        try:
            raw_data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"File is not valid JSON: {exc}") from exc
        if not isinstance(raw_data, list):
            raise ValueError("The file must contain a JSON array of grocery items.")
        if not raw_data:
            raise ValueError("The backup file is empty.")
        items: list[GroceryItem] = []
        seen_ids: set[str] = set()
        for idx, item in enumerate(raw_data):
            label = f"Item #{idx}"
            if not isinstance(item, dict):
                raise ValueError(f"{label}: expected a JSON object, got {type(item).__name__}.")
            if "id" not in item:
                raise ValueError(f"{label}: missing 'id'.")
            item_id = str(item["id"])
            if item_id in seen_ids:
                raise ValueError(f"{label}: duplicate id {item_id}.")
            if "name" not in item or not str(item.get("name", "")).strip():
                raise ValueError(f"{label} (id={item_id}): missing or empty 'name'.")
            try:
                grocery = GroceryItem.from_dict({**item, "id": item_id})
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"{label} ('{item.get('name', '?')}'): {exc}") from exc
            seen_ids.add(grocery.id)
            items.append(grocery)
        return items

    def restore_from_backup(self, items: list[GroceryItem]) -> None:
        self._repo.replace_all(items)