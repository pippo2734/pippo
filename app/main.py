"""レシートスキャナー - メインアプリケーション

レシート画像をアップロード → OCR解析 → Google Sheets保存 → MoneyForward ME連携
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_HOST, APP_PORT, UPLOAD_DIR
from app.models.receipt import Receipt
from app.moneyforward.client import MoneyForwardClient
from app.scanner.ocr import scan_receipt
from app.spreadsheet.google_sheets import GoogleSheetsClient

app = FastAPI(
    title="レシートスキャナー",
    description="レシートを読み取り、スプレッドシートに保存し、MoneyForward MEに連携するツール",
    version="1.0.0",
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ---------- ページ ----------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインページ（アップロードフォーム）"""
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- API ----------


@app.post("/api/scan")
async def api_scan_receipt(file: UploadFile = File(...)):
    """レシート画像をスキャンして構造化データを返す"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    # ファイルを一時保存
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    save_path.write_bytes(content)

    try:
        receipt = scan_receipt(str(save_path))
        return JSONResponse(content={
            "success": True,
            "receipt": receipt.model_dump(mode="json"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)


@app.post("/api/scan-and-save")
async def api_scan_and_save(file: UploadFile = File(...)):
    """レシートをスキャン → Google Sheetsに保存"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    save_path.write_bytes(content)

    try:
        # OCRスキャン
        receipt = scan_receipt(str(save_path))

        # Google Sheetsに保存
        sheets = GoogleSheetsClient()
        rows_added = sheets.append_receipt(receipt)

        return JSONResponse(content={
            "success": True,
            "receipt": receipt.model_dump(mode="json"),
            "sheets": {
                "rows_added": rows_added,
                "message": f"{rows_added}行をスプレッドシートに追加しました",
            },
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)


@app.post("/api/scan-and-sync")
async def api_scan_and_sync(file: UploadFile = File(...)):
    """レシートをスキャン → Google Sheets保存 → MoneyForward ME連携（フルフロー）"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    save_path.write_bytes(content)

    mf_client = MoneyForwardClient()

    try:
        # 1. OCRスキャン
        receipt = scan_receipt(str(save_path))

        # 2. Google Sheetsに保存
        sheets = GoogleSheetsClient()
        rows_added = sheets.append_receipt(receipt)

        # 3. MoneyForward MEに連携
        mf_result = await mf_client.register_receipt(receipt)

        # 4. CSV もバックアップとして生成
        csv_path = mf_client.export_csv(receipt)

        return JSONResponse(content={
            "success": True,
            "receipt": receipt.model_dump(mode="json"),
            "sheets": {
                "rows_added": rows_added,
                "message": f"{rows_added}行をスプレッドシートに追加しました",
            },
            "moneyforward": {
                "registered_count": mf_result["registered_count"],
                "errors": mf_result["errors"],
                "csv_backup": str(csv_path),
            },
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)
        await mf_client.close()


@app.post("/api/export-csv")
async def api_export_csv(file: UploadFile = File(...)):
    """レシートをスキャン → MoneyForward用CSVをダウンロード"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    save_path.write_bytes(content)

    try:
        receipt = scan_receipt(str(save_path))
        mf_client = MoneyForwardClient()
        csv_content = mf_client.export_csv_string(receipt)

        return StreamingResponse(
            iter([csv_content.encode("utf-8-sig")]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=moneyforward_import.csv"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "receipt-scanner"}


# ---------- 起動 ----------


def start():
    import uvicorn

    uvicorn.run("app.main:app", host=APP_HOST, port=int(APP_PORT), reload=True)


if __name__ == "__main__":
    start()
