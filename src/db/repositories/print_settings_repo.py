"""期間別印刷設定（period_print_settings）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_by_period(period_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM period_print_settings WHERE period_id = ?", (period_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def upsert(period_id: int, print_from_date: str | None, print_to_date: str | None) -> dict | None:
    """印刷設定を UPSERT し、更新後のレコードを返す。

    印刷実行成功時のみ呼び出すこと（archived 期間では呼ばない）。
    """
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO period_print_settings
                (period_id, print_from_date, print_to_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(period_id) DO UPDATE SET
                print_from_date = excluded.print_from_date,
                print_to_date   = excluded.print_to_date,
                updated_at      = excluded.updated_at
            """,
            (period_id, print_from_date, print_to_date, now, now),
        )
    return get_by_period(period_id)
