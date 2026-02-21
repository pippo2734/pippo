"""Google Sheetsへのレシートデータ書き込み"""

from __future__ import annotations

import gspread
from google.oauth2.credentials import Credentials

from app.models.receipt import Receipt


class GoogleSheetsClient:
    """Google Sheets操作クライアント"""

    def __init__(self, credentials: Credentials, spreadsheet_id: str, worksheet_name: str = "レシート") -> None:
        self._credentials = credentials
        self._spreadsheet_id = spreadsheet_id
        self._worksheet_name = worksheet_name
        self._client: gspread.Client | None = None
        self._worksheet: gspread.Worksheet | None = None

    def _ensure_connected(self) -> None:
        if self._client is None:
            self._client = gspread.authorize(self._credentials)

    def _get_worksheet(self) -> gspread.Worksheet:
        """ワークシートを取得（なければ作成）"""
        self._ensure_connected()

        if not self._spreadsheet_id:
            raise ValueError(
                "スプレッドシートIDが設定されていません。\n"
                "設定画面からGoogle SheetsのスプレッドシートIDを設定してください。"
            )

        spreadsheet = self._client.open_by_key(self._spreadsheet_id)

        try:
            self._worksheet = spreadsheet.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            self._worksheet = spreadsheet.add_worksheet(
                title=self._worksheet_name, rows=1000, cols=15
            )
            self._setup_header()

        return self._worksheet

    def _setup_header(self) -> None:
        """ヘッダー行を設定"""
        if self._worksheet is None:
            return
        header = Receipt().to_sheet_header()
        self._worksheet.update("A1", [header])
        self._worksheet.format("A1:K1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.95},
        })

    def append_receipt(self, receipt: Receipt) -> int:
        """レシートデータをスプレッドシートに追加

        Returns:
            追加された行数
        """
        ws = self._get_worksheet()
        rows = receipt.to_sheet_rows()

        existing = ws.get_all_values()
        if not existing:
            self._setup_header()
            start_row = 2
        else:
            start_row = len(existing) + 1

        cell_range = f"A{start_row}"
        ws.update(cell_range, rows)

        return len(rows)

    def get_all_receipts(self) -> list[list[str]]:
        """全レシートデータを取得"""
        ws = self._get_worksheet()
        return ws.get_all_values()
