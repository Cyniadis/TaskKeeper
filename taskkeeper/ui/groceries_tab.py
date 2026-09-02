"""The 'Groceries' tab: one data-editor tracking a tri-state shopping list.

Display labels (icon + text) live here, not on GroceryState itself —
keeps the domain model free of UI concerns.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ..domain.grocery import GroceryItem, GroceryState
from ..services.grocery_service import GroceryService

STATE_TO_LABEL = {
    GroceryState.TO_BUY: "⚪ À acheter",
    GroceryState.BOUGHT: "🟢 Acheté",
    GroceryState.NOT_TO_BUY: "⚫ Ne pas acheter",
}
LABEL_TO_STATE = {label: state for state, label in STATE_TO_LABEL.items()}


def _init_state() -> None:
    st.session_state.setdefault("groceries_grid_key", "GroceriesGrid1")
    st.session_state.setdefault("groceries_mode", False)


def _to_dataframe(items: list[GroceryItem]) -> pd.DataFrame | None:
    if not items:
        return None
    records = [
        {
            "id": item.id,
            "name": item.name,
            "state": STATE_TO_LABEL[GroceryState(item.state)],
            "last_bought_date": item.last_bought_date,
        }
        for item in items
    ]
    return pd.DataFrame.from_records(records)


def _column_config(grocery_mode: bool) -> dict:
    config = {
        "id": None,
        "name": st.column_config.TextColumn("Article", width="medium", required=True, disabled=grocery_mode),
        "state": st.column_config.SelectboxColumn("État", options=list(STATE_TO_LABEL.values()), width=140, required=True),
        "last_bought_date": st.column_config.DateColumn("Dernier achat", format="DD/MM/YYYY", disabled=True),
    }
    if grocery_mode:
        config["last_bought_date"] = None
    return config


def _apply_added_row(service: GroceryService, new_row: dict) -> None:
    service.add(new_row["name"].strip())


def _apply_edited_rows(service: GroceryService, edited_rows: dict, df: pd.DataFrame, current_date: date) -> None:
    for row_pos, changes in edited_rows.items():
        item_id = df.iloc[row_pos]["id"]
        if "name" in changes:
            service.apply_edits(item_id, {"name": changes["name"]})
        if "state" in changes:
            new_state = LABEL_TO_STATE[changes["state"]]
            if new_state == GroceryState.BOUGHT:
                service.mark_bought(item_id, current_date)
            else:
                service.set_state(item_id, new_state)


def _on_data_change(service: GroceryService, current_date: date) -> None:
    key = st.session_state.groceries_grid_key
    editor_state = st.session_state[key]
    df = st.session_state.groceries_df

    if editor_state["added_rows"]:
        _apply_added_row(service, editor_state["added_rows"][-1])
    if editor_state["edited_rows"]:
        _apply_edited_rows(service, editor_state["edited_rows"], df, current_date)
    if editor_state["deleted_rows"]:
        deleted_ids = [df.iloc[pos]["id"] for pos in editor_state["deleted_rows"]]
        service.remove(deleted_ids)
        
        
@st.dialog("Restore from backup")
def _restore_dialog(service: GroceryService) -> None:
    st.warning(
        "⚠️ Restoring a backup will **replace your entire grocery list** "
        "and cannot be undone."
    )
    uploaded = st.file_uploader("Choose a backup JSON file", type=["json"], key="groceries_restore_uploader")
    if uploaded is None:
        return
    try:
        items = service.import_json(uploaded.getvalue())
    except ValueError as exc:
        st.error(f"Could not restore this backup:\n\n{exc}")
        return
    st.success(f"Backup looks valid — {len(items)} items found.")
    st.caption("Click confirm below to replace your current list.")
    if st.button("✅ Replace list and reload", type="primary", key="groceries_restore_confirm"):
        service.restore_from_backup(items)
        st.rerun()


def render(service: GroceryService, current_date: date) -> None:
    _init_state()
    st.markdown("### Liste de courses")

    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            "⭳ Backup list", data=service.export_json(),
            file_name=f"taskkeeper_groceries_backup_{current_date.isoformat()}.json",
            mime="application/json",
        )
        if st.button("⭱ Restore from backup", key="groceries_restore_button"):
            _restore_dialog(service)
        st.toggle("🛒 Grocery mode", key="groceries_mode")
        
    items = service.get_all()
    if st.session_state.groceries_mode:
        items = [i for i in items if i.state != GroceryState.NOT_TO_BUY.value]

    df = _to_dataframe(items)
    if df is None:
        st.info("No grocery items yet — add one below.")
        df = pd.DataFrame(columns=["id", "name", "state", "last_bought_date"])

    st.session_state.groceries_df = df

    key = st.session_state.groceries_grid_key
    st.data_editor(
        df,
        column_config=_column_config(st.session_state.groceries_mode),
        hide_index=True,
        width="content",
        height="content",
        key=key,
        num_rows="fixed" if st.session_state.groceries_mode else "dynamic",
        on_change=lambda: _on_data_change(service, current_date),
    )
