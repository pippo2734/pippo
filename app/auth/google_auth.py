"""Google OAuth2認証（ログイン + Sheets API用）"""

from __future__ import annotations

import json
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_OAUTH_SCOPES,
)

# --- Starlette OAuth (ログイン用) ---

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": " ".join(GOOGLE_OAUTH_SCOPES)},
    authorize_params={"access_type": "offline", "prompt": "consent"},
)


# --- Google API Credentials (Sheets操作用) ---

def get_credentials_from_token(token_json: str) -> Credentials | None:
    """保存済みトークンからCredentialsを復元"""
    try:
        token_data = json.loads(token_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not token_data.get("token"):
        return None

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=GOOGLE_OAUTH_SCOPES,
    )

    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds
