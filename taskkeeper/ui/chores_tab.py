"""The 'Chores' tab: today's compact chore list."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from ..domain.task import Category, RecurringChore
from ..services.chore_service import ChoreService
from .components import render_reschedule, render_task_row
from .format import format_date_fr

_SORT_FIELDS = {
    "Priorité": lambda c: c.priority,
    "Durée": lambda c: c.duration,
    "Nom": lambda c: c.name.lower(),
    "Catégorie": lambda c: c.category.label,
}


def _init_widget_state() -> None:
    st.session_state.setdefault("chores_daily_budget", 60)
    st.session_state.setdefault("chores_show_completed", True)
    st.session_state.setdefault("chores_show_rescheduled", True)
    st.session_state.setdefault("chores_show_details", False)
    st.session_state.setdefault("chores_sort_field", "Priorité")
    st.session_state.setdefault("chores_sort_desc", True)
    st.session_state.setdefault("chores_category_filter", "Tout")
    st.session_state.setdefault("chores_add_form_open", False)


def _render_header(service: ChoreService, current_date: date) -> None:
    st.markdown(f"### Chores · {format_date_fr(current_date)}")

    with st.container(horizontal=True, vertical_alignment="center", key="chores_header_controls", width="content"):
        st.markdown("**Daily budget (min)**")
        st.number_input(
            "Daily budget", min_value=5, max_value=720, step=15,
            key="chores_daily_budget", width=90, label_visibility="collapsed",
        )
        st.button(
            "🔄 Regenerate",
            on_click=lambda: service.regenerate_today(current_date, st.session_state.chores_daily_budget),
            key="chores_regenerate_button"
        )
        st.checkbox("Show completed", key="chores_show_completed")
        st.checkbox("Show rescheduled", key="chores_show_rescheduled")


def _render_progress(chores: list[RecurringChore], daily_budget: int) -> None:
    active_minutes = sum(c.duration for c in chores if not c.is_completed())
    with st.container(horizontal=True, width="content"):
        st.caption(f"**{active_minutes} / {daily_budget} min** — {len(chores)} tasks")
        st.progress(min(1.0, active_minutes / daily_budget) if daily_budget else 0.0, width=500)


def _render_category_filter(chores: list[RecurringChore]) -> list[Category] | None:
    used_categories = sorted({c.category for c in chores}, key=lambda cat: cat.label)
    with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center", width="content"):
        st.markdown("**Filter**")
        choices = st.multiselect(
            "Catégorie", options=used_categories, key="chores_category_filter",
            width="stretch", label_visibility="collapsed",
            format_func=lambda cat: f"{cat.icon} {cat.label}",
        )
        return choices
    return None


def _render_toolbar() -> None:
    with st.container(horizontal=True, gap="xxsmall", vertical_alignment="center", width="content"):
        st.markdown("**Sort by**")
        st.selectbox(
            "Sort by", options=list(_SORT_FIELDS.keys()), key="chores_sort_field",
            width=140, label_visibility="collapsed",
        )
        label = "▼ Descending" if st.session_state.chores_sort_desc else "▲ Ascending"
        st.button(
            label, key="chores_sort_dir", type="tertiary",
            on_click=lambda: st.session_state.__setitem__(
                "chores_sort_desc", not st.session_state.chores_sort_desc
            ),
        )

    with st.container(horizontal=True, gap="xsmall", vertical_alignment="center", width="content"):
        st.markdown("**Details**")
        st.toggle("Details", key="chores_show_details", label_visibility="collapsed")


def render(service: ChoreService, current_date: date) -> None:
    _init_widget_state()

    with st.container(width="content", horizontal_alignment="distribute"):
        _render_header(service, current_date)

        all_today = service.get_today(current_date)

        # Build an index of ALL chores (not just today's) so the prereq
        # badge in render_task_row can resolve any prerequisite id.
        all_chores = service.get_all()
        chore_index = {c.id: c for c in all_chores}

        if not st.session_state.chores_show_completed:
            all_today = [c for c in all_today if not c.is_completed()]
        if not st.session_state.chores_show_rescheduled:
            all_today = [
                c for c in all_today
                if not (c.is_manually_rescheduled() and c.due_date != current_date)
            ]

        _render_progress(all_today, st.session_state.chores_daily_budget)

        with st.container(horizontal=True, vertical_alignment="center", key="chores_sort_toolbar"):
            _render_toolbar()
            category_filter = _render_category_filter(all_today)
            if category_filter is not None and len(category_filter) > 0:
                all_today = [c for c in all_today if c.category in category_filter]

        key_fn = _SORT_FIELDS[st.session_state.chores_sort_field]
        all_today = sorted(all_today, key=key_fn, reverse=st.session_state.chores_sort_desc)

        show_details = st.session_state.chores_show_details

        if not all_today:
            st.info("Aucune tâche à afficher pour ce filtre.")
        else:
            with st.container(gap=None, width="stretch"):
                for chore in all_today:
                    with st.container(
                        key=f"chore_row_{chore.id}",
                        horizontal=True,
                        vertical_alignment="center",
                        horizontal_alignment="left",
                        gap="small",
                        width=700,
                    ):
                        render_task_row(
                            chore, current_date,
                            show_details=show_details,
                            on_toggle=lambda cid: service.toggle_complete(cid, current_date),
                            chore_index=chore_index,
                        )

                        with st.popover(":material/edit_calendar:", width="content"):
                            render_reschedule(
                                chore, current_date,
                                next_due_date=service.next_due_date(chore.id, chore.due_date or current_date),
                                on_reschedule_today=lambda cid: service.reschedule(cid, current_date),
                                on_reschedule_weekend=lambda cid: service.reschedule(
                                    cid, current_date + timedelta(days=(5 - current_date.weekday()) % 7)
                                ),
                                on_reschedule_next_due=lambda cid: service.reschedule(
                                    cid, service.next_due_date(cid, chore.due_date or current_date)
                                ),
                                on_reschedule_date=lambda cid, d: service.reschedule(cid, d),
                                on_cancel=lambda cid: service.cancel(cid),
                                key_prefix="popover",
                            )
