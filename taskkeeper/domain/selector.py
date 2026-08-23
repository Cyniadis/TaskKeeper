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


def _select_by_priority(chores: list[RecurringChore], time_budget: int) -> list[RecurringChore]:
    """0/1 knapsack, favouring higher-priority chores."""
    ordered = sorted(chores, key=lambda c: (-c.priority, c.due_date or date.max))
    n = len(ordered)
    dp = [[0] * (time_budget + 1) for _ in range(n + 1)]
    for i, chore in enumerate(ordered, start=1):
        duration = chore.duration
        for capacity in range(time_budget + 1):
            if duration <= capacity:
                dp[i][capacity] = max(dp[i - 1][capacity], dp[i - 1][capacity - duration] + duration)
            else:
                dp[i][capacity] = dp[i - 1][capacity]

    selected: list[RecurringChore] = []
    capacity = time_budget
    for i in range(n, 0, -1):
        if dp[i][capacity] != dp[i - 1][capacity]:
            chore = ordered[i - 1]
            selected.append(chore)
            capacity -= chore.duration
    return selected


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
