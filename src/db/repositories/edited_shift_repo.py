"""編集シフト（edited_shifts）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_by_period(period_id: int) -> list[dict]:
    """期間内の全編集シフトを返す。"""
    rows = (
        get_connection()
        .execute(
            "SELECT * FROM edited_shifts WHERE period_id = ? ORDER BY staff_id ASC, work_date ASC",
            (period_id,),
        )
        .fetchall()
    )
    return [_row_to_dict(r) for r in rows]


def get_by_period_and_staff(period_id: int, staff_id: int) -> list[dict]:
    rows = (
        get_connection()
        .execute(
            "SELECT * FROM edited_shifts WHERE period_id = ? AND staff_id = ? ORDER BY work_date ASC",
            (period_id, staff_id),
        )
        .fetchall()
    )
    return [_row_to_dict(r) for r in rows]


def get_one(period_id: int, staff_id: int, work_date: str) -> dict | None:
    row = (
        get_connection()
        .execute(
            "SELECT * FROM edited_shifts WHERE period_id = ? AND staff_id = ? AND work_date = ?",
            (period_id, staff_id, work_date),
        )
        .fetchone()
    )
    return _row_to_dict(row) if row else None


def upsert(
    period_id: int,
    staff_id: int,
    work_date: str,
    start_time: float | None,
    end_time: float | None,
) -> dict | None:
    """編集シフトを UPSERT し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            INSERT INTO edited_shifts
                (period_id, staff_id, work_date, start_time, end_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_id, staff_id, work_date) DO UPDATE SET
                start_time = excluded.start_time,
                end_time   = excluded.end_time,
                updated_at = excluded.updated_at
            """,
            (period_id, staff_id, work_date, start_time, end_time, now, now),
        )
    return get_one(period_id, staff_id, work_date)


def upsert_bulk(period_id: int, staff_id: int, shifts: list[dict]) -> None:
    """スタッフの編集シフトを一括 UPSERT する（一括反映用）。

    shifts の各要素は {"work_date": str, "start_time": float|None, "end_time": float|None}
    """
    now = _now()
    with transaction() as txn:
        for s in shifts:
            txn.execute(
                """
                INSERT INTO edited_shifts
                    (period_id, staff_id, work_date, start_time, end_time, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(period_id, staff_id, work_date) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time   = excluded.end_time,
                    updated_at = excluded.updated_at
                """,
                (period_id, staff_id, s["work_date"], s.get("start_time"), s.get("end_time"), now, now),
            )


def clear(period_id: int, staff_id: int, work_date: str) -> None:
    """指定セルを「勤務なし（NULL/NULL）」に設定する（クリアボタン用）。"""
    upsert(period_id, staff_id, work_date, None, None)


def replace_bulk(period_id: int, staff_id: int, shifts: list[dict]) -> None:
    """スタッフの編集シフトを全削除してから再生成する（Undo/Redo一括復元用）。

    upsert_bulk と異なり、shifts に含まれない日付のレコードも削除される。
    shifts の各要素は {"work_date": str, "start_time": float|None, "end_time": float|None}
    shifts が空の場合は全削除のみ行う。
    """
    now = _now()
    with transaction() as txn:
        txn.execute(
            "DELETE FROM edited_shifts WHERE period_id = ? AND staff_id = ?",
            (period_id, staff_id),
        )
        for s in shifts:
            txn.execute(
                """
                INSERT INTO edited_shifts
                    (period_id, staff_id, work_date, start_time, end_time, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (period_id, staff_id, s["work_date"], s.get("start_time"), s.get("end_time"), now, now),
            )


def delete(period_id: int, staff_id: int, work_date: str) -> None:
    """指定セルのレコードを削除する（未編集状態に戻す、Undo用）。"""
    with transaction() as txn:
        txn.execute(
            "DELETE FROM edited_shifts WHERE period_id = ? AND staff_id = ? AND work_date = ?",
            (period_id, staff_id, work_date),
        )
