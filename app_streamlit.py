"""TaskKeeper — Streamlit entry point.

Persistence strategy:
- SQLite in /tmp (fast, ephemeral — wiped on redeploy/restart)
- Raw .db file synced to Dropbox (durable — pulled on cold start, pushed after writes)

Set DROPBOX_APP_KEY / DROPBOX_APP_SECRET / DROPBOX_REFRESH_TOKEN in Streamlit secrets to
enable sync. The app works without them (local dev).
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import streamlit as st

from taskkeeper.persistence.change_log import ChangeLog
from taskkeeper.persistence.dropbox_sync import DropboxSync
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
from taskkeeper.ui import sync_status

DB_PATH = Path(os.environ.get("TASKKEEPER_DB_PATH", "/tmp/taskkeeper.db"))

_AUTOSAVE_KEY = "autosave_enabled"


@dataclass
class Services:
    chores: ChoreService
    onetime: OneTimeTaskService
    groceries: GroceryService
    timer: TimerService
    settings: SettingsStore


@st.cache_resource(show_spinner=False)
def get_sync() -> DropboxSync | None:
    return DropboxSync.from_secrets(DB_PATH)


@st.cache_resource(show_spinner=False)
def get_connection() -> sqlite3.Connection:
    sync = get_sync()
    if sync is not None:
        msg = sync.pull()
        if msg:
            st.toast(msg, icon="✅")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_resource(show_spinner=False)
def build_services() -> Services:
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
        settings=settings,
    )


def _auto_push(services: Services) -> None:
    """Rate-limited push on every rerun — only when autosave is enabled."""
    sync = get_sync()
    if sync is None:
        return
    if not services.settings.get(_AUTOSAVE_KEY, True):
        return
    msg = sync.push()
    if msg:
        st.toast(msg, icon="☁️")


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
        unsafe_allow_html=True,
    )

    services = build_services()
    today = date.today()

    st.title("TaskKeeper", anchor=False)
    sync_status.render(get_sync(), services.settings, DB_PATH)

    _auto_push(services)

    chores_ui, library_ui, onetime_ui, groceries_ui, timer_ui = st.tabs(
        ["📝 Chores", "📋 Library", "🗓️ One-time", "🛒 Groceries", "⏱️ Timer"]
    )

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