"""DropboxService: optional auto-save of taskkeeper.db to Dropbox.

Uses a refresh token (long-lived) stored in st.secrets or in the
SettingsStore so the app can upload without any user interaction once
configured. The OAuth authorization-code flow is driven from the UI
(settings_tab.py) — this module only handles the token exchange and
the actual upload/download.

Daily backup
------------
On the first upload of each calendar day, the current remote file is
copied to /taskkeeper_backup_YYYY-MM-DD.db before being overwritten.
Subsequent uploads on the same day skip this step (the backup already
exists). The check is cheap: a single get_metadata call that returns
quickly with a 409 when the path is absent.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import streamlit as st

REDIRECT_URI = st.secrets["DROPBOX_REDIRECT_URI"]     # Dropbox requires one; we read the code from the URL bar
AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"
GET_METADATA_URL = "https://api.dropboxapi.com/2/files/get_metadata"

# All files live under this folder in the user's Dropbox.
FOLDER = "/TaskKeeper"
DROPBOX_PATH = f"{FOLDER}/taskkeeper.db"


def _daily_backup_path(today: date | None = None) -> str:
    d = today or date.today()
    return f"{FOLDER}/taskkeeper_backup_{d.isoformat()}.db"


def _export_path(today: date | None = None) -> str:
    d = today or date.today()
    return f"{FOLDER}/taskkeeper_export_{d.isoformat()}.db"


class DropboxService:
    """Thin wrapper around the Dropbox HTTP API — no SDK dependency."""

    def __init__(self, app_key: str, app_secret: str, refresh_token: str | None = None) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def authorization_url(self) -> str:
        """Build the URL the user must visit to authorize the app."""
        print(REDIRECT_URI)
        params = {
            "client_id": self.app_key,
            "response_type": "code",
            "token_access_type": "offline",   # gives us a refresh token
            "redirect_uri": REDIRECT_URI,
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        """Exchange an authorization code for a refresh token.

        Returns the refresh_token string and also stores it on self.
        """
        print(REDIRECT_URI)
        data = urllib.parse.urlencode({
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        }).encode()

        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
        # Basic auth: app_key:app_secret
        import base64
        creds = base64.b64encode(f"{self.app_key}:{self.app_secret}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())

        self.refresh_token = payload["refresh_token"]
        self._access_token = payload.get("access_token")
        return self.refresh_token

    def _get_access_token(self) -> str:
        """Return a valid short-lived access token, refreshing if needed."""
        if self._access_token:
            return self._access_token

        if not self.refresh_token:
            raise RuntimeError("No refresh token — complete the OAuth flow first.")

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }).encode()

        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
        import base64
        creds = base64.b64encode(f"{self.app_key}:{self.app_secret}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())

        self._access_token = payload["access_token"]
        return self._access_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remote_file_exists(self, path: str) -> bool:
        """Return True when `path` exists in Dropbox.

        Uses get_metadata — returns False on a 409 path_not_found error
        (the normal Dropbox way of saying "no such file"), re-raises
        anything else so genuine auth/network failures aren't swallowed.
        """
        token = self._get_access_token()
        data = json.dumps({"path": path}).encode()
        req = urllib.request.Request(GET_METADATA_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                # path_not_found — file simply doesn't exist yet
                return False
            raise

    def _download_remote(self, path: str) -> bytes:
        """Download the file at `path` from Dropbox and return its bytes."""
        token = self._get_access_token()
        api_args = json.dumps({"path": path})
        req = urllib.request.Request(DOWNLOAD_URL, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "")          # required to be empty for download
        req.add_header("Dropbox-API-Arg", api_args)
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def _upload_bytes(self, content: bytes, path: str, *, overwrite: bool = True) -> dict:
        """Upload raw bytes to `path` in Dropbox. Returns file metadata."""
        token = self._get_access_token()
        api_args = json.dumps({
            "path": path,
            "mode": "overwrite" if overwrite else "add",
            "autorename": not overwrite,
            "mute": True,
        })
        req = urllib.request.Request(UPLOAD_URL, data=content, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Dropbox-API-Arg", api_args)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _ensure_daily_backup(self) -> bool:
        """Copy the current remote DB to a dated backup path if not done today.

        Returns True when a backup was created, False when it already existed
        or the remote DB didn't exist yet (first-ever upload).

        Any exception is propagated — the caller (upload_db) decides whether
        to treat this as fatal or just log it.
        """
        backup_path = _daily_backup_path()
        if self._remote_file_exists(backup_path):
            return False   # already backed up today

        if not self._remote_file_exists(DROPBOX_PATH):
            return False   # nothing to back up yet

        content = self._download_remote(DROPBOX_PATH)
        self._upload_bytes(content, backup_path, overwrite=False)
        return True

    # ------------------------------------------------------------------
    # Public upload
    # ------------------------------------------------------------------

    def upload_db(self, db_path: Path) -> dict:
        """Upload `db_path` to Dropbox at DROPBOX_PATH, overwriting.

        Before the first upload of each calendar day, the existing remote
        file is copied to /taskkeeper_backup_YYYY-MM-DD.db so that the
        previous day's state is preserved. Subsequent uploads on the same
        day skip this step.

        Returns the Dropbox file metadata dict for the main upload.
        Raises urllib.error.HTTPError on API errors.
        """
        # Daily backup — best-effort: a failure here should not block saving.
        try:
            self._ensure_daily_backup()
        except Exception:
            pass  # logged by caller if desired; never prevent the live save

        db_bytes = db_path.read_bytes()
        return self._upload_bytes(db_bytes, DROPBOX_PATH, overwrite=True)

    def export_to_dropbox(self, db_path: Path) -> dict:
        """Copy the local DB to TaskKeeper/taskkeeper_export_YYYY-MM-DD.db.

        Uses autorename=True so repeated exports on the same day produce
        _export_2026-09-17.db, _export_2026-09-17 (1).db, etc. rather than
        silently overwriting an earlier export.

        Returns the Dropbox file metadata dict.
        """
        db_bytes = db_path.read_bytes()
        return self._upload_bytes(db_bytes, _export_path(), overwrite=False)

    def import_from_dropbox(self, local_path: Path) -> int:
        """Download TaskKeeper/taskkeeper.db from Dropbox and write it to
        `local_path`, replacing whatever is there.

        Returns the number of bytes written.
        Raises FileNotFoundError (wrapped) when the remote file is absent.
        """
        if not self._remote_file_exists(DROPBOX_PATH):
            raise FileNotFoundError(
                f"No database found at {DROPBOX_PATH} in your Dropbox."
            )
        content = self._download_remote(DROPBOX_PATH)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return len(content)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.refresh_token)