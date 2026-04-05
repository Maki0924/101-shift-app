"""SQLite接続管理

- PRAGMA foreign_keys = ON を強制
- コンテキストマネージャーでトランザクションを管理
"""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from src.utils.logger import get_logger
from src.utils.paths import APP_DIR

_DB_FILE = APP_DIR / "shift_app.db"
_connection: sqlite3.Connection | None = None


def init_connection() -> sqlite3.Connection:
    """DB接続を初期化して返す。すでに接続済みの場合は既存の接続を返す。"""
    global _connection
    if _connection is not None:
        return _connection

    _connection = sqlite3.connect(_DB_FILE, check_same_thread=False)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA foreign_keys = ON")
    _connection.commit()

    get_logger().info("DB connection initialized: %s", _DB_FILE)
    return _connection


def get_connection() -> sqlite3.Connection:
    if _connection is None:
        raise RuntimeError("DB connection is not initialized. Call init_connection() first.")
    return _connection


def close_connection() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        get_logger().info("DB connection closed")


@contextmanager
def transaction() -> Generator[sqlite3.Connection, None, None]:
    """トランザクションコンテキストマネージャー。

    with transaction() as conn:
        conn.execute(...)

    例外発生時は自動ロールバック、正常終了時はコミット。
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
