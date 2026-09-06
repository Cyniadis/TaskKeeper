"""Settings tab: Dropbox auto-save configuration.

Three states the UI handles:
  1. Fully configured via st.secrets  → show status + manual upload button.
  2. Partially configured (key+secret in secrets, no refresh token yet)
     → show the OAuth flow to generate + save the refresh token.
  3. Nothing in secrets → show a form to enter key + secret, then OAuth flow.

The refresh token, once obtained, is persisted in SettingsStore so the app
survives restarts without repeating the flow.
"""
from __future__ import annotations

import urllib.error
from pathlib import Path

import streamlit as st

from ..persistence.settings_store import SettingsStore
from ..services.dropbox_service import DropboxService

_KEY_APP_KEY = "dropbox_app_key"
_KEY_APP_SECRET = "dropbox_app_secret"
_KEY_REFRESH = "dropbox_refresh_token"

_STEP_KEY = "dbx_oauth_step"   # session-state machine: None | "awaiting_code"


def _load_service(settings: SettingsStore) -> DropboxService | None:
    """Build a DropboxService from secrets → SettingsStore fallback.

    Returns None when no app_key/app_secret is available at all.
    """
    # Prefer st.secrets, fall back to SettingsStore (user entered via form)
    try:
        app_key = st.secrets["DROPBOX_APP_KEY"]
        app_secret = st.secrets["DROPBOX_APP_SECRET"]
    except (KeyError, FileNotFoundError):
        app_key = settings.get(_KEY_APP_KEY, "")
        app_secret = settings.get(_KEY_APP_SECRET, "")

    if not (app_key and app_secret):
        return None

    # Refresh token: secrets first, then SettingsStore (persisted after flow)
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
# Sub-sections
# ---------------------------------------------------------------------------

def _render_credentials_form(settings: SettingsStore) -> None:
    """Shown when no app key/secret is available anywhere."""
    st.markdown("#### Connect your Dropbox app")
    st.markdown(
        "Create a Dropbox app at [dropbox.com/developers](https://www.dropbox.com/developers), "
        "then paste your **App key** and **App secret** below. "
        "Make sure the app has **files.content.write** permission enabled."
    )
    with st.form("dbx_creds_form", border=True):
        app_key = st.text_input("App key", placeholder="xxxxxxxxxxxx")
        app_secret = st.text_input("App secret", placeholder="xxxxxxxxxxxx", type="password")
        submitted = st.form_submit_button("Save and continue →", type="primary")
        if submitted:
            if not (app_key.strip() and app_secret.strip()):
                st.error("Both fields are required.")
            else:
                _save_credentials(settings, app_key.strip(), app_secret.strip())
                st.rerun()


def _render_oauth_flow(service: DropboxService, settings: SettingsStore) -> None:
    """Step-by-step OAuth flow for getting a refresh token."""
    st.markdown("#### Authorize TaskKeeper to access Dropbox")

    step = st.session_state.get(_STEP_KEY)

    if step != "awaiting_code":
        # Step 1 — send user to Dropbox
        auth_url = service.authorization_url()
        st.markdown(
            "**Step 1 —** Click the button below to open Dropbox in a new tab and authorize "
            "the app. You'll be redirected to a `localhost` URL that won't load — that's expected."
        )
        st.link_button("Open Dropbox authorization →", auth_url, type="primary")
        st.markdown(
            "**Step 2 —** After authorizing, copy the `code=…` value from the URL in your "
            "browser's address bar, then click **I have the code** below."
        )
        if st.button("I have the code →", key="dbx_have_code"):
            st.session_state[_STEP_KEY] = "awaiting_code"
            st.rerun()
    else:
        # Step 2 — exchange the code
        st.markdown(
            "**Paste the authorization code** from your browser's address bar. "
            "It's the value after `code=` (and before `&` if there are other params)."
        )
        code = st.text_input(
            "Authorization code", placeholder="paste the code here", key="dbx_auth_code_input"
        )
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("Get refresh token", type="primary", key="dbx_exchange_btn"):
                if not code.strip():
                    st.error("Paste the authorization code first.")
                else:
                    try:
                        refresh_token = service.exchange_code(code.strip())
                        _save_refresh_token(settings, refresh_token)
                        st.session_state.pop(_STEP_KEY, None)
                        st.success("✅ Authorized! Refresh token saved.")
                        st.rerun()
                    except urllib.error.HTTPError as exc:
                        body = exc.read().decode(errors="replace")
                        st.error(f"Dropbox returned an error ({exc.code}): {body}")
                    except Exception as exc:
                        st.error(f"Unexpected error: {exc}")
        with col2:
            if st.button("← Start over", key="dbx_restart", type="tertiary"):
                st.session_state.pop(_STEP_KEY, None)
                st.rerun()


def _render_connected(
    service: DropboxService,
    settings: SettingsStore,
    db_path: Path,
) -> None:
    """Shown when the service is fully configured."""
    st.success("✅ Dropbox connected — auto-save is active.")

    st.markdown("**Database path on Dropbox:** `/taskkeeper.db`")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("☁ Upload now", key="dbx_upload_now", type="primary"):
            with st.spinner("Uploading…"):
                try:
                    meta = service.upload_db(db_path)
                    name = meta.get("name", "taskkeeper.db")
                    size = meta.get("size", 0)
                    st.success(f"Uploaded **{name}** ({size:,} bytes).")
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode(errors="replace")
                    st.error(f"Upload failed ({exc.code}): {body}")
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")
    with col2:
        if st.button("Disconnect Dropbox", key="dbx_disconnect", type="tertiary"):
            _clear_credentials(settings)
            st.rerun()

    with st.expander("secrets.toml snippet (for permanent setup)"):
        st.markdown(
            "To skip this flow on future deployments, add these to your "
            "`.streamlit/secrets.toml` and to Streamlit Cloud's secret manager:"
        )
        try:
            app_key = st.secrets["dropbox"]["app_key"]
            app_secret = st.secrets["dropbox"]["app_secret"]
        except (KeyError, FileNotFoundError):
            app_key = settings.get(_KEY_APP_KEY, "YOUR_APP_KEY")
            app_secret = settings.get(_KEY_APP_SECRET, "YOUR_APP_SECRET")
        refresh = settings.get(_KEY_REFRESH) or "YOUR_REFRESH_TOKEN"
        st.code(
            f'[dropbox]\napp_key = "{app_key}"\napp_secret = "{app_secret}"\n'
            f'refresh_token = "{refresh}"',
            language="toml",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render(settings: SettingsStore, db_path: Path) -> None:
    st.markdown("### Settings")

    # Auto-save on every render when configured
    service = _load_service(settings)
    if service and service.is_configured():
        try:
            service.upload_db(db_path)
        except Exception:
            pass  # silent — the manual button shows errors; silent fail here avoids blocking the UI

    st.markdown("#### Dropbox auto-save")
    st.markdown(
        "When connected, TaskKeeper uploads `taskkeeper.db` to your Dropbox "
        "automatically every time the page loads, keeping an off-site backup in sync."
    )

    service = _load_service(settings)

    if service is None:
        # No credentials at all → show credential entry form
        _render_credentials_form(settings)
    elif not service.is_configured():
        # Have key + secret, but no refresh token → OAuth flow
        _render_oauth_flow(service, settings)
    else:
        # Fully configured
        _render_connected(service, settings, db_path)
