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
import sqlite3
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import streamlit as st

REDIRECT_URI = st.secrets["DROPBOX_REDIRECT_URI"]
AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"
GET_METADATA_URL = "https://api.dropboxapi.com/2/files/get_metadata"
LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
LIST_FOLDER_CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"

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
        params = {
            "client_id": self.app_key,
            "response_type": "code",
            "token_access_type": "offline",
            "redirect_uri": REDIRECT_URI,
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        data = urllib.parse.urlencode({
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        }).encode()

        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
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
                return False
            raise

    def _download_remote(self, path: str) -> bytes:
        token = self._get_access_token()
        api_args = json.dumps({"path": path})
        req = urllib.request.Request(DOWNLOAD_URL, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "")
        req.add_header("Dropbox-API-Arg", api_args)
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def _upload_bytes(self, content: bytes, path: str, *, overwrite: bool = True) -> dict:
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
        backup_path = _daily_backup_path()
        if self._remote_file_exists(backup_path):
            return False
        if not self._remote_file_exists(DROPBOX_PATH):
            return False
        content = self._download_remote(DROPBOX_PATH)
        self._upload_bytes(content, backup_path, overwrite=False)
        return True

    # ------------------------------------------------------------------
    # Folder listing
    # ------------------------------------------------------------------

    def list_db_files(self) -> list[dict]:
        """Return metadata dicts for every .db file in the TaskKeeper
        folder, sorted with taskkeeper.db first, then backups/exports
        newest-first by server_modified.

        Each dict has keys: path_lower, name, size, server_modified.
        Returns an empty list when the folder doesn't exist yet.
        """
        token = self._get_access_token()

        # list_folder
        data = json.dumps({"path": FOLDER, "recursive": False}).encode()
        req = urllib.request.Request(LIST_FOLDER_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return []  # folder doesn't exist yet
            raise

        entries = result.get("entries", [])

        # paginate if needed
        while result.get("has_more"):
            cursor = result["cursor"]
            cont_data = json.dumps({"cursor": cursor}).encode()
            cont_req = urllib.request.Request(LIST_FOLDER_CONTINUE_URL, data=cont_data, method="POST")
            cont_req.add_header("Authorization", f"Bearer {token}")
            cont_req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(cont_req) as resp:
                result = json.loads(resp.read())
            entries.extend(result.get("entries", []))

        db_files = [
            e for e in entries
            if e.get(".tag") == "file" and e.get("name", "").endswith(".db")
        ]

        # Sort: main file first, rest newest → oldest
        def _sort_key(e: dict) -> tuple:
            is_main = 0 if e["path_lower"] == DROPBOX_PATH.lower() else 1
            return (is_main, e.get("server_modified", ""))

        db_files.sort(key=_sort_key, reverse=False)
        # For non-main files we want newest first, so re-sort the tail
        main = [f for f in db_files if f["path_lower"] == DROPBOX_PATH.lower()]
        others = [f for f in db_files if f["path_lower"] != DROPBOX_PATH.lower()]
        others.sort(key=lambda e: e.get("server_modified", ""), reverse=True)
        return main + others

    # ------------------------------------------------------------------
    # Public upload
    # ------------------------------------------------------------------

    @staticmethod
    def _flush_to_disk(conn: "sqlite3.Connection") -> None:
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.commit()

    def upload_db(self, db_path: Path, conn: "sqlite3.Connection | None" = None) -> dict:
        if conn is not None:
            self._flush_to_disk(conn)
        try:
            self._ensure_daily_backup()
        except Exception:
            pass
        db_bytes = db_path.read_bytes()
        return self._upload_bytes(db_bytes, DROPBOX_PATH, overwrite=True)

    def export_to_dropbox(self, db_path: Path, conn: "sqlite3.Connection | None" = None) -> dict:
        if conn is not None:
            self._flush_to_disk(conn)
        db_bytes = db_path.read_bytes()
        return self._upload_bytes(db_bytes, _export_path(), overwrite=False)

    def import_from_dropbox(self, local_path: Path, remote_path: str = DROPBOX_PATH) -> int:
        """Download `remote_path` from Dropbox and write it to `local_path`.

        `remote_path` defaults to the main taskkeeper.db but can be any
        path returned by list_db_files() — backups, exports, etc.

        Returns the number of bytes written.
        Raises FileNotFoundError when the remote file is absent.
        """
        if not self._remote_file_exists(remote_path):
            raise FileNotFoundError(
                f"No database found at {remote_path} in your Dropbox."
            )
        content = self._download_remote(remote_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return len(content)

    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.refresh_token)