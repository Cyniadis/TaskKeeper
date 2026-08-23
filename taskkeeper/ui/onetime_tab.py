"""The 'One-time' tab: manage tasks that don't recur.

Simpler than the Chores tab — no priority, no frequency, no
recurrence-eligibility. A OneTimeTask only ever reaches 'today' via the
explicit schedule button here (see domain/task.py's OneTimeTask).
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
    row = st.container(key=f"onetime_row_{task.id}")
    with row:
        cols = st.columns([0.08, 0.06, 0.5, 0.14, 0.22], gap="small", vertical_alignment="center")

        with cols[0]:
            st.checkbox(
                "done", value=task.is_completed_on(current_date), key=f"onetime_chk_{task.id}",
                label_visibility="collapsed",
                on_change=lambda tid=task.id: service.toggle_complete(tid, current_date),
            )
        with cols[1]:
            st.markdown(f"<span>{task.category.icon}</span>", unsafe_allow_html=True)
        with cols[2]:
            name_class = "chore-name-done" if task.is_completed() else ""
            tag = (
                "<span class='chore-tag chore-tag-rescheduled'>sur aujourd'hui</span>"
                if task.is_manually_rescheduled() else ""
            )
            st.markdown(f"<span class='{name_class}'>{task.name}</span>{tag}", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<span class='chore-duration'>{task.duration} min</span>", unsafe_allow_html=True)
        with cols[4]:
            if task.is_manually_rescheduled():
                st.button(
                    "✓ Sur aujourd'hui", key=f"onetime_unsched_{task.id}", width="stretch", type="tertiary",
                    on_click=lambda tid=task.id: service.unschedule(tid),
                )
            else:
                st.button(
                    "📅 Ajouter à aujourd'hui", key=f"onetime_sched_{task.id}", width="stretch",
                    on_click=lambda tid=task.id: service.schedule_for_today(tid, current_date),
                )


def _render_add_form(service: OneTimeTaskService) -> None:
    if not st.session_state.onetime_add_form_open:
        st.button("+ Ajouter une tâche", key="onetime_add_toggle", type="tertiary",
                   on_click=lambda: st.session_state.__setitem__("onetime_add_form_open", True))
        return

    with st.form("add_onetime_form", clear_on_submit=True, border=True):
        cols = st.columns([0.4, 0.25, 0.15, 0.2])
        name = cols[0].text_input("Nom", label_visibility="collapsed", placeholder="Nom de la tâche")
        category = cols[1].selectbox(
            "Catégorie", options=list(Category), format_func=lambda c: f"{c.icon} {c.label}",
            label_visibility="collapsed",
        )
        duration = cols[2].number_input("Durée", min_value=1, step=5, value=10, label_visibility="collapsed")
        submitted = cols[3].form_submit_button("Enregistrer", width="stretch")

        if submitted and name.strip():
            service.add(name.strip(), category, int(duration))
            st.session_state.onetime_add_form_open = False
            st.rerun()

    st.button("Annuler", key="onetime_add_cancel", type="tertiary",
              on_click=lambda: st.session_state.__setitem__("onetime_add_form_open", False))


def render(service: OneTimeTaskService, current_date: date) -> None:
    _init_state()
    inject_compact_css()

    st.markdown("### One-time tasks")
    st.caption("Tasks that don't recur — scheduled onto Today explicitly, never by the daily selector.")

    tasks = service.get_all()
    if not tasks:
        st.info("No one-time tasks yet — add one below.")
    else:
        with st.container(gap=None):
            for task in tasks:
                _render_row(task, current_date, service)

    st.divider()
    _render_add_form(service)
