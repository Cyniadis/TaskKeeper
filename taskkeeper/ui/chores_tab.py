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
from .components import inject_compact_css, render_task_row
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
        )
        st.checkbox("Show completed", key="chores_show_completed")
        st.checkbox("Show rescheduled", key="chores_show_rescheduled")


def _render_progress(chores: list[RecurringChore], daily_budget: int) -> None:
    active_minutes = sum(c.duration for c in chores if not c.is_completed())
    with st.container(horizontal=True):
        st.caption(f"**{active_minutes} / {daily_budget} min** — {len(chores)} tasks")
        st.progress(min(1.0, active_minutes / daily_budget) if daily_budget else 0.0, width=500)


def _render_category_filter(chores: list[RecurringChore]) -> Category | None:
    used_categories = sorted({c.category for c in chores}, key=lambda cat: cat.label)
    options = ["Tout"] + [f"{cat.icon} {cat.label}" for cat in used_categories]
    choice = st.selectbox(
        "Catégorie", options=options, key="chores_category_filter",
        width=160,
    )
    if not choice or choice == "Tout":
        return None
    for cat in used_categories:
        if choice == f"{cat.icon} {cat.label}":
            return cat
    return None

def _render_toolbar() -> None:
    """Sort field + direction + details toggle, all on one line."""
    with st.container(horizontal=True, vertical_alignment="center", key="chores_sort_toolbar"):
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
        st.toggle("Details", key="chores_show_details")


def _render_add_form(service: ChoreService) -> None:
    if not st.session_state.chores_add_form_open:
        st.button("+ Ajouter une tâche", key="chores_add_toggle", type="tertiary",
                   on_click=lambda: st.session_state.__setitem__("chores_add_form_open", True))
        return

    with st.form("add_chore_form", clear_on_submit=True, border=True):
        cols = st.columns([0.4, 0.25, 0.15, 0.2])
        name = cols[0].text_input("Nom", label_visibility="collapsed", placeholder="Nom de la tâche")
        category = cols[1].selectbox(
            "Catégorie", options=list(Category), format_func=lambda c: f"{c.icon} {c.label}",
            label_visibility="collapsed",
        )
        duration = cols[2].number_input("Durée", min_value=1, step=5, value=10, label_visibility="collapsed")
        submitted = cols[3].form_submit_button("Enregistrer", width="stretch")

        if submitted and name.strip():
            service.add(name.strip(), category, "1xsemaine", int(duration), initial_priority=3.0)
            st.session_state.chores_add_form_open = False
            st.rerun()

    st.button("Annuler", key="chores_add_cancel", type="tertiary",
              on_click=lambda: st.session_state.__setitem__("chores_add_form_open", False))


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
        
        st.space("xxsmall")

        category_filter = _render_category_filter(all_today)
        if category_filter is not None:
            all_today = [c for c in all_today if c.category == category_filter]

        _render_toolbar()
        key_fn = _SORT_FIELDS[st.session_state.chores_sort_field]
        all_today = sorted(all_today, key=key_fn, reverse=st.session_state.chores_sort_desc)

        show_details = st.session_state.chores_show_details
        
        if not all_today:
            st.info("Aucune tâche à afficher pour ce filtre.")
        else:
            with st.container(gap=None):
                for chore in all_today:
                    render_task_row(
                        chore, current_date,
                        show_details=show_details,
                        next_due_date=service.next_due_date(chore.id, current_date),
                        on_toggle=lambda cid: service.toggle_complete(cid, current_date),
                        on_reschedule_today=lambda cid: service.reschedule(cid, current_date),
                        on_reschedule_weekend=lambda cid: service.reschedule(
                            cid, current_date + timedelta(days=(5 - current_date.weekday()) % 7)
                        ),
                        on_reschedule_next_due=lambda cid: service.reschedule(
                            cid, service.next_due_date(cid, current_date)
                        ),
                        on_reschedule_date=lambda cid, d: service.reschedule(cid, d),
                        on_cancel=lambda cid: service.cancel(cid),
                    )

        # Custom divider with a small margin
        st.markdown(
            '<hr style="margin: 0; border: none; border-bottom: 1px solid rgba(128, 128, 128, 0.2);" />',
            unsafe_allow_html=True,
        )    
        _render_add_form(service)
