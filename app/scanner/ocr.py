"""Google Cloud Vision APIを使ったレシートOCR処理"""

from __future__ import annotations

import re
from pathlib import Path

from google.cloud import vision

from app.models.receipt import Receipt, ReceiptItem, parse_date_from_text, parse_price


def extract_text_from_image(image_path: str | Path) -> str:
    """画像ファイルからテキストを抽出"""
    client = vision.ImageAnnotatorClient()

    with open(image_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)
    response = client.text_detection(
        image=image,
        image_context=vision.ImageContext(language_hints=["ja"]),
    )

    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    texts = response.text_annotations
    if not texts:
        return ""

    return texts[0].description


def parse_receipt_text(raw_text: str) -> Receipt:
    """OCRテキストをレシートデータに構造化"""
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    store_name = _extract_store_name(lines)
    receipt_date = parse_date_from_text(raw_text)
    items = _extract_items(lines)
    subtotal, tax, total = _extract_totals(lines)
    payment_method = _extract_payment_method(raw_text)

    # 合計が取れなかった場合、商品合計から推定
    if total == 0 and items:
        total = sum(item.price for item in items)

    return Receipt(
        store_name=store_name,
        date=receipt_date,
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        payment_method=payment_method,
        raw_text=raw_text,
    )


def scan_receipt(image_path: str | Path) -> Receipt:
    """画像からレシートデータを抽出するメインエントリーポイント"""
    raw_text = extract_text_from_image(image_path)
    return parse_receipt_text(raw_text)


def _extract_store_name(lines: list[str]) -> str:
    """レシートの先頭部分から店舗名を推定"""
    skip_patterns = [
        r"^\d{4}[/\-]",           # 日付
        r"^〒",                    # 郵便番号
        r"^TEL",                   # 電話番号
        r"^\d{2,}-\d{2,}-\d{2,}", # 電話番号
        r"^レシート",
        r"^領収",
    ]

    for line in lines[:5]:
        if any(re.match(p, line) for p in skip_patterns):
            continue
        if len(line) >= 2 and not line.isdigit():
            return line

    return ""


def _extract_items(lines: list[str]) -> list[ReceiptItem]:
    """商品行を抽出"""
    items = []
    # 商品行のパターン: 商品名 + 金額
    item_pattern = re.compile(
        r"^(.+?)\s+[¥￥]?(\d{1,3}(?:,\d{3})*|\d+)\s*円?\s*$"
    )
    # 数量×単価パターン
    qty_pattern = re.compile(
        r"^(.+?)\s+(\d+)\s*[×xX]\s*[¥￥]?(\d{1,3}(?:,\d{3})*|\d+)\s+"
        r"[¥￥]?(\d{1,3}(?:,\d{3})*|\d+)\s*円?\s*$"
    )
    # 軽減税率マーカー
    reduced_tax_pattern = re.compile(r"[※＊\*]")

    skip_keywords = [
        "小計", "合計", "税", "消費", "内税", "外税", "釣", "預",
        "支払", "カード", "現金", "ポイント", "値引", "割引",
        "クレジット", "電子マネー", "合 計",
    ]

    for line in lines:
        if any(kw in line for kw in skip_keywords):
            continue

        has_reduced_tax = bool(reduced_tax_pattern.search(line))
        tax_cat = "8%" if has_reduced_tax else "10%"
        clean_line = reduced_tax_pattern.sub("", line).strip()

        # 数量×単価パターンを先に試す
        qty_match = qty_pattern.match(clean_line)
        if qty_match:
            name, qty, unit_p, total_p = qty_match.groups()
            items.append(ReceiptItem(
                name=name.strip(),
                quantity=int(qty),
                unit_price=parse_price(unit_p),
                price=parse_price(total_p),
                tax_category=tax_cat,
            ))
            continue

        # 商品名 + 金額パターン
        item_match = item_pattern.match(clean_line)
        if item_match:
            name, price_str = item_match.groups()
            price = parse_price(price_str)
            if price > 0 and len(name) >= 1:
                items.append(ReceiptItem(
                    name=name.strip(),
                    quantity=1,
                    unit_price=price,
                    price=price,
                    tax_category=tax_cat,
                ))

    return items


def _extract_totals(lines: list[str]) -> tuple[int, int, int]:
    """小計・消費税・合計を抽出"""
    subtotal = 0
    tax = 0
    total = 0

    for line in lines:
        price = _extract_line_price(line)
        if price == 0:
            continue

        if "合計" in line and "小計" not in line and "税" not in line:
            total = price
        elif "小計" in line:
            subtotal = price
        elif "消費税" in line or "内税" in line or "外税" in line:
            tax = price

    return subtotal, tax, total


def _extract_line_price(line: str) -> int:
    """行から金額を抽出"""
    match = re.search(r"[¥￥]?\s*(\d{1,3}(?:,\d{3})*|\d+)\s*円?\s*$", line)
    if match:
        return parse_price(match.group(1))
    return 0


def _extract_payment_method(text: str) -> str:
    """支払方法を推定"""
    methods = {
        "現金": ["現金", "つり", "釣り", "お預り", "お預かり"],
        "クレジットカード": ["クレジット", "VISA", "Master", "JCB", "AMEX", "カード"],
        "電子マネー": ["Suica", "PASMO", "iD", "QUICPay", "nanaco", "WAON", "楽天Edy"],
        "QRコード決済": ["PayPay", "LINE Pay", "d払い", "au PAY", "メルペイ", "楽天ペイ"],
    }

    text_upper = text.upper()
    for method, keywords in methods.items():
        if any(kw.upper() in text_upper for kw in keywords):
            return method

    return ""
