"""Per-field change tracking, backing the Library tab's 'Changes' dialog.

Replaces task_baseline.json's approach (snapshot the whole list, diff a
live object against it). Instead, every edit is recorded as it happens:
- The first edit to a field since the last snapshot records the true
  baseline value as `old_value`.
- Every subsequent edit to that same field just updates `new_value` —
  the baseline is never overwritten, so 'Changes' always compares
  against "since the last full reload", matching the original
  semantics.
- If a field is edited back to its baseline value, the row is deleted —
  it's no longer a change, so it shouldn't show up as one.

Deliberately domain-agnostic (works on any entity_id/field_name pair,
not just chores) so it doesn't need to know about Category/Frequency/etc.
— the caller (ChoreService) supplies already-serialized string values
and maps field names to human labels.
"""
from __future__ import annotations

import sqlite3


class ChangeLog:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS changes (
                entity_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                PRIMARY KEY (entity_id, field_name)
            )
            """
        )
        self._conn.commit()

    def record_change(self, entity_id: str, field_name: str, old_value: str, new_value: str) -> None:
        existing = self._conn.execute(
            "SELECT old_value FROM changes WHERE entity_id = ? AND field_name = ?",
            (entity_id, field_name),
        ).fetchone()

        if existing is None:
            if old_value == new_value:
                return  # not actually a change
            self._conn.execute(
                "INSERT INTO changes (entity_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
                (entity_id, field_name, old_value, new_value),
            )
        else:
            baseline_old = existing[0]
            if baseline_old == new_value:
                self._conn.execute(
                    "DELETE FROM changes WHERE entity_id = ? AND field_name = ?",
                    (entity_id, field_name),
                )
            else:
                self._conn.execute(
                    "UPDATE changes SET new_value = ? WHERE entity_id = ? AND field_name = ?",
                    (new_value, entity_id, field_name),
                )
        self._conn.commit()

    def changes_for(self, entity_id: str) -> list[tuple[str, str, str]]:
        """(field_name, old_value, new_value) tuples — caller maps
        field_name to a human label."""
        rows = self._conn.execute(
            "SELECT field_name, old_value, new_value FROM changes WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
        return [tuple(row) for row in rows]

    def discard(self, entity_id: str) -> dict[str, str] | None:
        """Returns {field_name: baseline_value} to revert to, and clears
        the log for this entity (once reverted, it's no longer 'changed').
        Returns None if there's nothing logged for this entity."""
        rows = self._conn.execute(
            "SELECT field_name, old_value FROM changes WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
        if not rows:
            return None
        self._conn.execute("DELETE FROM changes WHERE entity_id = ?", (entity_id,))
        self._conn.commit()
        return {field_name: old_value for field_name, old_value in rows}

    def snapshot(self, entity_ids: list[str]) -> None:
        """Clears the log for these ids — the 'since the last full
        reload' reference point, called once at process start."""
        if not entity_ids:
            return
        placeholders = ",".join("?" for _ in entity_ids)
        self._conn.execute(f"DELETE FROM changes WHERE entity_id IN ({placeholders})", entity_ids)
        self._conn.commit()
