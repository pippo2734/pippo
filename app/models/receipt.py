from __future__ import annotations

import re
from datetime import date, datetime
from pydantic import BaseModel, Field


class ReceiptItem(BaseModel):
    """レシート内の個別商品"""

    name: str = Field(description="商品名")
    quantity: int = Field(default=1, description="数量")
    unit_price: int = Field(default=0, description="単価（円）")
    price: int = Field(description="金額（円）")
    tax_category: str = Field(default="10%", description="税区分 (8% / 10%)")


class Receipt(BaseModel):
    """レシートの解析結果"""

    store_name: str = Field(default="", description="店舗名")
    date: date | None = Field(default=None, description="購入日")
    items: list[ReceiptItem] = Field(default_factory=list, description="商品一覧")
    subtotal: int = Field(default=0, description="小計（円）")
    tax: int = Field(default=0, description="消費税（円）")
    total: int = Field(default=0, description="合計（円）")
    payment_method: str = Field(default="", description="支払方法")
    raw_text: str = Field(default="", description="OCR生テキスト")

    @property
    def date_str(self) -> str:
        if self.date:
            return self.date.strftime("%Y/%m/%d")
        return ""

    def to_sheet_header(self) -> list[str]:
        return [
            "日付",
            "店舗名",
            "商品名",
            "数量",
            "単価",
            "金額",
            "税区分",
            "小計",
            "消費税",
            "合計",
            "支払方法",
        ]

    def to_sheet_rows(self) -> list[list[str]]:
        """スプレッドシート用の行データに変換"""
        rows = []
        for item in self.items:
            rows.append([
                self.date_str,
                self.store_name,
                item.name,
                str(item.quantity),
                str(item.unit_price),
                str(item.price),
                item.tax_category,
                str(self.subtotal),
                str(self.tax),
                str(self.total),
                self.payment_method,
            ])
        if not self.items:
            rows.append([
                self.date_str,
                self.store_name,
                "",
                "",
                "",
                "",
                "",
                str(self.subtotal),
                str(self.tax),
                str(self.total),
                self.payment_method,
            ])
        return rows

    def to_moneyforward_csv_rows(self) -> list[list[str]]:
        """MoneyForward MEインポート用CSV形式に変換

        MoneyForward MEのCSVインポート形式:
        計算対象, 日付, 内容, 金額(税込), 保有金融機関, 大項目, 中項目, メモ, 振替
        """
        rows = []
        for item in self.items:
            rows.append([
                "1",                          # 計算対象
                self.date_str,                # 日付
                f"{self.store_name} {item.name}",  # 内容
                str(item.price),              # 金額
                "",                           # 保有金融機関
                "食費" if self._is_food(item.name) else "日用品",  # 大項目
                "",                           # 中項目
                f"レシートスキャン",            # メモ
                "0",                          # 振替
            ])
        return rows

    @staticmethod
    def _is_food(item_name: str) -> bool:
        food_keywords = [
            "弁当", "おにぎり", "パン", "牛乳", "卵", "肉", "魚", "野菜",
            "果物", "飲料", "ジュース", "水", "茶", "コーヒー", "ビール",
            "酒", "米", "麺", "豆腐", "納豆", "ヨーグルト", "チーズ",
            "サラダ", "惣菜", "冷凍", "菓子", "スナック", "チョコ",
            "アイス", "ガム", "飴", "ドリンク", "食",
        ]
        return any(kw in item_name for kw in food_keywords)


def parse_date_from_text(text: str) -> date | None:
    """テキストから日付を抽出"""
    patterns = [
        r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})",
        r"(令和\d+)[年.](\d{1,2})[月.](\d{1,2})",
        r"(\d{1,2})[月/](\d{1,2})[日/]\s*(\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            try:
                if "令和" in str(groups[0]):
                    year_num = int(re.search(r"\d+", groups[0]).group())
                    year = 2018 + year_num
                    return date(year, int(groups[1]), int(groups[2]))
                if len(groups[0]) == 4:
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                return date(int(groups[2]), int(groups[0]), int(groups[1]))
            except (ValueError, AttributeError):
                continue
    return None


def parse_price(text: str) -> int:
    """価格文字列から数値を抽出"""
    cleaned = re.sub(r"[¥￥,、\s円]", "", text)
    match = re.search(r"\d+", cleaned)
    return int(match.group()) if match else 0
