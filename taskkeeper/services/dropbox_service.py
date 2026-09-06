"""DropboxService: optional auto-save of taskkeeper.db to Dropbox.

Uses a refresh token (long-lived) stored in st.secrets or in the
SettingsStore so the app can upload without any user interaction once
configured. The OAuth authorization-code flow is driven from the UI
(settings_tab.py) — this module only handles the token exchange and
the actual upload/download.
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
import json
from pathlib import Path
from typing import Any


REDIRECT_URI = "https://localhost"   # Dropbox requires one; we read the code from the URL bar
AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
DROPBOX_PATH = "/taskkeeper.db"


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
    # Upload
    # ------------------------------------------------------------------

    def upload_db(self, db_path: Path) -> dict:
        """Upload `db_path` to Dropbox at DROPBOX_PATH, overwriting.

        Returns the Dropbox file metadata dict.
        Raises urllib.error.HTTPError on API errors.
        """
        token = self._get_access_token()
        db_bytes = db_path.read_bytes()

        api_args = json.dumps({
            "path": DROPBOX_PATH,
            "mode": "overwrite",
            "autorename": False,
            "mute": True,
        })

        req = urllib.request.Request(UPLOAD_URL, data=db_bytes, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Dropbox-API-Arg", api_args)

        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.refresh_token)
