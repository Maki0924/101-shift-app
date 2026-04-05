"""期間（periods）リポジトリ"""

import sqlite3
from datetime import datetime

from src.db.connection import get_connection, transaction


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── 取得 ──────────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    """全期間を作成日時降順で返す。"""
    rows = get_connection().execute(
        "SELECT * FROM periods ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(period_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM periods WHERE id = ?", (period_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_status(status: str) -> list[dict]:
    rows = get_connection().execute(
        "SELECT * FROM periods WHERE status = ? ORDER BY created_at DESC", (status,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── 重複チェック ───────────────────────────────────────────────────────────────

def has_overlap(start_date: str, end_date: str, exclude_id: int | None = None) -> bool:
    """指定した日付範囲と重複する期間が存在するか確認する（境界日を含む inclusive）。

    Args:
        start_date: 確認する期間の開始日（YYYY-MM-DD）
        end_date: 確認する期間の終了日（YYYY-MM-DD）
        exclude_id: 重複判定から除外する期間ID（編集時に自己除外するために使用）
    """
    sql = """
        SELECT 1 FROM periods
        WHERE start_date <= ? AND end_date >= ?
    """
    params: list = [end_date, start_date]

    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)

    return get_connection().execute(sql, params).fetchone() is not None


# ── 作成・更新・削除 ────────────────────────────────────────────────────────────

def create(name: str, start_date: str, end_date: str, submission_deadline: str) -> dict:
    """期間を新規作成し、作成したレコードを返す。"""
    now = _now()
    with transaction() as txn:
        cursor = txn.execute(
            """
            INSERT INTO periods (name, start_date, end_date, submission_deadline,
                                 status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'collecting', ?, ?)
            """,
            (name, start_date, end_date, submission_deadline, now, now),
        )
    return get_by_id(cursor.lastrowid)


def update(
    period_id: int,
    name: str,
    start_date: str,
    end_date: str,
    submission_deadline: str,
) -> dict | None:
    """期間の基本情報を更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            """
            UPDATE periods
            SET name = ?, start_date = ?, end_date = ?,
                submission_deadline = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, start_date, end_date, submission_deadline, now, period_id),
        )
    return get_by_id(period_id)


def update_status(period_id: int, status: str) -> dict | None:
    """ステータスを更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            "UPDATE periods SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, period_id),
        )
    return get_by_id(period_id)


def update_form_info(
    period_id: int,
    form_url: str | None,
    spreadsheet_id: str | None,
) -> dict | None:
    """form_url / spreadsheet_id を更新し、更新後のレコードを返す。"""
    now = _now()
    with transaction() as txn:
        txn.execute(
            "UPDATE periods SET form_url = ?, spreadsheet_id = ?, updated_at = ? WHERE id = ?",
            (form_url, spreadsheet_id, now, period_id),
        )
    return get_by_id(period_id)


def delete(period_id: int) -> None:
    """期間を削除する。"""
    with transaction() as txn:
        txn.execute("DELETE FROM periods WHERE id = ?", (period_id,))
