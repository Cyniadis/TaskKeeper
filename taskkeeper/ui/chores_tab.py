"""The 'Chores' tab: today's compact chore list.

Render functions only — all state mutation goes through `service`
(ChoreService), never touches session_state for domain data. session_state
here is purely widget-local (sort field, filter selection, form open/closed).
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from ..domain.task import Category, RecurringChore
from ..services.chore_service import ChoreService
from .components import render_reschedule, render_sort_filter_toolbar, render_task_row
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
    st.session_state.setdefault("chores_category_filter", [])


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
        )
        st.checkbox("Show completed", key="chores_show_completed")
        st.checkbox("Show rescheduled", key="chores_show_rescheduled")


def _render_progress(chores: list[RecurringChore], daily_budget: int) -> None:
    active_minutes = sum(c.duration for c in chores if not c.is_completed())
    with st.container(horizontal=True, width="content"):
        st.caption(f"**{active_minutes} / {daily_budget} min** — {len(chores)} tasks")
        st.progress(min(1.0, active_minutes / daily_budget) if daily_budget else 0.0, width=500)


def render(service: ChoreService, current_date: date) -> None:
    _init_widget_state()

    with st.container(width="content", horizontal_alignment="distribute"):
        _render_header(service, current_date)

        all_today = service.get_today(current_date)
        if not st.session_state.chores_show_completed:
            all_today = [c for c in all_today if not c.is_completed()]
        if not st.session_state.chores_show_rescheduled:
            all_today = [
                c for c in all_today
                if not (c.is_manually_rescheduled() and c.due_date != current_date)
            ]

        _render_progress(all_today, st.session_state.chores_daily_budget)

        key_fn, descending, category_filter = render_sort_filter_toolbar(
            items=all_today,
            sort_fields=_SORT_FIELDS,
            get_category=lambda c: c.category,
            sort_field_key="chores_sort_field",
            sort_desc_key="chores_sort_desc",
            show_details_key="chores_show_details",
            category_filter_key="chores_category_filter",
        )

        if category_filter:
            all_today = [c for c in all_today if c.category in category_filter]

        all_today = sorted(all_today, key=key_fn, reverse=descending)
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
                        )

                        with st.popover(":material/edit_calendar:", width="content"):
                            render_reschedule(
                                chore, current_date,
                                next_due_date=service.next_due_date(chore.id, current_date),
                                on_reschedule_today=lambda cid: service.reschedule(cid, current_date),
                                on_reschedule_weekend=lambda cid: service.reschedule(
                                    cid, current_date + timedelta(days=(5 - current_date.weekday()) % 7)
                                ),
                                on_reschedule_next_due=lambda cid: service.reschedule(
                                    cid, service.next_due_date(cid, current_date)
                                ),
                                on_reschedule_date=lambda cid, d: service.reschedule(cid, d),
                                on_cancel=lambda cid: service.cancel(cid),
                                key_prefix="popover",
                            )