"""Google OAuth2認証（Sheets API / Drive API用）"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import BASE_DIR, GOOGLE_OAUTH_SCOPES

TOKEN_PATH = BASE_DIR / "token.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"


def get_google_credentials() -> Credentials:
    """Google OAuth2のクレデンシャルを取得

    初回実行時はブラウザで認証フローが起動します。
    2回目以降はトークンファイルから読み込みます。
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GOOGLE_OAUTH_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth2クレデンシャルファイルが見つかりません: {CREDENTIALS_PATH}\n"
                    "Google Cloud Consoleからcredentials.jsonをダウンロードし、"
                    "プロジェクトルートに配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), GOOGLE_OAUTH_SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return creds
