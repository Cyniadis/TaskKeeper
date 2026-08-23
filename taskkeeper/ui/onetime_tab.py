"""The 'One-time' tab: manage tasks that don't recur.

Simpler than the Chores tab — no priority, no frequency, no
recurrence-eligibility. A OneTimeTask only ever reaches 'today' via the
explicit schedule button here (see domain/task.py's OneTimeTask).

Layout uses st.container(horizontal=True) throughout — no st.columns,
no custom CSS.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from ..domain.task import Category, OneTimeTask
from ..services.chore_service import OneTimeTaskService
from .components import inject_compact_css


def _init_state() -> None:
    st.session_state.setdefault("onetime_add_form_open", False)


def _render_row(task: OneTimeTask, current_date: date, service: OneTimeTaskService) -> None:
    with st.container(
        key=f"onetime_row_{task.id}",
        horizontal=True,
        vertical_alignment="center",
        gap="small",
    ):
        # -- checkbox -------------------------------------------------------
        st.checkbox(
            "done",
            value=task.is_completed_on(current_date),
            key=f"onetime_chk_{task.id}",
            label_visibility="collapsed",
            on_change=lambda tid=task.id: service.toggle_complete(tid, current_date),
        )

        # -- category icon --------------------------------------------------
        st.markdown(task.category.icon, width="content")

        # -- name + optional "sur aujourd'hui" badge (stretches) ------------
        with st.container(horizontal=True, vertical_alignment="center",
                          gap="small", width="stretch"):
            name_text = f"~~{task.name}~~" if task.is_completed() else task.name
            st.markdown(name_text, width="stretch")
            if task.is_manually_rescheduled():
                st.badge("sur aujourd'hui", color="green")

        # -- duration -------------------------------------------------------
        st.caption(f"{task.duration} min", width="content")

        # -- schedule / unschedule button -----------------------------------
        if task.is_manually_rescheduled():
            st.button(
                "✓ Sur aujourd'hui",
                key=f"onetime_unsched_{task.id}",
                type="tertiary",
                on_click=lambda tid=task.id: service.unschedule(tid),
            )
        else:
            st.button(
                "📅 Ajouter à aujourd'hui",
                key=f"onetime_sched_{task.id}",
                on_click=lambda tid=task.id: service.schedule_for_today(tid, current_date),
            )

    st.divider()


def _render_add_form(service: OneTimeTaskService) -> None:
    if not st.session_state.onetime_add_form_open:
        st.button(
            "+ Ajouter une tâche",
            key="onetime_add_toggle",
            type="tertiary",
            on_click=lambda: st.session_state.__setitem__("onetime_add_form_open", True),
        )
        return

    with st.form("add_onetime_form", clear_on_submit=True, border=True):
        cols = st.columns([0.4, 0.25, 0.15, 0.2])
        name = cols[0].text_input(
            "Nom", label_visibility="collapsed", placeholder="Nom de la tâche"
        )
        category = cols[1].selectbox(
            "Catégorie",
            options=list(Category),
            format_func=lambda c: f"{c.icon} {c.label}",
            label_visibility="collapsed",
        )
        duration = cols[2].number_input(
            "Durée", min_value=1, step=5, value=10, label_visibility="collapsed"
        )
        submitted = cols[3].form_submit_button("Enregistrer", width="stretch")

        if submitted and name.strip():
            service.add(name.strip(), category, int(duration))
            st.session_state.onetime_add_form_open = False
            st.rerun()

    st.button(
        "Annuler",
        key="onetime_add_cancel",
        type="tertiary",
        on_click=lambda: st.session_state.__setitem__("onetime_add_form_open", False),
    )


def render(service: OneTimeTaskService, current_date: date) -> None:
    _init_state()
    inject_compact_css()

    st.markdown("### One-time tasks")
    st.caption(
        "Tasks that don't recur — scheduled onto Today explicitly, never by the daily selector."
    )

    tasks = service.get_all()
    if not tasks:
        st.info("No one-time tasks yet — add one below.")
    else:
        for task in tasks:
            _render_row(task, current_date, service)

    st.divider()
    _render_add_form(service)