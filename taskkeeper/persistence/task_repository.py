"""Repository builders for RecurringChore/OneTimeTask, and demo seed data."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ..domain.task import Category, OneTimeTask, RecurringChore
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


def seed_sample_onetime(repository: SQLiteRepository[OneTimeTask]) -> None:
    """Sample one-time tasks, matching the flavour of the original
    onetime_tasks.json (decluttering/errand-type items)."""
    if repository.get_all():
        return
    samples = [
        ("Trier les vêtements de l'armoire", Category.BEDROOM, 30),
        ("Racheter un cache sommier", Category.BEDROOM, 15),
        ("Appeler l'auto-école", Category.CAR, 15),
        ("Dégager le vélo elliptique", Category.OTHER, 10),
        ("Acheter un support TV", Category.LIVING_ROOM, 15),
    ]
    for name, category, duration in samples:
        repository.add(OneTimeTask(name=name, category=category, duration=duration))


def seed_sample_chores(repository: SQLiteRepository[RecurringChore], today: date) -> None:
    """Populate the repository with sample data if it's empty — same
    chores used in the earlier standalone HTML mockup, for continuity."""
    if repository.get_all():
        return

    samples = [
        ("Nettoyer le plan de travail", Category.KITCHEN, 5, 16.0, 0),
        ("Ranger la vaisselle propre", Category.KITCHEN, 5, 13.5, 0),
        ("Sortir les poubelles", Category.KITCHEN, 5, 5.0, -1),   # done yesterday-ish -> today for demo
        ("Changer l'eau et la pâtée", Category.PET, 5, 18.0, 0),
        ("Enlever crottes litière", Category.PET, 5, 16.0, 0),
        ("Ranger les vêtements qui trainent", Category.LAUNDRY, 15, 16.0, 0),
        ("Faire la lessive vêtements", Category.LAUNDRY, 5, 10.5, 3),   # rescheduled a few days out
        ("Entrainement épée longue", Category.HOBBY, 15, 8.5, 0),
        ("Réviser code de la route", Category.CAR, 30, 14.5, 0),
        ("Nettoyer plaque cuisson", Category.KITCHEN, 10, 14.0, -4),   # overdue / late
        ("Passer l'aspirateur", Category.LIVING_ROOM, 25, 7.0, 0),
        ("Passer la tondeuse", Category.GARDEN, 30, 4.5, 0),
    ]

    for name, category, duration, priority, offset in samples:
        chore = RecurringChore(
            name=name, category=category, duration=duration,
            frequency="1xsemaine", priority=priority, initial_priority=priority,
        )
        if name == "Sortir les poubelles":
            chore.complete(today)
        elif offset < 0:
            chore.set_due_date(today + timedelta(days=offset))
        elif offset > 0:
            chore.manually_reschedule(today + timedelta(days=offset))
        else:
            chore.set_due_date(today)
        repository.add(chore)
