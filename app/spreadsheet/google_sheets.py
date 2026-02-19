"""Google Sheetsへのレシートデータ書き込み"""

from __future__ import annotations

import gspread

from app.auth.google_auth import get_google_credentials
from app.config import GOOGLE_SHEETS_SPREADSHEET_ID, GOOGLE_SHEETS_WORKSHEET_NAME
from app.models.receipt import Receipt


class GoogleSheetsClient:
    """Google Sheets操作クライアント"""

    def __init__(self) -> None:
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._worksheet: gspread.Worksheet | None = None

    def _ensure_connected(self) -> None:
        if self._client is None:
            creds = get_google_credentials()
            self._client = gspread.authorize(creds)

    def _get_worksheet(self) -> gspread.Worksheet:
        """ワークシートを取得（なければ作成）"""
        self._ensure_connected()

        if not GOOGLE_SHEETS_SPREADSHEET_ID:
            raise ValueError(
                "スプレッドシートIDが設定されていません。\n"
                ".envファイルにGOOGLE_SHEETS_SPREADSHEET_IDを設定してください。"
            )

        self._spreadsheet = self._client.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID)

        try:
            self._worksheet = self._spreadsheet.worksheet(GOOGLE_SHEETS_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            self._worksheet = self._spreadsheet.add_worksheet(
                title=GOOGLE_SHEETS_WORKSHEET_NAME, rows=1000, cols=15
            )
            self._setup_header()

        return self._worksheet

    def _setup_header(self) -> None:
        """ヘッダー行を設定"""
        if self._worksheet is None:
            return
        header = Receipt().to_sheet_header()
        self._worksheet.update("A1", [header])
        # ヘッダー行を太字にフォーマット
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

        # 既存データの最終行を取得
        existing = ws.get_all_values()
        if not existing:
            # ヘッダーがない場合は追加
            self._setup_header()
            start_row = 2
        else:
            start_row = len(existing) + 1

        # データを追加
        cell_range = f"A{start_row}"
        ws.update(cell_range, rows)

        return len(rows)

    def get_all_receipts(self) -> list[list[str]]:
        """全レシートデータを取得"""
        ws = self._get_worksheet()
        return ws.get_all_values()
