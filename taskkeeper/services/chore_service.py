"""ChoreService (RecurringChore) and OneTimeTaskService — the business
rules layer, with no Streamlit dependency. Every method takes/returns
plain domain objects, so both are unit-testable without a Streamlit
runtime.
"""
from __future__ import annotations

import json
from datetime import date
from enum import Enum

from ..domain.selector import compute_daily_chores, eligibility, Eligibility
from ..domain.task import Category, OneTimeTask, RecurringChore
from ..persistence.change_log import ChangeLog
from ..persistence.repository import Repository

_FIELD_LABELS = {
    "name": "Name",
    "category": "Category",
    "frequency": "Frequency",
    "priority": "Priority",
    "initial_priority": "Initial priority",
    "duration": "Duration",
    "due_date": "Due date",
    "done_date": "Done date",
    "prereq_id": "Prerequisite",
    "prereq_window_days": "Prerequisite window",
}


def _serialize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _deserialize_for_field(chore: RecurringChore, field_name: str, raw: str):
    if field_name == "category":
        return Category(raw) if raw else Category.OTHER
    current = getattr(chore, field_name, None)
    if isinstance(current, bool):
        return raw == "True"
    if isinstance(current, float):
        return float(raw) if raw != "" else 0.0
    if isinstance(current, int):
        return int(raw) if raw != "" else 0
    return raw


def _detect_cycle(
    chore_id: str,
    new_prereq_id: str,
    all_chores: list[RecurringChore],
) -> bool:
    """Return True if setting chore_id's prereq to new_prereq_id would
    create a cycle (A → B → … → A). Uses a simple DFS on the prereq graph."""
    index = {c.id: c for c in all_chores}
    # Simulate the new edge
    visited: set[str] = set()
    current = new_prereq_id
    while current:
        if current == chore_id:
            return True  # cycle detected
        if current in visited:
            break
        visited.add(current)
        node = index.get(current)
        current = node.prereq_id if node else None
    return False


class ChoreService:
    """Everything the UI needs to do with RecurringChore."""

    def __init__(self, repository: Repository[RecurringChore], change_log: ChangeLog | None = None) -> None:
        self._repo = repository
        self._change_log = change_log

    def get_all(self) -> list[RecurringChore]:
        return self._repo.get_all()

    def get_today(self, current_date: date) -> list[RecurringChore]:
        all_chores = self._repo.get_all()
        chore_index = {c.id: c for c in all_chores}
        return [
            c for c in all_chores
            if not c.is_cancelled() and (
                c.is_completed_on(current_date)
                or c.is_manually_rescheduled()
                or eligibility(c, current_date, chore_index) is not Eligibility.NOT_ELIGIBLE
            )
        ]

    def regenerate_today(self, current_date: date, daily_limit: int) -> list[RecurringChore]:
        all_chores = self._repo.get_all()
        pre_selected = [c for c in all_chores if c.is_manually_rescheduled()]
        selected = compute_daily_chores(all_chores, current_date, daily_limit, pre_selected)
        for chore in selected:
            self._repo.update(chore)
        return selected

    def toggle_complete(self, chore_id: str, current_date: date) -> None:
        chore = self._repo.get(chore_id)
        if chore is None:
            return
        if chore.is_completed_on(current_date):
            chore.uncomplete()
        else:
            chore.complete(current_date)
        self._repo.update(chore)

    def reschedule(self, chore_id: str, new_date: date) -> None:
        chore = self._repo.get(chore_id)
        if chore is None:
            return
        old_due = chore.due_date
        chore.manually_reschedule(new_date)
        self._record_due_date_change(chore_id, old_due, chore.due_date)
        self._repo.update(chore)

    def cancel(self, chore_id: str) -> None:
        chore = self._repo.get(chore_id)
        if chore is None:
            return
        old_due = chore.due_date
        chore.cancel()
        self._record_due_date_change(chore_id, old_due, chore.due_date)
        self._repo.update(chore)

    def add(
        self, name: str, category: Category, frequency: str, duration: int, initial_priority: float
    ) -> RecurringChore:
        chore = RecurringChore(
            name=name, category=category, duration=duration,
            frequency=frequency, priority=initial_priority, initial_priority=initial_priority,
        )
        self._repo.add(chore)
        return chore

    def remove(self, chore_ids: list[str]) -> None:
        for chore_id in chore_ids:
            self._repo.delete(chore_id)
            # Clear any other chore that pointed at this one as a prereq
            for chore in self._repo.get_all():
                if chore.prereq_id == chore_id:
                    chore.prereq_id = None
                    self._repo.update(chore)

    def next_due_date(self, chore_id: str, current_date: date) -> date | None:
        chore = self._repo.get(chore_id)
        if chore is None:
            return None
        return chore.get_next_due_date(chore.due_date or current_date)

    def apply_edits(self, chore_id: str, changes: dict) -> None:
        chore = self._repo.get(chore_id)
        if chore is None:
            return
        for field_name, value in changes.items():
            old_value = getattr(chore, field_name)
            if field_name == "done_date":
                chore.set_done_date(value)
            else:
                chore.set_field(field_name, value)
            if self._change_log is not None:
                self._change_log.record_change(
                    chore_id, field_name, _serialize(old_value), _serialize(value)
                )
        self._repo.update(chore)

    # -- prerequisite management --------------------------------------

    def set_prereq(
        self, chore_id: str, prereq_id: str | None, window_days: int = 1
    ) -> None:
        """Set (or clear) the prerequisite for a chore.

        Raises ValueError if the new prereq would create a dependency cycle.
        """
        chore = self._repo.get(chore_id)
        if chore is None:
            return

        if prereq_id is not None:
            all_chores = self._repo.get_all()
            if prereq_id not in {c.id for c in all_chores}:
                raise ValueError(f"Prerequisite chore '{prereq_id}' not found.")
            if _detect_cycle(chore_id, prereq_id, all_chores):
                raise ValueError(
                    "Setting this prerequisite would create a dependency cycle."
                )

        old_prereq = chore.prereq_id
        chore.prereq_id = prereq_id
        chore.prereq_window_days = window_days
        self._repo.update(chore)

        if self._change_log is not None:
            self._change_log.record_change(
                chore_id, "prereq_id", _serialize(old_prereq), _serialize(prereq_id)
            )

    def get_prereq(self, chore_id: str) -> RecurringChore | None:
        """Return the prerequisite chore object, or None if unset/missing."""
        chore = self._repo.get(chore_id)
        if chore is None or not chore.prereq_id:
            return None
        return self._repo.get(chore.prereq_id)

    # -- change log ---------------------------------------------------

    def changes_for(self, chore_id: str) -> list[tuple[str, str, str]]:
        if self._change_log is None:
            return []
        raw = self._change_log.changes_for(chore_id)
        return [(_FIELD_LABELS.get(field, field), old, new) for field, old, new in raw]

    def discard_changes(self, chore_id: str) -> bool:
        if self._change_log is None:
            return False
        reverted = self._change_log.discard(chore_id)
        if reverted is None:
            return False
        chore = self._repo.get(chore_id)
        if chore is None:
            return False
        for field_name, raw_old_value in reverted.items():
            if field_name == "due_date":
                chore.set_due_date(date.fromisoformat(raw_old_value) if raw_old_value else None)
            else:
                chore.set_field(field_name, _deserialize_for_field(chore, field_name, raw_old_value))
        self._repo.update(chore)
        return True

    def _record_due_date_change(self, chore_id: str, old_due, new_due) -> None:
        if self._change_log is not None and old_due != new_due:
            self._change_log.record_change(chore_id, "due_date", _serialize(old_due), _serialize(new_due))

    # -- backup / restore -------------------------------------------------

    def export_json(self) -> bytes:
        payload = [c.to_dict() for c in self._repo.get_all()]
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def import_json(self, raw_bytes: bytes) -> list[RecurringChore]:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {exc}") from exc

        try:
            raw_data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"File is not valid JSON: {exc}") from exc

        if not isinstance(raw_data, list):
            raise ValueError("The file must contain a JSON array of chores.")
        if not raw_data:
            raise ValueError("The backup file is empty.")

        chores: list[RecurringChore] = []
        seen_ids: set[str] = set()
        for idx, item in enumerate(raw_data):
            label = f"Chore #{idx}"
            if not isinstance(item, dict):
                raise ValueError(f"{label}: expected a JSON object, got {type(item).__name__}.")
            if "id" not in item or not isinstance(item["id"], str):
                raise ValueError(f"{label}: missing or invalid 'id'.")
            if item["id"] in seen_ids:
                raise ValueError(f"{label}: duplicate id {item['id']}.")
            if "name" not in item or not str(item.get("name", "")).strip():
                raise ValueError(f"{label} (id={item['id']}): missing or empty 'name'.")
            try:
                chore = RecurringChore.from_dict(item)
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"{label} ('{item.get('name', '?')}'): {exc}") from exc
            seen_ids.add(chore.id)
            chores.append(chore)

        return chores

    def restore_from_backup(self, chores: list[RecurringChore]) -> None:
        self._repo.replace_all(chores)

    def snapshot_baseline(self) -> None:
        if self._change_log is not None:
            self._change_log.snapshot([c.id for c in self._repo.get_all()])


class OneTimeTaskService:
    """No frequency, no priority, no selector involvement."""

    def __init__(self, repository: Repository[OneTimeTask]) -> None:
        self._repo = repository

    def get_all(self) -> list[OneTimeTask]:
        return self._repo.get_all()

    def get_scheduled(self) -> list[OneTimeTask]:
        return [t for t in self._repo.get_all() if t.is_manually_rescheduled()]

    def schedule_for_today(self, task_id: str, current_date: date) -> None:
        task = self._repo.get(task_id)
        if task is None:
            return
        task.schedule_for(current_date)
        self._repo.update(task)

    def unschedule(self, task_id: str) -> None:
        task = self._repo.get(task_id)
        if task is None:
            return
        task.unschedule()
        self._repo.update(task)

    def toggle_complete(self, task_id: str, current_date: date) -> None:
        task = self._repo.get(task_id)
        if task is None:
            return
        if task.is_completed_on(current_date):
            task.uncomplete()
        else:
            task.complete(current_date)
        self._repo.update(task)

    def add(self, name: str, category: Category, duration: int) -> OneTimeTask:
        task = OneTimeTask(name=name, category=category, duration=duration)
        self._repo.add(task)
        return task

    def remove(self, task_ids: list[str]) -> None:
        for task_id in task_ids:
            self._repo.delete(task_id)

    def apply_edits(self, task_id: str, changes: dict) -> None:
        task = self._repo.get(task_id)
        if task is None:
            return
        for field_name, value in changes.items():
            task.set_field(field_name, value)
        self._repo.update(task)

    def export_json(self) -> bytes:
        payload = [t.to_dict() for t in self._repo.get_all()]
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
