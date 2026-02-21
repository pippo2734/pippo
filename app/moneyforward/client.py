"""MoneyForward ME連携クライアント

MoneyForward MEへのデータ連携を2つの方法で提供:
1. Webスクレイピングによる直接入力（API非公開のため）
2. CSVエクスポート → 手動インポート
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from io import StringIO
from pathlib import Path

from app.config import EXPORT_DIR
from app.models.receipt import Receipt

MF_BASE_URL = "https://moneyforward.com"
MF_CREATE_URL = f"{MF_BASE_URL}/cf/create"


class MoneyForwardClient:
    """MoneyForward ME操作クライアント"""

    def __init__(self, mf_email: str = "", mf_password: str = "") -> None:
        self._email = mf_email
        self._password = mf_password
        self._client = None
        self._authenticated = False

    async def _ensure_login(self) -> None:
        if self._authenticated and self._client:
            return

        if not self._email or not self._password:
            raise ValueError(
                "MoneyForward MEの認証情報が設定されていません。\n"
                "設定画面からメールアドレスとパスワードを設定してください。"
            )

        import httpx
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            headers={
                "User-Agent": "ReceiptScanner/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

        login_page = await self._client.get(f"{MF_BASE_URL}/sign_in")
        csrf_token = self._extract_csrf_token(login_page.text)

        response = await self._client.post(
            f"{MF_BASE_URL}/sign_in",
            data={
                "authenticity_token": csrf_token,
                "sign_in_session_service[email]": self._email,
                "sign_in_session_service[password]": self._password,
            },
        )

        if response.status_code != 200 or "sign_in" in str(response.url):
            raise RuntimeError("MoneyForward MEへのログインに失敗しました。")

        self._authenticated = True

    async def register_receipt(self, receipt: Receipt) -> dict:
        """レシートデータをMoneyForward MEに直接登録"""
        await self._ensure_login()
        results = {"success": True, "registered_count": 0, "errors": []}

        for item in receipt.items:
            try:
                page = await self._client.get(MF_CREATE_URL)
                csrf_token = self._extract_csrf_token(page.text)

                response = await self._client.post(
                    MF_CREATE_URL,
                    data={
                        "authenticity_token": csrf_token,
                        "user_asset_act[is_transfer]": "0",
                        "user_asset_act[is_income]": "0",
                        "user_asset_act[updated_at]": receipt.date_str,
                        "user_asset_act[content]": f"{receipt.store_name} {item.name}",
                        "user_asset_act[amount]": str(item.price),
                        "user_asset_act[large_category_id]": "",
                        "user_asset_act[middle_category_id]": "",
                        "commit": "保存",
                    },
                )

                if response.status_code in (200, 302):
                    results["registered_count"] += 1
                else:
                    results["errors"].append(f"{item.name}: HTTP {response.status_code}")
            except Exception as e:
                results["errors"].append(f"{item.name}: {e}")

        if results["errors"]:
            results["success"] = len(results["errors"]) == 0

        return results

    def export_csv(self, receipt: Receipt, filename: str | None = None) -> Path:
        """MoneyForward MEインポート用CSVを生成"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"moneyforward_{timestamp}.csv"

        filepath = EXPORT_DIR / filename
        rows = receipt.to_moneyforward_csv_rows()
        header = [
            "計算対象", "日付", "内容", "金額(税込)",
            "保有金融機関", "大項目", "中項目", "メモ", "振替",
        ]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

        return filepath

    def export_csv_string(self, receipt: Receipt) -> str:
        """CSV文字列として返す（ダウンロード用）"""
        rows = receipt.to_moneyforward_csv_rows()
        header = [
            "計算対象", "日付", "内容", "金額(税込)",
            "保有金融機関", "大項目", "中項目", "メモ", "振替",
        ]

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def _extract_csrf_token(html: str) -> str:
        match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
        if not match:
            match = re.search(r'<input[^>]+name="authenticity_token"[^>]+value="([^"]+)"', html)
        return match.group(1) if match else ""

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._authenticated = False
