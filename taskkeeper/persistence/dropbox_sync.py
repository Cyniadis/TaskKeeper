"""Dropbox-backed persistence for Streamlit Cloud.

On cold start:  download taskkeeper.db from Dropbox → write to /tmp.
On every write: upload /tmp/taskkeeper.db → Dropbox (rate-limited).

Authentication uses a refresh token (offline access) — no browser flow
needed on the server, the SDK refreshes the access token automatically.

Setup
-----
1. Go to https://www.dropbox.com/developers/apps → Create app.
   - Choose "Scoped access" → "Full Dropbox" (or "App folder" for isolation).
   - Give it a name, click Create.
2. In the app's Permissions tab, enable: files.content.read, files.content.write.
   Click Submit.
3. In the Settings tab, note your App key and App secret.
4. Generate a refresh token by running this once locally:
       python -m taskkeeper.persistence.dropbox_sync
   Follow the printed instructions (visit URL, paste code).
5. Add to Streamlit secrets:
       DROPBOX_APP_KEY    = "..."
       DROPBOX_APP_SECRET = "..."
       DROPBOX_REFRESH_TOKEN = "..."

The DB is stored at /taskkeeper.db in your Dropbox app folder
(or root if Full Dropbox access was chosen). Override with the
DROPBOX_REMOTE_PATH secret if needed.

Dependencies (add to requirements.txt)
---------------------------------------
    dropbox>=12.0.2
"""
from __future__ import annotations

import io
import time
from pathlib import Path

_REMOTE_PATH_DEFAULT = "/TaskKeeper/taskkeeper.db"


class DropboxSync:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        refresh_token: str,
        db_path: Path,
        remote_path: str = _REMOTE_PATH_DEFAULT,
        min_push_interval: float = 30.0,
    ) -> None:
        self.db_path = db_path
        self.remote_path = remote_path
        self.min_push_interval = min_push_interval
        self._last_push: float = 0.0
        self._dbx = self._build_client(app_key, app_secret, refresh_token)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_secrets(cls, db_path: Path) -> "DropboxSync | None":
        """Build from st.secrets; return None if secrets aren't set."""
        try:
            import streamlit as st
            return cls(
                app_key=st.secrets["DROPBOX_APP_KEY"],
                app_secret=st.secrets["DROPBOX_APP_SECRET"],
                refresh_token=st.secrets["DROPBOX_REFRESH_TOKEN"],
                db_path=db_path,
                remote_path=st.secrets.get("DROPBOX_REMOTE_PATH", _REMOTE_PATH_DEFAULT),
            )
        except Exception:
            return None

    @staticmethod
    def _build_client(app_key: str, app_secret: str, refresh_token: str):
        import dropbox
        return dropbox.Dropbox(
            app_key=app_key,
            app_secret=app_secret,
            oauth2_refresh_token=refresh_token,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pull(self) -> str | None:
        """Download the DB from Dropbox to self.db_path.

        Skipped if the local file already exists (warm restart within the
        same /tmp lifetime). Returns a status string or None if skipped.
        """
        if self.db_path.exists():
            return None

        import dropbox
        try:
            _, response = self._dbx.files_download(self.remote_path)
        except dropbox.exceptions.ApiError:
            return None  # file doesn't exist yet — first deploy

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        content = response.content
        self.db_path.write_bytes(content)
        size_kb = len(content) / 1024
        return f"📥 Database pulled from Dropbox ({size_kb:.1f} KB)"

    def push(self, *, force: bool = False) -> str | None:
        """Upload self.db_path to Dropbox.

        Rate-limited to once per min_push_interval seconds unless
        force=True. Returns a status string or None if skipped.
        """
        if not self.db_path.exists():
            return None

        now = time.monotonic()
        if not force and (now - self._last_push) < self.min_push_interval:
            return None

        import dropbox
        content = self.db_path.read_bytes()
        self._dbx.files_upload(
            content,
            self.remote_path,
            mode=dropbox.files.WriteMode.overwrite,
        )
        self._last_push = time.monotonic()
        size_kb = len(content) / 1024
        return f"📤 Database saved to Dropbox ({size_kb:.1f} KB)"


# ------------------------------------------------------------------
# One-time token generator — run locally to get a refresh token:
#   python -m taskkeeper.persistence.dropbox_sync
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=== Dropbox refresh token generator ===\n")
    app_key = input("Paste your App key: ").strip()
    app_secret = input("Paste your App secret: ").strip()

    import dropbox
    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
        app_key,
        app_secret,
        token_access_type="offline",
    )
    url = auth_flow.start()
    print(f"\n1. Visit this URL:\n   {url}")
    print("2. Click 'Allow'")
    code = input("3. Paste the authorization code here: ").strip()

    try:
        result = auth_flow.finish(code)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)

    print("\n✅ Success! Add these to your Streamlit secrets:\n")
    print(f'DROPBOX_APP_KEY       = "{app_key}"')
    print(f'DROPBOX_APP_SECRET    = "{app_secret}"')
    print(f'DROPBOX_REFRESH_TOKEN = "{result.refresh_token}"')
