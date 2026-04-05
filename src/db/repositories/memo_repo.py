"""店長メモ（manager_memos）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_one(period_id: int, staff_id: int, work_date: str) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM manager_memos WHERE period_id = ? AND staff_id = ? AND work_date = ?",
        (period_id, staff_id, work_date),
    ).fetchone()
    return _row_to_dict(row) if row else None


def upsert(period_id: int, staff_id: int, work_date: str, memo_text: str | None) -> dict | None:
    """店長メモを UPSERT し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO manager_memos
                (period_id, staff_id, work_date, memo_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_id, staff_id, work_date) DO UPDATE SET
                memo_text  = excluded.memo_text,
                updated_at = excluded.updated_at
            """,
            (period_id, staff_id, work_date, memo_text, now, now),
        )
    return get_one(period_id, staff_id, work_date)
