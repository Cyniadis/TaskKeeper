"""Settings tab: Dropbox auto-save configuration."""
from __future__ import annotations

import sqlite3
import urllib.error
from datetime import datetime
from pathlib import Path

import streamlit as st

from ..persistence.settings_store import SettingsStore
from ..services.dropbox_service import DropboxService

_KEY_APP_KEY    = "dropbox_app_key"
_KEY_APP_SECRET = "dropbox_app_secret"
_KEY_REFRESH    = "dropbox_refresh_token"
_KEY_AUTOSAVE   = "dropbox_autosave_enabled"
_STEP_KEY       = "dbx_oauth_step"

_MIN_DB_SIZE_BYTES = 16_384  # 16 KB — blank SQLite is ≤ 8 KB


# ---------------------------------------------------------------------------
# Service construction
# ---------------------------------------------------------------------------

def _load_service(settings: SettingsStore) -> DropboxService | None:
    try:
        app_key    = st.secrets["DROPBOX_APP_KEY"]
        app_secret = st.secrets["DROPBOX_APP_SECRET"]
    except (KeyError, FileNotFoundError):
        app_key    = settings.get(_KEY_APP_KEY, "")
        app_secret = settings.get(_KEY_APP_SECRET, "")

    if not (app_key and app_secret):
        return None

    try:
        refresh_token = st.secrets["DROPBOX_REFRESH_TOKEN"]
    except (KeyError, FileNotFoundError):
        refresh_token = settings.get(_KEY_REFRESH)

    return DropboxService(app_key, app_secret, refresh_token or None)


def _save_credentials(settings: SettingsStore, app_key: str, app_secret: str) -> None:
    settings.set(_KEY_APP_KEY, app_key)
    settings.set(_KEY_APP_SECRET, app_secret)


def _save_refresh_token(settings: SettingsStore, token: str) -> None:
    settings.set(_KEY_REFRESH, token)


def _clear_credentials(settings: SettingsStore) -> None:
    settings.set(_KEY_APP_KEY, "")
    settings.set(_KEY_APP_SECRET, "")
    settings.set(_KEY_REFRESH, "")


def _db_is_safe_to_upload(db_path: Path) -> bool:
    return db_path.exists() and db_path.stat().st_size >= _MIN_DB_SIZE_BYTES


# ---------------------------------------------------------------------------
# Import from Dropbox dialog — with file picker
# ---------------------------------------------------------------------------

def _fmt_file_entry(entry: dict) -> str:
    """Human-readable label: 'taskkeeper.db  (56.2 KB, 2026-09-17 14:32)'"""
    name = entry["name"]
    size_kb = entry.get("size", 0) / 1024
    modified_raw = entry.get("server_modified", "")
    try:
        dt = datetime.strptime(modified_raw, "%Y-%m-%dT%H:%M:%SZ")
        modified = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        modified = modified_raw or "—"
    return f"{name}  ({size_kb:.1f} KB, {modified})"


@st.dialog("Import from Dropbox")
def _render_import_from_dropbox(db_path: Path, service: DropboxService) -> None:
    st.warning(
        "⚠️ This will download the selected file from your Dropbox and "
        "replace your current local database. This cannot be undone."
    )

    with st.spinner("Listing files in TaskKeeper/…"):
        try:
            files = service.list_db_files()
        except Exception as exc:
            st.error(f"Could not list Dropbox files: {exc}")
            return

    if not files:
        st.info("No .db files found in your TaskKeeper Dropbox folder.")
        return

    labels = [_fmt_file_entry(f) for f in files]
    chosen_label = st.radio(
        "Choose a file to import",
        options=labels,
        index=0,
        key="settings_import_file_radio",
    )
    chosen_idx = labels.index(chosen_label)
    chosen_path = files[chosen_idx]["path_lower"]

    st.caption(f"Remote path: `{chosen_path}`")

    if st.button("✅ Replace and reload", type="primary", key="settings_import_confirm"):
        try:
            size = service.import_from_dropbox(db_path, remote_path=chosen_path)
            st.cache_resource.clear()
            st.toast(f"Imported {files[chosen_idx]['name']} ({size / 1024:.1f} KB) — reloading…", icon="✅")
            st.rerun()
        except FileNotFoundError as exc:
            st.error(str(exc))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            st.error(f"Import failed ({exc.code}): {body}")
        except Exception as exc:
            st.error(f"Import failed: {exc}")


# ---------------------------------------------------------------------------
# Local import dialog
# ---------------------------------------------------------------------------

@st.dialog("Import from computer")
def _render_import_from_computer(db_path: Path) -> None:
    st.warning(
        "⚠️ This will replace your current database with the uploaded file. "
        "This cannot be undone."
    )
    uploaded = st.file_uploader(
        "Choose a TaskKeeper .db file", type=["db"], key="settings_local_import_uploader"
    )
    if uploaded is None:
        return
    st.caption(f"{uploaded.name} · {len(uploaded.getvalue()) / 1024:.1f} KB")
    if st.button("✅ Replace and reload", type="primary", key="settings_local_import_confirm"):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(uploaded.getvalue())
        st.cache_resource.clear()
        st.toast("Database imported — reloading…", icon="✅")
        st.rerun()


# ---------------------------------------------------------------------------
# Credentials / OAuth forms
# ---------------------------------------------------------------------------

def _render_credentials_form(settings: SettingsStore) -> None:
    st.markdown(
        "Create a Dropbox app at [dropbox.com/developers](https://www.dropbox.com/developers) "
        "with **files.content.write** permission, then paste your credentials below."
    )
    with st.form("dbx_creds_form", border=False):
        col1, col2, col3 = st.columns([1, 1, 0.4])
        app_key    = col1.text_input("App key",    placeholder="xxxxxxxxxxxx")
        app_secret = col2.text_input("App secret", placeholder="xxxxxxxxxxxx", type="password")
        submitted  = col3.form_submit_button("Save →", type="primary", use_container_width=True)
        if submitted:
            if not (app_key.strip() and app_secret.strip()):
                st.error("Both fields are required.")
            else:
                _save_credentials(settings, app_key.strip(), app_secret.strip())
                st.rerun()


def _render_oauth_flow(service: DropboxService, settings: SettingsStore) -> None:
    step = st.session_state.get(_STEP_KEY)
    if step != "awaiting_code":
        auth_url = service.authorization_url()
        st.markdown(
            "**1.** [Open Dropbox authorization →]({url}) — you'll land on a `localhost` URL "
            "that won't load; that's expected.  \n"
            "**2.** Copy the `code=…` value from the address bar, then click below.".format(url=auth_url)
        )
        col1, col2 = st.columns([1, 4])
        col1.link_button("Open Dropbox →", auth_url, type="primary", use_container_width=True)
        if col2.button("I have the code →", key="dbx_have_code"):
            st.session_state[_STEP_KEY] = "awaiting_code"
            st.rerun()
    else:
        code = st.text_input(
            "Authorization code",
            placeholder="paste the code= value from the URL",
            key="dbx_auth_code_input",
        )
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("Confirm", type="primary", key="dbx_exchange_btn"):
                if not code.strip():
                    st.error("Paste the authorization code first.")
                else:
                    try:
                        token = service.exchange_code(code.strip())
                        _save_refresh_token(settings, token)
                        st.session_state.pop(_STEP_KEY, None)
                        st.rerun()
                    except urllib.error.HTTPError as exc:
                        body = exc.read().decode(errors="replace")
                        st.error(f"Dropbox error ({exc.code}): {body}")
                    except Exception as exc:
                        st.error(str(exc))
        with col2:
            if st.button("← Start over", key="dbx_restart", type="tertiary"):
                st.session_state.pop(_STEP_KEY, None)
                st.rerun()


def _render_setup_expander(service: DropboxService | None, settings: SettingsStore) -> None:
    label = "⚙️ Dropbox setup" if (service is None or not service.is_configured()) else "⚙️ Dropbox"
    with st.expander(label):
        if service is None:
            _render_credentials_form(settings)
        elif not service.is_configured():
            _render_oauth_flow(service, settings)
        else:
            try:
                app_key    = st.secrets["DROPBOX_APP_KEY"]
                app_secret = st.secrets["DROPBOX_APP_SECRET"]
            except (KeyError, FileNotFoundError):
                app_key    = settings.get(_KEY_APP_KEY, "YOUR_APP_KEY")
                app_secret = settings.get(_KEY_APP_SECRET, "YOUR_APP_SECRET")
            refresh = settings.get(_KEY_REFRESH) or "YOUR_REFRESH_TOKEN"
            st.markdown("**secrets.toml snippet** for permanent setup:")
            st.code(
                f'[dropbox]\napp_key = "{app_key}"\napp_secret = "{app_secret}"\n'
                f'refresh_token = "{refresh}"',
                language="toml",
            )
            if st.button("Disconnect Dropbox", key="dbx_disconnect", type="tertiary"):
                _clear_credentials(settings)
                st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render(settings: SettingsStore, db_path: Path, conn: "sqlite3.Connection | None" = None) -> None:
    st.markdown("### Settings")

    service = _load_service(settings)
    configured = service is not None and service.is_configured()

    autosave_on = settings.get(_KEY_AUTOSAVE, True)
    error_msg: str | None = None

    if configured and autosave_on and _db_is_safe_to_upload(db_path):
        try:
            service.upload_db(db_path, conn)
            st.toast("Auto-saved to Dropbox", icon="☁️")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode(errors="replace")
            except Exception:
                pass
            error_msg = f"HTTP {exc.code}" + (f" — {body}" if body else "")
        except Exception as exc:
            error_msg = str(exc)

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):

        if not configured:
            st.badge("⚙️ Not configured", color="gray")
        elif error_msg:
            st.badge("❌ Error", color="red")
        else:
            st.badge("✅ Connected", color="green")

        if configured:
            def _on_autosave_change() -> None:
                settings.set(_KEY_AUTOSAVE, st.session_state.settings_autosave_toggle)

            st.toggle(
                "Auto-save",
                value=autosave_on,
                key="settings_autosave_toggle",
                help="Upload to Dropbox on every page load.",
                on_change=_on_autosave_change,
            )

            if st.button("💾 Save now", key="settings_save_now"):
                if not _db_is_safe_to_upload(db_path):
                    st.error("Local database appears empty — refusing to overwrite Dropbox.")
                else:
                    try:
                        meta = service.upload_db(db_path, conn)
                        size_kb = meta.get("size", 0) / 1024
                        st.toast(f"Saved ({size_kb:.1f} KB)", icon="✅")
                    except urllib.error.HTTPError as exc:
                        body = exc.read().decode(errors="replace")
                        st.error(f"Save failed ({exc.code}): {body}")
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

            if st.button("⬆️ Export to Dropbox", key="settings_export_btn"):
                try:
                    meta = service.export_to_dropbox(db_path, conn)
                    name = meta.get("name", "taskkeeper_export.db")
                    size_kb = meta.get("size", 0) / 1024
                    st.toast(f"Exported as {name} ({size_kb:.1f} KB)", icon="✅")
                except FileNotFoundError:
                    st.error("Local database not found — nothing to export.")
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode(errors="replace")
                    st.error(f"Export failed ({exc.code}): {body}")
                except Exception as exc:
                    st.error(f"Export failed: {exc}")

            if st.button("⬇️ Import from Dropbox", key="settings_import_btn"):
                _render_import_from_dropbox(db_path, service)

        try:
            import datetime as _dt
            if conn is not None:
                DropboxService._flush_to_disk(conn)
            db_bytes = db_path.read_bytes()
            st.download_button(
                "⬇️ Export to computer",
                data=db_bytes,
                file_name=f"taskkeeper_{_dt.date.today().isoformat()}.db",
                mime="application/octet-stream",
                key="settings_local_export",
            )
        except FileNotFoundError:
            st.button("⬇️ Export to computer", disabled=True, key="settings_local_export_disabled")

        if st.button("⬆️ Import from computer", key="settings_local_import_btn"):
            _render_import_from_computer(db_path)

    if error_msg:
        st.caption(f"⚠️ {error_msg}")

    _render_setup_expander(service, settings)