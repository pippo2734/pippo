"""ユーザーデータベース（SQLite）"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import DATABASE_PATH


@dataclass
class User:
    id: int
    google_id: str
    email: str
    name: str
    picture: str
    spreadsheet_id: str
    worksheet_name: str
    mf_email: str
    mf_password: str
    google_token: str  # JSON string of OAuth token
    created_at: str
    updated_at: str


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """データベースとテーブルを初期化"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            picture TEXT NOT NULL DEFAULT '',
            spreadsheet_id TEXT NOT NULL DEFAULT '',
            worksheet_name TEXT NOT NULL DEFAULT 'レシート',
            mf_email TEXT NOT NULL DEFAULT '',
            mf_password TEXT NOT NULL DEFAULT '',
            google_token TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def upsert_user(
    google_id: str,
    email: str,
    name: str,
    picture: str,
    google_token: dict,
) -> User:
    """ユーザーを作成または更新"""
    conn = _get_conn()
    token_json = json.dumps(google_token)
    now = datetime.utcnow().isoformat()

    existing = conn.execute(
        "SELECT id FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE users SET email=?, name=?, picture=?, google_token=?, updated_at=?
               WHERE google_id=?""",
            (email, name, picture, token_json, now, google_id),
        )
    else:
        conn.execute(
            """INSERT INTO users (google_id, email, name, picture, google_token, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (google_id, email, name, picture, token_json, now, now),
        )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()
    conn.close()
    return _row_to_user(row)


def get_user_by_id(user_id: int) -> User | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def update_user_settings(
    user_id: int,
    spreadsheet_id: str,
    worksheet_name: str,
    mf_email: str,
    mf_password: str,
) -> User | None:
    """ユーザー設定を更新"""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """UPDATE users SET spreadsheet_id=?, worksheet_name=?, mf_email=?, mf_password=?, updated_at=?
           WHERE id=?""",
        (spreadsheet_id, worksheet_name, mf_email, mf_password, now, user_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        google_id=row["google_id"],
        email=row["email"],
        name=row["name"],
        picture=row["picture"],
        spreadsheet_id=row["spreadsheet_id"],
        worksheet_name=row["worksheet_name"],
        mf_email=row["mf_email"],
        mf_password=row["mf_password"],
        google_token=row["google_token"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
