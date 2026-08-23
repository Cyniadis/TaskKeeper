"""Shared row/status widgets for the Chores and One-time tabs.

Zero custom CSS. All visual differentiation comes from:
  - st.badge()                    → status tags (en retard / reporté)
  - Markdown syntax               → ~~strikethrough~~ for done names
  - Priority emoji                → 🔴 / 🟡 / ⚪ tier dot
  - st.divider()                  → row separation
  - st.container(horizontal=True) → layout structure (no st.columns)

inject_compact_css() is kept as a no-op so callers don't need updating.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import streamlit as st

from ..domain.task import RecurringChore
from .format import format_date_short_fr


def inject_compact_css() -> None:
    """No-op — retained so callers (chores_tab, onetime_tab) need no changes."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_status(chore: RecurringChore, current_date: date) -> str:
    if chore.is_completed_on(current_date):
        return "done"
    if chore.is_manually_rescheduled() and chore.due_date != current_date:
        return "rescheduled"
    if chore.due_date and chore.due_date < current_date and not chore.is_completed():
        return "late"
    return "todo"


def _priority_dot(priority: float) -> str:
    """Urgency tier as a single emoji — no CSS needed."""
    if priority >= 14:
        return "🔴"
    if priority >= 8:
        return "🟡"
    return "⚪"


def _name_markup(chore: RecurringChore, status: str) -> str:
    """Chore name with Markdown strikethrough when done.

    Late / rescheduled status is carried by the badge next to the name,
    not by colour on the name itself — better for accessibility.
    """
    if status == "done":
        return f"~~{chore.name}~~"
    return chore.name


# ---------------------------------------------------------------------------
# Public row renderer
# ---------------------------------------------------------------------------

def render_reschedule(
    chore: RecurringChore,
    current_date: date,
    next_due_date: date | None,
    on_reschedule_today: Callable[[str], None],
    on_reschedule_weekend: Callable[[str], None],
    on_reschedule_next_due: Callable[[str], None],
    on_reschedule_date: Callable[[str, date], None],
    on_cancel: Callable[[str], None],
    key_prefix: str
) -> None:
    button_clicked = False
    with st.container():
        # Two quick-reschedule buttons side by side
        st.markdown(f"**{chore.category.icon} {chore.name}**")
        with st.container(horizontal=True, gap="small", width="stretch"):
            button_clicked = st.button(
                "📅 Aujourd'hui",
                key=f"{key_prefix}_resched_today_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_reschedule_today(cid),
            )
            button_clicked = button_clicked or \
            st.button(
                "🛌 Week-end",
                key=f"{key_prefix}_resched_weekend_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_reschedule_weekend(cid),
            )

            next_label = (
                f"⏭ {format_date_short_fr(next_due_date)}"
                if next_due_date
                else "⏭ Prochaine échéance"
            )
            button_clicked = button_clicked or \
            st.button(
                next_label,
                key=f"{key_prefix}_resched_next_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_reschedule_next_due(cid),
            )
            button_clicked = button_clicked or \
            st.button(
                "✕ Annuler",
                key=f"{key_prefix}_cancel_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_cancel(cid),
            )
            
        # Date picker + OK button side by side
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            picked = st.date_input(
                "date",
                value=current_date,
                key=f"{key_prefix}_resched_pick_{chore.id}",
                label_visibility="collapsed",
                width="stretch",
            )
            button_clicked = button_clicked or \
            st.button(
                "OK",
                key=f"{key_prefix}_resched_pick_btn_{chore.id}",
                on_click=lambda cid=chore.id, d=picked: on_reschedule_date(cid, d),
            )
        return button_clicked


def render_task_row(
    chore: RecurringChore,
    current_date: date,
    *,
    show_details: bool,
    on_toggle: Callable[[str], None],
) -> None:
    """One chore row using st.container(horizontal=True) throughout.

    Layout in both modes:
      [✓] [dot] [icon] [name ~~~ :badge:]──stretch──  [detail?] [dur]  [⋯]

    The name container uses width="stretch" to fill available space;
    every other child uses width="content" (the default) so it stays
    as tight as its content. No st.columns, no CSS ratios.
    """
    status = _row_status(chore, current_date)

    # -- checkbox -------------------------------------------------------
    st.checkbox(
        "done",
        value=(status == "done"),
        key=f"chk_{chore.id}",
        label_visibility="collapsed",
        on_change=lambda cid=chore.id: on_toggle(cid),
        disabled=(status == "rescheduled"),
    )

    # -- priority dot + category icon -----------------------------------
    st.markdown(_priority_dot(chore.priority), width="content")
    st.markdown(chore.category.icon, width=10)

    # -- name (stretches to fill remaining space) + status badge -------
    with st.container(horizontal=True, vertical_alignment="center",
                        gap="small", width="stretch", horizontal_alignment="left"):
        st.markdown(_name_markup(chore, status), width="content")
        if status == "late":
            st.badge("en retard", color="red")
        elif status == "rescheduled":
            st.badge("reporté", color="orange")

    # -- detail extras (priority value + date) --------------------------
    if show_details:
        with st.container(horizontal=True, width="content"):
            st.caption(f"{chore.priority:.1f}")
            shown_date = chore.done_date if status == "done" else chore.due_date
            st.caption(
                format_date_short_fr(shown_date) if shown_date else "—", width=80
            )

    # -- duration -------------------------------------------------------
    st.caption(f"{chore.duration} min", width=50)

