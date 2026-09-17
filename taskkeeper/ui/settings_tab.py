"""Settings tab: Dropbox auto-save configuration.

Layout (compact single row)
----------------------------
  [status badge]  [Auto-save toggle]  [💾 Save now]  [⬇️ Export]  [⬆️ Import]
  (error detail below if red)
  ── expander: Dropbox setup / disconnect / secrets snippet ──

Toast messages fire on every save or import.
"""
from __future__ import annotations

import urllib.error
from pathlib import Path

import streamlit as st

from ..persistence.settings_store import SettingsStore
from ..services.dropbox_service import DropboxService

_KEY_APP_KEY  = "dropbox_app_key"
_KEY_APP_SECRET = "dropbox_app_secret"
_KEY_REFRESH  = "dropbox_refresh_token"
_KEY_AUTOSAVE = "dropbox_autosave_enabled"
_STEP_KEY     = "dbx_oauth_step"


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


# ---------------------------------------------------------------------------
# Import dialog
# ---------------------------------------------------------------------------

@st.dialog("Import from Dropbox")
def _render_import_from_dropbox(db_path: Path, service: DropboxService) -> None:
    st.warning(
        "⚠️ This will download **TaskKeeper/taskkeeper.db** from your Dropbox and "
        "replace your current local database. This cannot be undone."
    )
    if st.button("✅ Replace and reload", type="primary", key="settings_import_confirm"):
        try:
            size = service.import_from_dropbox(db_path)
            st.cache_resource.clear()
            st.toast(f"Imported from Dropbox ({size / 1024:.1f} KB) — reloading…", icon="✅")
            st.rerun()
        except FileNotFoundError as exc:
            st.error(str(exc))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            st.error(f"Import failed ({exc.code}): {body}")
        except Exception as exc:
            st.error(f"Import failed: {exc}")


# ---------------------------------------------------------------------------
# OAuth setup (inside expander)
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


def _render_setup_expander(
    service: DropboxService | None,
    settings: SettingsStore,
) -> None:
    label = "⚙️ Dropbox setup" if (service is None or not service.is_configured()) else "⚙️ Dropbox"
    with st.expander(label):
        if service is None:
            _render_credentials_form(settings)
        elif not service.is_configured():
            _render_oauth_flow(service, settings)
        else:
            # Fully configured — show secrets snippet + disconnect
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

def render(settings: SettingsStore, db_path: Path) -> None:
    st.markdown("### Settings")

    service = _load_service(settings)
    configured = service is not None and service.is_configured()

    # -- Silent auto-save on page load -------------------------------------
    autosave_on = settings.get(_KEY_AUTOSAVE, True)
    error_msg: str | None = None

    if configured and autosave_on:
        try:
            service.upload_db(db_path)
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

    # -- Single compact control row ----------------------------------------
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):

        # Status badge
        if not configured:
            st.badge("⚙️ Not configured", color="gray")
        elif error_msg:
            st.badge("❌ Error", color="red")
        else:
            st.badge("✅ Connected", color="green")

        # Controls only shown when Dropbox is configured
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

            # Save now
            if st.button("💾 Save now", key="settings_save_now"):
                try:
                    meta = service.upload_db(db_path)
                    size_kb = meta.get("size", 0) / 1024
                    st.toast(f"Saved ({size_kb:.1f} KB)", icon="✅")
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode(errors="replace")
                    st.error(f"Save failed ({exc.code}): {body}")
                except Exception as exc:
                    st.error(f"Save failed: {exc}")

            # Export to TaskKeeper/ folder on Dropbox
            if st.button("⬆️ Export to Dropbox", key="settings_export_btn"):
                try:
                    meta = service.export_to_dropbox(db_path)
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

            # Import from TaskKeeper/ folder on Dropbox
            if st.button("⬇️ Import from Dropbox", key="settings_import_btn"):
                _render_import_from_dropbox(db_path, service)

    # Error detail (shown only when status is red)
    if error_msg:
        st.caption(f"⚠️ {error_msg}")

    # Setup expander
    _render_setup_expander(service, settings)