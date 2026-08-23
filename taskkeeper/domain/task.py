"""Domain model: Task (base) with RecurringChore and OneTimeTask subclasses.

No dependency on Streamlit, pandas, or any storage mechanism — only the
shape and behaviour of a task. Mirrors the invariants of the original
tasktracker/task.py: due_date/done_date are read-only from outside this
module, every transition goes through a named method so the
"cancelled xor manually-rescheduled" invariant can't be bypassed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields, asdict
from datetime import date, datetime
from enum import Enum
from typing import Any


# -- category -----------------------------------------------------------

class Category(str, Enum):
    """A task's household area. Drives the icon + filter chips in the UI."""
    KITCHEN = "kitchen"
    LAUNDRY = "laundry"
    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    GARDEN = "garden"
    CAR = "car"
    PET = "pet"
    ADMIN = "admin"
    HOBBY = "hobby"
    OTHER = "other"

    @property
    def icon(self) -> str:
        return _CATEGORY_ICONS[self]

    @property
    def label(self) -> str:
        return _CATEGORY_LABELS[self]


_CATEGORY_ICONS: dict[Category, str] = {
    Category.KITCHEN: "🍴",
    Category.LAUNDRY: "👕",
    Category.BEDROOM: "🛏",
    Category.LIVING_ROOM: "🛋️",
    Category.GARDEN: "🌱",
    Category.CAR: "🚘",
    Category.PET: "😺",
    Category.ADMIN: "📞",
    Category.HOBBY: "⚔",
    Category.OTHER: "🔧",
}

_CATEGORY_LABELS: dict[Category, str] = {
    Category.KITCHEN: "Cuisine",
    Category.LAUNDRY: "Linge",
    Category.BEDROOM: "Chambre",
    Category.LIVING_ROOM: "Salon",
    Category.GARDEN: "Jardin",
    Category.CAR: "Voiture",
    Category.PET: "Animaux",
    Category.ADMIN: "Admin",
    Category.HOBBY: "Loisir",
    Category.OTHER: "Autre",
}


# -- frequency (recurring chores only) -----------------------------------

class Period(str, Enum):
    DAY = "jour"
    WEEK = "semaine"
    MONTH = "mois"
    YEAR = "an"

    @property
    def length_in_days(self) -> float:
        return {
            Period.DAY: 1.0,
            Period.WEEK: 7.0,
            Period.MONTH: 30.4,
            Period.YEAR: 365.0,
        }[self]


@dataclass(frozen=True)
class Frequency:
    count: int = 1
    period: Period = Period.DAY

    @classmethod
    def parse(cls, text: str | None) -> "Frequency":
        if text:
            try:
                count_str, period_str = text.lower().split("x", 1)
                return cls(count=int(count_str), period=Period(period_str))
            except (ValueError, KeyError):
                pass
        return cls()

    @property
    def days(self) -> float:
        return self.period.length_in_days / self.count

    def __str__(self) -> str:
        return f"{self.count}x{self.period.value}"


# -- shared state ---------------------------------------------------------

class TaskDueDateState(str, Enum):
    NORMAL = "normal"
    CANCELLED = "cancelled"
    MANUALLY_RESCHEDULED = "rescheduled"
    ELIGIBLE = "eligible"


@dataclass
class TaskState:
    """Status as of today. `completed` is independent of `due_date_state`
    — a task can be both manually-scheduled today and completed today."""
    completed: bool = False
    due_date_state: TaskDueDateState = TaskDueDateState.NORMAL

    @classmethod
    def from_dict(cls, data: dict) -> "TaskState":
        return cls(
            completed=data.get("completed", False),
            due_date_state=TaskDueDateState(data.get("due_date_state", TaskDueDateState.NORMAL.value)),
        )


def _generate_id() -> str:
    return str(uuid.uuid4())[:8]


# -- base -------------------------------------------------------------

@dataclass
class Task:
    """Common surface both RecurringChore and OneTimeTask carry.

    Not an ABC on purpose here (kept a plain dataclass for simplicity in
    this mockup — the architecture doc sketches it as an abstract base;
    a real implementation would enforce complete()/uncomplete()/to_dict()
    as abstract methods).
    """
    name: str
    category: Category = Category.OTHER
    duration: int = 0
    id: str = field(default_factory=_generate_id)
    state: TaskState = field(default_factory=TaskState)
    _due_date: date | None = None
    _done_date: date | None = None

    @property
    def due_date(self) -> date | None:
        return self._due_date

    @property
    def done_date(self) -> date | None:
        return self._done_date

    def is_completed_on(self, current_date: date) -> bool:
        return self._done_date is not None and self._done_date == current_date

    def is_completed(self) -> bool:
        return self.state.completed

    def is_cancelled(self) -> bool:
        return self.state.due_date_state == TaskDueDateState.CANCELLED

    def is_manually_rescheduled(self) -> bool:
        return self.state.due_date_state == TaskDueDateState.MANUALLY_RESCHEDULED

    def set_field(self, field_name: str, value: Any) -> None:
        """Generic setter shared by both subtypes' grid-edit callbacks.

        due_date/done_date are intentionally excluded — those go through
        dedicated methods (set_due_date/schedule_for/etc.) so the
        due-date-state invariants can't be bypassed by a stray grid edit.
        """
        if field_name in ("due_date", "done_date"):
            raise AttributeError(
                f"{field_name!r} must be set via a dedicated method, not set_field()."
            )
        editable = {f.name for f in fields(self) if not f.name.startswith("_")}
        if field_name not in editable:
            raise AttributeError(f"Unknown field: {field_name!r}")
        setattr(self, field_name, value)


# -- recurring chore -----------------------------------------------------

@dataclass
class RecurringChore(Task):
    """A task that repeats on a frequency and competes for the daily time
    budget via the priority-knapsack selector (see domain/selector.py)."""
    frequency: str = "1xjour"
    priority: float = 0.0
    initial_priority: float = 0.0

    def __post_init__(self) -> None:
        self._pre_complete_priority: float | None = self.priority
        self._pre_complete_done_date: date | None = self._done_date

    @property
    def frequency_obj(self) -> Frequency:
        return Frequency.parse(self.frequency)

    def get_next_due_date(self, current_date: date):
        from datetime import timedelta
        return current_date + timedelta(days=self.frequency_obj.days)

    def set_due_date(self, new_date: date | None) -> None:
        self._due_date = new_date
        if self.state.due_date_state == TaskDueDateState.CANCELLED:
            self.state.due_date_state = TaskDueDateState.NORMAL

    def set_done_date(self, new_date: date | None) -> None:
        self._done_date = new_date

    def cancel(self) -> None:
        self.state.due_date_state = TaskDueDateState.CANCELLED
        self._due_date = None

    def manually_reschedule(self, current_date: date) -> None:
        self._due_date = current_date
        self.state.due_date_state = TaskDueDateState.MANUALLY_RESCHEDULED

    def set_next_due_date(self, from_date: date | None = None) -> None:
        if from_date is None:
            from_date = self._due_date
        self.set_due_date(self.get_next_due_date(from_date))

    def complete(self, completion_date: date) -> None:
        self._pre_complete_priority = self.priority
        self._pre_complete_done_date = self._done_date
        self._done_date = completion_date
        self.priority = self.initial_priority
        self.state.completed = True

    def uncomplete(self) -> None:
        self._done_date = self._pre_complete_done_date
        if self._pre_complete_priority is not None:
            self.priority = self._pre_complete_priority
        self.state.completed = False

    def increment_priority(self, amount: float = 0.5) -> None:
        self.priority += amount

    def is_eligible(self) -> bool:
        return self.state.due_date_state == TaskDueDateState.ELIGIBLE

    def reset_state(self) -> None:
        if not self.is_cancelled():
            completed = self.state.completed
            self.state = TaskState(completed=completed, due_date_state=TaskDueDateState.NORMAL)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "duration": self.duration,
            "frequency": self.frequency,
            "priority": self.priority,
            "initial_priority": self.initial_priority,
            "due_date": self._due_date.isoformat() if self._due_date else None,
            "done_date": self._done_date.isoformat() if self._done_date else None,
            "state": {"completed": self.state.completed, "due_date_state": self.state.due_date_state.value},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecurringChore":
        due = data.get("due_date")
        done = data.get("done_date")
        chore = cls(
            name=data["name"],
            category=Category(data.get("category", Category.OTHER.value)),
            duration=data.get("duration", 0),
            id=data.get("id") or _generate_id(),
            state=TaskState.from_dict(data.get("state", {})),
            frequency=data.get("frequency", "1xjour"),
            priority=data.get("priority", 0.0),
            initial_priority=data.get("initial_priority", 0.0),
        )
        chore._due_date = date.fromisoformat(due) if due else None
        chore._done_date = date.fromisoformat(done) if done else None
        return chore


# -- one-time task ---------------------------------------------------------

@dataclass
class OneTimeTask(Task):
    """A task with no recurrence and no priority/knapsack participation.
    `due_date` here means exactly one thing: scheduled for today or not."""

    def schedule_for(self, current_date: date) -> None:
        self._due_date = current_date
        self.state.due_date_state = TaskDueDateState.MANUALLY_RESCHEDULED

    def unschedule(self) -> None:
        self._due_date = None
        self.state.due_date_state = TaskDueDateState.NORMAL

    def complete(self, completion_date: date) -> None:
        self._done_date = completion_date
        self.state.completed = True

    def uncomplete(self) -> None:
        self._done_date = None
        self.state.completed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "duration": self.duration,
            "due_date": self._due_date.isoformat() if self._due_date else None,
            "done_date": self._done_date.isoformat() if self._done_date else None,
            "state": {"completed": self.state.completed, "due_date_state": self.state.due_date_state.value},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OneTimeTask":
        due = data.get("due_date")
        done = data.get("done_date")
        task = cls(
            name=data["name"],
            category=Category(data.get("category", Category.OTHER.value)),
            duration=data.get("duration", 0),
            id=data.get("id") or _generate_id(),
            state=TaskState.from_dict(data.get("state", {})),
        )
        task._due_date = date.fromisoformat(due) if due else None
        task._done_date = date.fromisoformat(done) if done else None
        return task
