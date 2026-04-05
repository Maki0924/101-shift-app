"""手動色付け（cell_marks）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_one(period_id: int, staff_id: int, work_date: str) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM cell_marks WHERE period_id = ? AND staff_id = ? AND work_date = ?",
        (period_id, staff_id, work_date),
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_period(period_id: int) -> list[dict]:
    rows = get_connection().execute(
        "SELECT * FROM cell_marks WHERE period_id = ?", (period_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert(period_id: int, staff_id: int, work_date: str, mark_color: str) -> dict | None:
    """色付けを UPSERT（別色押下で上書き）し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO cell_marks
                (period_id, staff_id, work_date, mark_color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_id, staff_id, work_date) DO UPDATE SET
                mark_color = excluded.mark_color,
                updated_at = excluded.updated_at
            """,
            (period_id, staff_id, work_date, mark_color, now, now),
        )
    return get_one(period_id, staff_id, work_date)


def delete(period_id: int, staff_id: int, work_date: str) -> None:
    """色付けを削除する（同色再押下で解除）。"""
    with transaction() as txn:
        txn.execute(
            "DELETE FROM cell_marks WHERE period_id = ? AND staff_id = ? AND work_date = ?",
            (period_id, staff_id, work_date),
        )
