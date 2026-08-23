"""Decides which recurring chores belong on today's plate.

Pure business logic: no Streamlit, no I/O. Ported from the original
tasktracker/selector.py, retyped against RecurringChore. OneTimeTask
never passes through here — it only joins "today" via explicit
scheduling (see services/chore_service.OneTimeTaskService).
"""
from __future__ import annotations

from datetime import date
from enum import Enum, auto

from .task import RecurringChore


class Eligibility(Enum):
    NOT_ELIGIBLE = auto()    # already done today, cancelled, or not due yet
    MAYBE_ELIGIBLE = auto()  # never scheduled/done before — usable as filler
    ELIGIBLE = auto()        # due today, overdue, or its recurrence window elapsed


def eligibility(chore: RecurringChore, current_date: date) -> Eligibility:
    if chore.is_cancelled():
        return Eligibility.NOT_ELIGIBLE
    if chore.done_date == current_date:
        return Eligibility.NOT_ELIGIBLE
    if chore.due_date == current_date:
        return Eligibility.ELIGIBLE
    if not chore.due_date or chore.due_date < current_date:
        if chore.done_date:
            days_since_done = (current_date - chore.done_date).days
            if days_since_done >= chore.frequency_obj.days:
                return Eligibility.NOT_ELIGIBLE
            return Eligibility.ELIGIBLE
        return Eligibility.MAYBE_ELIGIBLE
    return Eligibility.NOT_ELIGIBLE


def _select_by_priority(
    chores: list[RecurringChore],
    time_budget: int,
    *,
    priority_override_threshold: float = 8.0,
) -> list[RecurringChore]:
    """0/1 knapsack, favouring higher-priority chores.

    Chores whose priority is at or above `priority_override_threshold` are
    pulled out first and included unconditionally — they go on today's list
    regardless of whether their duration fits the remaining budget.  The
    knapsack then fills the leftover time with the rest.  This means a very
    urgent chore can push the day slightly over budget rather than being
    silently dropped because it didn't happen to fit in the remaining slot.
    """
    ordered = sorted(chores, key=lambda c: (-c.priority, c.due_date or date.max))

    # Split: must-do (priority override) vs normal candidates.
    must_do = [c for c in ordered if c.priority >= priority_override_threshold]
    candidates = [c for c in ordered if c.priority < priority_override_threshold]

    remaining = time_budget - sum(c.duration for c in must_do)

    if not candidates or remaining <= 0:
        return must_do

    # Standard knapsack over the lower-priority candidates.
    n = len(candidates)
    dp = [[0] * (remaining + 1) for _ in range(n + 1)]
    for i, chore in enumerate(candidates, start=1):
        duration = chore.duration
        for capacity in range(remaining + 1):
            if duration <= capacity:
                dp[i][capacity] = max(dp[i - 1][capacity], dp[i - 1][capacity - duration] + duration)
            else:
                dp[i][capacity] = dp[i - 1][capacity]

    knapsack_selected: list[RecurringChore] = []
    capacity = remaining
    for i in range(n, 0, -1):
        if dp[i][capacity] != dp[i - 1][capacity]:
            chore = candidates[i - 1]
            knapsack_selected.append(chore)
            capacity -= chore.duration

    return must_do + knapsack_selected


def compute_daily_chores(
    chores: list[RecurringChore],
    current_date: date,
    daily_time_limit: int,
    pre_selected: list[RecurringChore] | None = None,
) -> list[RecurringChore]:
    """Return the subset of `chores` scheduled for `current_date`."""
    pre_selected = pre_selected or []
    eligible = [c for c in chores if eligibility(c, current_date) is not Eligibility.NOT_ELIGIBLE]

    for c in eligible:
        from .task import TaskDueDateState
        c.state.due_date_state = TaskDueDateState.ELIGIBLE

    if pre_selected:
        remaining = daily_time_limit - sum(c.duration for c in pre_selected)
        if remaining <= 0:
            return pre_selected
        pre_ids = {c.id for c in pre_selected}
        candidates = [c for c in eligible if c.id not in pre_ids]
        if sum(c.duration for c in candidates) <= remaining:
            return pre_selected + candidates
        return pre_selected + _select_by_priority(candidates, remaining)

    if sum(c.duration for c in eligible) <= daily_time_limit:
        return eligible

    return _select_by_priority(eligible, daily_time_limit)