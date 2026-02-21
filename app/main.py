"""レシートスキャナー - メインアプリケーション

レシート画像をアップロード → OCR解析 → Google Sheets保存 → MoneyForward ME連携
マルチユーザー対応（Googleログイン）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth.google_auth import get_credentials_from_token, oauth
from app.config import APP_HOST, APP_PORT, APP_SECRET_KEY, APP_URL, UPLOAD_DIR
from app.models.database import (
    User,
    get_user_by_id,
    init_db,
    update_user_settings,
    upsert_user,
)
from app.models.receipt import Receipt
from app.moneyforward.client import MoneyForwardClient
from app.scanner.ocr import scan_receipt
from app.spreadsheet.google_sheets import GoogleSheetsClient

app = FastAPI(
    title="レシートスキャナー",
    description="レシートを読み取り、スプレッドシートに保存し、MoneyForward MEに連携するツール",
    version="2.0.0",
)

app.add_middleware(SessionMiddleware, secret_key=APP_SECRET_KEY)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
async def startup():
    init_db()


# ---------- ヘルパー ----------


def _get_current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def _require_user(request: Request) -> User:
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user


# ---------- 認証 ----------


@app.get("/login")
async def login(request: Request):
    """Googleログインページ"""
    if _get_current_user(request):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/auth/google")
async def auth_google(request: Request):
    """Google OAuth2 認証開始"""
    redirect_uri = f"{APP_URL}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    """Google OAuth2 コールバック"""
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo", {})

    if not userinfo.get("sub"):
        raise HTTPException(status_code=400, detail="Google認証に失敗しました")

    user = upsert_user(
        google_id=userinfo["sub"],
        email=userinfo.get("email", ""),
        name=userinfo.get("name", ""),
        picture=userinfo.get("picture", ""),
        google_token={
            "token": token.get("access_token"),
            "refresh_token": token.get("refresh_token"),
            "token_type": token.get("token_type"),
            "expires_at": token.get("expires_at"),
        },
    )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


# ---------- ページ ----------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインページ（アップロードフォーム）"""
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """ユーザー設定ページ"""
    user = _get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})


@app.post("/settings")
async def save_settings(request: Request):
    """ユーザー設定を保存"""
    user = _require_user(request)
    form = await request.form()

    update_user_settings(
        user_id=user.id,
        spreadsheet_id=str(form.get("spreadsheet_id", "")),
        worksheet_name=str(form.get("worksheet_name", "レシート")) or "レシート",
        mf_email=str(form.get("mf_email", "")),
        mf_password=str(form.get("mf_password", "")),
    )

    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ---------- API ----------


@app.post("/api/scan")
async def api_scan_receipt(request: Request, file: UploadFile = File(...)):
    """レシート画像をスキャンして構造化データを返す"""
    _require_user(request)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

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
async def api_scan_and_save(request: Request, file: UploadFile = File(...)):
    """レシートをスキャン → Google Sheetsに保存"""
    user = _require_user(request)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    if not user.spreadsheet_id:
        raise HTTPException(status_code=400, detail="スプレッドシートIDが設定されていません。設定画面から設定してください。")

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    save_path.write_bytes(content)

    try:
        receipt = scan_receipt(str(save_path))

        creds = get_credentials_from_token(user.google_token)
        if not creds:
            raise HTTPException(status_code=401, detail="Google認証の再ログインが必要です")

        sheets = GoogleSheetsClient(creds, user.spreadsheet_id, user.worksheet_name)
        rows_added = sheets.append_receipt(receipt)

        return JSONResponse(content={
            "success": True,
            "receipt": receipt.model_dump(mode="json"),
            "sheets": {
                "rows_added": rows_added,
                "message": f"{rows_added}行をスプレッドシートに追加しました",
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)


@app.post("/api/scan-and-sync")
async def api_scan_and_sync(request: Request, file: UploadFile = File(...)):
    """レシートをスキャン → Sheets保存 → MoneyForward ME連携（フルフロー）"""
    user = _require_user(request)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="画像ファイルをアップロードしてください")

    if not user.spreadsheet_id:
        raise HTTPException(status_code=400, detail="スプレッドシートIDが設定されていません。")

    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    save_path.write_bytes(content)

    mf_client = MoneyForwardClient(mf_email=user.mf_email, mf_password=user.mf_password)

    try:
        receipt = scan_receipt(str(save_path))

        creds = get_credentials_from_token(user.google_token)
        if not creds:
            raise HTTPException(status_code=401, detail="Google認証の再ログインが必要です")

        sheets = GoogleSheetsClient(creds, user.spreadsheet_id, user.worksheet_name)
        rows_added = sheets.append_receipt(receipt)

        mf_result = await mf_client.register_receipt(receipt)
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"処理エラー: {e}")
    finally:
        save_path.unlink(missing_ok=True)
        await mf_client.close()


@app.post("/api/export-csv")
async def api_export_csv(request: Request, file: UploadFile = File(...)):
    """レシートをスキャン → MoneyForward用CSVダウンロード"""
    _require_user(request)

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
            headers={"Content-Disposition": "attachment; filename=moneyforward_import.csv"},
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
