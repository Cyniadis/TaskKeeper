"""Sync status bar: badge, enable/disable toggle, manual save/pull buttons.

Rendered in the top-right of the main layout. Kept in its own module so
app_streamlit.py stays a thin wiring file.

Entry point: render(sync, settings, db_path)
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from ..persistence.dropbox_sync import DropboxSync
from ..persistence.settings_store import SettingsStore

_AUTOSAVE_KEY = "autosave_enabled"


def render(sync: DropboxSync | None, settings: SettingsStore, db_path: Path) -> None:
    """Render the full sync control bar into the current layout position.

    Parameters
    ----------
    sync:
        The DropboxSync instance (or None when Dropbox secrets are not set).
    settings:
        The app's SettingsStore, used to persist the autosave toggle.
    db_path:
        Local path of the SQLite DB — needed by the Pull button to delete
        the local file before re-downloading.
    """
    if sync is None:
        st.badge("⚙️ Auto-save not configured", color="gray")
        return

    autosave_on = settings.get(_AUTOSAVE_KEY, True)

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):

        # -- enable / disable toggle ---------------------------------------
        def _on_toggle_change() -> None:
            new_value = st.session_state.autosave_toggle
            settings.set(_AUTOSAVE_KEY, new_value)
            # Immediate push when re-enabling so nothing is lost.
            if new_value:
                msg = sync.push(force=True)
                if msg:
                    st.toast(msg, icon="☁️")

        new_autosave_on = st.toggle(
            "Auto-save",
            label_visibility="collapsed",
            value=autosave_on,
            key="autosave_toggle",
            help="Automatically save the database to Dropbox every 30 seconds.",
            on_change=_on_toggle_change,
        )

        # -- status badge --------------------------------------------------
        if new_autosave_on:
            st.badge("Auto-save ON", color="green")
        else:
            st.badge("Auto-save OFF", color="orange")

        # -- manual save ---------------------------------------------------
        def _manual_push() -> None:
            msg = sync.push(force=True)
            st.toast(msg if msg else "Nothing to save.", icon="☁️")

        st.button("💾 Save now", key="manual_push", type="tertiary", on_click=_manual_push)

        # -- manual pull ---------------------------------------------------
        def _manual_pull() -> None:
            if db_path.exists():
                db_path.unlink()
            msg = sync.pull()
            if msg:
                st.toast(msg, icon="📥")
                st.cache_resource.clear()
            else:
                st.toast("No remote file found.", icon="⚠️")

        st.button("⬇️ Pull now", key="manual_pull", type="tertiary", on_click=_manual_pull)