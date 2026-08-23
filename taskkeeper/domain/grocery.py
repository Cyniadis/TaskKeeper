"""Domain model for a grocery list item.

Kept pure like Task — display labels/icons for GroceryState live in the
UI layer (ui/groceries_tab.py), not here, unlike the original app where
STATE_TO_LABEL lived inside grocery.py itself.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import date
from enum import Enum
from typing import Any


class GroceryState(str, Enum):
    TO_BUY = "to_buy"
    BOUGHT = "bought"
    NOT_TO_BUY = "not_to_buy"


def _generate_id() -> str:
    return str(uuid.uuid4())[:8]


@dataclass
class GroceryItem:
    name: str
    state: str = GroceryState.TO_BUY.value
    id: str = field(default_factory=_generate_id)
    last_bought_date: date | None = None

    def mark_bought(self, bought_date: date) -> None:
        self.state = GroceryState.BOUGHT.value
        self.last_bought_date = bought_date

    def set_state(self, state: GroceryState) -> None:
        self.state = state.value

    def set_field(self, field_name: str, value: Any) -> None:
        if field_name == "last_bought_date":
            raise AttributeError("'last_bought_date' must be set via mark_bought(), not set_field().")
        editable = {f.name for f in fields(self) if not f.name.startswith("_")}
        if field_name not in editable:
            raise AttributeError(f"Unknown grocery field: {field_name!r}")
        setattr(self, field_name, value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "last_bought_date": self.last_bought_date.isoformat() if self.last_bought_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroceryItem":
        last = data.get("last_bought_date")
        return cls(
            name=data["name"],
            state=data.get("state", GroceryState.TO_BUY.value),
            id=data.get("id") or _generate_id(),
            last_bought_date=date.fromisoformat(last) if last else None,
        )
