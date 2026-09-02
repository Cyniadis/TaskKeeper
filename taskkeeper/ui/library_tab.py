"""The 'Task Library' tab: bulk view/edit of every recurring chore.

Kept as the one screen that still uses st.data_editor — sorting/bulk
editing a list of 10-30+ chores is genuinely the one interaction a grid
suits better than the compact row list the Chores tab uses.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from ..domain.task import Category, Period
from ..services.chore_service import ChoreService
from .components import render_reschedule

_CATEGORY_OPTIONS = [f"{cat.icon} {cat.label}" for cat in Category]
_CATEGORY_LABEL_TO_ENUM = {f"{cat.icon} {cat.label}": cat for cat in Category}

_COLUMNS = [
    "state", "id", "category", "name", "frequency_count", "frequency_period",
    "priority", "initial_priority", "duration", "due_date", "done_date",
    "prereq", "prereq_window_days", "reschedule", "changes",
]

# Sentinel shown in the prereq selectbox when no prerequisite is set.
_NO_PREREQ = "—"


def _init_state() -> None:
    st.session_state.setdefault("library_sort_field", "name")
    st.session_state.setdefault("library_sort_asc", True)
    st.session_state.setdefault("library_grid_key", "LibraryGrid1")


def _build_prereq_options(service: ChoreService) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return (options_list, label→id map, id→label map) for the prereq selectbox."""
    chores = service.get_all()
    id_to_label = {c.id: f"{c.category.icon} {c.name}" for c in chores}
    label_to_id = {v: k for k, v in id_to_label.items()}
    options = [_NO_PREREQ] + sorted(id_to_label.values())
    return options, label_to_id, id_to_label


def _to_dataframe(service: ChoreService, id_to_label: dict[str, str]) -> pd.DataFrame | None:
    chores = service.get_all()
    if not chores:
        return None
    records = []
    for c in chores:
        freq = c.frequency_obj
        state = (
            "✅" if c.is_completed()
            else "❌" if c.is_cancelled()
            else "📅" if c.is_manually_rescheduled()
            else ""
        )
        has_changes = bool(service.changes_for(c.id))
        prereq_label = id_to_label.get(c.prereq_id, _NO_PREREQ) if c.prereq_id else _NO_PREREQ
        records.append({
            "id": c.id,
            "category": f"{c.category.icon} {c.category.label}",
            "name": c.name,
            "frequency_count": freq.count,
            "frequency_period": freq.period.value,
            "priority": c.priority,
            "initial_priority": c.initial_priority,
            "duration": c.duration,
            "due_date": c.due_date,
            "done_date": c.done_date,
            "state": state,
            "prereq": prereq_label,
            "prereq_window_days": c.prereq_window_days,
            "reschedule": ":material/edit_calendar: Reporter",
            "changes": ":material/edit_note: Changes" if has_changes else None,
        })
    return pd.DataFrame.from_records(records, columns=_COLUMNS)


def _column_config(
    prereq_options: list[str],
    on_show_changes,
    on_reschedule,
) -> dict:
    return {
        "id": None,
        "category": st.column_config.SelectboxColumn("Catégorie", options=_CATEGORY_OPTIONS, required=True),
        "name": st.column_config.TextColumn("Tâche", required=True),
        "frequency_count": st.column_config.NumberColumn(
            "", min_value=1, step=1, format="%d", required=True,
        ),
        "frequency_period": st.column_config.SelectboxColumn(
            "Période", options=[p.value for p in Period], required=True,
        ),
        "priority": st.column_config.NumberColumn("Priorité", step=0.5, format="%.1f"),
        "initial_priority": st.column_config.NumberColumn("Priorité init.", step=0.5, format="%.1f", required=True),
        "duration": st.column_config.NumberColumn("Durée (min)", min_value=1, step=5, required=True),
        "due_date": st.column_config.DateColumn("Échéance", format="DD/MM/YYYY", disabled=True),
        "done_date": st.column_config.DateColumn("Fait le", format="DD/MM/YYYY"),
        "state": st.column_config.TextColumn("État", disabled=True, alignment="center"),
        "prereq": st.column_config.SelectboxColumn(
            "Prérequis",
            options=prereq_options,
            help="This chore only appears once the selected prerequisite chore has been completed.",
            width=180,
        ),
        "prereq_window_days": st.column_config.NumberColumn(
            "Fenêtre (j)",
            min_value=0,
            max_value=30,
            step=1,
            format="%d j",
            help="How many days after the prerequisite was completed this chore stays eligible. 0 = same day only, 1 = today or yesterday, …",
            width=90,
        ),
        "reschedule": st.column_config.ButtonColumn(
            "", on_click=on_reschedule, key="show_reschedule_button", alignment="left", width=100,
        ),
        "changes": st.column_config.ButtonColumn(
            "", on_click=on_show_changes, key="show_changes_button", alignment="left", width=100,
        ),
    }


def _apply_added_row(service: ChoreService, new_row: dict, label_to_id: dict[str, str]) -> None:
    category = _CATEGORY_LABEL_TO_ENUM.get(new_row.get("category"), Category.OTHER)
    frequency = f"{int(new_row['frequency_count'])}x{new_row['frequency_period']}"
    chore = service.add(
        name=new_row["name"].strip(),
        category=category,
        frequency=frequency,
        duration=int(new_row["duration"]),
        initial_priority=float(new_row["initial_priority"]),
    )
    # Apply prereq if provided in the add row
    prereq_label = new_row.get("prereq", _NO_PREREQ)
    if prereq_label and prereq_label != _NO_PREREQ:
        prereq_id = label_to_id.get(prereq_label)
        if prereq_id:
            try:
                service.set_prereq(chore.id, prereq_id, int(new_row.get("prereq_window_days", 1)))
            except ValueError:
                pass  # cycle guard — shouldn't happen on a brand-new chore


def _apply_edited_rows(
    service: ChoreService,
    edited_rows: dict,
    df: pd.DataFrame,
    label_to_id: dict[str, str],
) -> None:
    for row_pos, changes in edited_rows.items():
        chore_id = df.iloc[row_pos]["id"]
        field_changes: dict = {}

        if "frequency_count" in changes or "frequency_period" in changes:
            count = changes.get("frequency_count", df.iloc[row_pos]["frequency_count"])
            period = changes.get("frequency_period", df.iloc[row_pos]["frequency_period"])
            field_changes["frequency"] = f"{int(count)}x{period}"

        if "category" in changes:
            field_changes["category"] = _CATEGORY_LABEL_TO_ENUM.get(changes["category"], Category.OTHER)


        if "done_date" in changes:
            field_changes["done_date"] = date.fromisoformat(changes["done_date"])
            field_changes["due_date"] = service.next_due_date(chore_id, field_changes["done_date"])
            
        for key in ("name", "priority", "initial_priority", "duration"):
            if key in changes:
                field_changes[key] = changes[key]

        if field_changes:
            service.apply_edits(chore_id, field_changes)

        # Handle prereq changes separately (they go through set_prereq for
        # cycle detection, not through the generic apply_edits path).
        prereq_changed = "prereq" in changes
        window_changed = "prereq_window_days" in changes

        if prereq_changed or window_changed:
            prereq_label = changes.get("prereq", df.iloc[row_pos]["prereq"])
            window = int(changes.get("prereq_window_days", df.iloc[row_pos]["prereq_window_days"]))
            new_prereq_id = label_to_id.get(prereq_label) if prereq_label != _NO_PREREQ else None
            try:
                service.set_prereq(chore_id, new_prereq_id, window)
            except ValueError as exc:
                st.error(str(exc))


def _on_data_change(service: ChoreService, label_to_id: dict[str, str]) -> None:
    key = st.session_state.library_grid_key
    editor_state = st.session_state[key]
    df = st.session_state.library_df

    if editor_state["added_rows"]:
        _apply_added_row(service, editor_state["added_rows"][-1], label_to_id)
    if editor_state["edited_rows"]:
        _apply_edited_rows(service, editor_state["edited_rows"], df, label_to_id)
    if editor_state["deleted_rows"]:
        deleted_ids = [df.iloc[pos]["id"] for pos in editor_state["deleted_rows"]]
        service.remove(deleted_ids)


def _reload_grid() -> None:
    import datetime as _dt
    st.session_state.library_grid_key = f"LibraryGrid{_dt.datetime.now().timestamp()}"


@st.dialog("Restore from backup")
def _restore_dialog(service: ChoreService) -> None:
    st.warning(
        "⚠️ Restoring a backup will **replace your entire task library** "
        "(priorities, due dates, done dates — everything) and cannot be undone."
    )
    uploaded = st.file_uploader("Choose a backup JSON file", type=["json"], key="library_restore_uploader")
    if uploaded is None:
        return

    try:
        chores = service.import_json(uploaded.getvalue())
    except ValueError as exc:
        st.error(f"Could not restore this backup:\n\n{exc}")
        return

    st.success(f"Backup looks valid — {len(chores)} chores found.")
    st.caption("Click confirm below to replace your current library.")
    if st.button("✅ Replace library and reload", type="primary", key="library_restore_confirm"):
        service.restore_from_backup(chores)
        _reload_grid()
        st.rerun()


def render(service: ChoreService) -> None:
    _init_state()
    st.markdown(
        """
        <style>
        [data-testid="stTabPanel"] > div {
            overflow-x: auto !important;
        }
        [data-testid="stTabPanel"] iframe {
            min-width: 1500px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Task Library")

    prereq_options, label_to_id, id_to_label = _build_prereq_options(service)

    cont = st.container(horizontal=True, vertical_alignment="center")
    cont.download_button(
        "⭳ Backup library",
        data=service.export_json(),
        file_name=f"taskkeeper_backup_{date.today().isoformat()}.json",
        mime="application/json",
    )
    if cont.button("⭱ Restore from backup", key="library_restore_button"):
        _restore_dialog(service)

    df = _to_dataframe(service, id_to_label)
    if df is None:
        st.info("No chores yet — add one from the grid below.")
        df = pd.DataFrame(columns=_COLUMNS)

    with cont.container(horizontal=True, vertical_alignment="center", gap="xsmall"):
        st.markdown("**Sort by**")
        sort_col = st.selectbox(
            "Sort by", options=[c for c in df.columns if c not in ("id", "changes")],
            key="library_sort_field", width=160, label_visibility="collapsed"
        )
        asc_label = "▲ Ascending" if st.session_state.library_sort_asc else "▼ Descending"
        st.button(
            asc_label, key="library_sort_dir", type="tertiary",
            on_click=lambda: st.session_state.__setitem__(
                "library_sort_asc", not st.session_state.library_sort_asc
            ),
        )

    sorted_df = df.sort_values(by=sort_col, ascending=st.session_state.library_sort_asc).reset_index(drop=True)
    st.session_state.library_df = sorted_df

    @st.dialog("Changes")
    def _show_changes_dialog(row: int) -> None:
        row_df = st.session_state.library_df
        chore_id = row_df.iloc[row]["id"]
        chore_name = row_df.iloc[row]["name"]
        st.markdown(f"**{chore_name}**")

        diffs = service.changes_for(chore_id)
        if not diffs:
            st.info("No changes on this chore.")
            return

        for label, old, new in diffs:
            st.markdown(f"**{label}:** ~~{old or '—'}~~ → {new or '—'}")

        if st.button("Discard changes", key="library_discard_changes"):
            service.discard_changes(chore_id)
            st.rerun()

    def _on_show_changes_click() -> None:
        click = st.session_state.show_changes_button
        _show_changes_dialog(click["row"])

    @st.dialog("Reschedule chore")
    def _show_reschedule_dialog(row: int) -> None:
        row_df = st.session_state.library_df
        chore_id = row_df.iloc[row]["id"]
        chore = next((item for item in service.get_all() if item.id == chore_id), None)
        if chore is None:
            st.error("Chore not found.")
            return

        current_date = date.today()
        next_due_date = service.next_due_date(chore_id, chore.due_date or current_date)

        if render_reschedule(
            chore=chore,
            current_date=current_date,
            next_due_date=next_due_date,
            on_reschedule_today=lambda cid: service.reschedule(cid, current_date),
            on_reschedule_weekend=lambda cid: service.reschedule(
                cid, current_date + timedelta(days=(5 - current_date.weekday()) % 7)
            ),
            on_reschedule_next_due=lambda cid: (
                service.reschedule(cid, next_due_date) if next_due_date else None
            ),
            on_reschedule_date=lambda cid, selected_date: service.reschedule(cid, selected_date),
            on_cancel=lambda cid: st.rerun(),
            key_prefix="dialog"
        ):
            st.rerun()

    def _on_reschedule_click() -> None:
        click = st.session_state.show_reschedule_button
        _show_reschedule_dialog(click["row"])
        _reload_grid()

    key = st.session_state.library_grid_key
    st.data_editor(
        sorted_df,
        column_config=_column_config(prereq_options, _on_show_changes_click, _on_reschedule_click),
        hide_index=True,
        width="content",
        height="content",
        key=key,
        num_rows="dynamic",
        on_change=lambda: _on_data_change(service, label_to_id),
    )
