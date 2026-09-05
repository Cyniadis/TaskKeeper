"""The 'One-time' tab: manage tasks that don't recur.

Layout mirrors the Chores tab:
  - Header with section title
  - Progress bar (active minutes / budget)
  - Shared sort + filter toolbar (render_sort_filter_toolbar)
  - Per-row: [✓] [icon] [name ~~~ :badge:] ──stretch── [detail?] [dur] [⋯]
  - ⋯ popover: schedule/unschedule + delete
  - Add-task form at the bottom

No priority dot or reschedule submenus — OneTimeTask has none of those.
The ⋯ popover hosts schedule/unschedule and removal instead, keeping the
row itself clean.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from ..domain.task import Category, OneTimeTask
from ..services.chore_service import OneTimeTaskService
from .components import render_sort_filter_toolbar
from .format import format_date_short_fr

_SORT_FIELDS = {
    "Nom": lambda t: t.name.lower(),
    "Durée": lambda t: t.duration,
    "Catégorie": lambda t: t.category.label,
}


def _init_state() -> None:
    st.session_state.setdefault("onetime_add_form_open", False)
    st.session_state.setdefault("onetime_show_completed", True)
    st.session_state.setdefault("onetime_show_details", False)
    st.session_state.setdefault("onetime_sort_field", "Nom")
    st.session_state.setdefault("onetime_sort_desc", False)
    st.session_state.setdefault("onetime_category_filter", [])


# ---------------------------------------------------------------------------
# Header / progress
# ---------------------------------------------------------------------------

@st.dialog("Restore from backup")
def _restore_dialog(service: OneTimeTaskService) -> None:
    st.warning(
        "⚠️ Restoring a backup will **replace your entire one-time task list** "
        "and cannot be undone."
    )
    uploaded = st.file_uploader("Choose a backup JSON file", type=["json"], key="onetime_restore_uploader")
    if uploaded is None:
        return
    try:
        tasks = service.import_json(uploaded.getvalue())
    except ValueError as exc:
        st.error(f"Could not restore this backup:\n\n{exc}")
        return
    st.success(f"Backup looks valid — {len(tasks)} tasks found.")
    st.caption("Click confirm below to replace your current list.")
    if st.button("✅ Replace list and reload", type="primary", key="onetime_restore_confirm"):
        service.restore_from_backup(tasks)
        st.rerun()


def _render_header(service: OneTimeTaskService, current_date: date) -> None:
    st.markdown("### One-time tasks")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            "⭳ Backup list",
            data=service.export_json(),
            file_name=f"taskkeeper_onetime_backup_{current_date.isoformat()}.json",
            mime="application/json",
        )
        if st.button("⭱ Restore from backup", key="onetime_restore_button"):
            _restore_dialog(service)

# ---------------------------------------------------------------------------
# Individual task row
# ---------------------------------------------------------------------------

def _render_row(
    task: OneTimeTask,
    current_date: date,
    service: OneTimeTaskService,
    *,
    show_details: bool,
) -> None:
    is_done = task.is_completed_on(current_date)
    is_scheduled = task.is_manually_rescheduled()
    name_text = f"~~{task.name}~~" if task.is_completed() else task.name

    with st.container(
        key=f"onetime_row_{task.id}",
        horizontal=True,
        vertical_alignment="center",
        gap="small",
    ):
        # -- checkbox -------------------------------------------------------
        st.checkbox(
            "done",
            value=is_done,
            key=f"onetime_chk_{task.id}",
            label_visibility="collapsed",
            on_change=lambda tid=task.id: service.toggle_complete(tid, current_date),
        )

        # -- category icon --------------------------------------------------
        st.markdown(task.category.icon, width="content")

        # -- name + optional badge (stretches) ------------------------------
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small", width="stretch"
        ):
            st.markdown(name_text, width="content")
            if is_scheduled:
                st.badge("sur aujourd'hui", color="green")

        # -- detail: done/due date ------------------------------------------
        if show_details:
            shown_date = task.done_date if is_done else task.due_date
            st.caption(
                format_date_short_fr(shown_date) if shown_date else "—",
                width="content",
            )

        # -- duration -------------------------------------------------------
        st.caption(f"{task.duration} min", width="content")

        # -- actions popover ------------------------------------------------
        with st.popover(":material/edit_calendar:", width="content"):
            with st.container(horizontal=False):
                if is_scheduled:
                    st.button(
                        "✓ Retirer d'aujourd'hui",
                        key=f"onetime_unsched_{task.id}",
                        width="stretch",
                        on_click=lambda tid=task.id: service.unschedule(tid),
                    )
                else:
                    st.button(
                        "📅 Ajouter à aujourd'hui",
                        key=f"onetime_sched_{task.id}",
                        width="stretch",
                        on_click=lambda tid=task.id: service.schedule_for_today(tid, current_date),
                    )
                st.button(
                    "🗑 Supprimer",
                    key=f"onetime_del_{task.id}",
                    width="stretch",
                    on_click=lambda tid=task.id: service.remove([tid]),
                )


# ---------------------------------------------------------------------------
# Add form
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render(service: OneTimeTaskService, current_date: date) -> None:
    _init_state()

    with st.container(width="content", horizontal_alignment="left"):
        _render_header(service, current_date)
        
        all_tasks = service.get_all()
        if not st.session_state.onetime_show_completed:
            all_tasks = [t for t in all_tasks if not t.is_completed()]

        key_fn, descending, category_filter = render_sort_filter_toolbar(
            items=all_tasks,
            sort_fields=_SORT_FIELDS,
            get_category=lambda t: t.category,
            sort_field_key="onetime_sort_field",
            sort_desc_key="onetime_sort_desc",
            show_details_key="onetime_show_details",
            category_filter_key="onetime_category_filter",
            extra_toggles=[("Show completed", "onetime_show_completed")],
        )

        if category_filter:
            all_tasks = [t for t in all_tasks if t.category in category_filter]

        all_tasks = sorted(all_tasks, key=key_fn, reverse=descending)
        show_details = st.session_state.onetime_show_details

        if not all_tasks:
            st.info("Aucune tâche à afficher pour ce filtre.")
        else:
            with st.container(gap=None, width=700):
                for task in all_tasks:
                    _render_row(task, current_date, service, show_details=show_details)

        st.markdown(
            '<hr style="margin: 0; border: none; border-bottom: 1px solid rgba(128, 128, 128, 0.2);" />',
            unsafe_allow_html=True,
        )
        _render_add_form(service)
