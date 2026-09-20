"""TaskKeeper — Streamlit entry point.

Run with: streamlit run app_streamlit.py
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
from taskkeeper.ui import settings_tab

DB_PATH = Path(os.environ.get("TASKKEEPER_DB_PATH", "data/taskkeeper.db"))


@dataclass
class Services:
    chores: ChoreService
    onetime: OneTimeTaskService
    groceries: GroceryService
    timer: TimerService
    settings: SettingsStore


@st.cache_resource(show_spinner=False)
def pull_from_dropbox_once() -> tuple[str | None, str | None]:
    """Pull the DB from Dropbox exactly once per process lifetime,
    before the SQLite connection is opened.

    Returns (success_message, error_message) — one of the two will be None.
    """
    if DB_PATH.exists():
        return None, None  # warm restart — file already on disk

    try:
        app_key = st.secrets["DROPBOX_APP_KEY"]
        app_secret = st.secrets["DROPBOX_APP_SECRET"]
        refresh = st.secrets["DROPBOX_REFRESH_TOKEN"]
    except (KeyError, FileNotFoundError):
        return None, None  # Dropbox not configured — skip silently

    from taskkeeper.services.dropbox_service import DropboxService

    svc = DropboxService(app_key, app_secret, refresh)
    try:
        size = svc.import_from_dropbox(DB_PATH)
        return f"📥 Pulled from Dropbox ({size / 1024:.1f} KB)", None
    except FileNotFoundError:
        return None, None  # no remote file yet — first-ever deploy
    except Exception as exc:
        # Surface the error so it's visible in the UI rather than silently
        # leaving a blank DB that will then overwrite the real one on Dropbox.
        return None, f"⚠️ Dropbox pull failed on cold start: {exc}"


@st.cache_resource(show_spinner=False)
def get_connection() -> sqlite3.Connection:
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

    st.title("TaskKeeper", anchor=False)

    # Pull from Dropbox BEFORE build_services() opens the SQLite connection.
    # On a Streamlit Cloud cold start the local file doesn't exist yet —
    # without this pull, build_services() would create a blank DB which
    # auto-save would then upload, overwriting the real data on Dropbox.
    pull_msg, pull_err = pull_from_dropbox_once()
    if pull_msg:
        st.toast(pull_msg, icon="📥")
    if pull_err:
        # Show a persistent banner so the error is visible even on the
        # Settings tab — a toast would disappear before the user sees it.
        st.error(pull_err)

    services = build_services()
    conn = get_connection()
    today = date.today()

    chores_ui, library_ui, onetime_ui, groceries_ui, timer_ui, settings_ui = st.tabs(
        ["📝 Chores", "📋 Library", "🗓️ One-time", "🛒 Groceries", "⏱️ Timer", "⚙️ Settings"]
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

    with settings_ui:
        settings_tab.render(services.settings, DB_PATH, conn)


if __name__ == "__main__":
    main()