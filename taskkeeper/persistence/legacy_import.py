"""Migrates data from the original tasktracker JSON files into TaskKeeper's
domain model + SQLite repositories.

The legacy schema (tasklist.json / onetime_tasks.json / groceries.json) has
no `category` field — the original app used an emoji prefix in the task
name as an informal category marker (see tasktracker/general_tab.py's
_colorize_rows and the household docs this data came from). This module
makes that convention explicit by mapping each known emoji to a real
Category, so the migrated data gets real filtering/grouping in the new UI
instead of just carrying the emoji as a decorative prefix forever.

Unrecognized emoji fall back to Category.OTHER — see MigrationReport for
which chores/tasks landed there, so you can manually recategorize a
handful of edge cases in the Library tab after import rather than the
script silently guessing wrong.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..domain.grocery import GroceryItem
from ..domain.task import Category, OneTimeTask, RecurringChore
from .grocery_repository import build_grocery_repository
from .repository import SQLiteRepository
from .task_repository import build_chore_repository, build_onetime_repository

# Primary mapping: each Category's own icon (defined in domain/task.py).
_PRIMARY_EMOJI_TO_CATEGORY = {cat.icon: cat for cat in Category}

# The legacy data uses a couple of emoji that don't match any Category's
# canonical icon one-for-one (e.g. bedroom decluttering tasks used 🛌,
# not 🛏) — these extend the lookup without changing what Category.icon
# reports elsewhere in the UI.
_EXTRA_EMOJI_TO_CATEGORY = {
    "🛌": Category.BEDROOM,
    "🪟": Category.LIVING_ROOM,
}

_EMOJI_TO_CATEGORY = {**_PRIMARY_EMOJI_TO_CATEGORY, **_EXTRA_EMOJI_TO_CATEGORY}


def infer_category(name: str) -> Category:
    """Scans `name` for the earliest-occurring recognized category
    emoji. Falls back to Category.OTHER if none match — see module
    docstring. Uses substring search, not per-character iteration:
    several emoji (e.g. the couch icon, 🛋️) are two Unicode code points
    (base glyph + variation selector), so checking one code point at a
    time would never match a multi-code-point icon."""
    best_index: int | None = None
    best_category = Category.OTHER
    for icon, category in _EMOJI_TO_CATEGORY.items():
        idx = name.find(icon)
        if idx != -1 and (best_index is None or idx < best_index):
            best_index = idx
            best_category = category
    return best_category


@dataclass
class MigrationReport:
    chores_migrated: int = 0
    onetime_migrated: int = 0
    groceries_migrated: int = 0
    uncategorized: list[str] = field(default_factory=list)  # names that fell back to OTHER

    def __str__(self) -> str:
        lines = [
            f"Chores migrated:     {self.chores_migrated}",
            f"One-time migrated:   {self.onetime_migrated}",
            f"Groceries migrated:  {self.groceries_migrated}",
        ]
        if self.uncategorized:
            lines.append(f"Fell back to 'Other' category ({len(self.uncategorized)}):")
            lines.extend(f"  - {name}" for name in self.uncategorized)
        return "\n".join(lines)


def _load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array, got {type(data).__name__}.")
    return data


def migrate_chores(raw_tasks: list[dict], report: MigrationReport) -> list[RecurringChore]:
    """Legacy tasklist.json entries -> RecurringChore. Reuses
    RecurringChore.from_dict for all the date/state parsing it already
    does correctly — this just injects the inferred `category` first."""
    chores = []
    for item in raw_tasks:
        category = infer_category(item["name"])
        if category is Category.OTHER:
            report.uncategorized.append(item["name"])
        enriched = {**item, "category": category.value}
        chores.append(RecurringChore.from_dict(enriched))
    return chores


def migrate_onetime(raw_tasks: list[dict], report: MigrationReport) -> list[OneTimeTask]:
    """Legacy onetime_tasks.json entries -> OneTimeTask. The legacy
    entries carry frequency/priority/initial_priority fields (inert
    sentinels the original app never read for these) — OneTimeTask.from_dict
    already ignores unknown keys, so no stripping needed here."""
    tasks = []
    for item in raw_tasks:
        category = infer_category(item["name"])
        if category is Category.OTHER:
            report.uncategorized.append(item["name"])
        enriched = {**item, "category": category.value}
        tasks.append(OneTimeTask.from_dict(enriched))
    return tasks


def migrate_groceries(raw_items: list[dict]) -> list[GroceryItem]:
    """Legacy groceries.json entries -> GroceryItem. Legacy ids are
    integers; GroceryItem.id is a string, so they're coerced here."""
    items = []
    for item in raw_items:
        enriched = {**item, "id": str(item["id"])}
        items.append(GroceryItem.from_dict(enriched))
    return items


def run_migration(
    data_dir: Path,
    chore_repo: SQLiteRepository[RecurringChore],
    onetime_repo: SQLiteRepository[OneTimeTask],
    grocery_repo: SQLiteRepository[GroceryItem],
    *,
    force: bool = False,
) -> MigrationReport:
    """Reads tasklist.json / onetime_tasks.json / groceries.json from
    `data_dir` (any of the three may be absent — that file is just
    skipped) and replaces the given repositories' contents.

    Refuses to overwrite non-empty repositories unless `force=True`, so
    running this twice by accident doesn't silently duplicate everything.
    """
    if not force:
        for repo, label in (
            (chore_repo, "chores"), (onetime_repo, "one-time tasks"), (grocery_repo, "groceries"),
        ):
            if repo.get_all():
                raise RuntimeError(
                    f"The {label} repository already has data — pass force=True to overwrite it."
                )

    report = MigrationReport()

    raw_chores = _load_json_array(data_dir / "tasklist.json")
    chores = migrate_chores(raw_chores, report)
    chore_repo.replace_all(chores)
    report.chores_migrated = len(chores)

    raw_onetime = _load_json_array(data_dir / "onetime_tasks.json")
    onetime = migrate_onetime(raw_onetime, report)
    onetime_repo.replace_all(onetime)
    report.onetime_migrated = len(onetime)

    raw_groceries = _load_json_array(data_dir / "groceries.json")
    groceries = migrate_groceries(raw_groceries)
    grocery_repo.replace_all(groceries)
    report.groceries_migrated = len(groceries)

    return report
