import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Google Cloud Vision
GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS", "credentials.json"
)

# Google Sheets
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
GOOGLE_SHEETS_WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "レシート")

# Google OAuth2
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# MoneyForward ME
MONEYFORWARD_EMAIL = os.getenv("MONEYFORWARD_EMAIL", "")
MONEYFORWARD_PASSWORD = os.getenv("MONEYFORWARD_PASSWORD", "")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "change-me")
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
EXPORT_DIR = BASE_DIR / os.getenv("EXPORT_DIR", "exports")

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
