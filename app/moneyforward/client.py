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

from app.auth.moneyforward_auth import MoneyForwardAuth
from app.config import EXPORT_DIR
from app.models.receipt import Receipt

MF_BASE_URL = "https://moneyforward.com"
MF_CREATE_URL = f"{MF_BASE_URL}/cf/create"


class MoneyForwardClient:
    """MoneyForward ME操作クライアント"""

    def __init__(self) -> None:
        self._auth = MoneyForwardAuth()

    async def register_receipt(self, receipt: Receipt) -> dict:
        """レシートデータをMoneyForward MEに直接登録

        Returns:
            登録結果 {"success": bool, "registered_count": int, "errors": list}
        """
        client = await self._auth.get_client()
        results = {"success": True, "registered_count": 0, "errors": []}

        for item in receipt.items:
            try:
                # 入力画面を取得してCSRFトークンを取得
                page = await client.get(MF_CREATE_URL)
                csrf_token = self._extract_csrf_token(page.text)

                # 支出データを登録
                response = await client.post(
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
                    results["errors"].append(
                        f"{item.name}: HTTP {response.status_code}"
                    )
            except Exception as e:
                results["errors"].append(f"{item.name}: {e}")

        if results["errors"]:
            results["success"] = len(results["errors"]) == 0

        return results

    def export_csv(self, receipt: Receipt, filename: str | None = None) -> Path:
        """MoneyForward MEインポート用CSVを生成

        MoneyForward MEの手動CSVインポートに対応したフォーマットで出力します。

        Returns:
            生成されたCSVファイルのパス
        """
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
        match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html
        )
        if match:
            return match.group(1)
        return ""

    async def close(self) -> None:
        await self._auth.close()
