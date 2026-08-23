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
from typing import Callable, TypeVar

import streamlit as st

from ..domain.task import Category, RecurringChore
from .format import format_date_short_fr


def inject_compact_css() -> None:
    """No-op — retained so callers (chores_tab, onetime_tab) need no changes."""
    pass


# ---------------------------------------------------------------------------
# Shared sort + category filter toolbar
# ---------------------------------------------------------------------------

T = TypeVar("T")


def render_sort_filter_toolbar(
    *,
    items: list[T],
    sort_fields: dict[str, Callable[[T], object]],
    get_category: Callable[[T], Category],
    sort_field_key: str,
    sort_desc_key: str,
    show_details_key: str,
    category_filter_key: str,
    extra_toggles: list[tuple[str, str]] | None = None,
) -> tuple[Callable[[T], object], bool, list[Category] | None]:
    """Render the combined sort + category filter toolbar used by both
    the Chores and One-time tabs.

    Parameters
    ----------
    items:
        The full (pre-filter) list being displayed — used to derive
        which categories are actually present.
    sort_fields:
        Ordered mapping of display label → key function, e.g.
        ``{"Priorité": lambda c: c.priority, ...}``.
    get_category:
        Callable that extracts the ``Category`` from one item.
    sort_field_key / sort_desc_key / show_details_key / category_filter_key:
        Session-state keys for the four controls — each tab passes its
        own prefixed keys so they don't collide.
    extra_toggles:
        Optional list of ``(label, session_state_key)`` pairs for
        additional ``st.toggle`` widgets appended after "Details".

    Returns
    -------
    (key_fn, descending, selected_categories)
        ``key_fn``             — the currently chosen sort function
        ``descending``         — True when sort direction is descending
        ``selected_categories``— non-empty list of Category filters, or
                                 None when no filter is active (show all)
    """
    with st.container(
        horizontal=True,
        gap="medium",
        vertical_alignment="center",
        width="content",
        key=f"{sort_field_key}_toolbar_row",
    ):
        # -- Sort field --------------------------------------------------
        with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center", width="content"):
            st.markdown("Sort by")
            st.selectbox(
                "Sort by",
                options=list(sort_fields.keys()),
                key=sort_field_key,
                width=140,
                label_visibility="collapsed",
            )
            # -- Sort direction toggle ---------------------------------------
            dir_label = "▼ Descending" if st.session_state[sort_desc_key] else "▲ Ascending"
            st.button(
                dir_label,
                key=f"{sort_desc_key}_btn",
                type="tertiary",
                on_click=lambda: st.session_state.__setitem__(
                    sort_desc_key, not st.session_state[sort_desc_key]
                ),
            )

        with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center", width="content"):
            # -- Details toggle ---------------------------------------------
            st.markdown("Details")
            st.toggle("Details", key=show_details_key, label_visibility="collapsed")

            # -- Extra toggles (e.g. "Show completed") ----------------------
        for label, key in (extra_toggles or []):
            with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center"):
                st.markdown(f"{label}")
                st.toggle(label, key=key, label_visibility="collapsed")

        # -- Category multiselect ---------------------------------------
        with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center", width="content"):
            used_categories = sorted(
                {get_category(item) for item in items},
                key=lambda cat: cat.label,
            )
            st.markdown("Filter")
            selected: list[Category] = st.multiselect(
                "Catégorie",
                options=used_categories,
                key=category_filter_key,
                width="stretch",
                label_visibility="collapsed",
                format_func=lambda cat: f"{cat.icon} {cat.label}",
            )

    key_fn = sort_fields[st.session_state[sort_field_key]]
    descending = st.session_state[sort_desc_key]
    return key_fn, descending, selected if selected else None


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
    if status == "done":
        return f"~~{chore.name}~~"
    return chore.name


# ---------------------------------------------------------------------------
# Public row renderers
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
    key_prefix: str,
) -> None:
    button_clicked = False
    with st.container():
        st.markdown(f"**{chore.category.icon} {chore.name}**")
        with st.container(horizontal=True, gap="small", width="stretch"):
            button_clicked = st.button(
                "📅 Aujourd'hui",
                key=f"{key_prefix}_resched_today_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_reschedule_today(cid),
            )
            button_clicked = button_clicked or st.button(
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
            button_clicked = button_clicked or st.button(
                next_label,
                key=f"{key_prefix}_resched_next_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_reschedule_next_due(cid),
            )
            button_clicked = button_clicked or st.button(
                "✕ Annuler",
                key=f"{key_prefix}_cancel_{chore.id}",
                width="stretch",
                on_click=lambda cid=chore.id: on_cancel(cid),
            )

        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            picked = st.date_input(
                "date",
                value=current_date,
                key=f"{key_prefix}_resched_pick_{chore.id}",
                label_visibility="collapsed",
                width="stretch",
            )
            button_clicked = button_clicked or st.button(
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
    """
    status = _row_status(chore, current_date)

    st.checkbox(
        "done",
        value=(status == "done"),
        key=f"chk_{chore.id}",
        label_visibility="collapsed",
        on_change=lambda cid=chore.id: on_toggle(cid),
        disabled=(status == "rescheduled"),
    )

    st.markdown(_priority_dot(chore.priority), width="content")
    st.markdown(chore.category.icon, width=10)

    with st.container(
        horizontal=True,
        vertical_alignment="center",
        gap="small",
        width="stretch",
        horizontal_alignment="left",
    ):
        st.markdown(_name_markup(chore, status), width="content")
        if status == "late":
            st.badge("en retard", color="red")
        elif status == "rescheduled":
            st.badge("reporté", color="orange")

    if show_details:
        with st.container(horizontal=True, width="content"):
            st.caption(f"{chore.priority:.1f}")
            shown_date = chore.done_date if status == "done" else chore.due_date
            st.caption(
                format_date_short_fr(shown_date) if shown_date else "—", width=80
            )

    st.caption(f"{chore.duration} min", width=50)