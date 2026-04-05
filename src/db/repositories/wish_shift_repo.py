"""希望シフト（wish_shifts）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_by_period(period_id: int) -> list[dict]:
    """期間内の全希望シフトを返す。"""
    rows = get_connection().execute(
        "SELECT * FROM wish_shifts WHERE period_id = ? ORDER BY staff_id ASC, work_date ASC",
        (period_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_period_and_staff(period_id: int, staff_id: int) -> list[dict]:
    rows = get_connection().execute(
        "SELECT * FROM wish_shifts WHERE period_id = ? AND staff_id = ? ORDER BY work_date ASC",
        (period_id, staff_id),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def rebuild_bulk(period_id: int, staff_id: int, shifts: list[dict]) -> None:
    """スタッフの希望シフトを全削除してから再生成する（採用処理用）。

    ON CONFLICT UPSERT ではなく DELETE+INSERT のため、rebuild_bulk と命名。
    shifts の各要素は {"work_date": str, "start_time": float, "end_time": float, "submission_id": int}
    勤務可能日のレコードのみを渡すこと（NULL/NULL は含めない）。
    """
    now = _now()
    with transaction() as txn:
        txn.execute(
            "DELETE FROM wish_shifts WHERE period_id = ? AND staff_id = ?",
            (period_id, staff_id),
        )
        for s in shifts:
            txn.execute(
                """
                INSERT INTO wish_shifts
                    (period_id, staff_id, work_date, start_time, end_time, submission_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    period_id, staff_id,
                    s["work_date"], s["start_time"], s["end_time"], s["submission_id"],
                    now, now,
                ),
            )


def delete_by_period_and_staff(period_id: int, staff_id: int) -> None:
    """スタッフの期間内希望シフトを全削除する。"""
    with transaction() as txn:
        txn.execute(
            "DELETE FROM wish_shifts WHERE period_id = ? AND staff_id = ?",
            (period_id, staff_id),
        )
