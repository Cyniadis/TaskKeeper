"""TaskKeeper — Streamlit entry point.

Run with: streamlit run app_streamlit.py

Full implementation of architecture.md: every service (ChoreService,
OneTimeTaskService, GroceryService, TimerService) and the ChangeLog are
wired up for real here — nothing left as a placeholder.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import streamlit as st

from taskkeeper.persistence.change_log import ChangeLog
from taskkeeper.persistence.grocery_repository import build_grocery_repository
from taskkeeper.persistence.settings_store import SettingsStore
from taskkeeper.persistence.task_repository import (
    build_chore_repository,
    build_onetime_repository,
)
from taskkeeper.services.chore_service import ChoreService, OneTimeTaskService
from taskkeeper.services.grocery_service import GroceryService
from taskkeeper.services.timer_service import TimerService
from taskkeeper.ui import chores_tab, groceries_tab, library_tab, onetime_tab, timer_tab

# Overridable so tests / a docker setup can point elsewhere without
# touching this file; defaults to a real, persistent file next to the app.
DB_PATH = Path(os.environ.get("TASKKEEPER_DB_PATH", "data/taskkeeper.db"))


@dataclass
class Services:
    chores: ChoreService
    onetime: OneTimeTaskService
    groceries: GroceryService
    timer: TimerService


@st.cache_resource(show_spinner=False)
def get_connection() -> sqlite3.Connection:
    """One persistent SQLite connection per app session — the file at
    DB_PATH is the actual source of truth now, surviving both Streamlit
    reruns (via st.cache_resource) and full process restarts (via the
    file itself). Use migrate_legacy_data.py to populate it from the
    original app's JSON files."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_resource(show_spinner=False)
def build_services() -> Services:
    """The only place concrete repositories/services get constructed —
    everything above this only ever sees the Services dataclass."""
    conn = get_connection()

    chore_repo = build_chore_repository(conn)
    onetime_repo = build_onetime_repository(conn)
    grocery_repo = build_grocery_repository(conn)
    change_log = ChangeLog(conn)
    settings = SettingsStore(conn)

    chores_service = ChoreService(chore_repo, change_log)
    chores_service.snapshot_baseline()

    return Services(
        chores=chores_service,
        onetime=OneTimeTaskService(onetime_repo),
        groceries=GroceryService(grocery_repo),
        timer=TimerService(settings),
    )


def main() -> None:
    st.set_page_config(page_title="TaskKeeper", layout="wide")
    
    
    st.markdown(
    """
    <style>
        .block-container {
        margin-left: auto;
        margin-right: auto;
        width: 90%;
        text-align: center;
        }
    </style>
    """,
    unsafe_allow_html=True)

    st.title("TaskKeeper", anchor=False)

    services = build_services()
    today = date.today()

    chores_ui, library_ui, onetime_ui, groceries_ui, timer_ui = st.tabs(
        ["📝 Chores", "📋 Library", "🗓️ One-time", "🛒 Groceries", "⏱️ Timer"])

    with chores_ui:
        chores_tab.render(services.chores, today)

    with library_ui:
        library_tab.render(services.chores)

    with onetime_ui:
        onetime_tab.render(services.onetime, today)

    with groceries_ui:
        groceries_tab.render(services.groceries, today)

    with timer_ui:
        timer_tab.render(services.timer)


if __name__ == "__main__":
    main()