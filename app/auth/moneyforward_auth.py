"""MoneyForward ME認証クライアント

MoneyForward MEは公式のパブリックAPIを提供していないため、
セッションベースの認証を実装します。
"""

from __future__ import annotations

import httpx

from app.config import MONEYFORWARD_EMAIL, MONEYFORWARD_PASSWORD

MF_BASE_URL = "https://moneyforward.com"
MF_LOGIN_URL = f"{MF_BASE_URL}/sign_in"
MF_SESSION_URL = f"{MF_BASE_URL}/sign_in"


class MoneyForwardAuth:
    """MoneyForward MEのセッション認証"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

    async def get_client(self) -> httpx.AsyncClient:
        """認証済みHTTPクライアントを取得"""
        if self._client is None or not self._authenticated:
            await self._login()
        return self._client

    async def _login(self) -> None:
        """MoneyForward MEにログイン"""
        if not MONEYFORWARD_EMAIL or not MONEYFORWARD_PASSWORD:
            raise ValueError(
                "MoneyForward MEの認証情報が設定されていません。\n"
                ".envファイルにMONEYFORWARD_EMAILとMONEYFORWARD_PASSWORDを設定してください。"
            )

        self._client = httpx.AsyncClient(
            follow_redirects=True,
            headers={
                "User-Agent": "ReceiptScanner/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

        # CSRFトークンを取得
        login_page = await self._client.get(MF_LOGIN_URL)
        csrf_token = self._extract_csrf_token(login_page.text)

        # ログインリクエスト
        response = await self._client.post(
            MF_SESSION_URL,
            data={
                "authenticity_token": csrf_token,
                "sign_in_session_service[email]": MONEYFORWARD_EMAIL,
                "sign_in_session_service[password]": MONEYFORWARD_PASSWORD,
            },
        )

        if response.status_code != 200 or "sign_in" in str(response.url):
            raise RuntimeError(
                "MoneyForward MEへのログインに失敗しました。\n"
                "メールアドレスとパスワードを確認してください。"
            )

        self._authenticated = True

    @staticmethod
    def _extract_csrf_token(html: str) -> str:
        """HTMLからCSRFトークンを抽出"""
        import re

        match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html
        )
        if not match:
            match = re.search(
                r'<input[^>]+name="authenticity_token"[^>]+value="([^"]+)"', html
            )
        if match:
            return match.group(1)
        return ""

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._authenticated = False
